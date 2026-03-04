"""
User model.

Covers both regular users and admin users via the `role` enum column
(avoids a separate admin_users table while preserving the spec's semantics).
Admin-only operations check `role == UserRole.admin` in the dependency layer.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Enum, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, uuid_pk

import enum


class UserRole(str, enum.Enum):
    user = "user"
    admin = "admin"


class User(TimestampMixin, Base):
    """
    Registered users and admin accounts.

    JWT payload: { sub: id, role: role, email: email }
    Password hashed with bcrypt (work factor ≥ 12).
    Email must be verified before login is permitted.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(
        String(254), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum"),
        nullable=False,
        default=UserRole.user,
        server_default=UserRole.user.value,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # One-time token sent via email; cleared after verification
    email_verification_token: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    # For password-reset flow
    password_reset_token: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )

    # ── Relationships ────────────────────────────────────────
    # (back-references populated by child models)
