# Eric eval — p1-dryrun — ❌ FAIL

- run_id: `20260518T023244Z`
- dev_pass_rate: **0.00%**
- holdout_pass_rate: **100.00%**
- total_cost_usd: $0.0000
- total_wall_seconds: 418.5

## Run-level failures

- dev_pass_rate 0.00 < 0.80

## Per-fixture results

| fixture | bucket | passed | hook_extraction_f1 | selling_point_recall | schema_validity_rate | failed |
|---|---|---|---|---|---|---|
| dev-food-02 | dev | ❌ | 0.364 | 0.400 | 1.000 | hook_extraction_f1:0.364<0.750, selling_point_recall:0.400<0.700, strategy_brief_quality:missing |
