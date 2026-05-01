"""
AGRA Phase 2 — Router: Document Upload & Management
Upload files, trigger ingestion, list/delete documents.
"""

import json
import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Query
from fastapi.responses import StreamingResponse

from api.utils.auth_check import get_current_user
from api.rag.pipeline import ingest_document
from api.rag.vector_store import get_store

logger = logging.getLogger("agra.upload")

router = APIRouter()

import os as _os
_DATA_DIR = Path(_os.environ.get("AGRA_DATA_DIR", "/workspace/agra_data"))
if not _DATA_DIR.exists():
    _DATA_DIR = Path(__file__).resolve().parent.parent.parent / "agra_data"
_UPLOADS_DIR = _DATA_DIR / "uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".jpg", ".jpeg", ".png"}
_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """
    Upload a document for ingestion into the RAG knowledge base.
    Returns an SSE stream of ingestion progress events.
    """
    # Validate file extension
    filename = file.filename or "untitled"
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(_ALLOWED_EXTENSIONS)}",
        )

    # Check for duplicates by filename in Qdrant (not just disk, to allow retries if crashed)
    if get_store().document_exists(filename):
        raise HTTPException(
            status_code=409,
            detail=f"Document '{filename}' has already been successfully ingested.",
        )

    # Read and validate size
    content = await file.read()
    if len(content) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({len(content) / 1024 / 1024:.1f} MB). Max: 50 MB.",
        )

    # Save to disk
    doc_id = str(uuid.uuid4())
    safe_name = f"{doc_id}_{filename}"
    save_path = _UPLOADS_DIR / safe_name
    save_path.write_bytes(content)

    logger.info("Uploaded %s (%d bytes) → %s", filename, len(content), save_path)

    # Stream ingestion progress as SSE
    def event_stream():
        for event in ingest_document(
            file_path=str(save_path),
            filename=filename,
            doc_id=doc_id,
            uploaded_by_user_id=0,  # Extracted from JWT if needed
            token=user.get("_raw_token", ""),
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/documents")
async def list_documents(
    user: dict = Depends(get_current_user),
):
    """
    List all ingested documents with their file info and chunk counts.
    """
    store = get_store()
    documents = []
    seen_docs = {}

    # Scan Qdrant for unique doc_ids
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
            did = meta.get("doc_id", "")
            if did and did not in seen_docs:
                seen_docs[did] = {
                    "doc_id": did,
                    "filename": meta.get("filename", "Unknown"),
                    "chunks": 0,
                    "pages": set(),
                }
            if did:
                seen_docs[did]["chunks"] += 1
                seen_docs[did]["pages"].add(meta.get("page", 0))
        if offset is None:
            break

    for doc in seen_docs.values():
        doc["page_count"] = len(doc["pages"])
        doc["pages"] = sorted(doc["pages"])
        # Check if file still exists on disk
        matching = list(_UPLOADS_DIR.glob(f"{doc['doc_id']}_*"))
        doc["file_exists"] = len(matching) > 0
        doc["status"] = "indexed"
        documents.append(doc)

    return {"documents": documents, "total": len(documents)}


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Delete a document from the vector store and uploads folder.
    """
    store = get_store()

    # Delete from Qdrant
    deleted_count = store.delete_document(doc_id)

    # Delete file from uploads
    files_deleted = 0
    for f in _UPLOADS_DIR.glob(f"{doc_id}_*"):
        f.unlink(missing_ok=True)
        files_deleted += 1

    if deleted_count == 0 and files_deleted == 0:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")

    logger.info("Deleted doc_id=%s: %d chunks, %d files.", doc_id, deleted_count, files_deleted)
    return {
        "deleted": True,
        "doc_id": doc_id,
        "chunks_removed": deleted_count,
        "files_removed": files_deleted,
    }
