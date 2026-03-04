"""
pytesseract fallback OCR provider
===================================
Activated when Google Document AI is unavailable or returns overall
confidence < 0.50 (Tech_Stack.md §3.1.6).

Strategy
--------
1. ``pdf2image.convert_from_bytes`` → list of PIL Images (one per page).
2. ``pytesseract.image_to_data``    → per-word confidence (0–100 scale).
3. ``pytesseract.image_to_string``  → full text for regex field extraction.
4. Regex patterns attempt to locate CBP Form 7501 field values in the text.
5. Per-field confidence = average word confidence in the extracted region;
   bounded to ≤ 0.75 to reflect that regex extraction is less reliable than
   Document AI's form understanding.

Confidence notes
----------------
- Tesseract ``image_to_data`` returns ``conf`` in range 0–100 (−1 for layout
  elements).  We normalise to 0.0–1.0 and cap at 0.75.
- If a field cannot be extracted, confidence is set to 0.0 and the value is
  None → review_required = True (BR-010).
"""
from __future__ import annotations

import logging
import re
import statistics
from typing import Any

from app.core.config import settings
from app.ocr.models import OcrField, OcrResult

logger = logging.getLogger(__name__)

_REVIEW_THRESHOLD: float = settings.OCR_CONFIDENCE_THRESHOLD  # 0.80

# Tesseract confidence is less reliable than Document AI; cap it so fields
# never appear more confident than this via pytesseract.
_TESSERACT_MAX_CONFIDENCE: float = 0.75

# ── CBP Form 7501 regex extraction patterns ───────────────────────────────────
# Each pattern has one capturing group for the field value.

_HEADER_REGEXES: dict[str, re.Pattern] = {
    "entry_number": re.compile(
        r"(?i)entry\s*no\.?\s*[:\-]?\s*([A-Z0-9]{3}[-\s]\d{7}[-\s]\d)", re.M
    ),
    "entry_type": re.compile(
        r"(?i)entry\s*type\s*[:\-]?\s*(\d{2})", re.M
    ),
    "summary_date": re.compile(
        r"(?i)(?:entry\s*summary\s*)?date\s*[:\-]?\s*"
        r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|\d{4}[/\-\.]\d{2}[/\-\.]\d{2})",
        re.M,
    ),
    "port_code": re.compile(
        r"(?i)port\s*(?:of\s*entry)?\s*(?:code)?\s*[:\-]?\s*(\d{4})", re.M
    ),
    "importer_name": re.compile(
        r"(?i)importer\s*(?:of\s*record)?\s*[:\-]?\s*([A-Za-z0-9 ,\.&'-]{3,60})", re.M
    ),
    "country_of_origin": re.compile(
        r"(?i)country\s*of\s*origin\s*[:\-]?\s*([A-Z]{2})\b", re.M
    ),
    "mode_of_transport": re.compile(
        r"(?i)mode\s*(?:of\s*)?trans(?:port)?\s*[:\-]?\s*(vessel|air|truck|rail)", re.M
    ),
    "total_entered_value": re.compile(
        r"(?i)(?:total\s*)?entered\s*value\s*[:\-]?\s*\$?([\d,]+\.?\d{0,2})", re.M
    ),
    "total_duty_fees": re.compile(
        r"(?i)total\s*(?:duty|fees|amount\s*due)\s*[:\-]?\s*\$?([\d,]+\.?\d{0,2})", re.M
    ),
}

# Line-item regex: matches repeated blocks that start with an HTS code
# Format: NNNN.NN.NNNN
_HTS_BLOCK_RE = re.compile(
    r"(\d{4}\.\d{2}\.\d{4})"             # HTS code
    r"[^\n]*?\n?"                          # rest of line
    r"(?:.*?(\$?[\d,]+\.\d{2}))?"         # entered value (first dollar amount)
    r"(?:.*?(\d+\.?\d*\s*%))?",           # duty rate
    re.M | re.S,
)


def _clean_value(raw: str) -> str:
    return raw.strip().replace(",", "")


def _extract_header_fields(text: str, base_conf: float) -> dict[str, OcrField]:
    """Run header regex patterns against *text* and return OcrField mapping."""
    fields: dict[str, OcrField] = {}
    for field_name, pattern in _HEADER_REGEXES.items():
        match = pattern.search(text)
        if match:
            value = match.group(1).strip()
            # Slightly reduce confidence for fields extracted by regex
            conf = min(base_conf * 0.90, _TESSERACT_MAX_CONFIDENCE)
            fields[field_name] = OcrField(
                value=value,
                confidence=conf,
                review_required=conf < _REVIEW_THRESHOLD,
            )
        else:
            fields[field_name] = OcrField(
                value=None,
                confidence=0.0,
                review_required=True,  # unextracted → always review
            )
    return fields


def _extract_line_items(text: str, base_conf: float) -> list[dict[str, OcrField]]:
    """Extract line-item HTS rows from raw OCR text."""
    line_items: list[dict[str, OcrField]] = []
    conf = min(base_conf * 0.85, _TESSERACT_MAX_CONFIDENCE)

    for match in _HTS_BLOCK_RE.finditer(text):
        hts = match.group(1)
        entered_raw = match.group(2)
        duty_rate_raw = match.group(3)

        item: dict[str, OcrField] = {
            "hts_code": OcrField(
                value=hts,
                confidence=min(conf * 1.05, _TESSERACT_MAX_CONFIDENCE),
                review_required=conf < _REVIEW_THRESHOLD,
            ),
        }
        if entered_raw:
            item["entered_value"] = OcrField(
                value=_clean_value(entered_raw),
                confidence=conf,
                review_required=conf < _REVIEW_THRESHOLD,
            )
        if duty_rate_raw:
            item["duty_rate"] = OcrField(
                value=duty_rate_raw.strip(),
                confidence=conf,
                review_required=conf < _REVIEW_THRESHOLD,
            )
        line_items.append(item)

    return line_items


def _compute_tesseract_confidence(data: dict) -> float:
    """
    Compute mean word confidence from ``pytesseract.image_to_data`` output.
    Filters out layout elements (conf == -1) and normalises 0–100 → 0.0–1.0.
    """
    valid_confs = [c for c in data.get("conf", []) if c != -1]
    if not valid_confs:
        return 0.0
    mean_conf = statistics.mean(valid_confs) / 100.0
    return min(mean_conf, _TESSERACT_MAX_CONFIDENCE)


def run_tesseract(file_bytes: bytes, mime_type: str) -> OcrResult:
    """
    Run pytesseract OCR on *file_bytes* and return an OcrResult.

    PDF input is first converted to page images via pdf2image.
    JPEG/PNG input is handled directly.

    Returns overall_confidence < 0.50 when the document is unreadable,
    which causes the caller to return UNRECOGNISED_DOCUMENT.
    """
    import pytesseract  # type: ignore[import]
    from pytesseract import Output  # type: ignore[import]

    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

    # ── Convert file to PIL Images ─────────────────────────────────────────
    images: list[Any] = []
    if mime_type == "application/pdf":
        try:
            from pdf2image import convert_from_bytes  # type: ignore[import]
            images = convert_from_bytes(file_bytes, dpi=200, fmt="png")
        except Exception as exc:
            logger.error("pdf2image conversion failed: %s", exc)
            return OcrResult(
                provider="tesseract",
                overall_confidence=0.0,
                fields={},
                line_items=[],
                raw_text="",
            )
    else:
        # JPEG / PNG — load as PIL Image
        import io
        from PIL import Image  # type: ignore[import]
        images = [Image.open(io.BytesIO(file_bytes))]

    # ── Run Tesseract on all pages ─────────────────────────────────────────
    all_text_parts: list[str] = []
    page_confidences: list[float] = []

    for img in images:
        try:
            data = pytesseract.image_to_data(img, output_type=Output.DICT)
            page_conf = _compute_tesseract_confidence(data)
            page_confidences.append(page_conf)

            page_text = pytesseract.image_to_string(img)
            all_text_parts.append(page_text)
        except Exception as exc:
            logger.warning("Tesseract failed on page: %s", exc)
            page_confidences.append(0.0)

    full_text = "\n".join(all_text_parts)
    overall_confidence = (
        statistics.mean(page_confidences) if page_confidences else 0.0
    )

    logger.info(
        "Tesseract OCR: %d pages, overall confidence=%.3f",
        len(images), overall_confidence,
    )

    if overall_confidence < 0.10:
        # Completely unreadable — return minimal result; caller will reject
        return OcrResult(
            provider="tesseract",
            overall_confidence=overall_confidence,
            fields={},
            line_items=[],
            raw_text=full_text,
        )

    header_fields = _extract_header_fields(full_text, overall_confidence)
    line_items = _extract_line_items(full_text, overall_confidence)

    return OcrResult(
        provider="tesseract",
        overall_confidence=overall_confidence,
        fields=header_fields,
        line_items=line_items,
        raw_text=full_text,
    )
