#!/usr/bin/env python3
"""Check OpenClip host environment. Does not download models."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(cmd: list[str]) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
        text = (out.stdout or out.stderr or "").strip()
        return text.splitlines()[0] if text else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    report: dict = {
        "python": sys.version.split()[0],
        "ffmpeg": _has("ffmpeg"),
        "ffprobe": _has("ffprobe"),
        "docker": _has("docker"),
        "nvidia_smi": _has("nvidia-smi"),
        "repo_root": str(root),
        "config_yaml": (root / "config.yaml").exists(),
        "env_example": (root / ".env.example").exists(),
        "storage_root": (root / "storage").exists(),
        "missing": [],
    }

    if report["ffmpeg"]:
        report["ffmpeg_version"] = _run(["ffmpeg", "-version"])
    else:
        report["missing"].append("ffmpeg")

    if not report["ffprobe"]:
        report["missing"].append("ffprobe")

    if report["nvidia_smi"]:
        report["gpu_line"] = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
    else:
        report["missing"].append("nvidia-smi (optional for Phase 1)")

    print(json.dumps(report, indent=2))
    # Phase 1: FFmpeg optional; exit 0 always after reporting
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
