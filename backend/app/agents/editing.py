from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import cv2
import numpy as np
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import Candidate, Clip, JobStatus, Transcript, TranscriptSegment, TranscriptWord, Video
from app.services.captions import get_caption_service
from app.services.job_service import update_job_progress
from app.services.storage import get_storage

logger = get_logger(__name__)

FILLERS = {"um", "uh", "erm", "ah", "like"}


class EditingAgent:
    def process(
        self,
        db: Session,
        video_id: UUID,
        job_id: UUID,
        *,
        top_n: int = 5,
        caption_preset: str = "bold",
        smart_cut: bool = True,
    ) -> list[Clip]:
        video = db.get(Video, video_id)
        if video is None:
            raise ValueError("video missing")
        settings = get_settings()
        min_score = float((settings.yaml_config.get("virality") or {}).get("min_short_form_score", 55))
        candidates = (
            db.query(Candidate)
            .filter(Candidate.video_id == video_id)
            .filter(Candidate.final_score.isnot(None))
            .filter(Candidate.final_score >= min_score)
            .order_by(Candidate.final_score.desc().nullslast())
            .limit(top_n)
            .all()
        )
        # If virality gate left none (edge case), take top ranked anyway but still prefer score order
        if not candidates:
            candidates = (
                db.query(Candidate)
                .filter(Candidate.video_id == video_id)
                .order_by(Candidate.final_score.desc().nullslast())
                .limit(min(2, top_n))
                .all()
            )
        update_job_progress(db, job_id, status=JobStatus.RUNNING, progress=10, current_step="edit_plans")

        # clear previous planned clips without renders? keep simple: delete planned
        for old in db.query(Clip).filter(Clip.video_id == video_id, Clip.status == "planned").all():
            db.delete(old)
        db.flush()

        storage = get_storage()
        source = storage.absolute(video.proxy_path or video.original_path or "")
        transcript = db.query(Transcript).filter(Transcript.video_id == video_id).one_or_none()
        words: list[TranscriptWord] = []
        if transcript:
            words = (
                db.query(TranscriptWord)
                .join(TranscriptSegment)
                .filter(TranscriptSegment.transcript_id == transcript.id)
                .order_by(TranscriptWord.start)
                .all()
            )

        clips: list[Clip] = []
        for idx, cand in enumerate(candidates):
            crop = self._compute_crop(source, video, cand.start, cand.end)
            drop_ranges = self._smart_cut_ranges(words, cand.start, cand.end) if smart_cut else []
            caption_events = get_caption_service().build_events(
                words, start_offset=cand.start, end_limit=cand.end
            )
            plan = {
                "clip_index": idx,
                "start": cand.start,
                "end": cand.end,
                "aspect_ratio": "9:16",
                "target": {"width": 1080, "height": 1920},
                "crop": crop,
                "caption_style": caption_preset,
                "caption_events": caption_events,
                "smart_cut": smart_cut,
                "drop_ranges": drop_ranges,
                "zoom_events": [],
                "speaker": None,
            }
            reasons = []
            if isinstance(cand.llm_score, dict):
                reasons = cand.llm_score.get("selection_reasons") or []
            if not reasons and isinstance(cand.features, dict):
                reasons = cand.features.get("selection_reasons") or []
            breakdown = dict(cand.llm_score or {})
            if not breakdown and isinstance(cand.features, dict):
                breakdown = dict(cand.features.get("feature_scores") or cand.features.get("breakdown") or {})
            breakdown["selection_reasons"] = reasons
            breakdown["short_form_potential_score"] = cand.final_score
            clip = Clip(
                id=uuid4(),
                video_id=video_id,
                candidate_id=cand.id,
                title=(cand.text[:80] + "…") if len(cand.text) > 80 else cand.text,
                start=cand.start,
                end=cand.end,
                score=cand.final_score,
                score_breakdown=breakdown,
                edit_plan=plan,
                status="planned",
            )
            db.add(clip)
            clips.append(clip)

        db.commit()
        update_job_progress(db, job_id, status=JobStatus.COMPLETED, progress=100, current_step="edit_plans_ready")
        return clips

    def _compute_crop(self, source_path, video: Video, start: float, end: float) -> dict[str, Any]:
        width = int(video.width or 1280)
        height = int(video.height or 720)
        target_aspect = 9 / 16
        crop_h = height
        crop_w = int(crop_h * target_aspect)
        if crop_w > width:
            crop_w = width
            crop_h = int(crop_w / target_aspect)
        center_x = width / 2
        center_y = height / 2

        # Sample a few frames for faces
        try:
            cap = cv2.VideoCapture(str(source_path))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            xs: list[float] = []
            cascade = None
            if hasattr(cv2, "CascadeClassifier") and hasattr(cv2, "data"):
                cascade = cv2.CascadeClassifier(
                    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                )
            for t in np.linspace(start, max(start, end - 0.1), num=8):
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
                ok, frame = cap.read()
                if not ok:
                    continue
                if cascade is not None and not cascade.empty():
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = cascade.detectMultiScale(gray, 1.1, 4)
                    if len(faces):
                        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                        xs.append(x + w / 2)
            cap.release()
            if xs:
                ema = xs[0]
                for x in xs[1:]:
                    ema = 0.7 * ema + 0.3 * x
                center_x = float(ema)
        except Exception as exc:  # noqa: BLE001
            logger.warning("face_track_fallback: %s", exc)

        crop_x = int(max(0, min(width - crop_w, center_x - crop_w / 2)))
        crop_y = int(max(0, min(height - crop_h, center_y - crop_h / 2)))
        return {
            "x": crop_x,
            "y": crop_y,
            "w": int(crop_w),
            "h": int(crop_h),
            "mode": "face" if center_x != width / 2 else "center",
        }

    def _smart_cut_ranges(
        self, words: list[TranscriptWord], start: float, end: float
    ) -> list[list[float]]:
        drops: list[list[float]] = []
        selected = [w for w in words if w.start >= start and w.end <= end]
        # long gaps between words
        for a, b in zip(selected, selected[1:]):
            gap = b.start - a.end
            if gap >= 0.8:
                drops.append([round(a.end, 3), round(b.start, 3)])
        # filler words — mark but do not over-delete
        for w in selected:
            if w.word.lower().strip(".,!") in FILLERS and (w.end - w.start) < 0.45:
                drops.append([round(w.start, 3), round(w.end, 3)])
        # merge overlaps lightly
        drops.sort()
        merged: list[list[float]] = []
        for d in drops:
            if not merged or d[0] > merged[-1][1]:
                merged.append(d)
            else:
                merged[-1][1] = max(merged[-1][1], d[1])
        return merged[:20]


def get_editing_agent() -> EditingAgent:
    return EditingAgent()
