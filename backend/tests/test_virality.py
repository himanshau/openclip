from app.services.ranker import RankedCandidate, RuleBasedRanker, ViralityEngine


def test_rule_ranker_penalizes_weak_context():
    ranker = RuleBasedRanker()
    weak = RankedCandidate(
        id="1",
        start=0,
        end=30,
        text="as I said before you need to watch the previous part um uh stuff",
        features={"filler_ratio": 0.2, "self_contained": 20, "hook_strength_features": 10},
    )
    strong = RankedCandidate(
        id="2",
        start=40,
        end=70,
        text="Why does this matter? Most creators waste hours. The result is simple: automate highlight discovery now!",
        features={
            "filler_ratio": 0.02,
            "self_contained": 80,
            "hook_strength_features": 80,
            "question_count": 1,
            "emotional_word_count": 1,
            "strong_claim_count": 1,
            "payoff_presence": 80,
            "narrative_completion": 80,
            "speech_density": 0.7,
            "rms_energy": 0.1,
            "scene_changes": 2,
        },
    )
    ranker.score(weak)
    ranker.score(strong)
    assert strong.final_score > weak.final_score
    assert strong.final_score >= 55
    assert any("payoff" in r.lower() or "opening" in r.lower() or "Self-contained" in r for r in strong.selection_reasons)


def test_virality_engine_filters_junk():
    engine = ViralityEngine()
    engine.enable_llm = False
    engine.enable_context_expand = False
    engine.min_score = 55
    raw = [
        {
            "id": "a",
            "start": 0,
            "end": 25,
            "text": "um uh like you know stuff basically",
            "features": {"filler_ratio": 0.4, "self_contained": 10},
            "deterministic_score": 20,
        },
        {
            "id": "b",
            "start": 30,
            "end": 60,
            "text": "Stop guessing which moments work. Here is the truth: strong hooks plus clear payoff keep viewers watching!",
            "features": {
                "filler_ratio": 0.01,
                "self_contained": 85,
                "hook_strength_features": 85,
                "question_count": 0,
                "strong_claim_count": 2,
                "payoff_presence": 85,
                "narrative_completion": 80,
                "speech_density": 0.8,
                "rms_energy": 0.12,
                "scene_changes": 1,
                "exclamation_count": 1,
            },
            "deterministic_score": 75,
        },
    ]
    kept = engine.run(raw)
    assert len(kept) >= 1
    assert all(k.final_score >= 40 for k in kept)
    assert any(k.id == "b" for k in kept)
