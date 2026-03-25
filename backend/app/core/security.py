"""
Security utilities
==================
JWT creation / validation, bcrypt password hashing, and Refresh Token
rotation logic (including Redis blacklist).

JWT spec (Security_Spec.md §7.1.2)
-----------------------------------
- Algorithm   : HS256
- Access TTL  : 15 minutes
- Refresh TTL : 7 days
- Payload     : { sub, role, email, iat, exp }
- Access token : Authorization: Bearer <token>
- Refresh token: httpOnly Cookie  (not stored in this module — handled by endpoint)

Refresh Token Rotation (§7.1.4)
---------------------------------
1. On /auth/refresh: validate token, check Redis blacklist.
2. Blacklist old refresh token in Redis (TTL = 7 days).
3. Issue new access + refresh tokens.
4. On /auth/logout: blacklist current refresh token.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt as _bcrypt
import jwt
import redis.asyncio as aioredis

from app.core.config import settings

# ---------------------------------------------------------------------------
# Password hashing (bcrypt, work factor ≥ 12)
# Uses the `bcrypt` library directly to avoid passlib 1.7.4 / bcrypt ≥ 4.0
# incompatibility (detect_wrap_bug exceeds the 72-byte limit enforced in 4+).
# ---------------------------------------------------------------------------

_BCRYPT_ROUNDS = 12


def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

_ALGORITHM = settings.JWT_ALGORITHM  # "HS256"
_SECRET = settings.JWT_SECRET_KEY
_ACCESS_DELTA = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)   # 15 min
_REFRESH_DELTA = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)       # 7 days


def create_access_token(
    user_id: str,
    role: str,
    email: str,
) -> str:
    """Create a signed JWT access token (TTL 15 minutes)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "email": email,
        "iat": now,
        "exp": now + _ACCESS_DELTA,
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def create_refresh_token(user_id: str) -> tuple[str, datetime]:
    """
    Create a signed JWT refresh token (TTL 7 days).

    Returns
    -------
    token : str
    expires_at : datetime (UTC)
    """
    now = datetime.now(timezone.utc)
    expires_at = now + _REFRESH_DELTA
    payload = {
        "sub": user_id,
        "type": "refresh",
        # jti allows us to blacklist individual tokens without decoding
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM), expires_at


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.

    Raises
    ------
    jwt.ExpiredSignatureError  — token has expired
    jwt.InvalidTokenError      — signature invalid / malformed
    """
    return jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])


def decode_refresh_token(token: str) -> dict:
    """
    Decode and validate a JWT refresh token.

    Also checks that the ``type`` claim is ``"refresh"``.

    Raises
    ------
    jwt.ExpiredSignatureError
    jwt.InvalidTokenError
    ValueError — wrong token type
    """
    payload = jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    if payload.get("type") != "refresh":
        raise ValueError("Not a refresh token")
    return payload


# ---------------------------------------------------------------------------
# Redis Refresh Token blacklist (Rotation, §7.1.4)
# ---------------------------------------------------------------------------

_BLACKLIST_PREFIX = "rt_blacklist:"


def _blacklist_key(jti: str) -> str:
    return f"{_BLACKLIST_PREFIX}{jti}"


async def blacklist_refresh_token(redis: aioredis.Redis, token: str) -> None:
    """
    Add a refresh token's JTI to the Redis blacklist.
    TTL is set to the remaining lifetime of the token (max 7 days),
    so the blacklist entry auto-expires when the token would have expired anyway.
    """
    try:
        payload = decode_refresh_token(token)
    except Exception:
        return  # already invalid — nothing to blacklist

    jti: str = payload.get("jti", "")
    if not jti:
        return

    exp: int = payload.get("exp", 0)
    remaining = max(1, exp - int(datetime.now(timezone.utc).timestamp()))
    await redis.set(_blacklist_key(jti), "1", ex=remaining)


async def is_refresh_token_revoked(redis: aioredis.Redis, token: str) -> bool:
    """Return True if the token's JTI is in the Redis blacklist."""
    try:
        payload = decode_refresh_token(token)
    except Exception:
        return True  # treat malformed token as revoked

    jti: str = payload.get("jti", "")
    if not jti:
        return True

    result = await redis.get(_blacklist_key(jti))
    return result is not None
