"""
AGRA Session/Jobs Router
─────────────────────────
HTTP endpoints for the SessionManager. Lets the UI poll background
job status and list outstanding jobs for a chat session.

Endpoints:
  GET  /api/agent/sessions/{session_id}/jobs    → list jobs for session
  GET  /api/agent/jobs/{job_id}                 → get one job's state
  POST /api/agent/jobs/{job_id}/cancel          → cancel a running job
"""

from fastapi import APIRouter, Depends, HTTPException

from api.utils.auth_check import get_current_user
from api.session_manager import get_session_manager

router = APIRouter()


@router.get("/sessions/{session_id}/jobs")
async def list_session_jobs(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    mgr = get_session_manager()
    jobs = await mgr.list_by_session(session_id)
    return {
        "session_id": session_id,
        "jobs": [j.to_dict() for j in jobs],
    }


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    user: dict = Depends(get_current_user),
):
    mgr = get_session_manager()
    job = await mgr.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    user: dict = Depends(get_current_user),
):
    mgr = get_session_manager()
    ok = await mgr.cancel(job_id)
    if not ok:
        raise HTTPException(status_code=409, detail="Job not cancellable (not found or already finished)")
    return {"job_id": job_id, "status": "cancelling"}
