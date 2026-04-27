"""Task 1.19d — agent-drafts gold fixtures for the 15 dev seed videos.

For each dev fixture in seed.yaml, this script:
  1. loads the pre-fetched gold transcript+comments (from gold/),
  2. runs the Eric LLM subgraph (extract_hooks → extract_selling_points →
     cluster_insights → write_brief) using the real CopilotClaudeClient,
  3. writes a draft EricFixture YAML to fixtures/<id>.yaml for Danny to review.

Holdout fixtures are NOT drafted — those are stubbed empty by Task 1.19e
and labeled by Danny manually; agent must never see them in advance.

Idempotent / resumable:
  - Skips fixtures whose output file already exists, unless --force.
  - On per-fixture failure, logs and continues (writes <id>.error.txt).

Cost: ~3 Copilot Premium requests per LLM call × 4 nodes × 15 videos ≈ 180
premium requests. Brief stage is freeform Markdown (no schema retry).
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packages" / "agents"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "evals"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "tools"))

from voyager_agents.eric.copilot_client import CopilotClaudeClient  # noqa: E402
from voyager_agents.eric.graph import build_llm_graph  # noqa: E402
from voyager_evals.eric.nodes_data_eval import load_gold_state  # noqa: E402

ERIC_DIR = REPO_ROOT / "packages" / "evals" / "voyager_evals" / "eric"
GOLD_DIR = ERIC_DIR / "gold"
SEED_PATH = ERIC_DIR / "seed.yaml"
FIXTURES_DIR = ERIC_DIR / "fixtures"


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _to_alias_list(text: str, raw_aliases: list[str] | None = None) -> list[str]:
    """Default aliases empty; Danny can add paraphrases during review."""
    return [a for a in (raw_aliases or []) if a and a != text]


async def _draft_one(
    fixture_id: str,
    client: CopilotClaudeClient,
    seed_entry: dict[str, Any],
) -> dict[str, Any]:
    state = load_gold_state(fixture_id, GOLD_DIR, SEED_PATH)
    graph = build_llm_graph(client).compile()

    t0 = time.monotonic()
    final = await graph.ainvoke(state)
    elapsed = time.monotonic() - t0

    # final is a dict (LangGraph returns dict-coerced state by default)
    hooks = final.get("hooks", []) if isinstance(final, dict) else final.hooks
    points = (
        final.get("selling_points", [])
        if isinstance(final, dict)
        else final.selling_points
    )
    brief_md = (
        final.get("brief_md") if isinstance(final, dict) else final.brief_md
    ) or ""

    transcript = state.transcripts[seed_entry["video_id"]]
    transcript_sha = _sha256_text(transcript.text)

    gold_hooks = [
        {
            "text": h.get("hook_text", ""),
            "aliases": _to_alias_list(h.get("hook_text", "")),
            "timestamp_s": float(h.get("timestamp_s") or 0.0),
        }
        for h in hooks
        if h.get("hook_text")
    ]
    gold_points = [
        {
            "text": p.get("point", ""),
            "aliases": _to_alias_list(p.get("point", "")),
        }
        for p in points
        if p.get("point")
    ]

    fixture: dict[str, Any] = {
        "id": seed_entry["id"],
        "video_id": seed_entry["video_id"],
        "topic": seed_entry["topic"],
        "difficulty": seed_entry["difficulty"],
        "content_type": seed_entry["content_type"],
        "holdout": seed_entry.get("holdout", False),
        "gold_hooks": gold_hooks,
        "gold_selling_points": gold_points,
        "notes": seed_entry.get("notes", ""),
        "transcript_sha256": transcript_sha,
        "_meta": {
            "drafted_by": "agent",
            "drafted_at_utc": datetime.now(timezone.utc).isoformat(),
            "model": client._model,  # noqa: SLF001
            "wall_seconds": round(elapsed, 1),
            "review_status": "pending",
            "draft_brief_md_path": f"{fixture_id}.brief.md",
        },
    }
    return {"fixture": fixture, "brief_md": brief_md}


async def _run(force: bool, only: list[str] | None, model: str) -> int:
    seed = yaml.safe_load(SEED_PATH.read_text(encoding="utf-8"))
    dev_entries = seed.get("dev", [])
    if only:
        dev_entries = [e for e in dev_entries if e["id"] in set(only)]

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    client = CopilotClaudeClient(model=model, max_retries=2, timeout_s=240)

    summary: list[dict[str, Any]] = []
    failed = 0
    for entry in dev_entries:
        fid = entry["id"]
        out_path = FIXTURES_DIR / f"{fid}.yaml"
        if out_path.exists() and not force:
            print(f"[skip] {fid} (exists)")
            summary.append({"id": fid, "status": "skipped"})
            continue
        print(f"[draft] {fid}  topic={entry['topic'][:60]!r}")
        try:
            res = await _draft_one(fid, client, entry)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ failed: {type(e).__name__}: {e}")
            (FIXTURES_DIR / f"{fid}.error.txt").write_text(
                traceback.format_exc(), encoding="utf-8"
            )
            failed += 1
            summary.append({"id": fid, "status": "error", "error": str(e)})
            continue

        fixture = res["fixture"]
        brief_md = res["brief_md"]
        out_path.write_text(
            yaml.safe_dump(fixture, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        (FIXTURES_DIR / f"{fid}.brief.md").write_text(brief_md, encoding="utf-8")
        print(
            f"  ✓ hooks={len(fixture['gold_hooks'])} "
            f"points={len(fixture['gold_selling_points'])} "
            f"brief={len(brief_md)}c "
            f"wall={fixture['_meta']['wall_seconds']}s"
        )
        summary.append(
            {
                "id": fid,
                "status": "ok",
                "hooks": len(fixture["gold_hooks"]),
                "points": len(fixture["gold_selling_points"]),
                "wall_seconds": fixture["_meta"]["wall_seconds"],
            }
        )

    summary_path = FIXTURES_DIR / "_draft_report.json"
    summary_path.write_text(
        json.dumps(
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "model": model,
                "results": summary,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nReport: {summary_path}")
    print(
        f"OK: {sum(1 for s in summary if s['status']=='ok')} | "
        f"Skipped: {sum(1 for s in summary if s['status']=='skipped')} | "
        f"Failed: {failed}"
    )
    return 1 if failed else 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Draft Eric eval gold fixtures.")
    ap.add_argument("--force", action="store_true", help="Overwrite existing fixtures")
    ap.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Only draft these fixture ids (e.g. dev-food-01 dev-vlog-01)",
    )
    ap.add_argument("--model", default="claude-sonnet-4.5")
    args = ap.parse_args()
    sys.exit(asyncio.run(_run(args.force, args.only, args.model)))


if __name__ == "__main__":
    main()
