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
from app.routers import auth, users, usage, audit, dashboard, documents, agents, reports, settings
from app.routers.audit import router as audit_logs_router
from app.seed import seed_superadmin
from app.utils.security import decode_access_token


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
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


@app.get("/")
def root():
    return {"message": "AGRA Super Admin API is running", "status": "operational"}


@app.get("/health")
def health():
    return {"status": "healthy", "service": "AGRA-API"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
