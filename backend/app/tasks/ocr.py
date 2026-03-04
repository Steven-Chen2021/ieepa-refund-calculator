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

logger = logging.getLogger(__name__)

# Confidence threshold below which the whole document is rejected (BR-010)
_UNRECOGNISED_THRESHOLD: float = 0.50

# Celery task name (used when queuing from the API endpoint)
TASK_NAME = "app.tasks.ocr.process_ocr_job"


# ---------------------------------------------------------------------------
# Async DB helpers (Celery workers are sync; we use asyncio.run() per task)
# ---------------------------------------------------------------------------

def _make_async_session() -> async_sessionmaker[AsyncSession]:
    """Create a fresh async engine + session factory for use inside a task."""
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=0,
    )
    return async_sessionmaker(
        bind=engine,
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
) -> None:
    """Patch the Document row with updated OCR state."""
    values: dict = {"status": status}
    if ocr_provider is not None:
        values["ocr_provider"] = ocr_provider
    if ocr_confidence is not None:
        values["ocr_confidence"] = ocr_confidence
    if extracted_fields is not None:
        values["extracted_fields"] = extracted_fields

    await session.execute(
        update(Document).where(Document.id == job_id).values(**values)
    )
    await session.commit()


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
    Full OCR pipeline for one document.  Runs inside ``asyncio.run()``.
    """
    job_id = uuid.UUID(job_id_str)
    session_factory = _make_async_session()

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
    except (FileNotFoundError, Exception) as exc:
        logger.error("OCR job %s: decryption failed: %s", job_id, exc)
        async with session_factory() as session:
            await _set_status(session, job_id, DocumentStatus.failed)
        return

    mime_type = doc.mime_type or "application/pdf"

    # ── Attempt primary: Google Document AI ───────────────────────────────
    ocr_result: OcrResult | None = None
    used_fallback = False

    try:
        if not settings.GOOGLE_DOC_AI_PROCESSOR_ID:
            raise ValueError("GOOGLE_DOC_AI_PROCESSOR_ID is not configured")
        ocr_result = await run_google_docai(file_bytes, mime_type)
    except Exception as exc:
        logger.warning(
            "OCR job %s: Google Document AI failed (%s), switching to Tesseract",
            job_id, exc,
        )

    if ocr_result is None or ocr_result.overall_confidence < _UNRECOGNISED_THRESHOLD:
        if ocr_result is not None:
            logger.warning(
                "OCR job %s: Google Document AI confidence %.3f < %.2f, using Tesseract",
                job_id, ocr_result.overall_confidence, _UNRECOGNISED_THRESHOLD,
            )
        # ── Fallback: pytesseract ─────────────────────────────────────────
        if not settings.OCR_FALLBACK_ENABLED:
            logger.warning("OCR job %s: fallback disabled, rejecting document", job_id)
            async with session_factory() as session:
                await _set_status(session, job_id, DocumentStatus.failed)
            return

        try:
            ocr_result = run_tesseract(file_bytes, mime_type)
            used_fallback = True
        except Exception as exc:
            logger.error("OCR job %s: Tesseract also failed: %s", job_id, exc)
            async with session_factory() as session:
                await _set_status(session, job_id, DocumentStatus.failed)
            return

    # ── BR-010: reject if still unrecognised after fallback ───────────────
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
            )
        return

    # ── Determine final status ────────────────────────────────────────────
    extracted_dict = ocr_result.to_extracted_fields_dict()
    review_count: int = extracted_dict.get("review_required_count", 0)

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
        )


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
