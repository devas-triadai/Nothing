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


def _clean_json(raw: str) -> str:
    """
    Strip markdown code fences and extract the first JSON array or object
    from LLM output before parsing.

    Gemma 4 (and most instruction-tuned LLMs) wrap JSON in:
        ```json\n{...}\n```
    or embed it inside preamble text.  This helper finds the first '[' or
    '{' and returns from there to the matching closing bracket/brace.
    """
    # Remove ```json ... ``` or ``` ... ``` fences
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'```\s*$', '', cleaned.strip(), flags=re.MULTILINE)
    cleaned = cleaned.strip()

    # If text still contains preamble, try to extract the first JSON block
    arr_start = cleaned.find('[')
    obj_start = cleaned.find('{')

    if arr_start != -1 and (obj_start == -1 or arr_start < obj_start):
        # Find matching closing bracket — naive but works for well-formed JSON
        depth = 0
        for i, ch in enumerate(cleaned[arr_start:], start=arr_start):
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    return cleaned[arr_start:i + 1]
        return cleaned[arr_start:]

    if obj_start != -1:
        depth = 0
        for i, ch in enumerate(cleaned[obj_start:], start=obj_start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return cleaned[obj_start:i + 1]
        return cleaned[obj_start:]

    return cleaned


# ── Master LLM System Prompt for Intelligent Slide Design ──
_PPT_SYSTEM_PROMPT = """You are an elite PowerPoint architect for Indian Coast Guard presentations.

You MUST analyze the content and decide the BEST visual layout for each slide.
DO NOT use only bullet slides — use a MIX of layouts to create engaging, professional presentations.

AVAILABLE LAYOUTS (use all types where appropriate):
1. "title"          — First slide only. Fields: title, subtitle
2. "section_header" — Section transition. Fields: title, subtitle
3. "bullets"        — Standard content. Fields: title, bullets (list of 3-6 strings), notes
4. "two_column"     — Comparison/pros-cons. Fields: title, left_column {header, items[]}, right_column {header, items[]}, notes
5. "table"          — Data tables. Fields: title, table_data {headers[], rows[[]]}, notes
6. "diagram"        — Process flow/architecture/hierarchy. Fields: title, diagram_data {type, nodes[], edges[]}, notes
   Diagram types: "flowchart", "hierarchy", "block_diagram", "cycle", "radial", "matrix", "pyramid", "swimlane"
   Node shapes: "rounded_rect", "rect", "diamond", "oval", "hexagon", "cylinder"
   Each node: {"id": "A", "label": "text", "shape": "rounded_rect"}
   Each edge: {"from": "A", "to": "B", "label": "optional text"}
7. "chart"          — Data visualization. Fields: title, chart_data {type, title, data {labels[], values[]}}, notes
   Chart types: "bar_chart", "pie_chart", "line_chart", "comparison_bar", "timeline"
   For comparison_bar: data {labels[], groups[{name, values[]}]}
8. "image"          — Image/diagram from documents. Fields: title, caption, notes
9. "thank_you"      — Last slide. Fields: title, subtitle

LAYOUT SELECTION RULES:
- If content describes a PROCESS or WORKFLOW → use "diagram" with type "flowchart"
- If content describes an ORGANIZATION or HIERARCHY → use "diagram" with type "hierarchy"
- If content describes a SYSTEM ARCHITECTURE → use "diagram" with type "block_diagram"
- If content has NUMERICAL DATA or STATISTICS → use "chart"
- If content COMPARES two things → use "two_column"
- If content has STRUCTURED DATA with multiple attributes → use "table"
- If content references existing IMAGES or DIAGRAMS → use "image"
- Use "section_header" between major topic transitions
- The LAST slide must be "thank_you"
- AIM for at least 40% non-bullet slides

Return ONLY a valid JSON array. No markdown. No explanations."""


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
        prompt = f"""Create a professional PowerPoint with exactly {body.num_slides} slides about: {body.topic}

DOCUMENT CONTEXT:
{context_text}
{extracted_data_hint}

{f'Style notes: {body.style_notes}' if body.style_notes else ''}
{has_images_hint}

Requirements:
- Slide 1 MUST be "layout": "title"
- Last slide MUST be "layout": "thank_you"
- Use at least 2 different non-bullet layouts (diagrams, charts, tables, two_column)
- Include a diagram if the content describes any process, system, or hierarchy
- Include a chart if there is any numerical/statistical data
- Include section_header slides between major topic shifts
- Every slide must have "layout", "title", and layout-specific fields

Return ONLY a valid JSON array of {body.num_slides} slide objects:"""

    messages = [
        {"role": "system", "content": _PPT_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    raw = await asyncio.to_thread(
        llm_engine.generate, messages,
        max_tokens=3000, temperature=0.2,
        response_format={"type": "json_object"}, raw=True,
    )

    # ── 4. Parse and validate slide JSON ──
    try:
        cleaned = _clean_json(raw)
        start = cleaned.find("[")
        end = cleaned.rfind("]") + 1
        if start == -1 or end == 0:
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON array or object found in LLM response")
            wrapper = json.loads(cleaned[start:end])
            slides_data = wrapper.get("slides", list(wrapper.values())[0] if wrapper else [])
        else:
            slides_data = json.loads(cleaned[start:end])
        if not isinstance(slides_data, list) or len(slides_data) == 0:
            raise ValueError("Expected a non-empty JSON array of slides")
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse slide JSON: %s\nRaw: %s", e, raw[:500])
        raise HTTPException(status_code=500, detail="Failed to generate slide structure. Please try again.")

    # ── 5. Validate layout fields and add defaults ──
    valid_layouts = {"title", "section_header", "bullets", "two_column", "table", "diagram", "chart", "image", "thank_you"}
    for sd in slides_data:
        layout = sd.get("layout", "bullets")
        if layout not in valid_layouts:
            sd["layout"] = "bullets"
        # Ensure bullets exist as fallback
        if "bullets" not in sd:
            sd["bullets"] = []

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

    try:
        cleaned = _clean_json(raw)
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON object found in LLM response")
        quiz_data = json.loads(cleaned[start:end])
        # Validate minimal structure
        if not isinstance(quiz_data, dict):
            raise ValueError("Quiz response is not a JSON object")
        if "mcq" not in quiz_data:
            quiz_data["mcq"] = []
        if "short_answer" not in quiz_data:
            quiz_data["short_answer"] = []
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse quiz JSON: %s\nRaw (first 800 chars): %s", e, raw[:800])
        raise HTTPException(status_code=500, detail=f"Failed to generate quiz ({e}). Please try again.")

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
