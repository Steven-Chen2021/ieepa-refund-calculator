"""
Shared base mixin and common column helpers for all ORM models.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func, Uuid
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """Adds server-managed created_at / updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def uuid_pk() -> Mapped[uuid.UUID]:
    """Standard UUID primary key column (database-agnostic Uuid type)."""
    return mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
