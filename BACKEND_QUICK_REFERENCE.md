# Quick Reference: Backend Data Flow

## 1️⃣ PATCH /api/v1/documents/{job_id}/fields
- **Location:** `documents.py` lines 306-360
- **What it does:** Saves user corrections to `Document.corrections` JSONB
- **Database write:** Line 334-339 (SQLAlchemy update + commit)
- **Key code:** 
  ```
  existing_corrections.update(body)
  await db.execute(update(Document).where(...).values(corrections=existing_corrections))
  await db.commit()
  ```

---

## 2️⃣ POST /api/v1/documents/{job_id}/calculate
- **Location:** `documents.py` lines 525-660
- **Flow:**
  1. Call `parse_entry_input(doc)` → line 570
  2. This calls `merge_doc_fields(extracted, corrections)` → line 455
  3. `merge_doc_fields()` blends data: corrections OVERRIDE extracted → line 427
  4. Run `calculate_entry(inputs)` with merged data → line 596
  5. Persist results to `Calculation` record → lines 641-654

---

## 3️⃣ Calculation Engine: calculate_entry()
- **Location:** `calculator.py` lines 537-632
- **Input:** `EntryInput` with corrected fields (from step 2)
- **Processing:**
  - For each line item: Calculate MFN, IEEPA, S301, S232 tariffs
  - Calculate MPF (merchandise processing fee)
  - Calculate HMF (harbor maintenance fee)
  - Sum IEEPA as estimated_refund
  - Determine refund pathway
  - Write audit trail
- **Output:** `CalculationResult` with all duty components

---

## 4️⃣ GET /api/v1/results/{calculation_id}
- **Location:** `results.py` lines 23-114
- **What it does:**
  1. Load `Calculation` record (line 40)
  2. Load associated `Document` for extra fields (line 57)
  3. Merge corrections into supplementary fields (lines 59-62)
  4. Aggregate duty components by tariff type (lines 64-81)
  5. Return complete result with:
     - `estimated_refund` (from corrected IEEPA calculations)
     - `tariff_lines` (MFN, IEEPA, S301, S232, MPF, HMF)
     - `refund_pathway` (PSC, PROTEST, INELIGIBLE)
     - `total_duty`

---

## Data Models

### Document (documents.py)
```
id: uuid                    # job_id
extracted_fields: dict      # Raw OCR output (never modified)
corrections: dict           # User corrections (from PATCH /fields)
status: enum               # queued, processing, completed, review_required, failed
```

### Calculation (calculation.py)
```
id: uuid                    # Unique calculation ID
document_id: uuid           # Links to Document
status: enum               # pending, calculating, completed, failed
entry_number: str
summary_date: date
country_of_origin: str
mode_of_transport: str
total_entered_value: float
duty_components: list       # Array of tariff breakdowns (JSONB)
total_duty: float
estimated_refund: float     # Sum of IEEPA amounts
refund_pathway: enum       # PSC, PROTEST, INELIGIBLE
days_since_summary: int
```

---

## Verification Checklist ✅

| Requirement | Location | Status |
|---|---|---|
| Edits saved to document | PATCH endpoint (line 337) | ✅ Persisted |
| Edits read by calculator | parse_entry_input (line 455) | ✅ Used |
| Corrections override OCR | merge_doc_fields (line 427) | ✅ Overrides |
| Calculation uses corrected data | calculate_entry (line 596) | ✅ Receives merged inputs |
| Results include refund | GET /results (line 101) | ✅ Returns estimated_refund |

---

## File Locations (All Backend)

1. **Documents Endpoint:** C:\Project\RefundCal\backend\app\api\v1\endpoints\documents.py
2. **Results Endpoint:** C:\Project\RefundCal\backend\app\api\v1\endpoints\results.py
3. **Calculation Engine:** C:\Project\RefundCal\backend\app\engine\calculator.py
4. **Document Model:** C:\Project\RefundCal\backend\app\models\document.py
5. **Calculation Model:** C:\Project\RefundCal\backend\app\models\calculation.py

---

## Key Functions

- `patch_document_fields()` - PATCH endpoint
- `merge_doc_fields()` - Merges extracted + corrections
- `parse_entry_input()` - Builds tariff calculation input
- `calculate_document()` - POST endpoint
- `calculate_entry()` - Tariff calculation engine
- `get_result()` - GET results endpoint

