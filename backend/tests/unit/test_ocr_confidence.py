"""
OCR confidence threshold unit tests.

Business rule under test:
  BR-010  Per-field confidence < 0.80 → review_required = True
          Document confidence < 0.50 → UNRECOGNISED_DOCUMENT (status=failed)

Test cases per TC-OCR-002:
  Case A: 0.95 → review_required=False
  Case B: 0.79 → review_required=True
  Case C: 0.80 → review_required=False  (≥ 0.80 is NOT flagged)
  Case D: 0.50 → review_required=True   (below threshold, but NOT read_failed)
          0.49 → read_failed=True
"""
import pytest

from app.core.config import settings
from app.ocr.google_docai import _make_field as docai_make_field  # type: ignore[attr-defined]
from app.ocr.tesseract import _make_field as tesseract_make_field  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Settings sanity checks
# ---------------------------------------------------------------------------

class TestOcrThresholdSettings:
    """Verify config values match BR-010 specification."""

    def test_review_threshold_is_080(self):
        """BR-010: review_required threshold must be exactly 0.80."""
        assert settings.OCR_CONFIDENCE_THRESHOLD == pytest.approx(0.80)

    def test_failed_threshold_is_050(self):
        """BR-010: document failure threshold must be exactly 0.50."""
        assert settings.OCR_FAILED_THRESHOLD == pytest.approx(0.50)

    def test_review_threshold_strictly_less_than_failed(self):
        # review_threshold > failed_threshold by design
        assert settings.OCR_CONFIDENCE_THRESHOLD > settings.OCR_FAILED_THRESHOLD


# ---------------------------------------------------------------------------
# Google Document AI provider — _make_field() threshold behaviour
# ---------------------------------------------------------------------------

class TestDocAiMakeField:
    """TC-OCR-002 cases applied to the Document AI field factory."""

    def test_high_confidence_no_flags(self):
        """TC-OCR-002 Case A: 0.95 → review_required=False, read_failed=False."""
        field = docai_make_field("value", 0.95)
        assert field.review_required is False
        assert field.read_failed is False
        assert field.confidence == pytest.approx(0.95)

    def test_confidence_079_requires_review(self):
        """TC-OCR-002 Case B: 0.79 < 0.80 → review_required=True."""
        field = docai_make_field("value", 0.79)
        assert field.review_required is True
        assert field.read_failed is False

    def test_confidence_080_no_review(self):
        """TC-OCR-002 Case C: 0.80 is NOT < 0.80 → review_required=False."""
        field = docai_make_field("value", 0.80)
        assert field.review_required is False
        assert field.read_failed is False

    def test_confidence_081_no_review(self):
        # Just above threshold
        field = docai_make_field("value", 0.81)
        assert field.review_required is False

    def test_confidence_050_review_but_not_failed(self):
        """TC-OCR-002 Case D: 0.50 is NOT < 0.50, so read_failed=False."""
        field = docai_make_field("value", 0.50)
        assert field.review_required is True
        assert field.read_failed is False  # 0.50 == threshold, not below it

    def test_confidence_049_is_read_failed(self):
        field = docai_make_field("value", 0.49)
        assert field.review_required is True
        assert field.read_failed is True

    def test_confidence_zero_is_read_failed(self):
        field = docai_make_field(None, 0.0)
        assert field.review_required is True
        assert field.read_failed is True

    @pytest.mark.parametrize("confidence,expected_review,expected_failed", [
        (0.95, False, False),
        (0.80, False, False),
        (0.79, True,  False),
        (0.51, True,  False),
        (0.50, True,  False),
        (0.49, True,  True),
        (0.00, True,  True),
    ])
    def test_parametrized_thresholds(
        self,
        confidence: float,
        expected_review: bool,
        expected_failed: bool,
    ):
        field = docai_make_field("v", confidence)
        assert field.review_required is expected_review, (
            f"confidence={confidence}: expected review_required={expected_review}"
        )
        assert field.read_failed is expected_failed, (
            f"confidence={confidence}: expected read_failed={expected_failed}"
        )


# ---------------------------------------------------------------------------
# Tesseract provider — _make_field() threshold behaviour
# ---------------------------------------------------------------------------

class TestTesseractMakeField:
    """Same TC-OCR-002 cases applied to the Tesseract field factory."""

    def test_high_confidence_no_flags(self):
        field = tesseract_make_field("value", 0.90)
        assert field.review_required is False
        assert field.read_failed is False

    def test_confidence_079_requires_review(self):
        field = tesseract_make_field("value", 0.79)
        assert field.review_required is True
        assert field.read_failed is False

    def test_confidence_080_no_review(self):
        field = tesseract_make_field("value", 0.80)
        assert field.review_required is False

    def test_confidence_049_is_read_failed(self):
        field = tesseract_make_field("value", 0.49)
        assert field.read_failed is True

    @pytest.mark.parametrize("confidence,expected_review,expected_failed", [
        (0.90, False, False),
        (0.80, False, False),
        (0.79, True,  False),
        (0.50, True,  False),
        (0.49, True,  True),
    ])
    def test_parametrized_thresholds(
        self,
        confidence: float,
        expected_review: bool,
        expected_failed: bool,
    ):
        field = tesseract_make_field("v", confidence)
        assert field.review_required is expected_review
        assert field.read_failed is expected_failed
