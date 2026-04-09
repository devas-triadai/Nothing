from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import datetime, timedelta

from app.database import get_db
from app.models.models import User, UsageLog, Document
from app.routers.auth import require_superadmin, get_current_user

router = APIRouter()


@router.get("/analytics")
def get_analytics(
    period: str = Query(default="7d", regex="^(24h|7d|30d|90d)$"),
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
            "name": user.username if user else "unknown",
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


@router.get("/")
def get_usage_logs(
    skip: int = 0,
    limit: int = 50,
    user_id: Optional[int] = None,
    action_type: Optional[str] = None,
    module: Optional[str] = None,
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    since = datetime.utcnow() - timedelta(days=days)
    query = db.query(UsageLog).filter(UsageLog.created_at >= since)

    if user_id:
        query = query.filter(UsageLog.user_id == user_id)
    if action_type:
        query = query.filter(UsageLog.action_type == action_type)
    if module:
        query = query.filter(UsageLog.module == module)

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
            "created_at": log.created_at
        })
    return {"total": total, "logs": result}


@router.get("/summary")
def get_usage_summary(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    since = datetime.utcnow() - timedelta(days=days)

    # Per user usage
    user_usage = db.query(
        UsageLog.user_id,
        func.count(UsageLog.id).label("total_actions"),
        func.sum(UsageLog.input_tokens).label("total_input_tokens"),
        func.sum(UsageLog.output_tokens).label("total_output_tokens"),
        func.avg(UsageLog.response_time_ms).label("avg_response_ms")
    ).filter(UsageLog.created_at >= since).group_by(UsageLog.user_id).all()

    result = []
    for row in user_usage:
        user = db.query(User).filter(User.id == row.user_id).first()
        result.append({
            "user_id": row.user_id,
            "username": user.username if user else "unknown",
            "full_name": user.full_name if user else "unknown",
            "total_actions": row.total_actions,
            "total_input_tokens": row.total_input_tokens or 0,
            "total_output_tokens": row.total_output_tokens or 0,
            "avg_response_ms": round(row.avg_response_ms or 0, 2)
        })

    return {"period_days": days, "user_summary": result}


@router.get("/top-users")
def get_top_users(
    limit: int = 10,
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    since = datetime.utcnow() - timedelta(days=days)
    top = db.query(
        UsageLog.user_id,
        func.count(UsageLog.id).label("count")
    ).filter(
        UsageLog.created_at >= since
    ).group_by(UsageLog.user_id).order_by(func.count(UsageLog.id).desc()).limit(limit).all()

    result = []
    for row in top:
        user = db.query(User).filter(User.id == row.user_id).first()
        result.append({
            "user_id": row.user_id,
            "username": user.username if user else "unknown",
            "department": user.department if user else None,
            "count": row.count
        })
    return result
