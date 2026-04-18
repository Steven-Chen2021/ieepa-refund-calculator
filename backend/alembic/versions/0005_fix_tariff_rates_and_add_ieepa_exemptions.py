"""Fix tariff rates and add IEEPA exemption indicator codes.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-18

Changes
-------
1.  9903.01.33 was incorrectly seeded as IEEPA 50% (CN) in 0004.
    Per EO 14266 of April 9, 2025 (90 FR 15625), headings 9903.01.26–9903.01.33
    are *product exemption indicator* codes — goods described under them are
    EXCLUDED from the IEEPA reciprocal tariff.  All eight codes carry 0% and
    apply to any country of origin ('*').

2.  9903.01.26 – 9903.01.32 are added as IEEPA 0% exemption indicators
    (EO 14266, eff. 2025-04-09).

3.  9903.85.08 (S232 aluminium, country-agnostic) is updated from 10% to 50%
    effective 2025-02-10 (Proclamation 10895).  The old 10% row is expired by
    setting effective_to = '2025-02-09'.

4.  9903.81.91 (S232 steel, country-agnostic) is updated from 10% to 50%
    effective 2025-02-10 (Proclamation 10895 / aligned with aluminium increase).
    Confirmed from CBP Form 7501 sample (2810306.pdf, Line 002: 50% × $2663 =
    $1331.50).  The old 10% row is expired by setting effective_to = '2025-02-09'.
"""
from __future__ import annotations

import uuid as _uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── IEEPA exemption indicator codes (EO 14266, 2025-04-09) ──────────────────
# Headings 9903.01.26-9903.01.33: products excluded from the IEEPA reciprocal
# tariff for all trading partners.  Rate is 0%; country_code is '*' (global).
_IEEPA_EXEMPTION_CODES = [
    "9903.01.26",
    "9903.01.27",
    "9903.01.28",
    "9903.01.29",
    "9903.01.30",
    "9903.01.31",
    "9903.01.32",
    "9903.01.33",
]
_IEEPA_EXEMPTION_EFF_FROM = "2025-04-09"
_IEEPA_EXEMPTION_SOURCE = "EO 14266 — IEEPA exemption indicator"


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # ── 1. Fix 9903.01.33: remove incorrect CN/50% row, seed correct */0% row ──
    op.execute(
        sa.text(
            "DELETE FROM tariff_rates "
            "WHERE hts_code = '9903.01.33' "
            "  AND country_code = 'CN' "
            "  AND tariff_type = 'IEEPA' "
            "  AND effective_from = '2025-04-09'"
        )
    )

    # ── 2. Add IEEPA exemption indicator codes 9903.01.26–9903.01.33 ───────────
    for hts_code in _IEEPA_EXEMPTION_CODES:
        row_id = str(_uuid.uuid4())
        if is_pg:
            op.execute(
                sa.text(
                    "INSERT INTO tariff_rates "
                    "(id, hts_code, country_code, tariff_type, rate_pct, "
                    " effective_from, effective_to, source_ref, created_at, updated_at) "
                    "VALUES (:id, :hts, '*', 'IEEPA', 0.0000, :eff_from, "
                    "        NULL, :source_ref, NOW(), NOW()) "
                    "ON CONFLICT (hts_code, country_code, tariff_type, effective_from) "
                    "DO NOTHING"
                ).bindparams(
                    id=row_id,
                    hts=hts_code,
                    eff_from=_IEEPA_EXEMPTION_EFF_FROM,
                    source_ref=_IEEPA_EXEMPTION_SOURCE,
                )
            )
        else:
            op.execute(
                sa.text(
                    "INSERT OR IGNORE INTO tariff_rates "
                    "(id, hts_code, country_code, tariff_type, rate_pct, "
                    " effective_from, effective_to, source_ref, created_at, updated_at) "
                    "VALUES (:id, :hts, '*', 'IEEPA', 0.0000, :eff_from, "
                    "        NULL, :source_ref, datetime('now'), datetime('now'))"
                ).bindparams(
                    id=row_id,
                    hts=hts_code,
                    eff_from=_IEEPA_EXEMPTION_EFF_FROM,
                    source_ref=_IEEPA_EXEMPTION_SOURCE,
                )
            )

    # ── 3. 9903.85.08 (S232 aluminium): expire 10% row, add 50% row ─────────
    # Expire old 10% row (eff 2018-03-23) by setting effective_to = 2025-02-09
    op.execute(
        sa.text(
            "UPDATE tariff_rates "
            "SET effective_to = '2025-02-09' "
            "WHERE hts_code = '9903.85.08' "
            "  AND country_code = '*' "
            "  AND tariff_type = 'S232' "
            "  AND effective_from = '2018-03-23' "
            "  AND effective_to IS NULL"
        )
    )

    # Insert new 50% row effective 2025-02-10 (Proclamation 10895)
    new_alum_id = str(_uuid.uuid4())
    if is_pg:
        op.execute(
            sa.text(
                "INSERT INTO tariff_rates "
                "(id, hts_code, country_code, tariff_type, rate_pct, "
                " effective_from, effective_to, source_ref, created_at, updated_at) "
                "VALUES (:id, '9903.85.08', '*', 'S232', 0.5000, '2025-02-10', "
                "        NULL, 'Proclamation 10895 — S232 aluminium', NOW(), NOW()) "
                "ON CONFLICT (hts_code, country_code, tariff_type, effective_from) "
                "DO NOTHING"
            ).bindparams(id=new_alum_id)
        )
    else:
        op.execute(
            sa.text(
                "INSERT OR IGNORE INTO tariff_rates "
                "(id, hts_code, country_code, tariff_type, rate_pct, "
                " effective_from, effective_to, source_ref, created_at, updated_at) "
                "VALUES (:id, '9903.85.08', '*', 'S232', 0.5000, '2025-02-10', "
                "        NULL, 'Proclamation 10895 — S232 aluminium', datetime('now'), datetime('now'))"
            ).bindparams(id=new_alum_id)
        )

    # ── 4. 9903.81.91 (S232 steel): expire 10% row, add 50% row ─────────────
    # Confirmed by CBP Form 7501 sample: 50% × entered-value matches duty shown
    # on lines with 9903.81.91 (same Proclamation 10895 increase as aluminium).
    op.execute(
        sa.text(
            "UPDATE tariff_rates "
            "SET effective_to = '2025-02-09' "
            "WHERE hts_code = '9903.81.91' "
            "  AND country_code = '*' "
            "  AND tariff_type = 'S232' "
            "  AND effective_from = '2018-03-23' "
            "  AND effective_to IS NULL"
        )
    )

    new_steel_id = str(_uuid.uuid4())
    if is_pg:
        op.execute(
            sa.text(
                "INSERT INTO tariff_rates "
                "(id, hts_code, country_code, tariff_type, rate_pct, "
                " effective_from, effective_to, source_ref, created_at, updated_at) "
                "VALUES (:id, '9903.81.91', '*', 'S232', 0.5000, '2025-02-10', "
                "        NULL, 'Proclamation 10895 — S232 steel', NOW(), NOW()) "
                "ON CONFLICT (hts_code, country_code, tariff_type, effective_from) "
                "DO NOTHING"
            ).bindparams(id=new_steel_id)
        )
    else:
        op.execute(
            sa.text(
                "INSERT OR IGNORE INTO tariff_rates "
                "(id, hts_code, country_code, tariff_type, rate_pct, "
                " effective_from, effective_to, source_ref, created_at, updated_at) "
                "VALUES (:id, '9903.81.91', '*', 'S232', 0.5000, '2025-02-10', "
                "        NULL, 'Proclamation 10895 — S232 steel', datetime('now'), datetime('now'))"
            ).bindparams(id=new_steel_id)
        )


def downgrade() -> None:
    # Remove IEEPA exemption indicator codes added in this migration
    for hts_code in _IEEPA_EXEMPTION_CODES:
        op.execute(
            sa.text(
                "DELETE FROM tariff_rates "
                "WHERE hts_code = :hts AND country_code = '*' "
                "  AND tariff_type = 'IEEPA' AND effective_from = '2025-04-09'"
            ).bindparams(hts=hts_code)
        )

    # Restore 9903.01.33 to the (incorrect) original seed state
    row_id = str(_uuid.uuid4())
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    if is_pg:
        op.execute(
            sa.text(
                "INSERT INTO tariff_rates "
                "(id, hts_code, country_code, tariff_type, rate_pct, "
                " effective_from, effective_to, source_ref, created_at, updated_at) "
                "VALUES (:id, '9903.01.33', 'CN', 'IEEPA', 0.5000, '2025-04-09', "
                "        NULL, 'EO 14259', NOW(), NOW()) "
                "ON CONFLICT (hts_code, country_code, tariff_type, effective_from) DO NOTHING"
            ).bindparams(id=row_id)
        )
    else:
        op.execute(
            sa.text(
                "INSERT OR IGNORE INTO tariff_rates "
                "(id, hts_code, country_code, tariff_type, rate_pct, "
                " effective_from, effective_to, source_ref, created_at, updated_at) "
                "VALUES (:id, '9903.01.33', 'CN', 'IEEPA', 0.5000, '2025-04-09', "
                "        NULL, 'EO 14259', datetime('now'), datetime('now'))"
            ).bindparams(id=row_id)
        )

    # Restore 9903.85.08: remove 50% row, un-expire 10% row
    op.execute(
        sa.text(
            "DELETE FROM tariff_rates "
            "WHERE hts_code = '9903.85.08' AND country_code = '*' "
            "  AND tariff_type = 'S232' AND effective_from = '2025-02-10'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE tariff_rates "
            "SET effective_to = NULL "
            "WHERE hts_code = '9903.85.08' AND country_code = '*' "
            "  AND tariff_type = 'S232' AND effective_from = '2018-03-23'"
        )
    )

    # Restore 9903.81.91: remove 50% row, un-expire 10% row
    op.execute(
        sa.text(
            "DELETE FROM tariff_rates "
            "WHERE hts_code = '9903.81.91' AND country_code = '*' "
            "  AND tariff_type = 'S232' AND effective_from = '2025-02-10'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE tariff_rates "
            "SET effective_to = NULL "
            "WHERE hts_code = '9903.81.91' AND country_code = '*' "
            "  AND tariff_type = 'S232' AND effective_from = '2018-03-23'"
        )
    )
