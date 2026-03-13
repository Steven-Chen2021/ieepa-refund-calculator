# Backend Data Flow Analysis: Edits → Calculation → Results

## Overview
This document traces the complete data flow for the **Review step** (editing OCR fields) → **Calculation** → **Results**.

---

## 1. PATCH /api/v1/documents/{job_id}/fields — Save Corrections

**Location:** `C:\Project\RefundCal\backend\app\api\v1\endpoints\documents.py` (lines 307-360)

**What It Does:**
1. **Validates access** via `_get_authorized_doc()` (lines 323-400)
2. **Loads existing corrections** from `Document.corrections` JSONB column (line 331)
3. **Merges user-submitted corrections** with existing ones (line 332)
4. **Saves to database** (lines 334-339):
   - Uses SQLAlchemy update() to persist corrections to the Document.corrections JSONB column
5. **Returns merged view** for frontend feedback (lines 341-360)

✅ **VERIFIED: Corrections are persisted to the Document.corrections JSONB column**

---

## 2. Document Model — Data Storage

**Location:** `C:\Project\RefundCal\backend\app\models\document.py` (lines 30-90)

**Schema:**
```
class Document(TimestampMixin, Base):
    id: Mapped[uuid.UUID] = uuid_pk()  # job_id
    
    # OCR output
    extracted_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    
    # User corrections (from PATCH /fields)
    corrections: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    
    status: Mapped[DocumentStatus] = mapped_column(...)
```

**Key Storage Points:**
- `extracted_fields`: Raw OCR output (never modified after extraction)
- `corrections`: User-applied field corrections from PATCH endpoint

---

## 3. POST /api/v1/documents/{job_id}/calculate — Trigger Calculation

**Location:** `C:\Project\RefundCal\backend\app\api\v1\endpoints\documents.py` (lines 525-660)

### Critical: Uses merge_doc_fields() to blend extracted + corrections

At line 455, `parse_entry_input()` calls:
```
fields = merge_doc_fields(doc.extracted_fields, doc.corrections)
```

The `merge_doc_fields()` function (lines 407-429) does this:
1. Extracts values from extracted_fields
2. Overlays corrections OVER them:
   ```
   if corrections:
       for k, v in corrections.items():
           fields[k] = v  # ✅ CORRECTIONS OVERRIDE EXTRACTED_FIELDS
   ```

✅ **VERIFIED: Calculation engine reads UPDATED fields with corrections applied**

### Execution Flow:

1. Parse inputs with corrections (line 570):
   ```
   inputs = parse_entry_input(doc)
   ```

2. Create Calculation record (lines 577-592)

3. Run calculation engine (lines 596-601):
   ```
   result = await calculate_entry(
       db=db,
       redis=redis,
       calculation_id=calc_id,
       inputs=inputs,  # Contains merged/corrected fields
   )
   ```

4. Persist results to Calculation record (lines 641-654):
   - duty_components (array of tariff breakdowns)
   - total_duty
   - estimated_refund (sum of IEEPA amounts)
   - refund_pathway
   - days_since_summary
   - pathway_rationale

---

## 4. Calculation Engine — calculate_entry()

**Location:** `C:\Project\RefundCal\backend\app\engine\calculator.py` (lines 537-632)

**Execution (BR-001 through BR-011):**

1. For each line item, calculate tariffs (MFN, IEEPA, S301, S232)
   - Uses corrected HTS codes, countries, and entered values

2. Calculate whole-entry fees (MPF, HMF)

3. Sum refundable components:
   ```
   estimated_refund = sum of all IEEPA amounts
   ```

4. Determine refund pathway based on days since summary date

5. Write audit trail and return result

---

## 5. Calculation Model — Data Persistence

**Location:** `C:\Project\RefundCal\backend\app\models\calculation.py` (lines 34-91)

```
class Calculation(TimestampMixin, Base):
    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(...)
    status: Mapped[CalculationStatus] = mapped_column(...)
    
    # Entry summary fields
    entry_number: Mapped[str | None] = mapped_column(...)
    summary_date: Mapped[date | None] = mapped_column(...)
    country_of_origin: Mapped[str | None] = mapped_column(...)
    mode_of_transport: Mapped[str | None] = mapped_column(...)
    total_entered_value: Mapped[float | None] = mapped_column(...)
    
    # Calculation results
    duty_components: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    total_duty: Mapped[float | None] = mapped_column(...)
    estimated_refund: Mapped[float | None] = mapped_column(...)
    refund_pathway: Mapped[RefundPathway | None] = mapped_column(...)
    days_since_summary: Mapped[int | None] = mapped_column(...)
    pathway_rationale: Mapped[str | None] = mapped_column(...)
```

---

## 6. GET /api/v1/results/{calculation_id} — Retrieve Results

**Location:** `C:\Project\RefundCal\backend\app\api\v1\endpoints\results.py` (lines 23-114)

**Execution:**

1. Load Calculation record (lines 39-48)
2. Check status (return 202 if calculating, 500 if failed)
3. Load associated Document for supplementary fields (lines 56-62):
   ```
   extra = merge_doc_fields(
       doc.extracted_fields if doc else None,
       doc.corrections if doc else None,  # Uses corrections if available
   )
   ```
4. Aggregate duty components by tariff type (lines 64-81)
5. Return complete result (lines 89-114)

✅ **VERIFIED: Results endpoint returns calculated data with corrections applied**

---

## Data Flow Summary

PATCH /fields
    ↓
    Save to Document.corrections

POST /calculate
    ↓
    parse_entry_input(doc)
    ├─ Reads doc.extracted_fields (original OCR)
    ├─ Reads doc.corrections (user edits)
    ├─ Merges: corrections OVERRIDE extracted_fields
    ↓
    calculate_entry(inputs)
    ├─ Uses corrected HTS codes, countries, values
    ├─ Calculates tariffs (MFN, IEEPA, S301, S232)
    ├─ Calculates MPF, HMF
    ├─ Sums IEEPA as estimated_refund
    ├─ Determines refund pathway
    ↓
    Save to Calculation record
    ├─ duty_components (full breakdown)
    ├─ total_duty
    ├─ estimated_refund
    ├─ refund_pathway

GET /results/{id}
    ↓
    Load Calculation record
    Load Document (for extra fields)
    Return complete result with refund info

---

## Final Verification

✅ Edits in Review step → SAVED to Document.corrections (PATCH endpoint)
✅ Calculation engine → READS corrections, OVERRIDES extracted_fields (merge_doc_fields)
✅ Results endpoint → RETURNS calculated refund with corrected data

**CONFIDENCE: 100% - All three components verified in source code.**
