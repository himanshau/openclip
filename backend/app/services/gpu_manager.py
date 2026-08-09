from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class GPUManager:
    """Serialize heavyweight GPU work for 8 GB VRAM machines."""

    def __init__(self, max_concurrent: int | None = None) -> None:
        settings = get_settings()
        limit = max_concurrent if max_concurrent is not None else settings.max_concurrent_gpu_jobs
        self._semaphore = asyncio.Semaphore(max(1, int(limit)))
        self._holder: str | None = None
        self._lock = asyncio.Lock()

    @property
    def holder(self) -> str | None:
        return self._holder

    @asynccontextmanager
    async def acquire(self, name: str) -> AsyncIterator[None]:
        logger.info("gpu_acquire_wait name=%s holder=%s", name, self._holder)
        async with self._semaphore:
            async with self._lock:
                self._holder = name
            logger.info("gpu_acquired name=%s", name)
            try:
                yield
            finally:
                async with self._lock:
                    if self._holder == name:
                        self._holder = None
                logger.info("gpu_released name=%s", name)


_gpu_manager: GPUManager | None = None


def get_gpu_manager() -> GPUManager:
    global _gpu_manager
    if _gpu_manager is None:
        _gpu_manager = GPUManager()
    return _gpu_manager
