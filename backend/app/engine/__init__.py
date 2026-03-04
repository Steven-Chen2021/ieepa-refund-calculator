"""
IEEPA Tariff Calculation Engine package.

Public surface:
    calculate_entry()          — full pipeline for one CBP Form 7501
    calculate_mpf()            — pure MPF helper (BR-005, TC-CALC-005)
    calculate_hmf()            — pure HMF helper (BR-006)
    determine_refund_pathway() — pure pathway helper (BR-007, TC-CALC-007)
    get_tariff_rate()          — cached rate lookup (BR-009)
    EntryInput, LineItem       — input dataclasses
    CalculationResult          — output dataclass
"""
from app.engine.calculator import (
    EntryFee,
    EntryInput,
    LineItem,
    CalculationResult,
    DutyComponent,
    calculate_entry,
    calculate_hmf,
    calculate_mpf,
    determine_refund_pathway,
    get_tariff_rate,
)

__all__ = [
    "EntryFee",
    "EntryInput",
    "LineItem",
    "CalculationResult",
    "DutyComponent",
    "calculate_entry",
    "calculate_hmf",
    "calculate_mpf",
    "determine_refund_pathway",
    "get_tariff_rate",
]
