from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from datetime import datetime, timedelta
from typing import Optional, List
from app.database import get_db
from app.models.models import UsageLog, User, AuditLog, Document, UserSession
from app.routers.auth import get_current_user

router = APIRouter()


@router.get("/")
def get_reports_list(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get list of available reports"""
    reports = [
        {
            "id": 1,
            "name": "Weekly Usage Report",
            "type": "usage",
            "created_at": datetime.utcnow().isoformat(),
            "status": "completed"
        },
        {
            "id": 2,
            "name": "User Activity Report",
            "type": "users",
            "created_at": datetime.utcnow().isoformat(),
            "status": "completed"
        },
        {
            "id": 3,
            "name": "Document Index Report",
            "type": "documents",
            "created_at": datetime.utcnow().isoformat(),
            "status": "completed"
        }
    ]
    return {"reports": reports, "total": len(reports)}


@router.get("/stats")
def get_reports_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get reports statistics — system snapshot with change percentages"""
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)

    # Current period counts
    total_users = db.query(User).count()
    active_sessions = db.query(UserSession).filter(UserSession.is_active == True).count()
    total_documents = db.query(Document).count()
    api_calls = db.query(UsageLog).count()

    # Previous period counts (30–60 days ago)
    prev_users = db.query(User).filter(User.created_at < thirty_days_ago).count()
    prev_docs = db.query(Document).filter(Document.created_at < thirty_days_ago).count()

    recent_calls = db.query(UsageLog).filter(UsageLog.created_at >= thirty_days_ago).count()
    prev_calls = db.query(UsageLog).filter(
        UsageLog.created_at >= sixty_days_ago,
        UsageLog.created_at < thirty_days_ago
    ).count()

    recent_sessions = db.query(UserSession).filter(UserSession.created_at >= thirty_days_ago).count()
    prev_sessions = db.query(UserSession).filter(
        UserSession.created_at >= sixty_days_ago,
        UserSession.created_at < thirty_days_ago
    ).count()

    # Calculate change percentages
    user_change = round(((total_users - prev_users) / max(prev_users, 1)) * 100, 1) if prev_users else 0.0
    session_change = round(((recent_sessions - prev_sessions) / max(prev_sessions, 1)) * 100, 1) if prev_sessions else 0.0
    doc_change = round(((total_documents - prev_docs) / max(prev_docs, 1)) * 100, 1) if prev_docs else 0.0
    api_change = round(((recent_calls - prev_calls) / max(prev_calls, 1)) * 100, 1) if prev_calls else 0.0

    return {
        "total_users": total_users,
        "active_sessions": active_sessions,
        "total_documents": total_documents,
        "api_calls": api_calls,
        "user_change": user_change,
        "session_change": session_change,
        "doc_change": doc_change,
        "api_change": api_change,
        # Legacy aliases
        "active_users": db.query(User).filter(User.status == "active").count(),
        "total_queries": api_calls,
        "queries_last_30_days": recent_calls,
        "generated_at": now.isoformat()
    }


@router.get("/summary")
def get_reports_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get overall system reports summary (alias for stats)"""
    return get_reports_stats(db=db, current_user=current_user)


@router.get("/usage-over-time")
def get_usage_over_time(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get usage statistics over time"""
    start_date = datetime.utcnow() - timedelta(days=days)

    usage_data = db.query(
        func.date(UsageLog.created_at).label("date"),
        func.count(UsageLog.id).label("count")
    ).filter(
        UsageLog.created_at >= start_date
    ).group_by(
        func.date(UsageLog.created_at)
    ).order_by(
        func.date(UsageLog.created_at)
    ).all()

    return {
        "period_days": days,
        "data": [{"date": str(row.date), "count": row.count} for row in usage_data]
    }


@router.get("/top-users")
def get_top_users(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get top users by query count"""
    top_users = db.query(
        UsageLog.user_id,
        User.username,
        User.email,
        func.count(UsageLog.id).label("query_count")
    ).join(
        User, UsageLog.user_id == User.id
    ).group_by(
        UsageLog.user_id, User.username, User.email
    ).order_by(
        func.count(UsageLog.id).desc()
    ).limit(limit).all()

    return [
        {
            "user_id": row.user_id,
            "username": row.username,
            "email": row.email,
            "query_count": row.query_count
        }
        for row in top_users
    ]


@router.get("/system-health")
def get_system_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get system health report"""
    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    one_day_ago = now - timedelta(days=1)

    queries_last_hour = db.query(UsageLog).filter(
        UsageLog.created_at >= one_hour_ago
    ).count()

    queries_last_day = db.query(UsageLog).filter(
        UsageLog.created_at >= one_day_ago
    ).count()

    audit_events_today = db.query(AuditLog).filter(
        AuditLog.created_at >= one_day_ago
    ).count()

    # Test database connectivity
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    return {
        "status": "healthy",
        "database": db_status,
        "uptime_percent": 99.9,
        "queries_last_hour": queries_last_hour,
        "queries_last_24h": queries_last_day,
        "audit_events_today": audit_events_today,
        "last_checked": now.isoformat(),
        "timestamp": now.isoformat()
    }


@router.get("/export")
def export_report(
    report_type: str = Query(default="usage", enum=["usage", "users", "audit"]),
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export report data as JSON"""
    start_date = datetime.utcnow() - timedelta(days=days)

    if report_type == "usage":
        records = db.query(UsageLog).filter(
            UsageLog.created_at >= start_date
        ).order_by(UsageLog.created_at.desc()).all()
        data = [
            {
                "id": r.id,
                "user_id": r.user_id,
                "action_type": r.action_type,
                "module": r.module,
                "response_time_ms": r.response_time_ms,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in records
        ]
    elif report_type == "users":
        records = db.query(User).all()
        data = [
            {
                "id": r.id,
                "username": r.username,
                "email": r.email,
                "role": r.role,
                "status": r.status,
                "department": r.department,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in records
        ]
    elif report_type == "audit":
        records = db.query(AuditLog).filter(
            AuditLog.created_at >= start_date
        ).order_by(AuditLog.created_at.desc()).all()
        data = [
            {
                "id": r.id,
                "user_id": r.user_id,
                "action": r.action,
                "resource_type": r.resource_type,
                "resource_id": r.resource_id,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in records
        ]
    else:
        raise HTTPException(status_code=400, detail="Invalid report type")

    return {
        "report_type": report_type,
        "period_days": days,
        "record_count": len(data),
        "exported_at": datetime.utcnow().isoformat(),
        "data": data
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  COMPLIANCE REPORT OVERSIGHT (SOTR Module 3)
# ═══════════════════════════════════════════════════════════════════════════════

from app.models.models import LegacyComplianceReport as ComplianceReport, HistoricalFeedback


@router.get("/compliance")
def list_compliance_reports(
    skip: int = 0,
    limit: int = 50,
    verdict: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all SOTR compliance evaluation reports for oversight"""
    query = db.query(ComplianceReport)
    
    if verdict:
        query = query.filter(ComplianceReport.verdict == verdict.upper())
    if status:
        query = query.filter(ComplianceReport.status == status.lower())
    
    total = query.count()
    reports = query.order_by(ComplianceReport.created_at.desc()).offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "reports": [
            {
                "id": r.id,
                "report_name": r.report_name,
                "sotr_doc": {
                    "id": r.sotr_doc.id if r.sotr_doc else None,
                    "filename": r.sotr_doc.original_filename if r.sotr_doc else None
                },
                "submission_doc": {
                    "id": r.submission_doc.id if r.submission_doc else None,
                    "filename": r.submission_doc.original_filename if r.submission_doc else None
                },
                "generated_by": r.generator.username if r.generator else "unknown",
                "total_clauses": r.total_clauses,
                "compliant_count": r.compliant_count,
                "partial_count": r.partial_count,
                "non_compliant_count": r.non_compliant_count,
                "unverifiable_count": r.unverifiable_count,
                "compliance_score": round(r.compliance_score, 1),
                "verdict": r.verdict,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in reports
        ]
    }


@router.get("/compliance/{report_id}")
def get_compliance_report_detail(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get detailed compliance report with clause breakdown"""
    report = db.query(ComplianceReport).filter(ComplianceReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    # Get associated historical feedback
    feedback = db.query(HistoricalFeedback).filter(
        HistoricalFeedback.compliance_report_id == report_id
    ).order_by(HistoricalFeedback.clause_id).all()
    
    return {
        "id": report.id,
        "report_name": report.report_name,
        "sotr_doc": {
            "id": report.sotr_doc.id if report.sotr_doc else None,
            "filename": report.sotr_doc.original_filename if report.sotr_doc else None,
            "category": report.sotr_doc.category if report.sotr_doc else None
        },
        "submission_doc": {
            "id": report.submission_doc.id if report.submission_doc else None,
            "filename": report.submission_doc.original_filename if report.submission_doc else None,
            "category": report.submission_doc.category if report.submission_doc else None
        },
        "generated_by": report.generator.username if report.generator else "unknown",
        "metrics": {
            "total_clauses": report.total_clauses,
            "compliant_count": report.compliant_count,
            "partial_count": report.partial_count,
            "non_compliant_count": report.non_compliant_count,
            "unverifiable_count": report.unverifiable_count,
            "compliance_score": round(report.compliance_score, 1)
        },
        "verdict": report.verdict,
        "status": report.status,
        "report_file_path": report.report_file_path,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "historical_feedback": [
            {
                "id": f.id,
                "clause_id": f.clause_id,
                "clause_reference": f.clause_reference,
                "feedback_text": f.feedback_text,
                "severity": f.severity,
                "referenced_sotr": f.referenced_sotr.original_filename if f.referenced_sotr else None,
                "created_at": f.created_at.isoformat() if f.created_at else None
            }
            for f in feedback
        ]
    }


@router.get("/compliance/{report_id}/feedback")
def get_historical_feedback(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get historical feedback audit trail for a compliance report"""
    report = db.query(ComplianceReport).filter(ComplianceReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    feedback = db.query(HistoricalFeedback).filter(
        HistoricalFeedback.compliance_report_id == report_id
    ).order_by(HistoricalFeedback.created_at.desc()).all()
    
    return {
        "report_id": report_id,
        "report_name": report.report_name,
        "total_feedback_entries": len(feedback),
        "feedback": [
            {
                "id": f.id,
                "clause_id": f.clause_id,
                "clause_reference": f.clause_reference,
                "feedback_text": f.feedback_text,
                "severity": f.severity,
                "referenced_sotr_id": f.referenced_sotr_id,
                "referenced_sotr_filename": f.referenced_sotr.original_filename if f.referenced_sotr else None,
                "created_at": f.created_at.isoformat() if f.created_at else None
            }
            for f in feedback
        ]
    }


@router.get("/compliance/stats/overview")
def get_compliance_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get compliance report statistics for dashboard"""
    total_reports = db.query(ComplianceReport).count()
    
    # Verdict distribution
    verdict_counts = db.query(
        ComplianceReport.verdict,
        func.count(ComplianceReport.id)
    ).group_by(ComplianceReport.verdict).all()
    
    # Average compliance score
    avg_score = db.query(func.avg(ComplianceReport.compliance_score)).scalar() or 0
    
    # Recent reports (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_reports = db.query(ComplianceReport).filter(
        ComplianceReport.created_at >= thirty_days_ago
    ).count()
    
    return {
        "total_reports": total_reports,
        "recent_reports_30d": recent_reports,
        "average_compliance_score": round(avg_score, 1),
        "verdict_distribution": {
            v: c for v, c in verdict_counts
        },
        "generated_at": datetime.utcnow().isoformat()
    }
