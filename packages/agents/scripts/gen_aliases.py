"""Generate paraphrase aliases for dev gold hooks/selling-points.

For each fixtures/dev-*.yaml (skips holdout==true), call Copilot Claude once
with all gold items in that fixture and ask for 3 short paraphrase aliases per
item (semantic-equivalent, different surface). Writes back into the yaml's
`aliases:` lists in-place. Skips items that already have aliases.

Usage:
  uv run --project packages/agents python scripts/gen_aliases.py [--dry-run]
"""
from __future__ import annotations

import argparse
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

SYSTEM = (
    "You generate paraphrase aliases for evaluation gold items. "
    "Given a list of gold items (hooks or selling points) extracted from a "
    "video transcript, produce exactly 3 short paraphrases per item. "
    "Each paraphrase MUST: (a) preserve the same factual claim/meaning, "
    "(b) use different surface words (no trivial reorderings), "
    "(c) be 4-20 words, plain English, no markdown, no quotes. "
    "Do NOT invent new facts or numbers not present in the original. "
    "Return strictly valid JSON matching the schema."
)


class AliasItem(BaseModel):
    index: int = Field(..., description="0-based index of the gold item")
    aliases: list[str] = Field(..., min_length=3, max_length=3)


class AliasBatch(BaseModel):
    items: list[AliasItem]


def build_user(kind: str, items: list[str]) -> str:
    listed = "\n".join(f"{i}. {t}" for i, t in enumerate(items))
    return (
        f"Gold items (kind={kind}):\n{listed}\n\n"
        "Return JSON: {\"items\":[{\"index\":0,\"aliases\":[...3 strings]}, ...]}"
    )


async def process_fixture(client: CopilotClaudeClient, fp: Path, dry: bool) -> dict:
    data = yaml.safe_load(fp.read_text())
    if data.get("holdout"):
        return {"file": fp.name, "skipped": "holdout"}
    changed = False
    summary = {"file": fp.name, "hooks_filled": 0, "sp_filled": 0}

    for kind, key in [("hooks", "gold_hooks"), ("selling_points", "gold_selling_points")]:
        items = data.get(key) or []
        # collect indices that need aliases
        need_idx = [i for i, it in enumerate(items) if not (it.get("aliases") or [])]
        if not need_idx:
            continue
        texts = [items[i].get("text", "") for i in need_idx]
        user = build_user(kind, texts)
        result = await client.complete(
            system=SYSTEM, user=user, schema=AliasBatch,
            log_tag=f"alias-{fp.stem}-{kind}",
        )
        # result is AliasBatch
        by_idx = {a.index: a.aliases for a in result.items}
        for local_i, gold_i in enumerate(need_idx):
            aliases = by_idx.get(local_i)
            if not aliases:
                continue
            items[gold_i]["aliases"] = aliases
            changed = True
            summary["hooks_filled" if kind == "hooks" else "sp_filled"] += 1

    if changed and not dry:
        fp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    summary["written"] = changed and not dry
    return summary


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", help="process only this fixture id (e.g. dev-food-03)")
    args = ap.parse_args()

    client = CopilotClaudeClient(
        log_dir=ROOT / "packages/evals/voyager_evals/eric/reports/_alias_logs",
    )

    files = sorted(FIX_DIR.glob("dev-*.yaml"))
    if args.only:
        files = [f for f in files if f.stem == args.only]

    results = []
    for fp in files:
        print(f"[gen_aliases] processing {fp.name}", flush=True)
        try:
            r = await process_fixture(client, fp, args.dry_run)
        except Exception as e:  # noqa: BLE001
            r = {"file": fp.name, "error": f"{type(e).__name__}: {e}"}
        print(f"  -> {r}", flush=True)
        results.append(r)

    out = ROOT / "packages/evals/voyager_evals/eric/reports/_alias_logs/summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print(f"[gen_aliases] summary → {out}")


if __name__ == "__main__":
    asyncio.run(main())
