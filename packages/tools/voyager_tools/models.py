"""Pydantic models for voyager_tools results."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class VideoSearchResult(BaseModel):
    video_id: str
    title: str
    channel_id: str
    channel_title: str
    published_at: datetime
    description: str = ""
    thumbnail_url: str | None = None


class AudioFile(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    video_id: str
    path: Path
    duration_s: float
    size_bytes: int
    sample_rate: int
    bitrate: int | None = None


class TranscriptResult(BaseModel):
    text: str
    language: str
    duration_s: float
    segments: list[dict[str, Any]] = Field(default_factory=list)


class CommentItem(BaseModel):
    comment_id: str
    author: str
    text: str
    like_count: int = 0
    published_at: datetime
    reply_count: int = 0
