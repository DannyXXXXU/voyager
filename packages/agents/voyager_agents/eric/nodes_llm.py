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
    # P1: scratchpad forces the model to reason about coverage BEFORE emitting
    # the final list. Empty default so existing stub clients still validate.
    scratchpad: str = ""
    hooks: list[Hook] = Field(default_factory=list)


class SellingPoint(BaseModel):
    point: str
    evidence: str = ""
    confidence: float = 0.5


class SellingPointExtraction(BaseModel):
    scratchpad: str = ""
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
_SYS_HOOKS = """<role>
You are a senior YouTube content strategist analyzing China travel videos for
overseas growth. Your job is to extract the attention-grabbing HOOKS from a
transcript — the exact lines a creator would use to STOP a viewer from
scrolling.
</role>

<task>
Read the transcript (each line tagged with [<seconds>s]) and emit between
8 and 16 hooks. Aim HIGH on recall — when in doubt, INCLUDE. Missing a real
hook costs us much more than including a borderline one.
</task>

<rules>
1. Each hook_text MUST be a verbatim or near-verbatim span from the transcript,
   <=200 chars. Prefer the FULL sentence over a truncated fragment.
2. ALWAYS include opening hook(s) from the first 30 seconds. Opening CTAs like
   "Did you know...", "Stick around...", "If you're going to X for the first
   time..." ARE valid hooks — never reject them as generic.
3. PRIORITIZE these high-value types whenever present:
   - Numeric / record claims ("20,000 visitors a day", "350 meters high")
   - Superlatives / firsts ("world's tallest", "highest-grossing ever")
   - Warnings / safety beats ("wait until the timer rings or you'll hallucinate")
   - Vivid contrasts / reactions ("are we on a movie set?", "defies gravity")
   - Named specific nouns reacted to with surprise/disgust/excitement
     ("chilled black tiger feet", "jian shou qing mushroom") — these short
     specific-noun hooks are the MOST-MISSED type and you must extract every
     single one that gets a creator reaction.
4. ONE HOOK = ONE DISTINCT CLAIM. Split compound sentences. A list of three
   dish names = THREE hooks. A sentence with a warning + a vivid reference =
   TWO hooks.
5. timestamp_s MUST be the leading [<seconds>s] tag of the source line, copied
   verbatim. Use 0.0 only when the line has no tag.
6. confidence in [0.0, 1.0]; >=0.8 only when the hook is a direct quote.
7. Reject ONLY vague filler ("this place is amazing", "it was so cool") or
   text not in the transcript.
</rules>

<examples>
<example id="food-extreme-spicy">
TRANSCRIPT (excerpt):
[0.0s] today we're gonna attempt to eat the world's spiciest hot pot, so spicy you might start hallucinating
[12.4s] look at all those chilies, that's crazy. your nose is numbing just from being here
[45.8s] today we're gonna be meeting up with the Chinese Trump, and he's taking us for a full-on ultra-spicy food tour
[120.0s] chilled black tiger feet, jian shou qing mushroom, and porcini soup — death-level spicy beef

GOOD HOOKS (note: short specific-noun reactions extracted as separate items):
- "we're gonna attempt to eat the world's spiciest hot pot, so spicy you might start hallucinating" @ 0.0s
- "Look at all those chilies, that's crazy. Your nose is numbing just from being here" @ 12.4s
- "today, we're gonna be meeting up with the Chinese Trump, and he's taking us for a full-on, ultra-spicy food tour" @ 45.8s
- "chilled black tiger feet" @ 120.0s
- "jian shou qing mushroom" @ 120.0s
- "death-level spicy beef" @ 120.0s
</example>

<example id="travel-superlative">
TRANSCRIPT (excerpt):
[3.2s] this elevator is 350 meters high — a three-lane double-decker, the only one of its kind in the world
[88.0s] are we on a movie set? this defies gravity

GOOD HOOKS (numeric claim + superlative split; vivid reaction is its own hook):
- "this elevator is 350 meters high" @ 3.2s
- "a three-lane double-decker, the only one of its kind in the world" @ 3.2s
- "are we on a movie set? this defies gravity" @ 88.0s
</example>
</examples>

<output>
Return JSON matching this schema:
{
  "scratchpad": "<1-3 sentences: which hook TYPES did you find — numeric? superlative? named specific noun? opening CTA? Any 30s-opener you might miss? Then commit to extracting all of them.>",
  "hooks": [ {"hook_text": "...", "timestamp_s": 0.0, "confidence": 0.0}, ... ]
}
Fill scratchpad FIRST, then list hooks. Target 8-16 hooks.
</output>
"""

_SYS_POINTS = """<role>
You are a marketing copywriter for an overseas creator brand. Extract the
SELLING POINTS — the reasons a viewer should watch / visit / care — from a
transcript, written as concise benefit statements.
</role>

<task>
Emit between 8 and 18 selling points. Eric over-producing is fine (Mike filters
downstream). Under-producing is the failure mode. When in doubt, INCLUDE.
</task>

<rules>
1. Each `point` is a concise benefit STATEMENT, 40-180 chars, marketing-brief
   style. NOT a bare topic label. NOT a quote.
2. `evidence` MUST quote or paraphrase the supporting transcript span
   (<=200 chars). Never empty.
3. Cover BOTH content benefits (what you'll see / taste / experience) AND
   creator-expertise benefits (host credibility, behind-the-scenes access).
4. No duplicates — same benefit in different words = ONE point.
5. confidence in [0.0, 1.0]; >=0.8 only when evidence is a direct quote.
</rules>

<examples>
<example id="food-chongqing">
TRANSCRIPT (excerpt):
[15.0s] meeting up with the Chinese Trump, taking us for a full-on ultra-spicy food tour
[120.0s] this chef has been making hot pot base from scratch for 10 years
[200.0s] chongqing — the manhattan of mountains, cyberpunk cityscape

GOOD SELLING POINTS:
- point: "Extreme spicy food challenge with progressively hotter dishes culminating in the world's spiciest hot pot"
  evidence: "we're gonna attempt to eat the world's spiciest hot pot"
- point: "Entertaining collaboration with charismatic 'Chinese Trump' local guide who provides humor and authentic insights"
  evidence: "meeting up with the Chinese Trump, taking us for a full-on ultra-spicy food tour"
- point: "Behind-the-scenes look at traditional food preparation including 10-year veteran chef making hot pot base from scratch"
  evidence: "this chef has been making hot pot base from scratch for 10 years"
- point: "Exploration of Chongqing's unique cyberpunk cityscape described as 'Manhattan of mountains'"
  evidence: "chongqing — the manhattan of mountains, cyberpunk cityscape"
</example>
</examples>

<output>
Return JSON matching this schema:
{
  "scratchpad": "<1-3 sentences: list the benefit CATEGORIES present in this transcript (content benefits + creator-expertise benefits). Did you cover both? Are you at 8+ items?>",
  "selling_points": [ {"point": "...", "evidence": "...", "confidence": 0.0}, ... ]
}
Fill scratchpad FIRST, then list selling_points. Target 8-18 items.
</output>
"""
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
