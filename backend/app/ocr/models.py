"""
Shared data types for the OCR pipeline.

Used by both the Google Document AI provider and the pytesseract fallback,
and consumed by the Celery OCR task.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OcrField:
    """
    Represents one extracted form field with its confidence score.

    ``review_required`` is set to True when confidence < OCR_CONFIDENCE_THRESHOLD
    (0.80 per BR-010).
    """
    value: Any               # str | float | int | None
    confidence: float        # 0.0 – 1.0
    review_required: bool    # True when confidence < 0.80 (BR-010)

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "confidence": round(self.confidence, 4),
            "review_required": self.review_required,
        }


@dataclass
class OcrResult:
    """
    Full OCR result from either the primary or fallback engine.

    ``fields`` holds the header-level extracted fields.
    ``line_items`` holds per-HTS-line extracted data.
    ``overall_confidence`` is the mean confidence across all extracted fields.
    """
    provider: str             # "google_document_ai" | "tesseract"
    overall_confidence: float # 0.0 – 1.0; < 0.50 triggers fallback / rejection

    # Header fields (entry_number, summary_date, country_of_origin, etc.)
    fields: dict[str, OcrField] = field(default_factory=dict)

    # Line-item fields; each dict has keys: hts_code, entered_value, duty_rate,
    # duty_amount, country_of_origin (all OcrField values)
    line_items: list[dict[str, OcrField]] = field(default_factory=list)

    raw_text: str = ""  # full OCR text (useful for debugging / audit)

    def to_extracted_fields_dict(self) -> dict:
        """
        Serialise to the ``extracted_fields`` JSONB structure stored in the
        Document model and returned by GET /documents/{job_id}/status.
        """
        result: dict = {k: v.to_dict() for k, v in self.fields.items()}
        result["line_items"] = [
            {k: v.to_dict() for k, v in item.items()}
            for item in self.line_items
        ]
        # Count fields that need review (excluding line_items key itself)
        review_count = sum(
            1 for f in self.fields.values() if f.review_required
        ) + sum(
            1
            for item in self.line_items
            for f in item.values()
            if f.review_required
        )
        result["review_required_count"] = review_count
        return result
