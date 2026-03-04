"""
Celery application instance.

All async jobs (OCR, calculation, CRM sync, file cleanup) are dispatched
through this app.  Tasks register themselves via the ``include`` list below.
"""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "ieepa",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.ocr",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)
