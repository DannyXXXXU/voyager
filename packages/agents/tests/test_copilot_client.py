"""Tests for CopilotClaudeClient — parsing logic & error handling (no real CLI).

Live smoke test lives in scripts/smoke_copilot.py (separate, manual run).
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from voyager_agents.eric.copilot_client import (
    CopilotCLIError,
    CopilotClaudeClient,
    _extract_json_text,
    _wsl_to_windows,
)


class Out(BaseModel):
    hook: str
    score: float


def test_wsl_to_windows_basic():
    from pathlib import Path

    assert _wsl_to_windows(Path("/mnt/c/temp/foo.txt")) == "C:\\temp\\foo.txt"
    assert _wsl_to_windows(Path("/mnt/d/x/y.bin")) == "D:\\x\\y.bin"


def test_extract_json_strips_stats_and_fences():
    raw = (
        "```json\n"
        '{"hook":"abc","score":0.9}\n'
        "```\n"
        "\n"
        "Changes   +0 -0\n"
        "Requests  3 Premium (9s)\n"
        "Tokens    123\n"
    )
    assert _extract_json_text(raw) == '{"hook":"abc","score":0.9}'


def test_extract_json_plain():
    raw = '{"hook":"abc","score":0.9}\nChanges   +0 -0\n'
    assert _extract_json_text(raw) == '{"hook":"abc","score":0.9}'


def test_extract_json_with_prose_prefix():
    raw = 'Sure! Here you go:\n{"hook":"abc","score":0.9}\nChanges   +0 -0\n'
    body = _extract_json_text(raw)
    assert body.startswith("{")
    assert '"hook"' in body


@pytest.mark.asyncio
async def test_complete_parses_schema(tmp_path, monkeypatch):
    client = CopilotClaudeClient()

    async def fake_invoke(self, prompt: str) -> str:
        return '```json\n{"hook":"x","score":0.5}\n```\nChanges  +0 -0\n'

    with patch.object(CopilotClaudeClient, "_invoke", fake_invoke):
        got = await client.complete(system="s", user="u", schema=Out)
    assert isinstance(got, Out)
    assert got.hook == "x"
    assert got.score == 0.5


@pytest.mark.asyncio
async def test_complete_no_schema_returns_raw():
    client = CopilotClaudeClient()

    async def fake_invoke(self, prompt: str) -> str:
        return "free-form text"

    with patch.object(CopilotClaudeClient, "_invoke", fake_invoke):
        got = await client.complete(system="s", user="u", schema=None)
    assert got == "free-form text"


@pytest.mark.asyncio
async def test_complete_retries_on_invalid_json_then_succeeds():
    client = CopilotClaudeClient(max_retries=1)
    calls = {"n": 0}

    async def fake_invoke(self, prompt: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "not json at all"
        return '{"hook":"ok","score":0.9}'

    with patch.object(CopilotClaudeClient, "_invoke", fake_invoke):
        got = await client.complete(system="s", user="u", schema=Out)
    assert isinstance(got, Out)
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_complete_gives_up_after_max_retries():
    client = CopilotClaudeClient(max_retries=1)

    async def fake_invoke(self, prompt: str) -> str:
        return "garbage"

    with patch.object(CopilotClaudeClient, "_invoke", fake_invoke):
        with pytest.raises(CopilotCLIError):
            await client.complete(system="s", user="u", schema=Out)
