"""
Lead model — prospective customer contact information.

PII FIELDS: `full_name`, `email`, `phone` are stored encrypted using
the EncryptedString TypeDecorator (Fernet AES-256-GCM). The database
column holds the base64url-encoded ciphertext; the Python attribute
transparently exposes the plaintext string.

Never read `full_name_encrypted` / `email_encrypted` / `phone_encrypted`
columns directly from SQL — always go through the ORM to trigger decryption.
For admin CSV export, use the service layer which decrypts via ORM.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TimestampMixin, uuid_pk
from app.models.types import EncryptedString


class CrmSyncStatus(str, enum.Enum):
    pending = "pending"
    synced = "synced"
    failed = "failed"


class Lead(TimestampMixin, Base):
    """
    Prospective customer captured after the results page.

    PII fields use EncryptedString so that plaintext never reaches the DB.
    Non-PII fields (company_name, country, refund figures) are stored plaintext
    for admin filtering without decryption.

    CRM sync is handled asynchronously by the Celery crm_sync task with
    exponential back-off: 1 min → 5 min → 30 min (max 3 retries).
    After 3 failures: crm_sync_status = 'failed', alert emitted.
    """

    __tablename__ = "leads"
    __table_args__ = (
        # One lead per calculation — enforced at DB level
        UniqueConstraint("calculation_id", name="uq_leads_calculation_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()

    calculation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )

    # ── PII — stored encrypted (Fernet AES-256-GCM) ──────────
    # Column names use the plain logical names; encryption is transparent.
    full_name: Mapped[str] = mapped_column(
        EncryptedString, nullable=False
    )
    email: Mapped[str] = mapped_column(
        EncryptedString, nullable=False
    )
    phone: Mapped[str | None] = mapped_column(
        EncryptedString, nullable=True
    )

    # ── Non-PII ───────────────────────────────────────────────
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)           # ISO alpha-2
    preferred_contact: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "email" | "phone"
    contact_consent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Denormalised from calculation at lead submission time for admin filtering
    estimated_refund: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    refund_pathway: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ── CRM Sync State ────────────────────────────────────────
    crm_sync_status: Mapped[CrmSyncStatus] = mapped_column(
        Enum(CrmSyncStatus, name="crm_sync_status_enum"),
        nullable=False,
        default=CrmSyncStatus.pending,
        server_default=CrmSyncStatus.pending.value,
        index=True,
    )
    crm_lead_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    crm_retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    crm_last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
