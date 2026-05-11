"""JSONL-backed cache for LLM-judge calls.

Key = sha256(model + rubric_version + brief_text). Value = full judge entry.
Writes are append-only JSONL; reads are dict-loaded on open. This keeps
re-runs deterministic and cheap once a brief has been judged.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class JudgeCacheEntry:
    key: str
    model: str
    rubric_version: str
    brief_sha256: str
    scores: dict[str, float] = field(default_factory=dict)
    overall_median: float = 0.0
    raw_responses: list[str] = field(default_factory=list)
    created_at: str = ""


def compute_key(model: str, rubric_version: str, brief_text: str) -> str:
    h = hashlib.sha256()
    h.update(model.encode())
    h.update(b"\x00")
    h.update(rubric_version.encode())
    h.update(b"\x00")
    h.update(brief_text.encode())
    return h.hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class JudgeCache:
    """Append-only JSONL cache. Safe for sequential use."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._mem: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def load(self) -> None:
        self._mem = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    self._mem[obj["key"]] = obj
                except (json.JSONDecodeError, KeyError):
                    continue
        self._loaded = True

    def get(self, key: str) -> dict[str, Any] | None:
        if not self._loaded:
            self.load()
        return self._mem.get(key)

    def put(self, entry: JudgeCacheEntry) -> None:
        if not self._loaded:
            self.load()
        d = asdict(entry)
        self._mem[entry.key] = d
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


__all__ = ["JudgeCacheEntry", "JudgeCache", "compute_key", "sha256_text"]
