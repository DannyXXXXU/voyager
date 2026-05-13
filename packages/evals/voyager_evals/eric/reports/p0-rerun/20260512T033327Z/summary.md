# Eric eval — p0-rerun — ❌ FAIL

- run_id: `20260512T033327Z`
- dev_pass_rate: **0.00%**
- holdout_pass_rate: **100.00%**
- total_cost_usd: $0.0000
- total_wall_seconds: 5517.0

## Run-level failures

- dev_pass_rate 0.00 < 0.80
- wall 5517s > 900s

## Per-fixture results

| fixture | bucket | passed | hook_extraction_f1 | selling_point_recall | schema_validity_rate | failed |
|---|---|---|---|---|---|---|
| dev-food-01 | dev | ❌ | 0.588 | 0.125 | 1.000 | hook_extraction_f1:0.588<0.750, selling_point_recall:0.125<0.700, strategy_brief_quality:missing |
| dev-food-02 | dev | ❌ | 0.000 | 0.133 | 1.000 | hook_extraction_f1:0.000<0.750, selling_point_recall:0.133<0.700, strategy_brief_quality:missing |
| dev-vlog-01 | dev | ❌ | 0.308 | 0.000 | 1.000 | hook_extraction_f1:0.308<0.750, selling_point_recall:0.000<0.700, strategy_brief_quality:missing |
| dev-travel-01 | dev | ❌ | 0.714 | 0.692 | 1.000 | hook_extraction_f1:0.714<0.750, selling_point_recall:0.692<0.700, strategy_brief_quality:missing |
| dev-culture-01 | dev | ❌ | 0.462 | 0.200 | 1.000 | hook_extraction_f1:0.462<0.750, selling_point_recall:0.200<0.700, strategy_brief_quality:missing |
| dev-food-03 | dev | ❌ | 0.167 | 0.111 | 1.000 | hook_extraction_f1:0.167<0.750, selling_point_recall:0.111<0.700, strategy_brief_quality:missing |
| dev-vlog-02 | dev | ❌ | 0.364 | 0.429 | 1.000 | hook_extraction_f1:0.364<0.750, selling_point_recall:0.429<0.700, strategy_brief_quality:missing |
| dev-travel-02 | dev | ❌ | 0.133 | 0.545 | 1.000 | hook_extraction_f1:0.133<0.750, selling_point_recall:0.545<0.700, strategy_brief_quality:missing |
| dev-culture-02 | dev | ❌ | 0.714 | 0.625 | 1.000 | hook_extraction_f1:0.714<0.750, selling_point_recall:0.625<0.700, strategy_brief_quality:missing |
| dev-nature-01 | dev | ❌ | 0.333 | 0.308 | 1.000 | hook_extraction_f1:0.333<0.750, selling_point_recall:0.308<0.700, strategy_brief_quality:missing |
| dev-vlog-03 | dev | ❌ | 0.800 | 0.286 | 1.000 | selling_point_recall:0.286<0.700, strategy_brief_quality:missing |
| dev-history-01 | dev | ❌ | 0.333 | 0.333 | 1.000 | hook_extraction_f1:0.333<0.750, selling_point_recall:0.333<0.700, strategy_brief_quality:missing |
| dev-travel-03 | dev | ❌ | 0.625 | 0.400 | 1.000 | hook_extraction_f1:0.625<0.750, selling_point_recall:0.400<0.700, strategy_brief_quality:missing |
| dev-culture-03 | dev | ❌ | 0.500 | 0.250 | 1.000 | hook_extraction_f1:0.500<0.750, selling_point_recall:0.250<0.700, strategy_brief_quality:missing |
| dev-food-04 | dev | ❌ | 0.750 | 0.200 | 1.000 | selling_point_recall:0.200<0.700, strategy_brief_quality:missing |
