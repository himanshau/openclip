from __future__ import annotations

import math
import re
from typing import Any
from uuid import UUID, uuid4

import numpy as np
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import Candidate, JobStatus, Scene, Transcript, TranscriptSegment, TranscriptWord, Video
from app.services.job_service import update_job_progress
from app.services.storage import get_storage

logger = get_logger(__name__)

EMOTIONAL = {
    "amazing", "incredible", "shocking", "love", "hate", "fear", "happy", "sad",
    "angry", "wow", "insane", "crazy", "best", "worst", "never", "always",
}
STRONG_CLAIMS = {"always", "never", "everyone", "nobody", "must", "prove", "fact", "truth"}
FILLERS = {"um", "uh", "like", "you", "know", "actually", "basically"}


class ClipDiscoveryAgent:
    def process(self, db: Session, video_id: UUID, job_id: UUID) -> list[Candidate]:
        settings = get_settings()
        video = db.get(Video, video_id)
        transcript = db.query(Transcript).filter(Transcript.video_id == video_id).one_or_none()
        if video is None or transcript is None:
            raise ValueError("Video/transcript required for clip discovery")

        try:
            update_job_progress(db, job_id, status=JobStatus.RUNNING, progress=10, current_step="scenes")
            self._detect_scenes(db, video)

            update_job_progress(db, job_id, progress=30, current_step="candidates")
            words = (
                db.query(TranscriptWord)
                .join(TranscriptSegment)
                .filter(TranscriptSegment.transcript_id == transcript.id)
                .order_by(TranscriptWord.start)
                .all()
            )
            segments = (
                db.query(TranscriptSegment)
                .filter(TranscriptSegment.transcript_id == transcript.id)
                .order_by(TranscriptSegment.start)
                .all()
            )
            scenes = db.query(Scene).filter(Scene.video_id == video_id).all()
            audio_feats = self._audio_features(video)

            cfg = settings.yaml_config.get("candidate") or {}
            min_d = float(cfg.get("min_duration", 20))
            max_d = float(cfg.get("max_duration", 60))
            targets = [float(x) for x in cfg.get("target_durations", [15, 20, 30, 45, 60])]
            duration = float(video.duration or 0)
            if duration and duration < min_d:
                min_d = max(5.0, duration * 0.25)
                max_d = max(min_d + 1.0, duration)
                targets = [t for t in targets if t <= max_d] or [min_d, max_d]

            raw = self._generate_candidates(segments, words, scenes, targets, min_d, max_d)
            update_job_progress(db, job_id, progress=60, current_step="scoring")

            db.execute(delete(Candidate).where(Candidate.video_id == video_id))
            db.flush()

            weights = (settings.yaml_config.get("ranking") or {}).get("weights") or {}
            candidates: list[Candidate] = []
            for item in raw:
                feats = self._text_features(item["text"], item["start"], item["end"])
                feats.update(self._structural_features(item["text"]))
                feats.update(audio_feats)
                feats["scene_changes"] = self._scene_changes(scenes, item["start"], item["end"])
                score, breakdown = self._deterministic_score(feats, weights, item["end"] - item["start"], min_d, max_d)
                cand = Candidate(
                    id=uuid4(),
                    video_id=video_id,
                    start=item["start"],
                    end=item["end"],
                    text=item["text"],
                    features={**feats, "breakdown": breakdown},
                    deterministic_score=score,
                    final_score=score,
                )
                db.add(cand)
                candidates.append(cand)

            db.commit()
            update_job_progress(
                db, job_id, status=JobStatus.COMPLETED, progress=100, current_step="candidates_ready"
            )
            return candidates
        except Exception as exc:
            logger.exception("clip_discovery_failed")
            update_job_progress(
                db,
                job_id,
                status=JobStatus.FAILED,
                current_step="failed",
                error={
                    "error_code": "clip_discovery_failed",
                    "message": str(exc),
                    "stage": "clip_discovery",
                    "technical_details": repr(exc),
                },
            )
            raise

    def _detect_scenes(self, db: Session, video: Video) -> None:
        storage = get_storage()
        source = storage.absolute(video.proxy_path or video.original_path or "")
        db.execute(delete(Scene).where(Scene.video_id == video.id))
        db.flush()
        try:
            from scenedetect import ContentDetector, detect

            scene_list = detect(str(source), ContentDetector(threshold=27.0))
            if not scene_list:
                db.add(Scene(id=uuid4(), video_id=video.id, start=0.0, end=float(video.duration or 0), score=0))
            else:
                for start_tc, end_tc in scene_list:
                    db.add(
                        Scene(
                            id=uuid4(),
                            video_id=video.id,
                            start=start_tc.get_seconds(),
                            end=end_tc.get_seconds(),
                            score=1.0,
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("scene_detect_fallback: %s", exc)
            db.add(Scene(id=uuid4(), video_id=video.id, start=0.0, end=float(video.duration or 0), score=0))
        db.commit()

    def _generate_candidates(
        self,
        segments: list[TranscriptSegment],
        words: list[TranscriptWord],
        scenes: list[Scene],
        targets: list[float],
        min_d: float,
        max_d: float,
    ) -> list[dict[str, Any]]:
        if not segments:
            return []
        boundaries = sorted(
            {float(s.start) for s in segments}
            | {float(s.end) for s in segments}
            | {float(sc.start) for sc in scenes}
            | {float(sc.end) for sc in scenes}
        )
        # sentence-ish starts
        starts = [float(s.start) for s in segments]
        out: list[dict[str, Any]] = []
        seen: set[tuple[float, float]] = set()
        for start in starts:
            for target in targets:
                end = self._snap_end(start + target, boundaries, words, max_d)
                dur = end - start
                if dur < min_d * 0.8 or dur > max_d * 1.2:
                    continue
                key = (round(start, 2), round(end, 2))
                if key in seen:
                    continue
                seen.add(key)
                text = self._text_between(words, start, end)
                if len(text.split()) < 8:
                    continue
                out.append({"start": start, "end": end, "text": text})
        if not out and segments:
            start = float(segments[0].start)
            end = float(segments[-1].end)
            text = self._text_between(words, start, end) or " ".join(s.text for s in segments)
            if end > start:
                out.append({"start": start, "end": min(end, start + max_d), "text": text})
        return out

    def _snap_end(
        self, desired: float, boundaries: list[float], words: list[TranscriptWord], max_d: float
    ) -> float:
        if not words:
            return desired
        # Prefer end at word boundary near desired
        best = min(words, key=lambda w: abs(w.end - desired))
        end = float(best.end)
        # also snap to nearest segment/scene boundary if closer
        if boundaries:
            b = min(boundaries, key=lambda x: abs(x - desired))
            if abs(b - desired) < abs(end - desired):
                end = b
        return end

    def _text_between(self, words: list[TranscriptWord], start: float, end: float) -> str:
        return " ".join(w.word for w in words if w.start >= start - 0.05 and w.end <= end + 0.05)

    def _text_features(self, text: str, start: float, end: float) -> dict[str, Any]:
        tokens = re.findall(r"[A-Za-z0-9']+", text.lower())
        dur = max(0.1, end - start)
        sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
        return {
            "word_count": len(tokens),
            "sentence_count": max(1, len(sentences)),
            "words_per_second": len(tokens) / dur,
            "average_sentence_length": len(tokens) / max(1, len(sentences)),
            "question_count": text.count("?"),
            "exclamation_count": text.count("!"),
            "number_count": len(re.findall(r"\d+", text)),
            "strong_claim_count": sum(1 for t in tokens if t in STRONG_CLAIMS),
            "emotional_word_count": sum(1 for t in tokens if t in EMOTIONAL),
            "filler_ratio": sum(1 for t in tokens if t in FILLERS) / max(1, len(tokens)),
            "topic_density": len(set(tokens)) / max(1, len(tokens)),
        }

    def _structural_features(self, text: str) -> dict[str, Any]:
        first = (text[:80] or "").lower()
        hook = 50.0
        if any(x in first for x in ("?", "secret", "why", "how", "never", "stop")):
            hook += 25
        if text.strip().endswith((".", "!", "?")):
            ending = 70.0
        else:
            ending = 40.0
        return {
            "hook_strength_features": hook,
            "self_contained": 60.0 if len(text.split()) > 20 else 35.0,
            "narrative_completion": ending,
            "beginning_quality": hook,
            "ending_quality": ending,
            "payoff_presence": 55.0 + (10 if "!" in text or "?" in text else 0),
            "context_dependency": 40.0,
        }

    def _audio_features(self, video: Video) -> dict[str, Any]:
        storage = get_storage()
        defaults = {
            "rms_energy": 0.0,
            "volume": 0.0,
            "pitch_variation": 0.0,
            "silence_duration": 0.0,
            "speech_density": 0.5,
            "pause_frequency": 0.0,
        }
        if not video.audio_path:
            return defaults
        try:
            import librosa

            path = storage.absolute(video.audio_path)
            y, sr = librosa.load(str(path), sr=16000, mono=True)
            rms = float(np.sqrt(np.mean(y**2)))
            intervals = librosa.effects.split(y, top_db=30)
            speech = sum((e - s) for s, e in intervals) / max(1, len(y))
            return {
                "rms_energy": rms,
                "volume": rms,
                "pitch_variation": float(np.std(y)),
                "silence_duration": 1.0 - speech,
                "speech_density": speech,
                "pause_frequency": float(max(0, len(intervals) - 1) / max(0.1, len(y) / sr)),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("audio_features_failed: %s", exc)
            return defaults

    def _scene_changes(self, scenes: list[Scene], start: float, end: float) -> int:
        return sum(1 for s in scenes if start < s.start < end)

    def _deterministic_score(
        self,
        feats: dict[str, Any],
        weights: dict[str, float],
        duration: float,
        min_d: float,
        max_d: float,
    ) -> tuple[float, dict[str, float]]:
        hook = float(feats.get("hook_strength_features", 50))
        curiosity = min(100.0, feats.get("question_count", 0) * 20 + feats.get("topic_density", 0) * 50)
        emotion = min(100.0, feats.get("emotional_word_count", 0) * 15 + feats.get("exclamation_count", 0) * 10)
        info = min(100.0, feats.get("words_per_second", 0) * 25 + feats.get("number_count", 0) * 5)
        self_contained = float(feats.get("self_contained", 50))
        visual = min(100.0, 40 + feats.get("scene_changes", 0) * 15)
        audio = min(100.0, feats.get("rms_energy", 0) * 200 + feats.get("speech_density", 0) * 50)
        quotability = min(100.0, feats.get("strong_claim_count", 0) * 20 + 30)
        # duration suitability
        if min_d <= duration <= max_d:
            dur_score = 90.0
        else:
            dur_score = max(0.0, 90.0 - abs(((min_d + max_d) / 2) - duration) * 2)

        components = {
            "hook": hook,
            "curiosity": curiosity,
            "emotional_impact": emotion,
            "information_density": info,
            "self_contained": self_contained,
            "visual_interest": visual,
            "audio_energy": audio,
            "quotability": quotability,
            "duration_suitability": dur_score,
        }
        default_w = {
            "hook": 0.25,
            "curiosity": 0.15,
            "emotional_impact": 0.15,
            "information_density": 0.10,
            "self_contained": 0.10,
            "visual_interest": 0.10,
            "audio_energy": 0.05,
            "quotability": 0.05,
            "duration_suitability": 0.05,
        }
        w = {**default_w, **{k: float(v) for k, v in weights.items()}}
        total_w = sum(w.values()) or 1.0
        score = sum(components[k] * w.get(k, 0) for k in components) / total_w
        # penalize fillers
        score *= max(0.5, 1.0 - float(feats.get("filler_ratio", 0)) * 0.8)
        return round(score, 2), {k: round(v, 2) for k, v in components.items()}


def get_clip_discovery_agent() -> ClipDiscoveryAgent:
    return ClipDiscoveryAgent()
