"""
AGRA Phase 2 — Router: Compliance Check Engine
Clause-by-clause analysis against ingested standards.
"""

import asyncio
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


def _is_json_array_start_global(s: str) -> bool:
    """Return True only if s starts with a real JSON array (not '[*' markdown list)."""
    if not s.startswith('['):
        return False
    i = 1
    while i < len(s) and s[i] in ' \t\n\r':
        i += 1
    return i < len(s) and s[i] == '{'


def _strip_echo_for_json(raw: str) -> str:
    """Robustly strip prompt-echo prefix and return a JSON-array-shaped string."""
    s = (raw or "").strip()
    # Fast path: valid JSON array start
    if _is_json_array_start_global(s):
        return s
    # Gemma outputs markdown bullet list [* item] as echo — aggressively strip it
    # Look for first real JSON object start '{'
    first_brace = s.find('{')
    # Also look for JSON array-of-objects start '[{'
    m = re.search(r'\[\s*\{', s)
    first_bracket_brace = m.start() if m else -1
    # If we see '[*' or '[ \n*' pattern, it's markdown list NOT JSON — skip past it
    if s.startswith('[') and not _is_json_array_start_global(s):
        # Find the first '{' after the opening junk
        if first_brace >= 0:
            return '[' + s[first_brace:]
        return '[]'
    if s.startswith('{'):
        return '[' + s + ']'
    if first_bracket_brace >= 0 and (first_brace < 0 or first_bracket_brace <= first_brace):
        return s[first_bracket_brace:]
    if first_brace >= 0:
        return '[' + s[first_brace:]
    return '[]'


def _run_compliance_batch(subject_slice: str, standard_slice: str, subject_filenames_str: str,
                          scope_note: str, max_tokens: int = 1200) -> list:
    """
    One compliance LLM call on a (subject_slice, standard_slice) pair.
    Returns parsed findings list (may be empty on failure).
    """
    prompt = f"""SUBJECT DOCUMENTS ({subject_filenames_str}):
{subject_slice}

STANDARDS:
{standard_slice}
{scope_note}

Instructions: Compare each standard clause against the subject documents.
For each clause output one JSON object with keys: topic, clause_id, requirement, acceptance_criterion, verdict, severity, finding, recommendation, citation.
verdict: Compliant | Non-Compliant | Partial | Missing | Contradiction | Unverifiable
severity: Critical | Major | Minor | None
Output 3-5 findings. Return a JSON array only. No prose. No markdown.
["""
    try:
        raw = llm_engine.generate(
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens, temperature=0.1,
        )
    except Exception as e:
        logger.warning("Compliance batch LLM call failed: %s", e)
        return []
    stripped = _strip_echo_for_json(raw)
    try:
        cleaned = _clean_json(stripped)
        data = json.loads(cleaned)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Compliance batch JSON parse failed: %s", e)
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
    # Context caps for 3328-token per-request limit (llama-server has 5 parallel slots
    # sharing 16640 total tokens = 3328 per slot).
    # Budget: 3328 - 400 (prompt template) - 1200 (output) = ~1728 tokens for content.
    # At ~4 chars/token: ~6900 chars total. Split: 60% subject (4000) + 40% standard (2800).
    _MAX_SUBJECT_CHARS = 4000
    _MAX_STANDARD_CHARS = 2800
    _MAX_SUBJECT_CHUNKS = 10
    _MAX_STANDARD_CHUNKS = 6
    # Keep a FULL buffer for multi-batch mode (used below) — gives richer findings.
    _FULL_SUBJECT_CHARS = 18000
    _FULL_STANDARD_CHARS = 12000

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

    # Full buffers used by multi-batch mode below for richer clause-by-clause analysis
    subject_full = "\n\n".join(
        f"[{c['metadata'].get('filename', 'Unknown')}]: {c['text']}"
        for c in subject_chunks[:30]
    )
    if len(subject_full) > _FULL_SUBJECT_CHARS:
        subject_full = subject_full[:_FULL_SUBJECT_CHARS]
    standards_full = "\n\n".join(c["text"] for c in standard_chunks[:20])
    if len(standards_full) > _FULL_STANDARD_CHARS:
        standards_full = standards_full[:_FULL_STANDARD_CHARS]

    scope_note = f"\nFocus specifically on: {body.check_scope}" if body.check_scope else ""

    # ── Compliance prompt (Gemma-safe) ──
    # Gemma echoes the first sentence when it reads like a role/instruction header.
    # Fix: structure the prompt as pure data with the JSON array already started
    # at the end so Gemma's first generated token continues the array, not the prompt.
    prompt = f"""SUBJECT DOCUMENTS ({subject_filenames_str}):
{subject_text}

STANDARDS:
{standards_text}
{scope_note}

Instructions: Compare each standard clause against the subject documents.
For each clause output one JSON object with keys: topic, clause_id, requirement, acceptance_criterion, verdict, severity, finding, recommendation, citation.
verdict: Compliant | Non-Compliant | Partial | Missing | Contradiction | Unverifiable
severity: Critical | Major | Minor | None
Output 5-8 findings. Return a JSON array only. No prose. No markdown.
["""

    # ═══════════════════════════════════════════════════════════
    # MULTI-BATCH COMPLIANCE (Primary path for thorough findings)
    # Slice standards into 3 batches; pair each with subject slice.
    # 3 LLM calls × 3-5 findings each = 9-15 total findings spanning the FULL standard.
    # Each call ~1700 input + ~1200 output tokens — safely under 3328 limit.
    # ═══════════════════════════════════════════════════════════
    findings = []
    try:
        SL = len(standards_full)
        std_slices = [
            standards_full[: SL // 3],
            standards_full[SL // 3 : 2 * SL // 3],
            standards_full[2 * SL // 3 :],
        ] if SL > 500 else [standards_full]

        # Subject slice for each batch: rotate through subject_full thirds for coverage
        SubL = len(subject_full)
        if SubL > 500 and len(std_slices) >= 3:
            sub_slices = [
                subject_full[: SubL // 3][:3500],
                subject_full[SubL // 3 : 2 * SubL // 3][:3500],
                subject_full[2 * SubL // 3 :][:3500],
            ]
        else:
            sub_slices = [subject_full[:3500]] * len(std_slices)

        loop = asyncio.get_event_loop()
        for std_slice, sub_slice in zip(std_slices, sub_slices):
            batch_findings = await loop.run_in_executor(
                None, _run_compliance_batch,
                sub_slice, std_slice[:2500], subject_filenames_str, scope_note, 1200,
            )
            if batch_findings:
                findings.extend(batch_findings)

        # De-duplicate by clause_id (case-insensitive)
        seen_clauses = set()
        deduped = []
        for f in findings:
            cid = (f.get("clause_id", "") or "").strip().lower()
            if cid and cid in seen_clauses:
                continue
            if cid:
                seen_clauses.add(cid)
            deduped.append(f)
        findings = deduped
        logger.info("Compliance multi-batch produced %d unique findings across %d batches",
                    len(findings), len(std_slices))
    except Exception as e:
        logger.warning("Compliance multi-batch failed (%s) — falling back to single-pass", e)
        findings = []

    if findings:
        # Skip single-pass since multi-batch succeeded
        findings_raw = ""  # not used downstream when findings is already populated
        _SKIP_SINGLE_PASS = True
    else:
        _SKIP_SINGLE_PASS = False

    messages = [
        {"role": "user", "content": prompt},
    ]

    if not _SKIP_SINGLE_PASS:
        try:
            findings_raw = llm_engine.generate(messages, max_tokens=1200, temperature=0.1)
        except Exception as e:
            logger.error("Compliance LLM call failed: %s", e)
            raise HTTPException(status_code=500, detail="Compliance analysis engine is temporarily unavailable. Please try with smaller documents or fewer standards.")
    else:
        findings_raw = "[]"  # placeholder so downstream parsing is a no-op

    # ── Echo-strip: Gemma echoes the prompt as markdown bullet list [* text...]
    # A valid JSON array MUST start with '[{' or '[ {' — NOT '[*', '[\n*', '[word'.
    # Strategy: find the first '[{' or '{' that indicates real JSON.
    _strip = findings_raw.strip()

    def _is_json_array_start(s: str) -> bool:
        """Return True only if s starts with a real JSON array (not a markdown list)."""
        if not s.startswith('['):
            return False
        # Scan past '[' and whitespace to find the first meaningful char
        i = 1
        while i < len(s) and s[i] in ' \t\n\r':
            i += 1
        return i < len(s) and s[i] == '{'

    if _is_json_array_start(_strip):
        findings_raw = _strip
    elif _strip.startswith('{'):
        findings_raw = '[' + _strip + ']'
    else:
        # Search for first real JSON object or array-of-objects
        _brace = _strip.find('{')
        # Find '[{' pattern (real JSON array)
        _bracket_brace = _strip.find('[{')
        if _bracket_brace < 0:
            # Try '[ {' with spaces
            import re as _re
            _m = _re.search(r'\[\s*\{', _strip)
            _bracket_brace = _m.start() if _m else -1
        if _bracket_brace >= 0 and (_brace < 0 or _bracket_brace <= _brace):
            findings_raw = _strip[_bracket_brace:]
        elif _brace >= 0:
            findings_raw = '[' + _strip[_brace:]
        else:
            findings_raw = '[' + _strip

    logger.debug("Compliance raw after echo-strip (first 200): %s", findings_raw[:200])

    # Workstream D: Multi-strategy JSON parsing with graceful degradation
    # Skip this entire block if multi-batch already produced findings.
    if not _SKIP_SINGLE_PASS:
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
    
    # Trim standards for the second pass to fit within 3328-token per-request limit.
    _standards_short = standards_text[:1500] if len(standards_text) > 1500 else standards_text
    missing_prompt = f"""STANDARD (excerpt):
{_standards_short}

Already checked clauses:
{covered_str}

List any CRITICAL requirements in the STANDARD completely MISSING from the subject documents.
Output JSON array only. Each item: {{topic, clause_id, requirement, acceptance_criterion, verdict: "Missing", severity: "Major", finding, recommendation, citation: "N/A"}}
If none missing, return [].
["""

    messages_missing = [
        {"role": "user", "content": missing_prompt},
    ]
    try:
        missing_raw = llm_engine.generate(messages_missing, max_tokens=600, temperature=0.0)
        # Echo-strip for second pass — same robust logic as primary pass
        _ms = missing_raw.strip()
        if _is_json_array_start(_ms):
            pass  # already valid
        elif _ms.startswith('{'):
            _ms = '[' + _ms + ']'
        else:
            _brace2 = _ms.find('{')
            _m2 = __import__('re').search(r'\[\s*\{', _ms)
            _bb2 = _m2.start() if _m2 else -1
            if _bb2 >= 0 and (_brace2 < 0 or _bb2 <= _brace2):
                _ms = _ms[_bb2:]
            elif _brace2 >= 0:
                _ms = '[' + _ms[_brace2:]
            else:
                _ms = '[]'  # nothing to parse — skip gracefully
        cleaned = _clean_json(_ms)
        start = cleaned.find("[")
        end = cleaned.rfind("]") + 1
        if start != -1 and end > start:
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
