from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class ModelManager:
    """Lifecycle for heavyweight models. Phase 1: registry only (no loads)."""

    def __init__(self) -> None:
        self._models: dict[str, Any] = {}

    def is_loaded(self, name: str) -> bool:
        return name in self._models

    def get_model(self, name: str) -> Any:
        if name not in self._models:
            raise KeyError(f"Model '{name}' is not loaded")
        return self._models[name]

    def load_model(self, name: str, loader: Any | None = None, **kwargs: Any) -> Any:
        if name in self._models:
            return self._models[name]
        if loader is None:
            raise RuntimeError(
                f"No loader provided for model '{name}'. "
                "Real model loading is implemented in later phases."
            )
        logger.info("loading_model name=%s", name)
        model = loader(**kwargs) if callable(loader) else loader
        self._models[name] = model
        return model

    def unload_model(self, name: str) -> None:
        if name not in self._models:
            return
        logger.info("unloading_model name=%s", name)
        model = self._models.pop(name)
        close = getattr(model, "close", None) or getattr(model, "cleanup", None)
        if callable(close):
            close()
        self.clear_gpu_memory()

    def clear_gpu_memory(self) -> None:
        try:
            import torch  # type: ignore

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("cuda_cache_cleared")
        except ImportError:
            pass

    def loaded_names(self) -> list[str]:
        return list(self._models.keys())


_model_manager: ModelManager | None = None


def get_model_manager() -> ModelManager:
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager
