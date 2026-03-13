# Backend Code Reference — Detailed Implementation

## 1. PATCH Endpoint — Save Corrections
**File:** C:\Project\RefundCal\backend\app\api\v1\endpoints\documents.py
**Lines:** 306-360

```python
@router.patch(
    "/{job_id}/fields",
    status_code=status.HTTP_200_OK,
    summary="Save user corrections to OCR fields",
)
async def patch_document_fields(
    request: Request,
    job_id: uuid.UUID,
    body: dict,
    session_id_cookie: str | None = Cookie(default=None, alias="session_id"),
    current_user: OptionalUser = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Merge user-supplied corrections into the document's ``corrections`` JSONB
    column.  Returns the merged ``extracted_fields`` view.
    """
    doc = await _get_authorized_doc(db, job_id, session_id_cookie, current_user)

    if doc.status not in (DocumentStatus.completed, DocumentStatus.review_required):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="JOB_NOT_READY",
        )

    # ✅ LINE 331-332: Merge corrections
    existing_corrections: dict = doc.corrections or {}
    existing_corrections.update(body)

    # ✅ LINE 334-339: PERSIST TO DATABASE
    await db.execute(
        update(Document)
        .where(Document.id == job_id)
        .values(corrections=existing_corrections)
    )
    await db.commit()

    # Return merged view for frontend
    merged = dict(doc.extracted_fields or {})
    for key, value in body.items():
        if key == "line_items":
            continue  # line item patching handled separately
        if key in merged and isinstance(merged[key], dict):
            merged[key]["value"] = value
        else:
            merged[key] = {"value": value, "confidence": 1.0, "review_required": False}

    return {
        "success": True,
        "data": {
            "job_id": str(doc.id),
            "corrections_applied": len(body),
            "merged_fields": merged,
        },
        "error": None,
        "meta": None,
    }
```

---

## 2. Document Model
**File:** C:\Project\RefundCal\backend\app\models\document.py
**Lines:** 30-90

```python
class Document(TimestampMixin, Base):
    """
    One row per uploaded Form 7501 file / OCR job.

    `id` is the `job_id` returned to the client.
    `extracted_fields` holds the raw OCR output (JSONB, see API spec §6.4.1).
    `corrections` holds user-applied field corrections from PATCH /fields.
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = uuid_pk()

    # OCR processing state
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status_enum"),
        nullable=False,
        default=DocumentStatus.queued,
        server_default=DocumentStatus.queued.value,
        index=True,
    )
    ocr_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ✅ LINE 79-80: Structured OCR output
    extracted_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ✅ LINE 82-83: User corrections
    corrections: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

---

## 3. Merge Function — Corrections Override Extracted
**File:** C:\Project\RefundCal\backend\app\api\v1\endpoints\documents.py
**Lines:** 407-429

```python
def merge_doc_fields(extracted: dict | None, corrections: dict | None) -> dict:
    """
    Merge user corrections over OCR extracted_fields.
    Returns a flat dict of {field_name: plain_value}.

    extracted_fields values are OcrField dicts: {"value": ..., "confidence": ..., "review_required": ...}
    corrections values are plain scalars (strings from the review form).
    Line-item corrections use keys like "line_items[0].hts_code".
    """
    fields: dict = {}
    
    # Extract OCR values first
    if extracted:
        for k, v in extracted.items():
            if k in ("line_items", "review_required_count"):
                continue
            fields[k] = v["value"] if isinstance(v, dict) and "value" in v else v

    # ✅ LINE 423-427: CORRECTIONS OVERRIDE EXTRACTED_FIELDS
    if corrections:
        for k, v in corrections.items():
            if k == "line_items" or "[" in k:
                continue  # line-item corrections handled separately
            fields[k] = v  # ← User correction replaces extracted value

    return fields
```

---

## 4. POST /calculate — Parse Inputs with Corrections
**File:** C:\Project\RefundCal\backend\app\api\v1\endpoints\documents.py
**Lines:** 453-518 (parse_entry_input function)
**Lines:** 525-660 (calculate_document endpoint)

```python
def parse_entry_input(doc: "Document") -> "EntryInput":
    """Build EntryInput from a Document's extracted_fields + corrections."""
    # ✅ LINE 455: Merge extracted + corrections (corrections override)
    fields = merge_doc_fields(doc.extracted_fields, doc.corrections)
    
    header_country = str(fields.get("country_of_origin") or "").upper()
    summary_date = _parse_date(fields.get("summary_date"))
    total_ev = _safe_decimal(fields.get("total_entered_value"))
    transport = str(fields.get("mode_of_transport") or "air").strip().lower()
    entry_number = str(fields.get("entry_number") or "UNKNOWN").strip()

    # Build line items from extracted_fields + corrections
    raw_items: list = (doc.extracted_fields or {}).get("line_items", [])

    # Collect line-item corrections keyed as "line_items[N].field"
    li_corrections: dict[int, dict] = {}
    for k, v in (doc.corrections or {}).items():
        m = re.match(r"line_items\[(\d+)\]\.(.+)", k)
        if m:
            idx, field = int(m.group(1)), m.group(2)
            li_corrections.setdefault(idx, {})[field] = v

    line_items: list[LineItem] = []
    for i, item in enumerate(raw_items):
        def _fval(d: dict, key: str) -> str:
            v = d.get(key)
            if isinstance(v, dict):
                return str(v.get("value") or "")
            return str(v or "")

        hts = _fval(item, "hts_code")
        ev_raw = _fval(item, "entered_value") or "0"
        country = _fval(item, "country_of_origin") or header_country

        # ✅ LINE 487-490: Apply line-item corrections
        corr = li_corrections.get(i, {})
        hts = corr.get("hts_code", hts)
        ev_raw = corr.get("entered_value", ev_raw)
        country = corr.get("country_of_origin", country)

        ev = _safe_decimal(ev_raw)
        if hts and ev > 0:
            line_items.append(LineItem(
                hts_code=hts,
                country_of_origin=(country.upper() or header_country or ""),
                entered_value=ev,
            ))

    # ... return EntryInput with corrected values
```

```python
@router.post(
    "/{job_id}/calculate",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger tariff calculation for a completed OCR job",
)
async def calculate_document(
    request: Request,
    job_id: uuid.UUID,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    session_id_cookie: str | None = Cookie(default=None, alias="session_id"),
    current_user: OptionalUser = None,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """
    Run the tariff calculation engine (BR-001–BR-011) on an OCR-completed job.
    """
    doc = await _get_authorized_doc(db, job_id, session_id_cookie, current_user)

    if doc.status not in (DocumentStatus.completed, DocumentStatus.review_required):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="JOB_NOT_READY",
        )

    # Idempotency: return existing completed calculation
    existing = await db.execute(
        select(Calculation)
        .where(Calculation.document_id == job_id)
        .order_by(Calculation.created_at.desc())
        .limit(1)
    )
    existing_calc: Calculation | None = existing.scalar_one_or_none()
    if existing_calc and existing_calc.status == CalculationStatus.completed:
        return {
            "success": True,
            "data": {"calculation_id": str(existing_calc.id)},
            "error": None,
            "meta": None,
        }

    # ✅ LINE 570: Parse inputs from OCR fields + corrections
    try:
        inputs = parse_entry_input(doc)  # Uses merge_doc_fields internally
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot parse document fields: {exc}",
        )

    # Create the Calculation row
    calc_id = uuid.uuid4()
    new_calc = Calculation(
        id=calc_id,
        document_id=job_id,
        status=CalculationStatus.calculating,
        entry_number=inputs.entry_number,
        summary_date=inputs.summary_date,
        country_of_origin=(
            inputs.line_items[0].country_of_origin if inputs.line_items else None
        ),
        mode_of_transport=inputs.mode_of_transport,
        total_entered_value=float(inputs.total_entered_value),
    )
    db.add(new_calc)
    await db.commit()

    # ✅ LINE 596-601: Run calculation engine with corrected inputs
    try:
        result = await calculate_entry(
            db=db,
            redis=redis,
            calculation_id=calc_id,
            inputs=inputs,  # Contains merged/corrected fields
        )
    except Exception as exc:
        await db.execute(
            update(Calculation)
            .where(Calculation.id == calc_id)
            .values(status=CalculationStatus.failed)
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Calculation engine error: {exc}",
        )

    # ✅ LINE 614-654: Persist duty breakdown + final status
    duty_json = [
        {
            "tariff_type": dc.tariff_type,
            "hts_code": dc.hts_code,
            "country_of_origin": dc.country_of_origin,
            "entered_value": float(dc.entered_value),
            "rate_pct": float(dc.rate_pct),
            "amount": float(dc.amount),
            "applicable": dc.applicable,
        }
        for dc in result.line_duty_components
    ] + [
        {
            "tariff_type": "MPF",
            "rate_pct": float(MPF_RATE),
            "amount": float(result.mpf.amount),
            "applicable": True,
        },
        {
            "tariff_type": "HMF",
            "rate_pct": float(HMF_RATE),
            "amount": float(result.hmf.amount),
            "applicable": result.hmf.applicable,
        },
    ]

    await db.execute(
        update(Calculation)
        .where(Calculation.id == calc_id)
        .values(
            status=CalculationStatus.completed,
            duty_components=duty_json,
            total_duty=float(result.total_duty),
            estimated_refund=float(result.estimated_refund),
            refund_pathway=result.refund_pathway,
            days_since_summary=result.days_since_summary,
            pathway_rationale=result.pathway_rationale,
        )
    )
    await db.commit()

    return {
        "success": True,
        "data": {"calculation_id": str(calc_id)},
        "error": None,
        "meta": None,
    }
```

---

## 5. Calculation Engine
**File:** C:\Project\RefundCal\backend\app\engine\calculator.py
**Lines:** 537-632

```python
async def calculate_entry(
    *,
    db: AsyncSession,
    redis: aioredis.Redis,
    calculation_id: uuid.UUID,
    inputs: EntryInput,  # ← Already contains corrections (merged fields)
) -> CalculationResult:
    """
    Full tariff calculation pipeline for one CBP Form 7501.

    Execution order (BR-001 – BR-011):
    ①  For each HTS line item:
        a. BR-002  MFN  tariff
        b. BR-001  IEEPA tariff  (CN origin only)
        c. BR-003  S301  tariff
        d. BR-004  S232  tariff  (steel/aluminium only)
    ②  BR-005  MPF  (whole-entry, with $32.71 floor / $634.62 cap)
    ③  BR-006  HMF  (whole-entry, vessel only)
    ④  BR-008  estimated_refund = Σ IEEPA component amounts
    ⑤  BR-007  determine_refund_pathway(summary_date)
    ⑥  BR-011  append-only audit record written to calculation_audit
    """
    all_components: list[DutyComponent] = []

    # ① Per-line-item duties (using corrected HTS codes, countries, values)
    for item in inputs.line_items:
        mfn   = await _calc_mfn(db, redis, item, inputs.summary_date)
        ieepa = await _calc_ieepa(db, redis, item, inputs.summary_date)
        s301  = await _calc_s301(db, redis, item, inputs.summary_date)
        s232  = await _calc_s232(db, redis, item, inputs.summary_date)
        all_components.extend([mfn, ieepa, s301, s232])

    tv = inputs.total_entered_value

    # ② BR-005 MPF
    raw_mpf = (tv * MPF_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    mpf_fee = EntryFee(
        fee_type="MPF",
        total_entered_value=tv,
        raw_amount=raw_mpf,
        amount=calculate_mpf(tv),
        applicable=True,
    )

    # ③ BR-006 HMF
    raw_hmf = (tv * HMF_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    hmf_fee = EntryFee(
        fee_type="HMF",
        total_entered_value=tv,
        raw_amount=raw_hmf,
        amount=calculate_hmf(tv, inputs.mode_of_transport),
        applicable=inputs.mode_of_transport.lower() == VESSEL_TRANSPORT,
    )

    # ④ BR-008: estimated refund = Σ IEEPA amounts (excludes MFN/S301/S232/MPF/HMF)
    estimated_refund: Decimal = sum(
        (c.amount for c in all_components if c.tariff_type == TariffType.IEEPA.value),
        Decimal("0.00"),
    )

    # Total duty = all line-level tariffs + MPF + HMF
    total_duty: Decimal = (
        sum((c.amount for c in all_components), Decimal("0.00"))
        + mpf_fee.amount
        + hmf_fee.amount
    )

    # ⑤ BR-007: refund pathway
    days_elapsed = (date.today() - inputs.summary_date).days
    pathway = determine_refund_pathway(inputs.summary_date)

    result = CalculationResult(
        entry_number=inputs.entry_number,
        summary_date=inputs.summary_date,
        country_of_origin=(
            inputs.line_items[0].country_of_origin if inputs.line_items else ""
        ),
        mode_of_transport=inputs.mode_of_transport,
        total_entered_value=tv,
        line_duty_components=all_components,
        mpf=mpf_fee,
        hmf=hmf_fee,
        total_duty=total_duty,
        estimated_refund=estimated_refund,
        refund_pathway=pathway,
        days_since_summary=days_elapsed,
        pathway_rationale=_pathway_rationale(pathway, days_elapsed),
    )

    # ⑥ BR-011: immutable audit trail
    await _write_audit(db, calculation_id, result, inputs)

    return result
```

---

## 6. GET /api/v1/results/{calculation_id} — Retrieve Results
**File:** C:\Project\RefundCal\backend\app\api\v1\endpoints\results.py
**Lines:** 23-114

```python
@router.get(
    "/{calculation_id}",
    status_code=status.HTTP_200_OK,
    summary="Retrieve a completed tariff calculation result",
)
async def get_result(
    calculation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return the full calculation result for *calculation_id*.
    """
    res = await db.execute(
        select(Calculation).where(Calculation.id == calculation_id)
    )
    calc: Calculation | None = res.scalar_one_or_none()

    if calc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")

    if calc.status in (CalculationStatus.pending, CalculationStatus.calculating):
        raise HTTPException(status_code=status.HTTP_202_ACCEPTED, detail="Calculation in progress")

    if calc.status == CalculationStatus.failed:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Calculation failed",
        )

    # ✅ LINE 56-62: Load document for supplementary fields (including corrections)
    doc_res = await db.execute(select(Document).where(Document.id == calc.document_id))
    doc: Document | None = doc_res.scalar_one_or_none()
    extra = merge_doc_fields(
        doc.extracted_fields if doc else None,
        doc.corrections if doc else None,  # ← Use corrections for extra fields
    )

    # ✅ LINE 64-81: Aggregate duty components by tariff type (sum amounts)
    components: list[dict] = calc.duty_components or []
    agg: dict[str, dict] = {}
    for c in components:
        tt = c.get("tariff_type", "")
        if tt not in agg:
            agg[tt] = {"amount": 0.0, "rate_pct": float(c.get("rate_pct", 0))}
        agg[tt]["amount"] += float(c.get("amount", 0))

    tariff_lines = []
    for tt in ("MFN", "IEEPA", "S301", "S232", "MPF", "HMF"):
        if tt in agg:
            tariff_lines.append({
                "tariff_type": tt,
                "rate": round(agg[tt]["rate_pct"], 6),
                "amount": round(agg[tt]["amount"], 2),
                "refundable": tt in _REFUNDABLE,  # Only IEEPA is refundable
            })

    calculated_at = (
        calc.updated_at.isoformat()
        if hasattr(calc, "updated_at") and calc.updated_at
        else ""
    )

    # ✅ Return complete result with refund information
    return {
        "success": True,
        "data": {
            "calculation_id": str(calc.id),
            "entry_number": calc.entry_number or extra.get("entry_number", ""),
            "summary_date": (
                calc.summary_date.isoformat() if calc.summary_date else extra.get("summary_date", "")
            ),
            "country_of_origin": calc.country_of_origin or extra.get("country_of_origin", ""),
            "port_of_entry": extra.get("port_code", "") or extra.get("port_of_entry", ""),
            "importer_name": calc.importer_name or extra.get("importer_name", ""),
            "mode_of_transport": calc.mode_of_transport or extra.get("mode_of_transport", ""),
            "estimated_refund": float(calc.estimated_refund or 0),  # ✅ Refund from corrected data
            "refund_pathway": (
                calc.refund_pathway.value
                if calc.refund_pathway
                else "INELIGIBLE"
            ),
            "days_elapsed": calc.days_since_summary or 0,
            "tariff_lines": tariff_lines,
            "total_duty": float(calc.total_duty or 0),
            "calculated_at": calculated_at,
        },
        "error": None,
        "meta": None,
    }
```

---

## Calculation Model
**File:** C:\Project\RefundCal\backend\app\models\calculation.py
**Lines:** 34-91

```python
class Calculation(TimestampMixin, Base):
    """
    Tariff calculation result for one Form 7501.

    `duty_components` stores the full breakdown array matching the
    `duty_components` array in GET /api/v1/results/{calculation_id}.
    """

    __tablename__ = "calculations"

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    status: Mapped[CalculationStatus] = mapped_column(
        Enum(CalculationStatus, name="calculation_status_enum"),
        nullable=False,
        default=CalculationStatus.pending,
        server_default=CalculationStatus.pending.value,
        index=True,
    )

    # Entry Summary Fields
    entry_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    summary_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    country_of_origin: Mapped[str | None] = mapped_column(String(2), nullable=True)
    port_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    importer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mode_of_transport: Mapped[str | None] = mapped_column(String(20), nullable=True)
    total_entered_value: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )

    # Calculation Results
    duty_components: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    total_duty: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    estimated_refund: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    refund_pathway: Mapped[RefundPathway | None] = mapped_column(
        Enum(RefundPathway, name="refund_pathway_enum"),
        nullable=True,
    )
    days_since_summary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pathway_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
```

---

## Summary of Verification

✅ **1. Edits Saved:** PATCH endpoint persists to Document.corrections (line 337)
✅ **2. Corrections Used:** calculate_entry receives merged fields (line 570)
✅ **3. Override Logic:** merge_doc_fields puts corrections OVER extracted_fields (line 427)
✅ **4. Results Return:** GET endpoint returns calculated refund from Calculation record (line 101)

**Files Modified/Referenced:**
- C:\Project\RefundCal\backend\app\api\v1\endpoints\documents.py
- C:\Project\RefundCal\backend\app\api\v1\endpoints\results.py
- C:\Project\RefundCal\backend\app\models\document.py
- C:\Project\RefundCal\backend\app\models\calculation.py
- C:\Project\RefundCal\backend\app\engine\calculator.py
