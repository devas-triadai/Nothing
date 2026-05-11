"""
AGRA Phase 4 — Router: Admin-to-Agent Document Ingestion (Single Source of Truth)

This module is NO LONGER exposed to the Agent UI frontend.
It provides one internal endpoint: POST /admin/ingest

Called exclusively by the backend after a Superadmin uploads a file.
Runs the full OCR → chunk → embed → store pipeline in a background thread
so the backend request returns immediately.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks, Form
from pydantic import BaseModel

from api.rag.pipeline import ingest_document

logger = logging.getLogger("agra.upload")

router = APIRouter()

import os as _os
_DATA_DIR = Path(_os.environ.get("AGRA_DATA_DIR", "/workspace/agra_data"))
if not _DATA_DIR.exists():
    _DATA_DIR = Path(__file__).resolve().parent.parent.parent / "agra_data"
_UPLOADS_DIR = _DATA_DIR / "uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


class AdminIngestRequest(BaseModel):
    file_path: str
    filename: str
    doc_id: str
    category: Optional[str] = None
    description: Optional[str] = None
    parent_doc_id: Optional[str] = None
    version_notes: Optional[str] = None


def _run_ingestion_sync(req: AdminIngestRequest):
    """
    Synchronous wrapper around the generator-based ingest_document.
    Executed in a background thread so it doesn't block the event loop.
    """
    logger.info("[Admin Ingest] Starting for doc_id=%s file=%s", req.doc_id, req.filename)
    try:
        events = []
        for event in ingest_document(
            file_path=req.file_path,
            filename=req.filename,
            doc_id=req.doc_id,
            uploaded_by_user_id=0,
            token="",
            category=req.category,
            description=req.description,
            parent_doc_id=req.parent_doc_id,
            version_notes=req.version_notes,
            source="admin_upload",
        ):
            events.append(event)

        last_event = events[-1] if events else {}
        if last_event.get("error"):
            logger.error("[Admin Ingest] Failed for doc_id=%s: %s", req.doc_id, last_event)
        else:
            logger.info("[Admin Ingest] Completed for doc_id=%s (%d events)", req.doc_id, len(events))
    except Exception as e:
        logger.error("[Admin Ingest] Exception for doc_id=%s: %s", req.doc_id, e, exc_info=True)


@router.post("/admin/ingest")
async def admin_ingest(
    background_tasks: BackgroundTasks,
    file_path: str = Form(...),
    filename: str = Form(...),
    doc_id: str = Form(...),
    category: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    parent_doc_id: Optional[str] = Form(None),
    version_notes: Optional[str] = Form(None),
):
    """
    INTERNAL endpoint — called by the backend after a Superadmin uploads a file.
    Triggers the full RAG ingestion pipeline asynchronously using FastAPI BackgroundTasks.
    """
    req = AdminIngestRequest(
        file_path=file_path,
        filename=filename,
        doc_id=doc_id,
        category=category,
        description=description,
        parent_doc_id=parent_doc_id,
        version_notes=version_notes,
    )

    # Use FastAPI BackgroundTasks for proper async background execution
    background_tasks.add_task(_run_ingestion_sync, req)

    logger.info("[Admin Ingest] Queued doc_id=%s via BackgroundTasks", doc_id)
    return {
        "message": "Ingestion queued",
        "doc_id": doc_id,
        "filename": filename,
        "status": "queued",
    }


@router.get("/documents")
async def list_documents():
    """
    List all documents currently available in the Agent's vector store.
    Used by the UI to populate the context selector.
    """
    from api.rag.vector_store import get_store
    store = get_store()
    docs = store.list_unique_documents()
    return {"documents": docs}
