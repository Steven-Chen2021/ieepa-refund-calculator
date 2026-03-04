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
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import magic  # python-magic — SEC-007
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
from app.core.dependencies import OptionalUser, get_db
from app.core.limiter import limiter
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
    async for chunk in file:
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
