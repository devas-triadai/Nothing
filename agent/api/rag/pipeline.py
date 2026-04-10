"""
AGRA Phase 2 — RAG: Orchestration Pipeline
Ties together OCR → chunking → embedding → vector store → rerank → LLM.
Exposes two main flows: document ingestion and question answering.
"""

import json
import logging
import time
from typing import Any, Dict, Generator, List, Optional

import httpx

from api.rag import embedder, chunker, reranker, ocr
from api.rag.vector_store import get_store
from api.rag import llm as llm_engine

logger = logging.getLogger("agra.pipeline")

_ADMIN_BASE = "http://localhost:8000"
_SIMILARITY_THRESHOLD = 0.35
_REFUSAL = (
    "I could not find relevant information in the knowledge base to answer "
    "your question. Please try rephrasing or ensure the relevant documents "
    "have been uploaded."
)

# ── System prompt template ──
_SYSTEM_PROMPT = """You are AGRA, the AI assistant for Indian Coast Guard Headquarters, New Delhi.
You answer questions ONLY based on the provided context documents.

RULES:
1. Answer using ONLY the information in the provided context chunks below.
2. Always cite your sources using [Source: filename, Page X] format at the point where you use the information.
3. If the context does not contain enough information, say so clearly — NEVER fabricate or hallucinate information.
4. Be concise, professional, and precise.
5. Use structured formatting (headings, bullet points) when appropriate.
{house_rules}
---
CONTEXT DOCUMENTS:
{context}
---"""


def _format_context(chunks: List[Dict[str, Any]]) -> str:
    """Format retrieved chunks into a numbered context block for the prompt."""
    lines = []
    for i, c in enumerate(chunks, 1):
        meta = c.get("metadata", {})
        fname = meta.get("filename", "Unknown")
        page = meta.get("page", "?")
        lines.append(f"[{i}] Source: {fname}, Page {page}")
        lines.append(c["text"])
        lines.append("")
    return "\n".join(lines)


def _format_sources(chunks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Build the sources list for the response footer."""
    seen = set()
    sources = []
    for c in chunks:
        meta = c.get("metadata", {})
        key = f"{meta.get('filename', '')}|{meta.get('page', '')}"
        if key not in seen:
            seen.add(key)
            sources.append({
                "document": meta.get("filename", "Unknown"),
                "page": meta.get("page", "?"),
                "excerpt": c["text"][:200] + ("…" if len(c["text"]) > 200 else ""),
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
) -> Generator[Dict[str, Any], None, None]:
    """
    Full RAG query: embed → hybrid search → rerank → build prompt → stream LLM.
    Yields SSE events: {"token": str} for each token, then {"done": true, "sources": [...]}.
    """
    start_time = time.time()
    store = get_store()

    # 1. Embed the question
    query_emb = embedder.embed_query(question)

    # 2. Hybrid search (dense + BM25) → top 10
    candidates = store.hybrid_search(
        query_text=question,
        query_embedding=query_emb,
        top_k=10,
        doc_id_filter=doc_id_filter,
    )

    if not candidates:
        yield {"token": _REFUSAL}
        yield {"done": True, "sources": []}
        return

    # 3. Check similarity threshold
    max_score = max(c.get("combined_score", 0) for c in candidates)
    if max_score < _SIMILARITY_THRESHOLD:
        yield {"token": _REFUSAL}
        yield {"done": True, "sources": []}
        return

    # 4. Rerank → top 5
    top_chunks = reranker.rerank(question, candidates, top_k=5)

    # 5. Build prompt
    house_rules = await _fetch_house_rules(token)
    context_str = _format_context(top_chunks)
    system_msg = _SYSTEM_PROMPT.format(house_rules=house_rules, context=context_str)

    messages: List[Dict[str, str]] = [{"role": "system", "content": system_msg}]

    # Add conversation history (last 10 messages)
    for msg in session_history[-10:]:
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

    messages.append({"role": "user", "content": question})

    # 6. Stream LLM response
    full_response = []
    for tok in llm_engine.stream_generate(messages, max_tokens=2048):
        full_response.append(tok)
        yield {"token": tok}

    # 7. Append sources footer
    sources = _format_sources(top_chunks)
    source_text = "\n\n**Sources:**\n"
    for s in sources:
        source_text += f"- {s['document']}, Page {s['page']}\n"

    yield {"token": source_text}
    full_response.append(source_text)

    elapsed_ms = round((time.time() - start_time) * 1000, 1)

    # 8. Log usage to admin backend
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
