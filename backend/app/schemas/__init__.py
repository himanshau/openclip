from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class HealthComponent(BaseModel):
    status: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    project: str
    components: dict[str, HealthComponent]


class ModelStatus(BaseModel):
    name: str
    installed: bool
    detail: str | None = None


class GpuStatus(BaseModel):
    available: bool
    cuda_available: bool = False
    device_count: int = 0
    devices: list[dict[str, Any]] = Field(default_factory=list)
    vram_used_mb: float | None = None
    vram_total_mb: float | None = None


class SystemStatusResponse(BaseModel):
    project: str
    gpu: GpuStatus
    cpu_percent: float
    ram_used_mb: float
    ram_total_mb: float
    disk_used_gb: float
    disk_total_gb: float
    ffmpeg: dict[str, Any]
    cuda: dict[str, Any]
    models: list[ModelStatus]
    workers: dict[str, Any]
    ollama: dict[str, Any]


class ProcessingJobRead(BaseModel):
    id: UUID
    type: str
    status: str
    progress: int
    current_step: str | None = None
    project_id: UUID | None = None
    video_id: UUID | None = None
    error: dict[str, Any] | None = None
    job_metadata: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}
