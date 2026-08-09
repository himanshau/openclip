from __future__ import annotations

from uuid import UUID

from app.core.logging import get_logger, log_extra
from app.db.session import SessionLocal
from app.models import JobStatus
from app.services.job_service import update_job_progress
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="openclip.healthcheck_noop", bind=True)
def healthcheck_noop(self, job_id: str | None = None) -> dict:
    """Prove the worker can run. Optionally updates a ProcessingJob row."""
    logger.info(
        "healthcheck_noop_start",
        extra=log_extra(job_id=job_id or "-", stage="healthcheck", progress=0),
    )
    if job_id:
        db = SessionLocal()
        try:
            update_job_progress(
                db,
                UUID(job_id),
                status=JobStatus.RUNNING,
                progress=50,
                current_step="worker_ping",
            )
            update_job_progress(
                db,
                UUID(job_id),
                status=JobStatus.COMPLETED,
                progress=100,
                current_step="done",
                metadata_update={"celery_task_id": self.request.id},
            )
        finally:
            db.close()

    result = {"ok": True, "task_id": self.request.id}
    logger.info(
        "healthcheck_noop_done",
        extra=log_extra(job_id=job_id or "-", stage="healthcheck", progress=100),
    )
    return result
