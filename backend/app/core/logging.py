from __future__ import annotations

import logging
import sys
from typing import Any


class ContextFilter(logging.Filter):
    """Ensure job/stage fields exist for structured log formatting."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key in ("job_id", "project_id", "video_id", "stage", "progress"):
            if not hasattr(record, key):
                setattr(record, key, "-")
        return True


def setup_logging(debug: bool = True) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s job_id=%(job_id)s project_id=%(project_id)s "
            "video_id=%(video_id)s stage=%(stage)s progress=%(progress)s %(message)s"
        )
    )
    handler.addFilter(ContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_extra(
    *,
    job_id: Any = "-",
    project_id: Any = "-",
    video_id: Any = "-",
    stage: str = "-",
    progress: Any = "-",
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "project_id": project_id,
        "video_id": video_id,
        "stage": stage,
        "progress": progress,
    }
