from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import Optional, List
from app.database import get_db
from app.models.models import UsageLog, User, AuditLog, Document
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
            "name": "System Usage Report",
            "type": "usage",
            "created_at": datetime.utcnow(),
            "status": "completed"
        },
        {
            "id": 2,
            "name": "User Activity Report",
            "type": "users",
            "created_at": datetime.utcnow(),
            "status": "completed"
        },
        {
            "id": 3,
            "name": "Document Index Report",
            "type": "documents",
            "created_at": datetime.utcnow(),
            "status": "completed"
        }
    ]
    return {"reports": reports, "total": len(reports)}


@router.get("/stats")
def get_reports_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get reports statistics (alias for summary)"""
    return get_reports_summary(db, current_user)


@router.get("/summary")
def get_reports_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get overall system reports summary"""
    from app.models.models import UserSession
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.status == "active").count()
    total_queries = db.query(UsageLog).count()
    total_documents = db.query(Document).count()

    # Active sessions count
    active_sessions = db.query(UserSession).filter(UserSession.is_active == True).count()

    # Last 30 days stats
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_queries = db.query(UsageLog).filter(
        UsageLog.created_at >= thirty_days_ago
    ).count()

    return {
        "total_users": total_users,
        "active_users": active_users,
        "active_sessions": active_sessions,
        "total_queries": total_queries,
        "total_documents": total_documents,
        "api_calls": total_queries,
        "queries_last_30_days": recent_queries,
        "generated_at": datetime.utcnow().isoformat()
    }


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

    return {
        "status": "healthy",
        "queries_last_hour": queries_last_hour,
        "queries_last_24h": queries_last_day,
        "audit_events_today": audit_events_today,
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
