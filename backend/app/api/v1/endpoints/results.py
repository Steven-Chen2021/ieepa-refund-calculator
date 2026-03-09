"""
Results endpoint
================
GET /api/v1/results/{calculation_id}  — retrieve a completed calculation result
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.models.calculation import Calculation, CalculationStatus
from app.models.document import Document
from app.api.v1.endpoints.documents import merge_doc_fields

router = APIRouter(prefix="/results", tags=["results"])

# Only IEEPA components are refundable (BR-008)
_REFUNDABLE: frozenset[str] = frozenset({"IEEPA"})


@router.get(
    "/{calculation_id}",
    status_code=status.HTTP_200_OK,
    summary="Retrieve a completed tariff calculation result",
)
async def get_result(
    calculation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return the full calculation result for *calculation_id*.

    Returns 202 while the calculation is still pending/calculating so the
    frontend polling loop knows to retry.
    Returns 404 if not found.
    """
    res = await db.execute(
        select(Calculation).where(Calculation.id == calculation_id)
    )
    calc: Calculation | None = res.scalar_one_or_none()

    if calc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")

    if calc.status in (CalculationStatus.pending, CalculationStatus.calculating):
        raise HTTPException(status_code=status.HTTP_202_ACCEPTED, detail="Calculation in progress")

    if calc.status == CalculationStatus.failed:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Calculation failed",
        )

    # Load associated document for supplementary fields
    doc_res = await db.execute(select(Document).where(Document.id == calc.document_id))
    doc: Document | None = doc_res.scalar_one_or_none()
    extra = merge_doc_fields(
        doc.extracted_fields if doc else None,
        doc.corrections if doc else None,
    )

    # Aggregate duty components by tariff type (sum amounts, use first rate)
    components: list[dict] = calc.duty_components or []
    agg: dict[str, dict] = {}
    for c in components:
        tt = c.get("tariff_type", "")
        if tt not in agg:
            agg[tt] = {"amount": 0.0, "rate_pct": float(c.get("rate_pct", 0))}
        agg[tt]["amount"] += float(c.get("amount", 0))

    tariff_lines = []
    for tt in ("MFN", "IEEPA", "S301", "S232", "MPF", "HMF"):
        if tt in agg:
            tariff_lines.append({
                "tariff_type": tt,
                "rate": round(agg[tt]["rate_pct"], 6),
                "amount": round(agg[tt]["amount"], 2),
                "refundable": tt in _REFUNDABLE,
            })

    calculated_at = (
        calc.updated_at.isoformat()  # type: ignore[attr-defined]
        if hasattr(calc, "updated_at") and calc.updated_at  # type: ignore[attr-defined]
        else ""
    )

    return {
        "success": True,
        "data": {
            "calculation_id": str(calc.id),
            "entry_number": calc.entry_number or extra.get("entry_number", ""),
            "filer_code": extra.get("filer_code", ""),
            "summary_date": (
                calc.summary_date.isoformat() if calc.summary_date else extra.get("summary_date", "")
            ),
            "import_date": extra.get("import_date", ""),
            "bl_number": extra.get("bl_number", ""),
            "country_of_origin": calc.country_of_origin or extra.get("country_of_origin", ""),
            "port_of_entry": extra.get("port_code", "") or extra.get("port_of_entry", ""),
            "importer_name": calc.importer_name or extra.get("importer_name", ""),
            "mode_of_transport": calc.mode_of_transport or extra.get("mode_of_transport", ""),
            "estimated_refund": float(calc.estimated_refund or 0),
            "refund_pathway": (
                calc.refund_pathway.value
                if calc.refund_pathway
                else "INELIGIBLE"
            ),
            "days_elapsed": calc.days_since_summary or 0,
            "tariff_lines": tariff_lines,
            "total_duty": float(calc.total_duty or 0),
            "calculated_at": calculated_at,
        },
        "error": None,
        "meta": None,
    }
