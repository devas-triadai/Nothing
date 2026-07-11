"""
AGRA Backend — Compliance Run Router (Rebuild Spec)
Endpoints:
  POST   /api/compliance/runs              — Create run (multipart: files + reference name + standards)
  GET    /api/compliance/runs               — List runs
  GET    /api/compliance/runs/{id}          — Get run with clause results
  GET    /api/compliance/runs/{id}/status   — Get progress
  GET    /api/compliance/runs/{id}/result   — Get full JSON result
  GET    /api/compliance/runs/{id}/report   — Stream .docx report
  GET    /api/compliance/runs/{id}/zip-contents — List files extracted from vendor commercial ZIP
  PATCH  /api/compliance/runs/{id}/toggle-file  — Enable/disable a file from ZIP evaluation
  PATCH  /api/compliance/runs/{id}/progress — Internal: agent updates progress
  PATCH  /api/compliance/runs/{id}/complete — Internal: agent stores result
"""

import json
import logging
import os
import re
import shutil
import threading
import uuid
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import ComplianceRun, ClauseResult, User
from app.routers.auth import get_current_user
from app.utils.security import create_access_token
from sqlalchemy.orm.attributes import flag_modified

logger = logging.getLogger("agra.backend.compliance")

_AGENT_BASE = os.getenv("AGENT_BASE_URL", "http://localhost:8005")
_DATA_DIR = Path(os.environ.get("AGRA_DATA_DIR", "/workspace/agra_data"))
if not _DATA_DIR.exists():
    _DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_COMPLIANCE_DIR = _DATA_DIR / "compliance"
_COMPLIANCE_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter()


def _get_service_token() -> str:
    return create_access_token(
        data={"sub": "backend_service", "role": "service"},
        expires_delta=timedelta(minutes=30),
    )


def _agent_post(path: str, payload: dict, timeout: int = 300):
    url = f"{_AGENT_BASE}/api/agent/compliance/{path.lstrip('/')}"
    token = _get_service_token()
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    if resp.status_code >= 400:
        detail = resp.text[:500]
        logger.error("Agent API error %s -> %s: %s", url, resp.status_code, detail)
        raise HTTPException(status_code=502, detail=f"Agent API error: {resp.status_code} {detail}")
    return resp.json()


def _agent_get(path: str, timeout: int = 30):
    url = f"{_AGENT_BASE}/api/agent/compliance/{path.lstrip('/')}"
    token = _get_service_token()
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.get(url, headers=headers, timeout=timeout)
    if resp.status_code >= 400:
        detail = resp.text[:500]
        raise HTTPException(status_code=502, detail=f"Agent API error: {resp.status_code} {detail}")
    return resp.json()


def _sanitize_filename(name: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|]', '_', name)
    return safe[:100].strip()


# ── Pydantic Response Schemas ──

class ClauseResultResponse(BaseModel):
    id: int
    clause_id: str
    source_file: str
    source_doc_id: Optional[str] = None
    source_file_detail: Optional[str] = None
    requirement_text: Optional[str] = None
    verdict: Optional[str] = None
    finding: Optional[str] = None
    house_rule_flag: Optional[dict] = None
    recommendation: Optional[str] = None
    severity: Optional[str] = None
    citations: Optional[list] = None
    contradictions: Optional[list] = None
    is_missing: bool = False
    historical_notes: Optional[list] = None


class RunResponse(BaseModel):
    id: int
    reference_name: str
    status: str
    progress: Optional[dict] = None
    overall_score: Optional[float] = None
    compliant_count: int = 0
    partial_count: int = 0
    non_compliant_count: int = 0
    unverifiable_count: int = 0
    total_clauses: int = 0
    recommendation: Optional[str] = None
    missing_clause_count: int = 0
    contradiction_count: int = 0
    house_rule_violation_count: int = 0
    vendor_commercial_files: Optional[list] = None
    created_at: str
    updated_at: str
    clauses: List[ClauseResultResponse] = []

    @classmethod
    def from_orm(cls, run: ComplianceRun, include_clauses: bool = False):
        clauses = []
        if include_clauses and run.clauses:
            for cr in run.clauses:
                clauses.append(ClauseResultResponse(
                    id=cr.id,
                    clause_id=cr.clause_id,
                    source_file=cr.source_file,
                    source_doc_id=cr.source_doc_id,
                    source_file_detail=cr.source_file_detail,
                    requirement_text=cr.requirement_text,
                    verdict=cr.verdict,
                    finding=cr.finding,
                    house_rule_flag=cr.house_rule_flag,
                    recommendation=cr.recommendation,
                    severity=cr.severity,
                    citations=cr.citations,
                    contradictions=cr.contradictions,
                    is_missing=cr.is_missing or False,
                    historical_notes=cr.historical_notes,
                ))

        result = run.result_json or {}
        return cls(
            id=run.id,
            reference_name=run.reference_name,
            status=run.status or "queued",
            progress=run.progress,
            overall_score=run.overall_score,
            compliant_count=run.compliant_count or 0,
            partial_count=run.partial_count or 0,
            non_compliant_count=run.non_compliant_count or 0,
            unverifiable_count=run.unverifiable_count or 0,
            total_clauses=run.total_clauses or 0,
            recommendation=run.recommendation,
            missing_clause_count=result.get("missing_clause_count", 0) if isinstance(result, dict) else 0,
            contradiction_count=result.get("contradiction_count", 0) if isinstance(result, dict) else 0,
            house_rule_violation_count=result.get("house_rule_violation_count", 0) if isinstance(result, dict) else 0,
            vendor_commercial_files=run.vendor_commercial_files,
            created_at=run.created_at.isoformat() if run.created_at else "",
            updated_at=run.updated_at.isoformat() if run.updated_at else "",
            clauses=clauses,
        )


# ── Constants ──

MAX_ZIP_SIZE_MB = 50
MAX_ZIP_SIZE_BYTES = MAX_ZIP_SIZE_MB * 1024 * 1024

ALLOWED_VENDOR_ZIP_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".txt", ".xlsx", ".xls",
    ".pptx", ".ppt", ".csv", ".rtf", ".odt",
}

# ── Create Compliance Run ──

@router.post("/runs", response_model=RunResponse)
async def create_run(
    reference_name: str = Form(...),
    selected_standards: str = Form("[]"),
    sotr_commercial: Optional[UploadFile] = File(None),
    sotr_technical: Optional[UploadFile] = File(None),
    vendor_commercial: Optional[UploadFile] = File(None),
    vendor_dpr: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reference_name = reference_name.strip()
    if not reference_name:
        raise HTTPException(status_code=400, detail="reference_name is required")

    standards_list = []
    try:
        parsed = json.loads(selected_standards)
        if isinstance(parsed, list):
            standards_list = parsed
    except (json.JSONDecodeError, TypeError):
        pass

    # Validate pairing: vendor_commercial can be ZIP or single file
    # For validation, treat any vendor_commercial upload as "present"
    has_vendor_com = vendor_commercial is not None
    has_p1 = sotr_commercial is not None and has_vendor_com
    has_p2 = sotr_technical is not None and vendor_dpr is not None
    if not has_p1 and not has_p2:
        orphan1 = (sotr_commercial is None) != has_vendor_com
        orphan2 = (sotr_technical is None) != (vendor_dpr is None)
        if orphan1 or orphan2:
            raise HTTPException(status_code=400, detail="SOTR Commercial & Vendor Commercial must be submitted together; SOTR Technical & Vendor DPR must be submitted together")
        raise HTTPException(status_code=400, detail="Must upload SOTR Commercial + Vendor Commercial (ZIP), or SOTR Technical + Vendor DPR, or all files")

    # Save files to compliance temp directory
    run_uuid = str(uuid.uuid4())
    run_dir = _COMPLIANCE_DIR / run_uuid
    run_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = {}
    vendor_commercial_files = []
    vendor_commercial_zip_path = None

    # Save SOTR Commercial
    if sotr_commercial:
        if not sotr_commercial.filename:
            raise HTTPException(status_code=400, detail="Missing file: sotr_commercial")
        ext = Path(sotr_commercial.filename).suffix or ""
        dest = run_dir / f"sotr_commercial{ext}"
        content = await sotr_commercial.read()
        dest.write_bytes(content)
        saved_paths["sotr_commercial"] = str(dest)

    # Save SOTR Technical
    if sotr_technical:
        if not sotr_technical.filename:
            raise HTTPException(status_code=400, detail="Missing file: sotr_technical")
        ext = Path(sotr_technical.filename).suffix or ""
        dest = run_dir / f"sotr_technical{ext}"
        content = await sotr_technical.read()
        dest.write_bytes(content)
        saved_paths["sotr_technical"] = str(dest)

    # Save Vendor DPR
    if vendor_dpr:
        if not vendor_dpr.filename:
            raise HTTPException(status_code=400, detail="Missing file: vendor_dpr")
        ext = Path(vendor_dpr.filename).suffix or ""
        dest = run_dir / f"vendor_dpr{ext}"
        content = await vendor_dpr.read()
        dest.write_bytes(content)
        saved_paths["vendor_dpr"] = str(dest)

    # Save + Extract Vendor Commercial (ZIP or single file)
    if vendor_commercial:
        if not vendor_commercial.filename:
            raise HTTPException(status_code=400, detail="Missing file: vendor_commercial")

        vc_content = await vendor_commercial.read()
        vc_filename = vendor_commercial.filename
        vc_ext = Path(vc_filename).suffix.lower()

        if vc_ext == ".zip":
            # ── ZIP path: validate size, extract, list files ──
            if len(vc_content) > MAX_ZIP_SIZE_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail=f"ZIP file exceeds {MAX_ZIP_SIZE_MB}MB limit ({len(vc_content) / (1024*1024):.1f}MB)"
                )

            zip_path = run_dir / "vendor_commercial.zip"
            zip_path.write_bytes(vc_content)
            vendor_commercial_zip_path = str(zip_path)

            # Extract ZIP
            extract_dir = run_dir / "vendor_commercial_extracted"
            extract_dir.mkdir(parents=True, exist_ok=True)

            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    # Check for nested ZIPs
                    for info in zf.infolist():
                        if info.filename.lower().endswith('.zip'):
                            raise HTTPException(status_code=400, detail="Nested ZIP files are not supported")

                    zf.extractall(extract_dir)
            except zipfile.BadZipFile:
                raise HTTPException(status_code=400, detail="Invalid or corrupted ZIP file")
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to extract ZIP: {str(e)}")

            # List extracted files
            for f_path in sorted(extract_dir.rglob("*")):
                if f_path.is_file():
                    f_ext = f_path.suffix.lower()
                    if f_ext in ALLOWED_VENDOR_ZIP_EXTENSIONS:
                        rel_path = f_path.relative_to(extract_dir)
                        file_info = {
                            "path": str(f_path),
                            "filename": str(rel_path),
                            "size": f_path.stat().st_size,
                            "selected": True,
                        }
                        vendor_commercial_files.append(file_info)

            if not vendor_commercial_files:
                raise HTTPException(status_code=400, detail="ZIP contains no supported files (PDF, DOCX, XLSX, TXT, etc.)")

            # Store first file as the primary vendor_commercial path for backward compat
            saved_paths["vendor_commercial"] = vendor_commercial_files[0]["path"]

        else:
            # ── Single file path (backward compatible) ──
            dest = run_dir / f"vendor_commercial{vc_ext}"
            dest.write_bytes(vc_content)
            saved_paths["vendor_commercial"] = str(dest)
            vendor_commercial_files = [{
                "path": str(dest),
                "filename": vc_filename,
                "size": len(vc_content),
                "selected": True,
            }]

    # Create DB record
    run = ComplianceRun(
        created_by=current_user.id,
        reference_name=reference_name,
        status="queued",
        progress={"stage": "queued", "current": 0, "total": 0, "message": "Run queued"},
        selected_standards=standards_list,
        vendor_commercial_zip_path=vendor_commercial_zip_path,
        vendor_commercial_files=vendor_commercial_files if vendor_commercial_files else None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Start background ingestion + pipeline
    def _background():
        try:
            _run_pipeline(run.id, saved_paths, standards_list, reference_name)
        except Exception as e:
            logger.exception("Pipeline failed for run %s: %s", run.id, e)
            try:
                db2 = next(get_db())
                db_run = db2.query(ComplianceRun).filter(ComplianceRun.id == run.id).first()
                if db_run:
                    db_run.status = "failed"
                    db_run.progress = {"stage": "failed", "current": 0, "total": 0, "message": str(e)}
                    db2.commit()
                db2.close()
            except Exception:
                pass

    thread = threading.Thread(target=_background, daemon=True)
    thread.start()

    return RunResponse.from_orm(run)


def _run_pipeline(run_id: int, saved_paths: dict, standards_list: list, reference_name: str):
    """Background task: ingest files via agent, run pipeline, store results."""
    db = None
    try:
        db = next(get_db())
        run = db.query(ComplianceRun).filter(ComplianceRun.id == run_id).first()
        if not run:
            return

        # Collect vendor commercial file paths (may be multiple from ZIP)
        vendor_com_files = []
        if run.vendor_commercial_files:
            for f_info in run.vendor_commercial_files:
                if f_info.get("selected", True) and f_info.get("path"):
                    vendor_com_files.append(f_info["path"])
        elif saved_paths.get("vendor_commercial"):
            vendor_com_files = [saved_paths["vendor_commercial"]]

        file_count = len(saved_paths) + max(0, len(vendor_com_files) - 1)  # -1 because first is already in saved_paths
        run.status = "ingesting"
        run.progress = {"stage": "ingesting", "current": 0, "total": file_count, "message": "Ingesting files..."}
        db.commit()

        # Step 1: Ingest files via agent
        # Send both old field (for backward compat) and new field (for multi-file ZIP)
        ingest_payload = IngestBundleRequest(
            sotr_commercial_path=saved_paths.get("sotr_commercial", ""),
            sotr_technical_path=saved_paths.get("sotr_technical", ""),
            vendor_commercial_paths=vendor_com_files,
            vendor_dpr_path=saved_paths.get("vendor_dpr", ""),
            run_id=run_id,
        ).model_dump()
        # Add backward-compat field for agent
        ingest_payload["vendor_commercial_path"] = vendor_com_files[0] if vendor_com_files else ""
        ingest_resp = _agent_post("/ingest-bundle", ingest_payload)

        run.doc_id_sotr_com = ingest_resp.get("doc_id_sotr_com")
        run.doc_id_sotr_tech = ingest_resp.get("doc_id_sotr_tech")
        run.doc_id_vendor_com = ingest_resp.get("doc_id_vendor_com")
        run.doc_id_vendor_dpr = ingest_resp.get("doc_id_vendor_dpr")
        # Store additional vendor commercial doc IDs (from ZIP)
        run.vendor_commercial_doc_ids = ingest_resp.get("vendor_commercial_doc_ids")
        run.status = "parsing_clauses"
        run.progress = {"stage": "parsing_clauses", "current": 0, "total": 0, "message": "Parsing clauses..."}
        db.commit()

        # Step 2: Run pipeline
        run.status = "evaluating"
        run.progress = {"stage": "evaluating", "current": 0, "total": 0, "message": "Starting evaluation..."}
        db.commit()

        _agent_post("/run-pipeline", RunPipelineRequest(
            run_id=run_id,
            doc_id_sotr_com=run.doc_id_sotr_com or "",
            doc_id_sotr_tech=run.doc_id_sotr_tech or "",
            doc_id_vendor_com=run.doc_id_vendor_com or "",
            doc_id_vendor_com_others=ingest_resp.get("vendor_commercial_doc_ids") or [],
            doc_id_vendor_dpr=run.doc_id_vendor_dpr or "",
            selected_standards=standards_list,
            reference_name=reference_name,
        ).model_dump())

        # Pipeline runs async on agent — poll DB until agent's PATCH /complete writes results
        import time
        max_wait = 1800
        waited = 0
        log_interval = 60
        next_log = log_interval
        while waited < max_wait:
            time.sleep(3)
            waited += 3
            try:
                poll_db = next(get_db())
                poll_run = poll_db.query(ComplianceRun).filter(ComplianceRun.id == run_id).first()
                poll_status = poll_run.status if poll_run else None
                poll_db.close()
                if poll_status == "complete":
                    break
                if poll_status == "failed":
                    return
                if waited >= next_log:
                    logger.info("Pipeline run %s: still running after %ds (max %ds)", run_id, waited, max_wait)
                    next_log += log_interval
            except Exception:
                pass
        else:
            run.status = "failed"
            run.progress = {"stage": "failed", "current": 0, "total": 0, "message": "Pipeline timed out"}
            db.commit()
            return

        db.refresh(run)

    except Exception as e:
        logger.exception("Pipeline error for run %s: %s", run_id, e)
        if db is not None:
            try:
                run = db.query(ComplianceRun).filter(ComplianceRun.id == run_id).first()
                if run:
                    run.status = "failed"
                    run.progress = {"stage": "failed", "current": 0, "total": 0, "message": str(e)}
                    db.commit()
            except Exception:
                pass
    finally:
        if db is not None:
            db.close()
        # Clean up temp files
        run_dir = saved_paths.get("sotr_commercial", "")
        if run_dir:
            parent = Path(run_dir).parent
            if parent.exists():
                shutil.rmtree(parent, ignore_errors=True)


def _store_results_in_db(run: ComplianceRun, agent_result: dict, db: Session):
    from app.models.models import ClauseResult

    clauses_data = agent_result.get("clauses", [])
    run.total_clauses = agent_result.get("total_clauses", len(clauses_data))
    run.compliant_count = agent_result.get("compliant_count", 0)
    run.partial_count = agent_result.get("partial_count", 0)
    run.non_compliant_count = agent_result.get("non_compliant_count", 0)
    run.unverifiable_count = agent_result.get("unverifiable_count", 0)
    run.overall_score = agent_result.get("overall_score", 0.0)
    run.recommendation = agent_result.get("recommendation")
    run.result_json = agent_result
    run.report_docx_path = agent_result.get("report_path") or run.report_docx_path
    run.status = "complete"
    run.progress = {"stage": "complete", "current": 0, "total": 0, "message": "Evaluation complete"}

    # Delete old clause results if any
    db.query(ClauseResult).filter(ClauseResult.run_id == run.id).delete(synchronize_session='fetch')

    for cd in clauses_data:
        cr = ClauseResult(
            run_id=run.id,
            clause_id=cd.get("clause_id", ""),
            source_file=cd.get("source_file", ""),
            source_doc_id=cd.get("source_doc_id", ""),
            source_file_detail=cd.get("source_file_detail"),
            requirement_text=cd.get("requirement_text", ""),
            applicable_standards=cd.get("applicable_standards"),
            technical_parameters=cd.get("technical_parameters"),
            acceptance_criterion=cd.get("acceptance_criterion", ""),
            verdict=cd.get("verdict"),
            finding=cd.get("finding", ""),
            house_rule_flag=cd.get("house_rule_flag"),
            recommendation=cd.get("recommendation"),
            severity=cd.get("severity"),
            citations=cd.get("citations"),
            contradictions=cd.get("contradictions"),
            is_missing=cd.get("is_missing", False),
            historical_notes=cd.get("historical_notes"),
        )
        db.add(cr)

    db.commit()
    db.refresh(run)

    logger.info(
        "Run %s complete: %d clauses, score=%.1f%%, rec=%s",
        run.id, run.total_clauses, run.overall_score or 0, run.recommendation
    )


# ── List Runs ──

@router.get("/runs", response_model=List[RunResponse])
def list_runs(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    runs = (
        db.query(ComplianceRun)
        .order_by(ComplianceRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return [RunResponse.from_orm(r) for r in runs]


# ── Get Run ──

@router.get("/runs/{run_id}", response_model=RunResponse)
def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = db.query(ComplianceRun).filter(ComplianceRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunResponse.from_orm(run, include_clauses=True)


# ── Get Status ──

@router.get("/runs/{run_id}/status")
def get_run_status(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = db.query(ComplianceRun).filter(ComplianceRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "status": run.status,
        "progress": run.progress or {"stage": run.status, "current": 0, "total": 0, "message": ""},
    }


# ── Get Result ──

@router.get("/runs/{run_id}/result")
def get_run_result(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = db.query(ComplianceRun).filter(ComplianceRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run.result_json or {}


# ── Download Report ──

@router.get("/runs/{run_id}/report")
def download_report(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = db.query(ComplianceRun).filter(ComplianceRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Prefer stored path from agent, then fall back to constructing it
    report_path = None
    if run.report_docx_path:
        p = Path(run.report_docx_path)
        if p.exists():
            report_path = p
    if not report_path:
        safe_name = _sanitize_filename(run.reference_name) or "compliance_report"
        filename = f"{safe_name}_Compliance_Report.docx"
        report_path = _DATA_DIR / "outputs" / filename
    else:
        filename = Path(report_path).name

    if not report_path or not report_path.exists():
        raise HTTPException(status_code=404, detail="Report file not found. Run may still be in progress.")

    return FileResponse(
        path=str(report_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# ── Get ZIP Contents ──

@router.get("/runs/{run_id}/zip-contents")
def get_zip_contents(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return list of files extracted from the vendor commercial ZIP."""
    run = db.query(ComplianceRun).filter(ComplianceRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    files = run.vendor_commercial_files or []
    has_zip = run.vendor_commercial_zip_path is not None

    return {
        "run_id": run.id,
        "has_zip": has_zip,
        "zip_path": run.vendor_commercial_zip_path,
        "files": files,
        "total_files": len(files),
        "selected_count": sum(1 for f in files if f.get("selected", True)),
    }


# ── Toggle File Selection ──

class ToggleFileRequest(BaseModel):
    filename: str
    selected: bool


@router.patch("/runs/{run_id}/toggle-file")
def toggle_file(
    run_id: int,
    body: ToggleFileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Enable or disable a file from the vendor commercial ZIP evaluation."""
    run = db.query(ComplianceRun).filter(ComplianceRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if not run.vendor_commercial_files:
        raise HTTPException(status_code=400, detail="No vendor commercial files found for this run")

    updated = False
    for f_info in run.vendor_commercial_files:
        if f_info.get("filename") == body.filename:
            f_info["selected"] = body.selected
            updated = True
            break

    if not updated:
        raise HTTPException(status_code=404, detail=f"File '{body.filename}' not found in ZIP contents")

    # Check at least one file is selected
    selected_count = sum(1 for f in run.vendor_commercial_files if f.get("selected", True))
    if selected_count == 0:
        raise HTTPException(status_code=400, detail="At least one file must be selected for evaluation")

    flag_modified(run, 'vendor_commercial_files')
    db.commit()

    return {
        "ok": True,
        "files": run.vendor_commercial_files,
        "selected_count": selected_count,
    }


# ── Internal: Update Progress (called by agent) ──

class ProgressUpdateRequest(BaseModel):
    status: str
    progress: dict


@router.patch("/runs/{run_id}/progress")
def update_progress(
    run_id: int,
    body: ProgressUpdateRequest,
    db: Session = Depends(get_db),
):
    run = db.query(ComplianceRun).filter(ComplianceRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    run.status = body.status
    run.progress = body.progress
    db.commit()
    return {"ok": True}


# ── Internal: Store Result (called by agent) ──

class CompleteRunRequest(BaseModel):
    clauses: list = []
    total_clauses: int = 0
    compliant_count: int = 0
    partial_count: int = 0
    non_compliant_count: int = 0
    unverifiable_count: int = 0
    overall_score: float = 0.0
    recommendation: Optional[str] = None
    missing_clause_count: int = 0
    contradiction_count: int = 0
    house_rule_violation_count: int = 0
    report_path: Optional[str] = None


@router.patch("/runs/{run_id}/complete")
def complete_run(
    run_id: int,
    body: CompleteRunRequest,
    db: Session = Depends(get_db),
):
    run = db.query(ComplianceRun).filter(ComplianceRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    _store_results_in_db(run, body.model_dump(), db)
    return {"ok": True}


# ── Workaround: define IngestBundleRequest / RunPipelineRequest here for JSON serialization ──

class IngestBundleRequest(BaseModel):
    sotr_commercial_path: str = ""
    sotr_technical_path: str = ""
    vendor_commercial_paths: List[str] = []  # Multiple files from ZIP
    vendor_dpr_path: str = ""
    run_id: int = 0


class RunPipelineRequest(BaseModel):
    run_id: int = 0
    doc_id_sotr_com: str = ""
    doc_id_sotr_tech: str = ""
    doc_id_vendor_com: str = ""
    doc_id_vendor_com_others: List[str] = []  # Additional vendor commercial doc IDs from ZIP
    doc_id_vendor_dpr: str = ""
    selected_standards: List[str] = []
    reference_name: str = ""


# ── Standards Relevance ──

@router.post("/standards/relevance")
async def compute_standards_relevance(
    sotr_commercial: Optional[UploadFile] = File(None),
    sotr_technical: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
):
    """Accept SOTR files, extract text via agent, and return standards relevance scores."""
    tmp_dir = Path(_COMPLIANCE_DIR) / "_relevance_tmp" / str(uuid.uuid4())
    tmp_dir.mkdir(parents=True, exist_ok=True)

    file_paths = []
    try:
        for upload_file, label in [(sotr_commercial, "sotr_com"), (sotr_technical, "sotr_tech")]:
            if upload_file is None:
                continue
            safe_name = _sanitize_filename(upload_file.filename or label)
            dest = tmp_dir / safe_name
            content = await upload_file.read()
            dest.write_bytes(content)
            file_paths.append(str(dest))

        if not file_paths:
            return []

        result = _agent_post("standards/relevance-from-files", {
            "file_paths": file_paths,
        })
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Relevance computation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Relevance computation failed: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
