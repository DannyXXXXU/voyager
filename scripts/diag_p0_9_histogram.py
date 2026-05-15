"""Histogram diagnostic per llm-eval-regression-diagnosis skill §Second-order.

For each of the worst-3 dev fixtures from P0.9 rerun, take each unmatched
gold item and compute max(cos_sim(gold_surfaces, predictions)). Bucket:
  >= 0.75               already matched
  0.65 <= best < 0.75   near-miss → aliases will help
  < 0.65                missing extraction → prompt fix needed

Picks the worst 3 dev fixtures by hook_extraction_f1.
Prints aggregate counts + the actual sim values so we can eyeball.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "packages/evals/voyager_evals/eric/reports/p0.9-rerun/20260513T084832Z"
FIX_DIR = ROOT / "packages/evals/voyager_evals/eric/fixtures"

sys.path.insert(0, str(ROOT / "packages/evals"))
from voyager_evals.eric.metrics import _embed, _gold_surfaces  # noqa: E402

THRESHOLD = 0.75
NEAR = 0.65


def load_fixture_yaml(fid: str) -> dict:
    return yaml.safe_load((FIX_DIR / f"{fid}.yaml").read_text())


def load_run_json(fid: str) -> dict:
    return json.loads((REPORT / "fixtures" / f"{fid}.json").read_text())


def worst_dev_fixtures(n: int = 3) -> list[str]:
    rows = []
    for p in (REPORT / "fixtures").glob("dev-*.json"):
        d = json.loads(p.read_text())
        rows.append((d["scores"]["hook_extraction_f1"], d["fixture_id"]))
    rows.sort()
    return [fid for _, fid in rows[:n]]


def best_sim_per_gold(preds: list[str], gold: list[dict]) -> list[tuple[str, float, str]]:
    """Return list of (gold_text, best_sim, best_pred) per gold item."""
    if not preds or not gold:
        return [(g.get("text", ""), 0.0, "") for g in gold]
    surfaces = [_gold_surfaces(g) for g in gold]
    all_surf = [s for sl in surfaces for s in sl]
    emb = _embed(preds + all_surf)
    pred_mat = emb[: len(preds)]
    surf_mat = emb[len(preds) :]
    sim = pred_mat @ surf_mat.T  # (P, S_total)

    out = []
    offset = 0
    for j, sl in enumerate(surfaces):
        k = len(sl)
        block = sim[:, offset : offset + k]  # (P, k)
        best_pred_idx, best_surf_idx = divmod(int(block.argmax()), k)
        best = float(block.max())
        out.append((gold[j].get("text", ""), best, preds[best_pred_idx]))
        offset += k
    return out


def histogram(rows: list[tuple[str, float, str]]) -> dict:
    buckets = {"matched": 0, "near_miss": 0, "missing": 0}
    for _, sim, _ in rows:
        if sim >= THRESHOLD:
            buckets["matched"] += 1
        elif sim >= NEAR:
            buckets["near_miss"] += 1
        else:
            buckets["missing"] += 1
    return buckets


def main() -> int:
    worst = worst_dev_fixtures(3)
    print(f"worst dev fixtures by hook_f1: {worst}\n")

    agg_hooks = {"matched": 0, "near_miss": 0, "missing": 0}
    agg_sp = {"matched": 0, "near_miss": 0, "missing": 0}

    for fid in worst:
        fix = load_fixture_yaml(fid)
        run = load_run_json(fid)
        gh = fix.get("gold_hooks", []) or []
        gsp = fix.get("gold_selling_points", []) or []
        ph = run.get("hooks_predicted", []) or []
        psp = run.get("selling_points_predicted", []) or []

        hook_rows = best_sim_per_gold(ph, gh)
        sp_rows = best_sim_per_gold(psp, gsp)

        hh = histogram(hook_rows)
        hsp = histogram(sp_rows)
        for k in agg_hooks:
            agg_hooks[k] += hh[k]
            agg_sp[k] += hsp[k]

        print(f"=== {fid} ===")
        print(f"  hooks  : f1={run['scores']['hook_extraction_f1']:.3f}  buckets={hh}")
        for g, s, p in sorted(hook_rows, key=lambda r: r[1]):
            tag = "MATCH" if s >= THRESHOLD else ("NEAR " if s >= NEAR else "MISS ")
            print(f"    {tag} sim={s:.3f}  gold: {g[:80]!r}")
            if s < THRESHOLD:
                print(f"             best_pred: {p[:80]!r}")
        print(f"  sp     : recall={run['scores']['selling_point_recall']:.3f}  buckets={hsp}")
        for g, s, p in sorted(sp_rows, key=lambda r: r[1]):
            tag = "MATCH" if s >= THRESHOLD else ("NEAR " if s >= NEAR else "MISS ")
            print(f"    {tag} sim={s:.3f}  gold: {g[:80]!r}")
            if s < THRESHOLD:
                print(f"             best_pred: {p[:80]!r}")
        print()

    print("=" * 60)
    print(f"AGGREGATE across {len(worst)} worst fixtures:")
    print(f"  hooks: {agg_hooks}")
    print(f"  sp   : {agg_sp}")
    print()
    print(
        "Aliases will help if near_miss >> missing.\n"
        "If missing dominates, the agent never extracted those claims → prompt fix needed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
