from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.ranking import OllamaProvider, get_ranking_service

logger = get_logger(__name__)

RANKING_VERSION = "virality_v1"

NEGATIVE_PHRASES = [
    "as i said before",
    "as i mentioned",
    "earlier",
    "previous part",
    "watch the previous",
    "in the last video",
    "like i said",
    "going back to",
    "continue from",
]

HOOK_CUES = [
    "secret",
    "why",
    "how",
    "never",
    "stop",
    "mistake",
    "truth",
    "warning",
    "shocking",
    "nobody",
    "everyone",
    "?",
]

PAYOFF_CUES = [
    "so",
    "therefore",
    "that's why",
    "result",
    "because",
    "finally",
    "in short",
    "bottom line",
    "!",
]


@dataclass
class RankedCandidate:
    id: str | None
    start: float
    end: float
    text: str
    features: dict[str, Any] = field(default_factory=dict)
    feature_scores: dict[str, float] = field(default_factory=dict)
    penalties: dict[str, float] = field(default_factory=dict)
    selection_reasons: list[str] = field(default_factory=list)
    final_score: float = 0.0
    ranking_version: str = RANKING_VERSION
    ranking_weights: dict[str, float] = field(default_factory=dict)
    source: str = "rule_based"
    rejected: bool = False
    reject_reason: str | None = None

    @property
    def duration(self) -> float:
        return max(0.1, self.end - self.start)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "final_score": self.final_score,
            "feature_scores": self.feature_scores,
            "penalties": self.penalties,
            "selection_reasons": self.selection_reasons,
            "ranking_version": self.ranking_version,
            "ranking_weights": self.ranking_weights,
            "source": self.source,
            "rejected": self.rejected,
            "reject_reason": self.reject_reason,
            "short_form_potential_score": self.final_score,
        }


class Ranker(ABC):
    """Swappable ranking backend. RuleBased now; LightGBM later."""

    @abstractmethod
    def score(self, candidate: RankedCandidate) -> RankedCandidate: ...


class RuleBasedRanker(Ranker):
    def __init__(self, weights: dict[str, float] | None = None) -> None:
        settings = get_settings()
        cfg = (settings.yaml_config.get("virality") or {}).get("weights") or {}
        legacy = (settings.yaml_config.get("ranking") or {}).get("weights") or {}
        self.weights = {
            "hook": 0.18,
            "curiosity": 0.10,
            "emotion": 0.10,
            "information": 0.08,
            "narrative": 0.12,
            "payoff": 0.12,
            "shareability": 0.08,
            "self_contained": 0.08,
            "visual": 0.07,
            "audio": 0.07,
            **legacy,
            **(weights or {}),
            **cfg,
        }
        # normalize known keys only
        keys = [
            "hook",
            "curiosity",
            "emotion",
            "information",
            "narrative",
            "payoff",
            "shareability",
            "self_contained",
            "visual",
            "audio",
        ]
        total = sum(float(self.weights.get(k, 0)) for k in keys) or 1.0
        self.weights = {k: float(self.weights.get(k, 0)) / total for k in keys}

    def score(self, candidate: RankedCandidate) -> RankedCandidate:
        text = candidate.text or ""
        feats = candidate.features or {}
        scores = self._feature_scores(text, feats, candidate.duration)
        penalties = self._penalties(text, feats, scores)
        weighted = sum(scores[k] * self.weights[k] for k in self.weights)
        penalty_total = sum(penalties.values())
        final = max(0.0, min(100.0, weighted - penalty_total))
        reasons = self._reasons(scores, penalties, text)

        candidate.feature_scores = {k: round(v, 2) for k, v in scores.items()}
        candidate.penalties = {k: round(v, 2) for k, v in penalties.items()}
        candidate.selection_reasons = reasons
        candidate.final_score = round(final, 2)
        candidate.ranking_version = RANKING_VERSION
        candidate.ranking_weights = dict(self.weights)
        candidate.source = "rule_based"
        return candidate

    def _feature_scores(self, text: str, feats: dict[str, Any], duration: float) -> dict[str, float]:
        lower = text.lower().strip()
        tokens = re.findall(r"[a-z0-9']+", lower)
        first = lower[:120]
        last = lower[-120:] if len(lower) > 120 else lower

        hook = 35.0
        if any(c in first for c in HOOK_CUES):
            hook += 25
        if first.endswith("?") or "?" in first[:80]:
            hook += 15
        if feats.get("strong_claim_count", 0):
            hook += min(20, float(feats["strong_claim_count"]) * 8)
        hook = min(100.0, hook + float(feats.get("hook_strength_features", 0)) * 0.15)

        curiosity = min(
            100.0,
            float(feats.get("question_count", 0)) * 18
            + float(feats.get("topic_density", 0)) * 40
            + (15 if "why" in tokens or "how" in tokens else 0),
        )
        emotion = min(
            100.0,
            float(feats.get("emotional_word_count", 0)) * 14
            + float(feats.get("exclamation_count", 0)) * 10
            + 20,
        )
        information = min(
            100.0,
            float(feats.get("words_per_second", 0)) * 22
            + float(feats.get("number_count", 0)) * 8
            + float(feats.get("specificity", feats.get("topic_density", 0.4))) * 35,
        )
        narrative = float(feats.get("narrative_completion", 50))
        if any(c in lower for c in ("because", "so ", "therefore", "but ", "however")):
            narrative = min(100.0, narrative + 15)
        if feats.get("narrative_arc"):
            # bonus if HOOK+PAYOFF present from LLM
            arc = feats["narrative_arc"]
            if isinstance(arc, dict):
                present = sum(1 for k in ("HOOK", "SETUP", "CONFLICT", "PAYOFF") if arc.get(k))
                narrative = min(100.0, narrative + present * 8)

        payoff = float(feats.get("payoff_presence", 45))
        if any(c in last for c in PAYOFF_CUES):
            payoff = min(100.0, payoff + 20)
        if last.endswith((".", "!", "?")):
            payoff = min(100.0, payoff + 10)

        shareability = min(
            100.0,
            float(feats.get("strong_claim_count", 0)) * 12
            + float(feats.get("quotability_hint", 30))
            + (20 if len(tokens) < 90 else 5),
        )
        self_contained = float(feats.get("self_contained", 50))
        if not any(p in lower for p in NEGATIVE_PHRASES):
            self_contained = min(100.0, self_contained + 10)

        visual = min(100.0, 35 + float(feats.get("scene_changes", 0)) * 12 + float(feats.get("face_score", 20)))
        audio = min(
            100.0,
            float(feats.get("rms_energy", 0)) * 180
            + float(feats.get("speech_density", 0.4)) * 55
            + float(feats.get("pitch_variation", 0)) * 20,
        )

        # duration suitability folded into narrative/payoff lightly
        if 15 <= duration <= 60:
            hook = min(100.0, hook + 5)
            payoff = min(100.0, payoff + 5)

        return {
            "hook": hook,
            "curiosity": curiosity,
            "emotion": emotion,
            "information": information,
            "narrative": narrative,
            "payoff": payoff,
            "shareability": shareability,
            "self_contained": self_contained,
            "visual": visual,
            "audio": audio,
            "ending_quality": float(feats.get("ending_quality", payoff)),
            "rewatch_potential": min(100.0, (hook + curiosity + payoff) / 3),
        }

    def _penalties(self, text: str, feats: dict[str, Any], scores: dict[str, float]) -> dict[str, float]:
        lower = text.lower()
        tokens = re.findall(r"[a-z0-9']+", lower)
        penalties: dict[str, float] = {}

        if scores["hook"] < 45:
            penalties["weak_opening"] = 12
        if float(feats.get("filler_ratio", 0)) > 0.12:
            penalties["filler"] = min(20.0, float(feats["filler_ratio"]) * 80)
        if any(p in lower for p in NEGATIVE_PHRASES):
            penalties["missing_context_reference"] = 25
        if not text.strip().endswith((".", "!", "?")):
            penalties["incomplete_sentence"] = 10
        if scores["payoff"] < 40:
            penalties["weak_payoff"] = 15
        if scores["self_contained"] < 40:
            penalties["context_dependency"] = 18
        if len(tokens) < 12:
            penalties["too_thin"] = 30
        if len(set(tokens)) < max(5, len(tokens) * 0.25):
            penalties["repetitive"] = 12
        # generic fluff
        generic = {"thing", "stuff", "basically", "actually", "really", "very"}
        if tokens and sum(1 for t in tokens if t in generic) / len(tokens) > 0.15:
            penalties["generic_statement"] = 10
        return penalties

    def _reasons(self, scores: dict[str, float], penalties: dict[str, float], text: str) -> list[str]:
        reasons: list[str] = []
        mapping = [
            ("hook", 70, "Strong opening claim"),
            ("curiosity", 65, "Creates curiosity"),
            ("emotion", 65, "Emotional intensity"),
            ("information", 65, "High information density"),
            ("narrative", 65, "Complete narrative"),
            ("payoff", 65, "Strong payoff"),
            ("shareability", 65, "Quotable / shareable"),
            ("self_contained", 65, "Self-contained"),
            ("visual", 60, "Visual interest"),
            ("audio", 60, "Strong audio energy"),
        ]
        for key, thr, label in mapping:
            if scores.get(key, 0) >= thr:
                reasons.append(label)
        if text.strip().endswith(("!", "?")):
            reasons.append("Punchy ending")
        if penalties:
            reasons.append("Applied quality penalties")
        return reasons[:8] or ["Borderline short-form potential"]


class LightGBMRanker(Ranker):
    """Future trained model stub — falls back to RuleBasedRanker until a model exists."""

    def __init__(self) -> None:
        self._fallback = RuleBasedRanker()

    def score(self, candidate: RankedCandidate) -> RankedCandidate:
        # Placeholder: when a model file exists, score pairwise/listwise here.
        out = self._fallback.score(candidate)
        out.source = "lightgbm_fallback_rule_based"
        return out


class ViralityEngine:
    """
    Short-form Potential pipeline:
    candidates → cheap filter → rule/LLM enrich → context expand → rank →
    dedupe → diversity → min-score gate
    """

    def __init__(self, ranker: Ranker | None = None) -> None:
        settings = get_settings()
        vcfg = settings.yaml_config.get("virality") or {}
        self.min_score = float(vcfg.get("min_short_form_score", 55))
        self.max_final = int(vcfg.get("max_final_clips", 5))
        self.cheap_cutoff = float(vcfg.get("cheap_filter_score", 35))
        self.enable_llm = bool(vcfg.get("enable_llm_semantic", True))
        self.enable_context_expand = bool(vcfg.get("enable_context_expansion", True))
        backend = (vcfg.get("ranker") or "rule_based").lower()
        if ranker is not None:
            self.ranker = ranker
        elif backend == "lightgbm":
            self.ranker = LightGBMRanker()
        else:
            self.ranker = RuleBasedRanker()
        self.ranking_service = get_ranking_service()

    def run(self, raw_candidates: list[dict[str, Any]]) -> list[RankedCandidate]:
        ranked: list[RankedCandidate] = []
        for raw in raw_candidates:
            cand = RankedCandidate(
                id=str(raw.get("id")) if raw.get("id") else None,
                start=float(raw["start"]),
                end=float(raw["end"]),
                text=raw.get("text") or "",
                features=dict(raw.get("features") or {}),
            )
            # cheap filter on preliminary deterministic score if present
            prelim = float(raw.get("deterministic_score") or raw.get("final_score") or 0)
            if prelim and prelim < self.cheap_cutoff and len(raw_candidates) > 3:
                cand.rejected = True
                cand.reject_reason = "cheap_filter"
                cand.final_score = prelim
                continue

            if self.enable_llm:
                cand = self._maybe_llm_enrich(cand)

            self.ranker.score(cand)
            ranked.append(cand)

        if self.enable_context_expand and ranked:
            ranked = self._context_expand(ranked, raw_candidates)

        # re-score expanded set already scored; keep best
        ranked.sort(key=lambda c: c.final_score, reverse=True)
        deduped = self._dedupe(ranked)
        diverse = self._diversity_select(deduped)

        survivors: list[RankedCandidate] = []
        for cand in diverse:
            if cand.final_score < self.min_score:
                cand.rejected = True
                cand.reject_reason = f"below_min_short_form_score_{self.min_score}"
                continue
            survivors.append(cand)
            if len(survivors) >= self.max_final:
                break

        # Safety: if everything filtered but we had candidates, keep the single best
        # only when it is not extremely weak
        if not survivors and ranked:
            best = max(ranked, key=lambda c: c.final_score)
            if best.final_score >= max(40.0, self.min_score - 15):
                best.rejected = False
                best.reject_reason = None
                best.selection_reasons = list(best.selection_reasons) + [
                    "Best available candidate (relaxed gate)"
                ]
                survivors = [best]
        return survivors

    def _maybe_llm_enrich(self, cand: RankedCandidate) -> RankedCandidate:
        provider = OllamaProvider()
        if not provider.healthy() or not provider.model_available():
            return cand
        prompt = f"""You are a short-form producer. Analyze this clip transcript.
Return JSON only:
{{
  "hook": 0-100,
  "curiosity": 0-100,
  "emotion": 0-100,
  "information_density": 0-100,
  "quotability": 0-100,
  "self_contained": 0-100,
  "surprise": 0-100,
  "debate": 0-100,
  "payoff": 0-100,
  "short_form": 0-100,
  "overall": 0-100,
  "reason": "one sentence",
  "narrative_arc": {{
    "HOOK": true/false,
    "SETUP": true/false,
    "CONFLICT": true/false,
    "ESCALATION": true/false,
    "TURN": true/false,
    "PAYOFF": true/false,
    "CONCLUSION": true/false
  }}
}}
Do NOT claim the clip will go viral. Score short-form potential only.

Transcript:
\"\"\"{cand.text[:3500]}\"\"\"
"""
        try:
            data = provider.generate_json(prompt)
            cand.features["llm_semantic"] = data
            cand.features["narrative_arc"] = data.get("narrative_arc") or {}
            if "overall" in data:
                # light blend into features for rule ranker
                cand.features["payoff_presence"] = float(data.get("payoff", cand.features.get("payoff_presence", 50)))
                cand.features["self_contained"] = float(
                    data.get("self_contained", cand.features.get("self_contained", 50))
                )
                cand.features["quotability_hint"] = float(data.get("quotability", 40))
                cand.features["hook_strength_features"] = float(data.get("hook", 50))
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm_enrich_skipped: %s", exc)
        return cand

    def _context_expand(
        self, ranked: list[RankedCandidate], universe: list[dict[str, Any]]
    ) -> list[RankedCandidate]:
        """Around top moments, prefer windows with better narrative completeness."""
        if not ranked:
            return ranked
        top = ranked[: min(5, len(ranked))]
        expanded = list(ranked)
        for seed in top:
            center = (seed.start + seed.end) / 2
            for back, forward in ((25, 20), (20, 30), (15, 35), (10, 40)):
                start = max(0.0, center - back)
                end = center + forward
                # find closest existing candidate window text from universe
                nearest = min(
                    universe,
                    key=lambda u: abs(((float(u["start"]) + float(u["end"])) / 2) - center),
                    default=None,
                )
                if not nearest:
                    continue
                # use overlapping text if window similar
                text = nearest.get("text") or seed.text
                trial = RankedCandidate(
                    id=None,
                    start=start,
                    end=end,
                    text=text,
                    features=dict(seed.features),
                )
                self.ranker.score(trial)
                if trial.final_score > seed.final_score + 2:
                    trial.id = seed.id
                    trial.selection_reasons = list(trial.selection_reasons) + [
                        "Context-expanded narrative window"
                    ]
                    expanded.append(trial)
        return expanded

    def _dedupe(self, items: list[RankedCandidate], iou_thresh: float = 0.5) -> list[RankedCandidate]:
        kept: list[RankedCandidate] = []
        for item in items:
            if any(
                self.ranking_service._iou(item.to_dict(), k.to_dict()) >= iou_thresh
                or self.ranking_service._text_sim(item.to_dict(), k.to_dict()) > 0.85
                for k in kept
            ):
                continue
            kept.append(item)
        return kept

    def _diversity_select(self, items: list[RankedCandidate]) -> list[RankedCandidate]:
        """Avoid near-identical topics/openings."""
        kept: list[RankedCandidate] = []
        openings: list[set[str]] = []
        for item in items:
            tokens = set(re.findall(r"[a-z0-9']+", (item.text or "").lower())[:12])
            if openings and any(len(tokens & op) / max(1, len(tokens | op)) > 0.7 for op in openings):
                continue
            kept.append(item)
            openings.append(tokens)
        return kept


def get_virality_engine() -> ViralityEngine:
    return ViralityEngine()
