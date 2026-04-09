from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn

from app.database import engine, Base
from app.routers import auth, users, usage, audit, dashboard, documents, agents, reports, settings
from app.routers.audit import router as audit_logs_router
from app.seed import seed_superadmin

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_superadmin()
    yield

app = FastAPI(
    title="AGRA Super Admin API",
    description="AGRA - Air-Gapped Retrieval Agent | Indian Coast Guard HQ",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://0.0.0.0:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(usage.router, prefix="/api/usage", tags=["Usage"])
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
