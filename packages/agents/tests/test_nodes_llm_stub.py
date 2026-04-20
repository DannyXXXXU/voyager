"""Tests for LLM-subgraph nodes with StubCopilotClient."""
from __future__ import annotations

import pytest

from voyager_agents.eric.nodes_llm import (
    Cluster,
    ClusterOutput,
    Hook,
    HookExtraction,
    SellingPoint,
    SellingPointExtraction,
    StubCopilotClient,
    node_cluster_insights,
    node_extract_hooks,
    node_extract_selling_points,
    node_write_brief,
)
from voyager_agents.eric.state import EricState
from voyager_tools.models import TranscriptResult


def _state_with_transcripts() -> EricState:
    s = EricState(topic="yunnan")
    s.transcripts = {
        "v1": TranscriptResult(text="hello v1", language="en", duration_s=60.0),
        "v2": TranscriptResult(text="hello v2", language="en", duration_s=60.0),
    }
    return s


@pytest.mark.asyncio
async def test_extract_hooks_uses_canned() -> None:
    client = StubCopilotClient()
    client.set(
        HookExtraction,
        HookExtraction(hooks=[Hook(hook_text="incredible scenery", confidence=0.9)]),
    )
    state = _state_with_transcripts()
    out = await node_extract_hooks(state, client)
    assert len(out.hooks) == 2  # one per video
    assert {h["video_id"] for h in out.hooks} == {"v1", "v2"}
    assert out.hooks[0]["hook_text"] == "incredible scenery"


@pytest.mark.asyncio
async def test_extract_selling_points_defaults() -> None:
    state = _state_with_transcripts()
    out = await node_extract_selling_points(state, StubCopilotClient())
    assert len(out.selling_points) == 2
    assert out.selling_points[0]["point"] == "stub selling point"


@pytest.mark.asyncio
async def test_cluster_insights_populates_clusters() -> None:
    client = StubCopilotClient()
    client.set(
        ClusterOutput,
        ClusterOutput(clusters=[Cluster(theme="nature", members=["v1"], summary="s")]),
    )
    state = _state_with_transcripts()
    state.hooks = [{"video_id": "v1", "hook_text": "h"}]
    state.selling_points = [{"video_id": "v1", "point": "p"}]
    out = await node_cluster_insights(state, client)
    assert out.clusters == [{"theme": "nature", "members": ["v1"], "summary": "s"}]


@pytest.mark.asyncio
async def test_write_brief_sets_markdown() -> None:
    state = _state_with_transcripts()
    state.clusters = [{"theme": "nature", "members": ["v1"], "summary": "s"}]
    out = await node_write_brief(state, StubCopilotClient())
    assert isinstance(out.brief_md, str) and out.brief_md
