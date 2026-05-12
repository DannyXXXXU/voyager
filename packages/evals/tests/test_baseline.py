"""Tests for baseline runner: TrackingClient stats + judge cache/parser."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from voyager_agents.eric.copilot_client import CopilotCLIError
from voyager_evals.eric.baseline import CallStats, TrackingClient
from voyager_evals.eric.judges.brief_judge import _parse_judge_response
from voyager_evals.eric.judges.cache import JudgeCache, JudgeCacheEntry, compute_key


# --- TrackingClient ----------------------------------------------------------

class _Out(BaseModel):
    x: int = 1


class _FakeOK:
    _model = "fake"

    async def complete(self, system, user, schema=None, log_tag=None):
        if schema is None:
            return "free text"
        return schema()


class _FakeErr:
    _model = "fake"

    async def complete(self, system, user, schema=None, log_tag=None):
        raise CopilotCLIError("boom")


def test_tracking_counts_ok():
    t = TrackingClient(_FakeOK())
    r = asyncio.run(t.complete("s", "u", _Out))
    assert isinstance(r, _Out)
    assert t.stats.schema_total == 1
    assert t.stats.schema_ok == 1
    assert t.stats.schema_validity == 1.0


def test_tracking_counts_failure_and_returns_empty():
    t = TrackingClient(_FakeErr())
    r = asyncio.run(t.complete("s", "u", _Out))
    assert isinstance(r, _Out)  # empty instance returned, not raised
    assert t.stats.schema_total == 1
    assert t.stats.schema_ok == 0
    assert t.stats.schema_validity == 0.0
    assert len(t.stats.errors) == 1


def test_tracking_freeform_not_counted():
    t = TrackingClient(_FakeOK())
    r = asyncio.run(t.complete("s", "u", schema=None))
    assert r == "free text"
    assert t.stats.schema_total == 0
    assert t.stats.schema_validity == 1.0  # vacuously


# --- Judge JSON parser -------------------------------------------------------

def test_parse_judge_response_clean():
    raw = '{"specificity": 4, "actionability": 5, "evidence_grounding": 3, "completeness": 4, "consumability": 4, "total": 4.0}'
    parsed = _parse_judge_response(raw)
    assert parsed is not None
    assert parsed["total"] == 4.0
    assert parsed["specificity"] == 4.0


def test_parse_judge_response_embedded():
    raw = "Here is the score:\n```json\n{\"total\": 3.5, \"specificity\": 3}\n```\nThanks."
    parsed = _parse_judge_response(raw)
    assert parsed is not None
    assert parsed["total"] == 3.5


def test_parse_judge_response_garbage():
    assert _parse_judge_response("no json here") is None


# --- Judge cache -------------------------------------------------------------

def test_judge_cache_roundtrip(tmp_path: Path):
    cache_path = tmp_path / "judge.jsonl"
    cache = JudgeCache(cache_path)
    key = compute_key("gpt-5", "1", "brief text")
    assert cache.get(key) is None
    cache.put(
        JudgeCacheEntry(
            key=key,
            model="gpt-5",
            rubric_version="1",
            brief_sha256="abc",
            scores={"runs": [{"total": 4.2}]},
            overall_median=4.2,
            raw_responses=["{\"total\": 4.2}"],
            created_at="2026-04-22T00:00:00Z",
        )
    )
    # Reload fresh
    cache2 = JudgeCache(cache_path)
    hit = cache2.get(key)
    assert hit is not None
    assert hit["overall_median"] == 4.2
    assert hit["model"] == "gpt-5"
