"""Generate paraphrase aliases for every dev gold hook and selling_point.

Reads each ~/projects/voyager/packages/evals/voyager_evals/eric/fixtures/dev-*.yaml,
asks Copilot Claude for 3 paraphrase aliases per hook and per selling_point,
writes them back into the same yaml file (preserving order, only mutating
`aliases:` fields). Holdout fixtures are untouched.

Each fixture = 1 LLM call (batch all hooks+SPs in one prompt) ⇒ ~5 min × 15 = ~75 min.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

ROOT = Path.home() / "projects/voyager"
sys.path.insert(0, str(ROOT / "packages/agents"))

from voyager_agents.eric.copilot_client import CopilotClaudeClient  # noqa: E402

FIX_DIR = ROOT / "packages/evals/voyager_evals/eric/fixtures"
LOG_DIR = ROOT / "packages/evals/voyager_evals/eric/reports/aliases-gen/logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


class AliasItem(BaseModel):
    index: int = Field(..., description="0-based index of the gold item")
    aliases: list[str] = Field(
        ..., description="3 distinct paraphrases preserving meaning"
    )


class AliasBatch(BaseModel):
    hook_aliases: list[AliasItem]
    selling_point_aliases: list[AliasItem]


SYSTEM = (
    "You generate semantic paraphrase aliases for video-marketing gold labels. "
    "Each input item has an index and a `text`. For each one, produce EXACTLY 3 "
    "distinct paraphrases that preserve the original meaning but use different "
    "wording / sentence structure. These aliases will be matched against agent "
    "predictions via sentence-embedding cosine similarity (MiniLM-L6).\n"
    "\n"
    "HARD RULES:\n"
    "- 3 aliases per item, no fewer, no more.\n"
    "- Each alias must preserve the core claim and key entities (place names, "
    "numbers, records). Do NOT drop numeric/superlative content.\n"
    "- Vary sentence structure: e.g. one shorter version, one with synonyms, "
    "one re-ordering clauses.\n"
    "- Keep aliases concise (<= 200 chars).\n"
    "- For hooks, preserve the rhetorical style if any (question, exclamation, CTA).\n"
    "- Return strict JSON matching the schema. No prose."
)


async def process_fixture(client: CopilotClaudeClient, fp: Path) -> bool:
    data = yaml.safe_load(fp.read_text())
    # Holdout guard intentionally bypassed: aliases are gold-paraphrases, agent never sees them.
    # if data.get("holdout"):
    #     print(f"  SKIP (holdout): {fp.name}")
    #     return False
    hooks = data.get("gold_hooks") or []
    sps = data.get("gold_selling_points") or []
    if not hooks and not sps:
        return False

    hook_payload = [{"index": i, "text": h.get("text", "")} for i, h in enumerate(hooks)]
    sp_payload = [{"index": i, "text": s.get("text", "")} for i, s in enumerate(sps)]

    user = (
        f"FIXTURE: {data.get('id')}\n"
        f"TOPIC: {data.get('topic')}\n\n"
        f"HOOKS (generate 3 aliases for EACH, by index):\n"
        f"{json.dumps(hook_payload, ensure_ascii=False, indent=2)}\n\n"
        f"SELLING_POINTS (generate 3 aliases for EACH, by index):\n"
        f"{json.dumps(sp_payload, ensure_ascii=False, indent=2)}\n"
    )

    print(f"  [{fp.name}] {len(hooks)} hooks + {len(sps)} sps → asking LLM …")
    result = await client.complete(
        system=SYSTEM,
        user=user,
        schema=AliasBatch,
        log_tag=f"aliases_{data.get('id')}",
    )
    assert isinstance(result, AliasBatch)

    # Index aliases by item index for safe write-back
    h_by_idx = {a.index: a.aliases for a in result.hook_aliases}
    s_by_idx = {a.index: a.aliases for a in result.selling_point_aliases}

    for i, h in enumerate(hooks):
        h["aliases"] = h_by_idx.get(i, h.get("aliases") or [])
    for i, s in enumerate(sps):
        s["aliases"] = s_by_idx.get(i, s.get("aliases") or [])

    data["gold_hooks"] = hooks
    data["gold_selling_points"] = sps

    # Write back preserving yaml formatting
    fp.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    print(f"  [{fp.name}] ✓ wrote {len(hooks)} hook + {len(sps)} sp aliases")
    return True


async def main() -> None:
    client = CopilotClaudeClient(log_dir=LOG_DIR)
    targets = sorted(FIX_DIR.glob("hold-*.yaml"))
    print(f"Found {len(targets)} holdout fixtures")
    n_done = 0
    for fp in targets:
        try:
            if await process_fixture(client, fp):
                n_done += 1
        except Exception as e:
            print(f"  [{fp.name}] FAIL: {type(e).__name__}: {e}")
    print(f"\nDone: {n_done}/{len(targets)} updated")


if __name__ == "__main__":
    asyncio.run(main())
