from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

from app.database import get_db
from app.models.models import User, UsageLog, Document
from app.routers.auth import require_superadmin, get_current_user

router = APIRouter()


@router.get("/analytics")
def get_analytics(
    period: str = Query(default="7d", pattern="^(24h|7d|30d|90d)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get usage analytics for a time period"""
    period_days = {"24h": 1, "7d": 7, "30d": 30, "90d": 90}.get(period, 7)
    start_date = datetime.utcnow() - timedelta(days=period_days)

    # Previous period for calculating change percentages
    prev_start = start_date - timedelta(days=period_days)

    total_calls = db.query(UsageLog).filter(UsageLog.created_at >= start_date).count()
    prev_calls = db.query(UsageLog).filter(
        UsageLog.created_at >= prev_start, UsageLog.created_at < start_date
    ).count()

    active_users = db.query(UsageLog.user_id).filter(UsageLog.created_at >= start_date).distinct().count()
    prev_active = db.query(UsageLog.user_id).filter(
        UsageLog.created_at >= prev_start, UsageLog.created_at < start_date
    ).distinct().count()

    avg_response_time = db.query(func.avg(UsageLog.response_time_ms)).filter(
        UsageLog.created_at >= start_date
    ).scalar() or 0

    # Calculate change percentages
    calls_change = round(((total_calls - prev_calls) / max(prev_calls, 1)) * 100, 1)
    users_change = round(((active_users - prev_active) / max(prev_active, 1)) * 100, 1)

    # Top users
    top_users_data = db.query(
        UsageLog.user_id,
        func.count(UsageLog.id).label("count")
    ).filter(
        UsageLog.created_at >= start_date
    ).group_by(UsageLog.user_id).order_by(func.count(UsageLog.id).desc()).limit(10).all()

    top_users = []
    for row in top_users_data:
        user = db.query(User).filter(User.id == row.user_id).first()
        top_users.append({
            "id": row.user_id,
            "name": user.full_name or user.username if user else "unknown",
            "username": user.username if user else "unknown",
            "requests": row.count,
            "last_active": user.last_login if user else None
        })

    return {
        "period": period,
        "total_calls": total_calls,
        "active_users": active_users,
        "avg_response_time": round(avg_response_time, 2),
        "uptime": 99.9,
        "calls_change": calls_change,
        "users_change": users_change,
        "top_users": top_users,
        "top_agents": []
    }


class UsageLogEntry(BaseModel):
    """Schema for agent-submitted usage log events."""
    action_type: str               # e.g. 'chat', 'ppt', 'quiz', 'summary'
    module: Optional[str] = None   # e.g. 'rag', 'generate'
    input_tokens: int = 0
    output_tokens: int = 0
    response_time_ms: float = 0.0
    status: str = "success"        # 'success' | 'error'
    user_id: Optional[int] = None  # Override if not pulling from JWT
    metadata_: Optional[str] = None  # e.g. raw user question text


@router.post("/log", status_code=201)
def log_usage(
    entry: UsageLogEntry,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Accept a usage log event from the agent service.
    Called by the agent after every successful generation.
    Previously caused 405 because there was no POST handler.
    """
    log = UsageLog(
        user_id=entry.user_id or current_user.id,
        action_type=entry.action_type,
        module=entry.module,
        input_tokens=entry.input_tokens,
        output_tokens=entry.output_tokens,
        response_time_ms=entry.response_time_ms,
        status=entry.status,
        metadata_=entry.metadata_,
    )
    db.add(log)
    db.commit()
    return {"logged": True, "log_id": log.id}


@router.get("/")
def get_usage_logs(
    skip: int = 0,
    limit: int = 50,
    user_id: Optional[int] = None,
    action_type: Optional[str] = None,
    module: Optional[str] = None,
    status: Optional[str] = None,
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    """List usage logs with filters"""
    since = datetime.utcnow() - timedelta(days=days)
    query = db.query(UsageLog).filter(UsageLog.created_at >= since)

    if user_id:
        query = query.filter(UsageLog.user_id == user_id)
    if action_type:
        query = query.filter(UsageLog.action_type == action_type)
    if module:
        query = query.filter(UsageLog.module == module)
    if status:
        query = query.filter(UsageLog.status == status)

    total = query.count()
    logs = query.order_by(UsageLog.created_at.desc()).offset(skip).limit(limit).all()

    result = []
    for log in logs:
        user = db.query(User).filter(User.id == log.user_id).first()
        result.append({
            "id": log.id,
            "user": user.username if user else "unknown",
            "user_id": log.user_id,
            "action_type": log.action_type,
            "module": log.module,
            "input_tokens": log.input_tokens,
            "output_tokens": log.output_tokens,
            "response_time_ms": log.response_time_ms,
            "status": log.status,
            "metadata_": log.metadata_,
            "created_at": log.created_at
        })
    return {"total": total, "logs": result}


@router.get("/summary")
def get_usage_summary(
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    """Summary statistics for usage over a period"""
    since = datetime.utcnow() - timedelta(days=days)

    total_queries = db.query(UsageLog).filter(UsageLog.created_at >= since).count()

    avg_response_time = db.query(func.avg(UsageLog.response_time_ms)).filter(
        UsageLog.created_at >= since
    ).scalar() or 0

    total_logs = db.query(UsageLog).filter(UsageLog.created_at >= since).count()
    success_count = db.query(UsageLog).filter(
        UsageLog.created_at >= since,
        UsageLog.status == "success"
    ).count()
    success_rate = round((success_count / max(total_logs, 1)) * 100, 1)

    # Top modules
    top_modules_data = db.query(
        UsageLog.module,
        func.count(UsageLog.id).label("count")
    ).filter(
        UsageLog.created_at >= since,
        UsageLog.module.isnot(None)
    ).group_by(UsageLog.module).order_by(func.count(UsageLog.id).desc()).limit(10).all()

    top_modules = [{"module": row.module or "unknown", "count": row.count} for row in top_modules_data]

    # Daily counts
    daily_data = db.query(
        func.date(UsageLog.created_at).label("date"),
        func.count(UsageLog.id).label("count")
    ).filter(
        UsageLog.created_at >= since
    ).group_by(func.date(UsageLog.created_at)).order_by(func.date(UsageLog.created_at)).all()

    daily_counts = [{"date": str(row.date), "count": row.count} for row in daily_data]

    return {
        "total_queries": total_queries,
        "avg_response_time_ms": round(avg_response_time, 2),
        "success_rate": success_rate,
        "top_modules": top_modules,
        "daily_counts": daily_counts,
        # Legacy fields for backward compatibility
        "period_days": days,
        "user_summary": []
    }


@router.get("/top-users")
def get_top_users(
    limit: int = 10,
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    """Top users by usage count"""
    since = datetime.utcnow() - timedelta(days=days)
    top = db.query(
        UsageLog.user_id,
        func.count(UsageLog.id).label("count")
    ).filter(
        UsageLog.created_at >= since
    ).group_by(UsageLog.user_id).order_by(func.count(UsageLog.id).desc()).limit(limit).all()

    users_list = []
    for row in top:
        user = db.query(User).filter(User.id == row.user_id).first()
        users_list.append({
            "user_id": row.user_id,
            "username": user.username if user else "unknown",
            "department": user.department if user else None,
            "count": row.count,
            "last_active": user.last_login.isoformat() if user and user.last_login else None
        })
    return {"users": users_list}
