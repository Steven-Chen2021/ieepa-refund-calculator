"""
FastAPI dependency factories
=============================
All reusable Depends() callables live here.

Exported
--------
get_db          — async SQLAlchemy session (re-exported from db.session)
get_redis       — async Redis client
get_current_user   — decodes Bearer JWT; raises 401 on failure
get_optional_user  — like get_current_user but returns None for guests
require_admin      — get_current_user + role == admin check (403 otherwise)
"""
from __future__ import annotations

from typing import Annotated

import jwt
import redis.asyncio as aioredis
from fastapi import Cookie, Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.session import get_db  # noqa: F401 — re-exported for convenience

# ── Re-export DBSession type alias ────────────────────────────────────────────
DBSession = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Redis dependency
# ---------------------------------------------------------------------------

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return the shared async Redis client (lazily initialised)."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_pool


RedisClient = Annotated[aioredis.Redis, Depends(get_redis)]


# ---------------------------------------------------------------------------
# Token payload schema
# ---------------------------------------------------------------------------

class TokenPayload(BaseModel):
    sub: str        # user UUID
    role: str       # "user" | "admin"
    email: str
    iat: int | None = None
    exp: int | None = None


# ---------------------------------------------------------------------------
# JWT Bearer authentication
# ---------------------------------------------------------------------------

_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/token",
    auto_error=False,   # we raise our own exceptions
)


async def get_current_user(
    token: str | None = Depends(_oauth2_scheme),
) -> TokenPayload:
    """
    FastAPI dependency that requires a valid Bearer JWT.

    Raises
    ------
    HTTP 401 — missing, expired, or invalid token.
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(token)
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (jwt.InvalidTokenError, Exception):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]


async def get_optional_user(
    token: str | None = Depends(_oauth2_scheme),
) -> TokenPayload | None:
    """
    Like get_current_user but returns None for unauthenticated guests.
    Used on public endpoints that have optional user-level features.
    """
    if token is None:
        return None
    try:
        payload = decode_access_token(token)
        return TokenPayload(**payload)
    except Exception:
        return None


OptionalUser = Annotated[TokenPayload | None, Depends(get_optional_user)]


async def require_admin(
    current_user: TokenPayload = Depends(get_current_user),
) -> TokenPayload:
    """
    FastAPI dependency that requires role == 'admin'.

    Raises
    ------
    HTTP 403 — authenticated but not an admin.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


AdminUser = Annotated[TokenPayload, Depends(require_admin)]
