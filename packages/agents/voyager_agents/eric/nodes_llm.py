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
    "You extract short attention-grabbing hooks from a video transcript.\n"
    "\n"
    "HARD RULES:\n"
    "- Extract between 3 and 8 hooks. Never zero.\n"
    "- Each hook_text MUST be a verbatim or near-verbatim span from the transcript, "
    "no longer than 140 characters.\n"
    "- A hook is a single, concrete, surprising or curiosity-provoking statement "
    "(NOT a topic label, NOT a summary).\n"
    "- timestamp_s MUST be the start-second of the source line in the transcript "
    "if known; use 0.0 only if truly unknown.\n"
    "- confidence is a float in [0.0, 1.0]; use 0.8+ only when the hook is a direct quote.\n"
    "- Reject hooks that are generic (\"this place is amazing\") or hallucinated."
)
_SYS_POINTS = (
    "You extract concrete selling points (reasons a viewer should visit / watch / "
    "buy) from a transcript.\n"
    "\n"
    "HARD RULES:\n"
    "- Extract between 3 and 10 selling points. Never zero.\n"
    "- Each `point` is a SHORT noun phrase (<= 80 chars) naming ONE concrete reason "
    "(\"hand-pulled noodles served at 3am\", \"glacier-fed hot spring\").\n"
    "- `evidence` MUST quote or paraphrase the supporting transcript span verbatim "
    "(<= 200 chars). Never empty.\n"
    "- No marketing fluff (\"unforgettable experience\"). No duplicates.\n"
    "- confidence in [0.0, 1.0]; only >=0.8 when evidence is a direct quote."
)
_SYS_CLUSTER = (
    "You cluster the provided hooks and selling points into 3–6 themes.\n"
    "\n"
    "HARD RULES:\n"
    "- Produce 3–6 clusters. No more, no fewer.\n"
    "- Each `theme` is a SHORT noun phrase (<= 60 chars) — a recognizable category, "
    "not a sentence.\n"
    "- `members` MUST contain only ids/texts that appear in the input (no invention).\n"
    "- `summary` is one sentence (<= 200 chars) capturing what the cluster sells.\n"
    "- Every input hook/selling_point should belong to exactly one cluster."
)
_SYS_BRIEF = (
    "You write a concise Markdown Strategy Brief for overseas growth marketing of "
    "China travel content.\n"
    "\n"
    "HARD RULES:\n"
    "- Output Markdown only. No JSON, no code fences around the whole doc.\n"
    "- 250–600 words total. Tight, not padded.\n"
    "- REQUIRED sections (use these exact H2 headings):\n"
    "  ## Topic\n"
    "  ## Top Hooks\n"
    "  ## Selling Points\n"
    "  ## Themes\n"
    "  ## Recommendations\n"
    "- `## Top Hooks` lists 3–5 bullets, each a single verbatim hook from inputs.\n"
    "- `## Selling Points` lists 3–8 bullets, each prefixed by the point name in **bold**.\n"
    "- `## Themes` lists the cluster themes with a one-line description each.\n"
    "- `## Recommendations` is 3–5 numbered bullets, each actionable for a creator.\n"
    "- Do NOT invent video titles, channel names, or stats not present in the inputs."
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
