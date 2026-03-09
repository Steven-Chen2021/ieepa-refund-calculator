"""
Shared data types for the OCR pipeline.

Used by both the Google Document AI provider and the pytesseract fallback,
and consumed by the Celery OCR task.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── 7501_Parse.md §2B: IEEPA supplemental HTS codes (退稅目標) ─────────────
IEEPA_HTS_CODES: frozenset[str] = frozenset({
    "9903.01.24",
    "9903.01.25",
})


@dataclass
class OcrField:
    """
    Represents one extracted form field with its confidence score.

    ``review_required`` is True when confidence < OCR_CONFIDENCE_THRESHOLD (0.85,
    per 7501_Parse.md §3 and BR-010). Shown as amber/yellow in the UI.

    ``read_failed`` is True when confidence < OCR_FAILED_THRESHOLD (0.50,
    per 7501_Parse.md §3). Shown as red with '讀取失敗' label in the UI.
    """
    value: Any               # str | float | int | None
    confidence: float        # 0.0 – 1.0
    review_required: bool    # True when confidence < 0.85
    read_failed: bool = False  # True when confidence < 0.50

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "confidence": round(self.confidence, 4),
            "review_required": self.review_required,
            "read_failed": self.read_failed,
        }


@dataclass
class OcrResult:
    """
    Full OCR result from either the primary or fallback engine.

    Header fields extracted per 7501_Parse.md §2A:
      entry_number     – Box 1 entry number portion  (e.g. "2810374-2")
      filer_code       – Box 1 filer code portion     (e.g. "MYK")
      entry_type       – Box 2                         (e.g. "01")
      import_date      – Box 11, formatted YYYY-MM-DD  (e.g. "2026-01-28")
      bl_number        – Box 12 B/L or AWB No.         (e.g. "HLCUSHA260121460")
      total_duty       – Box 37 duty total, no $ sign  (e.g. "17625.60")
      summary_date     – Box 3 entry summary date
      country_of_origin, mode_of_transport, importer_name, port_code, …

    Line items (Box 27/29/33) include ``is_ieepa`` and ``tariff_category`` fields
    to identify IEEPA 退稅目標 rows (9903.01.24 / 9903.01.25).
    """
    provider: str             # "google_document_ai" | "tesseract"
    overall_confidence: float # 0.0 – 1.0; < 0.50 triggers fallback / rejection

    fields: dict[str, OcrField] = field(default_factory=dict)

    # Each dict has string keys mapping to OcrField values.
    # Special non-OcrField keys per row: "line_number" (int), "is_ieepa" (bool),
    # "tariff_category" (str: "main" | "S301" | "IEEPA" | "other")
    line_items: list[dict[str, Any]] = field(default_factory=list)

    raw_text: str = ""

    def to_extracted_fields_dict(self) -> dict:
        """
        Serialise to the ``extracted_fields`` JSONB structure stored in the
        Document model and returned by GET /documents/{job_id}/status.
        """
        result: dict = {k: v.to_dict() for k, v in self.fields.items()}

        serialised_items = []
        for item in self.line_items:
            row: dict = {}
            for k, v in item.items():
                if isinstance(v, OcrField):
                    row[k] = v.to_dict()
                else:
                    row[k] = v  # line_number (int), is_ieepa (bool), tariff_category (str)
            serialised_items.append(row)
        result["line_items"] = serialised_items

        review_count = sum(
            1 for f in self.fields.values() if f.review_required
        ) + sum(
            1
            for item in self.line_items
            for v in item.values()
            if isinstance(v, OcrField) and v.review_required
        )
        result["review_required_count"] = review_count
        return result
