from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
import uvicorn
import asyncio
import os
import logging
from datetime import datetime, timedelta

from app.database import engine, Base, SessionLocal
from app.routers import auth, users, usage, audit, dashboard, documents, agents, reports, settings, genealogy
from app.routers.compliance import router as compliance_router
from app.routers.audit import router as audit_logs_router
from app.seed import seed_superadmin
from app.utils.security import decode_access_token


def _run_migrations():
    """Add columns that were added to models after the SQLite DB was first created."""
    import sqlalchemy as sa
    from sqlalchemy import inspect
    from app.models.models import DocumentFolder, ComplianceRun, ClauseResult

    inspector = inspect(engine)
    doc_columns = {c["name"] for c in inspector.get_columns("documents")}

    with engine.connect() as conn:
        # ── Add missing columns to `documents` ──
        for col_name, col_type in (
            ("ocr_status", sa.String(20)),
            ("expiry_date", sa.DateTime()),
            ("full_text", sa.Text()),
            ("folder_id", sa.Integer()),
            ("doc_type", sa.String(50)),
        ):
            if col_name not in doc_columns:
                conn.execute(sa.text(f"ALTER TABLE documents ADD COLUMN {col_name} {col_type.compile(dialect=engine.dialect)}"))
                print(f"  [migrate] Added column `documents.{col_name}`")

        # ── Create `document_folders` table if missing ──
        if "document_folders" not in inspector.get_table_names():
            DocumentFolder.__table__.create(engine)
            print("  [migrate] Created table `document_folders`")

        # ── Drop old compliance tables, create new ones ──
        table_names = inspector.get_table_names()

        # Drop old tables (rebuild spec replaces them)
        for old_table in ("clause_scores", "compliance_evaluations"):
            if old_table in table_names:
                conn.execute(sa.text(f"DROP TABLE IF EXISTS {old_table}"))
                print(f"  [migrate] Dropped old table `{old_table}`")

        # Create new compliance tables if they don't exist
        if "compliance_runs" not in table_names:
            ComplianceRun.__table__.create(engine)
            print("  [migrate] Created table `compliance_runs`")
        else:
            _migrate_missing_columns(conn, inspector, "compliance_runs", ComplianceRun)

        if "clause_results" not in table_names:
            ClauseResult.__table__.create(engine)
            print("  [migrate] Created table `clause_results`")
        else:
            _migrate_missing_columns(conn, inspector, "clause_results", ClauseResult)

        conn.commit()

    # ── Reset stuck compliance runs ──
    _reset_stuck_runs()


def _reset_stuck_runs():
    """Reset any runs stuck in a non-terminal status on startup."""
    try:
        from app.models.models import ComplianceRun
        db = SessionLocal()
        stuck = db.query(ComplianceRun).filter(
            ComplianceRun.status.in_(["running", "queued", "ingesting", "parsing_clauses", "evaluating"])
        ).all()
        for run in stuck:
            run.status = "failed"
            logger = logging.getLogger("agra.backend.migrate")
            logger.warning("Reset stuck compliance run #%s (was '%s')", run.id, run.status)
        if stuck:
            db.commit()
        db.close()
    except Exception as exc:
        logger = logging.getLogger("agra.backend.migrate")
        logger.warning("Could not reset stuck runs: %s", exc)


def _migrate_missing_columns(conn, inspector, table_name: str, model_class):
    """Add any columns that exist in the model but are missing from the DB table."""
    import sqlalchemy as sa
    existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
    for col in model_class.__table__.columns:
        if col.name not in existing_cols and not col.primary_key:
            col_type = col.type
            try:
                conn.execute(sa.text(
                    f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type.compile(dialect=engine.dialect)}"
                ))
                print(f"  [migrate] Added column `{table_name}.{col.name}`")
            except Exception as exc:
                print(f"  [migrate] WARNING: Could not add `{table_name}.{col.name}`: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _run_migrations()
    seed_superadmin()
    
    # ── Log Retention Enforcement (Background) ──
    async def enforce_log_retention():
        while True:
            try:
                db = SessionLocal()
                from app.models.models import AuditLog, UsageLog
                cutoff = datetime.utcnow() - timedelta(days=90)
                deleted_audit = db.query(AuditLog).filter(AuditLog.created_at < cutoff).delete()
                deleted_usage = db.query(UsageLog).filter(UsageLog.created_at < cutoff).delete()
                db.commit()
                db.close()
                logging.getLogger("agra.backend").info(f"Log Retention Policy enforced: Deleted {deleted_audit} AuditLogs, {deleted_usage} UsageLogs older than 90 days.")
            except Exception as e:
                logging.getLogger("agra.backend").error(f"Failed to enforce log retention: {e}")
            await asyncio.sleep(86400)  # run once a day

    asyncio.create_task(enforce_log_retention())
    yield


app = FastAPI(
    title="AGRA Super Admin API",
    description="AGRA - Air-Gapped Retrieval Agent | Indian Coast Guard HQ",
    version="1.0.0",
    lifespan=lifespan
)

# ── Security: TLS Enforcement (Phase 7) ──
if os.getenv("ENFORCE_TLS", "false").lower() == "true":
    app.add_middleware(HTTPSRedirectMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://0.0.0.0:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Audit Logging Middleware ----------
class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Automatically logs every non-GET request to the AuditLog table."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Only log non-GET requests to /api/* paths
        if request.method == "GET" or not request.url.path.startswith("/api/"):
            return response

        # Extract user_id from JWT if present
        user_id = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = decode_access_token(token)
            if payload:
                username = payload.get("sub")
                if username:
                    db = SessionLocal()
                    try:
                        from app.models.models import User, AuditLog
                        user = db.query(User).filter(User.username == username).first()
                        if user:
                            user_id = user.id

                        # Determine resource type from path
                        path_parts = request.url.path.strip("/").split("/")
                        resource_type = path_parts[1] if len(path_parts) > 1 else "unknown"

                        action = f"{request.method} {request.url.path}"
                        status = "success" if response.status_code < 400 else "failed"
                        ip_address = request.client.host if request.client else "unknown"

                        audit_entry = AuditLog(
                            user_id=user_id,
                            action=action,
                            resource_type=resource_type,
                            ip_address=ip_address,
                            status=status
                        )
                        db.add(audit_entry)
                        db.commit()
                    except Exception:
                        db.rollback()
                    finally:
                        db.close()

        return response


app.add_middleware(AuditLoggingMiddleware)


# ---------- Router Registration ----------
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(usage.router, prefix="/api/usage", tags=["Usage"])
app.include_router(usage.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(audit_logs_router, prefix="/api/audit-logs", tags=["Audit Logs"])
app.include_router(audit.router, prefix="/api/audit", tags=["Audit Logs"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(agents.router, prefix="/api/agents", tags=["Agents"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])
app.include_router(genealogy.router, prefix="/api/genealogy", tags=["Genealogy"])
app.include_router(compliance_router, prefix="/api/compliance", tags=["Compliance"])



@app.get("/")
def root():
    return {"message": "AGRA Super Admin API is running", "status": "operational"}


@app.get("/health")
def health():
    return {"status": "healthy", "service": "AGRA-API"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
