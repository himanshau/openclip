from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class FFmpegError(RuntimeError):
    def __init__(self, message: str, *, stderr: str | None = None) -> None:
        super().__init__(message)
        self.stderr = stderr


class FFmpegService:
    def __init__(self) -> None:
        settings = get_settings()
        self.ffmpeg = settings.ffmpeg_path
        self.ffprobe = settings.ffprobe_path

    def available(self) -> bool:
        return shutil.which(self.ffmpeg) is not None and shutil.which(self.ffprobe) is not None

    def _run(self, args: list[str], *, timeout: int = 600) -> subprocess.CompletedProcess[str]:
        logger.info("ffmpeg_cmd %s", " ".join(args))
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise FFmpegError(f"Command timed out: {args[0]}") from exc
        if proc.returncode != 0:
            raise FFmpegError(
                f"Command failed ({proc.returncode}): {args[0]}",
                stderr=proc.stderr,
            )
        return proc

    def probe(self, path: Path) -> dict[str, Any]:
        args = [
            self.ffprobe,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        proc = self._run(args, timeout=60)
        return json.loads(proc.stdout or "{}")

    def extract_metadata(self, path: Path) -> dict[str, Any]:
        data = self.probe(path)
        video_stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
            None,
        )
        audio_stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "audio"),
            None,
        )
        fmt = data.get("format") or {}
        duration = float(fmt.get("duration") or 0)
        fps = None
        if video_stream and video_stream.get("avg_frame_rate"):
            num, _, den = video_stream["avg_frame_rate"].partition("/")
            try:
                fps = float(num) / float(den or 1)
            except (TypeError, ValueError, ZeroDivisionError):
                fps = None
        return {
            "duration": duration,
            "width": int(video_stream["width"]) if video_stream and video_stream.get("width") else None,
            "height": int(video_stream["height"]) if video_stream and video_stream.get("height") else None,
            "fps": fps,
            "codec": video_stream.get("codec_name") if video_stream else None,
            "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
            "has_audio": audio_stream is not None,
            "has_video": video_stream is not None,
            "raw": data,
        }

    def extract_audio(self, video_path: Path, audio_path: Path) -> Path:
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            [
                self.ffmpeg,
                "-y",
                "-i",
                str(video_path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                str(audio_path),
            ]
        )
        return audio_path

    def generate_proxy(self, video_path: Path, proxy_path: Path, height: int = 720) -> Path:
        proxy_path.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            [
                self.ffmpeg,
                "-y",
                "-i",
                str(video_path),
                "-vf",
                f"scale=-2:{height}",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "28",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                str(proxy_path),
            ]
        )
        return proxy_path

    def generate_thumbnail(self, video_path: Path, thumb_path: Path, at_seconds: float = 1.0) -> Path:
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            [
                self.ffmpeg,
                "-y",
                "-ss",
                str(max(0.0, at_seconds)),
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(thumb_path),
            ],
            timeout=60,
        )
        return thumb_path

    def has_nvenc(self) -> bool:
        try:
            proc = subprocess.run(
                [self.ffmpeg, "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            return "h264_nvenc" in (proc.stdout or "")
        except (OSError, subprocess.TimeoutExpired):
            return False

    def render_vertical_clip(
        self,
        *,
        source: Path,
        output: Path,
        start: float,
        end: float,
        crop_x: int,
        crop_y: int,
        crop_w: int,
        crop_h: int,
        width: int = 1080,
        height: int = 1920,
        ass_path: Path | None = None,
        prefer_nvenc: bool = True,
    ) -> Path:
        output.parent.mkdir(parents=True, exist_ok=True)
        duration = max(0.1, end - start)
        vf_parts = [
            f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}",
            f"scale={width}:{height}:force_original_aspect_ratio=decrease",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        ]
        if ass_path is not None:
            # Escape path for FFmpeg filter on Windows
            ass = str(ass_path).replace("\\", "/").replace(":", "\\:")
            vf_parts.append(f"ass='{ass}'")
        vf = ",".join(vf_parts)

        video_codec = "h264_nvenc" if prefer_nvenc and self.has_nvenc() else "libx264"
        args = [
            self.ffmpeg,
            "-y",
            "-ss",
            str(start),
            "-i",
            str(source),
            "-t",
            str(duration),
            "-vf",
            vf,
            "-c:v",
            video_codec,
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output),
        ]
        if video_codec == "libx264":
            args[args.index("-c:v") + 1 : args.index("-c:v") + 1]  # no-op clarity
            # insert preset after codec
            idx = args.index(video_codec)
            args[idx + 1 : idx + 1] = ["-preset", "medium", "-crf", "20"]
        try:
            self._run(args, timeout=1800)
        except FFmpegError:
            if video_codec != "libx264":
                logger.warning("nvenc_failed_fallback_libx264")
                return self.render_vertical_clip(
                    source=source,
                    output=output,
                    start=start,
                    end=end,
                    crop_x=crop_x,
                    crop_y=crop_y,
                    crop_w=crop_w,
                    crop_h=crop_h,
                    width=width,
                    height=height,
                    ass_path=ass_path,
                    prefer_nvenc=False,
                )
            raise
        return output

    def validate_output(self, path: Path, *, expect_width: int = 1080, expect_height: int = 1920) -> dict[str, Any]:
        if not path.exists() or path.stat().st_size == 0:
            raise FFmpegError(f"Output missing or empty: {path}")
        meta = self.extract_metadata(path)
        if not meta["has_video"]:
            raise FFmpegError("Output has no video stream")
        if not meta["has_audio"]:
            raise FFmpegError("Output has no audio stream")
        if meta["width"] != expect_width or meta["height"] != expect_height:
            raise FFmpegError(
                f"Unexpected resolution {meta['width']}x{meta['height']} "
                f"(expected {expect_width}x{expect_height})"
            )
        return meta


_ffmpeg: FFmpegService | None = None


def get_ffmpeg() -> FFmpegService:
    global _ffmpeg
    if _ffmpeg is None:
        _ffmpeg = FFmpegService()
    return _ffmpeg
