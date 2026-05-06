"""
AGRA Phase 4 — Router: Cross-Document Reasoning
Multi-document comparative analysis (e.g. Bidder A vs Bidder B vs Standard).
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
from api.rag import llm as llm_engine
from api.rag.vector_store import get_store

logger = logging.getLogger("agra.compare")

router = APIRouter()

import os as _os
_DATA_DIR = Path(_os.environ.get("AGRA_DATA_DIR", "/workspace/agra_data"))
if not _DATA_DIR.exists():
    _DATA_DIR = Path(__file__).resolve().parent.parent.parent / "agra_data"
_OUTPUTS_DIR = _DATA_DIR / "outputs"
_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def _clean_json(raw: str) -> str:
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'```\s*$', '', cleaned.strip(), flags=re.MULTILINE)
    return cleaned.strip()


class CompareRequest(BaseModel):
    bid_doc_ids: List[str] = Field(..., min_length=2, description="At least two bid documents to compare")
    standard_doc_id: Optional[str] = Field(None, description="Optional standard/SOTR to compare against")
    check_scope: Optional[str] = Field(None, description="Specific area to focus on")


@router.post("/compare/bids")
async def compare_bids(
    body: CompareRequest,
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """
    Perform a comparative analysis across multiple bid documents.
    If standard_doc_id is provided, evaluates both against the standard.
    Returns SSE stream of comparison matrices.
    """
    compare_start = time.time()
    auth_tok = ""
    if request:
        ah = request.headers.get("authorization", "")
        auth_tok = ah.replace("Bearer ", "") if ah else ""
    store = get_store()

    # Load Standard
    standard_text = ""
    if body.standard_doc_id:
        std_chunks = store.get_chunks_by_doc(body.standard_doc_id)
        if not std_chunks:
            raise HTTPException(status_code=404, detail="Standard document not found.")
        standard_text = "\n\n".join(c["text"] for c in std_chunks[:20])

    # Load Bids
    bids_data = {}
    for bid_id in body.bid_doc_ids:
        chunks = store.get_chunks_by_doc(bid_id)
        if not chunks:
            raise HTTPException(status_code=404, detail=f"Bid document {bid_id} not found.")
        filename = chunks[0]["metadata"].get("filename", f"Bid_{bid_id}")
        bids_data[filename] = "\n\n".join(c["text"] for c in chunks[:20])

    if len(bids_data) < 2:
        raise HTTPException(status_code=400, detail="Must have at least two valid bid documents.")

    bids_context = ""
    for filename, text in bids_data.items():
        bids_context += f"\n--- BID: {filename} ---\n{text[:8000]}\n"

    scope_note = f"\nFocus specifically on: {body.check_scope}" if body.check_scope else ""
    std_note = f"\nSTANDARD / SOTR:\n{standard_text[:8000]}\n" if standard_text else ""

    prompt = f"""You are a senior procurement evaluation officer for the Indian Coast Guard.

TASK: Perform a Cross-Document Comparative Analysis of multiple bid proposals.
{std_note}

BID DOCUMENTS:
{bids_context}

{scope_note}

Identify 5-10 key technical parameters or requirements from the documents.
For each parameter, compare what each bid proposes. If a standard is provided, also list the standard's requirement.

Return ONLY a valid JSON array of comparisons:
[
  {{
    "parameter": "E.g., Top Speed, Endurance, Hull Material",
    "standard_requirement": "What the standard requires (if available, else 'N/A')",
    "bids": [
      {{ "bidder": "Bid_Filename.pdf", "value": "What they proposed", "compliant": true/false }}
    ],
    "analysis": "Brief analysis of who is better or if someone is non-compliant",
    "winner": "Name of best bidder for this parameter or 'Tie'"
  }}
]
"""

    messages = [
        {"role": "system", "content": "You are an expert bid evaluator. Return only valid JSON arrays."},
        {"role": "user", "content": prompt},
    ]

    raw_resp = llm_engine.generate(messages, max_tokens=4096, temperature=0.2)

    try:
        cleaned = _clean_json(raw_resp)
        start = cleaned.find("[")
        end = cleaned.rfind("]") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON array found")
        comparisons = json.loads(cleaned[start:end])
    except Exception as e:
        logger.error("Failed to parse compare JSON: %s\nRaw: %s", e, raw_resp[:500])
        raise HTTPException(status_code=500, detail="Failed to parse comparison analysis.")

    job_id = str(uuid.uuid4())

    def event_stream():
        for i, comp in enumerate(comparisons):
            yield f"data: {json.dumps({'comparison': comp, 'index': i + 1, 'total': len(comparisons)})}\n\n"

        # Generate DOCX report
        docx_path = _OUTPUTS_DIR / f"{job_id}_compare.docx"
        doc = DocxDocument()
        doc.add_heading("Comparative Bid Analysis", level=1)
        doc.add_heading(f"Bids Evaluated: {', '.join(bids_data.keys())}", level=2)
        if body.standard_doc_id:
            doc.add_heading("Standard: Included", level=2)
        
        doc.add_paragraph("")

        for comp in comparisons:
            doc.add_heading(comp.get("parameter", "Parameter"), level=3)
            doc.add_paragraph(f"Standard Requirement: {comp.get('standard_requirement', 'N/A')}")
            for bid in comp.get("bids", []):
                doc.add_paragraph(f"• {bid.get('bidder', 'Bidder')}: {bid.get('value', 'N/A')} (Compliant: {bid.get('compliant', 'N/A')})")
            doc.add_paragraph(f"Analysis: {comp.get('analysis', 'N/A')}")
            doc.add_paragraph(f"Winner: {comp.get('winner', 'N/A')}")
            doc.add_paragraph("")

        doc.save(str(docx_path))

        yield f"data: {json.dumps({'done': True, 'download_url': f'/api/agent/download/{job_id}_compare.docx'})}\n\n"

        elapsed_ms = (time.time() - compare_start) * 1000
        log_usage(action_type="compare", module="reasoning", token=auth_tok, response_time_ms=elapsed_ms)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
