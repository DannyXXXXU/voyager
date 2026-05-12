"""P0.5 — verify pydantic→TypeScript-interface schema rendering."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from voyager_agents.eric.copilot_client import (
    pydantic_to_ts_interface,
    _ts_type,
    _pydantic_to_ts_body,
)


class Hook(BaseModel):
    hook_text: str = Field(description="verbatim span, <= 140 chars")
    timestamp_s: float = Field(description="seconds from transcript")
    confidence: float = Field(description="0.0-1.0")


class HookExtraction(BaseModel):
    hooks: List[Hook] = Field(description="3-8 verbatim hooks")


class WithOptional(BaseModel):
    name: str
    note: Optional[str] = None
    flag: bool = False


def test_primitives() -> None:
    assert _ts_type(str) == "string"
    assert _ts_type(int) == "number"
    assert _ts_type(float) == "number"
    assert _ts_type(bool) == "boolean"


def test_list_of_primitive() -> None:
    assert _ts_type(List[str]) == "Array<string>"


def test_optional_renders_nullable() -> None:
    out = _ts_type(Optional[str])
    assert "string" in out and "null" in out


def test_nested_model_inline() -> None:
    body = _pydantic_to_ts_body(Hook)
    assert "hook_text: string" in body
    assert "timestamp_s: number" in body
    assert "confidence: number" in body
    # description preserved as comment
    assert "// verbatim span" in body


def test_interface_header() -> None:
    out = pydantic_to_ts_interface(HookExtraction)
    assert out.startswith("interface HookExtraction {")
    assert out.rstrip().endswith("}")
    # Nested Hook inlined inside Array<...>
    assert "Array<" in out
    assert "hook_text: string" in out
    assert "timestamp_s: number" in out


def test_no_json_schema_noise() -> None:
    """The hallmark fields of JSON Schema must NOT appear."""
    out = pydantic_to_ts_interface(HookExtraction)
    for bad in ("$defs", '"type": "object"', '"properties"', '"title"'):
        assert bad not in out, f"leak: {bad}"


def test_prompt_uses_ts_interface() -> None:
    """_build_prompt must embed the TS interface, not raw JSON Schema."""
    from voyager_agents.eric.copilot_client import CopilotClaudeClient

    client = CopilotClaudeClient.__new__(CopilotClaudeClient)
    client._model = "claude-sonnet-4.5"  # type: ignore[attr-defined]
    client._timeout_s = 60  # type: ignore[attr-defined]
    client._max_retries = 1  # type: ignore[attr-defined]
    client._backoff_base_s = 0.0  # type: ignore[attr-defined]
    client._log_dir = None  # type: ignore[attr-defined]

    prompt = client._build_prompt(
        system="be terse",
        user="extract hooks",
        schema=HookExtraction,
    )
    assert "interface HookExtraction" in prompt
    assert "$defs" not in prompt
    assert '"type": "object"' not in prompt


def test_with_optional_and_bool() -> None:
    out = pydantic_to_ts_interface(WithOptional)
    assert "name: string" in out
    assert "flag: boolean" in out
    assert "null" in out  # note optional
