"""LLM-subgraph nodes (local CLI) — currently wired to a stub Copilot client.

The real backend will shell out to the GitHub Copilot CLI (`copilot --prompt`);
until that integration is proven we abstract it behind a Protocol and ship a
StubCopilotClient that returns canned pydantic payloads so tests and local
integration runs stay offline.
"""
from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from voyager_agents.eric.state import EricState

# TODO: implement ShellCopilotClient that shells out to `copilot --prompt` once
# the GitHub Copilot CLI non-interactive interface is confirmed. See:
#   https://docs.github.com/en/copilot/github-copilot-in-the-cli


# --------------------------------------------------------------------------- #
# Copilot client protocol + stub
# --------------------------------------------------------------------------- #
class CopilotClient(Protocol):
    async def complete(
        self,
        system: str,
        user: str,
        schema: type[BaseModel] | None = None,
    ) -> BaseModel | str: ...


class Hook(BaseModel):
    hook_text: str
    timestamp_s: float = 0.0
    confidence: float = 0.5


class HookExtraction(BaseModel):
    hooks: list[Hook] = Field(default_factory=list)


class SellingPoint(BaseModel):
    point: str
    evidence: str = ""
    confidence: float = 0.5


class SellingPointExtraction(BaseModel):
    selling_points: list[SellingPoint] = Field(default_factory=list)


class Cluster(BaseModel):
    theme: str
    members: list[str] = Field(default_factory=list)
    summary: str = ""


class ClusterOutput(BaseModel):
    clusters: list[Cluster] = Field(default_factory=list)


class StubCopilotClient:
    """Canned Copilot client for tests + offline dev runs."""

    def __init__(self, canned: dict[type[BaseModel], BaseModel] | None = None) -> None:
        self._canned: dict[type[BaseModel], BaseModel] = canned or {}

    def set(self, schema: type[BaseModel], value: BaseModel) -> None:
        self._canned[schema] = value

    async def complete(
        self,
        system: str,
        user: str,
        schema: type[BaseModel] | None = None,
    ) -> BaseModel | str:
        if schema is None:
            return "STUB RESPONSE"
        if schema in self._canned:
            return self._canned[schema]
        # Fall back to schema default
        if schema is HookExtraction:
            return HookExtraction(hooks=[Hook(hook_text="stub hook", confidence=0.5)])
        if schema is SellingPointExtraction:
            return SellingPointExtraction(
                selling_points=[SellingPoint(point="stub selling point", confidence=0.5)]
            )
        if schema is ClusterOutput:
            return ClusterOutput(
                clusters=[Cluster(theme="stub theme", members=[], summary="stub summary")]
            )
        return schema()  # best effort


# --------------------------------------------------------------------------- #
# LLM nodes
# --------------------------------------------------------------------------- #
_SYS_HOOKS = (
    "You extract short attention-grabbing hooks from a video transcript. "
    "Return strict JSON matching the HookExtraction schema."
)
_SYS_POINTS = (
    "You extract concrete selling points (reasons a viewer should visit / "
    "watch / buy) from a transcript. Return SellingPointExtraction JSON."
)
_SYS_CLUSTER = (
    "You cluster hooks and selling points by theme. Return ClusterOutput JSON."
)
_SYS_BRIEF = (
    "You write a concise Markdown Strategy Brief for overseas growth marketing "
    "of China travel content."
)


async def node_extract_hooks(state: EricState, client: CopilotClient) -> EricState:
    for video_id, tr in state.transcripts.items():
        result = await client.complete(
            system=_SYS_HOOKS,
            user=f"VIDEO_ID={video_id}\nTRANSCRIPT:\n{tr.text}",
            schema=HookExtraction,
        )
        if isinstance(result, HookExtraction):
            for h in result.hooks:
                state.hooks.append({"video_id": video_id, **h.model_dump()})
    return state


async def node_extract_selling_points(
    state: EricState, client: CopilotClient
) -> EricState:
    for video_id, tr in state.transcripts.items():
        result = await client.complete(
            system=_SYS_POINTS,
            user=f"VIDEO_ID={video_id}\nTRANSCRIPT:\n{tr.text}",
            schema=SellingPointExtraction,
        )
        if isinstance(result, SellingPointExtraction):
            for sp in result.selling_points:
                state.selling_points.append({"video_id": video_id, **sp.model_dump()})
    return state


async def node_cluster_insights(state: EricState, client: CopilotClient) -> EricState:
    payload: dict[str, Any] = {
        "hooks": state.hooks,
        "selling_points": state.selling_points,
    }
    result = await client.complete(
        system=_SYS_CLUSTER,
        user=str(payload),
        schema=ClusterOutput,
    )
    if isinstance(result, ClusterOutput):
        state.clusters = [c.model_dump() for c in result.clusters]
    return state


async def node_write_brief(state: EricState, client: CopilotClient) -> EricState:
    user = (
        f"TOPIC: {state.topic}\n"
        f"CLUSTERS: {state.clusters}\n"
        f"HOOKS_SAMPLE: {state.hooks[:10]}\n"
        f"SELLING_POINTS_SAMPLE: {state.selling_points[:10]}\n"
    )
    result = await client.complete(system=_SYS_BRIEF, user=user, schema=None)
    state.brief_md = result if isinstance(result, str) else str(result)
    return state
