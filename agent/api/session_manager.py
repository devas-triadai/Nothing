"""
AGRA Session Manager
─────────────────────
Tracks long-running background jobs (PPT generation, compliance check,
bid comparison, ingestion) per chat session so the UI can poll status,
switch tabs without aborting work, and reconnect if the SSE stream
drops.

Design principles:
  • Single in-memory registry guarded by a single asyncio.Lock.
  • Each Job has: id, session_id, kind, status, progress, result, error.
  • Status transitions: queued → running → done | failed | cancelled.
  • Jobs auto-expire from the registry 30 minutes after terminal state
    to avoid memory bloat in long-lived processes.
  • All public functions are coroutine-safe.

This module DOES NOT depend on any FastAPI primitives so it can be
imported anywhere (routers, pipeline, generators).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("agra.session_mgr")

# ── Job lifecycle constants ──────────────────────────────────────────
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

_TERMINAL = {STATUS_DONE, STATUS_FAILED, STATUS_CANCELLED}
_TTL_SECONDS = 30 * 60  # purge terminal jobs after 30 min


# ── Job kinds (free-form strings; documented here for discoverability) ─
KIND_PPT = "ppt"
KIND_QUIZ = "quiz"
KIND_SUMMARY = "summary"
KIND_COMPLIANCE = "compliance"
KIND_BID_COMPARE = "bid_compare"
KIND_INGEST = "ingest"


@dataclass
class Job:
    """A unit of background work tied to a chat session."""

    id: str
    session_id: str
    kind: str
    status: str = STATUS_QUEUED
    progress: int = 0
    message: str = ""
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Internal — not serialized
    _task: Optional[asyncio.Task] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("_task", None)
        return d


class SessionManager:
    """In-memory registry of jobs keyed by job_id and indexed by session_id."""

    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._by_session: Dict[str, List[str]] = {}
        self._lock = asyncio.Lock()
        self._gc_task: Optional[asyncio.Task] = None

    # ── lifecycle ─────────────────────────────────────────────────────
    def start_gc(self) -> None:
        """Spawn the background garbage collector. Idempotent."""
        if self._gc_task is None or self._gc_task.done():
            try:
                loop = asyncio.get_event_loop()
                self._gc_task = loop.create_task(self._gc_loop())
                logger.info("SessionManager GC task started.")
            except RuntimeError:
                # No running loop yet — caller should retry on app startup
                logger.debug("No event loop; GC not started.")

    async def _gc_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(300)  # every 5 min
                await self._gc_terminal_jobs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("SessionManager GC error: %s", e)

    async def _gc_terminal_jobs(self) -> None:
        cutoff = time.time() - _TTL_SECONDS
        async with self._lock:
            stale = [
                jid for jid, j in self._jobs.items()
                if j.status in _TERMINAL
                and j.finished_at is not None
                and j.finished_at < cutoff
            ]
            for jid in stale:
                self._remove_unsafe(jid)
        if stale:
            logger.info("SessionManager GC purged %d terminal jobs.", len(stale))

    def _remove_unsafe(self, job_id: str) -> None:
        """Caller must hold self._lock."""
        job = self._jobs.pop(job_id, None)
        if not job:
            return
        sid_list = self._by_session.get(job.session_id, [])
        try:
            sid_list.remove(job_id)
        except ValueError:
            pass
        if not sid_list:
            self._by_session.pop(job.session_id, None)

    # ── job creation & runners ────────────────────────────────────────
    async def create_job(
        self,
        session_id: str,
        kind: str,
        coro_factory: Callable[["Job"], Awaitable[Dict[str, Any]]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Job:
        """
        Register a new job and schedule it. The coroutine factory receives
        the Job instance so it can call `update_progress` during execution.
        Returns the Job immediately (status=queued).
        """
        job = Job(
            id=str(uuid.uuid4()),
            session_id=session_id,
            kind=kind,
            metadata=metadata or {},
        )
        async with self._lock:
            self._jobs[job.id] = job
            self._by_session.setdefault(session_id, []).append(job.id)

        async def _runner() -> None:
            try:
                await self._set_status(job.id, STATUS_RUNNING, message="Started")
                result = await coro_factory(job)
                await self._mark_done(job.id, result)
            except asyncio.CancelledError:
                await self._set_status(job.id, STATUS_CANCELLED, message="Cancelled")
                raise
            except Exception as e:
                logger.exception("Job %s (%s) failed: %s", job.id, job.kind, e)
                await self._mark_failed(job.id, str(e))

        job._task = asyncio.create_task(_runner())
        return job

    async def update_progress(self, job_id: str, progress: int, message: str = "") -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.progress = max(0, min(100, int(progress)))
            if message:
                job.message = message
            job.updated_at = time.time()

    async def _set_status(self, job_id: str, status: str, message: str = "") -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.status = status
            if message:
                job.message = message
            job.updated_at = time.time()
            if status in _TERMINAL:
                job.finished_at = job.updated_at

    async def _mark_done(self, job_id: str, result: Dict[str, Any]) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.status = STATUS_DONE
            job.progress = 100
            job.result = result
            job.message = "Completed"
            job.updated_at = time.time()
            job.finished_at = job.updated_at

    async def _mark_failed(self, job_id: str, error: str) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.status = STATUS_FAILED
            job.error = error
            job.message = "Failed"
            job.updated_at = time.time()
            job.finished_at = job.updated_at

    # ── query API ─────────────────────────────────────────────────────
    async def get(self, job_id: str) -> Optional[Job]:
        async with self._lock:
            return self._jobs.get(job_id)

    async def list_by_session(self, session_id: str) -> List[Job]:
        async with self._lock:
            ids = list(self._by_session.get(session_id, []))
            return [self._jobs[i] for i in ids if i in self._jobs]

    async def cancel(self, job_id: str) -> bool:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status in _TERMINAL:
                return False
            task = job._task
        if task is not None:
            task.cancel()
        return True


# ── Module-level singleton ────────────────────────────────────────────
_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Lazy singleton. Safe to call from any context."""
    global _manager
    if _manager is None:
        _manager = SessionManager()
    return _manager
