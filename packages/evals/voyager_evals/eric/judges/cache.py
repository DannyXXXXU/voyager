"""JSONL-backed cache for LLM-judge calls (Task 1.4 scaffold).

Key = sha256(model_name + rubric_version + brief_text). Value = full judge
response. Writes are append-only; reads are dict-loaded on open. This keeps
re-runs deterministic and cheap once a brief has been judged.

Implementation in Task 1.10.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class JudgeCacheEntry:
    key: str
    model: str
    rubric_version: str
    brief_sha256: str
    scores: dict[str, int]  # {specificity, actionability, evidence_grounding, completeness, consumability}
    overall_median: float
    raw_responses: list[str]  # median-of-3 → 3 raw texts
    created_at: str  # ISO-8601


def compute_key(model: str, rubric_version: str, brief_text: str) -> str:
    h = hashlib.sha256()
    h.update(model.encode())
    h.update(b"\x00")
    h.update(rubric_version.encode())
    h.update(b"\x00")
    h.update(brief_text.encode())
    return h.hexdigest()


class JudgeCache:
    def __init__(self, path: Path):
        self.path = path
        self._mem: dict[str, dict[str, Any]] = {}

    def load(self) -> None:
        raise NotImplementedError("JudgeCache.load — Task 1.10")

    def get(self, key: str) -> dict[str, Any] | None:
        raise NotImplementedError("JudgeCache.get — Task 1.10")

    def put(self, entry: JudgeCacheEntry) -> None:
        raise NotImplementedError("JudgeCache.put — Task 1.10")
