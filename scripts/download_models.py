#!/usr/bin/env python3
"""Document model download commands. Does NOT download anything automatically."""

from __future__ import annotations

HELP = """
OpenClip model setup (manual — large downloads)

Whisper (faster-whisper caches on first use):
  # No separate download required; first transcription pulls weights.

Ollama + Qwen3-4B:
  ollama pull qwen3:4b

Optional Qwen-VL (NOT required for MVP):
  ollama pull qwen3-vl:4b

pyannote Community-1 (requires HF account + accepted terms + HF_TOKEN):
  huggingface-cli login
  # Then download per pyannote docs when Phase 3 is implemented.

This script never downloads models. Set HF_TOKEN in .env only when needed.
"""


def main() -> int:
    print(HELP.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
