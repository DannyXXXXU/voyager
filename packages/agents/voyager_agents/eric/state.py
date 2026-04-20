"""EricState — pydantic state carried through the Eric agent LangGraph."""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from voyager_tools.models import AudioFile, CommentItem, TranscriptResult, VideoSearchResult


class EricState(BaseModel):
    """State for the Eric agent (cloud-data + local-LLM subgraphs).

    The cloud-worker data subgraph populates: search_results, downloaded,
    transcripts, comments, then persists. llm_status=pending is set on videos.

    The local-CLI llm subgraph reads from Postgres, populates: hooks,
    selling_points, clusters, brief_md.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Inputs
    topic: str
    keywords: list[str] = Field(default_factory=list)
    region_code: str = "US"
    language: str = "en"
    max_videos: int = 20

    # Data-subgraph outputs
    search_results: list[VideoSearchResult] = Field(default_factory=list)
    downloaded: list[AudioFile] = Field(default_factory=list)
    transcripts: dict[str, TranscriptResult] = Field(default_factory=dict)
    comments: dict[str, list[CommentItem]] = Field(default_factory=dict)

    # LLM-subgraph outputs (local only; Insight rows serialized separately)
    hooks: list[dict[str, Any]] = Field(default_factory=list)
    selling_points: list[dict[str, Any]] = Field(default_factory=list)
    clusters: list[dict[str, Any]] = Field(default_factory=list)
    brief_md: str | None = None

    # Meta
    errors: list[dict[str, Any]] = Field(default_factory=list)
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
