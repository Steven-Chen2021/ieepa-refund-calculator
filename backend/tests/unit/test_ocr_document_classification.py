from app.ocr.models import OcrField, OcrResult
from app.tasks.ocr import _classify_failure_code, _looks_like_cbp_7501


def _field(value: str | None, confidence: float = 0.9) -> OcrField:
    return OcrField(
        value=value,
        confidence=confidence,
        review_required=confidence < 0.8,
        read_failed=confidence < 0.5,
    )


class TestOcrDocumentClassification:
    def test_recognises_7501_from_populated_fields(self):
        result = OcrResult(
            provider="tesseract",
            overall_confidence=0.9,
            fields={
                "filer_code": _field("ABC"),
                "entry_number": _field("1234567-8"),
                "summary_date": _field("02/19/2026"),
            },
            line_items=[],
            raw_text="irrelevant",
        )

        assert _looks_like_cbp_7501(result) is True

    def test_recognises_7501_from_line_items(self):
        result = OcrResult(
            provider="tesseract",
            overall_confidence=0.75,
            fields={"filer_code": _field("ABC")},
            line_items=[{"hts_code": _field("9903.01.25")}],
            raw_text="Entry Summary 1. Filer Code/Entry No. 12. B/L or AWB No.",
        )

        assert _looks_like_cbp_7501(result) is True

    def test_non_7501_document_returns_invalid_format(self):
        result = OcrResult(
            provider="tesseract",
            overall_confidence=0.9,
            fields={},
            line_items=[],
            raw_text="Quarterly sales report for division north america.",
        )

        assert _looks_like_cbp_7501(result) is False
        assert _classify_failure_code(result) == "INVALID_7501_FORMAT"

    def test_unreadable_document_stays_unrecognised(self):
        result = OcrResult(
            provider="tesseract",
            overall_confidence=0.0,
            fields={},
            line_items=[],
            raw_text="",
        )

        assert _looks_like_cbp_7501(result) is False
        assert _classify_failure_code(result) == "UNRECOGNISED_DOCUMENT"
