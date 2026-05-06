"""
AGRA Phase 2 — Agent-Local Database Models
SQLAlchemy models for agent's own SQLite at agent/agent.db.
Tracks chat sessions, messages, and ingestion jobs.
"""

import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Column, String, Integer, Float, Text, Boolean, DateTime,
    ForeignKey, create_engine, JSON,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

import os

_DATA_DIR = Path(os.environ.get("AGRA_DATA_DIR", "/workspace/agra_data"))
if not _DATA_DIR.exists():
    _DATA_DIR = Path(__file__).resolve().parent.parent.parent / "agra_data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_DB_PATH = _DATA_DIR / "agent.db"
_DB_URL = f"sqlite:///{_DB_PATH}"

engine = create_engine(_DB_URL, echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def get_agent_db():
    """FastAPI dependency — yields a DB session and ensures it's closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _gen_uuid() -> str:
    return str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════════
#  Chat Sessions
# ═══════════════════════════════════════════════════════════════

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True, default=_gen_uuid)
    user_id = Column(Integer, nullable=False)
    username = Column(String(100), nullable=True)
    title = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String(20), nullable=False)  # "user", "assistant", "system"
    content = Column(Text, nullable=False)
    sources = Column(JSON, nullable=True)       # Citation data for assistant messages
    token_count = Column(Integer, nullable=True)
    response_time_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")


# ═══════════════════════════════════════════════════════════════
#  Ingestion Jobs
# ═══════════════════════════════════════════════════════════════

class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id = Column(String(36), primary_key=True, default=_gen_uuid)
    doc_id = Column(String(36), nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    file_type = Column(String(20), nullable=True)
    uploaded_by = Column(Integer, nullable=True)

    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    current_stage = Column(String(30), nullable=True)  # ocr, chunking, embedding, storing
    progress = Column(Integer, default=0)

    page_count = Column(Integer, nullable=True)
    chunk_count = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════
#  Background Jobs (VLM / Drawing Analysis)
# ═══════════════════════════════════════════════════════════════

class AsyncJob(Base):
    __tablename__ = "async_jobs"

    id = Column(String(36), primary_key=True, default=_gen_uuid)
    job_type = Column(String(50), nullable=False)  # e.g., "drawing_extraction", "drawing_compare"
    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    progress = Column(Integer, default=0)
    
    input_data = Column(JSON, nullable=True)
    result_data = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


# ═══════════════════════════════════════════════════════════════
#  Create all tables
# ═══════════════════════════════════════════════════════════════

def init_agent_db():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
