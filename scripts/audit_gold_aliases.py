"""Audit dev gold aliases coverage."""
import glob
import yaml

total_h = total_s = h_empty = s_empty = 0
for fp in sorted(glob.glob("packages/evals/voyager_evals/eric/fixtures/dev-*.yaml")):
    d = yaml.safe_load(open(fp))
    hooks = d.get("gold_hooks") or []
    sps = d.get("gold_selling_points") or []
    he = sum(1 for h in hooks if not h.get("aliases"))
    se = sum(1 for s in sps if not s.get("aliases"))
    total_h += len(hooks)
    total_s += len(sps)
    h_empty += he
    s_empty += se
    name = fp.split("/")[-1]
    print(f"{name:25s} hooks {len(hooks)} ({he} empty)  sp {len(sps)} ({se} empty)")
print()
print(f"TOTAL hooks empty: {h_empty}/{total_h}   sp empty: {s_empty}/{total_s}")
