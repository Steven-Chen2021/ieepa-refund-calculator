"""
Documents endpoints
====================
POST /api/v1/documents/upload   — upload CBP Form 7501, trigger OCR
GET  /api/v1/documents/{job_id}/status — poll OCR status
PATCH /api/v1/documents/{job_id}/fields — save user corrections

Upload security controls (Security_Spec.md §7.3.4, SEC-007)
-------------------------------------------------------------
1. Content-Type header check (first line of defence, fast-fail)
2. Magic Bytes validation via python-magic (true type detection)
3. File size ≤ 20 MB
4. privacy_accepted must be "true"
5. X-Idempotency-Key header required (idempotent job creation)
6. File stored encrypted on disk (AES-256/Fernet) before job is queued
7. Session cookie issued to guest on first upload (§7.1.7)
"""
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import magic  # python-magic — SEC-007
import redis.asyncio as aioredis
from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import OptionalUser, get_db, get_redis
from app.core.limiter import limiter
from app.engine.calculator import (
    EntryInput,
    LineItem,
    MPF_RATE,
    HMF_RATE,
    calculate_entry,
)
from app.models.calculation import Calculation, CalculationStatus
from app.models.document import Document, DocumentStatus
from app.tasks.ocr import TASK_NAME, store_upload_encrypted

router = APIRouter(prefix="/documents", tags=["documents"])

# ---------------------------------------------------------------------------
# Constants — SEC-007
# ---------------------------------------------------------------------------

# Accepted MIME types (magic-bytes derived, not extension-based)
_ALLOWED_MIMES: frozenset[str] = frozenset(
    {"application/pdf", "image/jpeg", "image/png"}
)

_MAX_BYTES: int = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024  # 20 MB

# Session cookie TTL: 24 hours (§7.1.7)
_SESSION_TTL = 86400

# File TTL: 24 hours (SEC-003)
_FILE_TTL_HOURS = settings.FILE_CLEANUP_TTL_HOURS


# ---------------------------------------------------------------------------
# Magic-bytes MIME validator (SEC-007)
# ---------------------------------------------------------------------------

async def _validate_file(file: UploadFile) -> bytes:
    """
    Read the full file, validate MIME via Magic Bytes, enforce size limit.

    Returns the raw file bytes (already read — caller must not re-read).

    Raises
    ------
    HTTP 413 FILE_TOO_LARGE        — file exceeds 20 MB
    HTTP 415 UNSUPPORTED_FILE_TYPE — magic bytes don't match allowed types
    """
    # Read in chunks to enforce size limit without buffering the whole file
    # before we know it's too large.
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(65536)  # 64 KB per read
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="FILE_TOO_LARGE",
            )
        chunks.append(chunk)

    raw = b"".join(chunks)

    # Magic Bytes check — read first 8 KB (sufficient for all supported types)
    detected_mime: str = magic.from_buffer(raw[:8192], mime=True)
    if detected_mime not in _ALLOWED_MIMES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="UNSUPPORTED_FILE_TYPE",
        )

    return raw


# ---------------------------------------------------------------------------
# POST /documents/upload
# ---------------------------------------------------------------------------

@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload CBP Form 7501 and start OCR job",
)
@limiter.limit(settings.RATE_LIMIT_UPLOAD)   # 10/hour — SEC-005
async def upload_document(
    request: Request,
    response: Response,
    file: UploadFile = File(..., description="PDF / JPEG / PNG, max 20 MB"),
    privacy_accepted: str = Form(..., description='Must be "true"'),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    session_id_cookie: str | None = Cookie(default=None, alias="session_id"),
    current_user: OptionalUser = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Upload a CBP Form 7501 file and queue an async OCR job.

    Security controls applied (in order):
    1. Rate limit: 10 uploads / IP / hour (slowapi)
    2. privacy_accepted == "true" required
    3. X-Idempotency-Key required (idempotent)
    4. Content-Type header pre-check (fast-fail)
    5. Magic Bytes MIME validation via python-magic (SEC-007)
    6. File size ≤ 20 MB
    7. File encrypted with Fernet before writing to disk (SEC-002)
    8. OCR Celery job enqueued

    Response: 202 Accepted with { job_id, status, expires_at }
    """
    # ── 1. Privacy consent ────────────────────────────────────────────────
    if privacy_accepted.lower() != "true":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PRIVACY_NOT_ACCEPTED",
        )

    # ── 2. Idempotency key ────────────────────────────────────────────────
    if not x_idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="X-Idempotency-Key header is required",
        )

    # ── 3. Check idempotency: return existing job if key already used ──────
    existing = await db.execute(
        select(Document).where(Document.idempotency_key == x_idempotency_key)
    )
    existing_doc: Document | None = existing.scalar_one_or_none()
    if existing_doc is not None:
        return _upload_response(existing_doc)

    # ── 4. Content-Type pre-check (fast-fail before magic-bytes read) ──────
    content_type = (file.content_type or "").split(";")[0].strip()
    if content_type and content_type not in _ALLOWED_MIMES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="UNSUPPORTED_FILE_TYPE",
        )

    # ── 5+6. Magic Bytes validation + size check ──────────────────────────
    raw_bytes = await _validate_file(file)

    # ── 7. Resolve session ────────────────────────────────────────────────
    session_id = session_id_cookie
    is_new_session = False
    if session_id is None and current_user is None:
        session_id = str(uuid.uuid4())
        is_new_session = True

    user_id: str | None = (
        str(current_user.sub) if current_user else None  # type: ignore[attr-defined]
    )

    # ── 8. Create Document record ─────────────────────────────────────────
    job_id = uuid.uuid4()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=_FILE_TTL_HOURS)

    doc = Document(
        id=job_id,
        user_id=uuid.UUID(user_id) if user_id else None,
        session_id=session_id,
        idempotency_key=x_idempotency_key,
        original_filename=file.filename or "upload",
        mime_type=content_type or "application/octet-stream",
        file_size_bytes=len(raw_bytes),
        privacy_accepted=True,
        status=DocumentStatus.queued,
        expires_at=expires_at,
    )
    db.add(doc)
    await db.flush()   # get the ID without committing yet

    # ── 9. Encrypt file to disk (SEC-002, AES-256/Fernet) ─────────────────
    encrypted_rel_path = store_upload_encrypted(
        file_bytes=raw_bytes,
        job_id=job_id,
        original_filename=file.filename or "upload",
    )

    # Persist path back to the document row
    await db.execute(
        update(Document)
        .where(Document.id == job_id)
        .values(encrypted_file_path=encrypted_rel_path)
    )
    await db.commit()

    # ── 10. Enqueue Celery OCR task ───────────────────────────────────────
    from app.celery_app import celery_app  # local import avoids circular deps at module load

    celery_app.send_task(TASK_NAME, args=[str(job_id)])

    # ── 11. Set session cookie for guests ─────────────────────────────────
    if is_new_session and session_id:
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=_SESSION_TTL,
        )

    return _upload_response(doc)


def _upload_response(doc: Document) -> dict:
    """Build the standard 202 response body."""
    return {
        "success": True,
        "data": {
            "job_id": str(doc.id),
            "status": doc.status.value,
            "expires_at": doc.expires_at.isoformat() if doc.expires_at else None,
        },
        "error": None,
        "meta": None,
    }


# ---------------------------------------------------------------------------
# GET /documents/{job_id}/status
# ---------------------------------------------------------------------------

@router.get(
    "/{job_id}/status",
    status_code=status.HTTP_200_OK,
    summary="Poll OCR job status",
)
@limiter.limit(settings.RATE_LIMIT_GET)   # 60/minute
async def get_document_status(
    request: Request,
    job_id: uuid.UUID,
    session_id_cookie: str | None = Cookie(default=None, alias="session_id"),
    current_user: OptionalUser = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Returns current OCR status and extracted fields once processing is complete.

    Access control: session cookie or authenticated user must own the document.
    """
    doc = await _get_authorized_doc(db, job_id, session_id_cookie, current_user)

    data: dict = {
        "job_id": str(doc.id),
        "status": doc.status.value,
        "ocr_provider": doc.ocr_provider,
        "ocr_confidence": doc.ocr_confidence,
    }

    if doc.status in (DocumentStatus.completed, DocumentStatus.review_required):
        data["extracted_fields"] = doc.extracted_fields

    return {"success": True, "data": data, "error": None, "meta": None}


# ---------------------------------------------------------------------------
# PATCH /documents/{job_id}/fields
# ---------------------------------------------------------------------------

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

    existing_corrections: dict = doc.corrections or {}
    existing_corrections.update(body)

    await db.execute(
        update(Document)
        .where(Document.id == job_id)
        .values(corrections=existing_corrections)
    )
    await db.commit()

    # Merge corrections over extracted_fields for the response
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


# ---------------------------------------------------------------------------
# Shared authorization helper
# ---------------------------------------------------------------------------

async def _get_authorized_doc(
    db: AsyncSession,
    job_id: uuid.UUID,
    session_id: str | None,
    current_user: "TokenPayload | None",
) -> Document:
    """
    Load document and verify that the requester owns it (session or JWT).

    Raises HTTP 404 if not found, HTTP 403 if unauthorized.
    """
    from app.core.dependencies import TokenPayload  # avoid circular import at top

    result = await db.execute(select(Document).where(Document.id == job_id))
    doc: Document | None = result.scalar_one_or_none()

    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    # Admins can see any document
    if current_user and current_user.role == "admin":
        return doc

    # Authenticated user must own the document
    if current_user and doc.user_id is not None:
        if str(doc.user_id) == current_user.sub:
            return doc
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Guest: session cookie must match
    if session_id and doc.session_id == session_id:
        return doc

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


# ---------------------------------------------------------------------------
# Field-merge helpers (also imported by results endpoint)
# ---------------------------------------------------------------------------

def merge_doc_fields(extracted: dict | None, corrections: dict | None) -> dict:
    """
    Merge user corrections over OCR extracted_fields.
    Returns a flat dict of {field_name: plain_value}.

    extracted_fields values are OcrField dicts: {"value": ..., "confidence": ..., "review_required": ...}
    corrections values are plain scalars (strings from the review form).
    Line-item corrections use keys like "line_items[0].hts_code".
    """
    fields: dict = {}
    if extracted:
        for k, v in extracted.items():
            if k in ("line_items", "review_required_count"):
                continue
            fields[k] = v["value"] if isinstance(v, dict) and "value" in v else v

    if corrections:
        for k, v in corrections.items():
            if k == "line_items" or "[" in k:
                continue  # line-item corrections handled separately
            fields[k] = v

    return fields


def _parse_date(raw: object) -> date:
    """Parse a date string from OCR (various formats) or return today."""
    if not raw:
        return date.today()
    raw_str = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(raw_str, fmt).date()
        except ValueError:
            continue
    return date.today()


def _safe_decimal(val: object, default: Decimal = Decimal("0")) -> Decimal:
    try:
        cleaned = str(val).replace(",", "").replace("$", "").strip()
        return Decimal(cleaned)
    except (InvalidOperation, TypeError, ValueError):
        return default


def _parse_rate_pct(raw: str) -> Decimal | None:
    """
    Parse an OCR-extracted rate string to a decimal fraction.
    Handles both percentage strings ("7.5%", "14.5 %") and decimal fractions ("0.075", "0.145").
    Returns None if parsing fails or the value is zero/negative.
    """
    if not raw:
        return None
    cleaned = raw.strip()
    try:
        if "%" in cleaned:
            pct = Decimal(cleaned.replace("%", "").replace(",", "").strip())
            rate = (pct / Decimal("100")).quantize(Decimal("0.000001"))
        else:
            rate = Decimal(cleaned.replace(",", ""))
            # Heuristic: values > 1 are likely percentages (e.g. "7.5" means 7.5%)
            if rate > Decimal("1"):
                rate = (rate / Decimal("100")).quantize(Decimal("0.000001"))
        return rate if rate > Decimal("0") else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def parse_entry_input(doc: "Document") -> "EntryInput":
    """Build EntryInput from a Document's extracted_fields + corrections."""
    fields = merge_doc_fields(doc.extracted_fields, doc.corrections)
    header_country = str(fields.get("country_of_origin") or "").upper()

    summary_date = _parse_date(fields.get("summary_date"))
    total_ev = _safe_decimal(fields.get("total_entered_value"))
    transport = str(fields.get("mode_of_transport") or "air").strip().lower()
    entry_number = str(fields.get("entry_number") or "UNKNOWN").strip()

    # --- Build line items from extracted_fields ---
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
        # OCR uses "tariff_category" and "duty_rate" as field names
        ocr_category_raw = (_fval(item, "tariff_category") or _fval(item, "category")).upper().strip()
        ocr_rate_str = _fval(item, "duty_rate") or _fval(item, "rate")
        ocr_duty_amount_str = _fval(item, "duty_amount") or _fval(item, "amount")
        is_ieepa_flag = bool(item.get("is_ieepa", False))

        # Apply line-item corrections
        corr = li_corrections.get(i, {})
        hts = corr.get("hts_code", hts)
        ev_raw = corr.get("entered_value", ev_raw)
        country = corr.get("country_of_origin", country)
        if "tariff_category" in corr:
            ocr_category_raw = corr["tariff_category"].upper().strip()
        elif "category" in corr:
            ocr_category_raw = corr["category"].upper().strip()
        if "duty_rate" in corr:
            ocr_rate_str = corr["duty_rate"]
        elif "rate" in corr:
            ocr_rate_str = corr["rate"]

        ev = _safe_decimal(ev_raw)
        ocr_rate = _parse_rate_pct(ocr_rate_str)
        _ocr_da = _safe_decimal(ocr_duty_amount_str) if ocr_duty_amount_str else Decimal("0")
        ocr_duty_amount_val: Decimal | None = _ocr_da if _ocr_da > Decimal("0") else None

        # Map OCR category labels to canonical tariff types
        _CAT_MAP = {
            "MAIN": "MFN",    # primary commercial tariff line on CBP 7501
            "MFN": "MFN",
            "IEEPA": "IEEPA",
            "S301": "S301",
            "S232": "S232",
        }
        ocr_tariff_type: str | None = "IEEPA" if is_ieepa_flag else _CAT_MAP.get(ocr_category_raw)

        if hts and ev > 0:
            # Standard commercial line with entered_value
            line_items.append(LineItem(
                hts_code=hts,
                country_of_origin=(country.upper() or header_country or ""),
                entered_value=ev,
                ocr_tariff_type=ocr_tariff_type,
                ocr_rate_pct=ocr_rate,
                ocr_duty_amount=None,  # entered_value × rate used; ocr_duty_amount only for add-ons
            ))
        elif hts and ocr_tariff_type == "IEEPA" and ocr_duty_amount_val is not None:
            # IEEPA add-on line (e.g. HTS 9903.01.24/25): no entered_value on the form,
            # but duty_amount is printed directly. Use duty_amount as the authoritative amount.
            line_items.append(LineItem(
                hts_code=hts,
                country_of_origin=(country.upper() or header_country or ""),
                entered_value=Decimal("1"),  # placeholder — not used in calculation
                ocr_tariff_type="IEEPA",
                ocr_rate_pct=ocr_rate,
                ocr_duty_amount=ocr_duty_amount_val,
            ))

    # Fallback: one synthetic line item using the total_entered_value
    if not line_items:
        fallback_country = header_country or "CN"
        line_items.append(LineItem(
            hts_code="0000.00.0000",
            country_of_origin=fallback_country,
            entered_value=total_ev if total_ev > 0 else Decimal("1"),
        ))

    if total_ev == Decimal("0"):
        total_ev = sum(li.entered_value for li in line_items)

    return EntryInput(
        entry_number=entry_number,
        summary_date=summary_date,
        mode_of_transport=transport,
        line_items=line_items,
        total_entered_value=total_ev,
    )


# ---------------------------------------------------------------------------
# POST /documents/{job_id}/calculate
# ---------------------------------------------------------------------------

@router.post(
    "/{job_id}/calculate",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger tariff calculation for a completed OCR job",
)
@limiter.limit("20/minute")
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
    Returns calculation_id; result is available via GET /api/v1/results/{id}.
    """
    doc = await _get_authorized_doc(db, job_id, session_id_cookie, current_user)

    if doc.status not in (DocumentStatus.completed, DocumentStatus.review_required):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="JOB_NOT_READY",
        )

    # Idempotency: return existing completed calculation for this document
    existing = await db.execute(
        select(Calculation)
        .where(Calculation.document_id == job_id)
        .order_by(Calculation.created_at.desc())  # type: ignore[attr-defined]
        .limit(1)
    )
    existing_calc: Calculation | None = existing.scalar_one_or_none()
    if existing_calc and existing_calc.status == CalculationStatus.completed:
        # Only reuse a completed calculation if it produced meaningful tariff-line amounts.
        # A non-zero estimated_refund or non-zero tariff duty (beyond MPF/HMF) indicates
        # the DB had rate data when the calculation ran. If both are $0, the tariff_rates
        # DB was likely empty — recalculate so OCR-extracted fallback rates are applied.
        prior_components: list[dict] = existing_calc.duty_components or []
        line_duty_nonzero = any(
            float(c.get("amount", 0)) > 0
            for c in prior_components
            if c.get("tariff_type") not in ("MPF", "HMF")
        )
        if line_duty_nonzero or float(existing_calc.estimated_refund or 0) > 0:
            return {
                "success": True,
                "data": {"calculation_id": str(existing_calc.id)},
                "error": None,
                "meta": None,
            }

    # Parse inputs from OCR fields + corrections
    try:
        inputs = parse_entry_input(doc)
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

    # Run calculation synchronously in-process (BR-001–BR-011)
    try:
        result = await calculate_entry(
            db=db,
            redis=redis,
            calculation_id=calc_id,
            inputs=inputs,
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

    # Persist duty breakdown + final status (CalculationAudit added by calculate_entry)
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
