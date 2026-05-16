"""
AGRA Phase 2 — Router: Compliance Check Engine
Clause-by-clause analysis against ingested standards.
"""

import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from docx import Document as DocxDocument

from api.utils.auth_check import get_current_user
from api.utils.usage_logger import log_usage
from api.rag import embedder, llm as llm_engine
from api.rag.vector_store import get_store
from api.rag.reranker import rerank

logger = logging.getLogger("agra.compliance")

router = APIRouter()

import os as _os
_DATA_DIR = Path(_os.environ.get("AGRA_DATA_DIR", "/workspace/agra_data"))
if not _DATA_DIR.exists():
    _DATA_DIR = Path(__file__).resolve().parent.parent.parent / "agra_data"
_OUTPUTS_DIR = _DATA_DIR / "outputs"
_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def _clean_json(raw: str) -> str:
    """
    Workstream D: Recursive JSON extraction with multiple fallback strategies.
    1. Strip markdown code fences
    2. Extract outermost [...] array
    3. If truncated, try closing partial objects/arrays
    """
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'```\s*$', '', cleaned.strip(), flags=re.MULTILINE)
    cleaned = cleaned.strip()

    # Strategy 1: Find outermost array brackets
    start = cleaned.find("[")
    end = cleaned.rfind("]") + 1
    if start != -1 and end > start:
        return cleaned[start:end]

    # Strategy 2: Array started but truncated — close partial objects
    if start != -1 and end <= start:
        partial = cleaned[start:]
        # Count open braces and try to close them
        open_braces = partial.count("{") - partial.count("}")
        open_brackets = partial.count("[") - partial.count("]")
        # Strip trailing comma or incomplete key
        partial = re.sub(r',\s*"[^"]*$', '', partial)
        partial = re.sub(r',\s*$', '', partial)
        partial += "}" * max(0, open_braces)
        partial += "]" * max(0, open_brackets)
        return partial

    return cleaned


def _repair_json_with_llm(broken_json: str) -> list:
    """
    Workstream D: Last-resort LLM-based JSON repair.
    Send the broken JSON to the LLM with a tiny prompt asking it to fix it.
    """
    repair_prompt = f"""The following JSON array is malformed or truncated. Fix it and return ONLY a valid JSON array. Do not add new data, just fix the syntax:

{broken_json[:2000]}"""
    try:
        repaired_raw = llm_engine.generate(
            [{"role": "user", "content": repair_prompt}],
            max_tokens=600,
            temperature=0.0,
        )
        cleaned = _clean_json(repaired_raw)
        result = json.loads(cleaned)
        if isinstance(result, list):
            logger.info("LLM JSON repair succeeded: %d items recovered", len(result))
            return result
    except Exception as e:
        logger.warning("LLM JSON repair also failed: %s", e)
    return []


class ComplianceRequest(BaseModel):
    subject_doc_ids: List[str] = Field(..., min_length=1, description="Documents being checked")
    standard_doc_ids: List[str] = Field(..., min_length=1, description="Standards to check against")
    check_scope: Optional[str] = Field(None, description="Specific area to focus on")


@router.post("/compliance/check")
async def compliance_check(
    body: ComplianceRequest,
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """
    Run clause-by-clause compliance analysis.
    Returns SSE stream of findings, then a .docx report download link.
    """
    compliance_start = time.time()
    auth_tok = ""
    if request:
        ah = request.headers.get("authorization", "")
        auth_tok = ah.replace("Bearer ", "") if ah else ""
    store = get_store()

    # Load subject document chunks
    subject_chunks = []
    for s_id in body.subject_doc_ids:
        chunks = store.get_chunks_by_doc(s_id)
        if chunks:
            subject_chunks.extend(chunks)

    if not subject_chunks:
        raise HTTPException(status_code=404, detail="Subject documents not found in knowledge base.")

    # Load standard document chunks
    standard_chunks = []
    for std_id in body.standard_doc_ids:
        std = store.get_chunks_by_doc(std_id)
        if not std:
            raise HTTPException(status_code=404, detail=f"Standard document {std_id} not found.")
        standard_chunks.extend(std)

    if not standard_chunks:
        raise HTTPException(status_code=400, detail="No standard document content found.")

    subject_filenames = list(set(c["metadata"].get("filename", "Subject Document") for c in subject_chunks if "metadata" in c))
    subject_filenames_str = ", ".join(subject_filenames)
    # Workstream D: Strictly cap context to fit 3328-token inference window
    # ~2500 chars subject + ~2000 chars standard + ~800 chars prompt = ~5300 chars ≈ 1300 tokens
    # Leaves ~2000 tokens for output (max_tokens=800 + safety)
    _MAX_SUBJECT_CHARS = 2500
    _MAX_STANDARD_CHARS = 2000
    _MAX_SUBJECT_CHUNKS = 8
    _MAX_STANDARD_CHUNKS = 6

    subject_text = "\n\n".join(
        f"[{c['metadata'].get('filename', 'Unknown')}]: {c['text']}"
        for c in subject_chunks[:_MAX_SUBJECT_CHUNKS]
    )
    if len(subject_text) > _MAX_SUBJECT_CHARS:
        subject_text = subject_text[:_MAX_SUBJECT_CHARS] + "\n[Content truncated]"

    # Calculate average OCR confidence
    conf_scores = [c["metadata"].get("ocr_confidence", 1.0) for c in subject_chunks if "metadata" in c]
    avg_conf = sum(conf_scores) / len(conf_scores) if conf_scores else 1.0

    # Extract key clauses from standards
    standards_text = "\n\n".join(c["text"] for c in standard_chunks[:_MAX_STANDARD_CHUNKS])
    if len(standards_text) > _MAX_STANDARD_CHARS:
        standards_text = standards_text[:_MAX_STANDARD_CHARS] + "\n[Content truncated]"

    scope_note = f"\nFocus specifically on: {body.check_scope}" if body.check_scope else ""

    prompt = f"""You are a compliance analyst for the Indian Coast Guard.

TASK: Perform a clause-by-clause compliance analysis of the SUBJECT DOCUMENT(S) against the STANDARD(S).

SUBJECT DOCUMENTS ({subject_filenames_str}):
{subject_text}

APPLICABLE STANDARDS:
{standards_text}
{scope_note}

For each relevant clause/requirement in the standard, evaluate the subject documents' compliance.
Critically:
- "Missing": If a requirement in the standard is completely absent in the subject document.
- "Contradiction": If the subject documents contain conflicting specifications between themselves (Inter-Document Inconsistency) or with the standard.
- "Selective Compliance": If the subject documents cite a standard but specifically omit or ignore a restrictive sub-clause.

Return ONLY a valid JSON array of findings. Each finding must strictly follow this structure:
{{
  "topic": "Broad category (e.g. Fire Safety, Propulsion, Hull Structure)",
  "clause_id": "Exact clause/section reference from the standard",
  "requirement": "What the standard requires",
  "acceptance_criterion": "The specific technical metric or condition required to pass",
  "verdict": "Compliant" | "Non-Compliant" | "Partial" | "Missing" | "Contradiction" | "Unverifiable",
  "severity": "Critical" | "Major" | "Minor" | "None" (Use Critical for life-safety or core mission failure; None if Compliant),
  "finding": "Detailed explanation of the compliance status, explicitly stating if it is missing, contradictory, or selectively compliant.",
  "recommendation": "Specific action needed (if not fully compliant)",
  "citation": "Relevant excerpt from the subject document, if any"
}}

Analyse at least 5-10 key clauses in depth. Return valid JSON array only:"""

    messages = [
        {"role": "system", "content": "You are an expert compliance auditor. Return only valid JSON arrays."},
        {"role": "user", "content": prompt},
    ]

    try:
        findings_raw = llm_engine.generate(messages, max_tokens=800, temperature=0.3)
    except Exception as e:
        logger.error("Compliance LLM call failed: %s", e)
        raise HTTPException(status_code=500, detail="Compliance analysis engine is temporarily unavailable. Please try with smaller documents or fewer standards.")

    # Workstream D: Multi-strategy JSON parsing with graceful degradation
    findings = None
    try:
        cleaned = _clean_json(findings_raw)
        findings = json.loads(cleaned)
        if not isinstance(findings, list):
            raise ValueError("Expected a JSON array of findings")
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Primary JSON parse failed: %s — attempting LLM repair", e)
        # Fallback: LLM-based repair
        findings = _repair_json_with_llm(findings_raw)

    if not findings:
        logger.error("All JSON recovery strategies failed. Raw (first 500): %s", findings_raw[:500])
        # Return a single degraded finding instead of 500
        findings = [{
            "topic": "Analysis Error",
            "clause_id": "N/A",
            "requirement": "Automated compliance parsing",
            "acceptance_criterion": "Valid JSON output",
            "verdict": "Unverifiable",
            "severity": "Major",
            "finding": "The compliance engine could not produce a structured analysis. This may be due to document complexity or context size. Please try with a narrower scope or fewer documents.",
            "recommendation": "Re-run with check_scope targeting specific sections, or reduce document count.",
            "citation": "N/A",
        }]

    # Second pass: Missing Requirements
    covered_clauses = [f.get("clause_id", "") for f in findings]
    covered_str = "\n".join(f"- {c}" for c in covered_clauses if c)
    
    missing_prompt = f"""You are a compliance analyst.
    
STANDARD:
{standards_text}

The following clauses were already checked:
{covered_str}

Identify any CRITICAL requirements or clauses in the STANDARD that were NOT checked above, and which are completely MISSING from the subject documents.
Return ONLY a valid JSON array of these missing findings, using the exact same format:
{{
  "topic": "Broad category",
  "clause_id": "Clause reference",
  "requirement": "What the standard requires",
  "acceptance_criterion": "The specific metric that is missing",
  "verdict": "Missing",
  "severity": "Major",
  "finding": "This requirement was completely omitted from the subject document.",
  "recommendation": "Shipbuilder must provide details on this requirement.",
  "citation": "N/A"
}}
If there are no major missing requirements, return an empty array []."""

    messages_missing = [
        {"role": "system", "content": "You are an expert compliance auditor. Return only valid JSON arrays."},
        {"role": "user", "content": missing_prompt},
    ]
    try:
        missing_raw = llm_engine.generate(messages_missing, max_tokens=800, temperature=0.3)
        cleaned = _clean_json(missing_raw)
        start = cleaned.find("[")
        end = cleaned.rfind("]") + 1
        if start != -1 and end != 0:
            missing_findings = json.loads(cleaned[start:end])
            if isinstance(missing_findings, list):
                findings.extend(missing_findings)
    except Exception as e:
        logger.warning("Second pass (Missing Requirements) failed or returned empty: %s", e)

    # Post-process for low OCR confidence
    if avg_conf < 0.65:
        logger.warning(f"Low OCR confidence detected: {avg_conf:.2f}")
        for finding in findings:
            if finding.get("verdict") != "Missing":
                finding["verdict"] = "Unverifiable"
                finding["finding"] = f"[LOW OCR CONFIDENCE: {avg_conf:.2f}] " + finding.get("finding", "")

    # Third pass: Historical Feedback
    history_findings = []
    try:
        history_query = f"historical non-compliance defect lessons learned failure {body.check_scope or ''}"
        history_emb = embedder.embed_query(history_query)
        historical_chunks = store.hybrid_search(history_query, history_emb, top_k=5)
        
        if historical_chunks:
            hist_text = "\n\n".join(c["text"] for c in historical_chunks)
            hist_prompt = f"""You are a compliance analyst.
Review these past historical records and lessons learned:
{hist_text[:2000]}

Based on the above, are there any common historical defects or past non-compliances that the auditor should specifically double-check in the current subject document?
Summarize the top 2-3 historical warnings. Return a simple string paragraph. If nothing is relevant, return 'None'."""
            hist_res = llm_engine.generate([{"role": "user", "content": hist_prompt}], max_tokens=500)
            if hist_res.strip() and hist_res.strip().lower() != 'none':
                history_findings.append(hist_res.strip())
    except Exception as e:
        logger.warning("Historical feedback pass failed: %s", e)

    # Stream findings as SSE
    job_id = str(uuid.uuid4())

    def event_stream():
        for i, finding in enumerate(findings):
            yield f"data: {json.dumps({'finding': finding, 'index': i + 1, 'total': len(findings)})}\n\n"

        # Build DOCX report
        docx_path = _OUTPUTS_DIR / f"{job_id}_compliance.docx"
        doc = DocxDocument()
        doc.add_heading("Compliance Analysis Report", level=1)
        doc.add_heading(f"Subjects: {subject_filenames_str}", level=2)
        doc.add_paragraph(f"Scope: {body.check_scope or 'Full Document'}")
        doc.add_paragraph("")

        # Summary metrics
        compliant = sum(1 for f in findings if f.get("verdict") == "Compliant")
        non_compliant = sum(1 for f in findings if f.get("verdict") == "Non-Compliant")
        partial = sum(1 for f in findings if f.get("verdict") == "Partial")
        missing = sum(1 for f in findings if f.get("verdict") == "Missing")
        contradiction = sum(1 for f in findings if f.get("verdict") == "Contradiction")
        unverifiable = sum(1 for f in findings if f.get("verdict") == "Unverifiable")
        
        critical_issues = sum(1 for f in findings if f.get("severity") == "Critical" and f.get("verdict") != "Compliant")
        
        total_evaluable = len(findings) - unverifiable
        compliance_score = (compliant / total_evaluable * 100) if total_evaluable > 0 else 0
        
        overall_rec = "APPROVE"
        if critical_issues > 0 or compliance_score < 70:
            overall_rec = "REJECT"
        elif non_compliant > 0 or missing > 0 or partial > 0:
            overall_rec = "APPROVE WITH CONDITIONS (REVISE)"

        doc.add_heading("Executive Summary", level=2)
        doc.add_paragraph(f"Overall Compliance Score: {compliance_score:.1f}%")
        doc.add_paragraph(f"Final Recommendation: {overall_rec}").bold = True
        doc.add_paragraph(f"Critical Deficiencies Found: {critical_issues}")
        doc.add_paragraph("")
        
        if history_findings:
            doc.add_heading("Historical Feedback & Lessons Learned", level=2)
            doc.add_paragraph(history_findings[0])
            doc.add_paragraph("")

        doc.add_heading("Summary Statistics", level=2)
        summary_table = doc.add_table(rows=7, cols=2)
        summary_table.style = "Table Grid"
        cells = summary_table.rows[0].cells
        cells[0].text = "Total Clauses Checked"
        cells[1].text = str(len(findings))
        cells = summary_table.rows[1].cells
        cells[0].text = "Compliant"
        cells[1].text = str(compliant)
        cells = summary_table.rows[2].cells
        cells[0].text = "Non-Compliant"
        cells[1].text = str(non_compliant)
        cells = summary_table.rows[3].cells
        cells[0].text = "Partial"
        cells[1].text = str(partial)
        cells = summary_table.rows[4].cells
        cells[0].text = "Missing"
        cells[1].text = str(missing)
        cells = summary_table.rows[5].cells
        cells[0].text = "Contradiction"
        cells[1].text = str(contradiction)
        cells = summary_table.rows[6].cells
        cells[0].text = "Unverifiable"
        cells[1].text = str(unverifiable)

        doc.add_paragraph("")
        doc.add_heading("Detailed Findings Register", level=2)

        for i, f in enumerate(findings, 1):
            doc.add_heading(f"Finding {i}: {f.get('clause_id', 'N/A')}", level=3)
            doc.add_paragraph(f"Verdict: {f.get('verdict', 'N/A')} | Severity: {f.get('severity', 'None')}")
            doc.add_paragraph(f"Requirement: {f.get('requirement', 'N/A')}")
            doc.add_paragraph(f"Acceptance Criterion: {f.get('acceptance_criterion', 'N/A')}")
            doc.add_paragraph(f"Finding: {f.get('finding', 'N/A')}")
            doc.add_paragraph(f"Recommendation: {f.get('recommendation', 'N/A')}")
            doc.add_paragraph(f"Citation: {f.get('citation', 'N/A')}")
            doc.add_paragraph("")

        doc.save(str(docx_path))

        yield f"data: {json.dumps({'done': True, 'download_url': f'/api/agent/download/{job_id}_compliance.docx', 'summary': {'total': len(findings), 'compliant': compliant, 'non_compliant': non_compliant, 'partial': partial, 'missing': missing, 'contradiction': contradiction, 'unverifiable': unverifiable, 'score': round(compliance_score, 1), 'recommendation': overall_rec}})}\n\n"

        # Log usage
        elapsed_ms = (time.time() - compliance_start) * 1000
        log_usage(action_type="compliance", module="compliance", token=auth_tok, response_time_ms=elapsed_ms)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
