"""
Celery OCR task
================
Processes an uploaded CBP Form 7501 through the OCR pipeline and persists the
extracted fields to the ``documents`` table.

Pipeline (BR-010, Tech_Stack.md §3.1.6)
----------------------------------------
1.  Update document status → ``processing``.
2.  Decrypt the uploaded file from disk (AES-256 / Fernet).
3.  PRIMARY: call Google Document AI Form Parser.
    - On any exception → skip to FALLBACK.
    - On overall_confidence < 0.50 → skip to FALLBACK.
4.  FALLBACK: call pytesseract + pdf2image.
    - On overall_confidence < 0.50 → status = ``failed``,
      error_code = ``UNRECOGNISED_DOCUMENT``.
5.  Apply BR-010:
    - Per-field confidence < 0.80 → ``review_required = true``.
6.  Determine final status:
    - Any ``review_required`` field → ``review_required``.
    - All fields confident       → ``completed``.
7.  Persist ``extracted_fields`` (JSONB), ``ocr_provider``,
    ``ocr_confidence`` to the Document row.

File encryption
---------------
Uploaded files are stored as Fernet-encrypted blobs under
    /data/uploads/{YYYY-MM-DD}/{job_id}/original.{ext}
Encrypted at upload time by the API endpoint; decrypted here before OCR.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import date
from pathlib import Path

from celery import Task
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.core.config import settings
from app.models.document import Document, DocumentStatus
from app.ocr.crypto import decrypt_file_to_bytes, encrypt_bytes_to_file
from app.ocr.models import OcrResult
from app.ocr.google_docai import run_google_docai
from app.ocr.tesseract import run_tesseract
from app.services.tariff_enrichment import enrich_extracted_fields

logger = logging.getLogger(__name__)

# Confidence threshold below which the whole document is rejected (BR-010)
_UNRECOGNISED_THRESHOLD: float = 0.50

_FORM_7501_SIGNATURES: tuple[str, ...] = (
    "cbp form 7501",
    "entry summary",
    "filer code",
    "entry no",
    "entry type",
    "summary date",
    "b/l or awb",
    "line a. htsus no.",
)

# Celery task name (used when queuing from the API endpoint)
TASK_NAME = "app.tasks.ocr.process_ocr_job"


# ---------------------------------------------------------------------------
# Async DB helpers (Celery workers are sync; we use asyncio.run() per task)
# ---------------------------------------------------------------------------

_engine = None

def _make_async_session() -> async_sessionmaker[AsyncSession]:
    """Create a fresh async engine + session factory for use inside a task."""
    global _engine
    if _engine is None:
        kwargs = {"pool_pre_ping": True}
        # SQLite does not support pool_size or max_overflow
        if not settings.DATABASE_URL.startswith("sqlite"):
            kwargs["pool_size"] = 5
            kwargs["max_overflow"] = 10
            
        _engine = create_async_engine(
            settings.DATABASE_URL,
            **kwargs
        )
    return async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


async def _get_document(session: AsyncSession, job_id: uuid.UUID) -> Document | None:
    result = await session.execute(
        select(Document).where(Document.id == job_id)
    )
    return result.scalar_one_or_none()


async def _set_status(
    session: AsyncSession,
    job_id: uuid.UUID,
    status: DocumentStatus,
    *,
    ocr_provider: str | None = None,
    ocr_confidence: float | None = None,
    extracted_fields: dict | None = None,
    error_code: str | None = None,
    extraction_method: str | None = None,
) -> None:
    """Patch the Document row with updated OCR state."""
    values: dict = {"status": status, "error_code": error_code}
    if ocr_provider is not None:
        values["ocr_provider"] = ocr_provider
    if ocr_confidence is not None:
        values["ocr_confidence"] = ocr_confidence
    if extracted_fields is not None:
        values["extracted_fields"] = extracted_fields
    if extraction_method is not None:
        values["extraction_method"] = extraction_method

    await session.execute(
        update(Document).where(Document.id == job_id).values(**values)
    )
    await session.commit()


def _count_populated_fields(ocr_result: OcrResult) -> int:
    """Count extracted header fields that contain a non-empty value."""
    count = 0
    for field in ocr_result.fields.values():
        value = field.value
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        count += 1
    return count


def _looks_like_cbp_7501(ocr_result: OcrResult) -> bool:
    """
    Heuristically determine whether OCR output resembles a CBP Form 7501.

    Non-7501 digital PDFs can still produce readable text or even a high OCR
    confidence, so we look for expected field coverage or characteristic 7501
    labels before allowing the flow to continue.
    """
    populated_fields = _count_populated_fields(ocr_result)
    if populated_fields >= 3 or len(ocr_result.line_items) > 0:
        return True

    raw_text = re.sub(r"\s+", " ", ocr_result.raw_text or "").lower()
    signature_hits = sum(1 for marker in _FORM_7501_SIGNATURES if marker in raw_text)
    return signature_hits >= 2 and (populated_fields >= 1 or len(raw_text) >= 100)


def _classify_failure_code(ocr_result: OcrResult) -> str:
    """Return the most appropriate failure code for the OCR output."""
    if _looks_like_cbp_7501(ocr_result):
        return "UNRECOGNISED_DOCUMENT"

    raw_text_length = len(re.sub(r"\s+", "", ocr_result.raw_text or ""))
    if raw_text_length < 100 and ocr_result.overall_confidence < _UNRECOGNISED_THRESHOLD:
        return "UNRECOGNISED_DOCUMENT"

    return "INVALID_7501_FORMAT"


# ---------------------------------------------------------------------------
# File path resolution
# ---------------------------------------------------------------------------

def _resolve_encrypted_path(encrypted_file_path: str) -> Path:
    """
    Return the absolute path to an encrypted upload file.
    ``encrypted_file_path`` is stored relative to settings.DATA_ROOT.
    """
    root = Path(settings.DATA_ROOT)
    rel = Path(encrypted_file_path)
    if rel.is_absolute():
        return rel
    return root / rel


def build_upload_path(job_id: uuid.UUID, original_filename: str) -> Path:
    """
    Build the destination path for a newly uploaded file:
        /data/uploads/{YYYY-MM-DD}/{job_id}/original.{ext}

    Called at upload time by the API endpoint before triggering this task.
    Returns a path relative to DATA_ROOT for storage in ``encrypted_file_path``.
    """
    ext = Path(original_filename).suffix.lower() or ".bin"
    today = date.today().isoformat()
    rel = Path("uploads") / today / str(job_id) / f"original{ext}"
    return rel


def store_upload_encrypted(
    file_bytes: bytes,
    job_id: uuid.UUID,
    original_filename: str,
) -> str:
    """
    Encrypt *file_bytes* and write to the upload directory.

    Returns the path relative to DATA_ROOT (stored in Document.encrypted_file_path).
    Called synchronously from the upload endpoint before the task is queued.
    """
    rel = build_upload_path(job_id, original_filename)
    abs_path = Path(settings.DATA_ROOT) / rel
    encrypt_bytes_to_file(file_bytes, abs_path, settings.FERNET_KEY_PATH)
    logger.info("Stored encrypted upload: %s (%d bytes)", abs_path, len(file_bytes))
    return str(rel)


# ---------------------------------------------------------------------------
# OCR pipeline (async, runs inside asyncio.run())
# ---------------------------------------------------------------------------

async def _run_ocr_pipeline(job_id_str: str) -> None:
    """
    Full OCR pipeline for one document. Runs inside ``asyncio.run()``.
    """
    job_id = uuid.UUID(job_id_str)
    session_factory = _make_async_session()

    try:
        async with session_factory() as session:
            doc = await _get_document(session, job_id)
            if doc is None:
                logger.error("OCR task: document %s not found", job_id)
                return

            # Mark as processing so the frontend knows work has started
            await _set_status(session, job_id, DocumentStatus.processing)
            logger.info("OCR job %s: status → processing", job_id)

        # ── Decrypt file ──────────────────────────────────────────────────────
        encrypted_path = _resolve_encrypted_path(doc.encrypted_file_path or "")
        try:
            file_bytes = decrypt_file_to_bytes(encrypted_path, settings.FERNET_KEY_PATH)
        except Exception as exc:
            logger.error("OCR job %s: decryption failed: %s", job_id, exc)
            async with session_factory() as session:
                await _set_status(session, job_id, DocumentStatus.failed)
            return

        mime_type = doc.mime_type or "application/pdf"

        # ── Attempt primary: Google Document AI ───────────────────────────────
        ocr_result: OcrResult | None = None
        
        try:
            if settings.GOOGLE_DOC_AI_PROCESSOR_ID and "REPLACE_WITH" not in settings.GOOGLE_DOC_AI_PROCESSOR_ID:
                # Google client is synchronous; run_google_docai is async but blocking.
                # Since we are in a single-task worker, awaiting is fine, but to_thread
                # would be cleaner if it was purely sync. Given it's async def:
                ocr_result = await run_google_docai(file_bytes, mime_type)
        except Exception as exc:
            logger.warning(
                "OCR job %s: Google Document AI failed (%s)",
                job_id, exc,
            )

        # ── Fallback: pytesseract ─────────────────────────────────────────
        if ocr_result is None or ocr_result.overall_confidence < _UNRECOGNISED_THRESHOLD:
            if ocr_result is not None:
                logger.warning(
                    "OCR job %s: Google Document AI confidence %.3f < %.2f",
                    job_id, ocr_result.overall_confidence, _UNRECOGNISED_THRESHOLD,
                )
            
            if not settings.OCR_FALLBACK_ENABLED:
                logger.warning("OCR job %s: fallback disabled, rejecting document", job_id)
                async with session_factory() as session:
                    await _set_status(session, job_id, DocumentStatus.failed)
                return

            try:
                logger.info("OCR job %s: switching to Tesseract fallback", job_id)
                # Tesseract is CPU-bound and synchronous; run in thread
                ocr_result = await asyncio.to_thread(run_tesseract, file_bytes, mime_type)
            except Exception as exc:
                logger.error("OCR job %s: Tesseract also failed: %s", job_id, exc)
                async with session_factory() as session:
                    await _set_status(session, job_id, DocumentStatus.failed)
                return

        # ── BR-010: reject if still unrecognised or doesn't look like a 7501 ──
        if ocr_result.overall_confidence < _UNRECOGNISED_THRESHOLD:
            logger.warning(
                "OCR job %s: %s confidence %.3f still below %.2f — UNRECOGNISED_DOCUMENT",
                job_id, ocr_result.provider, ocr_result.overall_confidence,
                _UNRECOGNISED_THRESHOLD,
            )
            async with session_factory() as session:
                await _set_status(
                    session, job_id, DocumentStatus.failed,
                    ocr_provider=ocr_result.provider,
                    ocr_confidence=ocr_result.overall_confidence,
                    error_code="UNRECOGNISED_DOCUMENT",
                )
            return

        if not _looks_like_cbp_7501(ocr_result):
            error_code = _classify_failure_code(ocr_result)
            logger.warning(
                "OCR job %s: OCR output does not resemble CBP Form 7501 — %s",
                job_id, error_code,
            )
            async with session_factory() as session:
                await _set_status(
                    session, job_id, DocumentStatus.failed,
                    ocr_provider=ocr_result.provider,
                    ocr_confidence=ocr_result.overall_confidence,
                    error_code=error_code,
                )
            return

        # ── Final success processing ─────────────────────────────────────────
        extracted_dict = ocr_result.to_extracted_fields_dict()

        # ── Post-OCR DB enrichment: resolve authoritative HTS rates ─────────
        # CBP Form 7501 Box 33 omits 0% rates, making OCR rate extraction
        # unreliable. We look up each HTS code's rate from the tariff_rates DB.
        _summary_date_str: str = (
            (extracted_dict.get("summary_date") or {}).get("value") or ""
        )
        _country_str: str = (
            (extracted_dict.get("country_of_origin") or {}).get("value") or ""
        ).upper().strip()

        if _summary_date_str and _country_str:
            try:
                from datetime import datetime as _dt
                _summary_date = _dt.strptime(_summary_date_str.strip(), "%m/%d/%Y").date()
                async with session_factory() as _enrich_session:
                    extracted_dict = await enrich_extracted_fields(
                        extracted_dict, _country_str, _summary_date, _enrich_session,
                    )
            except Exception as _enrich_exc:
                logger.warning(
                    "OCR job %s: tariff enrichment failed (non-fatal): %s",
                    job_id, _enrich_exc,
                )
        else:
            logger.warning(
                "OCR job %s: skipping tariff enrichment — "
                "summary_date=%r country=%r not available",
                job_id, _summary_date_str, _country_str,
            )

        review_count = extracted_dict.get("review_required_count", 0)
        
        final_status = (
            DocumentStatus.review_required if review_count > 0
            else DocumentStatus.completed
        )

        logger.info(
            "OCR job %s: provider=%s confidence=%.3f review_fields=%d status=%s",
            job_id,
            ocr_result.provider,
            ocr_result.overall_confidence,
            review_count,
            final_status.value,
        )

        async with session_factory() as session:
            await _set_status(
                session,
                job_id,
                final_status,
                ocr_provider=ocr_result.provider,
                ocr_confidence=ocr_result.overall_confidence,
                extracted_fields=extracted_dict,
                extraction_method=ocr_result.extraction_method,
            )

    except Exception as exc:
        logger.exception("OCR job %s: unhandled exception in pipeline: %s", job_id, exc)
        try:
            async with session_factory() as session:
                await _set_status(session, job_id, DocumentStatus.failed)
        except Exception:
            logger.error("OCR job %s: failed to mark as FAILED in DB", job_id)



# ---------------------------------------------------------------------------
# Celery task definition
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    name=TASK_NAME,
    max_retries=2,
    default_retry_delay=30,   # seconds before retry
    soft_time_limit=90,       # warn at 90 s
    time_limit=120,           # hard kill at 120 s
)
def process_ocr_job(self: Task, job_id: str) -> dict:
    """
    Celery task: run the full OCR pipeline for document *job_id*.

    Parameters
    ----------
    job_id : str
        UUID string of the Document to process.

    Returns
    -------
    dict
        ``{"job_id": str, "status": str}`` — informational; the authoritative
        state lives in the ``documents`` table.
    """
    logger.info("Celery OCR task started: job_id=%s", job_id)
    try:
        asyncio.run(_run_ocr_pipeline(job_id))
    except Exception as exc:
        logger.exception("OCR task %s raised an unexpected error: %s", job_id, exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            async def _mark_failed() -> None:
                sf = _make_async_session()
                async with sf() as session:
                    await _set_status(
                        session, uuid.UUID(job_id), DocumentStatus.failed
                    )
            asyncio.run(_mark_failed())
            return {"job_id": job_id, "status": "failed"}

    logger.info("Celery OCR task completed: job_id=%s", job_id)
    return {"job_id": job_id, "status": "done"}
