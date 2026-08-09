from app.services.captions import CaptionService
from app.services.ranking import RankingService


def test_deduplicate_keeps_higher_score():
    ranking = RankingService()
    items = [
        {"start": 0, "end": 30, "text": "hello world foo", "final_score": 40},
        {"start": 2, "end": 28, "text": "hello world foo bar", "final_score": 80},
        {"start": 100, "end": 130, "text": "totally different topic here", "final_score": 50},
    ]
    kept = ranking.deduplicate(items, iou_thresh=0.5)
    assert len(kept) == 2
    assert kept[0]["final_score"] == 80


def test_caption_ass_contains_dialogue():
    svc = CaptionService()
    events = [{"start": 0.0, "end": 1.2, "text": "Hello world"}]
    ass = svc.to_ass(events, "bold")
    assert "Dialogue:" in ass
    assert "Hello world" in ass
