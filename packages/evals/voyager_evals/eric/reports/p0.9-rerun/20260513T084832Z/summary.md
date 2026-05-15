# Eric eval — p0.9-rerun — ❌ FAIL

- run_id: `20260513T084832Z`
- dev_pass_rate: **0.00%**
- holdout_pass_rate: **100.00%**
- total_cost_usd: $0.0000
- total_wall_seconds: 5585.4

## Run-level failures

- dev_pass_rate 0.00 < 0.80
- wall 5585s > 900s

## Per-fixture results

| fixture | bucket | passed | hook_extraction_f1 | selling_point_recall | schema_validity_rate | failed |
|---|---|---|---|---|---|---|
| dev-food-01 | dev | ❌ | 0.292 | 0.500 | 1.000 | hook_extraction_f1:0.292<0.750, selling_point_recall:0.500<0.700, strategy_brief_quality:missing |
| dev-food-02 | dev | ❌ | 0.182 | 0.267 | 1.000 | hook_extraction_f1:0.182<0.750, selling_point_recall:0.267<0.700, strategy_brief_quality:missing |
| dev-vlog-01 | dev | ❌ | 0.471 | 0.250 | 1.000 | hook_extraction_f1:0.471<0.750, selling_point_recall:0.250<0.700, strategy_brief_quality:missing |
| dev-travel-01 | dev | ❌ | 0.556 | 0.615 | 1.000 | hook_extraction_f1:0.556<0.750, selling_point_recall:0.615<0.700, strategy_brief_quality:missing |
| dev-culture-01 | dev | ❌ | 0.632 | 0.300 | 1.000 | hook_extraction_f1:0.632<0.750, selling_point_recall:0.300<0.700, strategy_brief_quality:missing |
| dev-food-03 | dev | ❌ | 0.250 | 0.444 | 1.000 | hook_extraction_f1:0.250<0.750, selling_point_recall:0.444<0.700, strategy_brief_quality:missing |
| dev-vlog-02 | dev | ❌ | 0.714 | 0.571 | 1.000 | hook_extraction_f1:0.714<0.750, selling_point_recall:0.571<0.700, strategy_brief_quality:missing |
| dev-travel-02 | dev | ❌ | 0.333 | 0.545 | 1.000 | hook_extraction_f1:0.333<0.750, selling_point_recall:0.545<0.700, strategy_brief_quality:missing |
| dev-culture-02 | dev | ❌ | 0.300 | 0.750 | 1.000 | hook_extraction_f1:0.300<0.750, strategy_brief_quality:missing |
| dev-nature-01 | dev | ❌ | 0.500 | 0.615 | 1.000 | hook_extraction_f1:0.500<0.750, selling_point_recall:0.615<0.700, strategy_brief_quality:missing |
| dev-vlog-03 | dev | ❌ | 0.533 | 0.714 | 1.000 | hook_extraction_f1:0.533<0.750, strategy_brief_quality:missing |
| dev-history-01 | dev | ❌ | 0.125 | 0.556 | 1.000 | hook_extraction_f1:0.125<0.750, selling_point_recall:0.556<0.700, strategy_brief_quality:missing |
| dev-travel-03 | dev | ❌ | 0.526 | 0.900 | 1.000 | hook_extraction_f1:0.526<0.750, strategy_brief_quality:missing |
| dev-culture-03 | dev | ❌ | 0.125 | 0.500 | 1.000 | hook_extraction_f1:0.125<0.750, selling_point_recall:0.500<0.700, strategy_brief_quality:missing |
| dev-food-04 | dev | ❌ | 0.600 | 0.300 | 1.000 | hook_extraction_f1:0.600<0.750, selling_point_recall:0.300<0.700, strategy_brief_quality:missing |
