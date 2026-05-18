import json, sys
fp = sys.argv[1]
rec = json.loads(open(fp).read())
print("fixture:", rec.get("fixture_id"))
print("scores:", rec.get("scores"))
print("\nhooks_pred (%d):" % len(rec.get("hooks_predicted", [])))
for x in rec.get("hooks_predicted", [])[:15]:
    s = x if isinstance(x, str) else (x.get("text") if isinstance(x, dict) else str(x))
    print(" -", s[:140])
print("\nsp_pred (%d):" % len(rec.get("selling_points_predicted", []) or rec.get("sp_predicted", [])))
for x in (rec.get("selling_points_predicted") or rec.get("sp_predicted") or []):
    s = x if isinstance(x, str) else (x.get("text") if isinstance(x, dict) else str(x))
    print(" -", s[:140])
