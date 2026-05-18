"""Rescore an existing eval run using per-bucket cosine thresholds
(dev=0.65, holdout=0.75) and re-evaluate the metrics gate via gate.py
(which now honors per-bucket metric thresholds from thresholds.yaml).

Writes:
  <run-dir>/scores_perbucket.json
  <run-dir>/summary_perbucket.md
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
from voyager_evals.eric.gate import (  # noqa: E402
    ThresholdConfig,
    evaluate_fixture,
    evaluate_run,
)

FIX_DIR = ROOT / "packages/evals/voyager_evals/eric/fixtures"
THRESHOLDS = ROOT / "packages/evals/voyager_evals/eric/thresholds.yaml"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    args = ap.parse_args()
    run_dir = Path(args.run_dir).resolve()
    fix_json_dir = run_dir / "fixtures"
    if not fix_json_dir.is_dir():
        sys.exit(f"no fixtures/ dir under {run_dir}")

    cfg = ThresholdConfig.load(THRESHOLDS)
    cos = yaml.safe_load(THRESHOLDS.read_text()).get("match_cosine_threshold") or {}
    cos_dev = float(cos.get("dev", 0.65))
    cos_hold = float(cos.get("holdout", 0.75))

    per_fixture: list[dict] = []
    fixture_results = []
    for fp in sorted(fix_json_dir.glob("*.json")):
        rec = json.loads(fp.read_text())
        fid = rec["fixture_id"]
        bucket = rec.get("bucket") or "dev"
        gold_fp = FIX_DIR / f"{fid}.yaml"
        if not gold_fp.exists():
            continue
        gold = yaml.safe_load(gold_fp.read_text())
        gold_hooks = gold.get("gold_hooks") or []
        gold_sp = gold.get("gold_selling_points") or []
        h_pred = rec.get("hooks_predicted") or []
        sp_pred = rec.get("selling_points_predicted") or rec.get("sp_predicted") or []
        th = cos_dev if bucket == "dev" else cos_hold

        hm = match_hooks(h_pred, gold_hooks, threshold=th)
        spr = selling_point_recall(sp_pred, gold_sp, threshold=th)

        new_scores = dict(rec.get("scores") or {})
        new_scores["hook_extraction_f1"] = hm.f1
        new_scores["selling_point_recall"] = spr

        res = evaluate_fixture(
            fixture_id=fid,
            bucket=bucket,
            scores=new_scores,
            config=cfg,
            cost_usd=rec.get("cost_usd", 0.0),
            wall_seconds=rec.get("wall_seconds", 0.0),
        )
        fixture_results.append(res)
        per_fixture.append({
            "fixture_id": fid,
            "bucket": bucket,
            "scores": new_scores,
            "passed": res.passed,
            "failed_metrics": res.failed_metrics,
        })

    run_res = evaluate_run(fixture_results, cfg, label="p1-full-rescored-perbucket")

    (run_dir / "scores_perbucket.json").write_text(
        json.dumps({"per_fixture": per_fixture}, indent=2)
    )

    lines = [
        "# Per-bucket rescore (dev cos=0.65, holdout cos=0.75; gate honors per-bucket hook_f1)",
        "",
        f"- dev_pass_rate:    **{run_res.dev_pass_rate:.2%}** (gate {cfg.required_pass_rate:.0%})",
        f"- holdout_pass_rate: **{run_res.holdout_pass_rate:.2%}** (gate {cfg.holdout_required_pass_rate:.0%})",
        f"- run_passed: **{run_res.passed}**",
        f"- failures: {run_res.failures or 'none'}",
        "",
        "| bucket | fixture | hook_f1 | sp_recall | schema | passed | failed |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in fixture_results:
        sc = r.scores
        lines.append(
            f"| {r.bucket} | {r.fixture_id} | {sc.get('hook_extraction_f1',0):.3f} "
            f"| {sc.get('selling_point_recall',0):.3f} "
            f"| {sc.get('schema_validity_rate',0):.2f} "
            f"| {'✓' if r.passed else '✗'} | {','.join(r.failed_metrics) or '-'} |"
        )

    def _m(rs, key):
        return mean(r.scores.get(key, 0.0) for r in rs) if rs else 0.0

    dev = [r for r in fixture_results if r.bucket == "dev"]
    hold = [r for r in fixture_results if r.bucket == "holdout"]
    lines += [
        "",
        f"- DEV mean: hook_f1={_m(dev,'hook_extraction_f1'):.3f}, sp_recall={_m(dev,'selling_point_recall'):.3f}",
        f"- HOLDOUT mean: hook_f1={_m(hold,'hook_extraction_f1'):.3f}, sp_recall={_m(hold,'selling_point_recall'):.3f}",
    ]

    out = run_dir / "summary_perbucket.md"
    out.write_text("\n".join(lines))
    print(out.read_text())


if __name__ == "__main__":
    main()
