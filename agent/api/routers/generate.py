"""
AGRA Phase 2 — Router: Content Generation (PPT, Summary, Quiz)
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
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from api.utils.auth_check import get_current_user
from api.utils.usage_logger import log_usage
from api.rag import embedder, llm as llm_engine
from api.rag.vector_store import get_store
from api.rag.reranker import rerank
from api.generators.ppt_gen import build_pptx
from docx import Document as DocxDocument

logger = logging.getLogger("agra.generate")

router = APIRouter()

import os as _os
_DATA_DIR = Path(_os.environ.get("AGRA_DATA_DIR", "/workspace/agra_data"))
if not _DATA_DIR.exists():
    _DATA_DIR = Path(__file__).resolve().parent.parent.parent / "agra_data"
_OUTPUTS_DIR = _DATA_DIR / "outputs"
_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def _extract_balanced(text: str, open_char: str, close_char: str) -> Optional[str]:
    """
    Depth-counting bracket matcher. Returns the first balanced substring
    starting with `open_char`, accounting for strings (single/double quotes)
    and escaped chars inside strings. Returns None if no balanced region found.
    """
    start = text.find(open_char)
    if start < 0:
        return None

    depth = 0
    in_string = False
    string_char = ""
    i = start
    n = len(text)

    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\" and i + 1 < n:
                # Skip escaped character
                i += 2
                continue
            if ch == string_char:
                in_string = False
        else:
            if ch in ('"', "'"):
                in_string = True
                string_char = ch
            elif ch == open_char:
                depth += 1
            elif ch == close_char:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        i += 1

    return None  # unbalanced


def _clean_json(raw: str) -> str:
    """
    Strip markdown code fences and extract the first balanced JSON array or
    object from LLM output. Uses depth-counting bracket matching so it does
    not get confused by strings containing brackets or trailing prose.
    """
    if not raw:
        return ""

    # 1. Strip markdown fences aggressively (anywhere in text)
    cleaned = re.sub(r'```(?:json)?\s*', '', raw, flags=re.IGNORECASE)
    cleaned = re.sub(r'```', '', cleaned)
    cleaned = cleaned.strip()

    # 2. Locate first '[' or '{' and pick whichever appears first
    arr_pos = cleaned.find('[')
    obj_pos = cleaned.find('{')

    if arr_pos < 0 and obj_pos < 0:
        return cleaned

    # Choose the one that appears earlier in the text
    use_array = (arr_pos >= 0) and (obj_pos < 0 or arr_pos < obj_pos)

    if use_array:
        result = _extract_balanced(cleaned, '[', ']')
        if result:
            return result

    result = _extract_balanced(cleaned, '{', '}')
    if result:
        return result

    return cleaned


def _repair_json_with_llm(broken: str, error_msg: str) -> Optional[dict]:
    """
    Last-ditch repair: ask the LLM to fix malformed JSON. Returns parsed
    dict on success, None if repair also fails. Uses tight max_tokens to
    keep latency reasonable.
    """
    try:
        repair_prompt = (
            "The following text was supposed to be valid JSON but failed to parse. "
            f"Parser error: {error_msg}\n\n"
            "Return ONLY the corrected JSON. No prose, no explanation, no markdown fences.\n\n"
            f"BROKEN JSON:\n{broken[:6000]}"
        )
        repaired_raw = llm_engine.generate(
            messages=[
                {"role": "system", "content": "You are a JSON repair tool. Output only valid JSON."},
                {"role": "user", "content": repair_prompt},
            ],
            max_tokens=2048,
            temperature=0.0,
            response_format={"type": "json_object"},
            raw=True,
        )
        cleaned = _clean_json(repaired_raw)
        return json.loads(cleaned)
    except Exception as e:
        logger.warning("JSON repair pass failed: %s", e)
        return None


def _build_fallback_slides(topic: str, context_text: str, num_slides: int = 10) -> list:
    """
    Generate a basic bullet-slide deck when the LLM fails to return valid JSON.
    Splits context into chunks and creates one slide per chunk.
    """
    slides = [
        {"layout": "title", "title": topic, "subtitle": "AGRA Generated Presentation"},
    ]
    # Split context into roughly equal chunks for bullet slides
    sentences = [s.strip() for s in re.split(r'[.\n]+', context_text) if len(s.strip()) > 20]
    chunk_size = max(1, len(sentences) // max(1, num_slides - 2))
    idx = 0
    for i in range(num_slides - 2):
        chunk = sentences[idx:idx + chunk_size]
        idx += chunk_size
        if not chunk:
            chunk = [f"Section {i + 1} content placeholder"]
        slides.append({
            "layout": "bullets",
            "title": f"{topic} — Key Point {i + 1}",
            "bullets": [s[:200] for s in chunk[:6]],
        })
    slides.append({"layout": "thank_you", "title": "Thank You", "subtitle": "AGRA — AI-Powered Knowledge Management"})
    return slides


# ── Master LLM Prompt for Intelligent Slide Design ──
# NOTE: Gemma 4 IT does NOT reliably honour system-prompt JSON constraints,
# so ALL instructions live in the user message.
_PPT_SLIDE_LAYOUTS = """
AVAILABLE LAYOUTS (use a MIX — aim for 40%+ non-bullet):
1. "title"          — First slide only. Fields: title, subtitle
2. "section_header" — Section transition. Fields: title, subtitle
3. "bullets"        — Standard content. Fields: title, bullets (list of 3-6 strings), notes
4. "two_column"     — Comparison. Fields: title, left_column {header, items[]}, right_column {header, items[]}, notes
5. "table"          — Data tables. Fields: title, table_data {headers[], rows[[]]}, notes
6. "diagram"        — Process/hierarchy. Fields: title, diagram_data {type, nodes[], edges[]}, notes
   Diagram types: "flowchart", "hierarchy", "block_diagram", "cycle", "radial", "matrix", "pyramid", "swimlane"
   Each node: {"id": "A", "label": "text", "shape": "rounded_rect"}
   Each edge: {"from": "A", "to": "B", "label": "optional text"}
7. "chart"          — Data viz. Fields: title, chart_data {type, title, data {labels[], values[]}}, notes
   Chart types: "bar_chart", "pie_chart", "line_chart", "comparison_bar", "timeline"
   For comparison_bar: data {labels[], groups[{name, values[]}]}
8. "image"          — Image from docs. Fields: title, caption, notes
9. "thank_you"      — Last slide. Fields: title, subtitle
"""


class PPTRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    num_slides: int = Field(default=10, ge=3, le=25)
    doc_ids: List[str] = Field(default_factory=list)
    style_notes: Optional[str] = None
    # Revision / versioning fields
    revision_prompt: Optional[str] = Field(None, description="Instructions for revising an existing PPT")
    previous_slides_json: Optional[str] = Field(None, description="JSON of previous slides to revise")
    version: int = Field(default=1, ge=1, description="Version number (v1, v2, v3...)")


@router.post("/generate/ppt")
async def generate_ppt(
    body: PPTRequest,
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """
    Generate a PowerPoint presentation from RAG context.
    Intelligently selects slide layouts based on content analysis.
    Extracts images from uploaded documents when available.
    Returns the .pptx file as a download.
    """
    auth_header_token = ""
    if request:
        auth_h = request.headers.get("authorization", "")
        auth_header_token = auth_h.replace("Bearer ", "") if auth_h else ""
    store = get_store()
    start_time = time.time()

    # ── 1. Gather context from documents ──
    _loop = asyncio.get_event_loop()
    context_chunks = []
    if body.doc_ids:
        for did in body.doc_ids:
            context_chunks.extend(store.get_chunks_by_doc(did))
    else:
        query_emb = await _loop.run_in_executor(None, embedder.embed_query, body.topic)
        candidates = await _loop.run_in_executor(
            None, store.hybrid_search, body.topic, query_emb, 20
        )
        context_chunks = await _loop.run_in_executor(
            None, rerank, body.topic, candidates, 10
        )

    context_text = "\n\n".join(c["text"][:500] for c in context_chunks[:15])

    # ── 2. Extract images from uploaded documents ──
    extracted_images = []
    try:
        from api.generators.image_extractor import get_best_images_for_topic
        doc_ids_for_images = body.doc_ids if body.doc_ids else list({
            c.get("metadata", {}).get("doc_id", "") for c in context_chunks if c.get("metadata", {}).get("doc_id")
        })
        if doc_ids_for_images:
            extracted_images = get_best_images_for_topic(doc_ids_for_images, max_total=5)
            logger.info("Extracted %d images from documents for PPT.", len(extracted_images))
    except Exception as e:
        logger.debug("Image extraction skipped: %s", e)

    has_images_hint = ""
    if extracted_images:
        has_images_hint = f"""
NOTE: {len(extracted_images)} images/diagrams were found in the source documents.
Include {min(len(extracted_images), 3)} slides with "layout": "image" to display them.
Place image slides near relevant content sections."""

    # ── 2.5 LLM Data Extraction Pre-Pass (Chart Data Enhancement) ──
    # Skip pre-pass if context is tiny — reduces LLM load and failure rate
    extracted_data_hint = ""
    if len(context_text) > 500:
        try:
            data_ext_prompt = f"Analyze the following text and extract any numerical data, statistics, or metrics into structured tabular formats. Text:\n{context_text[:2000]}"
            data_ext_messages = [{"role": "system", "content": "You extract numbers into JSON arrays."}, {"role": "user", "content": data_ext_prompt}]
            prepass_raw = await asyncio.to_thread(
                llm_engine.generate, data_ext_messages,
                max_tokens=512, temperature=0.1, raw=True,
            )
            extracted_data_hint = f"\nNUMERICAL DATA FOR CHARTS:\n{_clean_json(prepass_raw)}\n"
        except Exception as e:
            logger.debug("Data pre-pass failed: %s", e)

    # ── 3. Build LLM prompt ──
    if body.revision_prompt and body.previous_slides_json:
        prompt = f"""You previously generated a PowerPoint about: {body.topic}

Current slides (JSON):
{body.previous_slides_json}

User revision request (this becomes version v{body.version}):
{body.revision_prompt}

Additional context:
{context_text}
{extracted_data_hint}
{has_images_hint}

Return ONLY an updated JSON array with all layout fields preserved and changes applied."""
    else:
        prompt = f"""You are an elite PowerPoint architect for Indian Coast Guard presentations.

Create a professional PowerPoint with exactly {body.num_slides} slides about: {body.topic}

DOCUMENT CONTEXT:
{context_text}
{extracted_data_hint}

{f'Style notes: {body.style_notes}' if body.style_notes else ''}
{has_images_hint}

{_PPT_SLIDE_LAYOUTS}

Requirements:
- Slide 1 MUST be "layout": "title"
- Last slide MUST be "layout": "thank_you"
- Use at least 2 different non-bullet layouts (diagrams, charts, tables, two_column)
- Include a diagram if the content describes any process, system, or hierarchy
- Include a chart if there is any numerical/statistical data
- Include section_header slides between major topic shifts
- Every slide must have "layout", "title", and layout-specific fields

Return ONLY a valid JSON array of {body.num_slides} slide objects. No other text, no markdown, no explanations:"""

    # ── 4. Generate slides with retry ──
    # Attempt 1: full intelligent prompt
    # Attempt 2 (fallback): simplified bullet-only prompt
    slides_data = None
    for attempt, (temp, prompt_text) in enumerate([
        (0.1, prompt),
        (0.0, f"Create exactly {body.num_slides} slides about: {body.topic}\n\nContext:\n{context_text}\n\nReturn ONLY a JSON array. Each slide MUST have: layout (title/bullets/section_header/thank_you), title, bullets."),
    ], 1):
        messages = [{"role": "user", "content": prompt_text}]
        try:
            raw = await asyncio.to_thread(
                llm_engine.generate, messages,
                max_tokens=2500, temperature=temp, raw=True,
            )
            cleaned = _clean_json(raw)
            # _clean_json now returns the outermost JSON array or object via regex
            slides_data = json.loads(cleaned)
            if isinstance(slides_data, list) and len(slides_data) > 0:
                logger.info("PPT JSON parsed successfully on attempt %d", attempt)
                break
            raise ValueError("Empty or non-array slides")
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("PPT attempt %d failed: %s\nRaw (first 400 chars): %s", attempt, e, raw[:400])
            slides_data = None

    if not slides_data:
        logger.warning("PPT generation failed after all LLM retries. Using fallback slide builder.")
        slides_data = _build_fallback_slides(body.topic, context_text, body.num_slides)

    # ── 5. Validate layout fields and enforce exact slide count ──
    valid_layouts = {"title", "section_header", "bullets", "two_column", "table", "diagram", "chart", "image", "sources", "thank_you"}
    for sd in slides_data:
        layout = sd.get("layout", "bullets")
        if layout not in valid_layouts:
            sd["layout"] = "bullets"
        if "bullets" not in sd:
            sd["bullets"] = []

    # Enforce exact slide count
    target = body.num_slides
    if len(slides_data) < target:
        while len(slides_data) < target:
            slides_data.insert(max(1, len(slides_data) - 1), {"layout": "section_header", "title": "Additional Content", "subtitle": ""})
    elif len(slides_data) > target:
        # Keep first (title) and last (thank_you); trim from middle
        first = slides_data[0]
        last = slides_data[-1]
        middle = slides_data[1:-1]
        keep = middle[:max(0, target - 2)]
        slides_data = [first] + keep + [last]

    # Auto-inject sources slide if documents were used and count allows
    source_names = []
    if body.doc_ids:
        source_names = [store.get_chunks_by_doc(did)[0]["metadata"].get("filename", did) for did in body.doc_ids if store.get_chunks_by_doc(did)]
    else:
        source_names = list({c.get("metadata", {}).get("filename", "") for c in context_chunks if c.get("metadata", {}).get("filename")})
    source_names = [s for s in source_names if s]
    if source_names and len(slides_data) >= 3:
        # Replace second-to-last slide (before thank_you) with sources
        slides_data[-2] = {"layout": "sources", "title": "Sources & References", "sources": source_names[:20]}

    # ── 6. Build PPTX ──
    job_id = str(uuid.uuid4())
    version_label = f"_v{body.version}" if body.version > 1 else ""
    safe_topic = body.topic[:30].replace(' ', '_')
    output_filename = f"{job_id}.pptx"
    output_path = _OUTPUTS_DIR / output_filename
    
    # ── 6.5 ICG Master Template Integration ──
    assets_dir = Path(__file__).resolve().parent.parent.parent / "assets"
    template_path = str(assets_dir / "icg_master.pptx") if (assets_dir / "icg_master.pptx").exists() else None

    build_pptx(
        slides_data,
        str(output_path),
        title=body.topic,
        template_path=template_path,
        extracted_images=extracted_images,
    )

    logger.info("Generated PPT v%d: %s (%d slides, %d doc images)", body.version, output_path.name, len(slides_data), len(extracted_images))

    elapsed_ms = (time.time() - start_time) * 1000
    log_usage(
        action_type="ppt",
        module="generate",
        token=auth_header_token,
        response_time_ms=elapsed_ms,
    )

    return FileResponse(
        path=str(output_path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=f"AGRA_{safe_topic}{version_label}.pptx",
        headers={"X-PPT-Version": str(body.version), "X-Slides-JSON": json.dumps(slides_data)},
    )


# ═══════════════════════════════════════════════════════════════
#  EXECUTIVE SUMMARY
# ═══════════════════════════════════════════════════════════════

class SummaryRequest(BaseModel):
    doc_ids: List[str] = Field(default_factory=list)
    doc_id: Optional[str] = None  # Legacy support
    summary_type: str = Field(default="executive", pattern="^(executive|technical)$")


@router.post("/generate/summary")
async def generate_summary(
    body: SummaryRequest,
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """
    Generate an executive or technical summary of a document.
    Returns SSE stream of the summary + a .docx download link.
    """
    summary_start = time.time()
    auth_tok = ""
    if request:
        ah = request.headers.get("authorization", "")
        auth_tok = ah.replace("Bearer ", "") if ah else ""
    store = get_store()
    target_doc_ids = body.doc_ids if body.doc_ids else ([body.doc_id] if body.doc_id else [])
    if not target_doc_ids:
        raise HTTPException(status_code=400, detail="Must provide at least one doc_id.")

    chunks = []
    filenames = []
    for did in target_doc_ids:
        doc_chunks = store.get_chunks_by_doc(did)
        if doc_chunks:
            chunks.extend(doc_chunks)
            if doc_chunks[0]["metadata"].get("filename") not in filenames:
                filenames.append(doc_chunks[0]["metadata"].get("filename", "document"))

    if not chunks:
        raise HTTPException(status_code=404, detail="Documents not found in knowledge base.")

    # Combine all chunk text (truncate if too long for context)
    full_text = "\n\n".join(c["text"] for c in chunks)
    if len(full_text) > 30000:
        full_text = full_text[:30000] + "\n[Content truncated for summary generation]"

    filename_label = ", ".join(filenames) if len(filenames) <= 3 else f"{len(filenames)} Documents"

    type_label = "Executive Summary" if body.summary_type == "executive" else "Technical Summary"
    prompt = f"""Generate a comprehensive {type_label} of the following document(s).

DOCUMENTS: {filename_label}

CONTENT:
{full_text}

FORMAT:
1. **Overview** — 2-3 sentences describing the document's purpose
2. **Key Points** — bullet list of the most important findings/topics
3. **Detailed Analysis** — paragraph-form analysis of major sections
4. **Conclusions & Recommendations** — actionable takeaways

Cite specific sections where relevant using [Page X] notation."""

    messages = [
        {"role": "system", "content": "You are a senior analyst creating professional document summaries for Indian Coast Guard leadership."},
        {"role": "user", "content": prompt},
    ]

    # Stream the summary and also collect for DOCX
    job_id = str(uuid.uuid4())
    collected_text: list = []

    async def event_stream():
        token_queue = asyncio.Queue()

        def _run_llm():
            try:
                for tok in llm_engine.stream_generate(messages, max_tokens=3000):
                    token_queue.put_nowait(tok)
                token_queue.put_nowait(None)
            except Exception as e:
                logger.error("Summary LLM error: %s", e)
                token_queue.put_nowait(None)

        llm_thread = asyncio.get_event_loop().run_in_executor(None, _run_llm)

        while True:
            tok = await token_queue.get()
            if tok is None:
                break
            collected_text.append(tok)
            yield f"data: {json.dumps({'token': tok})}\n\n"

        # Build DOCX
        docx_path = _OUTPUTS_DIR / f"{job_id}_summary.docx"
        doc = DocxDocument()
        doc.add_heading(f"{type_label}: {filename_label}", level=1)
        doc.add_paragraph("".join(collected_text))
        
        # Add Watermark (FR-GEN-006)
        try:
            section = doc.sections[0]
            footer = section.footer
            footer_para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
            footer_para.text = "AI-Generated Draft - ICG AGRA"
        except Exception as e:
            logger.warning(f"Could not add watermark: {e}")

        doc.save(str(docx_path))

        yield f"data: {json.dumps({'done': True, 'download_url': f'/api/agent/download/{job_id}_summary.docx'})}\n\n"

        # Log usage
        elapsed_ms = (time.time() - summary_start) * 1000
        log_usage(action_type="summary", module="generate", token=auth_tok, response_time_ms=elapsed_ms)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ═══════════════════════════════════════════════════════════════
#  KNOWLEDGE QUIZ
# ═══════════════════════════════════════════════════════════════

class QuizRequest(BaseModel):
    doc_id: str
    num_mcq: int = Field(default=5, ge=1, le=20)
    num_short_answer: int = Field(default=3, ge=0, le=10)
    difficulty: str = Field(default="medium", description="easy, medium, hard")
    scope: str = Field(default="comprehensive", description="concepts, details, comprehensive")


@router.post("/generate/quiz")
async def generate_quiz(
    body: QuizRequest,
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """
    Generate a knowledge quiz from a document.
    Returns JSON quiz data + a .docx download link.
    """
    quiz_start = time.time()
    auth_tok = ""
    if request:
        ah = request.headers.get("authorization", "")
        auth_tok = ah.replace("Bearer ", "") if ah else ""
    store = get_store()
    chunks = store.get_chunks_by_doc(body.doc_id)

    if not chunks:
        raise HTTPException(status_code=404, detail=f"Document {body.doc_id} not found in knowledge base.")

    content = "\n\n".join(c["text"] for c in chunks[:20])
    filename = chunks[0]["metadata"].get("filename", "document")

    prompt = f"""Generate a knowledge assessment quiz from this document.

DOCUMENT: {filename}

CONTENT:
{content}

Generate EXACTLY:
- {body.num_mcq} Multiple Choice Questions (MCQ) with 4 options each (A, B, C, D) and the correct answer
- {body.num_short_answer} Short Answer Questions with model answers

DIFFICULTY LEVEL: {body.difficulty.upper()}
SCOPE FOCUS: {body.scope.upper()}

Return ONLY valid JSON in this exact format:
{{
  "title": "Quiz: [document topic]",
  "mcq": [
    {{
      "question": "...",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "correct": "A",
      "explanation": "..."
    }}
  ],
  "short_answer": [
    {{
      "question": "...",
      "model_answer": "..."
    }}
  ]
}}"""

    messages = [
        {"role": "system", "content": "You are an expert quiz designer. Return only valid JSON."},
        {"role": "user", "content": prompt},
    ]

    raw = await asyncio.to_thread(
        llm_engine.generate, messages,
        max_tokens=4096, temperature=0.5,
        response_format={"type": "json_object"}, raw=True,
    )

    quiz_data: Optional[dict] = None
    last_error: Optional[Exception] = None

    # Pass 1: clean + parse with depth-counting matcher
    try:
        cleaned = _clean_json(raw)
        if not cleaned:
            raise ValueError("Empty response from LLM")
        quiz_data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        last_error = e
        logger.warning("Quiz JSON parse pass 1 failed: %s", e)

    # Pass 2: LLM repair if pass 1 failed
    if quiz_data is None:
        logger.info("Attempting LLM-based JSON repair for quiz output...")
        repaired = await asyncio.to_thread(
            _repair_json_with_llm, raw, str(last_error or "unknown")
        )
        if repaired is not None:
            quiz_data = repaired
            logger.info("Quiz JSON repaired successfully via LLM pass.")

    # Pass 3: Final synthetic fallback to avoid 500 error
    if quiz_data is None or not isinstance(quiz_data, dict):
        logger.error(
            "Quiz JSON unrecoverable. Returning minimal fallback. Raw (first 800 chars): %s",
            raw[:800],
        )
        quiz_data = {
            "title": f"Quiz: {filename}",
            "mcq": [],
            "short_answer": [],
            "_fallback": True,
            "_error": "The model failed to produce structured questions. Please try again.",
        }

    # Validate minimal structure
    if "mcq" not in quiz_data:
        quiz_data["mcq"] = []
    if "short_answer" not in quiz_data:
        quiz_data["short_answer"] = []

    # Build DOCX
    job_id = str(uuid.uuid4())
    docx_path = _OUTPUTS_DIR / f"{job_id}_quiz.docx"
    doc = DocxDocument()
    doc.add_heading(quiz_data.get("title", f"Quiz: {filename}"), level=1)

    doc.add_heading("Multiple Choice Questions", level=2)
    for i, q in enumerate(quiz_data.get("mcq", []), 1):
        doc.add_paragraph(f"Q{i}. {q['question']}", style="List Number")
        for key in ("A", "B", "C", "D"):
            opt = q.get("options", {}).get(key, "")
            doc.add_paragraph(f"   {key}) {opt}")
        doc.add_paragraph(f"   ✓ Correct: {q.get('correct', '?')}")
        doc.add_paragraph("")

    doc.add_heading("Short Answer Questions", level=2)
    for i, q in enumerate(quiz_data.get("short_answer", []), 1):
        doc.add_paragraph(f"Q{i}. {q['question']}", style="List Number")
        doc.add_paragraph(f"   Model Answer: {q.get('model_answer', '')}")
        doc.add_paragraph("")

    # Add Watermark (FR-GEN-006)
    try:
        section = doc.sections[0]
        footer = section.footer
        footer_para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        footer_para.text = "AI-Generated Draft - ICG AGRA"
    except Exception as e:
        logger.warning(f"Could not add watermark: {e}")

    doc.save(str(docx_path))

    elapsed_ms = (time.time() - quiz_start) * 1000
    log_usage(action_type="quiz", module="generate", token=auth_tok, response_time_ms=elapsed_ms)

    return {
        "quiz": quiz_data,
        "download_url": f"/api/agent/download/{job_id}_quiz.docx",
    }


# ═══════════════════════════════════════════════════════════════
#  DRAFT SOTR GENERATOR (FR-GEN-003)
# ═══════════════════════════════════════════════════════════════

class DraftSOTRRequest(BaseModel):
    doc_id: str
    focus_area: Optional[str] = Field(None, description="Specific area to focus the SOTR on")


@router.post("/generate/sotr")
async def generate_draft_sotr(
    body: DraftSOTRRequest,
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """
    Generate a Draft SOTR (Statement of Technical Requirements).
    Returns SSE stream of the SOTR + a .docx download link.
    """
    sotr_start = time.time()
    auth_tok = ""
    if request:
        ah = request.headers.get("authorization", "")
        auth_tok = ah.replace("Bearer ", "") if ah else ""
    
    store = get_store()
    chunks = store.get_chunks_by_doc(body.doc_id)

    if not chunks:
        raise HTTPException(status_code=404, detail=f"Document {body.doc_id} not found in knowledge base.")

    full_text = "\n\n".join(c["text"] for c in chunks)
    if len(full_text) > 25000:
        full_text = full_text[:25000] + "\n[Document truncated]"

    filename = chunks[0]["metadata"].get("filename", "document")
    focus_note = f"\\nFocus specifically on: {body.focus_area}" if body.focus_area else ""

    prompt = f"""Generate a Draft Statement of Technical Requirements (SOTR) based on the following document.

DOCUMENT: {filename}
{focus_note}

CONTENT:
{full_text}

FORMAT the SOTR strictly with the following sections:
1. **Introduction** — Purpose and scope
2. **Applicable Documents** — References and standards
3. **General Requirements** — High-level technical needs
4. **Specific Requirements** — Detailed specifications and performance criteria
5. **Quality Assurance & Testing** — Acceptance criteria

Use formal, objective military specification language (e.g., 'The system shall...', 'The contractor must...')."""

    messages = [
        {"role": "system", "content": "You are a technical specifications writer for the Indian Coast Guard."},
        {"role": "user", "content": prompt},
    ]

    job_id = str(uuid.uuid4())
    collected_text = []

    async def event_stream():
        token_queue = asyncio.Queue()

        def _run_llm():
            try:
                for tok in llm_engine.stream_generate(messages, max_tokens=3500):
                    token_queue.put_nowait(tok)
                token_queue.put_nowait(None)
            except Exception as e:
                logger.error("SOTR LLM error: %s", e)
                token_queue.put_nowait(None)

        llm_thread = asyncio.get_event_loop().run_in_executor(None, _run_llm)

        while True:
            tok = await token_queue.get()
            if tok is None:
                break
            collected_text.append(tok)
            yield f"data: {json.dumps({'token': tok})}\n\n"

        docx_path = _OUTPUTS_DIR / f"{job_id}_sotr.docx"
        doc = DocxDocument()
        doc.add_heading(f"Draft SOTR: {filename}", level=1)
        doc.add_paragraph("".join(collected_text))

        try:
            section = doc.sections[0]
            footer = section.footer
            footer_para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
            footer_para.text = "AI-Generated Draft - ICG AGRA"
        except Exception as e:
            logger.warning(f"Could not add watermark: {e}")

        doc.save(str(docx_path))
        yield f"data: {json.dumps({'done': True, 'download_url': f'/api/agent/download/{job_id}_sotr.docx'})}\n\n"

        log_usage(action_type="draft_sotr", module="generate", token=auth_tok, response_time_ms=(time.time() - sotr_start) * 1000)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════
#  TECHNICAL REVIEW COMMENT GENERATOR (FR-GEN-004)
# ═══════════════════════════════════════════════════════════════

class TechReviewRequest(BaseModel):
    doc_id: str
    target_audience: str = Field(default="shipyard", pattern="^(shipyard|internal|management)$")


@router.post("/generate/tech-review")
async def generate_tech_review(
    body: TechReviewRequest,
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """
    Generate Technical Review Comments for a document.
    """
    review_start = time.time()
    auth_tok = ""
    if request:
        ah = request.headers.get("authorization", "")
        auth_tok = ah.replace("Bearer ", "") if ah else ""
        
    store = get_store()
    chunks = store.get_chunks_by_doc(body.doc_id)

    if not chunks:
        raise HTTPException(status_code=404, detail="Document not found.")

    full_text = "\n\n".join(c["text"] for c in chunks[:30]) # Use first 30 chunks
    filename = chunks[0]["metadata"].get("filename", "document")

    prompt = f"""Generate Technical Review Comments for the following submission document.
Target Audience: {body.target_audience}

DOCUMENT: {filename}
CONTENT:
{full_text}

FORMAT the review strictly as:
1. **General Observations** — Overall assessment of the submission
2. **Major Deviations / Concerns** — Critical issues identified
3. **Clarifications Required** — Specific points needing more details
4. **Recommendations** — Proposed actions or accept/reject advice

Keep the tone professional, objective, and analytical."""

    messages = [
        {"role": "system", "content": "You are a lead technical reviewer for the Indian Coast Guard."},
        {"role": "user", "content": prompt},
    ]

    job_id = str(uuid.uuid4())
    collected_text = []

    async def event_stream():
        token_queue = asyncio.Queue()

        def _run_llm():
            try:
                for tok in llm_engine.stream_generate(messages, max_tokens=3000):
                    token_queue.put_nowait(tok)
                token_queue.put_nowait(None)
            except Exception as e:
                logger.error("Tech review LLM error: %s", e)
                token_queue.put_nowait(None)

        llm_thread = asyncio.get_event_loop().run_in_executor(None, _run_llm)

        while True:
            tok = await token_queue.get()
            if tok is None:
                break
            collected_text.append(tok)
            yield f"data: {json.dumps({'token': tok})}\n\n"

        docx_path = _OUTPUTS_DIR / f"{job_id}_tech_review.docx"
        doc = DocxDocument()
        doc.add_heading(f"Technical Review: {filename}", level=1)
        doc.add_paragraph("".join(collected_text))

        try:
            section = doc.sections[0]
            footer = section.footer
            footer_para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
            footer_para.text = "AI-Generated Draft - ICG AGRA"
        except Exception as e:
            logger.warning(f"Could not add watermark: {e}")

        doc.save(str(docx_path))
        yield f"data: {json.dumps({'done': True, 'download_url': f'/api/agent/download/{job_id}_tech_review.docx'})}\n\n"
        log_usage(action_type="tech_review", module="generate", token=auth_tok, response_time_ms=(time.time() - review_start) * 1000)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
