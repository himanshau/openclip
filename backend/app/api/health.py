from __future__ import annotations

from fastapi import APIRouter, Depends
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas import HealthComponent, HealthResponse
from app.services.system_status import collect_system_status

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    settings = get_settings()
    components: dict[str, HealthComponent] = {}

    try:
        db.execute(text("SELECT 1"))
        components["database"] = HealthComponent(status="ok")
    except Exception as exc:  # noqa: BLE001
        components["database"] = HealthComponent(status="error", detail=str(exc))

    try:
        redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        pong = redis.ping()
        components["redis"] = HealthComponent(
            status="ok" if pong else "error",
            detail=None if pong else "ping failed",
        )
    except Exception as exc:  # noqa: BLE001
        components["redis"] = HealthComponent(status="error", detail=str(exc))

    overall = "ok" if all(c.status == "ok" for c in components.values()) else "degraded"
    return HealthResponse(status=overall, project=settings.project_name, components=components)


@router.get("/api/system/status")
def system_status():
    return collect_system_status()
