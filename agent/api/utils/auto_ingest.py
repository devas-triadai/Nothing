"""
AGRA — Auto-Ingest Built-in Knowledge Base
On agent startup, checks if synthetic ICG/IMO documents from
agent/knowledge_base/ are already indexed. If not, ingests them
in a background thread so the compliance checker works out-of-the-box.
"""

import logging
import threading
import uuid
from pathlib import Path
from typing import List

logger = logging.getLogger("agra.auto_ingest")

_KB_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge_base"
_MARKER_PREFIX = "builtin:"


def _already_indexed(filename: str) -> bool:
    """Check if a knowledge-base file is already in the vector store."""
    from api.rag.vector_store import get_store
    store = get_store()
    try:
        results, _ = store.client.scroll(
            collection_name="agra_docs",
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
        # Scan for a chunk with this filename
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

    # 2. Chunk
    chunks = chunk_pages(pages, doc_id, filename)
    if not chunks:
        logger.warning("No chunks from %s — skipping.", filename)
        return

    # Mark chunks as built-in
    for c in chunks:
        c["metadata"]["source"] = "built-in"
        c["metadata"]["doc_id"] = doc_id

    # 3. Embed
    texts = [c["text"] for c in chunks]
    all_embeddings = []
    batch_size = 32
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embs = embedder.embed_texts(batch)
        all_embeddings.extend(embs)

    # 4. Store
    store = get_store()
    count = store.upsert_chunks(chunks, all_embeddings)
    logger.info("✓ Auto-ingested %s → %d chunks, %d pages.", filename, count, len(pages))


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
