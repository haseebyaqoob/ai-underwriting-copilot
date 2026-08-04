import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=settings.BCRYPT_ROUNDS)


# ---------------------------------------------------------------- passwords
def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


# --------------------------------------------------------------- access JWT
def create_access_token(*, user_id: str, role: str, org_id: str | None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "org_id": org_id,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises jose.JWTError on any invalid/expired/tampered token."""
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    if payload.get("type") != "access":
        raise JWTError("Not an access token")
    return payload


# -------------------------------------------------------------- refresh token
# Refresh tokens are opaque random strings, NOT JWTs — we only ever need to
# look them up by hash in `refresh_tokens`, we don't need them to carry
# claims. Storing only the hash means a DB dump alone can't be replayed.
def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)


# ------------------------------------------------------------------ WS token
# Module 3: `/ws?token=...` deliberately does NOT accept the long-lived
# access token as a query parameter — query params end up in server logs,
# browser history, and Referer headers, which is fine for a 15-minute
# access token's blast radius but not something we want to widen. A
# separate, very-short-lived, single-purpose token type keeps that
# exposure minimal: even if it leaks via a log line, it's expired within a
# minute and can't be used for anything but opening a socket.
def create_ws_token(*, user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "ws",
        "iat": now,
        "exp": now + timedelta(seconds=60),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_ws_token(token: str) -> dict:
    """Raises jose.JWTError on any invalid/expired/tampered token."""
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    if payload.get("type") != "ws":
        raise JWTError("Not a ws token")
    return payload
