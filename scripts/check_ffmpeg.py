#!/usr/bin/env python3
"""Verify FFmpeg / FFprobe are installed and runnable."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys


def _version(binary: str) -> dict:
    path = shutil.which(binary)
    if not path:
        return {"installed": False, "path": None, "version": None}
    try:
        out = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        first = (out.stdout or out.stderr or "").splitlines()
        return {
            "installed": True,
            "path": path,
            "version": first[0] if first else None,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"installed": False, "path": path, "error": str(exc)}


def main() -> int:
    report = {"ffmpeg": _version("ffmpeg"), "ffprobe": _version("ffprobe")}
    print(json.dumps(report, indent=2))
    ok = report["ffmpeg"]["installed"] and report["ffprobe"]["installed"]
    if not ok:
        print("FFmpeg/FFprobe missing — required from Phase 2 onward.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
