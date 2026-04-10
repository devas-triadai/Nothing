import bcrypt
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
import os
from pathlib import Path
from dotenv import dotenv_values

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
_env_config = dotenv_values(str(_ENV_PATH)) if _ENV_PATH.exists() else {}

SECRET_KEY = (
    _env_config.get("SECRET_KEY") 
    or os.getenv("SECRET_KEY") 
    or "agra-icg-super-secret-key-2026-hq-jwt-token-change-in-production"
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(_env_config.get("ACCESS_TOKEN_EXPIRE_MINUTES") or os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES") or "480")


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt directly (avoids passlib/bcrypt version conflicts)."""
    password_bytes = password.encode("utf-8")[:72]  # bcrypt max is 72 bytes
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        password_bytes = plain_password.encode("utf-8")[:72]
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
