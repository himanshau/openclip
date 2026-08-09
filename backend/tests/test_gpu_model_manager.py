from __future__ import annotations

import pytest

from app.services.gpu_manager import GPUManager
from app.services.model_manager import ModelManager


@pytest.mark.asyncio
async def test_gpu_manager_acquire():
    mgr = GPUManager(max_concurrent=1)
    assert mgr.holder is None
    async with mgr.acquire("whisper"):
        assert mgr.holder == "whisper"
    assert mgr.holder is None


def test_model_manager_lifecycle():
    mm = ModelManager()
    assert not mm.is_loaded("demo")
    mm.load_model("demo", loader=lambda: {"ok": True})
    assert mm.is_loaded("demo")
    assert mm.get_model("demo")["ok"] is True
    mm.unload_model("demo")
    assert not mm.is_loaded("demo")

    with pytest.raises(RuntimeError):
        mm.load_model("missing")
