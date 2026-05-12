"""Baseline runner — wires the live Eric agent through fixtures and writes scores.

Usage:
    python -m scripts.run_baseline --split dev
    python -m scripts.run_baseline --split holdout
    python -m scripts.run_baseline --split all --skip-judge
    python -m scripts.run_baseline --only dev-food-04 dev-vlog-01

Flow per fixture:
  1. load_gold_state -> EricState (transcripts/comments from gold/)
  2. graph.ainvoke (build_llm_graph wrapped in TrackingClient)
  3. compute deterministic metrics (hook_f1, sp_recall, schema_validity)
  4. judge_brief (median-of-3, cached) -> strategy_brief_quality
  5. write scores.json + per-fixture artifacts

Then optionally invoke run_eval.py's gate via --gate.

Idempotent:
  - Skips fixtures whose <run_id>/<fixture_id>.json exists, unless --force.
  - Judge cache lives at gold/../judge_cache.jsonl.
"""
from __future__ import annotations

import argparse
import asyncio
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
from voyager_evals.eric.baseline import run_one_fixture  # noqa: E402
from voyager_evals.eric.gate import (  # noqa: E402
    FixtureResult,
    ThresholdConfig,
    evaluate_fixture,
    evaluate_run,
)
from voyager_evals.eric.judges.brief_judge import judge_brief  # noqa: E402
from voyager_evals.eric.nodes_data_eval import load_gold_state  # noqa: E402
from voyager_evals.eric.reports import write_reports  # noqa: E402

ERIC_DIR = REPO_ROOT / "packages" / "evals" / "voyager_evals" / "eric"
GOLD_DIR = ERIC_DIR / "gold"
SEED_PATH = ERIC_DIR / "seed.yaml"
FIXTURES_DIR = ERIC_DIR / "fixtures"
THRESHOLDS_PATH = ERIC_DIR / "thresholds.yaml"
REPORTS_ROOT = ERIC_DIR / "reports"
JUDGE_CACHE_PATH = ERIC_DIR / "judge_cache.jsonl"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_fixture(fid: str) -> dict[str, Any]:
    p = FIXTURES_DIR / f"{fid}.yaml"
    if not p.exists():
        raise FileNotFoundError(f"fixture not found: {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def _select_fixtures(split: str, only: list[str] | None) -> list[tuple[str, str]]:
    """Return list of (fixture_id, bucket)."""
    seed = yaml.safe_load(SEED_PATH.read_text(encoding="utf-8"))
    splits = ["dev", "holdout"] if split == "all" else [split]
    out: list[tuple[str, str]] = []
    for s in splits:
        bucket = "dev" if s == "dev" else "holdout"
        for entry in seed.get(s, []):
            fid = entry["id"]
            if only and fid not in only:
                continue
            out.append((fid, bucket))
    return out


async def _score_one(
    fixture_id: str,
    bucket: str,
    client: CopilotClaudeClient,
    skip_judge: bool,
    run_dir: Path,
) -> dict[str, Any]:
    fixture_yaml = _load_fixture(fixture_id)
    state = load_gold_state(fixture_id, GOLD_DIR, SEED_PATH)

    t0 = time.monotonic()
    fs = await run_one_fixture(fixture_id, bucket, state, fixture_yaml, client)
    wall = time.monotonic() - t0

    judge_payload: dict[str, Any] = {}
    if not skip_judge and not fs.error and fs.brief_md.strip():
        try:
            judge_payload = await judge_brief(
                fs.brief_md,
                judge_model="gpt-5",
                median_of=3,
                cache_path=JUDGE_CACHE_PATH,
            )
            fs.scores["strategy_brief_quality"] = judge_payload["overall_median"]
        except Exception as e:  # noqa: BLE001
            fs.call_errors.append(f"judge: {type(e).__name__}: {e}")
            fs.scores["strategy_brief_quality"] = 0.0
    elif not skip_judge:
        fs.scores["strategy_brief_quality"] = 0.0

    # Persist per-fixture artifacts
    art_dir = run_dir / "fixtures"
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / f"{fixture_id}.brief.md").write_text(fs.brief_md, encoding="utf-8")
    (art_dir / f"{fixture_id}.json").write_text(
        json.dumps(
            {
                "fixture_id": fixture_id,
                "bucket": bucket,
                "scores": fs.scores,
                "wall_seconds": wall,
                "error": fs.error,
                "hooks_predicted": fs.hooks_predicted,
                "selling_points_predicted": fs.sp_predicted,
                "call_errors": fs.call_errors,
                "judge": {
                    "overall_median": judge_payload.get("overall_median"),
                    "cached": judge_payload.get("cached"),
                    "scores_runs": judge_payload.get("scores_runs"),
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return {
        "fixture_id": fixture_id,
        "bucket": bucket,
        "scores": fs.scores,
        "cost_usd": fs.cost_usd,
        "wall_seconds": wall,
        "error": fs.error,
    }


async def _run(
    split: str,
    only: list[str] | None,
    skip_judge: bool,
    force: bool,
    label: str,
    model: str,
    run_id: str | None,
) -> int:
    run_id = run_id or _utc_stamp()
    run_dir = REPORTS_ROOT / label / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    targets = _select_fixtures(split, only)
    if not targets:
        print(f"[baseline] no fixtures match split={split} only={only}", file=sys.stderr)
        return 2
    print(f"[baseline] run_id={run_id} label={label} split={split} count={len(targets)}")
    print(f"[baseline] reports → {run_dir}")
    print(f"[baseline] judge: {'SKIPPED' if skip_judge else 'gpt-5 median_of=3 cached'}")

    client = CopilotClaudeClient(
        model=model,
        max_retries=3,
        timeout_s=240,
        log_dir=run_dir / "logs",
    )

    scores: list[dict[str, Any]] = []
    failed = 0
    for fid, bucket in targets:
        out_path = run_dir / "fixtures" / f"{fid}.json"
        if out_path.exists() and not force:
            print(f"[skip] {fid} (exists)")
            scores.append(json.loads(out_path.read_text(encoding="utf-8")))
            # Trim to gate-shaped record
            scores[-1] = {
                k: scores[-1].get(k)
                for k in ("fixture_id", "bucket", "scores", "cost_usd", "wall_seconds", "error")
            }
            continue
        print(f"[run]  {fid:24s}  bucket={bucket}")
        try:
            rec = await _score_one(fid, bucket, client, skip_judge, run_dir)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {type(e).__name__}: {e}")
            traceback.print_exc()
            rec = {
                "fixture_id": fid,
                "bucket": bucket,
                "scores": {},
                "cost_usd": 0.0,
                "wall_seconds": 0.0,
                "error": f"{type(e).__name__}: {e}",
            }
            failed += 1
        scores.append(rec)
        s = rec.get("scores") or {}
        if rec.get("error"):
            print(f"  ✗ ERROR: {rec['error']}")
        else:
            print(
                "  ✓ "
                + " | ".join(
                    [
                        f"hook_f1={s.get('hook_extraction_f1', 0):.3f}",
                        f"sp_rec={s.get('selling_point_recall', 0):.3f}",
                        f"schema={s.get('schema_validity_rate', 0):.3f}",
                        f"brief={s.get('strategy_brief_quality', 0):.2f}",
                        f"wall={rec.get('wall_seconds', 0):.1f}s",
                    ]
                )
            )

    scores_path = run_dir / "scores.json"
    scores_path.write_text(
        json.dumps(scores, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n[baseline] wrote {scores_path}")

    # Gate
    config = ThresholdConfig.load(THRESHOLDS_PATH)
    fixtures = [
        evaluate_fixture(
            fixture_id=s["fixture_id"],
            bucket=s["bucket"],
            scores=s.get("scores") or {},
            config=config,
            cost_usd=float(s.get("cost_usd", 0.0)),
            wall_seconds=float(s.get("wall_seconds", 0.0)),
            error=s.get("error"),
        )
        for s in scores
    ]
    run = evaluate_run(fixtures, config, label=label)
    out = write_reports(run, reports_root=str(REPORTS_ROOT), run_id=run_id)
    print(f"\n[baseline] {'PASS' if run.passed else 'FAIL'} → {out}")
    print(f"  dev_pass_rate     = {run.dev_pass_rate:.2%}")
    print(f"  holdout_pass_rate = {run.holdout_pass_rate:.2%}")
    print(f"  total_cost_usd    = ${run.total_cost_usd:.4f}")
    print(f"  total_wall_s      = {run.total_wall_seconds:.1f}")
    if run.failures:
        print("  failures:")
        for f in run.failures:
            print(f"   - {f}")
    return 0 if run.passed and not failed else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="Run Eric eval baseline.")
    ap.add_argument("--split", default="all", choices=["dev", "holdout", "all"])
    ap.add_argument("--only", nargs="*", default=None, help="Only these fixture ids")
    ap.add_argument("--skip-judge", action="store_true", help="Skip GPT-5 brief judge")
    ap.add_argument("--force", action="store_true", help="Re-run even if cached")
    ap.add_argument("--label", default="baseline")
    ap.add_argument("--model", default="claude-sonnet-4.5")
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()
    sys.exit(
        asyncio.run(
            _run(
                split=args.split,
                only=args.only,
                skip_judge=args.skip_judge,
                force=args.force,
                label=args.label,
                model=args.model,
                run_id=args.run_id,
            )
        )
    )


if __name__ == "__main__":
    main()
