from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

from app.database import get_db
from app.models.models import User, UserSession, AuditLog
from app.utils.security import verify_password, create_access_token, decode_access_token

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user


def require_superadmin(current_user: User = Depends(get_current_user)):
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin access required"
        )
    return current_user


@router.post("/login")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active"
        )

    access_token = create_access_token(data={"sub": user.username, "role": user.role})

    # Update last login
    user.last_login = datetime.utcnow()

    # Create session record
    session = UserSession(
        user_id=user.id,
        session_token=access_token,
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", "unknown"),
        is_active=True,
        expires_at=datetime.utcnow() + timedelta(hours=8)
    )
    db.add(session)

    # Audit log
    audit = AuditLog(
        user_id=user.id,
        action="LOGIN",
        resource_type="auth",
        ip_address=request.client.host if request.client else "unknown",
        status="success"
    )
    db.add(audit)
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
            "is_superadmin": user.is_superadmin,
            "department": user.department,
            "rank": user.rank
        }
    }


@router.post("/logout")
def logout(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    session = db.query(UserSession).filter(
        UserSession.session_token == token,
        UserSession.is_active == True
    ).first()
    if session:
        session.is_active = False
        session.ended_at = datetime.utcnow()

    audit = AuditLog(
        user_id=current_user.id,
        action="LOGOUT",
        resource_type="auth",
        status="success"
    )
    db.add(audit)
    db.commit()
    return {"message": "Logged out successfully"}


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "role": current_user.role,
        "is_superadmin": current_user.is_superadmin,
        "department": current_user.department,
        "rank": current_user.rank,
        "last_login": current_user.last_login
    }
