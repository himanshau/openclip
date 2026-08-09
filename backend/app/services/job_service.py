from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import JobStatus, ProcessingJob


def update_job_progress(
    db: Session,
    job_id: UUID,
    *,
    progress: int | None = None,
    status: JobStatus | None = None,
    current_step: str | None = None,
    error: dict[str, Any] | None = None,
    metadata_update: dict[str, Any] | None = None,
) -> ProcessingJob:
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise ValueError(f"Job {job_id} not found")

    if progress is not None:
        job.progress = max(0, min(100, int(progress)))
    if status is not None:
        job.status = status
        if status == JobStatus.RUNNING and job.started_at is None:
            job.started_at = datetime.now(UTC)
        if status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
            job.completed_at = datetime.now(UTC)
            if status == JobStatus.COMPLETED:
                job.progress = 100
    if current_step is not None:
        job.current_step = current_step
    if error is not None:
        job.error = error
    if metadata_update:
        meta = dict(job.job_metadata or {})
        meta.update(metadata_update)
        job.job_metadata = meta

    db.add(job)
    db.commit()
    db.refresh(job)
    return job
