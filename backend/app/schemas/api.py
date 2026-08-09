from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None


class ProjectRead(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class VideoRead(BaseModel):
    id: UUID
    project_id: UUID
    filename: str
    status: str
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    codec: str | None = None
    audio_codec: str | None = None
    thumbnail_path: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class JobRead(BaseModel):
    id: UUID
    type: str
    status: str
    progress: int
    current_step: str | None = None
    video_id: UUID | None = None
    project_id: UUID | None = None
    error: dict[str, Any] | None = None
    job_metadata: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class TranscriptWordRead(BaseModel):
    word: str
    start: float
    end: float
    confidence: float | None = None
    speaker: str | None = None


class TranscriptSegmentRead(BaseModel):
    start: float
    end: float
    speaker: str | None = None
    text: str
    words: list[TranscriptWordRead] = Field(default_factory=list)


class TranscriptRead(BaseModel):
    id: UUID
    video_id: UUID
    language: str | None = None
    text: str
    duration: float | None = None
    segments: list[TranscriptSegmentRead] = Field(default_factory=list)


class CandidateRead(BaseModel):
    id: UUID
    start: float
    end: float
    text: str
    deterministic_score: float | None = None
    final_score: float | None = None
    rank: int | None = None
    llm_score: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class ClipRead(BaseModel):
    id: UUID
    video_id: UUID
    title: str | None = None
    start: float
    end: float
    score: float | None = None
    score_breakdown: dict[str, Any] | None = None
    edit_plan: dict[str, Any] | None = None
    render_path: str | None = None
    thumbnail_path: str | None = None
    status: str

    model_config = {"from_attributes": True}


class ProcessRequest(BaseModel):
    top_n: int = 3


class CaptionPresetRead(BaseModel):
    name: str
    config: dict[str, Any]
