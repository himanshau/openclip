from __future__ import annotations

import uuid
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.db.session import get_db
from app.models import (
    Candidate,
    Clip,
    JobStatus,
    JobType,
    ProcessingJob,
    Project,
    Transcript,
    TranscriptSegment,
    TranscriptWord,
    Video,
    VideoStatus,
)
from app.schemas.api import (
    CaptionPresetRead,
    CandidateRead,
    ClipRead,
    JobRead,
    ProcessRequest,
    ProjectCreate,
    ProjectRead,
    TranscriptRead,
    TranscriptSegmentRead,
    TranscriptWordRead,
    VideoRead,
)
from app.services.captions import CaptionService
from app.services.storage import get_storage
from app.workers import tasks as worker_tasks
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/api")


@router.post("/projects", response_model=ProjectRead)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(id=uuid.uuid4(), name=body.name, description=body.description)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.created_at.desc()).all()


@router.get("/projects/{project_id}", response_model=ProjectRead)
def get_project(project_id: UUID, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.delete("/projects/{project_id}")
def delete_project(project_id: UUID, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    db.delete(project)
    db.commit()
    return {"ok": True}


@router.get("/projects/{project_id}/videos", response_model=list[VideoRead])
def list_project_videos(project_id: UUID, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return db.query(Video).filter(Video.project_id == project_id).order_by(Video.created_at.desc()).all()


@router.post("/projects/{project_id}/videos", response_model=VideoRead)
async def upload_video(
    project_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    settings = get_settings()
    data = await file.read()
    if len(data) > settings.max_upload_size:
        raise HTTPException(413, "File too large")
    filename = Path(file.filename or "upload.mp4").name
    ext = Path(filename).suffix.lower()
    if ext not in {".mp4", ".mov", ".mkv", ".webm"}:
        raise HTTPException(400, f"Unsupported extension {ext}")

    video_id = uuid.uuid4()
    storage = get_storage()
    path = storage.save_upload(video_id, filename, data)
    video = Video(
        id=video_id,
        project_id=project_id,
        filename=filename,
        original_path=storage.relative(path),
        status=VideoStatus.UPLOADED,
    )
    db.add(video)

    job = ProcessingJob(
        id=uuid.uuid4(),
        type=JobType.MEDIA_INGESTION,
        status=JobStatus.QUEUED,
        progress=0,
        project_id=project_id,
        video_id=video_id,
        current_step="queued",
    )
    db.add(job)
    db.commit()

    async_result = worker_tasks.media_ingest.delay(str(video_id), str(job.id))
    job.celery_task_id = async_result.id
    db.commit()
    db.refresh(video)
    return video


@router.get("/videos/{video_id}", response_model=VideoRead)
def get_video(video_id: UUID, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    return video


@router.delete("/videos/{video_id}")
def delete_video(video_id: UUID, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    db.delete(video)
    db.commit()
    return {"ok": True}


@router.post("/videos/{video_id}/process", response_model=JobRead)
def process_video(video_id: UUID, body: ProcessRequest | None = None, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    top_n = body.top_n if body else 3
    job = ProcessingJob(
        id=uuid.uuid4(),
        type=JobType.VALIDATION,  # root orchestration marker
        status=JobStatus.QUEUED,
        progress=0,
        project_id=video.project_id,
        video_id=video.id,
        current_step="queued",
        job_metadata={"pipeline": True, "top_n": top_n},
    )
    db.add(job)
    db.commit()
    async_result = worker_tasks.process_video_pipeline.delay(str(video_id), str(job.id), top_n)
    job.celery_task_id = async_result.id
    db.commit()
    db.refresh(job)
    return job


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    job = db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=JobRead)
def cancel_job(job_id: UUID, db: Session = Depends(get_db)):
    job = db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True)
    job.status = JobStatus.CANCELLED
    job.current_step = "cancelled"
    db.commit()
    db.refresh(job)
    return job


@router.get("/videos/{video_id}/transcript", response_model=TranscriptRead)
def get_transcript(video_id: UUID, db: Session = Depends(get_db)):
    transcript = (
        db.query(Transcript)
        .options(joinedload(Transcript.segments).joinedload(TranscriptSegment.words))
        .filter(Transcript.video_id == video_id)
        .one_or_none()
    )
    if not transcript:
        raise HTTPException(404, "Transcript not found")
    segments = []
    for seg in sorted(transcript.segments, key=lambda s: s.start):
        segments.append(
            TranscriptSegmentRead(
                start=seg.start,
                end=seg.end,
                speaker=seg.speaker,
                text=seg.text,
                words=[
                    TranscriptWordRead(
                        word=w.word,
                        start=w.start,
                        end=w.end,
                        confidence=w.confidence,
                        speaker=w.speaker,
                    )
                    for w in sorted(seg.words, key=lambda x: x.start)
                ],
            )
        )
    return TranscriptRead(
        id=transcript.id,
        video_id=transcript.video_id,
        language=transcript.language,
        text=transcript.text,
        duration=transcript.duration,
        segments=segments,
    )


@router.get("/videos/{video_id}/speakers")
def get_speakers(video_id: UUID, db: Session = Depends(get_db)):
    transcript = db.query(Transcript).filter(Transcript.video_id == video_id).one_or_none()
    if not transcript:
        return []
    return [{"id": s.id, "label": s.speaker_label} for s in transcript.speakers]


@router.post("/videos/{video_id}/generate-clips", response_model=JobRead)
def generate_clips(video_id: UUID, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    job = ProcessingJob(
        id=uuid.uuid4(),
        type=JobType.CANDIDATE_GENERATION,
        status=JobStatus.QUEUED,
        video_id=video_id,
        project_id=video.project_id,
    )
    db.add(job)
    db.commit()
    worker_tasks.discover_clips.delay(str(video_id), str(job.id))
    db.refresh(job)
    return job


@router.get("/videos/{video_id}/clips", response_model=list[ClipRead])
def list_clips(video_id: UUID, db: Session = Depends(get_db)):
    clips = db.query(Clip).filter(Clip.video_id == video_id).order_by(Clip.score.desc().nullslast()).all()
    out: list[ClipRead] = []
    for c in clips:
        reasons = None
        if isinstance(c.score_breakdown, dict):
            reasons = c.score_breakdown.get("selection_reasons")
        out.append(
            ClipRead(
                id=c.id,
                video_id=c.video_id,
                title=c.title,
                start=c.start,
                end=c.end,
                score=c.score,
                score_breakdown=c.score_breakdown,
                edit_plan=c.edit_plan,
                render_path=c.render_path,
                thumbnail_path=c.thumbnail_path,
                status=c.status,
                selection_reasons=reasons,
                short_form_potential_score=c.score,
            )
        )
    return out


@router.get("/videos/{video_id}/candidates", response_model=list[CandidateRead])
def list_candidates(video_id: UUID, db: Session = Depends(get_db)):
    rows = (
        db.query(Candidate)
        .filter(Candidate.video_id == video_id)
        .order_by(Candidate.final_score.desc().nullslast())
        .all()
    )
    return [CandidateRead.from_orm_candidate(c) for c in rows]


@router.get("/clips/{clip_id}", response_model=ClipRead)
def get_clip(clip_id: UUID, db: Session = Depends(get_db)):
    clip = db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(404, "Clip not found")
    reasons = None
    if isinstance(clip.score_breakdown, dict):
        reasons = clip.score_breakdown.get("selection_reasons")
    return ClipRead(
        id=clip.id,
        video_id=clip.video_id,
        title=clip.title,
        start=clip.start,
        end=clip.end,
        score=clip.score,
        score_breakdown=clip.score_breakdown,
        edit_plan=clip.edit_plan,
        render_path=clip.render_path,
        thumbnail_path=clip.thumbnail_path,
        status=clip.status,
        selection_reasons=reasons,
        short_form_potential_score=clip.score,
    )


class ClipPerformanceIn(BaseModel):
    platform: str | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    average_view_duration: float | None = None
    average_percentage_viewed: float | None = None
    viewed_vs_swiped_away: float | None = None


@router.post("/clips/{clip_id}/performance")
def upsert_clip_performance(clip_id: UUID, body: ClipPerformanceIn, db: Session = Depends(get_db)):
    from datetime import datetime, timezone

    from app.models import ClipPerformance

    clip = db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(404, "Clip not found")
    row = db.query(ClipPerformance).filter(ClipPerformance.clip_id == clip_id).one_or_none()
    if row is None:
        row = ClipPerformance(id=uuid.uuid4(), clip_id=clip_id)
        db.add(row)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "clip_id": str(clip_id)}


@router.post("/clips/{clip_id}/render", response_model=JobRead)
def render_clip(clip_id: UUID, db: Session = Depends(get_db)):
    clip = db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(404, "Clip not found")
    job = ProcessingJob(
        id=uuid.uuid4(),
        type=JobType.RENDER,
        status=JobStatus.QUEUED,
        video_id=clip.video_id,
        current_step="queued",
    )
    db.add(job)
    db.commit()
    worker_tasks.render_clip.delay(str(clip_id), str(job.id))
    db.refresh(job)
    return job


@router.get("/renders/{clip_id}")
def download_render(clip_id: UUID, db: Session = Depends(get_db)):
    clip = db.get(Clip, clip_id)
    if not clip or not clip.render_path:
        raise HTTPException(404, "Render not found")
    path = get_storage().absolute(clip.render_path)
    if not path.exists():
        raise HTTPException(404, "Render file missing")
    return FileResponse(path, media_type="video/mp4", filename=f"{clip_id}.mp4")


@router.get("/media/{video_id}/original")
def media_original(video_id: UUID, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video or not video.original_path:
        raise HTTPException(404, "Media not found")
    path = get_storage().absolute(video.original_path)
    return FileResponse(path)


@router.get("/caption-presets", response_model=list[CaptionPresetRead])
def caption_presets():
    return [CaptionPresetRead(name=k, config=v) for k, v in CaptionService.PRESETS.items()]


@router.post("/caption-presets")
def create_caption_preset(body: CaptionPresetRead):
    # runtime-only for MVP
    CaptionService.PRESETS[body.name] = body.config
    return body
