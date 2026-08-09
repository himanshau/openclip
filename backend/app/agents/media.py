from __future__ import annotations

from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger, log_extra
from app.models import JobStatus, Video, VideoStatus
from app.services.ffmpeg_service import FFmpegError, get_ffmpeg
from app.services.job_service import update_job_progress
from app.services.storage import get_storage

logger = get_logger(__name__)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


class MediaAgent:
    """Ingest and normalize uploaded media."""

    def process_video(self, db: Session, video_id: UUID, job_id: UUID) -> Video:
        storage = get_storage()
        ffmpeg = get_ffmpeg()
        video = db.get(Video, video_id)
        if video is None:
            raise ValueError(f"Video {video_id} not found")

        try:
            update_job_progress(
                db, job_id, status=JobStatus.RUNNING, progress=5, current_step="validating"
            )
            video.status = VideoStatus.VALIDATING
            db.commit()

            original = storage.absolute(video.original_path or "")
            if not original.exists():
                raise FileNotFoundError(f"Original media missing: {original}")

            ext = original.suffix.lower()
            if ext not in ALLOWED_EXTENSIONS:
                raise ValueError(f"Unsupported extension: {ext}")

            update_job_progress(db, job_id, progress=15, current_step="ffprobe")
            meta = ffmpeg.extract_metadata(original)
            if not meta["has_video"]:
                raise ValueError("No video stream detected")

            video.duration = meta["duration"]
            video.width = meta["width"]
            video.height = meta["height"]
            video.fps = meta["fps"]
            video.codec = meta["codec"]
            video.audio_codec = meta["audio_codec"]
            video.status = VideoStatus.PROCESSING
            db.commit()

            update_job_progress(db, job_id, progress=35, current_step="hash")
            video.sha256 = storage.sha256_file(original)
            db.commit()

            vdir = storage.video_dir(video_id)
            audio_path = vdir / "audio.wav"
            proxy_path = vdir / "proxy.mp4"
            thumb_path = vdir / "thumbnail.jpg"

            update_job_progress(db, job_id, progress=50, current_step="extract_audio")
            if meta["has_audio"]:
                ffmpeg.extract_audio(original, audio_path)
                video.audio_path = storage.relative(audio_path)
            else:
                # Generate silent track for pipeline continuity
                self._generate_silent_wav(audio_path, meta["duration"] or 1.0)
                video.audio_path = storage.relative(audio_path)

            update_job_progress(db, job_id, progress=70, current_step="proxy")
            ffmpeg.generate_proxy(original, proxy_path)
            video.proxy_path = storage.relative(proxy_path)

            update_job_progress(db, job_id, progress=85, current_step="thumbnail")
            at = min(1.0, max(0.0, (meta["duration"] or 1.0) * 0.1))
            ffmpeg.generate_thumbnail(original, thumb_path, at_seconds=at)
            video.thumbnail_path = storage.relative(thumb_path)

            video.status = VideoStatus.READY
            db.commit()
            update_job_progress(
                db, job_id, status=JobStatus.COMPLETED, progress=100, current_step="ready"
            )
            logger.info(
                "media_ingest_complete",
                extra=log_extra(
                    job_id=job_id, video_id=video_id, project_id=video.project_id, stage="media", progress=100
                ),
            )
            return video
        except Exception as exc:
            logger.exception("media_ingest_failed")
            video.status = VideoStatus.FAILED
            db.commit()
            update_job_progress(
                db,
                job_id,
                status=JobStatus.FAILED,
                current_step="failed",
                error={
                    "error_code": "media_ingestion_failed",
                    "message": str(exc),
                    "stage": "media",
                    "technical_details": getattr(exc, "stderr", None) or repr(exc),
                },
            )
            raise

    @staticmethod
    def _generate_silent_wav(path: Path, duration: float) -> None:
        ffmpeg = get_ffmpeg()
        path.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg._run(  # noqa: SLF001 — intentional shared runner
            [
                ffmpeg.ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=r=16000:cl=mono",
                "-t",
                str(max(0.1, duration)),
                str(path),
            ]
        )


def get_media_agent() -> MediaAgent:
    return MediaAgent()
