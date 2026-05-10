"""
AGRA Phase 2 — Agent API (port 8001)
Air-Gapped Retrieval Agent for Indian Coast Guard HQ

Routes:
  /api/agent/upload        — Document upload & management
  /api/agent/chat          — Conversational Q&A (SSE)
  /api/agent/generate/*    — PPT, Summary, Quiz generation
  /api/agent/compliance/*  — Compliance check engine
  /api/agent/download/*    — File downloads for generated content
"""

import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse

from api.utils.auth_check import get_current_user

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


    yield

    logger.info("Agent API shutting down — releasing resources.")


# ── FastAPI App ──
app = FastAPI(
    title="AGRA Agent API",
    description=(
        "Air-Gapped Retrieval Agent — Document Q&A, PPT generation, "
        "summary, quiz, and compliance analysis. "
        "All processing runs locally — zero internet access."
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ── (ports from env vars)
_UI_PORT = os.getenv("AGENT_UI_PORT", "7860")
_ADMIN_PORT = os.getenv("ADMIN_PORT", "3000")
_BACKEND_PORT = os.getenv("BACKEND_PORT", "8000")

ALLOWED_ORIGINS = [
    f"http://localhost:{_ADMIN_PORT}",
    f"http://0.0.0.0:{_ADMIN_PORT}",
    f"http://localhost:{_UI_PORT}",
    f"http://0.0.0.0:{_UI_PORT}",
    f"http://localhost:{_BACKEND_PORT}",
]

RUNPOD_POD_ID = os.getenv("RUNPOD_POD_ID", "")
if RUNPOD_POD_ID:
    ALLOWED_ORIGINS.extend([
        f"https://{RUNPOD_POD_ID}-{_ADMIN_PORT}.proxy.runpod.net",
        f"https://{RUNPOD_POD_ID}-{_UI_PORT}.proxy.runpod.net",
        f"https://{RUNPOD_POD_ID}-{_BACKEND_PORT}.proxy.runpod.net",
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Slides-JSON"],
)


# ── Register Routers ──
from api.routers import upload, chat, generate, compliance, vlm, drawing, compare

app.include_router(upload.router,     prefix="/api/agent", tags=["Documents"])
app.include_router(chat.router,       prefix="/api/agent", tags=["Chat / Q&A"])
app.include_router(generate.router,   prefix="/api/agent", tags=["Generation"])
app.include_router(compliance.router, prefix="/api/agent", tags=["Compliance"])
app.include_router(vlm.router,        prefix="/api/agent", tags=["VLM"])
app.include_router(drawing.router,    prefix="/api/agent", tags=["Drawing"])
app.include_router(compare.router,    prefix="/api/agent", tags=["Compare"])


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
            "compliance_check",
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
