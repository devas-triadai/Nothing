from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta

from app.database import get_db
from app.models.models import User, UsageLog, AuditLog, Document, UserSession
from app.routers.auth import require_superadmin

router = APIRouter()


@router.get("/stats")
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)
    last_30d = now - timedelta(days=30)

    # User stats
    total_users = db.query(User).filter(User.is_superadmin == False).count()
    active_users = db.query(User).filter(User.status == "active", User.is_superadmin == False).count()
    new_users_30d = db.query(User).filter(User.created_at >= last_30d).count()

    # Active sessions
    active_sessions = db.query(UserSession).filter(
        UserSession.is_active == True,
        UserSession.expires_at > now
    ).count()

    # Usage stats
    total_queries = db.query(UsageLog).filter(UsageLog.action_type == "query").count()
    queries_24h = db.query(UsageLog).filter(
        UsageLog.action_type == "query",
        UsageLog.created_at >= last_24h
    ).count()
    ppts_generated = db.query(UsageLog).filter(UsageLog.action_type == "ppt_generate").count()
    ppts_7d = db.query(UsageLog).filter(
        UsageLog.action_type == "ppt_generate",
        UsageLog.created_at >= last_7d
    ).count()

    # Document stats
    total_docs = db.query(Document).count()
    indexed_docs = db.query(Document).filter(Document.status == "indexed").count()

    # Avg response time
    avg_response = db.query(func.avg(UsageLog.response_time_ms)).scalar() or 0

    # Daily usage for chart (last 7 days)
    daily_usage = []
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        count = db.query(UsageLog).filter(
            UsageLog.created_at >= day_start,
            UsageLog.created_at < day_end
        ).count()
        daily_usage.append({
            "date": day_start.strftime("%d %b"),
            "queries": count
        })

    # Usage by module
    module_usage = db.query(
        UsageLog.module,
        func.count(UsageLog.id).label("count")
    ).group_by(UsageLog.module).all()

    return {
        "users": {
            "total": total_users,
            "active": active_users,
            "new_30d": new_users_30d,
            "active_sessions": active_sessions
        },
        "usage": {
            "total_queries": total_queries,
            "queries_24h": queries_24h,
            "ppts_generated": ppts_generated,
            "ppts_7d": ppts_7d,
            "avg_response_ms": round(avg_response, 2)
        },
        "documents": {
            "total": total_docs,
            "indexed": indexed_docs
        },
        "charts": {
            "daily_usage": daily_usage,
            "module_usage": [
                {"module": m or "unknown", "count": c}
                for m, c in module_usage
            ]
        }
    }


@router.get("/activity")
def get_recent_activity(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    recent_logs = db.query(AuditLog).order_by(
        AuditLog.created_at.desc()
    ).limit(limit).all()

    result = []
    for log in recent_logs:
        user = db.query(User).filter(User.id == log.user_id).first()
        result.append({
            "id": log.id,
            "action": log.action,
            "user": user.username if user else "system",
            "resource_type": log.resource_type,
            "status": log.status,
            "created_at": log.created_at
        })
    return result
