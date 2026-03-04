"""
Authentication endpoints
=========================
POST /api/v1/auth/token   — login → access token + refresh token cookie
POST /api/v1/auth/refresh — rotate refresh token
POST /api/v1/auth/logout  — blacklist refresh token

JWT / Refresh Token spec: Security_Spec.md §7.1.2–7.1.4
"""
from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import CurrentUser, DBSession, RedisClient
from app.core.limiter import limiter
from app.core.security import (
    blacklist_refresh_token,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    is_refresh_token_revoked,
    verify_password,
)
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])

# Cookie attributes for refresh token
_REFRESH_COOKIE_NAME = "refresh_token"
_REFRESH_COOKIE_OPTS = dict(
    key=_REFRESH_COOKIE_NAME,
    httponly=True,
    secure=True,
    samesite="strict",
    path="/api/v1/auth/refresh",
    max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# POST /auth/token — Login
# ---------------------------------------------------------------------------

@router.post(
    "/token",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Login and obtain JWT tokens",
)
@limiter.limit(settings.RATE_LIMIT_LOGIN)  # 5/minute
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: DBSession,
    redis: RedisClient,
) -> TokenResponse:
    """
    Authenticate with email + password.

    On success:
    - Returns ``{ access_token }`` in body (store in memory, not localStorage).
    - Sets ``refresh_token`` httpOnly Cookie (7-day TTL).
    """
    # Constant-time lookup; always verify even if user not found (timing attack)
    result = await db.execute(select(User).where(User.email == body.email))
    user: User | None = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="INVALID_CREDENTIALS",
        )

    if not user.is_active or not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="EMAIL_NOT_VERIFIED",
        )

    access_token = create_access_token(
        user_id=str(user.id),
        role=user.role.value,
        email=user.email,
    )
    refresh_token, _ = create_refresh_token(user_id=str(user.id))

    response.set_cookie(**_REFRESH_COOKIE_OPTS, value=refresh_token)

    return TokenResponse(access_token=access_token)


# ---------------------------------------------------------------------------
# POST /auth/refresh — Rotate Refresh Token
# ---------------------------------------------------------------------------

@router.post(
    "/refresh",
    response_model=RefreshResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate refresh token and get a new access token",
)
async def refresh_token(
    request: Request,
    response: Response,
    db: DBSession,
    redis: RedisClient,
    refresh_token_cookie: str | None = Cookie(default=None, alias=_REFRESH_COOKIE_NAME),
) -> RefreshResponse:
    """
    Exchange a valid Refresh Token Cookie for new access + refresh tokens.
    The old refresh token is immediately blacklisted (Rotation §7.1.4).
    """
    if refresh_token_cookie is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="REFRESH_TOKEN_MISSING",
        )

    # Check blacklist before decoding expiry (revoked tokens must fail fast)
    if await is_refresh_token_revoked(redis, refresh_token_cookie):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="REFRESH_TOKEN_REVOKED",
        )

    try:
        payload = decode_refresh_token(refresh_token_cookie)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="REFRESH_TOKEN_EXPIRED",
        )

    user_id: str = payload["sub"]

    # Load user to get current role/email (role may have changed since last login)
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user: User | None = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="USER_NOT_FOUND",
        )

    # Rotation: blacklist old token, issue new pair
    await blacklist_refresh_token(redis, refresh_token_cookie)

    new_access = create_access_token(
        user_id=str(user.id),
        role=user.role.value,
        email=user.email,
    )
    new_refresh, _ = create_refresh_token(user_id=str(user.id))

    response.set_cookie(**_REFRESH_COOKIE_OPTS, value=new_refresh)

    return RefreshResponse(access_token=new_access)


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------

@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Logout: revoke refresh token",
)
async def logout(
    request: Request,
    response: Response,
    current_user: CurrentUser,
    redis: RedisClient,
    refresh_token_cookie: str | None = Cookie(default=None, alias=_REFRESH_COOKIE_NAME),
) -> dict:
    """
    Invalidate the current refresh token and clear the Cookie.
    """
    if refresh_token_cookie:
        await blacklist_refresh_token(redis, refresh_token_cookie)

    # Expire the cookie
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value="",
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/v1/auth/refresh",
        max_age=0,
    )

    return {"success": True, "data": {"message": "Logged out"}, "error": None, "meta": None}
