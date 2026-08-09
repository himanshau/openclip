from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.agents.clip_discovery import get_clip_discovery_agent
from app.agents.editing import get_editing_agent
from app.agents.media import get_media_agent
from app.agents.render import get_render_agent
from app.agents.transcript import get_transcript_agent
from app.core.logging import get_logger, log_extra
from app.db.session import SessionLocal
from app.models import Candidate, Clip, JobStatus, JobType, ProcessingJob, Video
from app.services.job_service import update_job_progress
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


def _create_job(db: Session, *, job_type: JobType, video_id: UUID, project_id: UUID | None) -> ProcessingJob:
    job = ProcessingJob(
        id=uuid4(),
        type=job_type,
        status=JobStatus.QUEUED,
        progress=0,
        video_id=video_id,
        project_id=project_id,
        current_step="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@celery_app.task(name="openclip.healthcheck_noop", bind=True)
def healthcheck_noop(self, job_id: str | None = None) -> dict:
    logger.info("healthcheck_noop_start", extra=log_extra(job_id=job_id or "-", stage="healthcheck"))
    if job_id:
        db = SessionLocal()
        try:
            update_job_progress(db, UUID(job_id), status=JobStatus.RUNNING, progress=50, current_step="worker_ping")
            update_job_progress(db, UUID(job_id), status=JobStatus.COMPLETED, progress=100, current_step="done")
        finally:
            db.close()
    return {"ok": True, "task_id": self.request.id}


@celery_app.task(name="openclip.media_ingest", bind=True)
def media_ingest(self, video_id: str, job_id: str) -> dict:
    db = SessionLocal()
    try:
        job = db.get(ProcessingJob, UUID(job_id))
        if job:
            job.celery_task_id = self.request.id
            db.commit()
        get_media_agent().process_video(db, UUID(video_id), UUID(job_id))
        return {"ok": True, "video_id": video_id}
    finally:
        db.close()


@celery_app.task(name="openclip.transcribe", bind=True)
def transcribe(self, video_id: str, job_id: str) -> dict:
    db = SessionLocal()
    try:
        get_transcript_agent().process(db, UUID(video_id), UUID(job_id))
        return {"ok": True}
    finally:
        db.close()


@celery_app.task(name="openclip.discover_clips", bind=True)
def discover_clips(self, video_id: str, job_id: str) -> dict:
    db = SessionLocal()
    try:
        cands = get_clip_discovery_agent().process(db, UUID(video_id), UUID(job_id))
        return {"ok": True, "count": len(cands)}
    finally:
        db.close()


@celery_app.task(name="openclip.rank_candidates", bind=True)
def rank_candidates(self, video_id: str, job_id: str) -> dict:
    from app.services.ranker import get_virality_engine
    from uuid import uuid4

    db = SessionLocal()
    try:
        update_job_progress(
            db, UUID(job_id), status=JobStatus.RUNNING, progress=10, current_step="virality_ranking"
        )
        engine = get_virality_engine()
        candidates = db.query(Candidate).filter(Candidate.video_id == UUID(video_id)).all()
        raw = [
            {
                "id": str(c.id),
                "start": c.start,
                "end": c.end,
                "text": c.text,
                "features": c.features or {},
                "deterministic_score": c.deterministic_score,
                "final_score": c.final_score,
            }
            for c in candidates
        ]
        survivors = engine.run(raw)
        keep_payload = {s.id: s for s in survivors if s.id}

        # Delete weak / non-selected candidates
        kept_ids = set(keep_payload.keys())
        for cand in candidates:
            sid = str(cand.id)
            if sid not in kept_ids:
                db.delete(cand)
                continue
            result = keep_payload[sid]
            # If context expansion changed bounds, update
            cand.start = result.start
            cand.end = result.end
            cand.text = result.text
            cand.final_score = result.final_score
            cand.llm_score = {
                "short_form_potential_score": result.final_score,
                "feature_scores": result.feature_scores,
                "penalties": result.penalties,
                "selection_reasons": result.selection_reasons,
                "ranking_version": result.ranking_version,
                "ranking_weights": result.ranking_weights,
                "source": result.source,
                "llm_semantic": (result.features or {}).get("llm_semantic"),
            }
            feats = dict(cand.features or {})
            feats.update(
                {
                    "selection_reasons": result.selection_reasons,
                    "feature_scores": result.feature_scores,
                    "penalties": result.penalties,
                    "ranking_version": result.ranking_version,
                }
            )
            cand.features = feats

        # Survivors without matching id (pure expansions) → insert new Candidate rows
        for result in survivors:
            if result.id and result.id in {str(c.id) for c in candidates}:
                continue
            new_id = uuid4()
            db.add(
                Candidate(
                    id=new_id,
                    video_id=UUID(video_id),
                    start=result.start,
                    end=result.end,
                    text=result.text,
                    features={
                        **(result.features or {}),
                        "selection_reasons": result.selection_reasons,
                        "feature_scores": result.feature_scores,
                        "penalties": result.penalties,
                        "ranking_version": result.ranking_version,
                    },
                    deterministic_score=result.final_score,
                    llm_score={
                        "short_form_potential_score": result.final_score,
                        "feature_scores": result.feature_scores,
                        "penalties": result.penalties,
                        "selection_reasons": result.selection_reasons,
                        "ranking_version": result.ranking_version,
                        "source": result.source,
                    },
                    final_score=result.final_score,
                )
            )
            result.id = str(new_id)

        remaining = (
            db.query(Candidate)
            .filter(Candidate.video_id == UUID(video_id))
            .order_by(Candidate.final_score.desc().nullslast())
            .all()
        )
        for rank, cand in enumerate(remaining, start=1):
            cand.rank = rank
        db.commit()
        update_job_progress(
            db,
            UUID(job_id),
            status=JobStatus.COMPLETED,
            progress=100,
            current_step="virality_ranked",
            metadata_update={
                "input_candidates": len(raw),
                "kept": len(remaining),
                "min_short_form_score": engine.min_score,
            },
        )
        return {"ok": True, "input": len(raw), "kept": len(remaining)}
    except Exception as exc:
        update_job_progress(
            db,
            UUID(job_id),
            status=JobStatus.FAILED,
            error={"error_code": "ranking_failed", "message": str(exc), "stage": "virality"},
        )
        raise
    finally:
        db.close()


@celery_app.task(name="openclip.edit_plans", bind=True)
def edit_plans(self, video_id: str, job_id: str, top_n: int = 5) -> dict:
    db = SessionLocal()
    try:
        clips = get_editing_agent().process(db, UUID(video_id), UUID(job_id), top_n=top_n)
        return {"ok": True, "clips": len(clips)}
    finally:
        db.close()


@celery_app.task(name="openclip.render_clip", bind=True)
def render_clip(self, clip_id: str, job_id: str) -> dict:
    db = SessionLocal()
    try:
        clip = get_render_agent().render_clip(db, UUID(clip_id), UUID(job_id))
        return {"ok": True, "render_path": clip.render_path}
    finally:
        db.close()


@celery_app.task(name="openclip.process_video_pipeline", bind=True)
def process_video_pipeline(self, video_id: str, root_job_id: str, top_n: int = 3) -> dict:
    """Full pipeline: media → transcript → discover → rank → edit → render top clips."""
    db = SessionLocal()
    try:
        video = db.get(Video, UUID(video_id))
        if video is None:
            raise ValueError("video not found")
        project_id = video.project_id
        update_job_progress(
            db, UUID(root_job_id), status=JobStatus.RUNNING, progress=5, current_step="media"
        )

        # Media (if not ready)
        if video.status.value != "READY":
            media_job = _create_job(db, job_type=JobType.MEDIA_INGESTION, video_id=video.id, project_id=project_id)
            get_media_agent().process_video(db, video.id, media_job.id)
        update_job_progress(db, UUID(root_job_id), progress=20, current_step="transcription")

        t_job = _create_job(db, job_type=JobType.TRANSCRIPTION, video_id=video.id, project_id=project_id)
        get_transcript_agent().process(db, video.id, t_job.id)
        update_job_progress(db, UUID(root_job_id), progress=40, current_step="discovery")

        d_job = _create_job(db, job_type=JobType.CANDIDATE_GENERATION, video_id=video.id, project_id=project_id)
        get_clip_discovery_agent().process(db, video.id, d_job.id)
        update_job_progress(db, UUID(root_job_id), progress=55, current_step="ranking")

        r_job = _create_job(db, job_type=JobType.LLM_RANKING, video_id=video.id, project_id=project_id)
        # call ranking logic inline via task function body
        rank_candidates.run(video_id, str(r_job.id))
        update_job_progress(db, UUID(root_job_id), progress=70, current_step="editing")

        e_job = _create_job(db, job_type=JobType.EDIT_PLANNING, video_id=video.id, project_id=project_id)
        clips = get_editing_agent().process(db, video.id, e_job.id, top_n=top_n)
        update_job_progress(db, UUID(root_job_id), progress=80, current_step="rendering")

        rendered = 0
        for clip in clips:
            rj = _create_job(db, job_type=JobType.RENDER, video_id=video.id, project_id=project_id)
            get_render_agent().render_clip(db, clip.id, rj.id)
            rendered += 1

        update_job_progress(
            db,
            UUID(root_job_id),
            status=JobStatus.COMPLETED,
            progress=100,
            current_step="complete",
            metadata_update={"rendered": rendered},
        )
        return {"ok": True, "rendered": rendered}
    except Exception as exc:
        logger.exception("pipeline_failed")
        update_job_progress(
            db,
            UUID(root_job_id),
            status=JobStatus.FAILED,
            current_step="failed",
            error={"error_code": "pipeline_failed", "message": str(exc), "stage": "pipeline"},
        )
        raise
    finally:
        db.close()
