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
    """Strip markdown code fences (```json...```) from LLM output before JSON parsing."""
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'```\s*$', '', cleaned.strip(), flags=re.MULTILINE)
    return cleaned.strip()


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
    # Truncate to fit 3328-token context window (~4000 chars subject + ~3000 chars standard)
    subject_text = "\n\n".join(f"[{c['metadata'].get('filename', 'Unknown')}]: {c['text']}" for c in subject_chunks[:15])
    if len(subject_text) > 4000:
        subject_text = subject_text[:4000] + "\n[Content truncated]"

    # Calculate average OCR confidence
    conf_scores = [c["metadata"].get("ocr_confidence", 1.0) for c in subject_chunks if "metadata" in c]
    avg_conf = sum(conf_scores) / len(conf_scores) if conf_scores else 1.0

    # Extract key clauses from standards
    standards_text = "\n\n".join(c["text"] for c in standard_chunks[:10])
    if len(standards_text) > 3000:
        standards_text = standards_text[:3000] + "\n[Content truncated]"

    scope_note = f"\nFocus specifically on: {body.check_scope}" if body.check_scope else ""

    prompt = f"""You are a compliance analyst for the Indian Coast Guard.

TASK: Perform a clause-by-clause compliance analysis of the SUBJECT DOCUMENT(S) against the STANDARD(S).

SUBJECT DOCUMENTS ({subject_filenames_str}):
{subject_text[:8000]}

APPLICABLE STANDARDS:
{standards_text[:6000]}
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

    try:
        cleaned = _clean_json(findings_raw)
        start = cleaned.find("[")
        end = cleaned.rfind("]") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON array found in compliance response")
        findings = json.loads(cleaned[start:end])
        if not isinstance(findings, list):
            raise ValueError("Expected a JSON array of findings")
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse compliance JSON: %s\nRaw (first 800): %s", e, findings_raw[:800])
        raise HTTPException(status_code=500, detail="Failed to parse compliance analysis. Please try again.")

    # Second pass: Missing Requirements
    covered_clauses = [f.get("clause_id", "") for f in findings]
    covered_str = "\n".join(f"- {c}" for c in covered_clauses if c)
    
    missing_prompt = f"""You are a compliance analyst.
    
STANDARD:
{standards_text[:6000]}

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
{hist_text[:6000]}

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
