"""Add clip_performances for post-publish learning-to-rank labels."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_clip_performance"
down_revision: Union[str, None] = "0002_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clip_performances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("clip_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clips.id"), nullable=False, unique=True),
        sa.Column("platform", sa.String(64)),
        sa.Column("publish_time", sa.DateTime(timezone=True)),
        sa.Column("views", sa.Integer()),
        sa.Column("likes", sa.Integer()),
        sa.Column("comments", sa.Integer()),
        sa.Column("shares", sa.Integer()),
        sa.Column("average_view_duration", sa.Float()),
        sa.Column("average_percentage_viewed", sa.Float()),
        sa.Column("viewed_vs_swiped_away", sa.Float()),
        sa.Column("extra", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("clip_performances")
