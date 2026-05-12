"""P0.3 — verify prompt prefill + hard rules + determinism hint."""
from __future__ import annotations

from pydantic import BaseModel

from voyager_agents.eric.copilot_client import CopilotClaudeClient
from voyager_agents.eric.nodes_llm import (
    _SYS_BRIEF,
    _SYS_CLUSTER,
    _SYS_HOOKS,
    _SYS_POINTS,
)


class _DummySchema(BaseModel):
    foo: str = "bar"


def _client() -> CopilotClaudeClient:
    # __init__ checks for the PS1 wrapper; create the bare object directly so
    # the test runs in any sandbox (the PS1 path may not exist).
    c = CopilotClaudeClient.__new__(CopilotClaudeClient)
    return c


def test_schema_prompt_has_determinism_block() -> None:
    p = _client()._build_prompt("sys", "usr", _DummySchema)
    assert "DETERMINISM:" in p
    assert "deterministic" in p.lower()


def test_schema_prompt_has_brace_prefill_hint() -> None:
    p = _client()._build_prompt("sys", "usr", _DummySchema)
    assert "BEGIN YOUR RESPONSE WITH THE CHARACTER `{`" in p
    assert "END WITH `}`" in p


def test_freeform_prompt_has_determinism_no_brace_hint() -> None:
    p = _client()._build_prompt("sys", "usr", None)
    assert "DETERMINISM:" in p
    # Free-form (e.g. brief) MUST NOT demand JSON braces.
    assert "BEGIN YOUR RESPONSE WITH THE CHARACTER `{`" not in p


def test_schema_prompt_still_carries_schema_json() -> None:
    p = _client()._build_prompt("sys", "usr", _DummySchema)
    assert "RESPONSE FORMAT:" in p
    assert '"foo"' in p  # schema field leaks into the json_schema dump


def test_hooks_system_has_hard_rules() -> None:
    assert "HARD RULES:" in _SYS_HOOKS
    assert "3 and 8" in _SYS_HOOKS
    assert "verbatim" in _SYS_HOOKS.lower()


def test_selling_points_system_has_hard_rules() -> None:
    assert "HARD RULES:" in _SYS_POINTS
    assert "3 and 10" in _SYS_POINTS
    assert "evidence" in _SYS_POINTS.lower()


def test_cluster_system_has_hard_rules() -> None:
    assert "HARD RULES:" in _SYS_CLUSTER
    assert "3–6" in _SYS_CLUSTER


def test_brief_system_has_required_sections() -> None:
    for section in (
        "## Topic",
        "## Top Hooks",
        "## Selling Points",
        "## Themes",
        "## Recommendations",
    ):
        assert section in _SYS_BRIEF
    assert "250–600 words" in _SYS_BRIEF
