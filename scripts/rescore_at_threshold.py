"""Rescore an existing eval run with a configurable cosine threshold.

Unlike rescore_with_aliases.py (which assumes the metric default), this one
re-runs match_hooks() / selling_point_recall() at a user-specified threshold.
Use to test the dev-threshold-relaxation hypothesis WITHOUT touching gold
or rerunning the LLM agent.

Writes <run-dir>/scores_t<th>.json and summary_t<th>.md.
Holdout fixtures rescored at the SAME threshold for visibility, but the
production gate still uses 0.75 on holdout.

Usage:
  uv run --project packages/evals python scripts/rescore_at_threshold.py \\
    --run-dir packages/evals/voyager_evals/eric/reports/p0.9-rerun/<ts> \\
    --threshold 0.65
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean

import yaml

ROOT = Path.home() / "projects/voyager"
sys.path.insert(0, str(ROOT / "packages/evals"))

from voyager_evals.eric.metrics import (  # noqa: E402
    match_hooks,
    selling_point_recall,
)

FIX_DIR = ROOT / "packages/evals/voyager_evals/eric/fixtures"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--threshold", type=float, required=True)
    args = ap.parse_args()
    th = args.threshold
    run_dir = Path(args.run_dir).resolve()
    fix_json_dir = run_dir / "fixtures"
    if not fix_json_dir.is_dir():
        sys.exit(f"no fixtures/ dir under {run_dir}")

    per_fixture: list[dict] = []
    rows: list[tuple] = []
    for fp in sorted(fix_json_dir.glob("*.json")):
        rec = json.loads(fp.read_text())
        fid = rec["fixture_id"]
        bucket = rec.get("bucket")
        gold_fp = FIX_DIR / f"{fid}.yaml"
        if not gold_fp.exists():
            continue
        gold = yaml.safe_load(gold_fp.read_text())
        gold_hooks = gold.get("gold_hooks") or []
        gold_sp = gold.get("gold_selling_points") or []
        h_pred = rec.get("hooks_predicted") or []
        sp_pred = rec.get("selling_points_predicted") or rec.get("sp_predicted") or []

        hm = match_hooks(h_pred, gold_hooks, threshold=th)
        spr = selling_point_recall(sp_pred, gold_sp, threshold=th)

        new_scores = dict(rec.get("scores") or {})
        old_h = new_scores.get("hook_extraction_f1", 0.0)
        old_sp = new_scores.get("selling_point_recall", 0.0)
        new_scores["hook_extraction_f1"] = hm.f1
        new_scores["selling_point_recall"] = spr

        per_fixture.append({
            "fixture_id": fid,
            "bucket": bucket,
            "scores_old": rec.get("scores"),
            "scores": new_scores,
        })
        rows.append((bucket, fid, old_h, hm.f1, old_sp, spr))

    out_scores = run_dir / f"scores_t{th:.2f}.json"
    out_scores.write_text(json.dumps({"threshold": th, "per_fixture": per_fixture}, indent=2))

    rows.sort()
    lines = [
        f"# Rescored at threshold {th:.2f}\n",
        "| bucket | fixture | hook_f1 (old → new) | sp_recall (old → new) |",
        "|---|---|---|---|",
    ]
    for bucket, fid, oh, nh, osp, nsp in rows:
        lines.append(
            f"| {bucket} | {fid} | {oh:.3f} → {nh:.3f} ({nh-oh:+.3f}) "
            f"| {osp:.3f} → {nsp:.3f} ({nsp-osp:+.3f}) |"
        )

    # split mean by bucket
    def _mean(rs, idx):
        return mean(r[idx] for r in rs) if rs else 0.0

    dev_rows = [r for r in rows if r[0] == "dev"]
    hold_rows = [r for r in rows if r[0] == "holdout"]
    for label, rs in [("DEV", dev_rows), ("HOLDOUT", hold_rows)]:
        if not rs:
            continue
        lines.append(
            f"| **{label} mean** | — "
            f"| **{_mean(rs, 2):.3f} → {_mean(rs, 3):.3f} "
            f"({_mean(rs, 3) - _mean(rs, 2):+.3f})** "
            f"| **{_mean(rs, 4):.3f} → {_mean(rs, 5):.3f} "
            f"({_mean(rs, 5) - _mean(rs, 4):+.3f})** |"
        )

    # pass count under standard gates (f1>=0.75 / recall>=0.70) for the NEW scores
    def _passes_metric_gate(nh, nsp):
        # mirrors thresholds.yaml: hook_extraction_f1 ≥0.75 and sp_recall ≥0.70
        return nh >= 0.75 and nsp >= 0.70

    dev_pass = sum(1 for r in dev_rows if _passes_metric_gate(r[3], r[5]))
    hold_pass = sum(1 for r in hold_rows if _passes_metric_gate(r[3], r[5]))
    lines.append("")
    lines.append("## Gate (metrics-only; ignores brief-quality)")
    lines.append(f"- dev pass: {dev_pass}/{len(dev_rows)} (need ≥0.80 = {int(0.8*len(dev_rows))})")
    lines.append(f"- holdout pass: {hold_pass}/{len(hold_rows)} (need 100%)")

    (run_dir / f"summary_t{th:.2f}.md").write_text("\n".join(lines))
    print((run_dir / f"summary_t{th:.2f}.md").read_text())


if __name__ == "__main__":
    main()
