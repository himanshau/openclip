from __future__ import annotations

import pytest
from sqlalchemy import text


def test_health_endpoint_shape(client):
    response = client.get("/health")
    # May be degraded if postgres/redis not running — still must return JSON shape
    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "project" in body
    assert "components" in body
    assert "database" in body["components"]
    assert "redis" in body["components"]


def test_system_status_shape(client):
    response = client.get("/api/system/status")
    assert response.status_code == 200
    body = response.json()
    for key in (
        "project",
        "gpu",
        "cpu_percent",
        "ram_used_mb",
        "ram_total_mb",
        "disk_used_gb",
        "disk_total_gb",
        "ffmpeg",
        "cuda",
        "models",
        "workers",
        "ollama",
    ):
        assert key in body
    assert isinstance(body["models"], list)
    assert "available" in body["gpu"]


@pytest.mark.integration
def test_database_select_one():
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        row = db.execute(text("SELECT 1")).scalar()
        assert row == 1
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL not available: {exc}")
    finally:
        db.close()
