from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings


class StorageService:
    """Local filesystem storage. DB stores paths only."""

    def __init__(self, root: Path | None = None) -> None:
        settings = get_settings()
        self.root = (root or settings.storage_root).resolve()
        self._ensure_layout()

    def _ensure_layout(self) -> None:
        for name in (
            "projects",
            "videos",
            "audio",
            "proxies",
            "transcripts",
            "scenes",
            "candidates",
            "clips",
            "renders",
            "thumbnails",
            "cache",
        ):
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def video_dir(self, video_id: UUID | str) -> Path:
        path = self.root / "videos" / str(video_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def path(self, *parts: str) -> Path:
        path = self.root.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def relative(self, absolute: Path) -> str:
        try:
            return str(absolute.resolve().relative_to(self.root))
        except ValueError:
            return str(absolute)

    def absolute(self, stored: str) -> Path:
        p = Path(stored)
        if p.is_absolute():
            return p
        return (self.root / p).resolve()

    @staticmethod
    def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def save_upload(self, video_id: UUID, filename: str, data: bytes) -> Path:
        safe = Path(filename).name
        dest = self.video_dir(video_id) / f"original_{safe}"
        dest.write_bytes(data)
        return dest

    def copy_into(self, video_id: UUID, src: Path, dest_name: str) -> Path:
        dest = self.video_dir(video_id) / dest_name
        shutil.copy2(src, dest)
        return dest


_storage: StorageService | None = None


def get_storage() -> StorageService:
    global _storage
    if _storage is None:
        _storage = StorageService()
    return _storage
