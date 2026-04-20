"""
AGRA Phase 2 — Router: Compliance Check Engine
Clause-by-clause analysis against ingested standards.
"""

import json
import logging
import re
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from docx import Document as DocxDocument

from api.utils.auth_check import get_current_user
from api.rag import embedder, llm as llm_engine
from api.rag.vector_store import get_store
from api.rag.reranker import rerank

logger = logging.getLogger("agra.compliance")

router = APIRouter()

_OUTPUTS_DIR = Path(__file__).resolve().parent.parent.parent / "outputs"
_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def _clean_json(raw: str) -> str:
    """Strip markdown code fences (```json...```) from LLM output before JSON parsing."""
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'```\s*$', '', cleaned.strip(), flags=re.MULTILINE)
    return cleaned.strip()


class ComplianceRequest(BaseModel):
    subject_doc_id: str = Field(..., description="Document being checked")
    standard_doc_ids: List[str] = Field(..., min_length=1, description="Standards to check against")
    check_scope: Optional[str] = Field(None, description="Specific area to focus on")


@router.post("/compliance/check")
async def compliance_check(
    body: ComplianceRequest,
    user: dict = Depends(get_current_user),
):
    """
    Run clause-by-clause compliance analysis.
    Returns SSE stream of findings, then a .docx report download link.
    """
    store = get_store()

    # Load subject document chunks
    subject_chunks = store.get_chunks_by_doc(body.subject_doc_id)
    if not subject_chunks:
        raise HTTPException(status_code=404, detail="Subject document not found in knowledge base.")

    # Load standard document chunks
    standard_chunks = []
    for std_id in body.standard_doc_ids:
        std = store.get_chunks_by_doc(std_id)
        if not std:
            raise HTTPException(status_code=404, detail=f"Standard document {std_id} not found.")
        standard_chunks.extend(std)

    if not standard_chunks:
        raise HTTPException(status_code=400, detail="No standard document content found.")

    subject_filename = subject_chunks[0]["metadata"].get("filename", "Subject Document")
    subject_text = "\n\n".join(c["text"] for c in subject_chunks[:20])

    # Extract key clauses from standards
    standards_text = "\n\n".join(c["text"] for c in standard_chunks[:20])

    scope_note = f"\nFocus specifically on: {body.check_scope}" if body.check_scope else ""

    prompt = f"""You are a compliance analyst for the Indian Coast Guard.

TASK: Perform a clause-by-clause compliance analysis of the SUBJECT DOCUMENT against the STANDARD(S).

SUBJECT DOCUMENT ({subject_filename}):
{subject_text[:12000]}

APPLICABLE STANDARDS:
{standards_text[:12000]}
{scope_note}

For each relevant clause/requirement in the standard, evaluate the subject document's compliance.

Return ONLY a valid JSON array of findings. Each finding must be:
{{
  "clause": "Clause/section reference from the standard",
  "requirement": "What the standard requires",
  "verdict": "Compliant" | "Non-Compliant" | "Partial" | "Unverifiable",
  "finding": "Detailed explanation of the compliance status",
  "recommendation": "Specific action needed (if not fully compliant)",
  "citation": "Relevant excerpt from the subject document"
}}

Analyse at least 5-10 key clauses. Return valid JSON array only:"""

    messages = [
        {"role": "system", "content": "You are an expert compliance auditor. Return only valid JSON arrays."},
        {"role": "user", "content": prompt},
    ]

    findings_raw = llm_engine.generate(messages, max_tokens=4096, temperature=0.3)

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

    # Stream findings as SSE
    job_id = str(uuid.uuid4())

    def event_stream():
        for i, finding in enumerate(findings):
            yield f"data: {json.dumps({'finding': finding, 'index': i + 1, 'total': len(findings)})}\n\n"

        # Build DOCX report
        docx_path = _OUTPUTS_DIR / f"{job_id}_compliance.docx"
        doc = DocxDocument()
        doc.add_heading("Compliance Analysis Report", level=1)
        doc.add_heading(f"Subject: {subject_filename}", level=2)
        doc.add_paragraph(f"Scope: {body.check_scope or 'Full Document'}")
        doc.add_paragraph("")

        # Summary table
        compliant = sum(1 for f in findings if f.get("verdict") == "Compliant")
        non_compliant = sum(1 for f in findings if f.get("verdict") == "Non-Compliant")
        partial = sum(1 for f in findings if f.get("verdict") == "Partial")
        unverifiable = sum(1 for f in findings if f.get("verdict") == "Unverifiable")

        doc.add_heading("Summary", level=2)
        summary_table = doc.add_table(rows=5, cols=2)
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
        cells[0].text = "Unverifiable"
        cells[1].text = str(unverifiable)

        doc.add_paragraph("")
        doc.add_heading("Detailed Findings", level=2)

        for i, f in enumerate(findings, 1):
            doc.add_heading(f"Finding {i}: {f.get('clause', 'N/A')}", level=3)
            doc.add_paragraph(f"Verdict: {f.get('verdict', 'N/A')}")
            doc.add_paragraph(f"Requirement: {f.get('requirement', 'N/A')}")
            doc.add_paragraph(f"Finding: {f.get('finding', 'N/A')}")
            doc.add_paragraph(f"Recommendation: {f.get('recommendation', 'N/A')}")
            doc.add_paragraph(f"Citation: {f.get('citation', 'N/A')}")
            doc.add_paragraph("")

        doc.save(str(docx_path))

        yield f"data: {json.dumps({'done': True, 'download_url': f'/api/agent/download/{job_id}_compliance.docx', 'summary': {'total': len(findings), 'compliant': compliant, 'non_compliant': non_compliant, 'partial': partial, 'unverifiable': unverifiable}})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
