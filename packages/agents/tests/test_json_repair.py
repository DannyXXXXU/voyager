"""Tests for json-repair fallback (P0.2)."""
from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import BaseModel

from voyager_agents.eric.copilot_client import (
    CopilotCLIError,
    CopilotClaudeClient,
    _parse_json_with_repair,
)


class _Out(BaseModel):
    name: str
    count: int = 0


# --- pure parser ------------------------------------------------------------

def test_strict_passes_no_repair():
    obj, note = _parse_json_with_repair('{"name": "a", "count": 1}')
    assert obj == {"name": "a", "count": 1}
    assert note is None


def test_repair_trailing_comma():
    obj, note = _parse_json_with_repair('{"name": "a", "count": 1,}')
    assert obj == {"name": "a", "count": 1}
    assert note and "repaired" in note


def test_repair_single_quotes():
    obj, note = _parse_json_with_repair("{'name': 'a', 'count': 2}")
    assert obj == {"name": "a", "count": 2}
    assert note and "repaired" in note


def test_repair_missing_quotes_on_keys():
    obj, note = _parse_json_with_repair('{name: "a", count: 3}')
    assert obj["name"] == "a"
    assert obj["count"] == 3
    assert note is not None


def test_repair_truncated_object():
    # Common LLM truncation: cut off mid-value
    obj, note = _parse_json_with_repair('{"name": "abc", "count":')
    assert obj["name"] == "abc"
    assert note is not None


def test_repair_total_garbage_raises():
    with pytest.raises(json.JSONDecodeError):
        _parse_json_with_repair("not json at all just words")


# --- end-to-end through the client -----------------------------------------

def _make_client(monkeypatch, responses, *, max_retries=3):
    client = CopilotClaudeClient(
        max_retries=max_retries, timeout_s=5, backoff_base_s=0.0
    )
    it = iter(responses)

    async def fake_invoke(self, prompt):  # noqa: ARG001
        return next(it)

    monkeypatch.setattr(CopilotClaudeClient, "_invoke", fake_invoke, raising=True)
    return client


def test_client_recovers_from_trailing_comma_first_try(monkeypatch):
    """Common LLM error (trailing comma) — should pass on attempt 1 via repair."""
    c = _make_client(monkeypatch, ['{"name": "x", "count": 5,}'])
    r = asyncio.run(c.complete("s", "u", _Out))
    assert r.name == "x" and r.count == 5


def test_client_recovers_from_single_quotes_first_try(monkeypatch):
    c = _make_client(monkeypatch, ["{'name': 'x', 'count': 5}"])
    r = asyncio.run(c.complete("s", "u", _Out))
    assert r.name == "x"


def test_client_still_uses_corrective_retry_on_total_garbage(monkeypatch):
    # Garbage → repair fails → retry → succeeds on attempt 2
    c = _make_client(
        monkeypatch,
        ["random prose with no json", '{"name": "ok"}'],
        max_retries=3,
    )
    r = asyncio.run(c.complete("s", "u", _Out))
    assert r.name == "ok"
