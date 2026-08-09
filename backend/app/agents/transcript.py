from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger, log_extra
from app.models import (
    JobStatus,
    Speaker,
    Transcript,
    TranscriptSegment,
    TranscriptWord,
    Video,
)
from app.services.job_service import update_job_progress
from app.services.model_manager import get_model_manager
from app.services.storage import get_storage

logger = get_logger(__name__)

FILLERS = {"um", "uh", "erm", "ah", "like", "you know"}


class TranscriptAgent:
    def process(self, db: Session, video_id: UUID, job_id: UUID) -> Transcript:
        settings = get_settings()
        storage = get_storage()
        video = db.get(Video, video_id)
        if video is None or not video.audio_path:
            raise ValueError("Video/audio not ready for transcription")

        audio = storage.absolute(video.audio_path)
        update_job_progress(db, job_id, status=JobStatus.RUNNING, progress=5, current_step="load_whisper")

        try:
            result = asyncio.run(self._transcribe_async(audio, settings.whisper_model))
            update_job_progress(db, job_id, progress=70, current_step="persist")

            # Replace existing transcript
            existing = db.query(Transcript).filter(Transcript.video_id == video_id).one_or_none()
            if existing:
                db.execute(delete(TranscriptWord).where(
                    TranscriptWord.segment_id.in_(
                        db.query(TranscriptSegment.id).filter(TranscriptSegment.transcript_id == existing.id)
                    )
                ))
                db.execute(delete(TranscriptSegment).where(TranscriptSegment.transcript_id == existing.id))
                db.execute(delete(Speaker).where(Speaker.transcript_id == existing.id))
                db.delete(existing)
                db.flush()

            transcript = Transcript(
                id=uuid4(),
                video_id=video_id,
                language=result.get("language"),
                text=result.get("text") or "",
                duration=result.get("duration"),
            )
            db.add(transcript)
            db.flush()

            speakers_seen: set[str] = set()
            for seg in result.get("segments", []):
                segment = TranscriptSegment(
                    id=uuid4(),
                    transcript_id=transcript.id,
                    start=float(seg["start"]),
                    end=float(seg["end"]),
                    speaker=seg.get("speaker"),
                    text=seg.get("text") or "",
                )
                db.add(segment)
                db.flush()
                if segment.speaker:
                    speakers_seen.add(segment.speaker)
                for w in seg.get("words", []):
                    db.add(
                        TranscriptWord(
                            id=uuid4(),
                            segment_id=segment.id,
                            word=w["word"],
                            start=float(w["start"]),
                            end=float(w["end"]),
                            confidence=w.get("probability"),
                            speaker=seg.get("speaker"),
                        )
                    )

            for label in sorted(speakers_seen):
                db.add(Speaker(id=uuid4(), transcript_id=transcript.id, speaker_label=label))

            db.commit()
            update_job_progress(
                db, job_id, status=JobStatus.COMPLETED, progress=100, current_step="transcript_ready"
            )
            logger.info(
                "transcription_complete",
                extra=log_extra(job_id=job_id, video_id=video_id, stage="transcription", progress=100),
            )
            return transcript
        except Exception as exc:
            logger.exception("transcription_failed")
            update_job_progress(
                db,
                job_id,
                status=JobStatus.FAILED,
                current_step="failed",
                error={
                    "error_code": "transcription_failed",
                    "message": str(exc),
                    "stage": "transcription",
                    "technical_details": repr(exc),
                },
            )
            raise

    async def _transcribe_async(self, audio: Path, model_size: str) -> dict[str, Any]:
        from app.services.gpu_manager import get_gpu_manager

        gpu = get_gpu_manager()
        async with gpu.acquire("whisper"):
            return await asyncio.to_thread(self._transcribe_sync, audio, model_size)

    def _transcribe_sync(self, audio: Path, model_size: str) -> dict[str, Any]:
        from faster_whisper import WhisperModel

        mm = get_model_manager()
        # Prefer smaller model if large-v3 OOM on 8GB — still honor config with fallback
        device, compute_type = self._device_config()
        model_name = model_size

        def loader() -> Any:
            try:
                return WhisperModel(model_name, device=device, compute_type=compute_type)
            except Exception:
                # Fallback to tiny for constrained environments / missing CUDA
                logger.warning("whisper_load_failed_fallback_tiny")
                return WhisperModel("tiny", device="cpu", compute_type="int8")

        # Unload other models first
        for name in list(mm.loaded_names()):
            if name != "whisper":
                mm.unload_model(name)

        model = mm.load_model("whisper", loader=loader)
        segments_iter, info = model.transcribe(
            str(audio),
            word_timestamps=True,
            vad_filter=True,
        )

        segments: list[dict[str, Any]] = []
        texts: list[str] = []
        for seg in segments_iter:
            words = []
            for w in seg.words or []:
                words.append(
                    {
                        "word": (w.word or "").strip(),
                        "start": float(w.start),
                        "end": float(w.end),
                        "probability": float(getattr(w, "probability", 0.0) or 0.0),
                    }
                )
            text = (seg.text or "").strip()
            texts.append(text)
            segments.append(
                {
                    "start": float(seg.start),
                    "end": float(seg.end),
                    "text": text,
                    "speaker": None,
                    "words": [w for w in words if w["word"]],
                }
            )

        # Optional pyannote diarization
        try:
            segments = self._maybe_diarize(audio, segments)
        except Exception as exc:  # noqa: BLE001
            logger.warning("diarization_skipped: %s", exc)

        return {
            "language": getattr(info, "language", None),
            "duration": float(getattr(info, "duration", 0.0) or 0.0),
            "text": " ".join(texts).strip(),
            "segments": segments,
        }

    def _device_config(self) -> tuple[str, str]:
        settings = get_settings()
        if not settings.gpu_enabled:
            return "cpu", "int8"
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda", "int8_float16"
        except ImportError:
            pass
        return "cpu", "int8"

    def _maybe_diarize(self, audio: Path, segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        settings = get_settings()
        if not settings.hf_token:
            return segments
        try:
            from pyannote.audio import Pipeline  # type: ignore
        except ImportError:
            logger.info("pyannote_not_installed")
            return segments

        mm = get_model_manager()
        mm.unload_model("whisper")

        def loader() -> Any:
            pipe = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-community-1",
                use_auth_token=settings.hf_token,
            )
            try:
                import torch

                if torch.cuda.is_available() and settings.gpu_enabled:
                    pipe.to(torch.device("cuda"))
            except Exception:  # noqa: BLE001
                pass
            return pipe

        pipeline = mm.load_model("pyannote", loader=loader)
        diarization = pipeline(str(audio))
        turns: list[tuple[float, float, str]] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            turns.append((float(turn.start), float(turn.end), str(speaker)))

        for seg in segments:
            mid = (seg["start"] + seg["end"]) / 2
            label = None
            for s, e, sp in turns:
                if s <= mid <= e:
                    label = sp
                    break
            seg["speaker"] = label
        mm.unload_model("pyannote")
        return segments


def get_transcript_agent() -> TranscriptAgent:
    return TranscriptAgent()
