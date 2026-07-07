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

