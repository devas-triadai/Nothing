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
    ClauseScore, ComplianceReport, ComplianceStatus, ClauseStatus
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
    
    logger.info(f"Created compliance evaluation {evaluation.id} by user {current_user.id}")
    
    # Auto-start if requested
    if request.auto_start:
        background_tasks.add_task(
            _run_evaluation_background,
            evaluation.id,
            db
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
        clause_scores=[]
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


def _run_evaluation_background(evaluation_id: int):
    """
    Background task to run full compliance evaluation.
    This runs in a separate worker context.
    """
    from sqlalchemy.orm import sessionmaker
    from app.database import engine
    
    # Create new session for background task
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        from api.rag.sotr_parser import parse_sotr_document, extract_clauses_to_models
        from api.rag.clause_scorer import score_all_clauses, generate_evaluation_summary
        
        # Get evaluation
        evaluation = db.query(ComplianceEvaluation).filter(
            ComplianceEvaluation.id == evaluation_id
        ).first()
        
        if not evaluation:
            logger.error(f"Evaluation {evaluation_id} not found for background processing")
            return
        
        # Step 1: Parse SOTR
        logger.info(f"Parsing SOTR for evaluation {evaluation_id}")
        evaluation.status = ComplianceStatus.PARSING_SOTR
        db.commit()
        
        # Get SOTR document text
        sotr_chunks = db.query(Document).filter(
            Document.id == evaluation.sotr_doc_id
        ).first()
        
        if not sotr_chunks:
            raise ValueError("SOTR document not found")
        
        # Extract clauses
        # Note: This would need actual document text - simplified here
        # In production, retrieve from vector store or document storage
        
        # Step 2: Score clauses
        logger.info(f"Scoring clauses for evaluation {evaluation_id}")
        evaluation.status = ComplianceStatus.SCORING
        db.commit()
        
        # Get existing clauses or create placeholder
        clauses = db.query(ComplianceClause).filter(
            ComplianceClause.sotr_doc_id == evaluation.sotr_doc_id
        ).all()
        
        if not clauses:
            logger.warning(f"No clauses found for SOTR {evaluation.sotr_doc_id}")
        
        # Score each clause (placeholder implementation)
        scored_count = 0
        for clause in clauses:
            # Create or update score
            score = db.query(ClauseScore).filter(
                ClauseScore.evaluation_id == evaluation_id,
                ClauseScore.clause_id == clause.id
            ).first()
            
            if not score:
                score = ClauseScore(
                    evaluation_id=evaluation_id,
                    clause_id=clause.id,
                    status=ClauseStatus.PENDING,
                    confidence=0.0
                )
                db.add(score)
            
            scored_count += 1
        
        db.commit()
        
        # Step 3: Calculate summary
        all_scores = db.query(ClauseScore).filter(
            ClauseScore.evaluation_id == evaluation_id
        ).all()
        
        # Count by status
        counts = {"compliant": 0, "partial": 0, "non_compliant": 0, "not_applicable": 0}
        for score in all_scores:
            if score.status in counts:
                counts[score.status] += 1
        
        evaluation.compliant_count = counts["compliant"]
        evaluation.partial_count = counts["partial"]
        evaluation.non_compliant_count = counts["non_compliant"]
        evaluation.not_applicable_count = counts["not_applicable"]
        evaluation.total_clauses = len(all_scores)
        
        # Calculate overall score
        scored = counts["compliant"] + counts["partial"] + counts["non_compliant"]
        if scored > 0:
            evaluation.overall_score = (counts["compliant"] + counts["partial"] * 0.5) / scored
        else:
            evaluation.overall_score = 0.0
        
        # Determine recommendation
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
        
        logger.info(f"Evaluation {evaluation_id} completed with score {evaluation.overall_score}")
        
    except Exception as e:
        logger.error(f"Evaluation {evaluation_id} failed: {e}")
        evaluation = db.query(ComplianceEvaluation).filter(
            ComplianceEvaluation.id == evaluation_id
        ).first()
        if evaluation:
            evaluation.status = ComplianceStatus.FAILED
            db.commit()
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
