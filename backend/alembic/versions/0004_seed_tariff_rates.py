"""Seed initial tariff rates for S301, IEEPA, and S232 HTS codes.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-01

Rates seeded:
  S301 (Section 301, CN):
    9903.88.01  25%  eff 2018-07-06  (83 FR 28710 — List 1)
    9903.88.02  25%  eff 2018-08-23  (83 FR 40823 — List 2)
    9903.88.03  25%  eff 2018-09-24  (83 FR 47974 — List 3)
    9903.88.15  7.5% eff 2020-02-14  (85 FR 3741  — List 4A, Phase 1 reduction)

  IEEPA (International Emergency Economic Powers Act, CN):
    9903.01.24  10%  eff 2025-02-04  (EO 14257)
    9903.01.25  10%  eff 2025-02-04  (EO 14257)
    9903.01.33  50%  eff 2025-04-09  (EO 14259 — INCORRECT; corrected to 0% in 0005)

  S232 (Section 232 steel / aluminium, country-agnostic '*'):
    9903.81.91  10%  eff 2018-03-23  (83 FR 11619 — steel;     expired in 0005, superseded by 50%)
    9903.85.08  10%  eff 2018-03-23  (83 FR 11619 — aluminium; expired in 0005, superseded by 50%)

All rows use ON CONFLICT DO NOTHING (PostgreSQL) / INSERT OR IGNORE (SQLite)
so re-running the migration is idempotent.
"""
from __future__ import annotations

import uuid as _uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (hts_code, country_code, tariff_type, rate_pct, effective_from, source_ref)
_RATES = [
    # S301 — Section 301 CN-specific codes
    ("9903.88.01", "CN", "S301", 0.2500, "2018-07-06", "83 FR 28710"),
    ("9903.88.02", "CN", "S301", 0.2500, "2018-08-23", "83 FR 40823"),
    ("9903.88.03", "CN", "S301", 0.2500, "2018-09-24", "83 FR 47974"),
    ("9903.88.15", "CN", "S301", 0.0750, "2020-02-14", "85 FR 3741"),
    # IEEPA — CN-specific
    ("9903.01.24", "CN", "IEEPA", 0.1000, "2025-02-04", "EO 14257"),
    ("9903.01.25", "CN", "IEEPA", 0.1000, "2025-02-04", "EO 14257"),
    ("9903.01.33", "CN", "IEEPA", 0.5000, "2025-04-09", "EO 14259"),
    # S232 — country-agnostic (wildcard)
    ("9903.81.91", "*", "S232", 0.1000, "2018-03-23", "83 FR 11619"),
    ("9903.85.08", "*", "S232", 0.1000, "2018-03-23", "83 FR 11619"),
]


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    for hts, country, tariff_type, rate, eff_from, source_ref in _RATES:
        row_id = str(_uuid.uuid4())
        if is_pg:
            op.execute(
                sa.text(
                    "INSERT INTO tariff_rates "
                    "(id, hts_code, country_code, tariff_type, rate_pct, "
                    " effective_from, effective_to, source_ref, created_at, updated_at) "
                    "VALUES (:id, :hts, :country, :tariff_type, :rate, :eff_from, "
                    "        NULL, :source_ref, NOW(), NOW()) "
                    "ON CONFLICT (hts_code, country_code, tariff_type, effective_from) "
                    "DO NOTHING"
                ).bindparams(
                    id=row_id,
                    hts=hts,
                    country=country,
                    tariff_type=tariff_type,
                    rate=rate,
                    eff_from=eff_from,
                    source_ref=source_ref,
                )
            )
        else:
            op.execute(
                sa.text(
                    "INSERT OR IGNORE INTO tariff_rates "
                    "(id, hts_code, country_code, tariff_type, rate_pct, "
                    " effective_from, effective_to, source_ref, created_at, updated_at) "
                    "VALUES (:id, :hts, :country, :tariff_type, :rate, :eff_from, "
                    "        NULL, :source_ref, datetime('now'), datetime('now'))"
                ).bindparams(
                    id=row_id,
                    hts=hts,
                    country=country,
                    tariff_type=tariff_type,
                    rate=rate,
                    eff_from=eff_from,
                    source_ref=source_ref,
                )
            )


def downgrade() -> None:
    _codes = (
        "9903.88.01", "9903.88.02", "9903.88.03", "9903.88.15",
        "9903.01.24", "9903.01.25", "9903.01.33",
        "9903.81.91", "9903.85.08",
    )
    for code in _codes:
        op.execute(
            sa.text("DELETE FROM tariff_rates WHERE hts_code = :hts").bindparams(hts=code)
        )
