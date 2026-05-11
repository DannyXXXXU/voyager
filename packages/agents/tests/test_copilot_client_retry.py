"""Tests for CopilotClaudeClient retry behavior (P0.1)."""
from __future__ import annotations

import asyncio
import time

import pytest
from pydantic import BaseModel

from voyager_agents.eric.copilot_client import CopilotCLIError, CopilotClaudeClient


class _Out(BaseModel):
    name: str


def _make_client(monkeypatch, responses, *, max_retries=3, backoff=0.01):
    """Build client with _invoke patched to yield a list of responses/raises."""
    client = CopilotClaudeClient(
        max_retries=max_retries, timeout_s=5, backoff_base_s=backoff
    )
    it = iter(responses)

    async def fake_invoke(self, prompt):  # noqa: ARG001
        item = next(it)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(CopilotClaudeClient, "_invoke", fake_invoke, raising=True)
    return client


def test_succeeds_first_try(monkeypatch):
    c = _make_client(monkeypatch, ['{"name": "ok"}'])
    r = asyncio.run(c.complete("s", "u", _Out))
    assert isinstance(r, _Out) and r.name == "ok"


def test_retries_then_succeeds(monkeypatch):
    c = _make_client(
        monkeypatch,
        ["not json", "still bad", '{"name": "third-try"}'],
        max_retries=3,
    )
    r = asyncio.run(c.complete("s", "u", _Out))
    assert r.name == "third-try"


def test_exhausts_retries_raises(monkeypatch):
    c = _make_client(
        monkeypatch,
        ["bad1", "bad2", "bad3", "bad4"],
        max_retries=3,
    )
    with pytest.raises(CopilotCLIError) as ei:
        asyncio.run(c.complete("s", "u", _Out))
    assert "after 4 attempts" in str(ei.value)


def test_cli_error_also_retries(monkeypatch):
    c = _make_client(
        monkeypatch,
        [CopilotCLIError("net down"), '{"name": "recovered"}'],
        max_retries=3,
    )
    r = asyncio.run(c.complete("s", "u", _Out))
    assert r.name == "recovered"


def test_backoff_actually_waits(monkeypatch):
    # backoff = 0.05 → sleeps 0.05, 0.10 between 3 attempts → ≥ 0.15s
    c = _make_client(
        monkeypatch,
        ["bad", "bad", '{"name": "ok"}'],
        max_retries=3,
        backoff=0.05,
    )
    t0 = time.monotonic()
    r = asyncio.run(c.complete("s", "u", _Out))
    elapsed = time.monotonic() - t0
    assert r.name == "ok"
    assert elapsed >= 0.14, f"backoff too short: {elapsed:.3f}s"
