"""
AGRA Phase 2 — Router: Content Generation (PPT, Summary, Quiz)
"""

import json
import logging
import re
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from api.utils.auth_check import get_current_user
from api.rag import embedder, llm as llm_engine
from api.rag.vector_store import get_store
from api.rag.reranker import rerank
from api.generators.ppt_gen import build_pptx
from docx import Document as DocxDocument

logger = logging.getLogger("agra.generate")

router = APIRouter()

_OUTPUTS_DIR = Path(__file__).resolve().parent.parent.parent / "outputs"
_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def _clean_json(raw: str) -> str:
    """
    Strip markdown code fences from LLM output before JSON parsing.

    Gemma 4 (and most instruction-tuned LLMs) wrap JSON in:
        ```json\n{...}\n```
    or:
        ```\n[...]\n```

    This helper removes those fences and returns the bare JSON string.
    """
    # Remove ```json ... ``` or ``` ... ``` fences
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'```\s*$', '', cleaned.strip(), flags=re.MULTILINE)
    return cleaned.strip()


# ═══════════════════════════════════════════════════════════════
#  PPT GENERATION
# ═══════════════════════════════════════════════════════════════

class PPTRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    num_slides: int = Field(default=10, ge=3, le=25)
    doc_ids: List[str] = Field(default_factory=list)
    style_notes: Optional[str] = None


@router.post("/generate/ppt")
async def generate_ppt(
    body: PPTRequest,
    user: dict = Depends(get_current_user),
):
    """
    Generate a PowerPoint presentation from RAG context.
    Returns the .pptx file as a download.
    """
    store = get_store()

    # Gather context from specified documents (or all)
    context_chunks = []
    if body.doc_ids:
        for did in body.doc_ids:
            context_chunks.extend(store.get_chunks_by_doc(did))
    else:
        query_emb = embedder.embed_query(body.topic)
        candidates = store.hybrid_search(body.topic, query_emb, top_k=20)
        context_chunks = rerank(body.topic, candidates, top_k=10)

    context_text = "\n\n".join(c["text"][:500] for c in context_chunks[:15])

    # Build prompt for slide structure
    prompt = f"""Create a structured PowerPoint presentation with exactly {body.num_slides} slides about: {body.topic}

Based on this context:
{context_text}

{f'Style notes: {body.style_notes}' if body.style_notes else ''}

Return ONLY a JSON array of slide objects. Each slide must have:
- "title": slide title string
- "bullets": list of 3-5 bullet point strings
- "notes": speaker notes string

The first slide should be a title slide with the presentation title and subtitle.
The last slide should be a summary/conclusion slide.

Return valid JSON only, no markdown formatting:"""

    messages = [
        {"role": "system", "content": "You are a presentation expert. Return only valid JSON."},
        {"role": "user", "content": prompt},
    ]

    raw = llm_engine.generate(messages, max_tokens=4096, temperature=0.4)

    # Parse JSON from response — strip markdown fences first
    try:
        cleaned = _clean_json(raw)
        start = cleaned.find("[")
        end = cleaned.rfind("]") + 1
        if start == -1 or end == 0:
            # Try object wrapper fallback
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON array or object found in LLM response")
            wrapper = json.loads(cleaned[start:end])
            # Some models return {"slides": [...]}
            slides_data = wrapper.get("slides", list(wrapper.values())[0] if wrapper else [])
        else:
            slides_data = json.loads(cleaned[start:end])
        if not isinstance(slides_data, list) or len(slides_data) == 0:
            raise ValueError("Expected a non-empty JSON array of slides")
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse slide JSON: %s\nRaw: %s", e, raw[:500])
        raise HTTPException(status_code=500, detail="Failed to generate slide structure. Please try again.")

    # Build PPTX
    job_id = str(uuid.uuid4())
    output_path = _OUTPUTS_DIR / f"{job_id}.pptx"
    build_pptx(slides_data, str(output_path), title=body.topic)

    logger.info("Generated PPT: %s (%d slides)", output_path.name, len(slides_data))

    return FileResponse(
        path=str(output_path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=f"AGRA_{body.topic[:30].replace(' ', '_')}.pptx",
    )


# ═══════════════════════════════════════════════════════════════
#  EXECUTIVE SUMMARY
# ═══════════════════════════════════════════════════════════════

class SummaryRequest(BaseModel):
    doc_id: str
    summary_type: str = Field(default="executive", pattern="^(executive|technical)$")


@router.post("/generate/summary")
async def generate_summary(
    body: SummaryRequest,
    user: dict = Depends(get_current_user),
):
    """
    Generate an executive or technical summary of a document.
    Returns SSE stream of the summary + a .docx download link.
    """
    store = get_store()
    chunks = store.get_chunks_by_doc(body.doc_id)

    if not chunks:
        raise HTTPException(status_code=404, detail=f"Document {body.doc_id} not found in knowledge base.")

    # Combine all chunk text (truncate if too long for context)
    full_text = "\n\n".join(c["text"] for c in chunks)
    if len(full_text) > 25000:
        full_text = full_text[:25000] + "\n[Document truncated for summary generation]"

    filename = chunks[0]["metadata"].get("filename", "document")

    type_label = "Executive Summary" if body.summary_type == "executive" else "Technical Summary"
    prompt = f"""Generate a comprehensive {type_label} of the following document.

DOCUMENT: {filename}

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

    def event_stream():
        for tok in llm_engine.stream_generate(messages, max_tokens=3000):
            collected_text.append(tok)
            yield f"data: {json.dumps({'token': tok})}\n\n"

        # Build DOCX
        docx_path = _OUTPUTS_DIR / f"{job_id}_summary.docx"
        doc = DocxDocument()
        doc.add_heading(f"{type_label}: {filename}", level=1)
        doc.add_paragraph("".join(collected_text))
        doc.save(str(docx_path))

        yield f"data: {json.dumps({'done': True, 'download_url': f'/api/agent/download/{job_id}_summary.docx'})}\n\n"

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


@router.post("/generate/quiz")
async def generate_quiz(
    body: QuizRequest,
    user: dict = Depends(get_current_user),
):
    """
    Generate a knowledge quiz from a document.
    Returns JSON quiz data + a .docx download link.
    """
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

    raw = llm_engine.generate(messages, max_tokens=4096, temperature=0.5)

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

    doc.save(str(docx_path))

    return {
        "quiz": quiz_data,
        "download_url": f"/api/agent/download/{job_id}_quiz.docx",
    }
