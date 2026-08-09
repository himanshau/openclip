"""Initial schema: users, projects, videos, processing_jobs."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    job_status = postgresql.ENUM(
        "QUEUED",
        "RUNNING",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        name="job_status",
        create_type=False,
    )
    job_type = postgresql.ENUM(
        "MEDIA_INGESTION",
        "TRANSCRIPTION",
        "DIARIZATION",
        "SCENE_DETECTION",
        "CANDIDATE_GENERATION",
        "CANDIDATE_SCORING",
        "LLM_RANKING",
        "DEDUPLICATION",
        "EDIT_PLANNING",
        "RENDER",
        "THUMBNAIL",
        "VALIDATION",
        "HEALTHCHECK",
        name="job_type",
        create_type=False,
    )
    video_status = postgresql.ENUM(
        "UPLOADED",
        "VALIDATING",
        "PROCESSING",
        "READY",
        "FAILED",
        name="video_status",
        create_type=False,
    )

    bind = op.get_bind()
    postgresql.ENUM(
        "QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", name="job_status"
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "MEDIA_INGESTION",
        "TRANSCRIPTION",
        "DIARIZATION",
        "SCENE_DETECTION",
        "CANDIDATE_GENERATION",
        "CANDIDATE_SCORING",
        "LLM_RANKING",
        "DEDUPLICATION",
        "EDIT_PLANNING",
        "RENDER",
        "THUMBNAIL",
        "VALIDATION",
        "HEALTHCHECK",
        name="job_type",
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "UPLOADED", "VALIDATING", "PROCESSING", "READY", "FAILED", name="video_status"
    ).create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("original_path", sa.String(length=1024), nullable=True),
        sa.Column("proxy_path", sa.String(length=1024), nullable=True),
        sa.Column("audio_path", sa.String(length=1024), nullable=True),
        sa.Column("thumbnail_path", sa.String(length=1024), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("fps", sa.Float(), nullable=True),
        sa.Column("codec", sa.String(length=64), nullable=True),
        sa.Column("audio_codec", sa.String(length=64), nullable=True),
        sa.Column("status", video_status, nullable=False, server_default="UPLOADED"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_videos_sha256", "videos", ["sha256"])

    op.create_table(
        "processing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("type", job_type, nullable=False),
        sa.Column("status", job_status, nullable=False, server_default="QUEUED"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_step", sa.String(length=255), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id"), nullable=True),
        sa.Column("error", postgresql.JSONB(), nullable=True),
        sa.Column("job_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("processing_jobs")
    op.drop_index("ix_videos_sha256", table_name="videos")
    op.drop_table("videos")
    op.drop_table("projects")
    op.drop_table("users")
    bind = op.get_bind()
    postgresql.ENUM(name="video_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="job_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="job_status").drop(bind, checkfirst=True)
