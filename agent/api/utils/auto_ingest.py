"""
AGRA — Auto-Ingest Built-in Knowledge Base (Phase 1 Unified)
On agent startup, checks if synthetic ICG/IMO documents from
agent/knowledge_base/ are already indexed. If not, ingests them
in a background thread so the compliance checker works out-of-the-box.

Phase 1 Enhancement:
  - Auto-classifies each knowledge_base file using Tier 1 heuristics
  - Stores category/tags/summary in Qdrant chunk metadata
  - Registers each file with admin backend PostgreSQL for unified visibility
"""

import hashlib
import logging
import threading
import uuid
from pathlib import Path
from typing import List

import httpx

logger = logging.getLogger("agra.auto_ingest")

_KB_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge_base"
_MARKER_PREFIX = "builtin:"
_ADMIN_BASE = "http://localhost:8000"

import os
_ADMIN_BASE = os.getenv("AGRA_BACKEND_URL", _ADMIN_BASE)


def _already_indexed(filename: str) -> bool:
    """Check if a knowledge-base file is already in the vector store."""
    from api.rag.vector_store import get_store
    store = get_store()
    try:
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
                meta = pt.payload.get("metadata", {})
                if meta.get("filename") == filename:
                    return True
            if offset is None:
                break
    except Exception as e:
        logger.warning("Error checking index for %s: %s", filename, e)
    return False


def _classify_file(file_path: Path, text_preview: str) -> dict:
    """Run Tier 1 + Tier 2 classification on a knowledge_base file."""
    from api.utils.classifier import classify_document
    ext = file_path.suffix.lower().lstrip(".")
    result = classify_document(file_path.name, ext, text_preview)
    return result


def _register_with_admin(file_path: Path, doc_id: str, classification: dict) -> None:
    """Register an auto-ingested file with the admin backend PostgreSQL (best effort)."""
    try:
        # Read file content for SHA-256
        with open(file_path, "rb") as f:
            content = f.read()
        sha256 = hashlib.sha256(content).hexdigest()

        # Use internal API — we send a minimal registration
        resp = httpx.post(
            f"{_ADMIN_BASE}/api/documents/register-agent-doc",
            json={
                "filename": file_path.name,
                "file_type": file_path.suffix.lower().lstrip("."),
                "file_size": len(content),
                "category": classification.get("category", "General"),
                "sub_category": classification.get("sub_category", ""),
                "tags": classification.get("tags", ""),
                "description": classification.get("summary", ""),
                "sha256_hash": sha256,
                "source": "knowledge_base",
                "classification_confidence": classification.get("confidence", 0.0),
                "qdrant_doc_id": doc_id,
                "derived_from": classification.get("derived_from"),
                "references": classification.get("references", []),
            },
            timeout=10.0,
        )
        if resp.status_code == 200:
            logger.info("✓ Registered %s with admin backend.", file_path.name)
        else:
            logger.warning("Admin registration for %s returned %d", file_path.name, resp.status_code)
    except Exception as e:
        logger.warning("Failed to register %s with admin backend: %s", file_path.name, e)


def _ingest_file(file_path: Path) -> None:
    """Ingest a single knowledge-base file using the standard pipeline."""
    from api.rag import ocr, embedder
    from api.rag.chunker import chunk_pages
    from api.rag.vector_store import get_store

    filename = file_path.name
    doc_id = f"{_MARKER_PREFIX}{filename}"

    logger.info("Auto-ingesting: %s", filename)

    # 1. Extract text
    pages = ocr.extract_document(str(file_path))
    if not pages:
        logger.warning("No text extracted from %s — skipping.", filename)
        return

    # 2. Classify using extracted text
    text_preview = "\n".join(p.get("text", "") for p in pages[:2])[:3000]
    classification = _classify_file(file_path, text_preview)
    category = classification.get("category", "General")
    tags = classification.get("tags", "")
    summary = classification.get("summary", "")

    logger.info(
        "Classified %s → category=%s, sub=%s, confidence=%.2f",
        filename, category,
        classification.get("sub_category", ""),
        classification.get("confidence", 0),
    )
    
    # 2.5 LLM Metadata Extraction (Cross-references)
    from api.rag import llm as llm_engine
    try:
        ref_prompt = f"Extract any standard numbers, codes, or document references mentioned in this text: {text_preview[:1500]}. Return ONLY a comma separated list, or 'None'."
        refs = llm_engine.generate([{"role": "user", "content": ref_prompt}], max_tokens=100)
        if refs and refs.lower() != 'none':
            classification["references"] = [r.strip() for r in refs.split(",") if r.strip()]
    except Exception as e:
        logger.warning("LLM cross-reference extraction failed: %s", e)

    # 3. Chunk (with category metadata)
    chunks = chunk_pages(pages, doc_id, filename, category=category, description=summary)
    if not chunks:
        logger.warning("No chunks from %s — skipping.", filename)
        return

    # Mark chunks as built-in with classification metadata
    for c in chunks:
        c["metadata"]["source"] = "built-in"
        c["metadata"]["doc_id"] = doc_id
        c["metadata"]["category"] = category
        c["metadata"]["sub_category"] = classification.get("sub_category", "")
        c["metadata"]["tags"] = tags
        c["metadata"]["classification_confidence"] = classification.get("confidence", 0)

    # 4. Embed
    texts = [c["text"] for c in chunks]
    all_embeddings = []
    batch_size = 32
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embs = embedder.embed_texts(batch)
        all_embeddings.extend(embs)

    # 5. Store
    store = get_store()
    
    # 5.5 Semantic Lineage Detection (cosine > 0.85)
    if all_embeddings:
        try:
            # Search for highly similar existing document using the first chunk's embedding
            sim_candidates = store.hybrid_search(texts[0][:100], all_embeddings[0], top_k=3)
            for cand in sim_candidates:
                if cand.get("dense_score", 0) > 0.85 and cand["metadata"].get("doc_id") != doc_id:
                    classification["derived_from"] = cand["metadata"]["doc_id"]
                    logger.info("Semantic Lineage Detected: %s is derived from %s (sim=%.2f)", doc_id, cand['metadata']['doc_id'], cand['dense_score'])
                    break
        except Exception as e:
            logger.warning("Semantic lineage detection failed: %s", e)

    count = store.upsert_chunks(chunks, all_embeddings)
    logger.info("✓ Auto-ingested %s → %d chunks, %d pages, category=%s.", filename, count, len(pages), category)

    # 6. Register with admin backend (best effort)
    _register_with_admin(file_path, doc_id, classification)


def _run_auto_ingest() -> None:
    """Scan knowledge_base/ and ingest any files not yet indexed."""
    if not _KB_DIR.exists():
        logger.info("No knowledge_base/ directory found — skipping auto-ingest.")
        return

    files: List[Path] = sorted(
        p for p in _KB_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in (".txt", ".pdf", ".docx")
    )

    if not files:
        logger.info("knowledge_base/ is empty — nothing to auto-ingest.")
        return

    logger.info("Found %d files in knowledge_base/. Checking index...", len(files))

    ingested = 0
    skipped = 0
    for f in files:
        if _already_indexed(f.name):
            logger.debug("Already indexed: %s", f.name)
            skipped += 1
            continue
        try:
            _ingest_file(f)
            ingested += 1
        except Exception as e:
            logger.error("Failed to auto-ingest %s: %s", f.name, e, exc_info=True)

    logger.info(
        "Auto-ingest complete: %d ingested, %d already present, %d total.",
        ingested, skipped, len(files),
    )


def start_auto_ingest_background() -> None:
    """Launch auto-ingest in a background thread (non-blocking startup)."""
    t = threading.Thread(target=_run_auto_ingest, name="auto-ingest", daemon=True)
    t.start()
    logger.info("Auto-ingest background thread started.")
