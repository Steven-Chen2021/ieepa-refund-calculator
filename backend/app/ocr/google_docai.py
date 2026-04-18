"""
Google Document AI — Form Parser provider
==========================================
Primary OCR engine for CBP Form 7501 processing.

Fallback trigger (BR-010 / Tech_Stack.md §3.1.6):
  - Google Cloud API raises an exception, OR
  - overall_confidence < 0.50

Field mapping
-------------
The Form Parser returns FormField objects whose ``field_name`` text is matched
against the CBP Form 7501 box labels using case-insensitive regex.
Line items are extracted from tables on the document pages.

Per 7501_Parse.md §2, the following header fields are targeted:
  Box 1  → filer_code + entry_number
  Box 2  → entry_type
  Box 3  → summary_date
  Box 11 → import_date   (formatted YYYY-MM-DD)
  Box 12 → bl_number     (B/L or AWB No.)
  Box 37 → total_duty    ($ removed)

Line items (Box 27/29/33) are grouped by line_number. IEEPA supplemental
HTS codes (9903.01.24 / 9903.01.25) are flagged with is_ieepa=True.

Confidence
----------
Per-field confidence comes directly from Document AI's
``field_value.layout.confidence`` (0.0 – 1.0).
overall_confidence = mean of all field-value confidences.
"""
from __future__ import annotations

import logging
import re
import statistics
from typing import Any

from app.core.config import settings
from app.ocr.models import IEEPA_HTS_CODES, OcrField, OcrResult

logger = logging.getLogger(__name__)

# ── Confidence thresholds (7501_Parse.md §3 / BR-010) ────────────────────────
_REVIEW_THRESHOLD: float = settings.OCR_CONFIDENCE_THRESHOLD  # 0.80 → amber (BR-010)
_FAILED_THRESHOLD: float = settings.OCR_FAILED_THRESHOLD      # 0.50 → red

# ── IEEPA / S301 supplemental tariff prefix detection ────────────────────────
_S301_PREFIX = re.compile(r"^9903\.88\.", re.I)
_IEEPA_PREFIX = re.compile(r"^9903\.01\.", re.I)

# ── CBP Form 7501 field label → internal field name ──────────────────────────
# Each pattern is tried (case-insensitive) against the key text returned by the
# Form Parser.  First match wins.
_HEADER_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Box 1: "1. Filer Code/Entry No." — split into filer_code and entry_number
    (re.compile(r"filer\s*code", re.I),                       "filer_code"),
    (re.compile(r"entry\s*(?:no\.?|number|\d\.)", re.I),      "entry_number"),
    # Box 2
    (re.compile(r"entry\s*type", re.I),                        "entry_type"),
    # Box 3
    (re.compile(r"entry\s*summary\s*date|summary\s*date", re.I), "summary_date"),
    # Box 11: Import Date
    (re.compile(r"(?:11\.?\s*)?import\s*date", re.I),          "import_date"),
    # Box 12: B/L or AWB No.
    (re.compile(r"(?:12\.?\s*)?b/?l\b|awb\s*no", re.I),       "bl_number"),
    # Box 37: Duty total
    (re.compile(r"(?:37\.?\s*)?(?:total\s*)?duty(?!\s*rate)", re.I), "total_duty"),
    # Other header fields
    (re.compile(r"port\s*(?:of\s*entry|code)", re.I),          "port_code"),
    (re.compile(r"importer\s*(?:of\s*record|name)", re.I),     "importer_name"),
    (re.compile(r"country\s*of\s*origin", re.I),               "country_of_origin"),
    (re.compile(r"mode\s*of\s*trans(?:port)?", re.I),          "mode_of_transport"),
    (re.compile(r"total\s*entered\s*value|entered\s*value\s*total", re.I), "total_entered_value"),
    (re.compile(r"total\s*(?:fees|amount\s*due)", re.I),       "total_fees"),
]

_LINE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"line\s*no\.?|item\s*no\.?", re.I),          "line_number"),
    (re.compile(r"hts\s*(?:us\s*)?(?:number|code)|harmonized\s*tariff", re.I), "hts_code"),
    (re.compile(r"entered\s*value|adval", re.I),               "entered_value"),
    (re.compile(r"duty\s*rate|rate\s*of\s*duty", re.I),        "duty_rate"),
    (re.compile(r"duty\s*amount|calculated\s*duty", re.I),     "duty_amount"),
    (re.compile(r"country\s*of\s*origin", re.I),               "country_of_origin"),
    (re.compile(r"description", re.I),                         "description"),
]


def _map_header_key(key_text: str) -> str | None:
    """Return the internal field name for a Form Parser key label, or None."""
    cleaned = key_text.strip()
    for pattern, name in _HEADER_PATTERNS:
        if pattern.search(cleaned):
            return name
    return None


def _map_line_key(key_text: str) -> str | None:
    """Return the internal field name for a line-item table column header."""
    cleaned = key_text.strip()
    for pattern, name in _LINE_PATTERNS:
        if pattern.search(cleaned):
            return name
    return None


def _segment_text(text_anchor: Any, full_text: str) -> str:
    """Extract the text referenced by a Document AI TextAnchor."""
    result = ""
    for seg in text_anchor.text_segments:
        start = int(seg.start_index) if seg.start_index else 0
        end = int(seg.end_index)
        result += full_text[start:end]
    return result.strip()


def _make_field(value: Any, confidence: float) -> OcrField:
    return OcrField(
        value=value,
        confidence=confidence,
        review_required=confidence < _REVIEW_THRESHOLD,
        read_failed=confidence < _FAILED_THRESHOLD,
    )


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


def _parse_document(document: Any) -> tuple[dict[str, OcrField], list[dict[str, Any]]]:
    """
    Parse a Document AI Document proto into header fields and line items.

    Line items are grouped by line_number (Box 27 trigger per 7501_Parse.md §2B).
    Each row carries is_ieepa and tariff_category metadata so the UI can
    highlight IEEPA 退稅目標 rows.

    Returns
    -------
    header_fields : dict[str, OcrField]
    line_items    : list[dict[str, Any]]
    """
    full_text: str = document.text
    header_fields: dict[str, OcrField] = {}
    line_items: list[dict[str, Any]] = []

    for page in document.pages:
        # ── Header form fields ────────────────────────────────────────────
        for ff in page.form_fields:
            key_text = _segment_text(ff.field_name.text_anchor, full_text)
            val_text = _segment_text(ff.field_value.text_anchor, full_text)
            confidence = float(ff.field_value.layout.confidence or 0.0)

            field_name = _map_header_key(key_text)
            if field_name and field_name not in header_fields:
                # Strip leading "$" from monetary fields (Box 37 total_duty)
                if field_name == "total_duty":
                    val_text = val_text.lstrip("$").strip().replace(",", "")
                header_fields[field_name] = _make_field(val_text, confidence)

        # ── Line-item tables ──────────────────────────────────────────────
        for table in page.tables:
            if not table.body_rows:
                continue

            # Build column index → internal field name from header row
            col_map: dict[int, str] = {}
            for header_row in table.header_rows:
                for col_idx, cell in enumerate(header_row.cells):
                    cell_text = _segment_text(cell.layout.text_anchor, full_text)
                    fname = _map_line_key(cell_text)
                    if fname:
                        col_map[col_idx] = fname

            if not col_map:
                continue  # table not recognised as a line-item table

            for row in table.body_rows:
                item: dict[str, Any] = {}
                for col_idx, cell in enumerate(row.cells):
                    fname = col_map.get(col_idx)
                    if fname:
                        cell_text = _segment_text(cell.layout.text_anchor, full_text)
                        conf = float(cell.layout.confidence or 0.0)
                        item[fname] = _make_field(cell_text, conf)

                if not item:
                    continue

                # Annotate with IEEPA metadata (7501_Parse.md §2B)
                hts_field = item.get("hts_code")
                hts_value = hts_field.value if isinstance(hts_field, OcrField) else ""
                is_ieepa, tariff_category = _classify_hts(str(hts_value or ""))
                item["is_ieepa"] = is_ieepa
                item["tariff_category"] = tariff_category

                line_items.append(item)

    line_items = _post_process_table_items(line_items)
    return header_fields, line_items


def _post_process_table_items(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Fix HTS code → duty rate matching after DocAI table extraction.

    CBP Form 7501 Box 33 omits 0% duty rates, making positional matching of
    table rows to rates unreliable. This function:

    1. Inherits blank ``line_number`` cells from the previous non-blank row
       (continuation rows in DocAI table parsing have no line_number cell).
    2. Groups rows by line_number.  Within each group the row with a non-None
       ``entered_value`` is the "main HTS" row; all other rows are supplementals.
    3. Propagates the main HTS ``entered_value`` to every supplemental row so
       that the calculation engine can derive duty for each code.
    4. Collects all PDF-printed rate/duty pairs into ``pdf_rate_duty_pairs`` on
       the main HTS row (for cross-validation) and clears ``duty_rate`` /
       ``duty_amount`` on every row.  The DB enrichment step will fill correct
       rates from the ``tariff_rates`` table.
    """
    # ── Step 1: inherit line_number for continuation rows ──────────────────
    last_line_no: str | None = None
    for item in items:
        ln_field = item.get("line_number")
        ln_val = ln_field.value if isinstance(ln_field, OcrField) else None
        if ln_val:
            last_line_no = str(ln_val).strip()
            item["_line_no_key"] = last_line_no
        elif last_line_no is not None:
            item["_line_no_key"] = last_line_no
        else:
            item["_line_no_key"] = None

    # ── Step 2: group by line_number key ───────────────────────────────────
    from collections import OrderedDict
    groups: OrderedDict[str | None, list[dict[str, Any]]] = OrderedDict()
    for item in items:
        key = item.get("_line_no_key")
        groups.setdefault(key, []).append(item)

    # ── Steps 3 & 4: propagate entered_value, collect pdf_pairs, clear rates ─
    result: list[dict[str, Any]] = []
    _missing = _make_field(None, 0.0)

    for _key, group in groups.items():
        # Identify main HTS row: has a non-None entered_value
        main_item: dict[str, Any] | None = None
        for row in group:
            ev = row.get("entered_value")
            if isinstance(ev, OcrField) and ev.value not in (None, ""):
                main_item = row
                break

        # Collect PDF-printed rate/duty pairs from all rows in this group
        pdf_pairs: list[dict[str, str]] = []
        for row in group:
            dr = row.get("duty_rate")
            da = row.get("duty_amount")
            dr_val = dr.value if isinstance(dr, OcrField) else None
            da_val = da.value if isinstance(da, OcrField) else None
            if dr_val and str(dr_val).strip():
                pair: dict[str, str] = {"rate_pct": str(dr_val).strip()}
                if da_val and str(da_val).strip():
                    pair["duty_amount"] = str(da_val).strip().replace(",", "")
                pdf_pairs.append(pair)
            # Clear rate/duty on every row — enrichment fills these from DB
            row["duty_rate"] = _missing
            row["duty_amount"] = _missing

        # Propagate entered_value to supplementals
        if main_item is not None:
            ev_field = main_item["entered_value"]
            for row in group:
                if row is not main_item:
                    row["entered_value"] = ev_field
            if pdf_pairs:
                main_item["pdf_rate_duty_pairs"] = pdf_pairs

        # Remove temporary helper key and emit rows
        for row in group:
            row.pop("_line_no_key", None)
            result.append(row)

    return result


async def run_google_docai(
    file_bytes: bytes,
    mime_type: str,
) -> OcrResult:
    """
    Process *file_bytes* with Google Document AI Form Parser.

    Returns an OcrResult with overall_confidence computed as the mean of all
    extracted field confidences.  Caller should check overall_confidence < 0.50
    and fall back to pytesseract if necessary.

    Raises
    ------
    Exception
        Any exception from the Document AI client (network error, auth failure,
        quota exceeded, etc.).  The caller catches this and invokes fallback.
    """
    # Lazy import: do not fail at module load if google-cloud-documentai is
    # missing in dev environments without GCP credentials.
    from google.cloud import documentai_v1 as documentai  # type: ignore[import]

    processor_name = (
        f"projects/{settings.GOOGLE_DOC_AI_PROJECT_ID}"
        f"/locations/{settings.GOOGLE_DOC_AI_LOCATION}"
        f"/processors/{settings.GOOGLE_DOC_AI_PROCESSOR_ID}"
    )

    client = documentai.DocumentProcessorServiceClient()
    request = documentai.ProcessRequest(
        name=processor_name,
        raw_document=documentai.RawDocument(
            content=file_bytes,
            mime_type=mime_type,
        ),
    )

    logger.info("Calling Google Document AI processor: %s", processor_name)
    response = client.process_document(request=request)
    document = response.document

    header_fields, line_items = _parse_document(document)

    # Compute overall confidence as mean of all extracted field confidences
    all_confidences: list[float] = [f.confidence for f in header_fields.values()]
    for item in line_items:
        all_confidences.extend(
            v.confidence for v in item.values() if isinstance(v, OcrField)
        )

    overall_confidence = statistics.mean(all_confidences) if all_confidences else 0.0

    logger.info(
        "Google Document AI: %d header fields, %d line items, confidence=%.3f",
        len(header_fields), len(line_items), overall_confidence,
    )

    return OcrResult(
        provider="google_document_ai",
        overall_confidence=overall_confidence,
        extraction_method="ocr",
        fields=header_fields,
        line_items=line_items,
        raw_text=document.text,
    )
