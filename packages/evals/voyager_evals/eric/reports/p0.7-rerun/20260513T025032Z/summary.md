# Eric eval — p0.7-rerun — ❌ FAIL

- run_id: `20260513T025032Z`
- dev_pass_rate: **0.00%**
- holdout_pass_rate: **100.00%**
- total_cost_usd: $0.0000
- total_wall_seconds: 5589.5

## Run-level failures

- dev_pass_rate 0.00 < 0.80
- wall 5590s > 900s

## Per-fixture results

| fixture | bucket | passed | hook_extraction_f1 | selling_point_recall | schema_validity_rate | failed |
|---|---|---|---|---|---|---|
| dev-food-01 | dev | ❌ | 0.556 | 0.250 | 1.000 | hook_extraction_f1:0.556<0.750, selling_point_recall:0.250<0.700, strategy_brief_quality:missing |
| dev-food-02 | dev | ❌ | 0.800 | 0.133 | 1.000 | selling_point_recall:0.133<0.700, strategy_brief_quality:missing |
| dev-vlog-01 | dev | ❌ | 0.615 | 0.375 | 1.000 | hook_extraction_f1:0.615<0.750, selling_point_recall:0.375<0.700, strategy_brief_quality:missing |
| dev-travel-01 | dev | ❌ | 0.769 | 0.692 | 1.000 | selling_point_recall:0.692<0.700, strategy_brief_quality:missing |
| dev-culture-01 | dev | ❌ | 0.571 | 0.400 | 1.000 | hook_extraction_f1:0.571<0.750, selling_point_recall:0.400<0.700, strategy_brief_quality:missing |
| dev-food-03 | dev | ❌ | 0.182 | 0.444 | 1.000 | hook_extraction_f1:0.182<0.750, selling_point_recall:0.444<0.700, strategy_brief_quality:missing |
| dev-vlog-02 | dev | ❌ | 0.462 | 0.571 | 1.000 | hook_extraction_f1:0.462<0.750, selling_point_recall:0.571<0.700, strategy_brief_quality:missing |
| dev-travel-02 | dev | ❌ | 0.267 | 0.727 | 1.000 | hook_extraction_f1:0.267<0.750, strategy_brief_quality:missing |
| dev-culture-02 | dev | ❌ | 0.400 | 0.625 | 1.000 | hook_extraction_f1:0.400<0.750, selling_point_recall:0.625<0.700, strategy_brief_quality:missing |
| dev-nature-01 | dev | ❌ | 0.500 | 0.692 | 1.000 | hook_extraction_f1:0.500<0.750, selling_point_recall:0.692<0.700, strategy_brief_quality:missing |
| dev-vlog-03 | dev | ❌ | 0.800 | 0.286 | 1.000 | selling_point_recall:0.286<0.700, strategy_brief_quality:missing |
| dev-history-01 | dev | ❌ | 0.308 | 0.333 | 1.000 | hook_extraction_f1:0.308<0.750, selling_point_recall:0.333<0.700, strategy_brief_quality:missing |
| dev-travel-03 | dev | ❌ | 0.625 | 0.700 | 1.000 | hook_extraction_f1:0.625<0.750, strategy_brief_quality:missing |
| dev-culture-03 | dev | ❌ | 0.000 | 0.375 | 1.000 | hook_extraction_f1:0.000<0.750, selling_point_recall:0.375<0.700, strategy_brief_quality:missing |
| dev-food-04 | dev | ❌ | 0.533 | 0.400 | 1.000 | hook_extraction_f1:0.533<0.750, selling_point_recall:0.400<0.700, strategy_brief_quality:missing |
