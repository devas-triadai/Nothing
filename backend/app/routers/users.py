from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.models.models import User, AuditLog
from app.utils.security import get_password_hash
from app.routers.auth import require_superadmin

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    email: str
    full_name: str
    password: str
    role: str = "viewer"
    department: Optional[str] = None
    rank: Optional[str] = None
    service_number: Optional[str] = None


class UserUpdate(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    department: Optional[str] = None
    rank: Optional[str] = None
    service_number: Optional[str] = None


class PasswordChange(BaseModel):
    new_password: str


@router.get("/")
def list_users(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    role: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    query = db.query(User)
    if search:
        query = query.filter(
            (User.username.ilike(f"%{search}%")) |
            (User.full_name.ilike(f"%{search}%")) |
            (User.email.ilike(f"%{search}%"))
        )
    if role:
        query = query.filter(User.role == role)
    if status:
        query = query.filter(User.status == status)

    total = query.count()
    users = query.offset(skip).limit(limit).all()

    return {
        "total": total,
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role,
                "status": u.status,
                "department": u.department,
                "rank": u.rank,
                "service_number": u.service_number,
                "is_superadmin": u.is_superadmin,
                "last_login": u.last_login,
                "created_at": u.created_at
            } for u in users
        ]
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")

    new_user = User(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=get_password_hash(user_data.password),
        role=user_data.role,
        department=user_data.department,
        rank=user_data.rank,
        service_number=user_data.service_number,
        status="active"
    )
    db.add(new_user)

    audit = AuditLog(
        user_id=current_user.id,
        action="CREATE_USER",
        resource_type="user",
        new_value=user_data.username,
        status="success"
    )
    db.add(audit)
    db.commit()
    db.refresh(new_user)
    return {"message": "User created successfully", "user_id": new_user.id}


@router.get("/{user_id}")
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "status": user.status,
        "department": user.department,
        "rank": user.rank,
        "service_number": user.service_number,
        "is_superadmin": user.is_superadmin,
        "last_login": user.last_login,
        "created_at": user.created_at
    }


@router.put("/{user_id}")
def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_superadmin and user.id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot modify super admin")

    update_data = user_data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)
    user.updated_at = datetime.utcnow()

    audit = AuditLog(
        user_id=current_user.id,
        action="UPDATE_USER",
        resource_type="user",
        resource_id=str(user_id),
        status="success"
    )
    db.add(audit)
    db.commit()
    return {"message": "User updated successfully"}


@router.put("/{user_id}/password")
def change_password(
    user_id: int,
    pwd_data: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.hashed_password = get_password_hash(pwd_data.new_password)
    db.commit()
    return {"message": "Password changed successfully"}


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_superadmin:
        raise HTTPException(status_code=403, detail="Cannot delete super admin")

    db.delete(user)
    audit = AuditLog(
        user_id=current_user.id,
        action="DELETE_USER",
        resource_type="user",
        resource_id=str(user_id),
        old_value=user.username,
        status="success"
    )
    db.add(audit)
    db.commit()
    return {"message": "User deleted successfully"}
