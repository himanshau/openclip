from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    project_name: str = "OpenClip"
    app_env: str = "development"
    debug: bool = True
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    database_url: str = "postgresql+psycopg://openclip:openclip@localhost:5432/openclip"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    storage_root: Path = Path("./storage")
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen3:4b"
    whisper_model: str = "large-v3"
    hf_token: str | None = None

    gpu_enabled: bool = True
    max_concurrent_gpu_jobs: int = 1
    max_upload_size: int = 2_147_483_648

    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    config_path: Path = Path("./config.yaml")

    yaml_config: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def resolve_paths(self) -> None:
        root = _repo_root()
        if not self.storage_root.is_absolute():
            candidate = (root / self.storage_root).resolve()
            self.storage_root = candidate
        cfg = self.config_path
        if not cfg.is_absolute():
            for candidate in (Path.cwd() / cfg, root / cfg):
                if candidate.exists():
                    self.config_path = candidate.resolve()
                    break
            else:
                self.config_path = (root / cfg).resolve()


def load_yaml_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise TypeError(f"Config at {path} must be a mapping")
    return data


@lru_cache
def get_settings() -> Settings:
    root = _repo_root()
    os.environ.setdefault("CONFIG_PATH", str(root / "config.yaml"))
    # Load .env into process for nested tools (alembic/celery) when present
    env_path = root / ".env"
    if env_path.exists():
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
    settings = Settings()
    settings.resolve_paths()
    settings.yaml_config = load_yaml_config(settings.config_path)
    gpu_cfg = settings.yaml_config.get("gpu") or {}
    if "max_concurrent_jobs" in gpu_cfg and "MAX_CONCURRENT_GPU_JOBS" not in os.environ:
        settings.max_concurrent_gpu_jobs = int(gpu_cfg["max_concurrent_jobs"])
    return settings
