from __future__ import annotations

import json
import re
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ClipScore(BaseModel):
    hook: float
    curiosity: float
    emotion: float
    information_density: float
    quotability: float
    self_contained: float
    surprise: float
    debate: float
    payoff: float
    short_form: float
    overall: float
    reason: str = ""

    @field_validator(
        "hook",
        "curiosity",
        "emotion",
        "information_density",
        "quotability",
        "self_contained",
        "surprise",
        "debate",
        "payoff",
        "short_form",
        "overall",
    )
    @classmethod
    def _range(cls, v: float) -> float:
        if v < 0 or v > 100:
            raise ValueError("score must be 0-100")
        return float(v)


class LLMProvider(Protocol):
    def generate_text(self, prompt: str) -> str: ...
    def generate_json(self, prompt: str) -> dict[str, Any]: ...


class OllamaProvider:
    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.llm_model

    def healthy(self) -> bool:
        try:
            with httpx.Client(timeout=2.0) as client:
                return client.get(f"{self.base_url}/api/tags").status_code == 200
        except httpx.HTTPError:
            return False

    def model_available(self) -> bool:
        try:
            with httpx.Client(timeout=3.0) as client:
                r = client.get(f"{self.base_url}/api/tags")
                names = [m.get("name") for m in r.json().get("models", [])]
                return any(self.model in (n or "") for n in names)
        except httpx.HTTPError:
            return False

    def generate_text(self, prompt: str) -> str:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False, "format": "json"},
            )
            r.raise_for_status()
            return r.json().get("response") or ""

    def generate_json(self, prompt: str) -> dict[str, Any]:
        raw = self.generate_text(prompt)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))


RANK_PROMPT = """You are a professional short-form video producer.
Evaluate this candidate for short-form content potential.
Return JSON only with keys:
hook, curiosity, emotion, information_density, quotability, self_contained,
surprise, debate, payoff, short_form, overall, reason
All scores are numbers from 0 to 100.

Candidate transcript:
\"\"\"{text}\"\"\"
"""


class RankingService:
    def score_candidate_llm(self, text: str, deterministic: float) -> tuple[float, dict[str, Any], str]:
        """Returns final_score, llm_payload, source (llm|deterministic)."""
        provider = OllamaProvider()
        if not provider.healthy() or not provider.model_available():
            return deterministic, {"fallback": True, "reason": "ollama_unavailable"}, "deterministic"

        prompt = RANK_PROMPT.format(text=text[:4000])
        for attempt in range(2):
            try:
                data = provider.generate_json(
                    prompt if attempt == 0 else prompt + "\nRespond with STRICT JSON only."
                )
                score = ClipScore.model_validate(data)
                # blend 60% llm overall + 40% deterministic
                final = round(0.6 * score.overall + 0.4 * deterministic, 2)
                return final, score.model_dump(), "llm"
            except (ValidationError, httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
                logger.warning("llm_rank_attempt_failed %s: %s", attempt, exc)
        return deterministic, {"fallback": True, "reason": "invalid_llm_output"}, "deterministic"

    def deduplicate(self, items: list[dict[str, Any]], iou_thresh: float = 0.5) -> list[dict[str, Any]]:
        ranked = sorted(items, key=lambda x: float(x.get("final_score") or 0), reverse=True)
        kept: list[dict[str, Any]] = []
        for item in ranked:
            if any(self._iou(item, k) >= iou_thresh or self._text_sim(item, k) > 0.85 for k in kept):
                continue
            kept.append(item)
        return kept

    @staticmethod
    def _iou(a: dict[str, Any], b: dict[str, Any]) -> float:
        s1, e1 = float(a["start"]), float(a["end"])
        s2, e2 = float(b["start"]), float(b["end"])
        inter = max(0.0, min(e1, e2) - max(s1, s2))
        union = max(e1, e2) - min(s1, s2)
        return inter / union if union > 0 else 0.0

    @staticmethod
    def _text_sim(a: dict[str, Any], b: dict[str, Any]) -> float:
        ta = set(re.findall(r"[a-z0-9]+", (a.get("text") or "").lower()))
        tb = set(re.findall(r"[a-z0-9]+", (b.get("text") or "").lower()))
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)


def get_ranking_service() -> RankingService:
    return RankingService()
