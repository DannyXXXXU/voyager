"""P0.6 — transcript segment timestamps surfaced to the LLM prompt."""
from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel

from voyager_agents.eric.nodes_llm import (
    HookExtraction,
    Hook,
    StubCopilotClient,
    _format_transcript_with_timestamps,
    node_extract_hooks,
    node_extract_selling_points,
)
from voyager_agents.eric.state import EricState
from voyager_tools.models import TranscriptResult


def _tr_with_segments() -> TranscriptResult:
    return TranscriptResult(
        text="Hello world. Spicy noodles at 3am.",
        language="en",
        duration_s=42.0,
        segments=[
            {"start": 0.0, "end": 2.5, "text": " Hello world."},
            {"start": 12.4, "end": 15.0, "text": "Spicy noodles at 3am."},
            {"start": 30.0, "end": 32.0, "text": ""},  # empty — skipped
        ],
    )


def _tr_text_only() -> TranscriptResult:
    return TranscriptResult(text="plain text body", language="en", duration_s=10.0, segments=[])


def test_format_with_segments_emits_timestamp_tags() -> None:
    out = _format_transcript_with_timestamps(_tr_with_segments())
    assert "[0.0s] Hello world." in out
    assert "[12.4s] Spicy noodles at 3am." in out
    # empty segment dropped
    assert "[30.0s]" not in out


def test_format_falls_back_to_text_when_no_segments() -> None:
    assert _format_transcript_with_timestamps(_tr_text_only()) == "plain text body"


def test_format_handles_malformed_segments() -> None:
    tr = TranscriptResult(
        text="fallback",
        language="en",
        duration_s=1.0,
        segments=[
            {"start": "not-a-number", "text": "bad"},
            {"text": "missing start"},
            {"start": None, "text": "none start"},
        ],
    )
    # All segments malformed → fall back to tr.text
    assert _format_transcript_with_timestamps(tr) == "fallback"


class _CapturingClient:
    """Stub that records every prompt and returns a canned schema instance."""

    def __init__(self, canned: dict[type, Any]) -> None:
        self._canned = canned
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        system: str,
        user: str,
        schema: type[BaseModel] | None = None,
        log_tag: str | None = None,
    ) -> BaseModel | str:
        self.calls.append({"system": system, "user": user, "schema": schema, "log_tag": log_tag})
        if schema is None:
            return ""
        return self._canned.get(schema, schema())


def test_hooks_node_passes_timestamped_transcript() -> None:
    state = EricState(topic="t")
    state.transcripts["vid-1"] = _tr_with_segments()
    client = _CapturingClient({HookExtraction: HookExtraction(hooks=[Hook(hook_text="x")])})
    asyncio.run(node_extract_hooks(state, client))
    assert client.calls, "expected at least one LLM call"
    user_prompt = client.calls[0]["user"]
    assert "VIDEO_ID=vid-1" in user_prompt
    assert "[0.0s] Hello world." in user_prompt
    assert "[12.4s] Spicy noodles at 3am." in user_prompt


def test_selling_points_node_passes_timestamped_transcript() -> None:
    from voyager_agents.eric.nodes_llm import SellingPointExtraction

    state = EricState(topic="t")
    state.transcripts["vid-2"] = _tr_with_segments()
    client = _CapturingClient(
        {SellingPointExtraction: SellingPointExtraction(selling_points=[])}
    )
    asyncio.run(node_extract_selling_points(state, client))
    assert client.calls
    user_prompt = client.calls[0]["user"]
    assert "[0.0s] Hello world." in user_prompt
    assert "[12.4s] Spicy noodles at 3am." in user_prompt


def test_hook_prompt_instructs_to_copy_timestamp_tag() -> None:
    """The HARD-RULE about copying [<s>s] tags must be present in the system prompt."""
    from voyager_agents.eric.nodes_llm import _SYS_HOOKS

    assert "[<seconds>s]" in _SYS_HOOKS or "[<seconds>s] tag" in _SYS_HOOKS
    assert "Copy that number verbatim" in _SYS_HOOKS


def test_unused_stub_client_still_works() -> None:
    """Sanity: existing StubCopilotClient wasn't broken by P0.6 changes."""
    stub = StubCopilotClient()
    result = asyncio.run(stub.complete("sys", "usr", schema=HookExtraction))
    assert isinstance(result, HookExtraction)
