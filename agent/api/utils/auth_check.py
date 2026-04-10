"""
AGRA Phase 2 — Agent API: JWT Authentication Utility
Validates Bearer tokens issued by the Phase 1 admin backend (port 8000).
Reads the shared SECRET_KEY from backend/.env so both services stay in sync.
"""

import os
from pathlib import Path
from typing import Optional

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
    or "agra-icg-super-secret-key-2026-hq-jwt-token-change-in-production"
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
