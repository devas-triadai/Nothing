from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models.models import User
from app.routers.auth import get_current_user

router = APIRouter()


@router.get("/")
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get system settings"""
    return {
        "system_name": "AGRA Super Admin",
        "version": "1.0.0",
        "max_file_size_mb": 100,
        "allowed_file_types": ["pdf", "docx", "xlsx", "pptx", "txt"],
        "session_timeout_minutes": 60,
        "enable_audit_logging": True,
        "enable_usage_tracking": True
    }


@router.put("/")
def update_settings(
    settings: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update system settings"""
    # In a real implementation, this would save to a settings table
    return {"message": "Settings updated successfully", "settings": settings}
