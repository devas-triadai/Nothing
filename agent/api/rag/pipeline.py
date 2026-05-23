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
from api.rag.evaluation_store import get_store as get_eval_store
from api.rag.citation_validator import validate_citations_against_sources, format_validation_report
from api.rag.hallucination_detector import detect_hallucinations, format_hallucination_report
from api.rag.delta_indexer import delta_index_document

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
    r'\b(creat|generat|build|make)e?\b.{0,40}\b(quiz|assessment|test|questions?|q\s*&\s*a|q\s+and\s+a|question\s+and\s+answer)\b'
    r'|\b(quiz|test me|assess|q\s*&\s*a|q\s+and\s+a|question\s+and\s+answer)\b',
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
# Workstream K: Drawing analysis intent — auto-detect drawings/schematics even without "analyze"
_INTENT_DRAWING = re.compile(
    r'\b(analy[zs]e|extract|parse|read|interpret|inspect|check|look\s+at|view|verify|identify)\b.{0,60}\b(drawing|schematic|blueprint|diagram|plan|sketch|image|map|layout|photo|figure|chart|specification|schemes?)\b'
    r'|\b(drawing|schematic|blueprint|layout|schemes?)\b.{0,60}\b(analysis|extraction|parameters?|details?|specs?)\b'
    r'|\b(what\s+is\s+in\s+this|what\s+does\s+this|can\s+you\s+see\s+the|tell\s+me\s+about\s+this)\s+(drawing|schematic|image|blueprint)\b',
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
        # Clean up topic — remove PPT trigger verb phrases
        topic = re.sub(
            r'^(creat|generat|build|make|prepar)e?\s+(a\s+)?(ppt|powerpoint|presentation|slides?)\s*',
            '', topic, flags=re.IGNORECASE
        ).strip()
        # Strip common non-topic filler phrases (e.g. "with the file attached", "from the document")
        topic = re.sub(
            r'\b(with\s+the\s+file\s+attached|from\s+the\s+(attached\s+)?(file|document|docs?)|using\s+the\s+(attached\s+)?(file|document|docs?)|based\s+on\s+(the\s+)?(attached\s+)?(file|document|docs?))\b',
            '', topic, flags=re.IGNORECASE
        ).strip()
        # If topic is now empty or still looks like a raw command, use a clean default
        if not topic or re.match(
            r'^(creat|generat|build|make|a|ppt|powerpoint|presentation|slides?|the|this)[\s.,!]*$',
            topic, re.IGNORECASE
        ):
            topic = "Document Overview"

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
        topic = re.sub(r'\s+(?:of|for|with|regarding|on|about)\s*$', '', topic, flags=re.IGNORECASE).strip() or "Document Overview"

        return {"type": "ppt", "topic": topic, "num_slides": max(3, min(num_slides, 25))}
    if _INTENT_QUIZ.search(q):
        # Parse user-specified question counts
        mcq_match = re.search(r'(\d+)\s*(?:mcq|multiple\s*choice)', q, re.IGNORECASE)
        tf_match  = re.search(r'(\d+)\s*(?:true\s*(?:or|and|/|&)?\s*false|t\s*[/&]\s*f|true[-/]false)', q, re.IGNORECASE)
        sa_match  = re.search(r'(\d+)\s*(?:short\s*answer|descriptive|open[- ]ended)', q, re.IGNORECASE)

        # If user asked for only a specific type, zero out the others
        only_mcq = bool(re.search(r'\bonly\s*(?:mcq|multiple\s*choice)\b|\b(?:mcq|multiple\s*choice)\s*only\b', q, re.IGNORECASE))
        only_tf  = bool(re.search(r'\bonly\s*(?:true\s*(?:or|and|/|&)?\s*false|t\s*[/&]\s*f)\b|\b(?:true\s*(?:or|and|/|&)?\s*false)\s*only\b', q, re.IGNORECASE))
        only_sa  = bool(re.search(r'\bonly\s*(?:short\s*answer|descriptive)\b|\b(?:short\s*answer)\s*only\b', q, re.IGNORECASE))

        if only_mcq:
            num_mcq = int(mcq_match.group(1)) if mcq_match else 10
            return {"type": "quiz", "num_mcq": num_mcq, "num_true_false": 0, "num_short_answer": 0}
        if only_tf:
            num_tf = int(tf_match.group(1)) if tf_match else 10
            return {"type": "quiz", "num_mcq": 0, "num_true_false": num_tf, "num_short_answer": 0}
        if only_sa:
            num_sa = int(sa_match.group(1)) if sa_match else 5
            return {"type": "quiz", "num_mcq": 0, "num_true_false": 0, "num_short_answer": num_sa}

        # Mixed: respect individual counts if specified, else use defaults (5 MCQ + 3 T/F + 2 SA)
        num_mcq = int(mcq_match.group(1)) if mcq_match else 5
        num_tf  = int(tf_match.group(1))  if tf_match  else 3
        num_sa  = int(sa_match.group(1))  if sa_match  else 2
        return {"type": "quiz", "num_mcq": num_mcq, "num_true_false": num_tf, "num_short_answer": num_sa}
    if _INTENT_SUMMARY.search(q):
        return {"type": "summary", "summary_type": "executive"}
    if _INTENT_SOTR.search(q):
        return {"type": "draft_sotr"}
    if _INTENT_TECH_REVIEW.search(q):
        return {"type": "tech_review", "target_audience": "shipyard"}
    # Workstream F: Drawing analysis intent detection
    if _INTENT_DRAWING.search(q):
        return {"type": "drawing_extract"}
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


def _format_context(chunks: List[Dict[str, Any]], max_chars_per_chunk: int = 800) -> str:
    """Format retrieved chunks into NUMBERED context blocks for the prompt.
    The number [N] is what the LLM should use for inline citations.
    Truncates each chunk to avoid exceeding the LLM context window.
    """
    lines = []
    for i, c in enumerate(chunks, 1):
        meta = c.get("metadata", {})
        fname = meta.get("filename", "Unknown")
        page = meta.get("page", "?")
        clause = meta.get("section_title", "Unknown Clause")
        lines.append(f"[{i}] {fname} — Page {page} (Clause: {clause})")
        text = c.get("text", "")
        if len(text) > max_chars_per_chunk:
            text = text[:max_chars_per_chunk] + "\n[chunk truncated]"
        lines.append(text)
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
    document_type: Optional[str] = None,
    content_hash: Optional[str] = None,
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
    chunks = chunker.chunk_pages(
        pages, doc_id, filename,
        category=category, description=description,
        source=source or "admin_upload",
        document_type=document_type,
        content_hash=content_hash,
    )
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
    
    # Module 7: Use delta indexing for version updates (when parent_doc_id provided)
    if parent_doc_id:
        # This is a version update — use delta indexing
        import asyncio
        loop = asyncio.get_event_loop()
        
        # Attach embeddings to chunks for delta indexer
        for chunk, emb in zip(chunks, all_embeddings):
            chunk["embedding"] = emb
        
        # Run delta indexing
        delta_result = loop.run_until_complete(
            delta_index_document(doc_id, chunks, store)
        )
        
        if delta_result["success"]:
            ops = delta_result["operations"]
            method = delta_result["method"]
            unchanged = delta_result.get("unchanged", 0)
            
            if method == "delta":
                yield {
                    "stage": "storing", 
                    "progress": 100, 
                    "message": f"Delta indexed: {ops['added']} added, {ops['updated']} updated, {ops['deleted']} deleted, {unchanged} unchanged."
                }
                count = ops["added"] + ops["updated"] + unchanged
            else:
                yield {
                    "stage": "storing", 
                    "progress": 100, 
                    "message": f"Full indexed {ops['added']} chunks (delta too complex)."
                }
                count = ops["added"]
        else:
            # Fall back to standard upsert
            count = store.upsert_chunks(chunks, all_embeddings)
            yield {"stage": "storing", "progress": 100, "message": f"Stored {count} chunks in Qdrant (delta failed)."}
    else:
        # New document — standard full indexing
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
        # If explicit doc_ids provided, use them. Otherwise auto-search knowledge base.
        if doc_ids_filter:
            doc_ids = doc_ids_filter
        else:
            # Auto-search knowledge base for relevant documents based on intent topic
            intent_topic = intent.get("topic", question)
            logger.info("Intent detected without explicit docs. Auto-searching for: %s", intent_topic)
            
            # Embed the topic and search
            topic_emb = await _loop.run_in_executor(None, embedder.embed_query, intent_topic)
            search_results = await _loop.run_in_executor(
                None, store.hybrid_search, intent_topic, topic_emb, 40
            )
            
            # Extract unique doc_ids from search results (prefer non-builtin)
            seen_doc_ids = set()
            doc_ids = []
            for chunk in search_results:
                doc_id = chunk.get("metadata", {}).get("doc_id")
                if doc_id and doc_id not in seen_doc_ids:
                    seen_doc_ids.add(doc_id)
                    doc_ids.append(doc_id)
            
            # Limit to top 5 most relevant docs
            doc_ids = doc_ids[:5]
            
            if doc_ids:
                logger.info("Auto-selected %d documents for intent: %s", len(doc_ids), doc_ids)
            else:
                logger.warning("No documents found in knowledge base for topic: %s", intent_topic)

        if not doc_ids:
            yield {"token": "No documents are indexed yet. Please upload documents first."}
            yield {"done": True, "sources": [], "intent": intent["type"]}
            return

        # Prefer user-uploaded docs (non-builtin) as the primary doc_id for summary/quiz.
        # Builtin knowledge-base docs are standards/reference material, not presentation targets.
        non_builtin = [d for d in doc_ids if not d.startswith("builtin:")]
        primary_doc_id = non_builtin[0] if non_builtin else doc_ids[0]

        # Signal intent to the frontend with doc context
        yield {
            "intent": intent["type"],
            "intent_params": {
                **intent,
                "doc_ids": doc_ids,
                "doc_id": primary_doc_id,  # Primary doc for summary/quiz — prefer user-uploaded
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
    # Search using Original + Rewritten + HyDE in parallel to minimize latency
    search_queries = list(dict.fromkeys([q for q in [question, rewritten] if q]))
    if hyde_doc:
        search_queries.append(hyde_doc)

    logger.info("Stage: embedding query …")
    query_emb = await _loop.run_in_executor(
        None, embedder.embed_query, hyde_doc if hyde_doc else rewritten
    )
    
    # ── Semantic Cache Check (Immediate exit if hit) ──
    cache_hit = await _loop.run_in_executor(
        None, semantic_cache.check_cache, rewritten, query_emb
    )
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

    logger.info("Stage: parallel hybrid search over %d variants …", len(search_queries))
    
    search_tasks = [
        _loop.run_in_executor(
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
        for q in search_queries
    ]
    
    results = await asyncio.gather(*search_tasks)
    candidates = []
    for res in results:
        candidates.extend(res)
    
    logger.info("Stage: total %d candidates collected from parallel search.", len(candidates))

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
    logger.info("Stage: dedup → %d unique candidates.", len(candidates))

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

    # 4. Rerank → top 6
    logger.info("Stage: reranking %d candidates …", len(candidates))
    top_chunks = await _loop.run_in_executor(
        None, reranker.rerank, question, candidates, 6
    )
    logger.info("Stage: reranked to %d chunks. Fetching house rules …", len(top_chunks))

    # 5. Build prompt
    house_rules = await _fetch_house_rules(token)
    logger.info("Stage: house rules fetched. Building prompt …")
    base_prompt = house_rules if house_rules.strip() else _SYSTEM_PROMPT_FALLBACK
    # Cap house rules at ~800 chars to leave room for context + history
    if len(base_prompt) > 800:
        base_prompt = base_prompt[:800] + "\n[Rules truncated]"
    context_str = _format_context(top_chunks, max_chars_per_chunk=800)

    # Check for superseded documents via Admin Backend
    # Skip builtin docs — they are auto-ingested at startup and never exist in
    # the PostgreSQL backend DB, so the superseded check is meaningless for them.
    doc_ids_to_check = list({
        c["metadata"].get("doc_id")
        for c in top_chunks
        if "metadata" in c and c["metadata"].get("doc_id")
        and not c["metadata"].get("doc_id", "").startswith("builtin:")
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
                else:
                    logger.warning(
                        "check-superseded returned %s: %s",
                        res.status_code, res.text[:200]
                    )
        except Exception as e:
            logger.warning("Failed to check superseded docs: %s", e)

    system_msg = f"{base_prompt.strip()}\n{superseded_warning}\n---\nCONTEXT DOCUMENTS:\n{context_str}\n---"

    messages: List[Dict[str, str]] = [{"role": "system", "content": system_msg}]

    # ── Workstream I: Token-budget-aware conversation history ──
    # Approximate 1 token ≈ 4 chars.  Reserve space for system + question + generation.
    # llama-server runs with -c 16384; use 8192 as a safe working budget.
    _CTX_LIMIT = 8192
    _PROMPT_RESERVE = 2048
    _CHAR_LIMIT = _CTX_LIMIT * 4  # ~32768 chars for 8192 tokens
    _QUESTION_RESERVE = 600       # chars reserved for the user question
    _GENERATION_RESERVE = _PROMPT_RESERVE * 4  # chars reserved for output tokens

    used_chars = len(system_msg) + _QUESTION_RESERVE + _GENERATION_RESERVE
    history_budget = max(0, _CHAR_LIMIT - used_chars)
    logger.info("Workstream I: history budget=%d chars (system=%d, question=%d, gen=%d)",
                history_budget, len(system_msg), _QUESTION_RESERVE, _GENERATION_RESERVE)

    # Filter: only user/assistant, non-empty, strip garbage
    clean_history = [
        msg for msg in session_history
        if msg.get("role") in ("user", "assistant")
        and msg.get("content", "").strip()
        and len(msg.get("content", "").strip()) > 2
    ]

    # Fill from most recent backward, respecting budget
    history_to_add = []
    remaining = history_budget
    for msg in reversed(clean_history[-20:]):  # Consider last 20 messages = 10 full turns
        content = msg.get("content", "")
        # Truncate each message to 300 chars to prevent a single long response from consuming the entire budget
        if len(content) > 300:
            content = content[:300] + "…"
        msg_chars = len(content) + 20  # +20 for role/formatting overhead
        if msg_chars > remaining:
            continue
        history_to_add.insert(0, {"role": msg.get("role", "user"), "content": content})
        remaining -= msg_chars

    logger.info("Workstream I: adding %d/%d history messages (%d chars used)",
                len(history_to_add), len(clean_history), history_budget - remaining)

    for msg in history_to_add:
        messages.append(msg)

    messages.append({"role": "user", "content": question})

    # 6. Stream LLM response (run in thread to avoid blocking async event loop)
    # _CTX_LIMIT and _PROMPT_RESERVE defined above in Workstream I history block
    llm_max_tokens = max(256, _CTX_LIMIT - _PROMPT_RESERVE)
    full_response = []
    token_queue: asyncio.Queue = asyncio.Queue()

    def _run_llm():
        try:
            logger.info("Stage: LLM stream starting (max_tokens=%d) …", llm_max_tokens)
            first = True
            for tok in llm_engine.stream_generate(messages, max_tokens=llm_max_tokens):
                if first:
                    logger.info("Stage: LLM first token received.")
                    first = False
                # asyncio.Queue is NOT thread-safe — must bridge via call_soon_threadsafe
                _loop.call_soon_threadsafe(token_queue.put_nowait, tok)
            logger.info("Stage: LLM stream finished.")
            _loop.call_soon_threadsafe(token_queue.put_nowait, None)  # sentinel
        except Exception as e:
            logger.error("LLM generation error: %s", e, exc_info=True)
            _loop.call_soon_threadsafe(token_queue.put_nowait, {"error": str(e)})
            _loop.call_soon_threadsafe(token_queue.put_nowait, None)

    llm_thread = _loop.run_in_executor(None, _run_llm)

    while True:
        tok = await token_queue.get()
        if tok is None:
            break
        if isinstance(tok, dict) and tok.get("error"):
            yield {"token": f"\n\n[LLM Error: {tok['error']}]\n"}
            break
        full_response.append(tok)
        yield {"token": tok}

    await llm_thread  # ensure thread is done

    # 7. Build structured sources
    sources = _format_sources(top_chunks)

    # ── Citation Validation + Encoding/LaTeX Sanitization ──
    full_text = "".join(full_response)
    original_text = full_text
    valid_source_indices = {str(s["index"]) for s in sources}
    hallucinated_citations = set(re.findall(r'\[(\d+)\]', full_text)) - valid_source_indices

    if hallucinated_citations:
        logger.warning("Stripping hallucinated citations: %s", hallucinated_citations)
        for bad_id in hallucinated_citations:
            full_text = full_text.replace(f"[{bad_id}]", "")

    # Always run sanitize_text to repair UTF-8 mojibake and convert LaTeX to Unicode
    full_text = llm_engine.sanitize_text(full_text)

    if full_text != original_text:
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
    # Use single-component max 1/(60+1) ≈ 0.0164 — a realistic ceiling for a
    # result that ranks #1 on dense search but not necessarily on BM25.
    _rrf_max = 1.0 / (60.0 + 1.0)
    confidence = min(max_score / _rrf_max, 1.0) if _rrf_max else 0.0

    # ═══════════════════════════════════════════════════════════════════════
    #  MODULE 2: Evaluation Logging & Validation
    # ═══════════════════════════════════════════════════════════════════════
    eval_store = get_eval_store()
    
    # Log query and retrieved chunks
    try:
        query_id = eval_store.log_query(
            query_text=question,
            user_id=user_id,
            session_id=token[:16] if token else None,  # Use token prefix as session ID
            doc_filter=doc_ids_filter,
            category_filter=category,
            response_time_ms=elapsed_ms,
            final_confidence_score=confidence
        )
        eval_store.log_chunks(query_id, top_chunks)
    except Exception as e:
        logger.warning("Failed to log evaluation data: %s", e)
    
    # Citation Validation
    validation_result = None
    try:
        validation_result = validate_citations_against_sources(full_text, sources)
        eval_store.log_citation_validation(
            query_id=query_id,
            response_text=full_text,
            total_citations=validation_result["total_citations"],
            valid_citations=validation_result["valid_citations"],
            invalid_citations=validation_result["invalid_citations"],
            unverified_claims=validation_result["unverified_claims"],
            citation_accuracy=validation_result["citation_accuracy"]
        )
        logger.info("Citation validation: %.1f%% accuracy (%d/%d)",
                    validation_result["citation_accuracy"],
                    validation_result["valid_citations"],
                    validation_result["total_citations"])
    except Exception as e:
        logger.warning("Citation validation failed: %s", e)
    
    # Hallucination Detection
    hallucination_result = None
    try:
        hallucination_result = detect_hallucinations(full_text, sources, validation_result)
        eval_store.log_hallucination_detection(
            query_id=query_id,
            total_claims=hallucination_result["total_claims"],
            supported_claims=hallucination_result["supported_claims"],
            unsupported_claims=hallucination_result["unsupported_claims"],
            contradicted_claims=hallucination_result["contradicted_claims"],
            hallucination_rate=hallucination_result["hallucination_rate"]
        )
        logger.info("Hallucination detection: %.1f%% rate (%d/%d claims)",
                    hallucination_result["hallucination_rate"],
                    hallucination_result["unsupported_claims"],
                    hallucination_result["total_claims"])
    except Exception as e:
        logger.warning("Hallucination detection failed: %s", e)

    yield {
        "done": True,
        "sources": sources,
        "response_time_ms": elapsed_ms,
        "chunks_used": len(top_chunks),
        "confidence_score": round(confidence, 3),
        "citation_accuracy": round(validation_result["citation_accuracy"], 1) if validation_result else None,
        "hallucination_rate": round(hallucination_result["hallucination_rate"], 1) if hallucination_result else None,
        "query_id": query_id,  # For feedback submission
    }
