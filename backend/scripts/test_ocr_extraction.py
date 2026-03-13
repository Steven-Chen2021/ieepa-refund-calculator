"""
Standalone OCR extraction test for CBP Form 7501 samples.
Uses pdfplumber to extract text then applies position-aware parsing
matching the actual CBP Form 7501 fixed-column layout.

Run from project root:
    python backend/scripts/test_ocr_extraction.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

try:
    import pdfplumber
except ImportError:
    sys.exit("pip install pdfplumber first")

# ── Constants ─────────────────────────────────────────────────────────────────
IEEPA_HTS_CODES: frozenset[str] = frozenset({"9903.01.24", "9903.01.25"})
REQUIRED_HEADER_FIELDS = [
    "filer_code", "entry_number", "entry_type", "summary_date",
    "import_date", "bl_number", "total_duty",
    "country_of_origin", "mode_of_transport", "importer_name",
]


def classify_hts(code: str) -> str:
    if code in IEEPA_HTS_CODES or code.startswith("9903.01."):
        return "IEEPA ★ 退稅目標"
    if code.startswith("9903.88."):
        return "Section 301"
    if code.startswith("9903."):
        return "Supplemental"
    return "Main"


# ── PDF text extraction ───────────────────────────────────────────────────────

def extract_pages(pdf_path: Path) -> list[str]:
    with pdfplumber.open(str(pdf_path)) as pdf:
        return [pg.extract_text(layout=True) or "" for pg in pdf.pages]


# ── Header field extraction (column-aware) ───────────────────────────────────

def parse_header(lines: list[str]) -> dict[str, str | None]:
    result: dict[str, str | None] = {f: None for f in REQUIRED_HEADER_FIELDS}

    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""

        # ── Box 1-3-7: Filer Code / Entry No. / Entry Type / Summary Date ──
        if "1. Filer Code/Entry No." in line and "2. Entry Type" in line:
            # Data row: "      MYK 2810374-2   01 ABI/A    02/19/2026 ..."
            m = re.match(
                r"\s+([A-Z]{2,4})\s+(\d{5,7}-\d)\s+(\d{2})\s+\S+"
                r"\s+(\d{1,2}/\d{1,2}/\d{4})",
                nxt,
            )
            if m:
                result["filer_code"]   = m.group(1)
                result["entry_number"] = m.group(2)
                result["entry_type"]   = m.group(3)
                result["summary_date"] = m.group(4)

        # ── Box 9-11: Mode / Country of Origin / Import Date ──────────────
        if "8. Importing Carrier" in line and "9. Mode of Transport" in line:
            # Regex approach: carrier (up to first 3-space gap) / mode (2 digits) /
            # country (2 uppercase letters) / import_date (MM/DD/YYYY)
            m = re.match(
                r"\s+.+?\s{3,}(\d{2})\s+([A-Z]{2})\s+(\d{1,2}/\d{1,2}/\d{4})",
                nxt,
            )
            if m:
                result["mode_of_transport"] = m.group(1)
                result["country_of_origin"] = m.group(2)
                result["import_date"]        = m.group(3)

        # ── Box 12: B/L or AWB No. ────────────────────────────────────────
        if "12. B/L or AWB No." in line:
            # Get column position of Box 12 label and extract from data line
            col12 = line.find("12.")
            if col12 >= 0 and len(nxt) > col12:
                # First whitespace-delimited token from col12
                segment = nxt[col12:].strip()
                bl_match = re.match(r"([A-Z0-9]{6,25})", segment)
                if bl_match:
                    result["bl_number"] = bl_match.group(1)

        # ── Box 26: Importer of Record ────────────────────────────────────
        if "26. Importer of Record Name and Address" in line:
            col26 = line.find("26.")
            # Add a small backward offset: the data can start 2-4 chars before the label
            start = max(0, col26 - 4)
            for j in range(i + 1, min(i + 4, len(lines))):
                data = lines[j]
                right = data[start:].strip() if len(data) > start else ""
                # Company name: all-caps/mixed with common chars (no digits-only, no address numbers at start)
                if right and re.match(r"[A-Z][A-Za-z0-9 &'()\-.,]+$", right):
                    result["importer_name"] = right
                    break

        # ── Box 37: Total Duty ────────────────────────────────────────────
        if "37. Duty" in line:
            # Amount appears 1-3 lines below, right-aligned: just a number like "17625.60"
            for j in range(i + 1, min(i + 5, len(lines))):
                stripped = lines[j].strip()
                m = re.match(r"^([\d,]+\.\d{2})$", stripped)
                if m:
                    result["total_duty"] = m.group(1).replace(",", "")
                    break

    return result


# ── Line item extraction ─────────────────────────────────────────────────────

def parse_line_items(lines: list[str]) -> list[dict[str, Any]]:
    """
    State-machine parser for Box 27/29/33 line items.
    
    Handles the multi-line structure:
      001 {description}          ← new line group
          {supplemental_hts}     ← IEEPA / S301 codes
          {main_hts}  {wt} {qty} {entered_val} {rate}%  {duty_amt}
    """
    items: list[dict[str, Any]] = []
    in_items = False
    current_line_no: int | None = None
    pending_supplementals: list[str] = []

    # Match exactly a 3-digit line number starting a new group
    LINE_NO_RE = re.compile(r"^\s{2,6}(\d{3})\s+\S")
    # Supplemental-only HTS (just the code, nothing after it)
    SUPP_HTS_RE = re.compile(r"^\s+(\d{4}\.\d{2}\.\d{2,4})\s*$")
    # Main HTS with entered value and rate
    MAIN_HTS_RE = re.compile(
        r"^\s+(\d{4}\.\d{2}\.\d{4})\s+"    # HTS code (8/10-digit)
        r"\S+\s+\S+\w*\s+"                  # gross_wt  net_qty[units]
        r"(\d[\d,]*)\s+"                     # entered value
        r"(\d+\.?\d*%)"                      # duty rate
        r"\s+([\d,]+\.\d{2})"               # duty amount
    )
    # Rate-only line (continuation for supplemental):  "          10%             3916.80"
    RATE_ONLY_RE = re.compile(
        r"^\s+(\d+\.?\d*%)\s+([\d,]+\.\d{2})\s*$"
    )

    for line in lines:
        # Detect start of line-items section
        if "Line A. HTSUS No." in line:
            in_items = True
            continue
        if not in_items:
            continue
        # End of line-items section — reset so we can re-arm on page 2
        if "Other Fee Summary" in line or "36. DECLARATION" in line:
            in_items = False
            continue

        # ── New line number group ──────────────────────────────────────
        m = LINE_NO_RE.match(line)
        if m:
            current_line_no = int(m.group(1))
            pending_supplementals = []
            continue

        if current_line_no is None:
            continue

        # ── Supplemental HTS code (alone on line) ─────────────────────
        m = SUPP_HTS_RE.match(line)
        if m:
            hts = m.group(1)
            pending_supplementals.append(hts)
            items.append({
                "line_number":    current_line_no,
                "hts_code":       hts,
                "category":       classify_hts(hts),
                "entered_value":  "",
                "duty_rate":      "",
                "duty_amount":    "",
            })
            continue

        # ── Main HTS with data ─────────────────────────────────────────
        m = MAIN_HTS_RE.match(line)
        if m:
            hts = m.group(1)
            items.append({
                "line_number":    current_line_no,
                "hts_code":       hts,
                "category":       classify_hts(hts),
                "entered_value":  m.group(2).replace(",", ""),
                "duty_rate":      m.group(3),
                "duty_amount":    m.group(4).replace(",", ""),
            })
            continue

        # ── Rate-only line → fill into last pending supplemental ──────
        m = RATE_ONLY_RE.match(line)
        if m and items:
            # Find the most recent supplemental without a rate
            for prev in reversed(items):
                if prev.get("line_number") == current_line_no and not prev.get("duty_rate"):
                    prev["duty_rate"]   = m.group(1)
                    prev["duty_amount"] = m.group(2).replace(",", "")
                    break

    return items


# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def report(pdf_path: Path) -> dict:
    print(f"\n{'='*72}")
    print(f"{BOLD}{CYAN}FILE: {pdf_path.name}{RESET}")
    print("=" * 72)

    pages = extract_pages(pdf_path)
    all_lines: list[str] = []
    for page_text in pages:
        all_lines.extend(page_text.splitlines())

    header = parse_header(all_lines)
    line_items = parse_line_items(all_lines)
    ieepa_items = [li for li in line_items if "IEEPA" in li["category"]]

    # ── Header fields ──────────────────────────────────────────────────────
    print(f"\n{BOLD}── Header Fields (7501_Parse.md §2A) ──{RESET}")
    found = 0
    for field in REQUIRED_HEADER_FIELDS:
        val = header.get(field)
        if val:
            print(f"  {GREEN}✓{RESET}  {field:<22} = {val}")
            found += 1
        else:
            print(f"  {RED}✗{RESET}  {field:<22} = (not found)")

    pct_h = round(found / len(REQUIRED_HEADER_FIELDS) * 100)
    colour = GREEN if pct_h == 100 else YELLOW if pct_h >= 70 else RED
    print(f"\n  {colour}Header: {found}/{len(REQUIRED_HEADER_FIELDS)} ({pct_h}%){RESET}")

    # ── Line items ─────────────────────────────────────────────────────────
    print(f"\n{BOLD}── Line Items (Box 27 / 29 / 33) ──{RESET}")
    if line_items:
        for li in line_items:
            cat_col = YELLOW if "IEEPA" in li["category"] else (CYAN if "301" in li["category"] or "Supp" in li["category"] else RESET)
            ev   = f"EV:{li['entered_value']}" if li.get("entered_value") else ""
            rate = li.get("duty_rate", "")
            amt  = f"${li['duty_amount']}" if li.get("duty_amount") else ""
            print(
                f"  {cat_col}[{li['category']:<22}]{RESET}"
                f"  Line {li['line_number']:03d}"
                f"  HTS: {li['hts_code']:<16}"
                f"  {rate:<8}  {ev:<14}  {amt}"
            )
    else:
        print(f"  {RED}✗  No line items found{RESET}")

    print(f"\n  Line items total  : {len(line_items)}")
    if ieepa_items:
        codes = ", ".join(sorted({li['hts_code'] for li in ieepa_items}))
        print(f"  {YELLOW}★ IEEPA targets    : {len(ieepa_items)} ({codes}){RESET}")
        total_ieepa = sum(float(li['duty_amount']) for li in ieepa_items if li.get('duty_amount'))
        if total_ieepa:
            print(f"  {YELLOW}★ Est. IEEPA refund: ${total_ieepa:,.2f}{RESET}")
    else:
        print(f"  {RED}★ IEEPA targets    : 0{RESET}")

    return {
        "file": pdf_path.name,
        "header_found": found,
        "header_total": len(REQUIRED_HEADER_FIELDS),
        "line_items": len(line_items),
        "ieepa_items": len(ieepa_items),
        "ieepa_refund": sum(float(li['duty_amount']) for li in ieepa_items if li.get('duty_amount')),
    }


def main() -> None:
    samples_dir = Path(__file__).parent.parent.parent / "7501Samples"
    pdfs_raw = list(samples_dir.glob("*.pdf")) + list(samples_dir.glob("*.PDF"))
    # Deduplicate by stem (case-insensitive)
    seen: set[str] = set()
    pdfs: list[Path] = []
    for p in sorted(pdfs_raw, key=lambda x: x.name.lower()):
        key = p.stem.lower()
        if key not in seen:
            seen.add(key)
            pdfs.append(p)

    if not pdfs:
        sys.exit(f"No PDF files found in {samples_dir}")

    print(f"\n{BOLD}IEEPA Refund Calculator — OCR Field Extraction Test{RESET}")
    print(f"Samples dir : {samples_dir}")
    print(f"PDFs found  : {len(pdfs)}")

    all_results = []
    for pdf in pdfs:
        all_results.append(report(pdf))

    # ── Overall summary ────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"{BOLD}OVERALL SUMMARY{RESET}")
    print("=" * 72)
    total_h   = sum(r["header_found"] for r in all_results)
    max_h     = sum(r["header_total"] for r in all_results)
    total_l   = sum(r["line_items"]   for r in all_results)
    total_i   = sum(r["ieepa_items"]  for r in all_results)
    total_ref = sum(r["ieepa_refund"] for r in all_results)

    for r in all_results:
        ok = r["header_found"] == r["header_total"]
        col = GREEN if ok else YELLOW
        print(
            f"  {col}{r['file']:<50}{RESET}"
            f"  H:{r['header_found']}/{r['header_total']}"
            f"  Lines:{r['line_items']}"
            f"  IEEPA:{r['ieepa_items']}"
            + (f"  Refund:${r['ieepa_refund']:,.2f}" if r["ieepa_refund"] else "")
        )

    pct = round(total_h / max_h * 100) if max_h else 0
    col = GREEN if pct >= 90 else YELLOW if pct >= 70 else RED
    print(f"\n  {col}Header coverage : {total_h}/{max_h} ({pct}%){RESET}")
    print(f"  Line items      : {total_l}")
    print(f"  IEEPA targets   : {total_i}")
    if total_ref:
        print(f"  {YELLOW}★ Total est. IEEPA refund: ${total_ref:,.2f}{RESET}")


if __name__ == "__main__":
    main()
