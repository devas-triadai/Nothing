from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from pathlib import Path

# ── Persistent data directory ──
# On RunPod: /workspace/agra_data/  (survives pod restarts)
# On dev:    ./agra_data/           (local fallback)
_WORKSPACE = Path(os.getenv("AGRA_DATA_DIR", "/workspace/agra_data"))
if not _WORKSPACE.exists():
    # Fallback for local development (Windows / non-RunPod)
    _WORKSPACE = Path(__file__).resolve().parent.parent / "agra_data"
_WORKSPACE.mkdir(parents=True, exist_ok=True)

_DB_PATH = _WORKSPACE / "agra.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_DB_PATH}")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

