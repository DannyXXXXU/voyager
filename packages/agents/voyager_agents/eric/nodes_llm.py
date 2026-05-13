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
from voyager_tools.models import TranscriptResult


def _format_transcript_with_timestamps(tr: TranscriptResult) -> str:
    """Render transcript as ``[12.5s] text…`` lines when Whisper segments exist.

    P0.6: the model previously saw plain concatenated text and had no way to
    ground ``timestamp_s`` other than guessing. By tagging each segment with its
    start-second the LLM can copy the timestamp directly from the source line.

    Falls back to ``tr.text`` when segments are missing or malformed.
    """
    segs = tr.segments or []
    if not segs:
        return tr.text
    lines: list[str] = []
    for seg in segs:
        # Whisper segment dict: {"start": float, "end": float, "text": str, ...}
        start = seg.get("start")
        text = (seg.get("text") or "").strip()
        if start is None or not text:
            continue
        try:
            start_f = float(start)
        except (TypeError, ValueError):
            continue
        lines.append(f"[{start_f:.1f}s] {text}")
    if not lines:
        return tr.text
    return "\n".join(lines)

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
        log_tag: str | None = None,
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
        log_tag: str | None = None,
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
    "You extract attention-grabbing hooks from a video transcript. Hooks are the "
    "lines a creator would use to STOP a viewer from scrolling — typically found in "
    "the first 30 seconds and at every major section opener.\n"
    "\n"
    "HARD RULES:\n"
    "- Extract between 3 and 8 hooks. Never zero.\n"
    "- ALWAYS include the opening hook(s) from the first 30 seconds of the transcript "
    "if any exist. Opening CTAs like \"Did you know...\", \"Stick around...\", "
    "\"If you're traveling to X for the first time...\", \"These mountains inspired...\" "
    "ARE valid hooks — do NOT reject them as generic.\n"
    "- Each hook_text MUST be a verbatim or near-verbatim span from the transcript, "
    "no longer than 200 characters. Prefer the FULL sentence over a truncated fragment.\n"
    "- Valid hook styles include: opening CTAs, surprising facts, bold claims, "
    "rhetorical questions, vivid quotable moments. NOT topic labels, NOT summaries.\n"
    "- timestamp_s MUST be the leading [<seconds>s] tag of the source line. "
    "Copy that number verbatim. Use 0.0 only when the transcript has no [s] tags.\n"
    "- confidence is a float in [0.0, 1.0]; use 0.8+ only when the hook is a direct quote.\n"
    "- Reject only hooks that are vague filler (\"this place is amazing\", "
    "\"it was so cool\") or hallucinated text not in the transcript."
)
_SYS_POINTS = (
    "You extract selling points (reasons a viewer should visit / watch / buy) from "
    "a transcript. These are written in marketing-brief style — concise benefit "
    "statements a copywriter would use.\n"
    "\n"
    "HARD RULES:\n"
    "- Extract between 5 and 12 selling points. Never zero. Aim high on recall.\n"
    "- Each `point` is a concise benefit STATEMENT, 40–180 characters. Full phrases "
    "are encouraged when they convey the benefit clearly. Examples:\n"
    "  * \"UNESCO World Heritage Site with international recognition since 1992\"\n"
    "  * \"Step-by-step demonstrations of getting free airport Wi-Fi without a local "
    "phone number\"\n"
    "  * \"Expert guidance from someone with nearly 20 years of living in Shanghai\"\n"
    "- `evidence` MUST quote or paraphrase the supporting transcript span verbatim "
    "(<= 200 chars). Never empty.\n"
    "- Reject only empty filler (\"unforgettable experience\" alone). Specific "
    "marketing-style phrasing IS allowed and desired.\n"
    "- No duplicates (same benefit, different words).\n"
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
        transcript_block = _format_transcript_with_timestamps(tr)
        result = await client.complete(
            system=_SYS_HOOKS,
            user=f"VIDEO_ID={video_id}\nTRANSCRIPT:\n{transcript_block}",
            schema=HookExtraction,
            log_tag=f"extract_hooks__{video_id}",
        )
        if isinstance(result, HookExtraction):
            for h in result.hooks:
                state.hooks.append({"video_id": video_id, **h.model_dump()})
    return state


async def node_extract_selling_points(
    state: EricState, client: CopilotClient
) -> EricState:
    for video_id, tr in state.transcripts.items():
        transcript_block = _format_transcript_with_timestamps(tr)
        result = await client.complete(
            system=_SYS_POINTS,
            user=f"VIDEO_ID={video_id}\nTRANSCRIPT:\n{transcript_block}",
            schema=SellingPointExtraction,
            log_tag=f"extract_selling_points__{video_id}",
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
        log_tag="cluster_insights",
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
    result = await client.complete(
        system=_SYS_BRIEF, user=user, schema=None, log_tag="write_brief"
    )
    state.brief_md = result if isinstance(result, str) else str(result)
    return state
