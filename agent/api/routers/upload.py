"""
AGRA Phase 4 — Router: Document Ingestion

Two endpoints:
  POST /admin/ingest   — INTERNAL (backend → agent) for Superadmin-uploaded
                         files via the Backend's /api/documents/upload route.
  POST /upload         — DIRECT (frontend → agent) for chat-driven uploads
                         that bypass the Admin Backend. Streams ingestion
                         progress via SSE.
"""

import hashlib
import json
import logging
import os
import re
import threading
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.rag.pipeline import ingest_document
from api.rag import llm as llm_engine
from api.rag.metadata_extractor import extract_document_metadata, format_metadata_for_storage
from api.utils.auth_check import get_current_user

logger = logging.getLogger("agra.upload")

# Backend API base URL for storing metadata
_ADMIN_BASE = os.getenv("AGRA_BACKEND_URL", "http://localhost:8000")

router = APIRouter()

_DATA_DIR = Path(os.environ.get("AGRA_DATA_DIR", "/workspace/agra_data"))
if not _DATA_DIR.exists():
    _DATA_DIR = Path(__file__).resolve().parent.parent.parent / "agra_data"
_UPLOADS_DIR = _DATA_DIR / "uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
_CHAT_UPLOADS_DIR = _UPLOADS_DIR / "chat"
_CHAT_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Allowed extensions for direct chat upload (broader than admin upload)
_ALLOWED_EXTS = {
    "pdf", "docx", "doc", "txt", "md", "csv", "xlsx", "pptx",
    "png", "jpg", "jpeg", "gif", "webp", "svg",
}
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


class AdminIngestRequest(BaseModel):
    file_path: str
    filename: str
    doc_id: str
    category: Optional[str] = None
    description: Optional[str] = None
    parent_doc_id: Optional[str] = None
    version_notes: Optional[str] = None


async def _extract_and_store_metadata(
    doc_id: str,
    file_path: str,
    filename: str,
    auth_token: str = "",
    parent_doc_id: Optional[str] = None
):
    """
    Background task: Extract metadata, entities, detect lineage, 
    generate change summaries, and store in backend.
    Fire-and-forget pattern — doesn't block upload completion.
    """
    try:
        import asyncio
        import httpx
        from api.rag import ocr
        from api.rag.vector_store import get_store
        from api.rag.lineage_detector import detect_document_lineage
        from api.rag.chunker import chunk_pages
        from api.rag.entity_extractor import extract_entities_from_chunks
        from api.rag.change_analyzer import generate_and_store_change_summary
        
        logger.info("[Metadata+Lineage+Entities+Changes] Starting for doc_id=%s", doc_id)
        
        # Check if doc_id is a backend integer ID or a chat-upload UUID
        try:
            int(doc_id)
            _is_backend_doc = True
        except (ValueError, TypeError):
            _is_backend_doc = False
        
        # Step 1: Extract text from document (reuse OCR)
        pages = ocr.extract_document(file_path)
        if not pages:
            logger.warning("[Metadata+Lineage] No text extracted from %s", filename)
            return
        
        # Combine text (first 10 pages for speed)
        full_text = "\n\n".join(p["text"] if isinstance(p, dict) else p for p in pages[:10])
        
        # Step 2: Run LLM metadata extraction
        metadata = await extract_document_metadata(full_text, filename)
        
        # Step 3: Check confidence threshold and store metadata
        if metadata.get("confidence", 0.0) >= 0.6:
            storage_data = format_metadata_for_storage(metadata)
            if storage_data and _is_backend_doc:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        f"{_ADMIN_BASE}/api/documents/{doc_id}/metadata/extracted",
                        json=storage_data,
                        headers={"Authorization": f"Bearer {auth_token}"} if auth_token else {}
                    )
                    if response.status_code == 200:
                        logger.info("[Metadata+Lineage] Metadata stored for doc_id=%s", doc_id)
                    else:
                        logger.warning("[Metadata+Lineage] Metadata backend returned %s", response.status_code)
        else:
            logger.info("[Metadata+Lineage] Low metadata confidence (%.2f) for %s",
                       metadata.get("confidence", 0.0), doc_id)
        
        # Step 4: Module 7 - Semantic Similarity Lineage Detection
        # Create chunks for lineage detection (reuse chunker)
        store = get_store()
        chunks = chunk_pages(
            pages, doc_id, filename,
            source="lineage_detection",
            document_type="unknown"
        )
        
        if chunks:
            logger.info("[Metadata+Lineage] Running lineage detection for %s (%d chunks)",
                       doc_id, len(chunks))
            
            # Run lineage detection
            lineage_result = await detect_document_lineage(
                doc_id=doc_id,
                chunks=chunks,
                filename=filename,
                metadata=metadata if metadata.get("confidence", 0.0) >= 0.6 else None,
                store=store
            )
            
            candidates = lineage_result.get("candidates", [])
            
            if candidates:
                logger.info("[Metadata+Lineage] Found %d lineage candidates for %s (top: %.3f)",
                           len(candidates), doc_id, candidates[0].get("similarity", 0.0))
                
                if _is_backend_doc:
                    # Send candidates to backend
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        response = await client.post(
                            f"{_ADMIN_BASE}/api/documents/{doc_id}/lineage/detected",
                            json=candidates,
                            params={"auto_accept": "false"},  # Manual review for safety
                            headers={"Authorization": f"Bearer {auth_token}"} if auth_token else {}
                        )
                        
                        if response.status_code == 200:
                            result = response.json()
                            logger.info("[Metadata+Lineage] Lineage stored for %s: %d auto, %d pending",
                                       doc_id, result.get("auto_accepted", 0), result.get("pending_review", 0))
                        else:
                            logger.warning("[Metadata+Lineage] Lineage backend returned %s: %s",
                                         response.status_code, response.text[:200])
                else:
                    logger.info("[Metadata+Lineage] Skipping backend lineage for chat-upload doc %s (UUID)", doc_id)
            else:
                logger.info("[Metadata+Lineage] No lineage candidates found for %s", doc_id)
        else:
            logger.warning("[Metadata+Lineage] No chunks for lineage detection: %s", doc_id)
        
        # Step 5: Module 7 Phase 4 - Entity Extraction
        if chunks:
            logger.info("[Metadata+Lineage] Running entity extraction for %s", doc_id)
            
            entities = await extract_entities_from_chunks(chunks, max_chunks=5)
            
            if entities:
                logger.info("[Metadata+Lineage] Extracted %d entities for %s", len(entities), doc_id)
                
                # Format entities for storage
                entity_data = [
                    {
                        "entity_type": e.entity_type,
                        "name": e.name,
                        "normalized_name": e.normalized_name,
                        "context": e.context,
                        "chunk_index": e.chunk_index,
                        "page_number": e.page_number,
                        "extraction_confidence": e.confidence
                    }
                    for e in entities
                ]
                
                # Send to backend (only for admin-uploaded docs with integer IDs)
                if _is_backend_doc:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        response = await client.post(
                            f"{_ADMIN_BASE}/api/documents/{doc_id}/entities",
                            json=entity_data,
                            headers={"Authorization": f"Bearer {auth_token}"} if auth_token else {}
                        )
                        
                        if response.status_code == 200:
                            result = response.json()
                            logger.info("[Metadata+Lineage] Entities stored for %s: %d new",
                                       doc_id, result.get("entities_stored", 0))
                        else:
                            logger.warning("[Metadata+Lineage] Entities backend returned %s", response.status_code)
            else:
                logger.info("[Metadata+Lineage] No entities extracted for %s", doc_id)
        
        # Step 6: Module 7 Phase 6 - Generate Change Summary for version updates
        if parent_doc_id and chunks:
            logger.info("[Metadata+Lineage] Generating change summary: %s -> %s", 
                       parent_doc_id, doc_id)
            
            try:
                store = get_store()
                change_result = await generate_and_store_change_summary(
                    old_doc_id=parent_doc_id,
                    new_doc_id=doc_id,
                    store=store,
                    backend_api_url=_ADMIN_BASE,
                    auth_token=auth_token
                )
                
                if change_result:
                    logger.info("[Metadata+Lineage] Change summary generated for %s -> %s (impact: %s)",
                               parent_doc_id, doc_id, change_result.get("impact", "Unknown"))
                else:
                    logger.warning("[Metadata+Lineage] Failed to generate change summary for %s -> %s",
                                  parent_doc_id, doc_id)
            except Exception as change_e:
                logger.error("[Metadata+Lineage] Change summary generation failed: %s", change_e)
                # Non-fatal, continue
    
    except Exception as e:
        logger.error("[Metadata+Lineage] Failed for doc_id=%s: %s", doc_id, e, exc_info=True)
        # Don't re-raise — this is fire-and-forget


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
    
    # Module 7: Queue metadata extraction as fire-and-forget background task
    # This runs after ingestion and doesn't block the response
    background_tasks.add_task(_extract_and_store_metadata, doc_id, file_path, filename, "", parent_doc_id)

    logger.info("[Admin Ingest] Queued doc_id=%s via BackgroundTasks", doc_id)
    return {
        "message": "Ingestion queued",
        "doc_id": doc_id,
        "filename": filename,
        "status": "queued",
    }


@router.get("/documents")
async def list_documents(user: dict = Depends(get_current_user)):
    """
    List documents available to the current user based on RBAC.
    Super Admin: All documents
    Admin/Officer: Documents with clearance <= Confidential (2)
    Viewer: Documents with clearance <= Unclassified (1)
    """
    from api.rag.vector_store import get_store
    from api.utils.auth_check import filter_documents_by_access
    store = get_store()
    docs = store.list_unique_documents()
    # Filter documents based on user's role and clearance level
    filtered_docs = filter_documents_by_access(user, docs)
    return {"documents": filtered_docs}


@router.patch("/documents/{doc_id}/clearance")
async def update_document_clearance(
    doc_id: str,
    clearance_level: int = Form(..., ge=1, le=4),
    user: dict = Depends(get_current_user),
):
    """
    Update the clearance level for an existing document.
    Only superadmins can modify document classification.
    
    Args:
        clearance_level: 1=Unclassified, 2=Confidential, 3=Secret, 4=Top Secret
    """
    from api.utils.auth_check import is_superadmin
    if not is_superadmin(user):
        raise HTTPException(status_code=403, detail="Super Admin access required")
    
    store = get_store()
    # Update clearance_level in all chunks belonging to this doc_id
    updated_count = store.update_document_metadata(doc_id, {"clearance_level": clearance_level})
    
    if updated_count == 0:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    
    return {"doc_id": doc_id, "clearance_level": clearance_level, "chunks_updated": updated_count}


# ─────────────────────────────────────────────────────────────────────
#  Direct Chat Upload — POST /api/agent/upload
#  Frontend uploads documents straight to the agent. Returns SSE
#  progress events.
# ─────────────────────────────────────────────────────────────────────

def _stream_duplicate(doc_id: str, filename: str, bytes_written: int, meta: dict):
    """
    SSE stream for duplicate file detection.
    Yields the same events as normal upload but immediately completes with existing doc info.
    """
    yield f"data: {json.dumps({'stage': 'saved', 'doc_id': doc_id, 'filename': filename, 'bytes': bytes_written, 'duplicate': True})}\n\n"
    yield f"data: {json.dumps({'stage': 'done', 'doc_id': doc_id, 'filename': filename, 'pages': meta.get('pages', 0), 'chunks': meta.get('chunks', 0), 'duplicate': True})}\n\n"


@router.post("/upload")
async def chat_upload(
    request: Request,
    file: UploadFile = File(...),
    document_type: Optional[str] = Form(None),
    clearance_level: int = Form(1),
    user: dict = Depends(get_current_user),
):
    """
    Direct chat upload.

    Streams Server-Sent Events as the document moves through:
      saved → ocr → chunking → embedding → storing → done

    The client receives:
      - 'saved' once the file is on disk
      - per-stage progress
      - final 'done' with doc_id, filename, chunks, pages
    
    Args:
        clearance_level: Document classification (1=Unclassified, 2=Confidential, 3=Secret, 4=Top Secret)
    """

    # ── Validate file ──
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename missing.")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")

    # ── Save bytes to disk (streamed) with size guard + content hash for dedup ──
    safe_name = re.sub(r"[^A-Za-z0-9._\-]+", "_", file.filename)[:200]
    bytes_written = 0
    hasher = hashlib.sha256()

    # Stream to temp file while computing hash
    temp_path = _CHAT_UPLOADS_DIR / f"_temp_{uuid.uuid4()}_{safe_name}"
    with open(temp_path, "wb") as fout:
        while True:
            chunk = await file.read(1024 * 256)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > _MAX_UPLOAD_BYTES:
                fout.close()
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass
                raise HTTPException(status_code=413, detail="File exceeds 50 MB limit.")
            fout.write(chunk)
            hasher.update(chunk)

    content_hash = hasher.hexdigest()

    # ── Check for duplicate by content hash ──
    from api.rag.vector_store import get_store
    store = get_store()
    existing_doc_id = store.get_doc_id_by_content_hash(content_hash)
    if existing_doc_id:
        # Duplicate found — clean up temp file and return existing doc info
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        logger.info("[Chat Upload] Duplicate detected (hash=%s), returning existing doc_id=%s", content_hash[:16], existing_doc_id)
        # Return existing doc info immediately (skip re-processing)
        existing_meta = store.get_document_metadata(existing_doc_id) or {}
        return StreamingResponse(
            _stream_duplicate(existing_doc_id, safe_name, bytes_written, existing_meta),
            media_type="text/event-stream",
        )

    # Not a duplicate — proceed with new doc_id
    doc_id = str(uuid.uuid4())
    saved_path = _CHAT_UPLOADS_DIR / f"{doc_id}_{safe_name}"
    temp_path.rename(saved_path)

    logger.info(
        "[Chat Upload] saved doc_id=%s filename=%s bytes=%d type=%s",
        doc_id, safe_name, bytes_written, document_type or "(none)",
    )

    # Capture auth token for downstream calls
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    user_id_str = user.get("sub") or user.get("user_id") or "0"
    try:
        uploaded_by = int(user_id_str)
    except (TypeError, ValueError):
        uploaded_by = 0

    def _stream():
        # Initial saved event
        yield f"data: {json.dumps({'stage': 'saved', 'doc_id': doc_id, 'filename': safe_name, 'bytes': bytes_written})}\n\n"

        eff_doc_type = document_type

        # ── Run the full ingestion pipeline (OCR/chunk/embed/store) ──
        try:
            extra_md = {}
            if clearance_level and clearance_level != 1:
                extra_md["clearance_level"] = clearance_level
            for event in ingest_document(
                file_path=str(saved_path),
                filename=safe_name,
                doc_id=doc_id,
                uploaded_by_user_id=uploaded_by,
                token=token,
                category=None,
                description=None,
                source="chat_upload",
                document_type=eff_doc_type,
                content_hash=content_hash,
                extra_metadata=extra_md or None,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as ex:
            logger.exception("Ingestion failed for %s: %s", safe_name, ex)
            yield f"data: {json.dumps({'stage': 'error', 'error': str(ex)})}\n\n"
            return

        # Final summary event
        yield (
            "data: " + json.dumps({
                "stage": "done",
                "doc_id": doc_id,
                "filename": safe_name,
                "document_type": eff_doc_type,
            }) + "\n\n"
        )
        
        # Module 7: Fire metadata extraction as background task
        # This runs after successful upload without blocking the response
        # Note: _stream() is a sync generator in a thread pool, so we spawn a new thread
        import asyncio as _asyncio
        def _run_metadata():
            _asyncio.run(
                _extract_and_store_metadata(doc_id, str(saved_path), safe_name, token, None)
            )
        threading.Thread(target=_run_metadata, daemon=True).start()

    return StreamingResponse(_stream(), media_type="text/event-stream")
