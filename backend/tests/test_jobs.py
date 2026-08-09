from __future__ import annotations

import uuid

import pytest

from app.models import JobStatus, JobType, ProcessingJob, Project
from app.services.job_service import update_job_progress
from app.workers.celery_app import celery_app


def test_celery_app_imports():
    assert celery_app.main == "openclip"
    assert "app.workers.tasks" in (celery_app.conf.include or [])


def test_job_model_crud_and_progress():
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db.close()
        pytest.skip(f"PostgreSQL not available: {exc}")

    try:
        project = Project(id=uuid.uuid4(), name="phase1-test")
        db.add(project)
        db.flush()
        job = ProcessingJob(
            id=uuid.uuid4(),
            type=JobType.HEALTHCHECK,
            status=JobStatus.QUEUED,
            progress=0,
            project_id=project.id,
            current_step="queued",
        )
        db.add(job)
        db.commit()

        updated = update_job_progress(
            db,
            job.id,
            status=JobStatus.RUNNING,
            progress=40,
            current_step="running",
        )
        assert updated.status == JobStatus.RUNNING
        assert updated.progress == 40

        done = update_job_progress(db, job.id, status=JobStatus.COMPLETED, progress=100)
        assert done.status == JobStatus.COMPLETED
        assert done.progress == 100
        assert done.completed_at is not None

        db.delete(done)
        db.delete(project)
        db.commit()
    finally:
        db.close()
