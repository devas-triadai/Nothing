"""
AGRA Backend — Compliance Evaluation Router
Orchestrates SOTR vs Vendor submission evaluations.
Stores evaluations in local DB, delegates parsing/scoring to the agent API.
"""

import json
import logging
import os
from datetime import datetime
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import ComplianceEvaluation, ClauseScore, User
from app.routers.auth import get_current_user

logger = logging.getLogger("agra.backend.compliance")

_AGENT_BASE = os.getenv("AGENT_BASE_URL", "http://localhost:8005")
router = APIRouter()


# ── Pydantic schemas ──

class CreateEvaluationRequest(BaseModel):
    sotr_doc_id: str = Field(..., description="SOTR document ID from agent vector store")
    vendor_doc_id: str = Field(..., description="Vendor submission document ID from agent vector store")
    project_name: Optional[str] = None
    vessel_name: Optional[str] = None
    vendor_name: Optional[str] = None
    auto_start: bool = False


class ScoreClauseRequest(BaseModel):
    clause_id: int = Field(..., description="ClauseScore DB id")
    status: str = Field(..., description="compliant|partial|non_compliant|not_applicable")
    notes: Optional[str] = None
    confidence: float = 1.0


class EvaluationResponse(BaseModel):
    id: int
    status: str
    project_name: Optional[str] = None
    vessel_name: Optional[str] = None
    vendor_name: Optional[str] = None
    overall_score: Optional[float] = None
    compliant_count: int = 0
    partial_count: int = 0
    non_compliant_count: int = 0
    not_applicable_count: int = 0
    total_clauses: int = 0
    recommendation: Optional[str] = None
    report_pdf_path: Optional[str] = None
    created_at: str
    updated_at: str
    clause_scores: List[dict] = []

    @classmethod
    def from_orm(cls, eval_: ComplianceEvaluation, include_scores: bool = False):
        scores = []
        if include_scores:
            for s in eval_.scores or []:
                scores.append({
                    "id": s.id,
                    "clause_id": s.id,
                    "clause_number": s.clause_number or "",
                    "clause": {
                        "clause_number": s.clause_number or "",
                        "clause_title": s.clause_title or "",
                        "clause_text": s.clause_text or "",
                    },
                    "status": s.status or "pending",
                    "confidence": s.confidence,
                    "evidence_text": s.evidence_text or "",
                    "gaps_identified": s.gaps_identified or "",
                    "vendor_response_summary": s.vendor_response_summary or "",
                    "recommendation": s.recommendation or "review",
                })
        return cls(
            id=eval_.id,
            status=eval_.status or "pending",
            project_name=eval_.project_name,
            vessel_name=eval_.vessel_name,
            vendor_name=eval_.vendor_name,
            overall_score=eval_.overall_score,
            compliant_count=eval_.compliant_count or 0,
            partial_count=eval_.partial_count or 0,
            non_compliant_count=eval_.non_compliant_count or 0,
            not_applicable_count=eval_.not_applicable_count or 0,
            total_clauses=eval_.total_clauses or 0,
            recommendation=eval_.recommendation,
            report_pdf_path=eval_.report_pdf_path,
            created_at=eval_.created_at.isoformat() if eval_.created_at else "",
            updated_at=eval_.updated_at.isoformat() if eval_.updated_at else "",
            clause_scores=scores,
        )


# ── Helper: call agent API ──

def _agent_post(path: str, payload: dict, timeout: int = 120):
    url = f"{_AGENT_BASE}/api/compliance/{path.lstrip('/')}"
    resp = httpx.post(url, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        detail = resp.text[:500]
        logger.error("Agent API error %s -> %s: %s", url, resp.status_code, detail)
        raise HTTPException(status_code=502, detail=f"Agent API error: {resp.status_code} {detail}")
    return resp.json()


# ── Endpoints ──

@router.get("/evaluations", response_model=List[EvaluationResponse])
def list_evaluations(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    evals = (
        db.query(ComplianceEvaluation)
        .order_by(ComplianceEvaluation.created_at.desc())
        .limit(limit)
        .all()
    )
    return [EvaluationResponse.from_orm(e) for e in evals]


@router.post("/evaluations", response_model=EvaluationResponse)
def create_evaluation(
    req: CreateEvaluationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Create evaluation record
    eval_ = ComplianceEvaluation(
        created_by=current_user.id,
        sotr_doc_id=req.sotr_doc_id,
        vendor_doc_id=req.vendor_doc_id,
        project_name=req.project_name,
        vessel_name=req.vessel_name,
        vendor_name=req.vendor_name,
        status="pending",
    )
    db.add(eval_)
    db.commit()
    db.refresh(eval_)

    # Parse SOTR via agent API
    try:
        parsed = _agent_post("/parse-sotr", {
            "doc_id": str(req.sotr_doc_id),
            "filename": f"sotr_{req.sotr_doc_id}",
        })
    except HTTPException:
        eval_.status = "failed"
        db.commit()
        raise
    except Exception as e:
        logger.exception("Failed to parse SOTR")
        eval_.status = "failed"
        db.commit()
        raise HTTPException(status_code=502, detail=f"Failed to parse SOTR: {e}")

    clauses_data = parsed.get("clauses", [])
    eval_.total_clauses = len(clauses_data)

    # Store clause placeholders
    for clause in clauses_data:
        cs = ClauseScore(
            evaluation_id=eval_.id,
            clause_number=clause.get("clause_number", ""),
            clause_title=clause.get("clause_title"),
            clause_text=clause.get("clause_text", ""),
            category=clause.get("category", "general"),
            subcategory=clause.get("subcategory"),
            is_mandatory=clause.get("is_mandatory", True),
            is_critical=clause.get("is_critical", False),
            status="pending",
        )
        db.add(cs)

    db.commit()
    db.refresh(eval_)

    if req.auto_start:
        _run_evaluation(eval_.id, db)

    return EvaluationResponse.from_orm(eval_, include_scores=True)


@router.get("/evaluations/{eval_id}", response_model=EvaluationResponse)
def get_evaluation(
    eval_id: int,
    include_scores: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    eval_ = db.query(ComplianceEvaluation).filter(ComplianceEvaluation.id == eval_id).first()
    if not eval_:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return EvaluationResponse.from_orm(eval_, include_scores=include_scores or "true" in str(include_scores).lower())


@router.post("/evaluations/{eval_id}/run", response_model=EvaluationResponse)
def run_evaluation(
    eval_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    eval_ = db.query(ComplianceEvaluation).filter(ComplianceEvaluation.id == eval_id).first()
    if not eval_:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    _run_evaluation(eval_.id, db)
    db.refresh(eval_)
    return EvaluationResponse.from_orm(eval_, include_scores=True)


def _run_evaluation(eval_id: int, db: Session):
    """Core logic: call agent score-all, store results."""
    eval_ = db.query(ComplianceEvaluation).filter(ComplianceEvaluation.id == eval_id).first()
    if not eval_:
        return

    eval_.status = "running"
    db.commit()

    # Fetch stored clauses
    scores = db.query(ClauseScore).filter(ClauseScore.evaluation_id == eval_id).all()
    if not scores:
        eval_.status = "failed"
        db.commit()
        return

    clauses_payload = []
    for s in scores:
        clauses_payload.append({
            "clause_number": s.clause_number or "",
            "clause_title": s.clause_title or "",
            "clause_text": s.clause_text or "",
            "category": s.category or "general",
            "is_mandatory": s.is_mandatory if s.is_mandatory is not None else True,
            "is_critical": s.is_critical if s.is_critical is not None else False,
            "acceptance_criteria": None,
            "vendor_doc_id": str(eval_.vendor_doc_id),
            "vendor_doc_ids": [str(eval_.vendor_doc_id)],
        })

    try:
        result = _agent_post("/score-all", {
            "clauses": clauses_payload,
            "vendor_doc_id": str(eval_.vendor_doc_id),
            "vendor_doc_ids": [str(eval_.vendor_doc_id)],
            "use_batch": True,
        }, timeout=300)
    except HTTPException:
        eval_.status = "failed"
        db.commit()
        raise
    except Exception as e:
        logger.exception("Failed to score clauses")
        eval_.status = "failed"
        db.commit()
        raise HTTPException(status_code=502, detail=f"Score-all failed: {e}")

    agent_scores = result.get("scores", [])
    summary = result.get("summary", {})

    # Update each clause score in DB
    score_map = {s.clause_number: s for s in scores}
    for agent_s in agent_scores:
        cn = agent_s.get("clause_number", "")
        existing = score_map.get(cn)
        if existing:
            existing.status = agent_s.get("status", "pending")
            existing.confidence = agent_s.get("confidence")
            existing.evidence_text = agent_s.get("evidence_text", "")
            existing.gaps_identified = agent_s.get("gaps_identified")
            existing.vendor_response_summary = agent_s.get("vendor_response_summary", "")
            existing.recommendation = agent_s.get("recommendation", "review")
            existing.updated_at = datetime.utcnow()

    # Update evaluation summary
    eval_.overall_score = summary.get("compliance_percentage", 0) / 100.0
    eval_.compliant_count = summary.get("compliant_count", 0)
    eval_.partial_count = summary.get("partial_count", 0)
    eval_.non_compliant_count = summary.get("non_compliant_count", 0)
    eval_.not_applicable_count = summary.get("not_applicable_count", 0)
    eval_.recommendation = summary.get("recommendation", "conditional")
    eval_.status = "completed"
    db.commit()


@router.post("/evaluations/{eval_id}/score", response_model=EvaluationResponse)
def score_clause(
    eval_id: int,
    req: ScoreClauseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    clause = db.query(ClauseScore).filter(
        ClauseScore.id == req.clause_id,
        ClauseScore.evaluation_id == eval_id,
    ).first()
    if not clause:
        raise HTTPException(status_code=404, detail="Clause score not found")

    clause.status = req.status
    clause.confidence = req.confidence
    clause.ai_notes = req.notes
    clause.manually_overridden = True
    clause.updated_at = datetime.utcnow()
    db.commit()

    # Recalculate evaluation summary
    eval_ = db.query(ComplianceEvaluation).filter(ComplianceEvaluation.id == eval_id).first()
    if eval_:
        _recalc_summary(eval_, db)

    return EvaluationResponse.from_orm(eval_, include_scores=True) if eval_ else None


def _recalc_summary(eval_: ComplianceEvaluation, db: Session):
    """Recalculate evaluation summary from current clause scores."""
    all_scores = db.query(ClauseScore).filter(ClauseScore.evaluation_id == eval_.id).all()
    total = len(all_scores)
    compliant = sum(1 for s in all_scores if s.status == "compliant")
    partial = sum(1 for s in all_scores if s.status == "partial")
    non_compliant = sum(1 for s in all_scores if s.status == "non_compliant")
    na = sum(1 for s in all_scores if s.status == "not_applicable")

    eval_.total_clauses = total
    eval_.compliant_count = compliant
    eval_.partial_count = partial
    eval_.non_compliant_count = non_compliant
    eval_.not_applicable_count = na

    scored = compliant + partial + non_compliant
    eval_.overall_score = (compliant + partial * 0.5) / scored if scored > 0 else 0.0
    eval_.recommendation = (
        "accept" if eval_.overall_score >= 0.8 else
        "conditional" if eval_.overall_score >= 0.6 else
        "reject"
    )
    db.commit()


@router.get("/evaluations/{eval_id}/report", response_model=dict)
def generate_report(
    eval_id: int,
    format: str = "pdf",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    eval_ = db.query(ComplianceEvaluation).filter(ComplianceEvaluation.id == eval_id).first()
    if not eval_:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    if eval_.status != "completed":
        raise HTTPException(status_code=400, detail="Evaluation not completed yet")

    # Try to fetch report from agent if it has a report endpoint,
    # otherwise generate a simple placeholder or return a JSON report URL.
    report = {
        "evaluation_id": eval_.id,
        "status": eval_.status,
        "overall_score": eval_.overall_score,
        "recommendation": eval_.recommendation,
        "total_clauses": eval_.total_clauses,
        "compliant_count": eval_.compliant_count,
        "partial_count": eval_.partial_count,
        "non_compliant_count": eval_.non_compliant_count,
        "not_applicable_count": eval_.not_applicable_count,
        "download_url": None,
    }

    # Check if agent has a report/pdf endpoint
    try:
        payload = {
            "sotr_doc_id": str(eval_.sotr_doc_id),
            "vendor_doc_id": str(eval_.vendor_doc_id),
            "overall_score": eval_.overall_score,
            "recommendation": eval_.recommendation,
            "compliant_count": eval_.compliant_count,
            "partial_count": eval_.partial_count,
            "non_compliant_count": eval_.non_compliant_count,
            "not_applicable_count": eval_.not_applicable_count,
            "clauses": [
                {
                    "clause_number": s.clause_number,
                    "clause_title": s.clause_title,
                    "status": s.status,
                    "confidence": s.confidence,
                    "evidence_text": s.evidence_text,
                    "gaps_identified": s.gaps_identified,
                }
                for s in (eval_.scores or [])
            ],
        }
        resp = httpx.post(f"{_AGENT_BASE}/api/compliance/generate-report", json=payload, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            report["download_url"] = data.get("download_url")
    except Exception as e:
        logger.warning("Failed to generate PDF report via agent: %s", e)

    return report
