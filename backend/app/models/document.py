"""
Document model — represents an uploaded CBP Form 7501.

The physical file is AES-256-GCM encrypted and stored under
/data/uploads/{YYYY-MM-DD}/{job_id}/original.{ext}.
OCR results and user corrections are stored as JSONB blobs.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TimestampMixin, uuid_pk


class DocumentStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    review_required = "review_required"
    failed = "failed"


class Document(TimestampMixin, Base):
    """
    One row per uploaded Form 7501 file / OCR job.

    `id` is the `job_id` returned to the client.
    `extracted_fields` holds the raw OCR output (JSONB, see API spec §6.4.1).
    `corrections` holds user-applied field corrections from PATCH /fields.
    File on disk is encrypted; `encrypted_file_path` is the relative path
    under DATA_ROOT.
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = uuid_pk()

    # Optional FK to a registered user; NULL for guest uploads
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    # Anonymous session identifier (cookie-based)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # Idempotency key from X-Idempotency-Key header
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True, index=True
    )

    # File metadata
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    privacy_accepted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # OCR processing state
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status_enum"),
        nullable=False,
        default=DocumentStatus.queued,
        server_default=DocumentStatus.queued.value,
        index=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocr_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # "direct_text" when pdfplumber reads a digital PDF; "ocr" otherwise
    extraction_method: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Structured OCR output from Google Document AI / pytesseract
    # Schema mirrors the `extracted_fields` object in API spec §6.4.1
    extracted_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # User corrections applied via PATCH /api/v1/documents/{job_id}/fields
    corrections: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # TTL: document row and encrypted file expire at this timestamp
    # Celery Beat cleanup task checks this field
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
