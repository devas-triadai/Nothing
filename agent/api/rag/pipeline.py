"""
AGRA Phase 2 — RAG: Orchestration Pipeline
Ties together OCR → chunking → embedding → vector store → rerank → LLM.
Exposes two main flows: document ingestion and question answering.
"""

import json
import logging
import re
import time
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional

import asyncio
import os

import httpx

from api.rag import embedder, chunker, reranker, ocr
from api.rag.vector_store import get_store
from api.rag import llm as llm_engine

logger = logging.getLogger("agra.pipeline")

_ADMIN_BASE = os.getenv("AGRA_BACKEND_URL", "http://localhost:8000")
_REFUSAL = (
    "I could not find relevant information in the knowledge base to answer "
    "your question. Please try rephrasing or ensure the relevant documents "
    "have been uploaded."
)

# ── Intent patterns ──
_INTENT_PPT = re.compile(
    r'\b(creat|generat|build|make|prepar)e?\b.{0,40}\b(ppt|powerpoint|presentation|slides?)\b'
    r'|\b(ppt|powerpoint|presentation|slides?)\b.{0,40}\b(about|on|for|regard)\b',
    re.IGNORECASE,
)
_INTENT_QUIZ = re.compile(
    r'\b(creat|generat|build|make)e?\b.{0,40}\b(quiz|assessment|test|questions?)\b'
    r'|\b(quiz|test me|assess)\b',
    re.IGNORECASE,
)
_INTENT_SUMMARY = re.compile(
    r'\b(summar|summarise|summarize|give me a summary|executive summary|brief|overview)\b',
    re.IGNORECASE,
)


def _detect_intent(question: str) -> Optional[Dict[str, Any]]:
    """
    Detect if the user wants to generate content (PPT/quiz/summary).
    Returns a dict with type and extracted params, or None for normal Q&A.
    """
    q = question.strip()
    if _INTENT_PPT.search(q):
        # Extract topic: everything after 'about/on/for/regarding'
        topic_match = re.search(
            r'(?:about|on|for|regarding|titled?)\s+["\']?(.+?)["\']?\s*$',
            q, re.IGNORECASE
        )
        topic = topic_match.group(1).strip() if topic_match else q
        # Clean up topic — remove trigger words
        topic = re.sub(
            r'^(creat|generat|build|make|prepar)e?\s+(a\s+)?(ppt|powerpoint|presentation|slides?)\s*',
            '', topic, flags=re.IGNORECASE
        ).strip() or q
        
        # Extract number of slides if mentioned (e.g., "5 slides")
        num_slides = 10
        slides_match = re.search(r'(\d+)\s*slides?', q, re.IGNORECASE)
        if slides_match:
            try:
                num_slides = int(slides_match.group(1))
            except ValueError:
                pass
                
        # Remove "of 5 slides" or "for 5 slides" from the topic so it doesn't end up in the PPT title
        topic = re.sub(r'\b(?:of|for|with)?\s*\d+\s*slides?\b', '', topic, flags=re.IGNORECASE).strip()
        # Clean up any trailing prepositions or spaces
        topic = re.sub(r'\s+(?:of|for|with|regarding|on|about)\s*$', '', topic, flags=re.IGNORECASE).strip()
        
        return {"type": "ppt", "topic": topic, "num_slides": max(3, min(num_slides, 25))}
    if _INTENT_QUIZ.search(q):
        return {"type": "quiz", "num_mcq": 5, "num_short_answer": 3}
    if _INTENT_SUMMARY.search(q):
        return {"type": "summary", "summary_type": "executive"}
    return None


def _get_all_doc_ids() -> List[str]:
    """Get all unique doc_ids currently indexed in the vector store."""
    store = get_store()
    seen = set()
    offset = None
    while True:
        results, offset = store.client.scroll(
            collection_name="agra_docs",
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for pt in results:
            did = pt.payload.get("metadata", {}).get("doc_id", "")
            if did:
                seen.add(did)
        if offset is None:
            break
    return list(seen)

# ── System prompt template ──
_SYSTEM_PROMPT = """You are AGRA, the AI assistant for Indian Coast Guard Headquarters, New Delhi.
You answer questions ONLY based on the provided context documents.

RULES:
1. Answer using ONLY the information in the provided context chunks below.
2. Cite sources inline using numbered superscript notation, e.g. [1], [2], immediately after the relevant sentence.
3. Each context chunk below is numbered — use that number as the citation reference.
4. If the context does not contain enough information, say so clearly — NEVER fabricate or hallucinate information.
5. Be concise, professional, and precise.
6. Use structured formatting (headings, bullet points) when appropriate.
{house_rules}
---
CONTEXT DOCUMENTS:
{context}
---"""


def _format_context(chunks: List[Dict[str, Any]]) -> str:
    """Format retrieved chunks into NUMBERED context blocks for the prompt.
    The number [N] is what the LLM should use for inline citations.
    """
    lines = []
    for i, c in enumerate(chunks, 1):
        meta = c.get("metadata", {})
        fname = meta.get("filename", "Unknown")
        page = meta.get("page", "?")
        lines.append(f"[{i}] {fname} — Page {page}")
        lines.append(c["text"])
        lines.append("")
    return "\n".join(lines)


def _format_sources(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build the numbered sources list for the response, including doc_id for linking."""
    sources = []
    for i, c in enumerate(chunks, 1):
        meta = c.get("metadata", {})
        sources.append({
            "index": i,                                      # Matches [N] in text
            "document": meta.get("filename", "Unknown"),
            "page": meta.get("page", "?"),
            "doc_id": meta.get("doc_id", ""),               # For download link
            "excerpt": c["text"][:250] + ("…" if len(c["text"]) > 250 else ""),
        })
    return sources


async def _fetch_house_rules(token: str) -> str:
    """Fetch ICG House Rules from admin backend (best effort)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{_ADMIN_BASE}/api/agents/house-rules",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                rules = data.get("house_rules", "")
                if rules:
                    return f"\nADDITIONAL GOVERNANCE RULES:\n{rules}\n"
    except Exception as e:
        logger.warning("Could not fetch house rules: %s", e)
    return ""


# ═══════════════════════════════════════════════════════════════
#  DOCUMENT INGESTION
# ═══════════════════════════════════════════════════════════════

def ingest_document(
    file_path: str,
    filename: str,
    doc_id: str,
    uploaded_by_user_id: int,
    token: str = "",
) -> Generator[Dict[str, Any], None, None]:
    """
    Full ingestion pipeline: OCR → chunk → embed → store.
    Yields SSE-style progress events.
    """
    store = get_store()

    # ── Stage 1: Text extraction / OCR ──
    yield {"stage": "ocr", "progress": 0, "message": "Extracting text…"}
    pages = ocr.extract_document(file_path)
    if not pages:
        yield {"stage": "ocr", "progress": 100, "message": "No text extracted.", "error": True}
        return
    yield {"stage": "ocr", "progress": 100, "message": f"Extracted {len(pages)} pages."}

    # ── Stage 2: Chunking ──
    yield {"stage": "chunking", "progress": 0, "message": "Chunking text…"}
    chunks = chunker.chunk_pages(pages, doc_id, filename)
    if not chunks:
        yield {"stage": "chunking", "progress": 100, "message": "No chunks produced.", "error": True}
        return
    yield {"stage": "chunking", "progress": 100, "message": f"Created {len(chunks)} chunks."}

    # ── Stage 3: Embedding ──
    yield {"stage": "embedding", "progress": 0, "message": "Generating embeddings…"}
    texts = [c["text"] for c in chunks]
    total = len(texts)
    all_embeddings: List[List[float]] = []

    batch_size = 32
    for i in range(0, total, batch_size):
        batch = texts[i:i + batch_size]
        embs = embedder.embed_texts(batch)
        all_embeddings.extend(embs)
        pct = min(int((i + len(batch)) / total * 100), 100)
        yield {"stage": "embedding", "progress": pct, "message": f"Embedded {i + len(batch)}/{total} chunks."}

    yield {"stage": "embedding", "progress": 100, "message": "All embeddings generated."}

    # ── Stage 4: Store in Qdrant ──
    yield {"stage": "storing", "progress": 0, "message": "Storing in vector database…"}
    count = store.upsert_chunks(chunks, all_embeddings)
    yield {"stage": "storing", "progress": 100, "message": f"Stored {count} chunks in Qdrant."}

    # ── Notify admin backend (best effort) ──
    if token:
        try:
            httpx.post(
                f"{_ADMIN_BASE}/api/documents/",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "filename": filename,
                    "original_filename": filename,
                    "file_type": filename.rsplit(".", 1)[-1] if "." in filename else "unknown",
                    "page_count": len(pages),
                    "status": "indexed",
                    "description": f"Ingested by AGRA Agent (doc_id: {doc_id})",
                },
                timeout=5.0,
            )
        except Exception as e:
            logger.warning("Failed to register document with admin backend: %s", e)

    yield {
        "stage": "done",
        "progress": 100,
        "message": "Ingestion complete.",
        "doc_id": doc_id,
        "chunks": count,
        "pages": len(pages),
    }


# ═══════════════════════════════════════════════════════════════
#  QUESTION-ANSWERING PIPELINE
# ═══════════════════════════════════════════════════════════════

async def query_pipeline(
    question: str,
    session_history: List[Dict[str, str]],
    user_id: int,
    token: str = "",
    doc_id_filter: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Full RAG query: embed → hybrid search → rerank → build prompt → stream LLM.
    Yields SSE events: {"token": str} for each token, then {"done": true, "sources": [...]}.
    """
    start_time = time.time()
    store = get_store()

    # Force FastAPI to flush HTTP headers immediately to prevent proxy timeouts
    yield {"token": ""}
    await asyncio.sleep(0)

    # ── 0. Intent detection — check for PPT/quiz/summary requests ──
    intent = _detect_intent(question)
    if intent:
        # Get available doc_ids (use filter if set, else all)
        if doc_id_filter:
            doc_ids = [doc_id_filter]
        else:
            doc_ids = _get_all_doc_ids()

        if not doc_ids:
            yield {"token": "No documents are indexed yet. Please upload documents first."}
            yield {"done": True, "sources": [], "intent": intent["type"]}
            return

        # Signal intent to the frontend with doc context
        yield {
            "intent": intent["type"],
            "intent_params": {
                **intent,
                "doc_ids": doc_ids,
                "doc_id": doc_ids[0],  # Primary doc for summary/quiz
            },
            "done": True,
            "sources": [],
        }
        return

    # ── 1. Query Rewriting (Priority 1) ──
    from api.rag.query_rewriter import rewrite_query
    rewritten = rewrite_query(question, session_history)

    # 2. Embed the REWRITTEN query (original kept for LLM prompt)
    query_emb = embedder.embed_query(rewritten)

    # 3. Hybrid search (dense + BM25) → top 10
    candidates = store.hybrid_search(
        query_text=rewritten,
        query_embedding=query_emb,
        top_k=10,
        doc_id_filter=doc_id_filter,
    )

    # ── 4. CRAG-Style Retry Loop (Priority 3) ──
    # Three-tier threshold: CONFIDENT → proceed; RETRY → rewrite & search again; REFUSE
    _CONFIDENT_THRESHOLD = 0.50
    _RETRY_THRESHOLD = 0.25

    max_score = max((c.get("combined_score", 0) for c in candidates), default=0)

    if not candidates or max_score < _RETRY_THRESHOLD:
        # Below retry threshold — refuse immediately
        yield {"token": _REFUSAL}
        yield {"done": True, "sources": []}
        return

    if max_score < _CONFIDENT_THRESHOLD:
        # Borderline — CRAG retry with broader rewritten query
        logger.info(
            "CRAG retry triggered: max_score=%.3f < %.3f (confident). Rewriting...",
            max_score, _CONFIDENT_THRESHOLD,
        )
        retry_query = rewrite_query(question, session_history, feedback="low_relevance")
        retry_emb = embedder.embed_query(retry_query)
        retry_candidates = store.hybrid_search(
            query_text=retry_query,
            query_embedding=retry_emb,
            top_k=10,
            doc_id_filter=doc_id_filter,
        )
        retry_max = max((c.get("combined_score", 0) for c in retry_candidates), default=0)
        if retry_max > max_score:
            logger.info("CRAG retry improved: %.3f → %.3f", max_score, retry_max)
            candidates = retry_candidates
            max_score = retry_max
        else:
            logger.info("CRAG retry did not improve (%.3f ≤ %.3f), using original.", retry_max, max_score)

        # After retry, still below refuse threshold? Give up.
        if max_score < _RETRY_THRESHOLD:
            yield {"token": _REFUSAL}
            yield {"done": True, "sources": []}
            return

    # 5. Rerank → top 5
    top_chunks = reranker.rerank(question, candidates, top_k=5)

    # 6. Build prompt
    house_rules = await _fetch_house_rules(token)
    context_str = _format_context(top_chunks)
    system_msg = _SYSTEM_PROMPT.format(house_rules=house_rules, context=context_str)

    messages: List[Dict[str, str]] = [{"role": "system", "content": system_msg}]

    # Add conversation history (last 10 messages)
    for msg in session_history[-10:]:
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

    messages.append({"role": "user", "content": question})

    # 7. Stream LLM response
    full_response = []
    for tok in llm_engine.stream_generate(messages, max_tokens=2048):
        full_response.append(tok)
        yield {"token": tok}

    # 8. Build structured sources (no inline text footer — UI handles display)
    sources = _format_sources(top_chunks)

    elapsed_ms = round((time.time() - start_time) * 1000, 1)

    # 9. Log usage to admin backend
    if token:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{_ADMIN_BASE}/api/usage/",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "user_id": user_id,
                        "action_type": "query",
                        "module": "agent_chat",
                        "response_time_ms": elapsed_ms,
                        "status": "success",
                    },
                )
        except Exception as e:
            logger.warning("Failed to log usage: %s", e)

    yield {
        "done": True,
        "sources": sources,
        "response_time_ms": elapsed_ms,
        "chunks_used": len(top_chunks),
    }
