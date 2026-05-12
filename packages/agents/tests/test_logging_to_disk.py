"""P0.4 — verify CopilotClaudeClient writes per-attempt stdout to log_dir."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import BaseModel

from voyager_agents.eric.copilot_client import (
    CopilotCLIError,
    CopilotClaudeClient,
)


class _Schema(BaseModel):
    foo: str


def _make_client(tmp_path: Path, **kwargs) -> CopilotClaudeClient:
    """Bypass __init__ (which checks for the PS1 wrapper) so tests run anywhere."""
    c = CopilotClaudeClient.__new__(CopilotClaudeClient)
    c._model = kwargs.get("model", "test-model")
    c._timeout_s = kwargs.get("timeout_s", 1)
    c._max_retries = kwargs.get("max_retries", 1)
    c._backoff_base_s = 0.0
    c._log_dir = tmp_path
    tmp_path.mkdir(parents=True, exist_ok=True)
    return c


def test_dump_log_skipped_without_log_dir(tmp_path: Path) -> None:
    c = _make_client(tmp_path)
    c._log_dir = None
    # Should not raise and should not create anything.
    c._dump_log("tag", 0, "prompt", raw="out", error=None)
    assert list(tmp_path.iterdir()) == []


def test_dump_log_skipped_without_tag(tmp_path: Path) -> None:
    c = _make_client(tmp_path)
    c._dump_log(None, 0, "prompt", raw="out", error=None)
    assert list(tmp_path.iterdir()) == []


def test_dump_log_writes_success_file(tmp_path: Path) -> None:
    c = _make_client(tmp_path)
    c._dump_log("extract_hooks", 0, "PROMPT-BODY", raw="STDOUT-BODY", error=None)
    f = tmp_path / "extract_hooks_00.txt"
    assert f.exists()
    text = f.read_text(encoding="utf-8")
    assert "TAG: extract_hooks" in text
    assert "ATTEMPT: 0" in text
    assert "PROMPT-BODY" in text
    assert "STDOUT-BODY" in text
    assert "--- ERROR ---" not in text


def test_dump_log_writes_error_file(tmp_path: Path) -> None:
    c = _make_client(tmp_path)
    c._dump_log("cluster_insights", 2, "P", raw=None, error="timeout")
    f = tmp_path / "cluster_insights_02.txt"
    text = f.read_text(encoding="utf-8")
    assert "(no stdout" in text
    assert "--- ERROR ---" in text
    assert "timeout" in text


def test_complete_success_creates_attempt00_log(tmp_path: Path, monkeypatch) -> None:
    c = _make_client(tmp_path)

    async def fake_invoke(self, prompt: str) -> str:
        return '{"foo": "ok"}'

    monkeypatch.setattr(CopilotClaudeClient, "_invoke", fake_invoke)
    out = asyncio.run(c.complete("sys", "usr", schema=_Schema, log_tag="t1"))
    assert isinstance(out, _Schema) and out.foo == "ok"
    f = tmp_path / "t1_00.txt"
    assert f.exists()
    assert '"foo": "ok"' in f.read_text(encoding="utf-8")


def test_complete_retry_writes_two_log_files(tmp_path: Path, monkeypatch) -> None:
    c = _make_client(tmp_path, max_retries=2)
    responses = iter(["garbage no json", '{"foo": "ok"}'])

    async def fake_invoke(self, prompt: str) -> str:
        return next(responses)

    monkeypatch.setattr(CopilotClaudeClient, "_invoke", fake_invoke)
    out = asyncio.run(c.complete("sys", "usr", schema=_Schema, log_tag="retry"))
    assert isinstance(out, _Schema)
    assert (tmp_path / "retry_00.txt").exists()
    assert (tmp_path / "retry_01.txt").exists()


def test_complete_cli_error_logged_with_error_section(tmp_path: Path, monkeypatch) -> None:
    c = _make_client(tmp_path, max_retries=0)

    async def fake_invoke(self, prompt: str) -> str:
        raise CopilotCLIError("boom")

    monkeypatch.setattr(CopilotClaudeClient, "_invoke", fake_invoke)
    with pytest.raises(CopilotCLIError):
        asyncio.run(c.complete("sys", "usr", schema=_Schema, log_tag="cli"))
    f = tmp_path / "cli_00.txt"
    assert f.exists()
    text = f.read_text(encoding="utf-8")
    assert "--- ERROR ---" in text
    assert "boom" in text
