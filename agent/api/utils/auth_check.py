"""
AGRA Phase 2 — Agent API: JWT Authentication Utility
Validates Bearer tokens issued by the Phase 1 admin backend (port 8000).
Reads the shared SECRET_KEY from backend/.env so both services stay in sync.
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from dotenv import dotenv_values

# ── Locate the shared .env from the admin backend ──
# Agent lives at Nothing/agent/api/utils/auth_check.py
# Backend .env at Nothing/backend/.env
_THIS_DIR = Path(__file__).resolve().parent
_BACKEND_ENV = _THIS_DIR.parent.parent.parent / "backend" / ".env"

# Try loading from backend/.env first, fall back to env vars / defaults
_env_config = dotenv_values(str(_BACKEND_ENV)) if _BACKEND_ENV.exists() else {}

SECRET_KEY: str = (
    _env_config.get("SECRET_KEY")
    or os.getenv("SECRET_KEY")
    or "agra-icg-super-secret-key-2026-hq-jwt-token"
)
ALGORITHM: str = os.getenv("ALGORITHM", "HS256")

# FastAPI security scheme (expects "Authorization: Bearer <token>")
_bearer_scheme = HTTPBearer(auto_error=False)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token. Returns the payload dict or None."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """
    FastAPI dependency that extracts and validates the JWT from the
    Authorization header.

    Returns the full JWT payload on success (contains at minimum:
      - sub: username
      - exp: expiration timestamp
    ).

    Raises HTTP 401 if the token is missing, expired, or invalid.
    """
    # 1. Try explicit Authorization header
    token: Optional[str] = None
    if credentials and credentials.credentials:
        token = credentials.credentials

    # 2. Fallback: check query param (for SSE/EventSource which can't set headers)
    if not token:
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required — no token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing 'sub' (username)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


# ── RBAC Helper Functions ──

# Clearance levels: 1=Unclassified, 2=Confidential, 3=Secret, 4=Top Secret
CLEARANCE_LEVELS = {1: "Unclassified", 2: "Confidential", 3: "Secret", 4: "Top Secret"}


def get_user_clearance(user: dict) -> int:
    """Extract clearance level from JWT payload. Defaults to 1 (Unclassified)."""
    return user.get("clearance_level", 1)


def get_user_role(user: dict) -> str:
    """Extract role from JWT payload. Defaults to 'viewer'."""
    return user.get("role", "viewer")


def is_superadmin(user: dict) -> bool:
    """Check if user is superadmin from JWT payload."""
    return user.get("is_superadmin", False)


def can_access_document(user: dict, doc_clearance: int) -> bool:
    """Check if user can access a document based on clearance level."""
    # Super admins can access everything
    if is_superadmin(user):
        return True
    # Check clearance level
    user_clearance = get_user_clearance(user)
    return user_clearance >= doc_clearance


def filter_documents_by_access(user: dict, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter a list of documents based on user's role and clearance level.
    
    - Super Admin: Can see all documents
    - Admin: Can see documents with clearance <= 2 (Confidential)
    - Officer: Can see documents with clearance <= 2 (Confidential)
    - Viewer: Can see documents with clearance <= 1 (Unclassified)
    """
    if is_superadmin(user):
        return documents  # Super admins see everything
    
    role = get_user_role(user)
    user_clearance = get_user_clearance(user)
    
    # Role-based clearance limits
    role_clearance_limits = {
        "super_admin": 4,  # Top Secret
        "admin": 2,        # Confidential
        "officer": 2,      # Confidential
        "viewer": 1,       # Unclassified
    }
    
    max_clearance = role_clearance_limits.get(role, 1)
    effective_clearance = min(user_clearance, max_clearance)
    
    # Filter documents
    filtered = []
    for doc in documents:
        doc_clearance = doc.get("clearance_level", 1)
        if doc_clearance <= effective_clearance:
            filtered.append(doc)
    
    return filtered
