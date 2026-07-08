"""
AGRA Compliance Module — Agent-Side Compliance Engine (Rebuild)
10-stage pipeline for SOTR vs Vendor submission evaluation.

Endpoints:
  POST /api/compliance/ingest       — Ingest a single file from path, return doc_id
  POST /api/compliance/ingest-bundle — Ingest all 4 files, return doc_ids
  POST /api/compliance/run-pipeline  — Run the 10-stage evaluation pipeline
  GET  /api/compliance/standards     — List standards documents from vector store
  GET  /api/compliance/pipeline/{run_id}/result  — Get stored pipeline result
"""

import json
import logging
import os
import re
import threading
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.utils.auth_check import get_current_user
from api.models.compliance_models import (
    VerdictEnum, SeverityEnum, RecommendationEnum,
    ClauseResultData, PipelineResult, Citation, HouseRuleFlag,
    Contradiction, ProgressUpdate, RunStatusEnum,
    IngestBundleRequest, IngestBundleResponse,
    RunPipelineRequest, StandardsDocument,
)

logger = logging.getLogger("agra.compliance_engine")

router = APIRouter()

_ADMIN_BASE = os.getenv("AGRA_BACKEND_URL", "http://localhost:8000")
_DATA_DIR = Path(os.environ.get("AGRA_DATA_DIR", "/workspace/agra_data"))
if not _DATA_DIR.exists():
    _DATA_DIR = Path(__file__).resolve().parent.parent.parent / "agra_data"

_OUTPUTS_DIR = _DATA_DIR / "outputs"
_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# In-memory store for pipeline results (keyed by run_id)
_pipeline_results: Dict[str, PipelineResult] = {}
_pipeline_progress: Dict[str, dict] = {}


def _get_service_token() -> str:
    """Build a service JWT for backend→agent calls."""
    import jwt as pyjwt
    from datetime import datetime, timedelta
    secret = os.getenv("SECRET_KEY", "agra-secret-key-change-in-production")
    payload = {
        "sub": "agent_service",
        "role": "service",
        "exp": datetime.utcnow() + timedelta(minutes=5),
    }
    return pyjwt.encode(payload, secret, algorithm="HS256")


def _update_backend_progress(run_id: int, status: str, current: int = 0, total: int = 0, message: str = ""):
    """Call back to the backend to update run progress."""
    try:
        token = _get_service_token()
        httpx.patch(
            f"{_ADMIN_BASE}/api/compliance/runs/{run_id}/progress",
            json={"status": status, "progress": {"current": current, "total": total, "message": message}},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except Exception as e:
        logger.warning("Failed to update backend progress: %s", e)


def _update_backend_result(run_id: int, result: PipelineResult):
    """Store final pipeline result in backend."""
    try:
        token = _get_service_token()
        httpx.patch(
            f"{_ADMIN_BASE}/api/compliance/runs/{run_id}/complete",
            json=result.model_dump() if hasattr(result, 'model_dump') else result,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
    except Exception as e:
        logger.warning("Failed to update backend result: %s", e)


def _store_pipeline_result(run_id: str, result: PipelineResult):
    _pipeline_results[run_id] = result


def get_pipeline_result(run_id: str) -> Optional[PipelineResult]:
    return _pipeline_results.get(run_id)


# ═══════════════════════════════════════════════════════════════
#  ENDPOINT: INGEST SINGLE FILE
# ═══════════════════════════════════════════════════════════════

class IngestFileRequest(BaseModel):
    file_path: str
    filename: str
    doc_id: Optional[str] = None
    bundle_role: Optional[str] = None
    sub_role: Optional[str] = None


@router.post("/ingest")
async def ingest_file(
    body: IngestFileRequest,
    user: dict = Depends(get_current_user),
):
    from api.rag.pipeline import ingest_document

    doc_id = body.doc_id or str(uuid.uuid4())
    file_path = body.file_path
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=400, detail=f"File not found: {file_path}")

    events = []
    extra_md = {}
    if body.bundle_role:
        extra_md["bundle_role"] = body.bundle_role
    if body.sub_role:
        extra_md["sub_role"] = body.sub_role
    for event in ingest_document(
        file_path=file_path,
        filename=body.filename,
        doc_id=doc_id,
        uploaded_by_user_id=0,
        token="",
        source="compliance_upload",
        document_type=body.sub_role or "",
        extra_metadata=extra_md or None,
    ):
        events.append(event)

    last = events[-1] if events else {}
    if last.get("error"):
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {last['error']}")

    return {"doc_id": doc_id, "filename": body.filename}


# ═══════════════════════════════════════════════════════════════
#  ENDPOINT: INGEST BUNDLE (all 4 files)
# ═══════════════════════════════════════════════════════════════

@router.post("/ingest-bundle", response_model=IngestBundleResponse)
async def ingest_bundle(
    body: IngestBundleRequest,
    user: dict = Depends(get_current_user),
):
    from api.rag.pipeline import ingest_document

    bundles = [
        ("sotr_commercial", "SOTR", "commercial", body.sotr_commercial_path),
        ("sotr_technical", "SOTR", "technical", body.sotr_technical_path),
        ("vendor_commercial", "SUBMISSION", "commercial", body.vendor_commercial_path),
        ("vendor_dpr", "SUBMISSION", "dpr", body.vendor_dpr_path),
    ]

    doc_ids = {}
    for key, bundle_role, sub_role, file_path in bundles:
        if not os.path.isfile(file_path):
            raise HTTPException(status_code=400, detail=f"File not found for {key}: {file_path}")

        doc_id = str(uuid.uuid4())
        filename = Path(file_path).name

        events = []
        for event in ingest_document(
            file_path=file_path,
            filename=filename,
            doc_id=doc_id,
            uploaded_by_user_id=0,
            token="",
            source="compliance_upload",
            document_type=sub_role,
            extra_metadata={"bundle_role": bundle_role, "sub_role": sub_role},
        ):
            events.append(event)

        last = events[-1] if events else {}
        if last.get("error"):
            raise HTTPException(status_code=500, detail=f"Ingestion failed for {key}: {last['error']}")

        doc_ids[key] = doc_id
        logger.info("Ingested %s -> doc_id=%s", key, doc_id)

    return IngestBundleResponse(
        doc_id_sotr_com=doc_ids["sotr_commercial"],
        doc_id_sotr_tech=doc_ids["sotr_technical"],
        doc_id_vendor_com=doc_ids["vendor_commercial"],
        doc_id_vendor_dpr=doc_ids["vendor_dpr"],
    )


# ═══════════════════════════════════════════════════════════════
#  ENDPOINT: RUN PIPELINE
# ═══════════════════════════════════════════════════════════════

@router.post("/run-pipeline")
async def run_pipeline(
    body: RunPipelineRequest,
    user: dict = Depends(get_current_user),
):
    def _run():
        try:
            result = _execute_pipeline(body)
            _store_pipeline_result(str(body.run_id), result)
            _update_backend_result(body.run_id, result)
        except Exception as e:
            logger.exception("Pipeline failed for run_id=%s: %s", body.run_id, e)
            _update_backend_progress(body.run_id, "failed", 0, 0, str(e))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"run_id": body.run_id, "status": "started"}


def _execute_pipeline(body: RunPipelineRequest) -> PipelineResult:
    run_id = body.run_id
    _update_backend_progress(run_id, "ingesting", 0, 0, "Starting pipeline...")

    from api.rag.vector_store import get_store
    from api.rag.sotr_parser import extract_clauses
    from api.rag import llm as llm_engine

    store = get_store()

    # ── Stage 2: Clause Extraction ──
    _update_backend_progress(run_id, "parsing_clauses", 0, 0, "Retrieving SOTR documents...")

    sotr_com_chunks = store.get_chunks_by_doc(body.doc_id_sotr_com) or []
    sotr_tech_chunks = store.get_chunks_by_doc(body.doc_id_sotr_tech) or []

    sotr_com_text = "\n\n".join(c.get("text", "") for c in sotr_com_chunks if c.get("text"))
    sotr_tech_text = "\n\n".join(c.get("text", "") for c in sotr_tech_chunks if c.get("text"))

    # Extract clauses from both files separately with file prefix
    all_clauses: List[ClauseResultData] = []
    clause_counter = {"com": 0, "tech": 0}

    if sotr_com_text.strip():
        com_clauses = extract_clauses(sotr_com_text)
        logger.info("Parsed %d clauses from SOTR Commercial", len(com_clauses))
        for pc in com_clauses:
            clause_counter["com"] += 1
            all_clauses.append(ClauseResultData(
                clause_id=f"SOTR-C-{clause_counter['com']}",
                source_file="SOTR Commercial",
                source_doc_id=body.doc_id_sotr_com,
                requirement_text=pc.clause_text,
                acceptance_criterion=pc.acceptance_criteria or "",
            ))

    if sotr_tech_text.strip():
        tech_clauses = extract_clauses(sotr_tech_text)
        logger.info("Parsed %d clauses from SOTR Technical", len(tech_clauses))
        for pc in tech_clauses:
            clause_counter["tech"] += 1
            all_clauses.append(ClauseResultData(
                clause_id=f"SOTR-T-{clause_counter['tech']}",
                source_file="SOTR Technical",
                source_doc_id=body.doc_id_sotr_tech,
                requirement_text=pc.clause_text,
                acceptance_criterion=pc.acceptance_criteria or "",
            ))

    if not all_clauses:
        raise HTTPException(status_code=400, detail="No clauses extracted from SOTR documents")

    total = len(all_clauses)
    _update_backend_progress(run_id, "parsing_clauses", total, total, f"Extracted {total} clauses")

    # ── Stage 3: House Rules / Standards Lookup ──
    _update_backend_progress(run_id, "evaluating", 0, total, "Looking up house rules...")
    standard_texts = {}
    if body.selected_standards:
        for std_id in body.selected_standards:
            std_chunks = store.get_chunks_by_doc(std_id) or []
            std_text = "\n\n".join(c.get("text", "") for c in std_chunks if c.get("text"))
            if std_text.strip():
                standard_texts[std_id] = std_text

    # ── Stage 4: Vendor Evidence Retrieval ──
    vendor_chunks_com = store.get_chunks_by_doc(body.doc_id_vendor_com) or []
    vendor_chunks_dpr = store.get_chunks_by_doc(body.doc_id_vendor_dpr) or []
    vendor_com_text = "\n\n".join(c.get("text", "") for c in vendor_chunks_com if c.get("text"))
    vendor_dpr_text = "\n\n".join(c.get("text", "") for c in vendor_chunks_dpr if c.get("text"))
    combined_vendor_text = vendor_com_text + "\n\n" + vendor_dpr_text

    # ── Stage 5-7: Clause Evaluation, Missing Detection, Contradictions ──
    evaluated = 0
    for clause in all_clauses:
        evaluated += 1
        _update_backend_progress(run_id, "evaluating", evaluated, total, f"Evaluating clause {clause.clause_id}...")

        # RAG search across both vendor files for this clause
        vendor_evidence = _search_vendor_for_clause(store, clause.requirement_text, body)
        std_evidence = ""
        for std_id, std_text in standard_texts.items():
            if clause.requirement_text.lower()[:50] in std_text.lower():
                std_evidence += f"\n[Standard {std_id}]:\n{std_text[:2000]}\n"

        # ── Stage 5: LLM Evaluation ──
        verdict, finding, severity, recommendation, citations = _evaluate_clause_llm(
            clause, vendor_evidence, std_evidence, llm_engine
        )
        clause.verdict = verdict
        clause.finding = finding
        clause.severity = severity
        clause.recommendation = recommendation
        clause.citations = citations

        # ── Stage 6: Missing Clause Detection ──
        if not vendor_evidence.strip():
            clause.is_missing = True
            if clause.verdict != VerdictEnum.UNVERIFIABLE:
                clause.verdict = VerdictEnum.UNVERIFIABLE
                clause.finding = "No vendor evidence found addressing this requirement."

        # ── Stage 7: Contradiction Detection ──
        if vendor_com_text.strip() and vendor_dpr_text.strip():
            contradictions = _detect_contradictions(clause, vendor_com_text, vendor_dpr_text, llm_engine)
            if contradictions:
                clause.contradictions = contradictions

        # ── Stage 3 (cont): House Rule Violation Check ──
        if std_evidence.strip():
            hr_flag = _check_house_rule_violation(clause, std_evidence, llm_engine)
            if hr_flag:
                clause.house_rule_flag = hr_flag

    # ── Stage 8: Historical Feedback ──
    _update_backend_progress(run_id, "evaluating", total, total, "Checking historical feedback...")
    for clause in all_clauses:
        history = _query_historical_feedback(clause)
        if history:
            clause.historical_notes = history

    # ── Stage 9: Aggregation ──
    _update_backend_progress(run_id, "aggregating", 0, 0, "Aggregating results...")
    result = _aggregate_results(all_clauses)

    # ── Stage 10: Report Generation ──
    _update_backend_progress(run_id, "generating_report", 0, 0, "Generating report...")
    _generate_report_file(result, body)

    return result


def _search_vendor_for_clause(store, requirement: str, body: RunPipelineRequest) -> str:
    """Search across both vendor files for evidence relevant to a clause."""
    evidence_parts = []
    vendor_doc_ids = [body.doc_id_vendor_com, body.doc_id_vendor_dpr]
    for vid in vendor_doc_ids:
        if not vid:
            continue
        try:
            results = store.search(
                query=requirement[:500],
                top_k=3,
                doc_filter=[vid],
            )
            for r in results:
                txt = r.get("text", "")
                if txt:
                    evidence_parts.append(txt)
        except Exception:
            pass
    return "\n\n---\n\n".join(evidence_parts[:5])


def _evaluate_clause_llm(clause: ClauseResultData, vendor_text: str, standards_text: str, llm_engine) -> tuple:
    """Call LLM to evaluate a single clause and return (verdict, finding, severity, recommendation, citations)."""
    prompt = f"""You are a compliance officer for the Indian Coast Guard evaluating vendor submissions against SOTR requirements.

SOTR CLAUSE: {clause.clause_id}
Source: {clause.source_file}
Requirement: {clause.requirement_text}
Acceptance Criteria: {clause.acceptance_criterion}

{"APPLICABLE STANDARDS:" + standards_text if standards_text else "[No specific standards referenced]"}

VENDOR SUBMISSION (relevant excerpts):
{vendor_text if vendor_text.strip() else "[No relevant vendor evidence found]"}

Return ONLY valid JSON with exactly these fields:
{{
  "verdict": "COMPLIANT|PARTIAL|NON_COMPLIANT|UNVERIFIABLE",
  "finding": "precise technical statement explaining the basis of the verdict (max 200 words)",
  "severity": "Critical|Major|Minor|null",
  "recommendation": "APPROVE|APPROVE WITH CONDITIONS|REVISE AND RESUBMIT|REJECT|null",
  "citations": [{{"doc_name": "string", "version": "string", "page": 0, "excerpt": "string"}}]
}}

Guidelines:
- COMPLIANT: Vendor fully meets all acceptance criteria with clear evidence.
- PARTIAL: Vendor meets some criteria but has minor gaps or conditions.
- NON_COMPLIANT: Vendor does not meet criteria or has significant deviations.
- UNVERIFIABLE: Not enough evidence to determine compliance.
- severity must be null if verdict is COMPLIANT.
- recommendation must be null if verdict is COMPLIANT (or APPROVE).
- For NON_COMPLIANT, recommendation must be REVISE_AND_RESUBMIT or REJECT.
- For PARTIAL, recommendation must be APPROVE WITH CONDITIONS or REVISE_AND_RESUBMIT."""

    messages = [
        {"role": "system", "content": "You are a military compliance officer. Return only valid JSON with the exact schema specified."},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = llm_engine.generate(messages, max_tokens=800, temperature=0.1)
        parsed = _parse_llm_json(raw) or {}
    except Exception:
        parsed = {}

    verdict_str = str(parsed.get("verdict", "UNVERIFIABLE")).upper().strip()
    verdict_map = {
        "COMPLIANT": VerdictEnum.COMPLIANT,
        "PARTIAL": VerdictEnum.PARTIAL,
        "NON_COMPLIANT": VerdictEnum.NON_COMPLIANT,
        "UNVERIFIABLE": VerdictEnum.UNVERIFIABLE,
    }
    verdict = verdict_map.get(verdict_str, VerdictEnum.UNVERIFIABLE)

    severity_str = str(parsed.get("severity") or "").strip().lower()
    severity = None
    if severity_str == "critical":
        severity = SeverityEnum.CRITICAL
    elif severity_str == "major":
        severity = SeverityEnum.MAJOR
    elif severity_str == "minor":
        severity = SeverityEnum.MINOR

    rec_str = str(parsed.get("recommendation") or "").strip().upper()
    rec = None
    if "APPROVE WITH CONDITIONS" in rec_str:
        rec = RecommendationEnum.APPROVE_WITH_CONDITIONS
    elif "REVISE" in rec_str or "RESUBMIT" in rec_str:
        rec = RecommendationEnum.REVISE_AND_RESUBMIT
    elif rec_str == "REJECT":
        rec = RecommendationEnum.REJECT
    elif rec_str == "APPROVE":
        rec = RecommendationEnum.APPROVE

    citations_raw = parsed.get("citations", [])
    citations = []
    if isinstance(citations_raw, list):
        for c in citations_raw:
            if isinstance(c, dict):
                citations.append(Citation(
                    doc_name=c.get("doc_name", ""),
                    version=c.get("version", ""),
                    page=c.get("page", 0),
                    excerpt=c.get("excerpt", ""),
                ))

    finding = str(parsed.get("finding", "") or "")
    if not finding and verdict == VerdictEnum.UNVERIFIABLE:
        finding = "Insufficient vendor evidence to determine compliance."

    return verdict, finding, severity, rec, citations


def _check_house_rule_violation(clause: ClauseResultData, standards_text: str, llm_engine) -> Optional[HouseRuleFlag]:
    """Check if clause violates house rules even if SOTR wording is satisfied."""
    prompt = f"""Check if the following SOTR clause has any house rule / standards violation.

SOTR CLAUSE: {clause.clause_id}
Requirement: {clause.requirement_text}

APPLICABLE HOUSE RULES / STANDARDS:
{standards_text[:2000]}

Does this clause violate any house rule or standard? Return ONLY valid JSON:
{{
  "violated": true/false,
  "rule_reference": "name of the rule or standard violated, or empty string",
  "note": "explanation of the violation, or empty string"
}}"""

    messages = [
        {"role": "system", "content": "You are a compliance officer. Return only valid JSON."},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = llm_engine.generate(messages, max_tokens=300, temperature=0.1)
        parsed = _parse_llm_json(raw) or {}
        if parsed.get("violated"):
            return HouseRuleFlag(
                violated=True,
                rule_reference=str(parsed.get("rule_reference", "")),
                note=str(parsed.get("note", "")),
            )
    except Exception:
        pass
    return None


def _detect_contradictions(clause: ClauseResultData, vendor_com_text: str, vendor_dpr_text: str, llm_engine) -> List[Contradiction]:
    """Check for contradictory statements across vendor commercial and DPR files."""
    prompt = f"""Compare the vendor Commercial submission and DPR/Technical response for conflicting statements about this requirement.

SOTR CLAUSE: {clause.clause_id}
Requirement: {clause.requirement_text}

VENDOR COMMERCIAL:
{vendor_com_text[:2000]}

VENDOR DPR:
{vendor_dpr_text[:2000]}

Are there any contradictory statements? Return ONLY valid JSON:
{{
  "has_contradiction": true/false,
  "statement_a": "text from commercial",
  "statement_b": "text from DPR that contradicts",
  "note": "explanation"
}}"""

    messages = [
        {"role": "system", "content": "You are a compliance officer. Return only valid JSON."},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = llm_engine.generate(messages, max_tokens=300, temperature=0.1)
        parsed = _parse_llm_json(raw) or {}
        if parsed.get("has_contradiction"):
            return [Contradiction(
                between=["Vendor Commercial", "Vendor DPR"],
                statement_a=str(parsed.get("statement_a", "")),
                statement_b=str(parsed.get("statement_b", "")),
                note=str(parsed.get("note", "")),
            )]
    except Exception:
        pass
    return []


def _query_historical_feedback(clause: ClauseResultData) -> List:
    """Query prior compliance runs for historical context on this clause area."""
    try:
        token = _get_service_token()
        resp = httpx.get(
            f"{_ADMIN_BASE}/api/compliance/runs?limit=5",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            runs = resp.json()
            notes = []
            for run in runs[:3]:
                rid = run.get("id")
                if rid and rid != clause.source_doc_id:
                    notes.append({
                        "run_id": rid,
                        "reference_name": run.get("reference_name", ""),
                        "previous_verdict": None,
                        "note": f"Previous compliance run #{rid}: {run.get('reference_name', 'N/A')}",
                    })
            return notes
    except Exception:
        pass
    return []


def _aggregate_results(clauses: List[ClauseResultData]) -> PipelineResult:
    total = len(clauses)
    compliant = sum(1 for c in clauses if c.verdict == VerdictEnum.COMPLIANT)
    partial = sum(1 for c in clauses if c.verdict == VerdictEnum.PARTIAL)
    non_comp = sum(1 for c in clauses if c.verdict == VerdictEnum.NON_COMPLIANT)
    unver = sum(1 for c in clauses if c.verdict in (VerdictEnum.UNVERIFIABLE, None))

    scored = compliant + partial + non_comp
    denom = scored if scored > 0 else total
    overall = (compliant + partial * 0.5) / denom * 100 if denom > 0 else 0

    missing = sum(1 for c in clauses if c.is_missing)
    contra = sum(len(c.contradictions) for c in clauses)
    hr_viol = sum(1 for c in clauses if c.house_rule_flag and c.house_rule_flag.violated)

    if non_comp > 0:
        rec = RecommendationEnum.REJECT
    elif partial > compliant:
        rec = RecommendationEnum.REVISE_AND_RESUBMIT
    elif partial > 0:
        rec = RecommendationEnum.APPROVE_WITH_CONDITIONS
    else:
        rec = RecommendationEnum.APPROVE

    return PipelineResult(
        clauses=clauses,
        total_clauses=total,
        compliant_count=compliant,
        partial_count=partial,
        non_compliant_count=non_comp,
        unverifiable_count=unver,
        overall_score=round(overall, 1),
        recommendation=rec,
        missing_clause_count=missing,
        contradiction_count=contra,
        house_rule_violation_count=hr_viol,
    )


def _generate_report_file(result: PipelineResult, body: RunPipelineRequest):
    """Generate and save the .docx compliance report."""
    try:
        from api.generators.compliance_docx import generate_compliance_report
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', body.reference_name)[:100] or "compliance_report"
        filename = f"{safe_name}_Compliance_Report.docx"
        output_path = str(_OUTPUTS_DIR / filename)
        generate_compliance_report(result, body.reference_name, output_path)
        logger.info("Compliance report generated: %s", output_path)
    except Exception as e:
        logger.error("Failed to generate compliance report: %s", e)


def _parse_llm_json(raw: str) -> Optional[Dict]:
    """Parse JSON from LLM response, handling markdown fences."""
    try:
        cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r'```\s*$', '', cleaned.strip(), flags=re.MULTILINE)
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(cleaned[start:end])
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════
#  ENDPOINT: LIST STANDARDS
# ═══════════════════════════════════════════════════════════════

@router.get("/standards", response_model=List[StandardsDocument])
async def list_standards(
    user: dict = Depends(get_current_user),
):
    """List documents with document_type=standard from vector store."""
    from api.rag.vector_store import get_store
    store = get_store()
    standards = []

    try:
        results = store.search(
            query="standard rules regulations compliance policy",
            top_k=50,
            doc_type="standard",
        )
        seen_ids = set()
        for r in results:
            doc_id = r.get("doc_id", "")
            if doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)
            meta = r.get("metadata", {})
            standards.append(StandardsDocument(
                doc_id=doc_id,
                filename=meta.get("filename", doc_id),
                category=meta.get("category", ""),
                description=meta.get("description", ""),
            ))
    except Exception as e:
        logger.warning("Failed to query standards: %s", e)

    return standards


# ═══════════════════════════════════════════════════════════════
#  ENDPOINT: GET PIPELINE RESULT
# ═══════════════════════════════════════════════════════════════

@router.get("/pipeline/{run_id}/result")
async def get_pipeline_result_endpoint(
    run_id: str,
    user: dict = Depends(get_current_user),
):
    result = _pipeline_results.get(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Pipeline result not found")
    return result.model_dump() if hasattr(result, 'model_dump') else result
