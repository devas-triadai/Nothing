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

_OUTPUTS_DIR = Path(__file__).resolve().parent.parent / "outputs"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: Load all models, init DBs and vector store.
    Shutdown: Release resources.
    """
    logger.info("╔══════════════════════════════════════════════════════════╗")
    logger.info("║   AGRA Phase 2 — Agent API starting on port 8001       ║")
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

    # ── 5. Load LLM ──
    from api.rag.llm import load_llm
    load_llm()
    logger.info("LLM (Gemma 4 31B-IT) loaded.")

    logger.info("━━━ All models loaded. Agent API ready. ━━━")

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

# ── CORS ──
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://0.0.0.0:3000",
    "http://localhost:7860",
    "http://0.0.0.0:7860",
    "http://localhost:8000",
]

RUNPOD_POD_ID = os.getenv("RUNPOD_POD_ID", "")
if RUNPOD_POD_ID:
    ALLOWED_ORIGINS.extend([
        f"https://{RUNPOD_POD_ID}-3000.proxy.runpod.net",
        f"https://{RUNPOD_POD_ID}-7860.proxy.runpod.net",
        f"https://{RUNPOD_POD_ID}-8000.proxy.runpod.net",
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Register Routers ──
from api.routers import upload, chat, generate, compliance

app.include_router(upload.router,     prefix="/api/agent", tags=["Documents"])
app.include_router(chat.router,       prefix="/api/agent", tags=["Chat / Q&A"])
app.include_router(generate.router,   prefix="/api/agent", tags=["Generation"])
app.include_router(compliance.router, prefix="/api/agent", tags=["Compliance"])


# ── Health & Root ──
@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "AGRA Agent API",
        "version": "2.0.0",
        "status": "operational",
        "port": 8001,
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
        port=8001,
        reload=True,
        log_level="info",
    )
