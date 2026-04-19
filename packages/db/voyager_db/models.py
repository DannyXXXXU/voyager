"""SQLModel ORM models for Voyager Postgres schema.

Tables:
    videos        YouTube video metadata (+ llm_status for LLM-pipeline gating)
    transcripts   Whisper output (Azure OpenAI)
    comments      Top YouTube comments
    insights      LLM-extracted hooks / selling_points / clusters (written by local CLI)
    briefs        Strategy Brief output (+ llm_status)

Architecture note:
    Cloud worker writes videos/transcripts/comments and sets videos.llm_status='pending'.
    Local CLI (GitHub Copilot Claude) polls for pending rows, produces insights and
    briefs, and flips llm_status to 'done' / 'failed'.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, Column, DateTime, Enum as SAEnum, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Field, SQLModel


class LLMStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


class InsightKind(str, enum.Enum):
    hook = "hook"
    selling_point = "selling_point"
    cluster = "cluster"


def _utcnow() -> datetime:
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# videos
# ---------------------------------------------------------------------------
class Video(SQLModel, table=True):
    __tablename__ = "videos"

    video_id: str = Field(primary_key=True, max_length=32)
    title: str = Field(sa_column=Column(Text, nullable=False))
    channel_id: Optional[str] = Field(default=None, max_length=64, index=True)
    channel_title: Optional[str] = Field(default=None, max_length=255)
    published_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), index=True)
    )
    view_count: Optional[int] = Field(default=None, sa_column=Column(BigInteger))
    like_count: Optional[int] = Field(default=None, sa_column=Column(BigInteger))
    duration_s: Optional[int] = None
    thumbnail_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    lang: Optional[str] = Field(default=None, max_length=16)
    region: Optional[str] = Field(default=None, max_length=8)
    source_query: Optional[str] = Field(default=None, sa_column=Column(Text))
    discovered_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    llm_status: LLMStatus = Field(
        default=LLMStatus.pending,
        sa_column=Column(
            SAEnum(LLMStatus, name="llm_status"), nullable=False, index=True
        ),
    )


# ---------------------------------------------------------------------------
# transcripts
# ---------------------------------------------------------------------------
class Transcript(SQLModel, table=True):
    __tablename__ = "transcripts"

    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: str = Field(foreign_key="videos.video_id", index=True, max_length=32)
    text: str = Field(sa_column=Column(Text, nullable=False))
    segments: Optional[list[dict[str, Any]]] = Field(
        default=None, sa_column=Column(JSONB)
    )
    language: Optional[str] = Field(default=None, max_length=16)
    model_name: Optional[str] = Field(default="whisper-1", max_length=64)
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


# ---------------------------------------------------------------------------
# comments
# ---------------------------------------------------------------------------
class Comment(SQLModel, table=True):
    __tablename__ = "comments"

    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: str = Field(foreign_key="videos.video_id", index=True, max_length=32)
    author: Optional[str] = Field(default=None, max_length=255)
    text: str = Field(sa_column=Column(Text, nullable=False))
    like_count: Optional[int] = Field(default=None, sa_column=Column(BigInteger))
    published_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    fetched_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


# ---------------------------------------------------------------------------
# insights  (written by LOCAL CLI via GitHub Copilot Claude)
# ---------------------------------------------------------------------------
class Insight(SQLModel, table=True):
    __tablename__ = "insights"

    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: str = Field(foreign_key="videos.video_id", index=True, max_length=32)
    kind: InsightKind = Field(
        sa_column=Column(
            SAEnum(InsightKind, name="insight_kind"), nullable=False, index=True
        )
    )
    payload: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    model_name: Optional[str] = Field(default=None, max_length=128)
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


# ---------------------------------------------------------------------------
# briefs
# ---------------------------------------------------------------------------
class Brief(SQLModel, table=True):
    __tablename__ = "briefs"

    id: Optional[int] = Field(default=None, primary_key=True)
    topic: str = Field(sa_column=Column(Text, nullable=False))
    video_ids: list[str] = Field(
        default_factory=list, sa_column=Column(ARRAY(Text), nullable=False)
    )
    content_md: Optional[str] = Field(default=None, sa_column=Column(Text))
    llm_status: LLMStatus = Field(
        default=LLMStatus.pending,
        sa_column=Column(
            SAEnum(LLMStatus, name="llm_status", create_type=False),
            nullable=False,
            index=True,
        ),
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
