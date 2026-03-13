"""
Calculation engine unit tests.
Covers pure helper functions (no DB / Redis required).

Business rules under test:
  BR-005  calculate_mpf  — 0.3464%, floor $32.71, cap $634.62
  BR-006  calculate_hmf  — 0.125%, vessel only
  BR-007  determine_refund_pathway — PSC ≤15 d, PROTEST 16–180 d, INELIGIBLE >180 d
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.engine.calculator import (
    MPF_CAP,
    MPF_FLOOR,
    MPF_RATE,
    HMF_RATE,
    calculate_hmf,
    calculate_mpf,
    determine_refund_pathway,
)


# ---------------------------------------------------------------------------
# BR-005: Merchandise Processing Fee (TC-CALC-005)
# formula : total_entered_value × 0.3464%
# floor   : $32.71
# cap     : $634.62
# ---------------------------------------------------------------------------

class TestCalculateMPF:
    """Boundary-value tests for calculate_mpf() per BR-005."""

    # ── below floor ────────────────────────────────────────────────────────
    def test_below_floor_returns_floor(self):
        # 9000 × 0.003464 = 31.176 → floor → 32.71
        assert calculate_mpf(Decimal("9000")) == MPF_FLOOR

    def test_just_below_floor_raw(self):
        # 9440 × 0.003464 = 32.70016 → rounds to 32.70 → floor → 32.71
        assert calculate_mpf(Decimal("9440")) == MPF_FLOOR

    # ── at / near floor ────────────────────────────────────────────────────
    def test_at_floor_boundary(self):
        # 9444 × 0.003464 = 32.714016 → rounds to 32.71 → equals floor → 32.71
        assert calculate_mpf(Decimal("9444")) == MPF_FLOOR

    def test_just_above_floor(self):
        # 9445 × 0.003464 = 32.71748 → rounds to 32.72 → above floor → 32.72
        assert calculate_mpf(Decimal("9445")) == Decimal("32.72")

    # ── normal range ────────────────────────────────────────────────────────
    def test_normal_range(self):
        # 50000 × 0.003464 = 173.20
        assert calculate_mpf(Decimal("50000")) == Decimal("173.20")

    def test_integer_input_coerced(self):
        assert calculate_mpf(50000) == Decimal("173.20")

    def test_float_input_coerced(self):
        assert calculate_mpf(50000.0) == Decimal("173.20")

    # ── at / above cap ──────────────────────────────────────────────────────
    def test_above_cap_returns_cap(self):
        # 200000 × 0.003464 = 692.80 → cap → 634.62
        assert calculate_mpf(Decimal("200000")) == MPF_CAP

    def test_just_above_cap(self):
        # 183215 × 0.003464 = 634.65676 → rounds to 634.66 → cap → 634.62
        assert calculate_mpf(Decimal("183215")) == MPF_CAP

    # ── constants sanity ────────────────────────────────────────────────────
    def test_mpf_rate_constant(self):
        assert MPF_RATE == Decimal("0.003464")

    def test_mpf_floor_constant(self):
        assert MPF_FLOOR == Decimal("32.71")

    def test_mpf_cap_constant(self):
        assert MPF_CAP == Decimal("634.62")


# ---------------------------------------------------------------------------
# BR-006: Harbor Maintenance Fee (TC-CALC-006)
# rate    : 0.125%
# applies : mode_of_transport == 'vessel' only
# ---------------------------------------------------------------------------

class TestCalculateHMF:
    """Tests for calculate_hmf() per BR-006."""

    def test_vessel_calculates_hmf(self):
        # 20000 × 0.00125 = 25.00
        assert calculate_hmf(Decimal("20000"), "vessel") == Decimal("25.00")

    def test_air_returns_zero(self):
        assert calculate_hmf(Decimal("20000"), "air") == Decimal("0.00")

    def test_truck_returns_zero(self):
        assert calculate_hmf(Decimal("20000"), "truck") == Decimal("0.00")

    def test_unknown_transport_returns_zero(self):
        assert calculate_hmf(Decimal("20000"), "other") == Decimal("0.00")

    def test_vessel_case_insensitive(self):
        # BR-006 comparison uses .lower() — uppercase should still work
        assert calculate_hmf(Decimal("20000"), "VESSEL") == Decimal("25.00")
        assert calculate_hmf(Decimal("20000"), "Vessel") == Decimal("25.00")

    def test_hmf_rate_constant(self):
        assert HMF_RATE == Decimal("0.00125")

    def test_vessel_large_value(self):
        # 1_000_000 × 0.00125 = 1250.00
        assert calculate_hmf(Decimal("1000000"), "vessel") == Decimal("1250.00")

    def test_float_input(self):
        assert calculate_hmf(20000.0, "vessel") == Decimal("25.00")


# ---------------------------------------------------------------------------
# BR-007: Refund pathway (TC-CALC-007)
# PSC        : days_elapsed ≤ 15
# PROTEST    : 16 ≤ days_elapsed ≤ 180
# INELIGIBLE : days_elapsed > 180
# ---------------------------------------------------------------------------

class TestDetermineRefundPathway:
    """Boundary-value tests for determine_refund_pathway() per BR-007."""

    def test_same_day_is_psc(self):
        assert determine_refund_pathway(date.today()) == "PSC"

    def test_day_1_is_psc(self):
        d = date.today() - timedelta(days=1)
        assert determine_refund_pathway(d) == "PSC"

    def test_day_14_is_psc(self):
        d = date.today() - timedelta(days=14)
        assert determine_refund_pathway(d) == "PSC"

    def test_day_15_boundary_is_psc(self):
        """TC-CALC-007 Case C: day 15 is still PSC."""
        d = date.today() - timedelta(days=15)
        assert determine_refund_pathway(d) == "PSC"

    def test_day_16_boundary_is_protest(self):
        """TC-CALC-007 Case D: day 16 crosses into PROTEST."""
        d = date.today() - timedelta(days=16)
        assert determine_refund_pathway(d) == "PROTEST"

    def test_day_100_is_protest(self):
        d = date.today() - timedelta(days=100)
        assert determine_refund_pathway(d) == "PROTEST"

    def test_day_180_boundary_is_protest(self):
        """TC-CALC-007 Case F: day 180 is still PROTEST."""
        d = date.today() - timedelta(days=180)
        assert determine_refund_pathway(d) == "PROTEST"

    def test_day_181_boundary_is_ineligible(self):
        """TC-CALC-007 Case G: day 181 is INELIGIBLE."""
        d = date.today() - timedelta(days=181)
        assert determine_refund_pathway(d) == "INELIGIBLE"

    def test_day_365_is_ineligible(self):
        d = date.today() - timedelta(days=365)
        assert determine_refund_pathway(d) == "INELIGIBLE"

    @pytest.mark.parametrize("days,expected", [
        (0,   "PSC"),
        (15,  "PSC"),
        (16,  "PROTEST"),
        (180, "PROTEST"),
        (181, "INELIGIBLE"),
        (365, "INELIGIBLE"),
    ])
    def test_pathway_parametrized(self, days: int, expected: str):
        """Full parametric coverage of all boundary cases from TC-CALC-007."""
        summary_date = date.today() - timedelta(days=days)
        assert determine_refund_pathway(summary_date) == expected
