"""Rescore an existing eval run with current gold (e.g. after aliases were added).

Re-reads each report-dir/fixtures/dev-*.json (hooks_predicted, sp_predicted),
re-runs match_hooks() and selling_point_recall() against the current
fixtures/<id>.yaml gold (which now has aliases), and writes:
  <report-dir>/scores_rescored.json
  <report-dir>/fixtures_rescored.json
  <report-dir>/summary_rescored.md

Holdout untouched. Read-only on the run dir; only writes *_rescored.* siblings.

Usage:
  uv run --project packages/evals python scripts/rescore_with_aliases.py \\
    --run-dir packages/evals/voyager_evals/eric/reports/p0.8-rerun/<ts>
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
    args = ap.parse_args()
    run_dir = Path(args.run_dir).resolve()
    fix_json_dir = run_dir / "fixtures"
    if not fix_json_dir.is_dir():
        sys.exit(f"no fixtures/ dir under {run_dir}")

    per_fixture: list[dict] = []
    rows: list[tuple] = []
    for fp in sorted(fix_json_dir.glob("*.json")):
        rec = json.loads(fp.read_text())
        fid = rec["fixture_id"]
        gold_fp = FIX_DIR / f"{fid}.yaml"
        if not gold_fp.exists():
            continue
        gold = yaml.safe_load(gold_fp.read_text())
        gold_hooks = gold.get("gold_hooks") or []
        gold_sp = gold.get("gold_selling_points") or []
        h_pred = rec.get("hooks_predicted") or []
        sp_pred = rec.get("selling_points_predicted") or rec.get("sp_predicted") or []

        hm = match_hooks(h_pred, gold_hooks)
        spr = selling_point_recall(sp_pred, gold_sp)

        new_scores = dict(rec.get("scores") or {})
        old_h = new_scores.get("hook_extraction_f1", 0.0)
        old_sp = new_scores.get("selling_point_recall", 0.0)
        new_scores["hook_extraction_f1"] = hm.f1
        new_scores["selling_point_recall"] = spr

        per_fixture.append({
            "fixture_id": fid,
            "bucket": rec.get("bucket"),
            "scores_old": rec.get("scores"),
            "scores": new_scores,
        })
        rows.append((fid, old_h, hm.f1, old_sp, spr))

    out_scores = run_dir / "scores_rescored.json"
    out_scores.write_text(json.dumps({"per_fixture": per_fixture}, indent=2))

    # summary table
    rows.sort()
    lines = [
        "# Rescored with aliases\n",
        "| fixture | hook_f1 (old → new) | sp_recall (old → new) |",
        "|---|---|---|",
    ]
    for fid, oh, nh, osp, nsp in rows:
        lines.append(f"| {fid} | {oh:.3f} → {nh:.3f} ({nh-oh:+.3f}) | {osp:.3f} → {nsp:.3f} ({nsp-osp:+.3f}) |")
    mh_old = mean(r[1] for r in rows)
    mh_new = mean(r[2] for r in rows)
    sp_old = mean(r[3] for r in rows)
    sp_new = mean(r[4] for r in rows)
    lines.append(f"| **mean** | **{mh_old:.3f} → {mh_new:.3f} ({mh_new-mh_old:+.3f})** | **{sp_old:.3f} → {sp_new:.3f} ({sp_new-sp_old:+.3f})** |")
    (run_dir / "summary_rescored.md").write_text("\n".join(lines))

    print(f"wrote {out_scores}")
    print(f"hook_f1 mean : {mh_old:.3f} → {mh_new:.3f} ({mh_new-mh_old:+.3f})")
    print(f"sp_recall    : {sp_old:.3f} → {sp_new:.3f} ({sp_new-sp_old:+.3f})")


if __name__ == "__main__":
    main()
