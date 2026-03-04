"""
Calculation and CalculationAudit models.

Calculation — one row per triggered calculation job (BR-001 through BR-011).
CalculationAudit — immutable append-only audit trail; never UPDATE or DELETE.
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TimestampMixin, uuid_pk


class CalculationStatus(str, enum.Enum):
    pending = "pending"
    calculating = "calculating"
    completed = "completed"
    failed = "failed"


class RefundPathway(str, enum.Enum):
    PSC = "PSC"          # Post-Summary Correction  (≤ 15 days, BR-007)
    PROTEST = "PROTEST"  # CBP Protest              (16–180 days)
    INELIGIBLE = "INELIGIBLE"  # > 180 days or non-CN


class Calculation(TimestampMixin, Base):
    """
    Tariff calculation result for one Form 7501.

    `duty_components` stores the full breakdown array matching the
    `duty_components` array in GET /api/v1/results/{calculation_id}.
    `entry_summary` stores a snapshot of the parsed header fields.

    Refund pathway determined by BR-007 (days_since_summary vs. summary_date).
    IEEPA only applies when country_of_origin == 'CN' (BR-002).
    """

    __tablename__ = "calculations"

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    status: Mapped[CalculationStatus] = mapped_column(
        Enum(CalculationStatus, name="calculation_status_enum"),
        nullable=False,
        default=CalculationStatus.pending,
        server_default=CalculationStatus.pending.value,
        index=True,
    )

    # Idempotency key from X-Idempotency-Key header on POST /calculate
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True, index=True
    )

    # ── Entry Summary Fields ──────────────────────────────────
    entry_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    summary_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    country_of_origin: Mapped[str | None] = mapped_column(String(2), nullable=True)
    port_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    importer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mode_of_transport: Mapped[str | None] = mapped_column(String(20), nullable=True)
    total_entered_value: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )

    # ── Calculation Results ───────────────────────────────────
    # Full duty breakdown — array of DutyComponent objects
    duty_components: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    total_duty: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    estimated_refund: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    refund_pathway: Mapped[RefundPathway | None] = mapped_column(
        Enum(RefundPathway, name="refund_pathway_enum"),
        nullable=True,
    )
    days_since_summary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pathway_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Path to the generated PDF report (relative to REPORTS_DIR)
    pdf_report_path: Mapped[str | None] = mapped_column(Text, nullable=True)


# ── Append-only audit trail ───────────────────────────────────────────────────


class CalculationAudit(Base):
    """
    Immutable audit record created after each successful calculation.

    CONSTRAINTS:
    - Never issue UPDATE or DELETE on this table (enforced by policy and
      optionally by a DB trigger — see migration script).
    - No `updated_at` column intentionally.
    - `snapshot` is the full calculation output at time of creation,
      preserving the historical record even if the calculation row changes.
    """

    __tablename__ = "calculation_audit"

    id: Mapped[uuid.UUID] = uuid_pk()
    calculation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    # Full point-in-time snapshot of the calculation result
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
