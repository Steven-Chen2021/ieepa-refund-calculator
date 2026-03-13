"""
IEEPA Tariff Calculation Engine
================================
Implements BR-001 through BR-009 (Business_Rules.md, Section 5.1).

Entry-point
-----------
    result = await calculate_entry(db=session, redis=redis_client,
                                   calculation_id=uuid, inputs=entry_input)

Pure helpers (no I/O — safe to call in tests without DB/Redis)
--------------------------------------------------------------
    calculate_mpf(total_entered_value)            → Decimal  (BR-005, TC-CALC-005)
    calculate_hmf(total_entered_value, transport) → Decimal  (BR-006)
    determine_refund_pathway(summary_date)        → str      (BR-007, TC-CALC-007)

Redis cache key pattern (per TariffRate model docstring)
---------------------------------------------------------
    tariff:{hts_code}:{country_code}:{tariff_type}:{YYYY-MM-DD}
    TTL   : settings.CACHE_TTL_SECONDS   (default 3 600 s)
    Invalidation: DEL on any admin rate update (admin rates service)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Union

import redis.asyncio as aioredis
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.calculation import CalculationAudit, RefundPathway
from app.models.tariff_rate import TariffRate, TariffType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# BR-005 — Merchandise Processing Fee
MPF_RATE: Decimal = Decimal("0.003464")   # 0.3464 %
MPF_FLOOR: Decimal = Decimal("32.71")     # minimum
MPF_CAP: Decimal = Decimal("634.62")      # maximum

# BR-006 — Harbor Maintenance Fee
HMF_RATE: Decimal = Decimal("0.00125")    # 0.125 %

# BR-001 — IEEPA is only for Chinese-origin goods
IEEPA_COUNTRY = "CN"

# BR-006 — HMF applies only to sea freight
VESSEL_TRANSPORT = "vessel"

# Redis sentinel written to cache when DB has no matching rate
_CACHE_NULL = "__NULL__"


# ---------------------------------------------------------------------------
# Input / Output Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class LineItem:
    """One HTS line item extracted from CBP Form 7501."""
    hts_code: str
    country_of_origin: str   # ISO alpha-2 (e.g. "CN", "TW", "VN")
    entered_value: Decimal   # declared value in USD
    # Optional OCR-extracted fallback values (used when DB tariff lookup returns None)
    ocr_tariff_type: str | None = None   # e.g. "IEEPA", "MFN", "S301", "S232"
    ocr_rate_pct: Decimal | None = None  # e.g. Decimal("0.145") for 14.5%
    ocr_duty_amount: Decimal | None = None  # pre-extracted duty amount (IEEPA add-on lines)


@dataclass
class EntryInput:
    """Full parsed input for a single CBP Form 7501 entry summary."""
    entry_number: str
    summary_date: date
    mode_of_transport: str   # "vessel" | "air" | other
    line_items: list[LineItem]
    total_entered_value: Decimal  # Σ line_item.entered_value


@dataclass
class DutyComponent:
    """Computed tariff for one type on one HTS line item."""
    tariff_type: str          # "MFN" | "IEEPA" | "S301" | "S232"
    hts_code: str
    country_of_origin: str
    entered_value: Decimal
    rate_pct: Decimal         # decimal fraction (e.g. 0.20 for 20 %)
    amount: Decimal           # entered_value × rate_pct, rounded to cents
    applicable: bool          # False → tariff does not apply to this item
    rate_not_found: bool = False  # True → no rate record found in DB


@dataclass
class EntryFee:
    """Whole-entry fee (MPF or HMF) after floor/cap logic."""
    fee_type: str             # "MPF" | "HMF"
    total_entered_value: Decimal
    raw_amount: Decimal       # before floor / cap
    amount: Decimal           # after floor / cap
    applicable: bool


@dataclass
class CalculationResult:
    """Full output of calculate_entry()."""
    entry_number: str
    summary_date: date
    country_of_origin: str    # from first line item (informational)
    mode_of_transport: str
    total_entered_value: Decimal
    line_duty_components: list[DutyComponent]   # all MFN/IEEPA/S301/S232 rows
    mpf: EntryFee
    hmf: EntryFee
    total_duty: Decimal       # Σ all duties + MPF + HMF
    estimated_refund: Decimal  # BR-008: Σ IEEPA amounts only
    refund_pathway: str       # "PSC" | "PROTEST" | "INELIGIBLE"
    days_since_summary: int
    pathway_rationale: str    # human-readable explanation


# ---------------------------------------------------------------------------
# Pure calculation helpers (no I/O — fully testable without DB/Redis)
# ---------------------------------------------------------------------------

def calculate_mpf(total_entered_value: Union[Decimal, float, int]) -> Decimal:
    """
    BR-005: Merchandise Processing Fee
    -----------------------------------
    formula  : total_entered_value × 0.3464 %
    floor    : $32.71  (TC-CALC-005 Case A/B)
    cap      : $634.62 (TC-CALC-005 Case G)

    Boundary values (TC-CALC-005):
        entered_value =   9 444  → raw $32.70  → floor → $32.71
        entered_value =  50 000  → raw $173.20 → normal
        entered_value = 200 000  → raw $692.80 → cap   → $634.62
    """
    tv = Decimal(str(total_entered_value))
    raw = (tv * MPF_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return max(MPF_FLOOR, min(MPF_CAP, raw))


def calculate_hmf(
    total_entered_value: Union[Decimal, float, int],
    mode_of_transport: str,
) -> Decimal:
    """
    BR-006: Harbor Maintenance Fee
    --------------------------------
    rate   : 0.125 %
    applies: mode_of_transport == 'vessel' only
    air    : always $0.00
    """
    if mode_of_transport.lower() != VESSEL_TRANSPORT:
        return Decimal("0.00")
    tv = Decimal(str(total_entered_value))
    return (tv * HMF_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def determine_refund_pathway(summary_date: date) -> str:
    """
    BR-007: Refund pathway decision based on days elapsed since summary_date.
    --------------------------------------------------------------------------
    days_elapsed = today − summary_date

    Boundary values (TC-CALC-007):
        day 15  → PSC       (still within window)
        day 16  → PROTEST   (PSC window closed)
        day 180 → PROTEST   (last day eligible)
        day 181 → INELIGIBLE

    Returns one of: "PSC" | "PROTEST" | "INELIGIBLE"
    """
    days_elapsed = (date.today() - summary_date).days
    if days_elapsed <= 15:
        return RefundPathway.PSC.value
    if days_elapsed <= 180:
        return RefundPathway.PROTEST.value
    return RefundPathway.INELIGIBLE.value


# ---------------------------------------------------------------------------
# Redis cache helpers
# ---------------------------------------------------------------------------

def _cache_key(
    hts_code: str,
    country_code: str,
    tariff_type: str,
    summary_date: date,
) -> str:
    """
    Builds the Redis cache key per TariffRate model documentation:
        tariff:{hts_code}:{country_code}:{tariff_type}:{YYYY-MM-DD}
    """
    return f"tariff:{hts_code}:{country_code}:{tariff_type}:{summary_date.isoformat()}"


async def get_tariff_rate(
    db: AsyncSession,
    redis: aioredis.Redis,
    hts_code: str,
    country_code: str,
    tariff_type: str,
    summary_date: date,
) -> Decimal | None:
    """
    BR-009: Cached tariff rate lookup.
    -----------------------------------
    1. Check Redis cache (key = tariff:{hts}:{cc}:{type}:{date}).
       - Hit + value   → return Decimal rate
       - Hit + null    → return None  (DB confirmed no rate, avoid re-querying)
       - Miss          → query DB, cache result
    2. DB query uses the composite key with date-range logic:
         WHERE hts_code = $hts
           AND country_code IN ($cc, '*')
           AND tariff_type = $type
           AND effective_from <= $date
           AND (effective_to IS NULL OR effective_to >= $date)
         ORDER BY country_code DESC   -- exact country match before wildcard '*'
         LIMIT 1

    Returns None when no rate record covers the given summary_date
    (e.g. IEEPA before its 2025-04-02 effective date — TC-CALC-009 Case B).
    """
    key = _cache_key(hts_code, country_code, tariff_type, summary_date)

    # --- cache lookup ---
    raw = await redis.get(key)
    if raw is not None:
        raw_str = raw.decode() if isinstance(raw, bytes) else raw
        return None if raw_str == _CACHE_NULL else Decimal(raw_str)

    # --- DB lookup ---
    rate = await _query_db_tariff_rate(db, hts_code, country_code, tariff_type, summary_date)

    if rate is None:
        logger.warning(
            "No tariff rate: hts=%s country=%s type=%s date=%s",
            hts_code, country_code, tariff_type, summary_date,
        )

    # --- populate cache ---
    cache_value = _CACHE_NULL if rate is None else str(rate)
    await redis.set(key, cache_value, ex=settings.CACHE_TTL_SECONDS)

    return rate


async def _query_db_tariff_rate(
    db: AsyncSession,
    hts_code: str,
    country_code: str,
    tariff_type: str,
    summary_date: date,
) -> Decimal | None:
    """
    BR-009 SQL implementation:
        WHERE hts_code=$1
          AND country_code IN ($2, '*')
          AND tariff_type=$3
          AND effective_from<=$4
          AND (effective_to IS NULL OR effective_to>=$4)
        ORDER BY country_code DESC   -- prefer exact match over '*'
        LIMIT 1
    """
    stmt = (
        select(TariffRate.rate_pct)
        .where(
            and_(
                TariffRate.hts_code == hts_code,
                TariffRate.country_code.in_([country_code, "*"]),
                TariffRate.tariff_type == tariff_type,
                TariffRate.effective_from <= summary_date,
                or_(
                    TariffRate.effective_to.is_(None),
                    TariffRate.effective_to >= summary_date,
                ),
            )
        )
        .order_by(TariffRate.country_code.desc())  # exact country before wildcard
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    return Decimal(str(row)) if row is not None else None


# ---------------------------------------------------------------------------
# Per-line-item tariff calculators
# ---------------------------------------------------------------------------

async def _calc_mfn(
    db: AsyncSession,
    redis: aioredis.Redis,
    item: LineItem,
    summary_date: date,
) -> DutyComponent:
    """BR-002: mfn_tariff = entered_value × mfn_rate"""
    # IEEPA add-on lines (9903.01.xx) have no entered_value-based MFN; skip.
    if item.ocr_duty_amount is not None and item.ocr_tariff_type == TariffType.IEEPA.value:
        return DutyComponent(
            tariff_type=TariffType.MFN.value,
            hts_code=item.hts_code,
            country_of_origin=item.country_of_origin,
            entered_value=item.entered_value,
            rate_pct=Decimal("0"),
            amount=Decimal("0.00"),
            applicable=False,
            rate_not_found=False,
        )
    rate = await get_tariff_rate(
        db, redis, item.hts_code, item.country_of_origin,
        TariffType.MFN.value, summary_date,
    )
    not_found = rate is None
    if not_found and item.ocr_tariff_type == TariffType.MFN.value and item.ocr_rate_pct is not None:
        rate = item.ocr_rate_pct
        not_found = False
    rate = rate or Decimal("0")
    amount = (item.entered_value * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return DutyComponent(
        tariff_type=TariffType.MFN.value,
        hts_code=item.hts_code,
        country_of_origin=item.country_of_origin,
        entered_value=item.entered_value,
        rate_pct=rate,
        amount=amount,
        applicable=not not_found,
        rate_not_found=not_found,
    )


async def _calc_ieepa(
    db: AsyncSession,
    redis: aioredis.Redis,
    item: LineItem,
    summary_date: date,
) -> DutyComponent:
    """
    BR-001: IEEPA tariff
    ----------------------
    - Non-CN origin → amount = $0.00, applicable = False (no cache hit needed)
    - CN origin     → look up rate by (hts_code, 'CN', 'IEEPA', summary_date)
                      If no rate exists (e.g. summary_date before IEEPA effective
                      date 2025-04-02), amount = $0.00 (TC-CALC-002 Case D)
    """
    if item.country_of_origin.upper() != IEEPA_COUNTRY:
        # BR-001 exception: non-CN always $0
        return DutyComponent(
            tariff_type=TariffType.IEEPA.value,
            hts_code=item.hts_code,
            country_of_origin=item.country_of_origin,
            entered_value=item.entered_value,
            rate_pct=Decimal("0"),
            amount=Decimal("0.00"),
            applicable=False,
            rate_not_found=False,
        )

    # IEEPA add-on line (e.g., 9903.01.24): duty_amount extracted directly from OCR.
    # These lines have no entered_value on the form; the amount comes from the 7501 directly.
    if item.ocr_duty_amount is not None and item.ocr_tariff_type == TariffType.IEEPA.value:
        return DutyComponent(
            tariff_type=TariffType.IEEPA.value,
            hts_code=item.hts_code,
            country_of_origin=item.country_of_origin,
            entered_value=item.entered_value,
            rate_pct=item.ocr_rate_pct or Decimal("0"),
            amount=item.ocr_duty_amount,
            applicable=True,
            rate_not_found=False,
        )

    rate = await get_tariff_rate(
        db, redis, item.hts_code, item.country_of_origin,
        TariffType.IEEPA.value, summary_date,
    )
    not_found = rate is None
    if not_found and item.ocr_tariff_type == TariffType.IEEPA.value and item.ocr_rate_pct is not None:
        rate = item.ocr_rate_pct
        not_found = False
    rate = rate or Decimal("0")
    amount = (item.entered_value * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return DutyComponent(
        tariff_type=TariffType.IEEPA.value,
        hts_code=item.hts_code,
        country_of_origin=item.country_of_origin,
        entered_value=item.entered_value,
        rate_pct=rate,
        amount=amount,
        applicable=not not_found,
        rate_not_found=not_found,
    )


async def _calc_s301(
    db: AsyncSession,
    redis: aioredis.Redis,
    item: LineItem,
    summary_date: date,
) -> DutyComponent:
    """BR-003: s301_tariff = entered_value × s301_rate (List 1–4B by HTS code)"""
    # IEEPA add-on lines are not S301 lines.
    if item.ocr_duty_amount is not None and item.ocr_tariff_type == TariffType.IEEPA.value:
        return DutyComponent(
            tariff_type=TariffType.S301.value,
            hts_code=item.hts_code,
            country_of_origin=item.country_of_origin,
            entered_value=item.entered_value,
            rate_pct=Decimal("0"),
            amount=Decimal("0.00"),
            applicable=False,
            rate_not_found=False,
        )
    rate = await get_tariff_rate(
        db, redis, item.hts_code, item.country_of_origin,
        TariffType.S301.value, summary_date,
    )
    not_found = rate is None
    if not_found and item.ocr_tariff_type == TariffType.S301.value and item.ocr_rate_pct is not None:
        rate = item.ocr_rate_pct
        not_found = False
    rate = rate or Decimal("0")
    amount = (item.entered_value * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return DutyComponent(
        tariff_type=TariffType.S301.value,
        hts_code=item.hts_code,
        country_of_origin=item.country_of_origin,
        entered_value=item.entered_value,
        rate_pct=rate,
        amount=amount,
        applicable=not not_found,
        rate_not_found=not_found,
    )


async def _calc_s232(
    db: AsyncSession,
    redis: aioredis.Redis,
    item: LineItem,
    summary_date: date,
) -> DutyComponent:
    """
    BR-004: Section 232 (steel / aluminium)
    ----------------------------------------
    Applies only to HTS codes on the steel/aluminium whitelist maintained in
    tariff_rates with tariff_type='S232'.  If no rate record exists the item
    is not steel/aluminium → applicable = False, amount = $0.00.
    The 'applicable' flag satisfies the section_232_applicable response field.
    """
    # IEEPA add-on lines are not S232 lines.
    if item.ocr_duty_amount is not None and item.ocr_tariff_type == TariffType.IEEPA.value:
        return DutyComponent(
            tariff_type=TariffType.S232.value,
            hts_code=item.hts_code,
            country_of_origin=item.country_of_origin,
            entered_value=item.entered_value,
            rate_pct=Decimal("0"),
            amount=Decimal("0.00"),
            applicable=False,
            rate_not_found=False,
        )
    rate = await get_tariff_rate(
        db, redis, item.hts_code, item.country_of_origin,
        TariffType.S232.value, summary_date,
    )
    applicable = rate is not None
    if not applicable and item.ocr_tariff_type == TariffType.S232.value and item.ocr_rate_pct is not None:
        rate = item.ocr_rate_pct
        applicable = True
    rate = rate or Decimal("0")
    amount = (
        (item.entered_value * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if applicable
        else Decimal("0.00")
    )
    return DutyComponent(
        tariff_type=TariffType.S232.value,
        hts_code=item.hts_code,
        country_of_origin=item.country_of_origin,
        entered_value=item.entered_value,
        rate_pct=rate,
        amount=amount,
        applicable=applicable,
        rate_not_found=False,  # absence of S232 rate is expected for non-steel/aluminium goods
    )


# ---------------------------------------------------------------------------
# Audit trail writer (BR-011)
# ---------------------------------------------------------------------------

async def _write_audit(
    db: AsyncSession,
    calculation_id: uuid.UUID,
    result: CalculationResult,
    inputs: EntryInput,
) -> None:
    """
    BR-011: Append-only calculation_audit record.
    Captures all inputs, every rate query result, intermediate values, and the
    final output so any calculation can be reproduced post-hoc.
    NEVER call UPDATE or DELETE on calculation_audit.
    """
    snapshot: dict = {
        "inputs": {
            "entry_number": inputs.entry_number,
            "summary_date": inputs.summary_date.isoformat(),
            "mode_of_transport": inputs.mode_of_transport,
            "total_entered_value": str(inputs.total_entered_value),
            "line_items": [
                {
                    "hts_code": li.hts_code,
                    "country_of_origin": li.country_of_origin,
                    "entered_value": str(li.entered_value),
                }
                for li in inputs.line_items
            ],
        },
        "duty_components": [
            {
                "tariff_type": dc.tariff_type,
                "hts_code": dc.hts_code,
                "country_of_origin": dc.country_of_origin,
                "entered_value": str(dc.entered_value),
                "rate_pct": str(dc.rate_pct),
                "amount": str(dc.amount),
                "applicable": dc.applicable,
                "rate_not_found": dc.rate_not_found,
            }
            for dc in result.line_duty_components
        ],
        "mpf": {
            "total_entered_value": str(result.mpf.total_entered_value),
            "raw_amount": str(result.mpf.raw_amount),
            "amount": str(result.mpf.amount),
        },
        "hmf": {
            "total_entered_value": str(result.hmf.total_entered_value),
            "raw_amount": str(result.hmf.raw_amount),
            "amount": str(result.hmf.amount),
            "applicable": result.hmf.applicable,
        },
        "total_duty": str(result.total_duty),
        "estimated_refund": str(result.estimated_refund),
        "refund_pathway": result.refund_pathway,
        "days_since_summary": result.days_since_summary,
        "pathway_rationale": result.pathway_rationale,
        "calculated_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    audit = CalculationAudit(
        calculation_id=calculation_id,
        snapshot=snapshot,
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(audit)
    # Caller commits the session; the audit row is part of the same transaction.


# ---------------------------------------------------------------------------
# Pathway rationale text
# ---------------------------------------------------------------------------

def _pathway_rationale(pathway: str, days_elapsed: int) -> str:
    messages = {
        RefundPathway.PSC.value: (
            f"Entry is {days_elapsed} day(s) old. "
            "Within the 15-day window — file a Post-Summary Correction (PSC) "
            "with your CBP Port of Entry for the fastest refund."
        ),
        RefundPathway.PROTEST.value: (
            f"Entry is {days_elapsed} day(s) old. "
            "The PSC window has closed (>15 days) but this entry is within the "
            "180-day protest period — file a CBP Protest (19 U.S.C. § 1514) "
            "to claim your IEEPA refund."
        ),
        RefundPathway.INELIGIBLE.value: (
            f"Entry is {days_elapsed} day(s) old. "
            "Beyond the 180-day protest deadline — this entry is no longer "
            "eligible for an IEEPA tariff refund."
        ),
    }
    return messages.get(pathway, "")


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def calculate_entry(
    *,
    db: AsyncSession,
    redis: aioredis.Redis,
    calculation_id: uuid.UUID,
    inputs: EntryInput,
) -> CalculationResult:
    """
    Full tariff calculation pipeline for one CBP Form 7501.

    Execution order (BR-001 – BR-011):
    ①  For each HTS line item:
        a. BR-002  MFN  tariff
        b. BR-001  IEEPA tariff  (CN origin only)
        c. BR-003  S301  tariff
        d. BR-004  S232  tariff  (steel/aluminium only)
    ②  BR-005  MPF  (whole-entry, with $32.71 floor / $634.62 cap)
    ③  BR-006  HMF  (whole-entry, vessel only)
    ④  BR-008  estimated_refund = Σ IEEPA component amounts
    ⑤  BR-007  determine_refund_pathway(summary_date)
    ⑥  BR-011  append-only audit record written to calculation_audit

    All tariff rate lookups go through Redis cache (BR-009).
    The caller is responsible for committing the DB session.
    """
    all_components: list[DutyComponent] = []

    # ① Per-line-item duties
    for item in inputs.line_items:
        mfn   = await _calc_mfn(db, redis, item, inputs.summary_date)
        ieepa = await _calc_ieepa(db, redis, item, inputs.summary_date)
        s301  = await _calc_s301(db, redis, item, inputs.summary_date)
        s232  = await _calc_s232(db, redis, item, inputs.summary_date)
        all_components.extend([mfn, ieepa, s301, s232])

    tv = inputs.total_entered_value

    # ② BR-005 MPF
    raw_mpf = (tv * MPF_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    mpf_fee = EntryFee(
        fee_type="MPF",
        total_entered_value=tv,
        raw_amount=raw_mpf,
        amount=calculate_mpf(tv),
        applicable=True,
    )

    # ③ BR-006 HMF
    raw_hmf = (tv * HMF_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    hmf_fee = EntryFee(
        fee_type="HMF",
        total_entered_value=tv,
        raw_amount=raw_hmf,
        amount=calculate_hmf(tv, inputs.mode_of_transport),
        applicable=inputs.mode_of_transport.lower() == VESSEL_TRANSPORT,
    )

    # ④ BR-008: estimated refund = Σ IEEPA amounts (excludes MFN/S301/S232/MPF/HMF)
    estimated_refund: Decimal = sum(
        (c.amount for c in all_components if c.tariff_type == TariffType.IEEPA.value),
        Decimal("0.00"),
    )

    # Total duty = all line-level tariffs + MPF + HMF
    total_duty: Decimal = (
        sum((c.amount for c in all_components), Decimal("0.00"))
        + mpf_fee.amount
        + hmf_fee.amount
    )

    # ⑤ BR-007: refund pathway
    days_elapsed = (date.today() - inputs.summary_date).days
    pathway = determine_refund_pathway(inputs.summary_date)

    result = CalculationResult(
        entry_number=inputs.entry_number,
        summary_date=inputs.summary_date,
        country_of_origin=(
            inputs.line_items[0].country_of_origin if inputs.line_items else ""
        ),
        mode_of_transport=inputs.mode_of_transport,
        total_entered_value=tv,
        line_duty_components=all_components,
        mpf=mpf_fee,
        hmf=hmf_fee,
        total_duty=total_duty,
        estimated_refund=estimated_refund,
        refund_pathway=pathway,
        days_since_summary=days_elapsed,
        pathway_rationale=_pathway_rationale(pathway, days_elapsed),
    )

    # ⑥ BR-011: immutable audit trail
    await _write_audit(db, calculation_id, result, inputs)

    return result
