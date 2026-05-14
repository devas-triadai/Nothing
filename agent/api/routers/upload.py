"""
AGRA Phase 4 — Router: Document Ingestion

Two endpoints:
  POST /admin/ingest   — INTERNAL (backend → agent) for Superadmin-uploaded
                         files via the Backend's /api/documents/upload route.
  POST /upload         — DIRECT (frontend → agent) for chat-driven uploads
                         that bypass the Admin Backend. Streams ingestion
                         progress via SSE and supports hierarchical metadata
                         (document_type, bidder_key, problem_statement).
"""

import json
import logging
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
from api.utils.auth_check import get_current_user

logger = logging.getLogger("agra.upload")

router = APIRouter()

import os as _os
_DATA_DIR = Path(_os.environ.get("AGRA_DATA_DIR", "/workspace/agra_data"))
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


# ─────────────────────────────────────────────────────────────────────
#  Direct Chat Upload — POST /api/agent/upload
#  Frontend uploads documents straight to the agent. Returns SSE
#  progress events and supports hierarchical metadata for bid RAG.
# ─────────────────────────────────────────────────────────────────────

_BIDDER_KEY_RE = re.compile(
    r"(?:bidder|vendor|company|firm|tenderer|contractor|supplier)\s*[:\-]?\s*([A-Z][A-Za-z0-9 .,&\-]{2,60})",
    re.IGNORECASE,
)
_PROBLEM_STMT_RE = re.compile(
    r"(?:tender|rfq|rfp|notice|nit|problem statement|reference no\.?|tender no\.?)\s*[:\-#]?\s*([A-Z0-9\-/]{3,40})",
    re.IGNORECASE,
)


def _heuristic_extract_metadata(text: str) -> dict:
    """
    Lightweight regex-based extraction of bidder_key and problem_statement
    from the first 2-3 pages of a document. Used as a fast pre-filter
    before deciding whether to invoke the LLM extractor.
    """
    result = {"bidder_key": None, "problem_statement": None, "confidence": 0.0}
    snippet = text[:4000]

    m1 = _BIDDER_KEY_RE.search(snippet)
    if m1:
        result["bidder_key"] = m1.group(1).strip()[:80]
        result["confidence"] += 0.4

    m2 = _PROBLEM_STMT_RE.search(snippet)
    if m2:
        result["problem_statement"] = m2.group(1).strip()[:40]
        result["confidence"] += 0.4

    return result


def _llm_extract_metadata(text: str) -> dict:
    """
    Ask the LLM to extract bidder_key and problem_statement from a doc.
    Returns dict with bidder_key, problem_statement, confidence (0..1).
    Falls back to heuristic on any failure.
    """
    snippet = text[:2000]
    prompt = (
        "Extract metadata from this document excerpt. Return ONLY a JSON object "
        "with keys 'bidder_key', 'problem_statement', 'confidence' (0..1).\n\n"
        "- bidder_key: the bidder/vendor/company name responding to the tender "
        "(short identifier like 'ACME Pvt Ltd' or 'Bidder A'). null if not found.\n"
        "- problem_statement: the tender/RFQ/RFP reference number or short title "
        "(e.g. 'NIT-2024-CG-05'). null if not found.\n"
        "- confidence: how sure you are (0.0 to 1.0).\n\n"
        f"DOCUMENT EXCERPT:\n{snippet}\n\n"
        "JSON only, no prose:"
    )
    try:
        raw = llm_engine.generate(
            messages=[
                {"role": "system", "content": "You are a precise metadata extraction tool. Output only JSON."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0.0,
            response_format={"type": "json_object"},
            raw=True,
        )
        # Strip code fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
        # Trim to outermost braces
        s = cleaned.find("{")
        e = cleaned.rfind("}") + 1
        if s < 0 or e <= s:
            raise ValueError("no json object in response")
        data = json.loads(cleaned[s:e])
        return {
            "bidder_key": (data.get("bidder_key") or None),
            "problem_statement": (data.get("problem_statement") or None),
            "confidence": float(data.get("confidence", 0.5)),
        }
    except Exception as ex:
        logger.warning("LLM metadata extraction failed, using heuristic: %s", ex)
        return _heuristic_extract_metadata(text)


@router.post("/upload")
async def chat_upload(
    request: Request,
    file: UploadFile = File(...),
    document_type: Optional[str] = Form(None),
    bidder_key: Optional[str] = Form(None),
    problem_statement: Optional[str] = Form(None),
    auto_extract: bool = Form(True),
    user: dict = Depends(get_current_user),
):
    """
    Direct chat upload with hierarchical metadata support.

    Streams Server-Sent Events as the document moves through:
      saved → ocr → metadata_extraction → chunking → embedding → storing → done

    The client receives:
      - 'saved' once the file is on disk
      - 'metadata_extracted' with detected bidder_key/problem_statement
        and a 'needs_confirmation' flag if confidence is low
      - per-stage progress
      - final 'done' with doc_id, filename, chunks, pages
    """

    # ── Validate file ──
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename missing.")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")

    # ── Save bytes to disk (streamed) with size guard ──
    doc_id = str(uuid.uuid4())
    safe_name = re.sub(r"[^A-Za-z0-9._\-]+", "_", file.filename)[:200]
    saved_path = _CHAT_UPLOADS_DIR / f"{doc_id}_{safe_name}"
    bytes_written = 0
    with open(saved_path, "wb") as fout:
        while True:
            chunk = await file.read(1024 * 256)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > _MAX_UPLOAD_BYTES:
                fout.close()
                try:
                    saved_path.unlink(missing_ok=True)
                except Exception:
                    pass
                raise HTTPException(status_code=413, detail="File exceeds 50 MB limit.")
            fout.write(chunk)

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

        # ── Stage: metadata extraction (only if hierarchical fields not supplied) ──
        eff_bidder = bidder_key
        eff_problem = problem_statement
        eff_doc_type = document_type
        metadata_info: dict = {
            "bidder_key": eff_bidder,
            "problem_statement": eff_problem,
            "document_type": eff_doc_type,
            "needs_confirmation": False,
            "confidence": 1.0 if (eff_bidder or eff_problem) else 0.0,
        }

        if auto_extract and not (eff_bidder and eff_problem):
            try:
                yield f"data: {json.dumps({'stage': 'metadata_extraction', 'progress': 0, 'message': 'Detecting bidder/tender…'})}\n\n"
                from api.rag import ocr as _ocr
                pages = _ocr.extract_document(str(saved_path))
                first_pages_text = "\n".join(p.get("text", "") for p in pages[:3])
                if first_pages_text.strip():
                    extracted = _llm_extract_metadata(first_pages_text)
                    if not eff_bidder and extracted.get("bidder_key"):
                        eff_bidder = extracted["bidder_key"]
                    if not eff_problem and extracted.get("problem_statement"):
                        eff_problem = extracted["problem_statement"]
                    metadata_info.update({
                        "bidder_key": eff_bidder,
                        "problem_statement": eff_problem,
                        "confidence": extracted.get("confidence", 0.0),
                        "needs_confirmation": extracted.get("confidence", 0.0) < 0.7,
                    })
                # If document_type still unspecified, infer from filename keywords
                if not eff_doc_type:
                    low = safe_name.lower()
                    if any(k in low for k in ("bid", "proposal", "tender_response", "rfp_response", "rfq_response")):
                        eff_doc_type = "bid"
                    elif any(k in low for k in ("standard", "iso", "ieee", "is_", "spec_", "specification")):
                        eff_doc_type = "standard"
                    else:
                        eff_doc_type = "subject"
                    metadata_info["document_type"] = eff_doc_type
                yield f"data: {json.dumps({'stage': 'metadata_extracted', 'metadata': metadata_info})}\n\n"
            except Exception as ex:
                logger.warning("Metadata extraction stage failed: %s", ex)
                yield f"data: {json.dumps({'stage': 'metadata_extracted', 'metadata': metadata_info, 'warning': str(ex)})}\n\n"

        # ── Run the full ingestion pipeline (OCR/chunk/embed/store) ──
        try:
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
                bidder_key=eff_bidder,
                problem_statement=eff_problem,
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
                "bidder_key": eff_bidder,
                "problem_statement": eff_problem,
            }) + "\n\n"
        )

    return StreamingResponse(_stream(), media_type="text/event-stream")
