"""
TariffRate model.

Stores the HTS tariff rate lookup table for all supported tariff types.
Composite lookup key: (hts_code, country_code, tariff_type, effective_from).

Redis cache key pattern: tariff:{hts_code}:{country_code}:{tariff_type}:{date}
Invalidate immediately via DEL after any admin rate update (BR-005).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Numeric, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TimestampMixin, uuid_pk

import enum


class TariffType(str, enum.Enum):
    MFN = "MFN"      # Most-Favoured-Nation base tariff
    IEEPA = "IEEPA"  # International Emergency Economic Powers Act (CN only, BR-002)
    S301 = "S301"    # Section 301 (List 1–4B)
    S232 = "S232"    # Section 232 (steel / aluminium)


class TariffRate(TimestampMixin, Base):
    """
    HTS code → tariff rate mapping.

    Lookup always uses (hts_code, country_code, tariff_type, summary_date)
    where summary_date must be within [effective_from, effective_to].
    effective_to = NULL means the rate is currently active.

    MFN and S232 rates are country-agnostic; use country_code = '*'
    for those rows and filter accordingly in the service layer.
    """

    __tablename__ = "tariff_rates"
    __table_args__ = (
        UniqueConstraint(
            "hts_code", "country_code", "tariff_type", "effective_from",
            name="uq_tariff_rate_lookup",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()

    hts_code: Mapped[str] = mapped_column(String(15), nullable=False, index=True)
    # ISO alpha-2 country code, or '*' for country-agnostic rates (MFN, S232)
    country_code: Mapped[str] = mapped_column(String(3), nullable=False, index=True)

    tariff_type: Mapped[TariffType] = mapped_column(
        Enum(TariffType, name="tariff_type_enum"),
        nullable=False,
        index=True,
    )

    rate_pct: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)

    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Regulatory source reference (e.g., "90 FR 12345")
    source_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Admin user who last updated this record (FK enforced at app layer)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
