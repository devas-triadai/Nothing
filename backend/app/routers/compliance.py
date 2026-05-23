"""
AGRA Compliance Module Phase 4-6 — Compliance API Endpoints
Backend API for SOTR compliance evaluation workflow.

Endpoints:
1. POST /api/compliance/evaluations — Create evaluation
2. GET /api/compliance/evaluations — List evaluations
3. GET /api/compliance/evaluations/{id} — Get evaluation
4. POST /api/compliance/evaluations/{id}/run — Run scoring (async)
5. POST /api/compliance/evaluations/{id}/score — Score single clause
6. GET /api/compliance/evaluations/{id}/report — Get/generate report
7. GET /api/compliance/reports/{id}/download — Download PDF report
8. GET /api/compliance/sotr/{doc_id}/clauses — Get SOTR clauses
"""

import logging
import os
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.models import (
    User, Document, ComplianceEvaluation, ComplianceClause, 
    ClauseScore, ComplianceReport, ComplianceStatus, ClauseStatus,
    AuditLog, DocEdge, DocEdgeType
)
from app.routers.auth import get_current_user
from app.utils.compliance_pdf_export import (
    ComplianceReportGenerator, ReportData, ReportClause,
    generate_compliance_report
)
from fastapi.responses import FileResponse

logger = logging.getLogger("agra.compliance")
router = APIRouter()


# ═══════════════════════════════════════════════════════════════
#  REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════

class CreateEvaluationRequest(BaseModel):
    sotr_doc_id: int
    vendor_doc_id: int
    project_name: Optional[str] = None
    vessel_name: Optional[str] = None
    vendor_name: Optional[str] = None
    auto_start: bool = False


class UpdateClauseScoreRequest(BaseModel):
    clause_id: int
    status: str  # compliant, partial, non_compliant, not_applicable
    notes: Optional[str] = None
    confidence: Optional[float] = None


class EvaluationResponse(BaseModel):
    id: int
    sotr_doc_id: int
    vendor_doc_id: int
    status: str
    project_name: Optional[str]
    vessel_name: Optional[str]
    vendor_name: Optional[str]
    overall_score: Optional[float]
    recommendation: Optional[str]
    total_clauses: int
    compliant_count: int
    partial_count: int
    non_compliant_count: int
    not_applicable_count: int
    created_at: datetime
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class ClauseResponse(BaseModel):
    id: int
    sotr_doc_id: int
    clause_number: str
    clause_title: Optional[str]
    clause_text: str
    category: str
    is_mandatory: bool
    is_critical: bool
    acceptance_criteria: Optional[str]
    
    class Config:
        from_attributes = True


class ClauseScoreResponse(BaseModel):
    id: int
    evaluation_id: int
    clause_id: int
    clause: Optional[ClauseResponse]
    status: str
    confidence: float
    vendor_response_summary: Optional[str]
    evidence_text: Optional[str]
    gaps_identified: Optional[str]
    manually_reviewed: bool
    reviewer_notes: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class DetailedEvaluationResponse(EvaluationResponse):
    clause_scores: List[ClauseScoreResponse]
    warnings: Optional[List[str]] = None


class ReportResponse(BaseModel):
    id: int
    evaluation_id: int
    report_type: str
    file_name: Optional[str]
    download_url: Optional[str]
    summary_text: Optional[str]
    generated_at: datetime
    version: int
    
    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════
#  ENDPOINT 1: CREATE EVALUATION
# ═══════════════════════════════════════════════════════════════

@router.post("/evaluations", response_model=EvaluationResponse)
async def create_evaluation(
    request: CreateEvaluationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new compliance evaluation.
    Links SOTR document with vendor submission for comparison.
    """
    # Verify documents exist
    sotr_doc = db.query(Document).filter(Document.id == request.sotr_doc_id).first()
    if not sotr_doc:
        raise HTTPException(status_code=404, detail="SOTR document not found")
    
    vendor_doc = db.query(Document).filter(Document.id == request.vendor_doc_id).first()
    if not vendor_doc:
        raise HTTPException(status_code=404, detail="Vendor document not found")
    
    # Create evaluation
    evaluation = ComplianceEvaluation(
        sotr_doc_id=request.sotr_doc_id,
        vendor_doc_id=request.vendor_doc_id,
        project_name=request.project_name,
        vessel_name=request.vessel_name,
        vendor_name=request.vendor_name,
        created_by=current_user.id,
        status=ComplianceStatus.CREATED
    )
    
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="COMPLIANCE_EVALUATION_CREATED",
        resource_type="compliance_evaluation",
        resource_id=str(evaluation.id),
        new_value=f"SOTR:{request.sotr_doc_id}, Vendor:{request.vendor_doc_id}, Project:{request.project_name or 'N/A'}",
        status="success"
    )
    db.add(audit)
    db.commit()
    
    logger.info(f"Created compliance evaluation {evaluation.id} by user {current_user.id}")
    
    # Auto-start if requested
    if request.auto_start:
        background_tasks.add_task(
            _run_evaluation_background,
            evaluation.id,
        )
        evaluation.status = ComplianceStatus.PARSING_SOTR
        db.commit()
    
    return evaluation


# ═══════════════════════════════════════════════════════════════
#  ENDPOINT 2: GET EVALUATION
# ═══════════════════════════════════════════════════════════════

@router.get("/evaluations/{evaluation_id}", response_model=DetailedEvaluationResponse)
async def get_evaluation(
    evaluation_id: int,
    include_scores: bool = Query(default=True, description="Include clause scores in response"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get evaluation details with optional clause scores.
    """
    evaluation = db.query(ComplianceEvaluation).filter(
        ComplianceEvaluation.id == evaluation_id
    ).first()
    
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    # Check for superseded documents (genealogy warnings)
    warnings = []
    sotr_doc = db.query(Document).filter(Document.id == evaluation.sotr_doc_id).first()
    if sotr_doc:
        # Check if SOTR has been superseded by a newer version
        child = db.query(Document).filter(Document.parent_doc_id == sotr_doc.id).first()
        if child:
            warnings.append(
                f"WARNING: SOTR document '{sotr_doc.original_filename}' has been superseded "
                f"by '{child.original_filename}'. Consider re-evaluating against the latest version."
            )
        else:
            edge = db.query(DocEdge).filter(
                DocEdge.source_id == sotr_doc.id,
                DocEdge.edge_type == DocEdgeType.SUPERSEDES
            ).first()
            if edge:
                target = db.query(Document).filter(Document.id == edge.target_id).first()
                if target:
                    warnings.append(
                        f"WARNING: SOTR document '{sotr_doc.original_filename}' has been superseded "
                        f"by '{target.original_filename}'. Consider re-evaluating against the latest version."
                    )
    
    # Build response
    response = DetailedEvaluationResponse(
        id=evaluation.id,
        sotr_doc_id=evaluation.sotr_doc_id,
        vendor_doc_id=evaluation.vendor_doc_id,
        status=evaluation.status,
        project_name=evaluation.project_name,
        vessel_name=evaluation.vessel_name,
        vendor_name=evaluation.vendor_name,
        overall_score=evaluation.overall_score,
        recommendation=evaluation.recommendation,
        total_clauses=evaluation.total_clauses,
        compliant_count=evaluation.compliant_count,
        partial_count=evaluation.partial_count,
        non_compliant_count=evaluation.non_compliant_count,
        not_applicable_count=evaluation.not_applicable_count,
        created_at=evaluation.created_at,
        completed_at=evaluation.completed_at,
        clause_scores=[],
        warnings=warnings if warnings else None
    )
    
    # Include clause scores if requested
    if include_scores:
        scores = db.query(ClauseScore).filter(
            ClauseScore.evaluation_id == evaluation_id
        ).all()
        
        response.clause_scores = [
            ClauseScoreResponse(
                id=score.id,
                evaluation_id=score.evaluation_id,
                clause_id=score.clause_id,
                clause=ClauseResponse(
                    id=score.clause.id,
                    sotr_doc_id=score.clause.sotr_doc_id,
                    clause_number=score.clause.clause_number,
                    clause_title=score.clause.clause_title,
                    clause_text=score.clause.clause_text[:200] + "..." if len(score.clause.clause_text) > 200 else score.clause.clause_text,
                    category=score.clause.category or "general",
                    is_mandatory=score.clause.is_mandatory,
                    is_critical=score.clause.is_critical,
                    acceptance_criteria=score.clause.acceptance_criteria
                ) if score.clause else None,
                status=score.status,
                confidence=score.confidence,
                vendor_response_summary=score.vendor_response_summary,
                evidence_text=score.evidence_text,
                gaps_identified=score.gaps_identified,
                manually_reviewed=score.manually_reviewed,
                reviewer_notes=score.reviewer_notes,
                created_at=score.created_at
            )
            for score in scores
        ]
    
    return response


# ═══════════════════════════════════════════════════════════════
#  ENDPOINT 3: RUN EVALUATION (ASYNC)
# ═══════════════════════════════════════════════════════════════

@router.post("/evaluations/{evaluation_id}/run")
async def run_evaluation(
    evaluation_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Trigger clause-by-clause scoring asynchronously.
    Returns immediately; use GET endpoint to poll for completion.
    """
    evaluation = db.query(ComplianceEvaluation).filter(
        ComplianceEvaluation.id == evaluation_id
    ).first()
    
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    if evaluation.status in [ComplianceStatus.SCORING, ComplianceStatus.PARSING_SOTR]:
        raise HTTPException(status_code=409, detail="Evaluation already in progress")
    
    if evaluation.status == ComplianceStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Evaluation already completed")
    
    # Queue background task
    background_tasks.add_task(
        _run_evaluation_background,
        evaluation_id
    )
    
    # Update status
    evaluation.status = ComplianceStatus.PARSING_SOTR
    evaluation.started_at = datetime.utcnow()
    db.commit()
    
    return {
        "message": "Evaluation started",
        "evaluation_id": evaluation_id,
        "status": evaluation.status
    }


def _run_evaluation_background(evaluation_id: int, db_session=None):
    """
    Background task to run full compliance evaluation.
    Calls the agent's compliance engine endpoints via HTTP for SOTR parsing
    and clause scoring, then persists results to PostgreSQL.
    """
    import httpx
    from sqlalchemy.orm import sessionmaker
    from app.database import engine
    
    # Create new session for background task (don't reuse request-scoped session)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    _AGENT_BASE = os.environ.get("AGRA_AGENT_URL", "http://localhost:8005")
    
    try:
        # Get evaluation
        evaluation = db.query(ComplianceEvaluation).filter(
            ComplianceEvaluation.id == evaluation_id
        ).first()
        
        if not evaluation:
            logger.error(f"Evaluation {evaluation_id} not found for background processing")
            return
        
        # Get document records for qdrant_doc_id mapping
        sotr_doc = db.query(Document).filter(
            Document.id == evaluation.sotr_doc_id
        ).first()
        vendor_doc = db.query(Document).filter(
            Document.id == evaluation.vendor_doc_id
        ).first()
        
        if not sotr_doc:
            raise ValueError("SOTR document not found in database")
        if not vendor_doc:
            raise ValueError("Vendor document not found in database")
        
        # Resolve vector store doc IDs
        sotr_qdrant_id = sotr_doc.qdrant_doc_id or str(sotr_doc.id)
        vendor_qdrant_id = vendor_doc.qdrant_doc_id or str(vendor_doc.id)
        
        # ── Step 1: Parse SOTR ──
        logger.info(f"[Eval {evaluation_id}] Step 1: Parsing SOTR doc_id={sotr_qdrant_id}")
        evaluation.status = ComplianceStatus.PARSING_SOTR
        db.commit()
        
        with httpx.Client(base_url=_AGENT_BASE, timeout=120.0) as client:
            # Parse SOTR via agent API
            parse_resp = client.post(
                "/api/compliance/parse-sotr",
                json={
                    "doc_id": sotr_qdrant_id,
                    "filename": sotr_doc.filename or sotr_doc.original_filename or "",
                },
            )
            
            if parse_resp.status_code != 200:
                raise ValueError(
                    f"SOTR parsing failed (HTTP {parse_resp.status_code}): "
                    f"{parse_resp.text[:300]}"
                )
            
            parse_data = parse_resp.json()
        
        parsed_clauses = parse_data.get("clauses", [])
        
        if not parsed_clauses:
            logger.warning(f"[Eval {evaluation_id}] No clauses extracted from SOTR")
            evaluation.status = ComplianceStatus.FAILED
            evaluation.recommendation_notes = "No clauses could be extracted from the SOTR document."
            db.commit()
            return
        
        logger.info(f"[Eval {evaluation_id}] Extracted {len(parsed_clauses)} clauses from SOTR")
        
        # ── Step 1b: Persist extracted clauses to DB ──
        # Check if clauses already exist for this SOTR doc
        existing_clauses = db.query(ComplianceClause).filter(
            ComplianceClause.sotr_doc_id == evaluation.sotr_doc_id
        ).all()
        
        if not existing_clauses:
            # Insert new clauses
            for pc in parsed_clauses:
                clause_record = ComplianceClause(
                    sotr_doc_id=evaluation.sotr_doc_id,
                    clause_number=pc["clause_number"],
                    clause_title=pc.get("clause_title"),
                    clause_text=pc["clause_text"],
                    category=pc.get("category", "general"),
                    subcategory=pc.get("subcategory"),
                    is_mandatory=pc.get("is_mandatory", True),
                    is_critical=pc.get("is_critical", False),
                    acceptance_criteria=pc.get("acceptance_criteria"),
                    page_number=pc.get("page_number"),
                    extraction_confidence=pc.get("extraction_confidence", 0.0),
                )
                db.add(clause_record)
            db.commit()
            logger.info(f"[Eval {evaluation_id}] Persisted {len(parsed_clauses)} clauses to DB")
        
        # Reload clauses from DB (ensures we have IDs)
        db_clauses = db.query(ComplianceClause).filter(
            ComplianceClause.sotr_doc_id == evaluation.sotr_doc_id
        ).order_by(ComplianceClause.clause_number).all()
        
        # ── Step 2: Score clauses via agent ──
        logger.info(f"[Eval {evaluation_id}] Step 2: Scoring {len(db_clauses)} clauses against vendor doc")
        evaluation.status = ComplianceStatus.SCORING
        db.commit()
        
        # Build scoring request
        score_request_clauses = []
        for clause in db_clauses:
            score_request_clauses.append({
                "clause_number": clause.clause_number,
                "clause_title": clause.clause_title,
                "clause_text": clause.clause_text,
                "category": clause.category or "general",
                "is_mandatory": clause.is_mandatory,
                "is_critical": clause.is_critical,
                "acceptance_criteria": clause.acceptance_criteria,
                "vendor_doc_id": vendor_qdrant_id,
            })
        
        with httpx.Client(base_url=_AGENT_BASE, timeout=300.0) as client:
            score_resp = client.post(
                "/api/compliance/score-all",
                json={
                    "clauses": score_request_clauses,
                    "vendor_doc_id": vendor_qdrant_id,
                    "use_batch": True,
                },
            )
            
            if score_resp.status_code != 200:
                raise ValueError(
                    f"Clause scoring failed (HTTP {score_resp.status_code}): "
                    f"{score_resp.text[:300]}"
                )
            
            score_data = score_resp.json()
        
        scores_list = score_data.get("scores", [])
        summary = score_data.get("summary", {})
        
        logger.info(f"[Eval {evaluation_id}] Received {len(scores_list)} scores from agent")
        
        # ── Step 2b: Persist scores to DB ──
        # Map clause_number -> db clause for lookup
        clause_map = {c.clause_number: c for c in db_clauses}
        
        for score_item in scores_list:
            clause_number = score_item.get("clause_number", "")
            db_clause = clause_map.get(clause_number)
            
            if not db_clause:
                logger.warning(f"[Eval {evaluation_id}] Score for unknown clause '{clause_number}', skipping")
                continue
            
            # Create or update score record
            existing_score = db.query(ClauseScore).filter(
                ClauseScore.evaluation_id == evaluation_id,
                ClauseScore.clause_id == db_clause.id,
            ).first()
            
            status_value = score_item.get("status", "pending")
            confidence_value = score_item.get("confidence", 0.0)
            
            if not existing_score:
                existing_score = ClauseScore(
                    evaluation_id=evaluation_id,
                    clause_id=db_clause.id,
                    status=status_value,
                    confidence=confidence_value,
                    vendor_response_summary=score_item.get("vendor_response_summary", ""),
                    evidence_text=score_item.get("evidence_text", ""),
                    gaps_identified=score_item.get("gaps_identified"),
                    deviation_notes=score_item.get("recommendation", ""),
                    llm_raw_response=None,
                )
                db.add(existing_score)
            else:
                existing_score.status = status_value
                existing_score.confidence = confidence_value
                existing_score.vendor_response_summary = score_item.get("vendor_response_summary", "")
                existing_score.evidence_text = score_item.get("evidence_text", "")
                existing_score.gaps_identified = score_item.get("gaps_identified")
                existing_score.deviation_notes = score_item.get("recommendation", "")
        
        db.commit()
        
        # ── Step 3: Calculate evaluation summary ──
        logger.info(f"[Eval {evaluation_id}] Step 3: Calculating summary")
        
        all_scores = db.query(ClauseScore).filter(
            ClauseScore.evaluation_id == evaluation_id
        ).all()
        
        counts = {"compliant": 0, "partial": 0, "non_compliant": 0, "not_applicable": 0}
        for score in all_scores:
            if score.status in counts:
                counts[score.status] += 1
        
        evaluation.compliant_count = counts["compliant"]
        evaluation.partial_count = counts["partial"]
        evaluation.non_compliant_count = counts["non_compliant"]
        evaluation.not_applicable_count = counts["not_applicable"]
        evaluation.total_clauses = len(all_scores)
        
        # Use agent-provided summary if available, otherwise calculate locally
        if summary and summary.get("compliance_percentage") is not None:
            evaluation.overall_score = summary["compliance_percentage"] / 100.0
            evaluation.recommendation = summary.get("recommendation", "review")
        else:
            scored = counts["compliant"] + counts["partial"] + counts["non_compliant"]
            if scored > 0:
                evaluation.overall_score = (counts["compliant"] + counts["partial"] * 0.5) / scored
            else:
                evaluation.overall_score = 0.0
            
            if counts["non_compliant"] == 0 and counts["compliant"] >= counts["partial"]:
                evaluation.recommendation = "accept"
            elif counts["non_compliant"] <= 2 and counts["compliant"] > counts["non_compliant"]:
                evaluation.recommendation = "conditional"
            else:
                evaluation.recommendation = "reject"
        
        # Mark complete
        evaluation.status = ComplianceStatus.COMPLETED
        evaluation.completed_at = datetime.utcnow()
        db.commit()
        
        logger.info(
            f"[Eval {evaluation_id}] COMPLETED — score={evaluation.overall_score:.2%}, "
            f"recommendation={evaluation.recommendation}, "
            f"clauses={evaluation.total_clauses} "
            f"(C:{counts['compliant']}/P:{counts['partial']}/NC:{counts['non_compliant']}/NA:{counts['not_applicable']})"
        )
        
    except Exception as e:
        logger.error(f"[Eval {evaluation_id}] FAILED: {e}", exc_info=True)
        try:
            evaluation = db.query(ComplianceEvaluation).filter(
                ComplianceEvaluation.id == evaluation_id
            ).first()
            if evaluation:
                evaluation.status = ComplianceStatus.FAILED
                evaluation.recommendation_notes = f"Evaluation failed: {str(e)[:500]}"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
#  ENDPOINT 4: SCORE SINGLE CLAUSE (MANUAL REVIEW)
# ═══════════════════════════════════════════════════════════════

@router.post("/evaluations/{evaluation_id}/score", response_model=ClauseScoreResponse)
async def score_single_clause(
    evaluation_id: int,
    request: UpdateClauseScoreRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Manually score or override a single clause.
    Used for manual review and corrections.
    """
    evaluation = db.query(ComplianceEvaluation).filter(
        ComplianceEvaluation.id == evaluation_id
    ).first()
    
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    # Validate clause exists
    clause = db.query(ComplianceClause).filter(
        ComplianceClause.id == request.clause_id
    ).first()
    
    if not clause:
        raise HTTPException(status_code=404, detail="Clause not found")
    
    # Validate status
    valid_statuses = ["compliant", "partial", "non_compliant", "not_applicable"]
    if request.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
    
    # Find or create score
    score = db.query(ClauseScore).filter(
        ClauseScore.evaluation_id == evaluation_id,
        ClauseScore.clause_id == request.clause_id
    ).first()
    
    if not score:
        score = ClauseScore(
            evaluation_id=evaluation_id,
            clause_id=request.clause_id,
            status=request.status,
            confidence=request.confidence or 1.0,
            reviewer_notes=request.notes,
            manually_reviewed=True,
            reviewed_by=current_user.id,
            reviewed_at=datetime.utcnow()
        )
        db.add(score)
    else:
        score.status = request.status
        if request.confidence is not None:
            score.confidence = request.confidence
        if request.notes:
            score.reviewer_notes = request.notes
        score.manually_reviewed = True
        score.reviewed_by = current_user.id
        score.reviewed_at = datetime.utcnow()
    
    db.commit()
    db.refresh(score)
    
    # Audit log for manual override
    audit = AuditLog(
        user_id=current_user.id,
        action="COMPLIANCE_CLAUSE_SCORED_MANUAL",
        resource_type="clause_score",
        resource_id=str(score.id),
        new_value=f"eval:{evaluation_id}, clause:{request.clause_id}, status:{request.status}",
        status="success"
    )
    db.add(audit)
    db.commit()
    
    # Recalculate evaluation summary
    _recalculate_evaluation_summary(evaluation_id, db)
    
    return ClauseScoreResponse(
        id=score.id,
        evaluation_id=score.evaluation_id,
        clause_id=score.clause_id,
        clause=None,
        status=score.status,
        confidence=score.confidence,
        vendor_response_summary=score.vendor_response_summary,
        evidence_text=score.evidence_text,
        gaps_identified=score.gaps_identified,
        manually_reviewed=score.manually_reviewed,
        reviewer_notes=score.reviewer_notes,
        created_at=score.created_at
    )


def _recalculate_evaluation_summary(evaluation_id: int, db: Session):
    """Recalculate evaluation summary after manual score update."""
    evaluation = db.query(ComplianceEvaluation).filter(
        ComplianceEvaluation.id == evaluation_id
    ).first()
    
    if not evaluation:
        return
    
    all_scores = db.query(ClauseScore).filter(
        ClauseScore.evaluation_id == evaluation_id
    ).all()
    
    counts = {"compliant": 0, "partial": 0, "non_compliant": 0, "not_applicable": 0}
    for score in all_scores:
        if score.status in counts:
            counts[score.status] += 1
    
    evaluation.compliant_count = counts["compliant"]
    evaluation.partial_count = counts["partial"]
    evaluation.non_compliant_count = counts["non_compliant"]
    evaluation.not_applicable_count = counts["not_applicable"]
    
    scored = counts["compliant"] + counts["partial"] + counts["non_compliant"]
    if scored > 0:
        evaluation.overall_score = (counts["compliant"] + counts["partial"] * 0.5) / scored
    
    # Update recommendation
    if counts["non_compliant"] == 0 and counts["compliant"] >= counts["partial"]:
        evaluation.recommendation = "accept"
    elif counts["non_compliant"] <= 2 and counts["compliant"] > counts["non_compliant"]:
        evaluation.recommendation = "conditional"
    else:
        evaluation.recommendation = "reject"
    
    db.commit()


# ═══════════════════════════════════════════════════════════════
#  ENDPOINT 5: GET/CREATE REPORT
# ═══════════════════════════════════════════════════════════════

@router.get("/evaluations/{evaluation_id}/report", response_model=ReportResponse)
async def get_report(
    evaluation_id: int,
    format: str = Query(default="json", description="Report format: json or pdf"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get or generate compliance report.
    If format=pdf, generates PDF report using Phase 6 PDF generator.
    """
    evaluation = db.query(ComplianceEvaluation).filter(
        ComplianceEvaluation.id == evaluation_id
    ).first()
    
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    if evaluation.status != ComplianceStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Evaluation not completed yet")
    
    # Get all clause scores for this evaluation
    clause_scores = db.query(ClauseScore).filter(
        ClauseScore.evaluation_id == evaluation_id
    ).all()
    
    # Build report clauses
    report_clauses = []
    for score in clause_scores:
        if score.clause:
            report_clauses.append(ReportClause(
                clause_number=score.clause.clause_number,
                clause_title=score.clause.clause_title or "Untitled",
                clause_text=score.clause.clause_text,
                category=score.clause.category or "general",
                is_mandatory=score.clause.is_mandatory,
                is_critical=score.clause.is_critical,
                acceptance_criteria=score.clause.acceptance_criteria or "",
                status=score.status,
                confidence=score.confidence,
                vendor_response_summary=score.vendor_response_summary or "",
                evidence_text=score.evidence_text or "",
                gaps_identified=score.gaps_identified
            ))
    
    # Get SOTR document name
    sotr_doc = db.query(Document).filter(Document.id == evaluation.sotr_doc_id).first()
    sotr_doc_name = sotr_doc.filename if sotr_doc else "Unknown"
    
    # Build key findings
    key_findings = []
    if evaluation.compliant_count > 0:
        key_findings.append(f"{evaluation.compliant_count} clauses fully compliant")
    if evaluation.partial_count > 0:
        key_findings.append(f"{evaluation.partial_count} clauses partially compliant - review recommended")
    if evaluation.non_compliant_count > 0:
        key_findings.append(f"{evaluation.non_compliant_count} clauses non-compliant")
    
    # Build recommendation reason
    if evaluation.recommendation == "accept":
        rec_reason = "Vendor submission meets all SOTR requirements. Ready for contract award."
    elif evaluation.recommendation == "conditional":
        rec_reason = "Vendor submission meets most requirements with minor gaps. Clarification required before contract award."
    else:
        rec_reason = "Vendor submission has significant non-compliance issues. Not recommended for contract award."
    
    # Create report data
    report_data = ReportData(
        evaluation_id=evaluation_id,
        project_name=evaluation.project_name or "",
        vessel_name=evaluation.vessel_name or "",
        vendor_name=evaluation.vendor_name or "",
        sotr_doc_name=sotr_doc_name,
        generated_at=datetime.utcnow(),
        overall_score=evaluation.overall_score or 0.0,
        total_clauses=evaluation.total_clauses,
        compliant_count=evaluation.compliant_count,
        partial_count=evaluation.partial_count,
        non_compliant_count=evaluation.non_compliant_count,
        not_applicable_count=evaluation.not_applicable_count,
        recommendation=evaluation.recommendation or "review",
        recommendation_reason=rec_reason,
        clauses=report_clauses,
        key_findings=key_findings
    )
    
    # Mark old reports as not latest
    db.query(ComplianceReport).filter(
        ComplianceReport.evaluation_id == evaluation_id
    ).update({"is_latest": False})
    
    # Create new report record
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    file_name = f"compliance_report_{evaluation_id:05d}_{timestamp}.pdf"
    
    report = ComplianceReport(
        evaluation_id=evaluation_id,
        report_type="full",
        file_name=file_name,
        file_path=f"/tmp/compliance_reports/{file_name}",
        summary_text=f"Compliance evaluation for {evaluation.vessel_name or 'Unknown Vessel'} - Score: {(evaluation.overall_score or 0)*100:.1f}%",
        key_findings=str(key_findings),
        generated_by=current_user.id,
        is_latest=True
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    
    # Generate PDF if requested
    if format.lower() == "pdf":
        try:
            generator = ComplianceReportGenerator(report.file_path)
            generator.generate(report_data)
            
            # Update report with file size
            import os
            if os.path.exists(report.file_path):
                report.file_size_bytes = os.path.getsize(report.file_path)
                db.commit()
        except Exception as e:
            logger.error(f"PDF generation failed: {e}")
            # Don't fail the request, just return without download URL
    
    download_url = f"/api/compliance/reports/{report.id}/download"
    
    return ReportResponse(
        id=report.id,
        evaluation_id=report.evaluation_id,
        report_type=report.report_type,
        file_name=report.file_name,
        download_url=download_url,
        summary_text=report.summary_text,
        generated_at=report.generated_at,
        version=report.version
    )


# ═══════════════════════════════════════════════════════════════
#  ENDPOINT 7: DOWNLOAD PDF REPORT
# ═══════════════════════════════════════════════════════════════

@router.get("/reports/{report_id}/download")
async def download_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Download generated PDF report.
    """
    report = db.query(ComplianceReport).filter(
        ComplianceReport.id == report_id
    ).first()
    
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    if not report.file_path or not os.path.exists(report.file_path):
        raise HTTPException(status_code=404, detail="Report file not found. Generate report first.")
    
    return FileResponse(
        report.file_path,
        media_type="application/pdf",
        filename=report.file_name
    )


# ═══════════════════════════════════════════════════════════════
#  ENDPOINT 6: GET SOTR CLAUSES
# ═══════════════════════════════════════════════════════════════

@router.get("/sotr/{doc_id}/clauses", response_model=List[ClauseResponse])
async def get_sotr_clauses(
    doc_id: int,
    category: Optional[str] = Query(default=None, description="Filter by category"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get extracted clauses from an SOTR document.
    Returns empty list if clauses not yet extracted.
    """
    # Verify document exists
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Build query
    query = db.query(ComplianceClause).filter(
        ComplianceClause.sotr_doc_id == doc_id
    )
    
    if category:
        query = query.filter(ComplianceClause.category == category)
    
    clauses = query.order_by(ComplianceClause.clause_number).all()
    
    # If no clauses found, return empty list (not error)
    # Frontend can trigger extraction if needed
    
    return [
        ClauseResponse(
            id=clause.id,
            sotr_doc_id=clause.sotr_doc_id,
            clause_number=clause.clause_number,
            clause_title=clause.clause_title,
            clause_text=clause.clause_text,
            category=clause.category or "general",
            is_mandatory=clause.is_mandatory,
            is_critical=clause.is_critical,
            acceptance_criteria=clause.acceptance_criteria
        )
        for clause in clauses
    ]


# ═══════════════════════════════════════════════════════════════
#  ADDITIONAL: LIST EVALUATIONS
# ═══════════════════════════════════════════════════════════════

@router.get("/evaluations", response_model=List[EvaluationResponse])
async def list_evaluations(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List compliance evaluations with pagination.
    """
    query = db.query(ComplianceEvaluation)
    
    if status:
        query = query.filter(ComplianceEvaluation.status == status)
    
    evaluations = query.order_by(
        ComplianceEvaluation.created_at.desc()
    ).offset(skip).limit(limit).all()
    
    return evaluations
