"""Compare P0.9 vs P1 on dev-food-02 dry-run (apples-to-apples at T=0.65)."""
import json

FID = "dev-food-02"
ROOT = "packages/evals/voyager_evals/eric/reports"


def find(path, fid, key="per_fixture"):
    raw = json.load(open(path))
    rows = raw[key] if isinstance(raw, dict) else raw
    for r in rows:
        if r["fixture_id"] == fid:
            return r["scores"]
    return None


p09_default = find(f"{ROOT}/p0.9-rerun/20260513T084832Z/scores.json", FID)
p09_t65 = find(f"{ROOT}/p0.9-rerun/20260513T084832Z/scores_t0.65.json", FID)
p1_t65 = find(f"{ROOT}/p1-dryrun/20260518T023244Z/scores.json", FID)

print(f"=== {FID} ===")
print(f"P0.9 (T=0.75 default): {p09_default}")
print(f"P0.9 (T=0.65 rescore): {p09_t65}")
print(f"P1   (T=0.65 native):  {p1_t65}")
print()
print("Delta P0.9@0.65 -> P1@0.65:")
for k in ("hook_extraction_f1", "selling_point_recall"):
    print(f"  {k}: {p09_t65[k]:.3f} -> {p1_t65[k]:.3f} ({p1_t65[k]-p09_t65[k]:+.3f})")
