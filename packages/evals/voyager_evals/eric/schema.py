"""Eric eval fixture schema."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Difficulty = Literal["easy", "medium", "hard"]


class GoldHook(BaseModel):
    """A hand-labeled hook a hook extractor should find.

    `aliases` lets fuzzy matching via sentence embeddings accept paraphrases.
    """

    text: str
    aliases: list[str] = Field(default_factory=list)
    timestamp_s: float | None = None


class GoldSellingPoint(BaseModel):
    text: str
    aliases: list[str] = Field(default_factory=list)


class EricFixture(BaseModel):
    id: str
    video_id: str
    topic: str
    difficulty: Difficulty
    content_type: str
    holdout: bool = False
    gold_hooks: list[GoldHook] = Field(default_factory=list)
    gold_selling_points: list[GoldSellingPoint] = Field(default_factory=list)
    notes: str = ""
    transcript_sha256: str | None = None


class SeedVideo(BaseModel):
    """An entry in seed.yaml driving scripts/prefetch_gold.py."""

    id: str
    video_id: str
    topic: str
    difficulty: Difficulty
    content_type: str
    holdout: bool = False


__all__ = ["GoldHook", "GoldSellingPoint", "EricFixture", "SeedVideo"]
