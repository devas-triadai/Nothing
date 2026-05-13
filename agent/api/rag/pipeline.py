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
from api.rag.cache import semantic_cache

logger = logging.getLogger("agra.pipeline")

_ADMIN_BASE = os.getenv("AGRA_BACKEND_URL", "http://localhost:8000")
_REFUSAL = (
    "I could not find relevant information in the knowledge base to answer "
    "your question. Please try rephrasing or ensure the relevant documents "
    "have been uploaded."
)

# ── Intent patterns ──
_INTENT_PPT = re.compile(
    r'\b(creat|generat|build|make|prepar|add|updat|revis|chang|modify)e?\b.{0,50}\b(ppt|powerpoint|presentation|slides?)\b'
    r'|\b(ppt|powerpoint|presentation|slides?)\b.{0,50}\b(about|on|for|regard|with|of)\b',
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
_INTENT_SOTR = re.compile(
    r'\b(draft|generat|creat|build|make|prepar)e?.{0,40}(sotr|statement of technical requirements|technical requirements)\b',
    re.IGNORECASE,
)
_INTENT_TECH_REVIEW = re.compile(
    r'\b(draft|generat|creat|build|make|prepar)e?.{0,40}(tech review|technical review|review comments?)\b',
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
    if _INTENT_SOTR.search(q):
        return {"type": "draft_sotr"}
    if _INTENT_TECH_REVIEW.search(q):
        return {"type": "tech_review", "target_audience": "shipyard"}
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
_SYSTEM_PROMPT_FALLBACK = """You are AGRA, the AI assistant for Indian Coast Guard Headquarters, New Delhi.
You answer questions ONLY based on the provided context documents.

RULES:
1. Answer using ONLY the information in the provided context chunks below.
2. Cite sources inline using numbered superscript notation, e.g. [1], [2], immediately after the relevant sentence.
3. Each context chunk below is numbered — use that number as the citation reference.
4. If the context does not contain enough information, state exactly 'Not found in standard'. NEVER fabricate or hallucinate information.
5. Be concise, professional, and precise.
6. Use structured formatting (headings, bullet points) when appropriate.
"""


def _format_context(chunks: List[Dict[str, Any]]) -> str:
    """Format retrieved chunks into NUMBERED context blocks for the prompt.
    The number [N] is what the LLM should use for inline citations.
    """
    lines = []
    for i, c in enumerate(chunks, 1):
        meta = c.get("metadata", {})
        fname = meta.get("filename", "Unknown")
        page = meta.get("page", "?")
        clause = meta.get("section_title", "Unknown Clause")
        lines.append(f"[{i}] {fname} — Page {page} (Clause: {clause})")
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
            "clause": meta.get("section_title", "Unknown"), # Added for FR-QRY-002
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
                    return rules
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
    category: Optional[str] = None,
    description: Optional[str] = None,
    parent_doc_id: Optional[str] = None,
    version_notes: Optional[str] = None,
    source: Optional[str] = None,
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
    chunks = chunker.chunk_pages(pages, doc_id, filename, category=category, description=description, source=source or "admin_upload")
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
    doc_ids_filter: Optional[List[str]] = None,
    date_range: Optional[tuple] = None,
    doc_type: Optional[str] = None,
    version: Optional[int] = None,
    category: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Full RAG query: embed → hybrid search → rerank → build prompt → stream LLM.
    Yields SSE events: {"token": str} for each token, then {"done": true, "sources": [...]}.
    """
    start_time = time.time()
    store = get_store()
    _loop = asyncio.get_event_loop()

    # Force FastAPI to flush HTTP headers immediately to prevent proxy timeouts
    yield {"token": ""}
    await asyncio.sleep(0)

    # ── 0. Intent detection — check for PPT/quiz/summary requests ──
    intent = _detect_intent(question)
    if intent:
        # Get available doc_ids (use filter if set, else all)
        if doc_ids_filter:
            doc_ids = doc_ids_filter
        else:
            doc_ids = await _loop.run_in_executor(None, _get_all_doc_ids)

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

    # ── 1. Fast Path Check ──
    # Simple lookups bypass LLM pre-processing for <300ms speed
    fast_keywords = ["what is", "where is", "define", "definition", "who is"]
    is_fast = len(question) < 45 and any(k in question.lower() for k in fast_keywords)

    rewritten = question
    hyde_doc = None

    if not is_fast:
        from api.rag.query_rewriter import rewrite_query
        # Offload blocking sync LLM call to executor — keeps event loop alive
        rewritten = await _loop.run_in_executor(
            None, rewrite_query, question, session_history, None
        )
        hyde_doc = await llm_engine.generate_hyde_document(rewritten)
        logger.info("HyDE generated for query: %s", hyde_doc[:100].replace('\n', ' '))
    else:
        logger.info("Fast Path triggered: Skipping LLM expansion for speed.")

    # ── 2. Multi-Query Retrieval ──
    # Search using Original + Rewritten + HyDE to maximize recall
    search_queries = list(dict.fromkeys([q for q in [question, rewritten] if q]))
    if hyde_doc:
        search_queries.append(hyde_doc)

    logger.info("Stage: embedding query …")
    query_emb = await _loop.run_in_executor(
        None, embedder.embed_query, hyde_doc if hyde_doc else rewritten
    )
    logger.info("Stage: hybrid search over %d query variants …", len(search_queries))

    candidates = []
    for i, q in enumerate(search_queries):
        logger.info("  → hybrid_search variant %d/%d (qlen=%d) …", i + 1, len(search_queries), len(q))
        res = await _loop.run_in_executor(
            None,
            store.hybrid_search,
            q,
            query_emb,
            20,
            doc_ids_filter,
            date_range,
            doc_type,
            version,
            category,
        )
        logger.info("  → hybrid_search returned %d hits", len(res))
        candidates.extend(res)
    logger.info("Stage: total %d candidates collected. Deduplicating …", len(candidates))

    # Deduplicate candidates by point ID (vector_store uses 'pid' key)
    seen_ids = set()
    unique_candidates = []
    for c in candidates:
        cid = c.get("pid") or c.get("id")
        if cid is None or cid not in seen_ids:
            unique_candidates.append(c)
            if cid is not None:
                seen_ids.add(cid)
    candidates = unique_candidates
    logger.info("Stage: dedup → %d unique candidates. Checking semantic cache …", len(candidates))

    # ── Semantic Cache Check ──
    cache_hit = await _loop.run_in_executor(
        None, semantic_cache.check_cache, rewritten, query_emb
    )
    logger.info("Stage: semantic cache check complete (hit=%s)", bool(cache_hit))
    if cache_hit:
        logger.info("Serving response from semantic cache.")
        words = cache_hit["response"].split(" ")
        for i, word in enumerate(words):
            yield {"token": word + (" " if i < len(words) - 1 else "")}
            await asyncio.sleep(0.01)
        yield {
            "done": True,
            "sources": cache_hit["sources"],
            "response_time_ms": round((time.time() - start_time) * 1000, 1),
            "chunks_used": 0,
            "confidence_score": 1.0,
            "cached": True
        }
        return

    # ── 3. CRAG-Style Retry Loop ──
    # Thresholds calibrated for RRF scores. RRF max ≈ 2/(60+1) = 0.0328.
    _CONFIDENT_THRESHOLD = 0.015
    _RETRY_THRESHOLD = 0.005

    max_score = max((c.get("combined_score", 0) for c in candidates), default=0)
    logger.info("Stage: max_score=%.4f (confident≥%.3f, retry≥%.3f)",
                max_score, _CONFIDENT_THRESHOLD, _RETRY_THRESHOLD)

    if not candidates or max_score < _RETRY_THRESHOLD:
        yield {"token": _REFUSAL}
        yield {"done": True, "sources": []}
        return

    if max_score < _CONFIDENT_THRESHOLD:
        logger.info(
            "CRAG retry triggered: max_score=%.3f < %.3f (confident). Rewriting...",
            max_score, _CONFIDENT_THRESHOLD,
        )
        from api.rag.query_rewriter import rewrite_query
        # Offload blocking LLM call to executor to keep event loop responsive
        retry_query = await _loop.run_in_executor(
            None, rewrite_query, question, session_history, "low_relevance"
        )
        retry_emb = await _loop.run_in_executor(
            None, embedder.embed_query, retry_query
        )
        retry_candidates = await _loop.run_in_executor(
            None,
            store.hybrid_search,
            retry_query,
            retry_emb,
            50,
            doc_ids_filter,
        )
        retry_max = max((c.get("combined_score", 0) for c in retry_candidates), default=0)
        if retry_max > max_score:
            logger.info("CRAG retry improved: %.3f → %.3f", max_score, retry_max)
            candidates = retry_candidates
            max_score = retry_max
        else:
            logger.info("CRAG retry did not improve (%.3f ≤ %.3f), using original.", retry_max, max_score)

        if max_score < _RETRY_THRESHOLD:
            yield {"token": _REFUSAL}
            yield {"done": True, "sources": []}
            return

    # 4. Rerank → top 8
    logger.info("Stage: reranking %d candidates …", len(candidates))
    top_chunks = await _loop.run_in_executor(
        None, reranker.rerank, question, candidates, 8
    )
    logger.info("Stage: reranked to %d chunks. Fetching house rules …", len(top_chunks))

    # 5. Build prompt
    house_rules = await _fetch_house_rules(token)
    logger.info("Stage: house rules fetched. Building prompt …")
    base_prompt = house_rules if house_rules.strip() else _SYSTEM_PROMPT_FALLBACK
    context_str = _format_context(top_chunks)

    # Check for superseded documents via Admin Backend
    doc_ids_to_check = list({
        c["metadata"].get("doc_id")
        for c in top_chunks
        if "metadata" in c and c["metadata"].get("doc_id")
    })
    superseded_warning = ""
    if token and doc_ids_to_check:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(
                    f"{_ADMIN_BASE}/api/documents/check-superseded",
                    params=[("doc_ids", d) for d in doc_ids_to_check],
                    headers={"Authorization": f"Bearer {token}"}
                )
                if res.status_code == 200:
                    sup_data = res.json().get("superseded", {})
                    if sup_data:
                        warnings = []
                        for q_id, info in sup_data.items():
                            warnings.append(f"- A document provided in the context has been SUPERSEDED by: {info.get('superseded_by_name')}")
                        if warnings:
                            superseded_warning = "\n\nWARNING - OUTDATED INFORMATION DETECTED:\n" + "\n".join(warnings) + "\nYou MUST explicitly warn the user that they are asking about deprecated/superseded documents and mention the new document name."
        except Exception as e:
            logger.warning("Failed to check superseded docs: %s", e)

    system_msg = f"{base_prompt.strip()}\n{superseded_warning}\n---\nCONTEXT DOCUMENTS:\n{context_str}\n---"

    messages: List[Dict[str, str]] = [{"role": "system", "content": system_msg}]

    # Add conversation history (last 10 messages)
    for msg in session_history[-10:]:
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

    messages.append({"role": "user", "content": question})

    # 6. Stream LLM response (run in thread to avoid blocking async event loop)
    full_response = []
    token_queue: asyncio.Queue = asyncio.Queue()

    def _run_llm():
        try:
            logger.info("Stage: LLM stream starting (max_tokens=2048) …")
            first = True
            for tok in llm_engine.stream_generate(messages, max_tokens=2048):
                if first:
                    logger.info("Stage: LLM first token received.")
                    first = False
                # asyncio.Queue is NOT thread-safe — must bridge via call_soon_threadsafe
                _loop.call_soon_threadsafe(token_queue.put_nowait, tok)
            logger.info("Stage: LLM stream finished.")
            _loop.call_soon_threadsafe(token_queue.put_nowait, None)  # sentinel
        except Exception as e:
            logger.error("LLM generation error: %s", e, exc_info=True)
            _loop.call_soon_threadsafe(token_queue.put_nowait, None)

    llm_thread = _loop.run_in_executor(None, _run_llm)

    while True:
        tok = await token_queue.get()
        if tok is None:
            break
        full_response.append(tok)
        yield {"token": tok}

    await llm_thread  # ensure thread is done

    # 7. Build structured sources
    sources = _format_sources(top_chunks)

    # ── Citation Validation ──
    full_text = "".join(full_response)
    valid_source_indices = {str(s["index"]) for s in sources}
    hallucinated_citations = set(re.findall(r'\[(\d+)\]', full_text)) - valid_source_indices

    if hallucinated_citations:
        logger.warning("Stripping hallucinated citations: %s", hallucinated_citations)
        for bad_id in hallucinated_citations:
            full_text = full_text.replace(f"[{bad_id}]", "")
        yield {"replace_all": full_text}

    # Add to Semantic Cache
    if len(full_text) > 10 and max_score >= _CONFIDENT_THRESHOLD:
        await _loop.run_in_executor(
            None, semantic_cache.add_to_cache, rewritten, query_emb, full_text, sources
        )

    elapsed_ms = round((time.time() - start_time) * 1000, 1)

    # 8. Log usage to admin backend
    if token:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{_ADMIN_BASE}/api/usage/log",
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
                        "metadata_": question,
                    },
                )
        except Exception as e:
            logger.warning("Failed to log usage: %s", e)

    # Normalize RRF to a human-friendly 0-1 confidence scale.
    # Theoretical RRF max with k=60: 2/(60+1) ≈ 0.0328.
    _rrf_max = 2.0 / (60.0 + 1.0)
    confidence = min(max_score / _rrf_max, 1.0) if _rrf_max else 0.0

    yield {
        "done": True,
        "sources": sources,
        "response_time_ms": elapsed_ms,
        "chunks_used": len(top_chunks),
        "confidence_score": round(confidence, 3),
    }
