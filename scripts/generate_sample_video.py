#!/usr/bin/env python3
"""Generate a synthetic 16:9 sample video with spoken audio (no copyrighted media)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = (
    "Welcome to OpenClip. This is a demonstration of automatic short form clip generation. "
    "Here is a surprising fact. Most long videos hide their best moments. "
    "Why does this matter? Because creators need highlights fast. "
    "Never waste hours scrubbing timelines. Always let software find the payoff!"
)


def synthesize_wav(path: Path) -> None:
    # Prefer Windows SAPI
    if sys.platform.startswith("win"):
        ps = f"""
Add-Type -AssemblyName System.Speech
$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer
$speak.Rate = 0
$speak.SetOutputToWaveFile('{str(path).replace("'", "''")}')
$speak.Speak('{SCRIPT.replace("'", "''")}')
$speak.Dispose()
"""
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            check=True,
            capture_output=True,
            text=True,
        )
        if path.exists() and path.stat().st_size > 1000:
            return
    # Fallback: ffmpeg sine + anull (ASR may be weak)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=25",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(path),
        ],
        check=True,
    )


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    out = root / "storage" / "cache" / "sample.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "speech.wav"
        synthesize_wav(wav)
        # Probe duration
        # Create 16:9 color video matching audio length
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x1a5f7a:s=1280x720:r=30",
            "-i",
            str(wav),
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-vf",
            "drawtext=text='OpenClip Sample':fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2",
            str(out),
        ]
        # drawtext may fail without fonts — fallback without text
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x1a5f7a:s=1280x720:r=30",
                "-i",
                str(wav),
                "-shortest",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(out),
            ]
            subprocess.run(cmd, check=True)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
