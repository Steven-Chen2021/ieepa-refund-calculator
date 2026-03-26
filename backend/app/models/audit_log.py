"""
AuditLog model — admin operation audit trail.

Records every admin action (tariff rate changes, user management, etc.)
for compliance and troubleshooting. Append-only by convention.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import uuid_pk


class AuditLog(Base):
    """
    Admin action log — append only, no TimestampMixin (no updated_at).

    action examples: "RATE_UPDATE", "RATE_IMPORT", "LEAD_EXPORT",
                     "USER_DEACTIVATE", "ADMIN_LOGIN"
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = uuid_pk()

    # NULL for system-generated events (e.g., Celery Beat tasks)
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )

    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Snapshots of the record before and after the change
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Source IP address for security auditing
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
