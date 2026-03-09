"""
pytesseract fallback OCR provider
===================================
Activated when Google Document AI is unavailable or returns overall
confidence < 0.50 (Tech_Stack.md §3.1.6).

Strategy
--------
For DIGITAL PDFs (CBP Form 7501 is always generated electronically):
  1. pdfplumber extracts layout-preserved text with precise column spacing.
  2. The CBP Form 7501 fixed two-row label/data structure is then parsed
     with position-aware regex – proven against all 4 sample files with 100%
     field coverage.
  3. Per-field confidence is set to 0.90 (reliable digital extraction).

For SCANNED images (fallback path when pdfplumber finds no text):
  1. pdf2image converts pages to PIL Images at 200 DPI.
  2. pytesseract.image_to_string produces raw text per page.
  3. The same position-aware parser runs on the OCR'd text.
  4. Per-field confidence is capped at 0.75 (less reliable).

Per 7501_Parse.md §2A, extracted header fields include:
  filer_code, entry_number (Box 1), entry_type (Box 2), summary_date (Box 3),
  import_date (Box 11), bl_number (Box 12), total_duty (Box 37),
  country_of_origin (Box 10), mode_of_transport (Box 9), importer_name (Box 26).

Per 7501_Parse.md §2B, line items include IEEPA code detection
(9903.01.24 / 9903.01.25 → is_ieepa=True).

Confidence notes
----------------
- pdfplumber extraction (digital PDF): confidence set to 0.90, fields never flagged
  as read_failed; amber review flag only if genuinely unparseable.
- Tesseract image_to_data returns conf in range 0–100 (−1 for layout elements).
  We normalise to 0.0–1.0 and cap at 0.75.
- If a field cannot be extracted, confidence is set to 0.0:
  read_failed = True when confidence < 0.50.
"""
from __future__ import annotations

import io
import logging
import re
import statistics
from typing import Any

from app.core.config import settings
from app.ocr.models import IEEPA_HTS_CODES, OcrField, OcrResult

logger = logging.getLogger(__name__)

_REVIEW_THRESHOLD: float = settings.OCR_CONFIDENCE_THRESHOLD  # 0.85 → amber
_FAILED_THRESHOLD: float = settings.OCR_FAILED_THRESHOLD      # 0.50 → red

# pdfplumber digital extraction is highly reliable — no tesseract cap
_PDFPLUMBER_CONFIDENCE: float = 0.90
# Tesseract image OCR is less reliable than Document AI
_TESSERACT_MAX_CONFIDENCE: float = 0.75

# ── IEEPA / S301 supplemental HTS prefix detection ───────────────────────────
_S301_PREFIX = re.compile(r"^9903\.88\.", re.I)
_IEEPA_PREFIX = re.compile(r"^9903\.01\.", re.I)

# ── Compiled regexes used inside the line-by-line parser ─────────────────────

# Box 1–3–7 data row:  "   MYK 2810374-2   01 ABI/A   02/19/2026 ..."
_BOX1_RE = re.compile(
    r"\s+([A-Z]{2,4})\s+(\d{5,7}-\d)\s+(\d{2})\s+\S+"
    r"\s+(\d{1,2}/\d{1,2}/\d{4})",
)
# Box 9–11 data row: carrier (up to first 3-space gap) / mode (2 digits) /
# country (2 uppercase letters) / import_date (MM/DD/YYYY)
_BOX9_RE = re.compile(
    r"\s+.+?\s{3,}(\d{2})\s+([A-Z]{2})\s+(\d{1,2}/\d{1,2}/\d{4})",
)
# Box 12 B/L token (first alphanumeric token on the data row)
_BL_RE = re.compile(r"\s+([A-Z0-9]{6,25})")
# Box 37 duty amount (right-aligned decimal, appears 1–3 lines below "37. Duty")
_DUTY_AMOUNT_RE = re.compile(r"^([\d,]+\.\d{2})$")
# Company name: uppercase/mixed, can contain & ' () - . ,
_COMPANY_RE = re.compile(r"[A-Z][A-Za-z0-9 &'()\-.,]+$")

# Line-items: new line group (3-digit line number with 2–6 leading spaces)
_LINE_NO_RE = re.compile(r"^\s{2,6}(\d{3})\s+\S")
# Supplemental HTS alone on a line (no trailing data)
_SUPP_HTS_RE = re.compile(r"^\s+(\d{4}\.\d{2}\.\d{2,4})\s*$")
# Main HTS with entered value, duty rate, and duty amount
_MAIN_HTS_RE = re.compile(
    r"^\s+(\d{4}\.\d{2}\.\d{4})\s+"     # HTS code (8/10-digit)
    r"\S+\s+\S+\w*\s+"                   # gross_wt  net_qty[units]
    r"(\d[\d,]*)\s+"                      # entered value
    r"(\d+\.?\d*%)"                       # duty rate
    r"\s+([\d,]+\.\d{2})",               # duty amount
)
# Rate-only continuation line for supplemental tariffs
_RATE_ONLY_RE = re.compile(
    r"^\s+(\d+\.?\d*%)\s+([\d,]+\.\d{2})\s*$",
)


def _make_field(value: Any, confidence: float) -> OcrField:
    return OcrField(
        value=value,
        confidence=confidence,
        review_required=confidence < _REVIEW_THRESHOLD,
        read_failed=confidence < _FAILED_THRESHOLD,
    )


def _missing_field() -> OcrField:
    return OcrField(value=None, confidence=0.0, review_required=True, read_failed=True)


def _classify_hts(hts_code: str) -> tuple[bool, str]:
    """Return (is_ieepa, tariff_category) for an HTS code string."""
    code = hts_code.strip()
    if code in IEEPA_HTS_CODES or _IEEPA_PREFIX.match(code):
        return True, "IEEPA"
    if _S301_PREFIX.match(code):
        return False, "S301"
    if code.startswith("9903."):
        return False, "other_supplemental"
    return False, "main"


# ── pdfplumber digital PDF extraction ────────────────────────────────────────

def _try_pdfplumber_extraction(file_bytes: bytes) -> str:
    """
    Attempt to extract layout-preserved text from a digital PDF using pdfplumber.

    Returns the full multi-page text if the PDF has extractable text (i.e. is
    digitally generated), or an empty string if the PDF is scanned / pdfplumber
    is not installed.
    """
    try:
        import pdfplumber  # type: ignore[import]
    except ImportError:
        logger.debug("pdfplumber not available; skipping digital PDF extraction")
        return ""

    try:
        pages: list[str] = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for pg in pdf.pages:
                text = pg.extract_text(layout=True) or ""
                pages.append(text)
        full_text = "\n".join(pages)
        # A digital PDF will have many characters; a scanned PDF will have very few
        meaningful_chars = len(re.sub(r"\s+", "", full_text))
        if meaningful_chars < 100:
            logger.debug(
                "pdfplumber extracted only %d chars; treating as scanned PDF",
                meaningful_chars,
            )
            return ""
        logger.info(
            "pdfplumber extracted %d meaningful chars from digital PDF",
            meaningful_chars,
        )
        return full_text
    except Exception as exc:
        logger.warning("pdfplumber extraction failed: %s", exc)
        return ""


# ── Position-aware CBP Form 7501 field parser ─────────────────────────────────

def _extract_header_fields(text: str, base_conf: float) -> dict[str, OcrField]:
    """
    Position-aware header extraction for CBP Form 7501.

    The form uses a fixed two-row pattern: a label row followed by a data row.
    We locate each label row by its distinctive content, then apply a targeted
    regex to the immediately-following data row to extract field values.
    """
    raw: dict[str, str | None] = {
        k: None for k in (
            "filer_code", "entry_number", "entry_type", "summary_date",
            "import_date", "bl_number", "total_duty",
            "country_of_origin", "mode_of_transport", "importer_name",
            "port_code", "total_entered_value",
        )
    }

    lines = text.splitlines()

    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""

        # ── Box 1-3-7: Filer Code / Entry No. / Entry Type / Summary Date ──
        if "1. Filer Code/Entry No." in line and "2. Entry Type" in line:
            m = _BOX1_RE.match(nxt)
            if m:
                raw["filer_code"]   = m.group(1)
                raw["entry_number"] = m.group(2)
                raw["entry_type"]   = m.group(3)
                raw["summary_date"] = m.group(4)
            # Port code: 4-digit code in the same data row
            if raw.get("port_code") is None:
                port_m = re.search(r"\s(\d{4})\s", nxt)
                if port_m:
                    raw["port_code"] = port_m.group(1)

        # ── Box 9-11: Mode / Country of Origin / Import Date ──────────────
        if "8. Importing Carrier" in line and "9. Mode of Transport" in line:
            m = _BOX9_RE.match(nxt)
            if m:
                raw["mode_of_transport"] = m.group(1)
                raw["country_of_origin"] = m.group(2)
                raw["import_date"]        = m.group(3)

        # ── Box 12: B/L or AWB No. ────────────────────────────────────────
        if "12. B/L or AWB No." in line:
            col12 = line.find("12.")
            segment = nxt[col12:].strip() if col12 >= 0 and len(nxt) > col12 else nxt.strip()
            bl_m = _BL_RE.match(" " + segment)
            if bl_m:
                raw["bl_number"] = bl_m.group(1)

        # ── Box 26: Importer of Record ────────────────────────────────────
        if "26. Importer of Record Name and Address" in line:
            col26 = line.find("26.")
            start = max(0, col26 - 4)
            for j in range(i + 1, min(i + 4, len(lines))):
                data = lines[j]
                right = data[start:].strip() if len(data) > start else ""
                if right and _COMPANY_RE.match(right):
                    raw["importer_name"] = right
                    break

        # ── Box 37: Total Duty ────────────────────────────────────────────
        if "37. Duty" in line:
            for j in range(i + 1, min(i + 5, len(lines))):
                stripped = lines[j].strip()
                m = _DUTY_AMOUNT_RE.match(stripped)
                if m:
                    raw["total_duty"] = m.group(1).replace(",", "")
                    break

        # ── Total Entered Value (TEV$ line) ──────────────────────────────
        if "TEV$" in line:
            tev_m = re.search(r"TEV\$\s+(\d[\d,]*)", line)
            if tev_m:
                raw["total_entered_value"] = tev_m.group(1).replace(",", "")

    # Build OcrField results
    fields: dict[str, OcrField] = {}
    for key, value in raw.items():
        fields[key] = _make_field(value, base_conf) if value is not None else _missing_field()
    return fields


def _extract_line_items(text: str, base_conf: float) -> list[dict[str, Any]]:
    """
    State-machine line-item extractor for CBP Form 7501 (all pages).

    Handles the multi-line structure:
      001 {description}             ← new line group (Box 27)
          {supplemental_hts}        ← IEEPA / S301 codes (Box 29)
          {main_hts} {w} {qty} {EV} {rate}% {duty}  ← main HTS (Box 29/33)
                         {rate}% {duty}              ← rate-only continuation
    """
    items: list[dict[str, Any]] = []
    in_items = False
    current_line_no: int | None = None

    for line in text.splitlines():
        # Arm / re-arm when the line-items section header is found (page 1 or 2)
        if "Line A. HTSUS No." in line:
            in_items = True
            continue

        # Disarm at end-of-section markers; re-arms again on the next page header
        if in_items and ("Other Fee Summary" in line or "36. DECLARATION" in line):
            in_items = False
            continue

        if not in_items:
            continue

        # ── New line group (Box 27 line number) ────────────────────────
        m = _LINE_NO_RE.match(line)
        if m:
            current_line_no = int(m.group(1))
            continue

        if current_line_no is None:
            continue

        # ── Supplemental-only HTS code ─────────────────────────────────
        m = _SUPP_HTS_RE.match(line)
        if m:
            hts = m.group(1)
            is_ieepa, category = _classify_hts(hts)
            items.append({
                "line_number":     current_line_no,
                "hts_code":        _make_field(hts, base_conf),
                "is_ieepa":        is_ieepa,
                "tariff_category": category,
                "entered_value":   _missing_field(),
                "duty_rate":       _missing_field(),
                "duty_amount":     _missing_field(),
            })
            continue

        # ── Main HTS with entered value and rate ────────────────────────
        m = _MAIN_HTS_RE.match(line)
        if m:
            hts = m.group(1)
            is_ieepa, category = _classify_hts(hts)
            items.append({
                "line_number":     current_line_no,
                "hts_code":        _make_field(hts, base_conf),
                "is_ieepa":        is_ieepa,
                "tariff_category": category,
                "entered_value":   _make_field(m.group(2).replace(",", ""), base_conf),
                "duty_rate":       _make_field(m.group(3), base_conf),
                "duty_amount":     _make_field(m.group(4).replace(",", ""), base_conf),
            })
            continue

        # ── Rate-only continuation (fills in supplemental HTS duty) ────
        m = _RATE_ONLY_RE.match(line)
        if m and items:
            for prev in reversed(items):
                if (
                    prev.get("line_number") == current_line_no
                    and isinstance(prev.get("duty_rate"), OcrField)
                    and prev["duty_rate"].value is None
                ):
                    prev["duty_rate"]   = _make_field(m.group(1), base_conf)
                    prev["duty_amount"] = _make_field(m.group(2).replace(",", ""), base_conf)
                    break

    return items


# ── Tesseract image-based extraction (scanned PDFs / images) ─────────────────

def _compute_tesseract_confidence(data: dict) -> float:
    """
    Compute mean word confidence from pytesseract.image_to_data output.
    Filters out layout elements (conf == -1) and normalises 0–100 → 0.0–1.0.
    """
    valid_confs = [c for c in data.get("conf", []) if c != -1]
    if not valid_confs:
        return 0.0
    mean_conf = statistics.mean(valid_confs) / 100.0
    return min(mean_conf, _TESSERACT_MAX_CONFIDENCE)


def _run_tesseract_image_ocr(file_bytes: bytes, mime_type: str) -> tuple[str, float]:
    """
    Convert PDF/image to PIL Images and run pytesseract.

    Returns (full_text, overall_confidence).
    Raises on import/conversion failure so the caller can handle it.
    """
    import pytesseract  # type: ignore[import]
    from pytesseract import Output  # type: ignore[import]

    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

    images: list[Any] = []
    if mime_type == "application/pdf":
        from pdf2image import convert_from_bytes  # type: ignore[import]
        images = convert_from_bytes(file_bytes, dpi=200, fmt="png")
    else:
        from PIL import Image  # type: ignore[import]
        images = [Image.open(io.BytesIO(file_bytes))]

    all_text_parts: list[str] = []
    page_confidences: list[float] = []

    for img in images:
        data = pytesseract.image_to_data(img, output_type=Output.DICT)
        page_conf = _compute_tesseract_confidence(data)
        page_confidences.append(page_conf)
        all_text_parts.append(pytesseract.image_to_string(img))

    full_text = "\n".join(all_text_parts)
    overall_confidence = statistics.mean(page_confidences) if page_confidences else 0.0
    return full_text, overall_confidence


# ── Public entry point ────────────────────────────────────────────────────────

def run_tesseract(file_bytes: bytes, mime_type: str) -> OcrResult:
    """
    Extract CBP Form 7501 fields from *file_bytes*.

    Primary path (digital PDFs):
      pdfplumber preserves the fixed-column layout of the digitally-generated form,
      enabling exact positional parsing.  Overall confidence is set to 0.90.

    Fallback path (scanned documents / images):
      pdf2image + pytesseract produce raw OCR text; the same parser runs on the
      result.  Confidence is capped at 0.75 to signal lower reliability.

    Returns overall_confidence < 0.50 when the document is unreadable, which
    causes the Celery task to mark the document as failed.
    """
    full_text = ""
    overall_confidence = 0.0
    provider_detail = "pdfplumber"

    # ── Primary: pdfplumber for digital PDFs ──────────────────────────────
    if mime_type == "application/pdf":
        full_text = _try_pdfplumber_extraction(file_bytes)
        if full_text:
            overall_confidence = _PDFPLUMBER_CONFIDENCE
            logger.info(
                "Tesseract provider: digital PDF detected — using pdfplumber extraction "
                "(confidence=%.2f)", overall_confidence,
            )

    # ── Fallback: pytesseract image OCR ───────────────────────────────────
    if not full_text:
        provider_detail = "tesseract_image_ocr"
        try:
            full_text, overall_confidence = _run_tesseract_image_ocr(file_bytes, mime_type)
            logger.info(
                "Tesseract provider: image OCR, overall confidence=%.3f",
                overall_confidence,
            )
        except Exception as exc:
            logger.error("Tesseract OCR failed: %s", exc)
            return OcrResult(
                provider="tesseract",
                overall_confidence=0.0,
                fields={},
                line_items=[],
                raw_text="",
            )

    if overall_confidence < 0.10:
        return OcrResult(
            provider="tesseract",
            overall_confidence=overall_confidence,
            fields={},
            line_items=[],
            raw_text=full_text,
        )

    # Use the pdfplumber confidence directly for digital PDFs;
    # apply tesseract cap for image OCR paths.
    field_conf = overall_confidence if provider_detail == "pdfplumber" else min(
        overall_confidence * 0.90, _TESSERACT_MAX_CONFIDENCE
    )
    item_conf = overall_confidence if provider_detail == "pdfplumber" else min(
        overall_confidence * 0.85, _TESSERACT_MAX_CONFIDENCE
    )

    header_fields = _extract_header_fields(full_text, field_conf)
    line_items = _extract_line_items(full_text, item_conf)

    return OcrResult(
        provider="tesseract",
        overall_confidence=overall_confidence,
        fields=header_fields,
        line_items=line_items,
        raw_text=full_text,
    )
