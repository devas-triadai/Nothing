"""
AGRA Phase 2 — Agent API (port 8001)
Air-Gapped Retrieval Agent for Indian Coast Guard HQ

Routes:
  /api/agent/upload        — Document upload & management
  /api/agent/chat          — Conversational Q&A (SSE)
  /api/agent/generate/*    — PPT, Summary, Quiz generation
  /api/agent/download/*    — File downloads for generated content
"""

import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse

from api.utils.auth_check import get_current_user

_ADMIN_BASE = os.getenv("AGRA_BACKEND_URL", "http://localhost:8000")

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("agra.agent")

_DATA_DIR = Path(os.environ.get("AGRA_DATA_DIR", "/workspace/agra_data"))
if not _DATA_DIR.exists():
    _DATA_DIR = Path(__file__).resolve().parent.parent / "agra_data"
_OUTPUTS_DIR = _DATA_DIR / "outputs"
_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: Load all models, init DBs and vector store.
    Shutdown: Release resources.
    """
    logger.info("╔══════════════════════════════════════════════════════════╗")
    _port = os.getenv("AGENT_API_PORT", "8005")
    logger.info("║   AGRA Phase 2 — Agent API starting on port %s       ║", _port)
    logger.info("╚══════════════════════════════════════════════════════════╝")

    # ── 1. Init agent-local database ──
    from api.models.models import init_agent_db
    init_agent_db()
    logger.info("Agent database initialised (agent.db).")

    # ── 2. Init Qdrant vector store ──
    from api.rag.vector_store import init_vector_store
    init_vector_store()
    logger.info("Qdrant vector store ready.")

    # ── 3. Load embedding model ──
    from api.rag.embedder import load_embedder
    load_embedder()
    logger.info("Embedding model (bge-m3) loaded.")

    # ── 4. Load reranker ──
    from api.rag.reranker import load_reranker
    load_reranker()
    logger.info("Reranker (bge-reranker-v2-m3) loaded.")

    # ── 5. Connect to llama-server (external C++ process) ──
    from api.rag.llm import load_llm
    load_llm()
    logger.info("Connected to llama-server (Gemma 4 31B-IT).")

    logger.info("━━━ All models loaded. Agent API ready. ━━━")

    # ── 6. Auto-ingest built-in knowledge base (background) ──
    from api.utils.auto_ingest import start_auto_ingest_background
    start_auto_ingest_background()

    # ── 7. Start SessionManager garbage collector ──
    from api.session_manager import get_session_manager
    get_session_manager().start_gc()
    logger.info("SessionManager GC started.")

    yield

    logger.info("Agent API shutting down — releasing resources.")


# ── FastAPI App ──
app = FastAPI(
    title="AGRA Agent API",
    description=(
        "Air-Gapped Retrieval Agent — Document Q&A, PPT generation, "
        "summary, and quiz. "
        "All processing runs locally — zero internet access."
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Security: TLS Enforcement (Phase 7) ──
if os.getenv("ENFORCE_TLS", "false").lower() == "true":
    app.add_middleware(HTTPSRedirectMiddleware)
    logger.info("🛡️ TLS Enforcement Enabled: All plaintext HTTP traffic will be rejected/redirected.")

# ── CORS ── (ports from env vars)
_UI_PORT = os.getenv("AGENT_UI_PORT", "7860")
_ADMIN_PORT = os.getenv("ADMIN_PORT", "3000")
_BACKEND_PORT = os.getenv("BACKEND_PORT", "8000")

# Static known-safe origins (localhost variants)
_STATIC_ORIGINS = [
    f"http://localhost:{_ADMIN_PORT}",
    f"http://0.0.0.0:{_ADMIN_PORT}",
    f"http://localhost:{_UI_PORT}",
    f"http://0.0.0.0:{_UI_PORT}",
    f"http://localhost:{_BACKEND_PORT}",
    "http://localhost:5173",  # Vite dev server
    "http://localhost:3000",
]

RUNPOD_POD_ID = os.getenv("RUNPOD_POD_ID", "")
if RUNPOD_POD_ID:
    _STATIC_ORIGINS.extend([
        f"https://{RUNPOD_POD_ID}-{_ADMIN_PORT}.proxy.runpod.net",
        f"https://{RUNPOD_POD_ID}-{_UI_PORT}.proxy.runpod.net",
        f"https://{RUNPOD_POD_ID}-{_BACKEND_PORT}.proxy.runpod.net",
    ])

import re as _re
_RUNPOD_ORIGIN_RE = _re.compile(r'^https://[a-z0-9]+-\d+\.proxy\.runpod\.net$', _re.IGNORECASE)


@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    """
    Custom CORS middleware that correctly handles credentials + dynamic origins.
    The standard CORSMiddleware cannot use allow_credentials=True with allow_origins=["*"];
    this middleware echoes back the specific requesting origin when it is trusted.
    Trusted: static list OR any *.proxy.runpod.net origin (for RunPod deployments).
    """
    origin = request.headers.get("origin", "")

    def _is_trusted(o: str) -> bool:
        if not o:
            return False
        if o in _STATIC_ORIGINS:
            return True
        if _RUNPOD_ORIGIN_RE.match(o):
            return True
        return False

    trusted = _is_trusted(origin)

    # Pre-flight OPTIONS — respond immediately
    if request.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": origin if trusted else "",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Expose-Headers": "Content-Disposition, X-Slides-JSON",
            "Access-Control-Max-Age": "600",
        }
        from starlette.responses import Response as _Resp
        return _Resp(status_code=200, headers={k: v for k, v in headers.items() if v})

    response = await call_next(request)

    if trusted:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Expose-Headers"] = "Content-Disposition, X-Slides-JSON"
    else:
        # Non-browser or internal call — allow without credentials
        response.headers["Access-Control-Allow-Origin"] = "*"

    return response


# ── Register Routers ──
from api.routers import upload, chat, generate, vlm, drawing, sessions

app.include_router(upload.router,     prefix="/api/agent", tags=["Documents"])
app.include_router(chat.router,       prefix="/api/agent", tags=["Chat / Q&A"])
app.include_router(generate.router,   prefix="/api/agent", tags=["Generation"])
app.include_router(vlm.router,        prefix="/api/agent", tags=["VLM"])
app.include_router(drawing.router,    prefix="/api/agent", tags=["Drawing"])
app.include_router(sessions.router,   prefix="/api/agent", tags=["Sessions"])


# ── Health & Root ──
@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "AGRA Agent API",
        "version": "2.0.0",
        "status": "operational",
        "port": int(os.getenv("AGENT_API_PORT", "8005")),
        "capabilities": [
            "document_qa",
            "ppt_generation",
            "executive_summary",
            "knowledge_quiz",
        ],
    }


@app.get("/health", tags=["Health"])
async def health():
    from api.rag.vector_store import get_store
    store = get_store()
    try:
        count = store.collection_count()
        db_status = "connected"
    except Exception:
        count = 0
        db_status = "error"

    return {
        "status": "healthy",
        "service": "AGRA-Agent",
        "models": {
            "llm": "loaded",
            "embedder": "loaded",
            "reranker": "loaded",
        },
        "vector_db": db_status,
        "total_chunks": count,
    }


@app.get("/api/whoami", tags=["Auth"])
async def whoami(user: dict = Depends(get_current_user)):
    return {
        "authenticated": True,
        "username": user.get("sub"),
        "token_payload": user,
    }


# ── File Downloads ──
@app.get("/api/agent/download/{filename}", tags=["Downloads"])
async def download_file(
    filename: str,
    user: dict = Depends(get_current_user),
):
    """Download a generated file (PPT, DOCX, etc.)."""
    file_path = _OUTPUTS_DIR / filename
    if not file_path.exists():
        return JSONResponse(status_code=404, content={"detail": "File not found."})

    suffix = file_path.suffix.lower()
    media_types = {
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pdf": "application/pdf",
    }

    return FileResponse(
        path=str(file_path),
        media_type=media_types.get(suffix, "application/octet-stream"),
        filename=filename,
    )


# ── Original Document Download (local builtin + local chat uploads + backend proxy) ──
_KB_DIR = Path(__file__).resolve().parent.parent / "knowledge_base"
_CHAT_UPLOADS_DIR = _DATA_DIR / "uploads" / "chat"

_UUID_RE = __import__('re').compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    __import__('re').IGNORECASE
)


@app.get("/api/agent/download/doc/{doc_id:path}", tags=["Downloads"])
async def download_original_document(
    doc_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Download an original document.
    - builtin: prefix → serve directly from knowledge_base/
    - UUID doc_id   → serve from local agra_data/uploads/chat/ (chat-uploaded files)
    - integer id    → proxy to admin backend
    """
    # ── 1. Builtin knowledge-base documents ──
    if doc_id.startswith("builtin:"):
        filename = doc_id.split(":", 1)[1]
        filename = filename.replace("/", "").replace("\\", "").replace("..", "")
        local_path = _KB_DIR / filename
        if not local_path.exists() or not local_path.is_file():
            raise HTTPException(status_code=404, detail=f"Built-in document '{filename}' not found")
        suffix = local_path.suffix.lower()
        media_types = {
            ".txt": "text/plain",
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        return FileResponse(
            path=str(local_path),
            media_type=media_types.get(suffix, "application/octet-stream"),
            filename=filename,
        )

    # ── 2. Chat-uploaded documents (UUID doc_id) ──
    # Files saved by upload.py as: agra_data/uploads/chat/{doc_id}_{original_filename}
    if _UUID_RE.match(doc_id):
        if _CHAT_UPLOADS_DIR.exists():
            # Find any file whose name starts with this doc_id
            matches = list(_CHAT_UPLOADS_DIR.glob(f"{doc_id}_*"))
            if matches:
                local_path = matches[0]  # There will be exactly one per doc_id
                suffix = local_path.suffix.lower()
                media_types = {
                    ".pdf": "application/pdf",
                    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ".doc": "application/msword",
                    ".txt": "text/plain",
                    ".md": "text/markdown",
                    ".csv": "text/csv",
                    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                }
                # Reconstruct the original filename (strip UUID prefix)
                original_name = local_path.name[len(doc_id) + 1:]  # +1 for underscore
                return FileResponse(
                    path=str(local_path),
                    media_type=media_types.get(suffix, "application/octet-stream"),
                    filename=original_name or local_path.name,
                )
        raise HTTPException(
            status_code=404,
            detail=f"Document '{doc_id}' not found in local storage. It may have been deleted or not yet indexed.",
        )

    # ── 3. Admin-backend documents (integer id) ──
    token = request.query_params.get("token") or (
        request.headers.get("Authorization", "").replace("Bearer ", "")
    )
    if not token:
        raise HTTPException(status_code=401, detail="Token required")

    backend_url = f"{_ADMIN_BASE}/api/documents/{doc_id}/download"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                backend_url,
                headers={"Authorization": f"Bearer {token}"},
                follow_redirects=True,
            )
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Document not found on backend")
        if resp.status_code == 403:
            raise HTTPException(status_code=403, detail="Access denied — superadmin required on backend")
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Backend error: {e.response.text[:200]}",
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Backend unreachable: {e}")

    content_disposition = resp.headers.get("content-disposition", "")
    media_type = resp.headers.get("content-type", "application/octet-stream")

    return StreamingResponse(
        content=resp.iter_bytes(),
        media_type=media_type,
        headers={
            "Content-Disposition": content_disposition or f'attachment; filename="doc_{doc_id}.pdf"'
        },
    )


# ── Global Exception Handler ──
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if os.getenv("DEBUG") else "An unexpected error occurred.",
        },
    )


# ── Entry Point ──
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=int(os.getenv("AGENT_API_PORT", "8005")),
        reload=True,
        log_level="info",
    )
