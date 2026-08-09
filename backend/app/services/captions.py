from __future__ import annotations

from typing import Any

from app.models import TranscriptWord


class CaptionService:
    PRESETS = {
        "classic": {"fontsize": 48, "primary": "&H00FFFFFF", "outline": 3, "bold": 0},
        "minimal": {"fontsize": 42, "primary": "&H00FFFFFF", "outline": 2, "bold": 0},
        "bold": {"fontsize": 56, "primary": "&H0000FFFF", "outline": 4, "bold": 1},
        "karaoke": {"fontsize": 52, "primary": "&H0000FFFF", "outline": 3, "bold": 1},
        "neon": {"fontsize": 52, "primary": "&H00FF00FF", "outline": 4, "bold": 1},
        "box": {"fontsize": 48, "primary": "&H00FFFFFF", "outline": 0, "bold": 1, "borderstyle": 3},
        "clean": {"fontsize": 46, "primary": "&H00FFFFFF", "outline": 2, "bold": 0},
    }

    def build_events(
        self,
        words: list[TranscriptWord] | list[dict[str, Any]],
        *,
        start_offset: float,
        end_limit: float,
        max_words: int = 5,
    ) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        for w in words:
            if hasattr(w, "start"):
                ws, we, text = float(w.start), float(w.end), w.word
            else:
                ws, we, text = float(w["start"]), float(w["end"]), w["word"]
            if we < start_offset or ws > end_limit:
                continue
            selected.append(
                {
                    "start": max(0.0, ws - start_offset),
                    "end": max(0.05, we - start_offset),
                    "text": text,
                }
            )
        events: list[dict[str, Any]] = []
        buf: list[dict[str, Any]] = []
        for item in selected:
            buf.append(item)
            if len(buf) >= max_words:
                events.append(
                    {
                        "start": buf[0]["start"],
                        "end": buf[-1]["end"],
                        "text": " ".join(x["text"] for x in buf),
                    }
                )
                buf = []
        if buf:
            events.append(
                {
                    "start": buf[0]["start"],
                    "end": buf[-1]["end"],
                    "text": " ".join(x["text"] for x in buf),
                }
            )
        return events

    def to_ass(self, events: list[dict[str, Any]], preset: str = "bold") -> str:
        style = self.PRESETS.get(preset, self.PRESETS["bold"])
        borderstyle = style.get("borderstyle", 1)
        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{style['fontsize']},{style['primary']},&H000000FF,&H00000000,&H80000000,{style['bold']},0,0,0,100,100,0,0,{borderstyle},{style['outline']},1,2,40,40,160,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        lines = [header]
        for ev in events:
            lines.append(
                f"Dialogue: 0,{self._ts(ev['start'])},{self._ts(ev['end'])},Default,,0,0,0,,{ev['text']}"
            )
        return "\n".join(lines)

    @staticmethod
    def _ts(seconds: float) -> str:
        s = max(0.0, float(seconds))
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sec = s % 60
        return f"{h}:{m:02d}:{sec:05.2f}"


def get_caption_service() -> CaptionService:
    return CaptionService()
