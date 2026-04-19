"""initial schema: videos, transcripts, comments, insights, briefs

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-19 23:20:00

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LLM_STATUS_VALUES = ("pending", "processing", "done", "failed")
INSIGHT_KIND_VALUES = ("hook", "selling_point", "cluster")


def upgrade() -> None:
    llm_status = postgresql.ENUM(*LLM_STATUS_VALUES, name="llm_status", create_type=False)
    insight_kind = postgresql.ENUM(*INSIGHT_KIND_VALUES, name="insight_kind", create_type=False)

    # Create enums once.
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE llm_status AS ENUM ('pending','processing','done','failed'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE insight_kind AS ENUM ('hook','selling_point','cluster'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$;"
    )

    # videos
    op.create_table(
        "videos",
        sa.Column("video_id", sa.String(length=32), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("channel_id", sa.String(length=64)),
        sa.Column("channel_title", sa.String(length=255)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("view_count", sa.BigInteger()),
        sa.Column("like_count", sa.BigInteger()),
        sa.Column("duration_s", sa.Integer()),
        sa.Column("thumbnail_url", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("lang", sa.String(length=16)),
        sa.Column("region", sa.String(length=8)),
        sa.Column("source_query", sa.Text()),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "llm_status",
            llm_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.create_index("ix_videos_channel_id", "videos", ["channel_id"])
    op.create_index("ix_videos_published_at", "videos", ["published_at"])
    op.create_index("ix_videos_llm_status", "videos", ["llm_status"])

    # transcripts
    op.create_table(
        "transcripts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "video_id",
            sa.String(length=32),
            sa.ForeignKey("videos.video_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("segments", postgresql.JSONB()),
        sa.Column("language", sa.String(length=16)),
        sa.Column("model_name", sa.String(length=64), server_default="whisper-1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_transcripts_video_id", "transcripts", ["video_id"])

    # comments
    op.create_table(
        "comments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "video_id",
            sa.String(length=32),
            sa.ForeignKey("videos.video_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("author", sa.String(length=255)),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("like_count", sa.BigInteger()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_comments_video_id", "comments", ["video_id"])

    # insights (LOCAL CLI writes here)
    op.create_table(
        "insights",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "video_id",
            sa.String(length=32),
            sa.ForeignKey("videos.video_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", insight_kind, nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("model_name", sa.String(length=128)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_insights_video_id", "insights", ["video_id"])
    op.create_index("ix_insights_kind", "insights", ["kind"])

    # briefs
    op.create_table(
        "briefs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column(
            "video_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("content_md", sa.Text()),
        sa.Column(
            "llm_status",
            llm_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_briefs_llm_status", "briefs", ["llm_status"])


def downgrade() -> None:
    op.drop_index("ix_briefs_llm_status", table_name="briefs")
    op.drop_table("briefs")
    op.drop_index("ix_insights_kind", table_name="insights")
    op.drop_index("ix_insights_video_id", table_name="insights")
    op.drop_table("insights")
    op.drop_index("ix_comments_video_id", table_name="comments")
    op.drop_table("comments")
    op.drop_index("ix_transcripts_video_id", table_name="transcripts")
    op.drop_table("transcripts")
    op.drop_index("ix_videos_llm_status", table_name="videos")
    op.drop_index("ix_videos_published_at", table_name="videos")
    op.drop_index("ix_videos_channel_id", table_name="videos")
    op.drop_table("videos")
    op.execute("DROP TYPE IF EXISTS insight_kind")
    op.execute("DROP TYPE IF EXISTS llm_status")
