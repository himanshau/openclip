from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings, load_yaml_config


def test_settings_load():
    settings = get_settings()
    assert settings.project_name
    assert settings.database_url.startswith("postgresql")
    assert settings.max_concurrent_gpu_jobs >= 1
    assert settings.storage_root


def test_yaml_config_loads():
    settings = get_settings()
    data = load_yaml_config(settings.config_path)
    assert "ranking" in data or settings.config_path.exists()
    if settings.config_path.exists():
        assert "candidate" in data
        assert "ranking" in data


def test_repo_config_yaml_exists():
    root = Path(__file__).resolve().parents[2]
    assert (root / "config.yaml").exists()
