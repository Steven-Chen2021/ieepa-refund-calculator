"""
Post-OCR HTS Rate Enrichment Service
=====================================
Resolves the authoritative duty rate for every extracted HTS code by querying
the ``tariff_rates`` DB table — bypassing Redis since this runs inside the OCR
Celery task which has no Redis client.

Why this is needed
------------------
CBP Form 7501 Box 33 omits 0% duty rates entirely, so the number of printed
rates is less than or equal to the number of HTS codes on a line group.
Positional matching of rates to codes is therefore unreliable.  The OCR
parsers (both tesseract and DocAI) now extract rates into ``pdf_rate_duty_pairs``
for cross-validation only and leave ``duty_rate`` / ``duty_amount`` as
_missing_field().  This service fills them from the DB.

Called from ``app/tasks/ocr.py`` after OCR and before ``_set_status``.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tariff_rate import TariffRate, TariffType
from app.ocr.models import OcrField

logger = logging.getLogger(__name__)

# ── Confidence for DB-derived fields ─────────────────────────────────────────
_DB_CONFIDENCE: float = 0.95
_REVIEW_THRESHOLD: float = 0.80
_FAILED_THRESHOLD: float = 0.50

# ── HTS prefix → TariffType ──────────────────────────────────────────────────
_IEEPA_RE = re.compile(r"^9903\.01\.", re.I)
_S301_RE = re.compile(r"^9903\.88\.", re.I)
# Section 232 steel: 9903.80.xx, 9903.81.xx, 9903.82.xx
_S232_STEEL_RE = re.compile(r"^9903\.8[012]\.", re.I)
# Section 232 aluminium: 9903.85.xx, 9903.86.xx
_S232_ALUM_RE = re.compile(r"^9903\.8[56]\.", re.I)
# Any other 9903.xx.xx not covered above
_OTHER_9903_RE = re.compile(r"^9903\.", re.I)


def infer_tariff_type(hts_code: str) -> str | None:
    """
    Infer the TariffType string from an HTS code prefix.

    Returns the TariffType enum value string, or ``None`` for unknown
    9903.xx.xx codes where the enrichment will try S232 then S301.

    Examples
    --------
    >>> infer_tariff_type("9903.01.24")  # IEEPA
    'IEEPA'
    >>> infer_tariff_type("9903.88.03")  # Section 301
    'S301'
    >>> infer_tariff_type("9903.85.08")  # Section 232 aluminium
    'S232'
    >>> infer_tariff_type("8508.70.0000")  # regular HTS
    'MFN'
    >>> infer_tariff_type("9903.99.00")  # unknown supplemental
    None
    """
    code = hts_code.strip()
    if _IEEPA_RE.match(code):
        return TariffType.IEEPA.value
    if _S301_RE.match(code):
        return TariffType.S301.value
    if _S232_STEEL_RE.match(code) or _S232_ALUM_RE.match(code):
        return TariffType.S232.value
    if _OTHER_9903_RE.match(code):
        # Unknown supplemental — caller will try S232 then S301
        return None
    # Regular commercial HTS code
    return TariffType.MFN.value


def _make_db_field(value: Any) -> OcrField:
    """Create an OcrField populated from the DB (high confidence)."""
    return OcrField(
        value=value,
        confidence=_DB_CONFIDENCE,
        review_required=_DB_CONFIDENCE < _REVIEW_THRESHOLD,
        read_failed=_DB_CONFIDENCE < _FAILED_THRESHOLD,
    )


def _get_val(item: dict[str, Any], key: str) -> Any:
    """Extract the raw value from an OcrField dict or plain value."""
    v = item.get(key)
    if isinstance(v, OcrField):
        return v.value
    if isinstance(v, dict):
        return v.get("value")
    return v


async def _query_rate(
    session: AsyncSession,
    hts_code: str,
    country_code: str,
    tariff_type: str,
    summary_date: date,
) -> Decimal | None:
    """
    DB-only tariff rate lookup — same composite-key logic as
    ``calculator._query_db_tariff_rate`` but without Redis.

    Returns None when no active rate record covers ``summary_date``.
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
        .order_by(TariffRate.country_code.desc())  # exact country before wildcard '*'
        .limit(1)
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return Decimal(str(row)) if row is not None else None


async def _resolve_rate(
    session: AsyncSession,
    hts_code: str,
    country_code: str,
    tariff_type_hint: str | None,
    summary_date: date,
) -> tuple[Decimal | None, str | None]:
    """
    Resolve the applicable rate for ``hts_code``.

    Returns ``(rate_decimal_fraction, resolved_tariff_type)`` where the rate is
    a decimal fraction (e.g. ``Decimal("0.25")`` for 25%).

    For unknown 9903.xx.xx codes (``tariff_type_hint=None``), tries S232 then
    S301 in order.  IEEPA returns $0 immediately for non-CN goods (BR-001).
    """
    if tariff_type_hint == TariffType.IEEPA.value and country_code.upper() != "CN":
        # BR-001: IEEPA only applies to Chinese-origin goods
        return Decimal("0"), TariffType.IEEPA.value

    if tariff_type_hint is not None:
        rate = await _query_rate(session, hts_code, country_code, tariff_type_hint, summary_date)
        return rate, tariff_type_hint

    # Unknown supplemental (9903.xx.xx not matching a known prefix):
    # try S232 first, then S301
    rate = await _query_rate(session, hts_code, country_code, TariffType.S232.value, summary_date)
    if rate is not None:
        return rate, TariffType.S232.value
    rate = await _query_rate(session, hts_code, country_code, TariffType.S301.value, summary_date)
    if rate is not None:
        return rate, TariffType.S301.value
    return None, None


async def enrich_extracted_fields(
    extracted_dict: dict[str, Any],
    country_code: str,
    summary_date: date,
    session: AsyncSession,
) -> dict[str, Any]:
    """
    Enrich ``extracted_dict["line_items"]`` in-place with DB-sourced duty
    rates and calculated duty amounts.

    For each line item:
      - Infers TariffType from the HTS code prefix via ``infer_tariff_type``.
      - Queries the ``tariff_rates`` table for the rate applicable on
        ``summary_date`` (same composite-key logic as the calculator).
      - Sets ``duty_rate`` (e.g. ``"25%"``) and ``duty_amount`` as OcrFields
        with confidence 0.95.
      - Sets ``rate_source = "db"`` on success, ``"not_found"`` on miss.
      - Updates ``tariff_category`` for previously-unknown 9903.xx.xx codes.
      - Performs cross-validation against ``pdf_rate_duty_pairs`` (warn only).

    ``country_code`` should be the entry-level country of origin (Box 10).
    ``summary_date`` must be the entry summary date (Box 3) — not today.

    Returns the modified ``extracted_dict``.
    """
    line_items: list[dict[str, Any]] = extracted_dict.get("line_items", [])
    if not line_items:
        return extracted_dict

    # Group items by line_number for cross-validation
    groups: dict[Any, list[dict[str, Any]]] = {}
    for item in line_items:
        key = _get_val(item, "line_number") or "__ungrouped__"
        groups.setdefault(key, []).append(item)

    for group_items in groups.values():
        # Process each item and accumulate DB-computed duties for cross-validation
        group_db_total = Decimal("0")
        main_item_for_xval: dict[str, Any] | None = None

        for item in group_items:
            hts_code = _get_val(item, "hts_code")
            if not hts_code:
                continue
            hts_str = str(hts_code).strip()

            tariff_type_hint = infer_tariff_type(hts_str)
            rate_pct, resolved_type = await _resolve_rate(
                session, hts_str, country_code, tariff_type_hint, summary_date,
            )

            if rate_pct is None:
                item["rate_source"] = "not_found"
                # Explicitly clear any stale OCR-assigned rate/amount so wrong
                # values from positional OCR mapping do not persist in the UI.
                _none_field = OcrField(
                    value=None, confidence=0.0, review_required=True, read_failed=True
                ).to_dict()
                item["duty_rate"] = _none_field
                item["duty_amount"] = _none_field
                logger.warning(
                    "No DB rate found: hts=%s country=%s type_hint=%s date=%s",
                    hts_str, country_code, tariff_type_hint, summary_date,
                )
                continue

            # Format as percentage string (e.g., Decimal("0.25") → "25%")
            rate_display = f"{(rate_pct * 100).normalize():f}%"
            item["duty_rate"] = _make_db_field(rate_display).to_dict()
            item["rate_source"] = "db"

            # Update tariff_category when OCR couldn't classify the code or
            # misclassified a S232 code as "other_supplemental"
            if resolved_type and (
                tariff_type_hint is None
                or item.get("tariff_category") == "other_supplemental"
            ):
                item["tariff_category"] = resolved_type

            # Compute duty amount when entered_value is available
            ev_raw = _get_val(item, "entered_value")
            if ev_raw is not None and str(ev_raw).strip():
                try:
                    ev = Decimal(str(ev_raw).replace(",", "").strip())
                    duty = (ev * rate_pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    item["duty_amount"] = _make_db_field(str(duty)).to_dict()
                    group_db_total += duty
                except Exception:
                    logger.warning(
                        "Could not compute duty_amount: hts=%s ev=%r", hts_str, ev_raw
                    )

            # Track main item (has pdf_rate_duty_pairs) for cross-validation
            if item.get("pdf_rate_duty_pairs"):
                main_item_for_xval = item

        # Cross-validate: sum of DB duties vs sum of PDF-printed duties
        if main_item_for_xval is not None:
            _cross_validate_group(
                group_db_total, main_item_for_xval["pdf_rate_duty_pairs"]
            )

    return extracted_dict


def _cross_validate_group(
    db_total: Decimal,
    pdf_pairs: list[dict[str, str]],
) -> None:
    """
    Warn if the DB-computed duty total differs from the PDF-printed duty total
    by more than 5%.  Informational only — DB rates always take precedence.
    """
    try:
        pdf_total = sum(
            Decimal(p["duty_amount"].replace(",", ""))
            for p in pdf_pairs
            if p.get("duty_amount")
        )
        if pdf_total == Decimal("0"):
            return
        diff_pct = abs(db_total - pdf_total) / pdf_total
        if diff_pct > Decimal("0.05"):
            logger.warning(
                "Duty cross-validation mismatch: db_total=%.2f pdf_total=%.2f diff=%.1f%%",
                db_total, pdf_total, float(diff_pct) * 100,
            )
    except Exception:
        pass  # cross-validation is best-effort; never block the pipeline
