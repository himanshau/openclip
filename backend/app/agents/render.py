from __future__ import annotations

from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger, log_extra
from app.models import Clip, JobStatus, Video
from app.services.captions import get_caption_service
from app.services.ffmpeg_service import get_ffmpeg
from app.services.job_service import update_job_progress
from app.services.storage import get_storage

logger = get_logger(__name__)


class RenderAgent:
    def render_clip(self, db: Session, clip_id: UUID, job_id: UUID) -> Clip:
        settings = get_settings()
        storage = get_storage()
        ffmpeg = get_ffmpeg()
        clip = db.get(Clip, clip_id)
        if clip is None or not clip.edit_plan:
            raise ValueError("Clip/edit plan missing")
        video = db.get(Video, clip.video_id)
        if video is None:
            raise ValueError("Video missing")

        try:
            update_job_progress(db, job_id, status=JobStatus.RUNNING, progress=10, current_step="prepare")
            plan = clip.edit_plan
            source = storage.absolute(video.original_path or video.proxy_path or "")
            out_dir = storage.root / "renders" / str(video.id)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{clip.id}.mp4"
            ass_path = out_dir / f"{clip.id}.ass"

            events = plan.get("caption_events") or []
            ass_path.write_text(
                get_caption_service().to_ass(events, plan.get("caption_style") or "bold"),
                encoding="utf-8",
            )

            crop = plan.get("crop") or {}
            render_cfg = settings.yaml_config.get("render") or {}
            update_job_progress(db, job_id, progress=40, current_step="ffmpeg")
            ffmpeg.render_vertical_clip(
                source=source,
                output=out_path,
                start=float(plan["start"]),
                end=float(plan["end"]),
                crop_x=int(crop.get("x", 0)),
                crop_y=int(crop.get("y", 0)),
                crop_w=int(crop.get("w", 608)),
                crop_h=int(crop.get("h", 1080)),
                width=int(render_cfg.get("width", 1080)),
                height=int(render_cfg.get("height", 1920)),
                ass_path=ass_path,
                prefer_nvenc=bool(render_cfg.get("prefer_nvenc", True)),
            )

            update_job_progress(db, job_id, progress=80, current_step="validate")
            meta = ffmpeg.validate_output(
                out_path,
                expect_width=int(render_cfg.get("width", 1080)),
                expect_height=int(render_cfg.get("height", 1920)),
            )

            thumb = out_dir / f"{clip.id}_thumb.jpg"
            ffmpeg.generate_thumbnail(out_path, thumb, at_seconds=0.5)
            clip.render_path = storage.relative(out_path)
            clip.thumbnail_path = storage.relative(thumb)
            clip.status = "rendered"
            db.commit()
            update_job_progress(
                db,
                job_id,
                status=JobStatus.COMPLETED,
                progress=100,
                current_step="rendered",
                metadata_update={"duration": meta.get("duration"), "path": clip.render_path},
            )
            logger.info(
                "render_complete",
                extra=log_extra(job_id=job_id, video_id=video.id, stage="render", progress=100),
            )
            return clip
        except Exception as exc:
            logger.exception("render_failed")
            clip.status = "failed"
            db.commit()
            update_job_progress(
                db,
                job_id,
                status=JobStatus.FAILED,
                current_step="failed",
                error={
                    "error_code": "render_failed",
                    "message": str(exc),
                    "stage": "render",
                    "technical_details": getattr(exc, "stderr", None) or repr(exc),
                },
            )
            raise


def get_render_agent() -> RenderAgent:
    return RenderAgent()
