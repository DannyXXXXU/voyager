"""Dump pred vs gold hooks side-by-side for diagnostic fixtures."""
import json
import sys
import yaml

RUN = "packages/evals/voyager_evals/eric/reports/p1-full/20260518T032744Z"
FIX = "packages/evals/voyager_evals/eric/fixtures"

fids = sys.argv[1:] or ["dev-culture-02", "dev-food-02", "hold-04"]
for fid in fids:
    pred = json.load(open(f"{RUN}/fixtures/{fid}.json"))
    gold = yaml.safe_load(open(f"{FIX}/{fid}.yaml"))
    print(f"\n===== {fid}  scores={pred['scores']} =====")
    gh = gold.get("gold_hooks") or []
    ph = pred.get("hooks_predicted") or []
    print(f"GOLD hooks ({len(gh)}):")
    for h in gh:
        print(f"  G - {h['text'][:110]}")
    print(f"PRED hooks ({len(ph)}):")
    for h in ph:
        print(f"  P - {h[:110]}")
