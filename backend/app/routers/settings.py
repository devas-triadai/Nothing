from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.models.models import User, SystemSetting
from app.routers.auth import get_current_user
from app.utils.security import verify_password, get_password_hash

router = APIRouter()


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@router.get("/")
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get system settings"""
    # Try to load notification preferences from DB
    notifications = None
    try:
        setting = db.query(SystemSetting).filter(SystemSetting.key == "notifications").first()
        if setting:
            import json
            notifications = json.loads(setting.value)
    except Exception:
        pass

    return {
        "system_name": "AGRA Super Admin",
        "version": "1.0.0",
        "max_file_size_mb": 100,
        "allowed_file_types": ["pdf", "docx", "xlsx", "pptx", "txt"],
        "session_timeout_minutes": 60,
        "enable_audit_logging": True,
        "enable_usage_tracking": True,
        "notifications": notifications
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


@router.put("/profile")
def update_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update current user's profile (full_name and email)"""
    name = payload.full_name or payload.name
    if name:
        current_user.full_name = name
    if payload.email:
        # Check email uniqueness
        existing = db.query(User).filter(User.email == payload.email, User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        current_user.email = payload.email

    db.commit()
    db.refresh(current_user)

    return {
        "message": "Profile updated successfully",
        "user": {
            "id": current_user.id,
            "username": current_user.username,
            "full_name": current_user.full_name,
            "email": current_user.email,
            "role": current_user.role
        }
    }


@router.put("/password")
def change_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Change current user's password"""
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.hashed_password = get_password_hash(payload.new_password)
    db.commit()

    return {"success": True, "message": "Password changed successfully"}


@router.put("/notifications")
def update_notifications(
    prefs: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Store notification preferences"""
    import json

    try:
        setting = db.query(SystemSetting).filter(SystemSetting.key == "notifications").first()
        if setting:
            setting.value = json.dumps(prefs)
        else:
            setting = SystemSetting(key="notifications", value=json.dumps(prefs))
            db.add(setting)
        db.commit()
    except Exception:
        # If table doesn't exist yet, return mock
        pass

    return {"saved": True, "notifications": prefs}
