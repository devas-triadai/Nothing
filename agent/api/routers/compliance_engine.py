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
    StandardRelevance, RelevanceRequest,
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
    # Try agent env first, then fall back to reading backend .env
    secret = os.getenv("SECRET_KEY")
    if not secret:
        from pathlib import Path
        backend_env = Path(__file__).resolve().parent.parent.parent.parent / "backend" / ".env"
        if backend_env.exists():
            for line in backend_env.read_text().splitlines():
                line = line.strip()
                if line.startswith("SECRET_KEY="):
                    secret = line.split("=", 1)[1]
                    break
    if not secret:
        secret = "agra-secret-key-change-in-production"
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


def _update_backend_result(run_id: int, result: PipelineResult, report_path: Optional[str] = None):
    """Store final pipeline result in backend."""
    try:
        payload = result.model_dump() if hasattr(result, 'model_dump') else dict(result)
        if report_path:
            payload["report_path"] = report_path
        token = _get_service_token()
        httpx.patch(
            f"{_ADMIN_BASE}/api/compliance/runs/{run_id}/complete",
            json=payload,
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
#  ENDPOINT: INGEST BUNDLE (all files)
# ═══════════════════════════════════════════════════════════════

@router.post("/ingest-bundle", response_model=IngestBundleResponse)
async def ingest_bundle(
    body: IngestBundleRequest,
    user: dict = Depends(get_current_user),
):
    from api.rag.pipeline import ingest_document

    # Build bundles list: SOTR files + DPR (single) + all vendor commercial files
    bundles = [
        ("sotr_commercial", "SOTR", "commercial", body.sotr_commercial_path),
        ("sotr_technical", "SOTR", "technical", body.sotr_technical_path),
        ("vendor_dpr", "SUBMISSION", "dpr", body.vendor_dpr_path),
    ]

    # Collect vendor commercial paths (support both single and multi-file)
    vendor_com_paths = []
    if body.vendor_commercial_paths:
        vendor_com_paths = body.vendor_commercial_paths
    elif body.vendor_commercial_path:
        vendor_com_paths = [body.vendor_commercial_path]

    doc_ids = {}
    vendor_commercial_doc_ids = []
    ingested_docs = []  # Track doc_ids for rollback on failure

    try:
        # Ingest SOTR + DPR files
        for key, bundle_role, sub_role, file_path in bundles:
            if not file_path:
                continue
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
            ingested_docs.append(doc_id)
            logger.info("Ingested %s -> doc_id=%s", key, doc_id)

        # Ingest all vendor commercial files (from ZIP or single)
        for idx, vc_path in enumerate(vendor_com_paths):
            if not vc_path:
                continue
            if not os.path.isfile(vc_path):
                logger.warning("Vendor commercial file not found, skipping: %s", vc_path)
                continue

            doc_id = str(uuid.uuid4())
            filename = Path(vc_path).name
            file_label = f"vendor_commercial_{idx}" if len(vendor_com_paths) > 1 else "vendor_commercial"

            events = []
            for event in ingest_document(
                file_path=vc_path,
                filename=filename,
                doc_id=doc_id,
                uploaded_by_user_id=0,
                token="",
                source="compliance_upload",
                document_type="commercial",
                extra_metadata={
                    "bundle_role": "SUBMISSION",
                    "sub_role": "commercial",
                    "zip_file_index": idx,
                    "zip_file_label": file_label,
                },
            ):
                events.append(event)

            last = events[-1] if events else {}
            if last.get("error"):
                raise HTTPException(status_code=500, detail=f"Ingestion failed for vendor commercial [{filename}]: {last['error']}")

            if idx == 0:
                doc_ids["vendor_commercial"] = doc_id  # Primary doc_id for backward compat
            vendor_commercial_doc_ids.append(doc_id)
            ingested_docs.append(doc_id)
            logger.info("Ingested vendor commercial %d/%d: %s -> doc_id=%s", idx + 1, len(vendor_com_paths), filename, doc_id)

    except Exception:
        # Rollback: delete all successfully ingested docs from vector store
        from api.rag.vector_store import get_store
        store = get_store()
        for did in ingested_docs:
            try:
                store.delete_document(did)
                logger.warning("Rolled back ingested doc_id=%s", did)
            except Exception as rollback_err:
                logger.warning("Rollback cleanup failed for doc_id=%s: %s", did, rollback_err)
        raise

    return IngestBundleResponse(
        doc_id_sotr_com=doc_ids.get("sotr_commercial"),
        doc_id_sotr_tech=doc_ids.get("sotr_technical"),
        doc_id_vendor_com=doc_ids.get("vendor_commercial"),
        doc_id_vendor_dpr=doc_ids.get("vendor_dpr"),
        vendor_commercial_doc_ids=vendor_commercial_doc_ids,
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
            result, report_path = _execute_pipeline(body)
            _store_pipeline_result(str(body.run_id), result)
            _update_backend_result(body.run_id, result, report_path)
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
    sotr_tech_chunks = store.get_chunks_by_doc(body.doc_id_sotr_tech) if body.doc_id_sotr_tech else []

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
    # Collect ALL vendor commercial doc IDs (primary + additional from ZIP)
    all_vendor_com_doc_ids = []
    if body.doc_id_vendor_com:
        all_vendor_com_doc_ids.append(body.doc_id_vendor_com)
    if body.doc_id_vendor_com_others:
        for did in body.doc_id_vendor_com_others:
            if did not in all_vendor_com_doc_ids:
                all_vendor_com_doc_ids.append(did)

    # Retrieve chunks from all vendor commercial files
    vendor_chunks_com = []
    for vc_doc_id in all_vendor_com_doc_ids:
        chunks = store.get_chunks_by_doc(vc_doc_id) or []
        vendor_chunks_com.extend(chunks)
    vendor_chunks_dpr = store.get_chunks_by_doc(body.doc_id_vendor_dpr) if body.doc_id_vendor_dpr else []

    vendor_com_text = "\n\n".join(c.get("text", "") for c in vendor_chunks_com if c.get("text"))
    vendor_dpr_text = "\n\n".join(c.get("text", "") for c in vendor_chunks_dpr if c.get("text"))
    combined_vendor_text = vendor_com_text + "\n\n" + vendor_dpr_text

    logger.info("Vendor evidence: %d com chunks from %d files, %d dpr chunks",
                len(vendor_chunks_com), len(all_vendor_com_doc_ids), len(vendor_chunks_dpr))

    # Pre-split vendor text into overlapping windows for fallback retrieval
    vendor_com_chunks_text = _split_into_windows(vendor_com_text, window_chars=1500, overlap_chars=200) if vendor_com_text.strip() else []
    vendor_dpr_chunks_text = _split_into_windows(vendor_dpr_text, window_chars=1500, overlap_chars=200) if vendor_dpr_text.strip() else []
    all_vendor_windows = vendor_com_chunks_text + vendor_dpr_chunks_text

    # Track how many clauses get evidence from fallback vs search
    search_hits = 0
    fallback_hits = 0

    # ── Stage 5-7: Clause Evaluation, Missing Detection, Contradictions ──
    evaluated = 0
    for clause in all_clauses:
        evaluated += 1
        _update_backend_progress(run_id, "evaluating", evaluated, total, f"Evaluating clause {clause.clause_id}...")

        # RAG search across both vendor files for this clause
        vendor_evidence, source_files = _search_vendor_for_clause(store, clause.requirement_text, body, clause_id=clause.clause_id)

        # ── Fallback: keyword-overlap retrieval from pre-loaded vendor text ──
        if not vendor_evidence.strip() and all_vendor_windows:
            vendor_evidence, fb_source = _fallback_keyword_retrieval(clause.requirement_text, all_vendor_windows)
            if vendor_evidence.strip():
                fallback_hits += 1
                source_files = fb_source
                logger.info("Clause %s: fallback retrieved %d chars of vendor evidence", clause.clause_id, len(vendor_evidence))
        elif vendor_evidence.strip():
            search_hits += 1

        clause.source_file_detail = ", ".join(source_files) if source_files else ""
        std_evidence = ""
        for std_id, std_text in standard_texts.items():
            if clause.requirement_text.lower()[:50] in std_text.lower():
                std_evidence += f"\n[Standard {std_id}]:\n{std_text[:2000]}\n"

        # ── Stage 5: LLM Evaluation ──
        logger.debug("Clause %s: vendor_evidence length=%d chars", clause.clause_id, len(vendor_evidence))
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

    logger.info("Evidence source summary: %d from vector search, %d from keyword fallback, %d total clauses",
                search_hits, fallback_hits, total)

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
    report_path = _generate_report_file(result, body)

    return result, report_path


def _search_vendor_for_clause(store, requirement: str, body: RunPipelineRequest, clause_id: str = "") -> tuple:
    """Search across all vendor files (commercial ZIP files + DPR) for evidence relevant to a clause.
    Returns (evidence_text, source_file_names).
    """
    evidence_parts = []
    source_files = []

    # Collect ALL vendor doc IDs: primary com + additional com from ZIP + DPR
    vendor_doc_ids = []
    if body.doc_id_vendor_com:
        vendor_doc_ids.append(body.doc_id_vendor_com)
    if body.doc_id_vendor_com_others:
        for did in body.doc_id_vendor_com_others:
            if did not in vendor_doc_ids:
                vendor_doc_ids.append(did)
    if body.doc_id_vendor_dpr:
        vendor_doc_ids.append(body.doc_id_vendor_dpr)

    # ── Pass 1: Per-document filtered search ──
    for vid in vendor_doc_ids:
        if not vid:
            continue
        try:
            results = store.search(
                query=requirement[:500],
                top_k=8,
                doc_filter=[vid],
            )
            logger.info(
                "Clause %s: search doc=%s returned %d results",
                clause_id, vid[:12], len(results),
            )
            for r in results:
                txt = r.get("text", "")
                meta = r.get("metadata", {})
                if txt:
                    evidence_parts.append(txt)
                    fname = meta.get("filename", meta.get("zip_file_label", ""))
                    if fname and fname not in source_files:
                        source_files.append(fname)
        except Exception as exc:
            logger.warning("Vector search failed for %s (doc=%s): %s", clause_id, vid[:12] if vid else "?", exc)

    # ── Pass 2: Broader fallback — search ALL vendor docs combined if per-doc search found nothing ──
    if not evidence_parts and vendor_doc_ids:
        valid_ids = [v for v in vendor_doc_ids if v]
        try:
            logger.info("Clause %s: per-doc search empty, trying combined search across %d vendor docs", clause_id, len(valid_ids))
            results = store.search(
                query=requirement[:500],
                top_k=15,
                doc_filter=valid_ids,
            )
            logger.info("Clause %s: combined search returned %d results", clause_id, len(results))
            for r in results:
                txt = r.get("text", "")
                meta = r.get("metadata", {})
                if txt:
                    evidence_parts.append(txt)
                    fname = meta.get("filename", meta.get("zip_file_label", ""))
                    if fname and fname not in source_files:
                        source_files.append(fname)
        except Exception as exc:
            logger.warning("Combined vendor search failed for %s: %s", clause_id, exc)

    # Deduplicate evidence (same text from different chunks)
    seen = set()
    unique_parts = []
    for part in evidence_parts:
        # Use first 100 chars as dedup key
        key = part[:100].strip()
        if key not in seen:
            seen.add(key)
            unique_parts.append(part)

    result = "\n\n---\n\n".join(unique_parts[:8])  # Allow more evidence from multiple files
    if not result.strip():
        logger.warning("No vendor evidence found for clause %s (query=%s…)", clause_id, requirement[:80])
    else:
        logger.info("Clause %s: found %d unique evidence parts (%d chars)", clause_id, len(unique_parts), len(result))
    return result, source_files


def _split_into_windows(text: str, window_chars: int = 1500, overlap_chars: int = 200) -> List[str]:
    """Split text into overlapping character windows for fallback retrieval."""
    if not text or not text.strip():
        return []
    text = text.strip()
    if len(text) <= window_chars:
        return [text]
    windows = []
    start = 0
    while start < len(text):
        end = start + window_chars
        windows.append(text[start:end])
        start = end - overlap_chars
        if start + overlap_chars >= len(text):
            break
    return windows


def _fallback_keyword_retrieval(requirement: str, vendor_windows: List[str]) -> tuple:
    """Retrieve the most relevant vendor text windows using keyword overlap.
    Used as a last-resort fallback when vector search returns empty evidence.
    Returns (evidence_text, source_files).
    """
    import re as _re

    # Tokenize requirement into meaningful keywords
    req_tokens = set(
        t for t in _re.findall(r'[a-z]{3,}', requirement.lower())
        if t not in {"the", "and", "for", "with", "from", "this", "that", "are", "was", "not", "shall", "should", "will", "can", "may"}
    )
    if not req_tokens:
        # No meaningful keywords — return first window as generic evidence
        if vendor_windows:
            return vendor_windows[0][:2000], ["vendor_submission"]
        return "", []

    scored_windows = []
    for i, window in enumerate(vendor_windows):
        win_tokens = set(_re.findall(r'[a-z]{3,}', window.lower()))
        overlap = len(req_tokens & win_tokens)
        scored_windows.append((overlap, i, window))

    # Sort by keyword overlap descending
    scored_windows.sort(key=lambda x: (-x[0], x[1]))

    # Take top 3 windows with any keyword overlap, or top 1 if none overlap
    evidence_parts = []
    for score, idx, window in scored_windows[:3]:
        if score > 0:
            evidence_parts.append(window[:2000])
    if not evidence_parts and scored_windows:
        evidence_parts.append(scored_windows[0][2][:2000])

    result = "\n\n---\n\n".join(evidence_parts)
    return result, ["vendor_submission"]


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

IMPORTANT EVALUATION RULES:
- If vendor submission text is provided above, you MUST evaluate it against the requirement. Do NOT default to UNVERIFIABLE when evidence is present.
- COMPLIANT: The vendor submission addresses the requirement, even if using different terminology. Capability descriptions, feature lists, and product specifications count as evidence.
- PARTIAL: The vendor partially addresses the requirement but has gaps.
- NON_COMPLIANT: The vendor submission contradicts the requirement or clearly does not address it.
- UNVERIFIABLE: ONLY use this when the vendor submission section shows "[No relevant vendor evidence found]" OR the provided excerpts are completely unrelated to the requirement.
- When in doubt between UNVERIFIABLE and COMPLIANT/PARTIAL, prefer COMPLIANT/PARTIAL if the vendor text mentions relevant capabilities.
- severity must be null if verdict is COMPLIANT.
- recommendation must be null if verdict is COMPLIANT (or APPROVE).
- For NON_COMPLIANT, recommendation must be REVISE_AND_RESUBMIT or REJECT.
- For PARTIAL, recommendation must be APPROVE WITH CONDITIONS or REVISE_AND_RESUBMIT."""

    messages = [
        {"role": "system", "content": "You are a military compliance officer. Return only valid JSON with the exact schema specified. Always evaluate vendor evidence that is provided - never ignore it."},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = llm_engine.generate(messages, max_tokens=2048, temperature=0.1, raw=True)
        logger.debug("LLM raw response for %s: %s", clause.clause_id, (raw or "")[:500])
        parsed = _parse_llm_json(raw) or {}
        if not parsed:
            logger.warning("LLM returned unparseable JSON for %s: %s", clause.clause_id, (raw or "")[:500])
    except Exception as exc:
        logger.warning("LLM evaluation failed for clause %s: %s", clause.clause_id, exc)
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
        violated_raw = parsed.get("violated", False)
        if isinstance(violated_raw, str):
            violated = violated_raw.lower() in ("true", "1", "yes")
        else:
            violated = bool(violated_raw)
        if violated:
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
        contra_raw = parsed.get("has_contradiction", False)
        if isinstance(contra_raw, str):
            has_contra = contra_raw.lower() in ("true", "1", "yes")
        else:
            has_contra = bool(contra_raw)
        if has_contra:
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
    from api.models.compliance_models import HistoricalNote
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
                if rid and str(rid) != clause.source_doc_id:
                    notes.append(HistoricalNote(
                        run_id=rid,
                        reference_name=run.get("reference_name", ""),
                        previous_verdict=None,
                        note=f"Previous compliance run #{rid}: {run.get('reference_name', 'N/A')}",
                    ))
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


def _generate_report_file(result: PipelineResult, body: RunPipelineRequest) -> Optional[str]:
    """Generate and save the .docx compliance report. Returns the output path or None."""
    try:
        from api.generators.compliance_docx import generate_compliance_report
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', body.reference_name)[:100] or "compliance_report"
        filename = f"{safe_name}_Compliance_Report.docx"
        output_path = str(_OUTPUTS_DIR / filename)
        generate_compliance_report(result, body.reference_name, output_path)
        logger.info("Compliance report generated: %s", output_path)
        return output_path
    except Exception as e:
        logger.error("Failed to generate compliance report: %s", e)
        return None


def _parse_llm_json(raw: str) -> Optional[Dict]:
    """Parse JSON from LLM response, handling markdown fences, thinking blocks, and system prompt leakage."""
    if not raw:
        return None

    # 1. Strip <think>...</think> blocks (Gemma 4 reasoning)
    cleaned = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL)

    # 2. Strip lines that look like system prompt leakage or chain-of-thought
    leak_markers = (
        "Military Compliance Officer", "Evaluate vendor submission",
        "Return only valid JSON", "SOTR Clause:", "Requirement (SOTR",
        "*   Requirement", "*   SOTR", "Acceptance Criteria:",
    )
    lines = cleaned.split("\n")
    cleaned_lines = [l for l in lines if not any(m in l for m in leak_markers)]
    cleaned = "\n".join(cleaned_lines)

    # 3. Strip markdown code fences
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'```\s*$', '', cleaned.strip(), flags=re.MULTILINE)

    # 4. Find the outermost JSON object by tracking brace depth
    try:
        depth = 0
        start = -1
        for i, ch in enumerate(cleaned):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start >= 0:
                    return json.loads(cleaned[start:i + 1])
    except (json.JSONDecodeError, ValueError):
        pass

    # 5. Truncation recovery: if JSON was cut off mid-string, try to close it
    if start >= 0:
        fragment = cleaned[start:]
        # Close any unclosed string (count unescaped quotes)
        in_string = False
        quote_count = 0
        for ch in fragment:
            if ch == '"' and (quote_count == 0 or fragment[max(0, quote_count - 1)] != '\\'):
                in_string = not in_string
                quote_count += 1
        if in_string:
            fragment += '"'
        # Close any unclosed brackets/braces
        open_braces = fragment.count('{') - fragment.count('}')
        open_brackets = fragment.count('[') - fragment.count(']')
        fragment += ']' * max(0, open_brackets)
        fragment += '}' * max(0, open_braces)
        try:
            return json.loads(fragment)
        except (json.JSONDecodeError, ValueError):
            pass

    return None


# ═══════════════════════════════════════════════════════════════
#  STANDARDS RELEVANCE SCORING
# ═══════════════════════════════════════════════════════════════

# Mapping: filename patterns → domain tags for relevance scoring
_FILENAME_TAG_MAP = {
    "safety": ["safety", "fire", "lifesaving", "emergency", "alarm", "rescue", "survival"],
    "electrical": ["electrical", "power", "wiring", "cable", "switchboard", "generator", "sld", "single line"],
    "navigation": ["navigation", "bridge", "radar", "compass", "gps", "communication", "gmdss"],
    "structural": ["structural", "hull", "frame", "steel", "welding", "plate", "thickness"],
    "propulsion": ["propulsion", "engine", "machinery", "main engine", "gearbox", "shaft", "propeller"],
    "environmental": ["environmental", "marpol", "emission", "pollution", "waste", "oil", "sewage", "ballast", "garbage"],
    "classification": ["classification", "irs", "dnv", "abs", "bv", "lr", "nk", "rules", "notation"],
    "solas": ["solas", "safety of life at sea", "convention"],
    "stcw": ["stcw", "seafarer", "training", "certification", "watchkeeping"],
    "marpol": ["marpol", "marine pollution", "annex"],
    "port_state": ["port state", "psc", "inspection", "detention", "deficiency"],
    "sop": ["sop", "standard operating", "procedure", "operations"],
    "ga_drawing": ["ga drawing", "general arrangement", "layout", "deck", "plan"],
    "technical_spec": ["technical spec", "specification", "requirement", "statement of technical"],
    "commercial": ["commercial", "price", "cost", "payment", "delivery", "warranty", "bid", "tender"],
    "quality": ["quality", "inspection", "testing", "commissioning", "iso", "certification"],
}

# Mapping: SOTR clause category → relevant standard domain tags
_CATEGORY_TAG_MAP = {
    "Technical": ["electrical", "navigation", "structural", "propulsion", "technical_spec", "ga_drawing", "classification"],
    "Safety": ["safety", "solas", "port_state"],
    "Environmental": ["environmental", "marpol"],
    "Quality": ["quality", "classification", "port_state"],
    "Commercial": ["commercial"],
    "General": ["sop", "technical_spec"],
}


def _score_standards_relevance(
    sotr_text: str,
    sotr_categories: Dict[str, int],
    standards: List[StandardsDocument],
) -> List[StandardRelevance]:
    """Score each standard's relevance to the given SOTR content.

    Uses three signals:
      1. Filename pattern matching → domain tags
      2. SOTR clause category distribution → domain tag preferences
      3. Direct keyword overlap between SOTR text and standard filenames
    """
    sotr_lower = sotr_text.lower() if sotr_text else ""

    # Build a set of domain tags present in the SOTR text
    sotr_tags: set = set()
    for tag, keywords in _FILENAME_TAG_MAP.items():
        for kw in keywords:
            if kw in sotr_lower:
                sotr_tags.add(tag)
                break

    # Build preferred tags from clause categories
    preferred_tags: set = set()
    total_clauses = sum(sotr_categories.values()) or 1
    for cat, count in sotr_categories.items():
        weight = count / total_clauses
        if weight >= 0.15 and cat in _CATEGORY_TAG_MAP:
            preferred_tags.update(_CATEGORY_TAG_MAP[cat])
        elif cat in _CATEGORY_TAG_MAP:
            preferred_tags.update(_CATEGORY_TAG_MAP[cat][:2])

    all_query_tags = sotr_tags | preferred_tags

    results: List[StandardRelevance] = []
    for std in standards:
        fname_lower = std.filename.lower()
        score = 0.0
        reasons: List[str] = []

        # Signal 1: filename tag match
        matched_tags = set()
        for tag, keywords in _FILENAME_TAG_MAP.items():
            for kw in keywords:
                if kw in fname_lower:
                    matched_tags.add(tag)
                    break

        # Score overlap between query tags and standard tags
        overlap = all_query_tags & matched_tags
        if overlap:
            tag_score = len(overlap) / max(len(all_query_tags), 1) * 60
            score += tag_score
            reasons.append(f"matches: {', '.join(sorted(overlap)[:3])}")

        # Signal 2: direct keyword in filename from SOTR text
        sotr_words = set(re.findall(r'\b[a-z]{4,}\b', sotr_lower))
        fname_words = set(re.findall(r'\b[a-z]{4,}\b', fname_lower))
        common = sotr_words & fname_words - {"the", "and", "with", "from", "that", "this", "shall", "must", "file", "standard", "compliance"}
        if common:
            kw_score = min(len(common) * 5, 30)
            score += kw_score
            reasons.append(f"keywords: {', '.join(sorted(common)[:3])}")

        # Signal 3: category alignment bonus
        for cat, cat_tags in _CATEGORY_TAG_MAP.items():
            cat_count = sotr_categories.get(cat, 0)
            if cat_count > 0 and (set(cat_tags) & matched_tags):
                bonus = min(cat_count / total_clauses * 15, 15)
                score += bonus
                break

        score = min(round(score, 1), 100.0)
        recommended = score >= 25.0

        results.append(StandardRelevance(
            doc_id=std.doc_id,
            filename=std.filename,
            score=score,
            reasons=reasons,
            recommended=recommended,
        ))

    results.sort(key=lambda x: x.score, reverse=True)
    return results


# ═══════════════════════════════════════════════════════════════
#  ENDPOINT: STANDARDS RELEVANCE
# ═══════════════════════════════════════════════════════════════

@router.post("/standards/relevance", response_model=List[StandardRelevance])
async def compute_standards_relevance(
    body: RelevanceRequest,
    user: dict = Depends(get_current_user),
):
    """Compute relevance scores for each standard against uploaded SOTR content."""
    standards = await list_standards(user=user)
    return _score_standards_relevance(
        sotr_text=body.sotr_text,
        sotr_categories=body.sotr_categories,
        standards=standards,
    )


# ═══════════════════════════════════════════════════════════════
#  ENDPOINT: STANDARDS RELEVANCE FROM FILES
# ═══════════════════════════════════════════════════════════════

class RelevanceFromFilesRequest(BaseModel):
    file_paths: List[str] = []


@router.post("/standards/relevance-from-files", response_model=List[StandardRelevance])
async def compute_standards_relevance_from_files(
    body: RelevanceFromFilesRequest,
    user: dict = Depends(get_current_user),
):
    """Extract text from SOTR files and compute standards relevance scores."""
    import tempfile
    from api.rag.ocr import extract_pdf, extract_docx

    all_text_parts: List[str] = []
    categories: Dict[str, int] = {}

    for fp in body.file_paths:
        if not os.path.exists(fp):
            continue
        ext = Path(fp).suffix.lower()
        try:
            if ext == '.pdf':
                pages = extract_pdf(fp)
                for p in pages:
                    all_text_parts.append(p.get("text", ""))
            elif ext in ('.docx', '.doc'):
                pages = extract_docx(fp)
                for p in pages:
                    all_text_parts.append(p.get("text", ""))
            elif ext == '.txt':
                all_text_parts.append(Path(fp).read_text(encoding='utf-8', errors='ignore'))
        except Exception as e:
            logger.warning("Failed to extract text from %s: %s", fp, e)

    combined_text = "\n".join(all_text_parts)

    if combined_text:
        try:
            from api.rag.sotr_parser import extract_clauses
            clauses = extract_clauses(combined_text)
            if clauses:
                for c in clauses:
                    cat = c.category.value if hasattr(c.category, 'value') else str(c.category)
                    categories[cat] = categories.get(cat, 0) + 1
        except Exception as e:
            logger.warning("SOTR parsing for relevance failed: %s", e)

    standards = await list_standards(user=user)
    return _score_standards_relevance(
        sotr_text=combined_text,
        sotr_categories=categories,
        standards=standards,
    )


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
        all_docs = store.list_unique_documents()
        for doc in all_docs:
            if doc.get("document_type") == "standard":
                standards.append(StandardsDocument(
                    doc_id=doc.get("doc_id", ""),
                    filename=doc.get("filename", ""),
                    category=doc.get("category", ""),
                    description=doc.get("filename", ""),
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
