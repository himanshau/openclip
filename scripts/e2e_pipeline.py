#!/usr/bin/env python3
"""End-to-end pipeline test: sample video → playable 9:16 MP4."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Ensure backend imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

# Prefer tiny whisper for CI/dev machines during E2E
os.environ.setdefault("WHISPER_MODEL", "tiny")
os.environ.setdefault("CONFIG_PATH", str(ROOT / "config.yaml"))


def main() -> int:
    from app.core.config import get_settings
    from app.db.session import SessionLocal
    from app.models import Clip, JobType, ProcessingJob, Project, Video, VideoStatus, JobStatus
    from app.services.storage import get_storage
    from app.workers.tasks import process_video_pipeline
    from uuid import uuid4
    import subprocess

    get_settings.cache_clear()
    sample_script = ROOT / "scripts" / "generate_sample_video.py"
    subprocess.run([sys.executable, str(sample_script)], check=True)
    sample = ROOT / "storage" / "cache" / "sample.mp4"
    if not sample.exists():
        print("sample missing", file=sys.stderr)
        return 1

    db = SessionLocal()
    storage = get_storage()
    try:
        project = Project(id=uuid4(), name="E2E Sample")
        db.add(project)
        db.flush()
        video_id = uuid4()
        dest = storage.save_upload(video_id, "sample.mp4", sample.read_bytes())
        video = Video(
            id=video_id,
            project_id=project.id,
            filename="sample.mp4",
            original_path=storage.relative(dest),
            status=VideoStatus.UPLOADED,
        )
        db.add(video)
        job = ProcessingJob(
            id=uuid4(),
            type=JobType.VALIDATION,
            status=JobStatus.QUEUED,
            project_id=project.id,
            video_id=video.id,
            job_metadata={"pipeline": True},
        )
        db.add(job)
        db.commit()

        print("Running pipeline synchronously...")
        result = process_video_pipeline.run(str(video.id), str(job.id), 2)
        print("pipeline result:", result)

        db.refresh(job)
        clips = db.query(Clip).filter(Clip.video_id == video.id, Clip.status == "rendered").all()
        print(f"rendered clips: {len(clips)}")
        if not clips:
            print("No rendered clips", file=sys.stderr)
            return 2
        for clip in clips:
            path = storage.absolute(clip.render_path or "")
            print("checking", path)
            assert path.exists() and path.stat().st_size > 1000
            # ffprobe decode check
            proc = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of", "json", str(path)],
                capture_output=True,
                text=True,
                check=True,
            )
            print(proc.stdout)
            if "1920" not in proc.stdout or "1080" not in proc.stdout:
                print("unexpected resolution", file=sys.stderr)
                return 3
        print("E2E PASS")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
