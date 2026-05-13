# Eric eval — p0.8-rerun — ❌ FAIL

- run_id: `20260513T062651Z`
- dev_pass_rate: **0.00%**
- holdout_pass_rate: **100.00%**
- total_cost_usd: $0.0000
- total_wall_seconds: 5778.7

## Run-level failures

- dev_pass_rate 0.00 < 0.80
- wall 5779s > 900s

## Per-fixture results

| fixture | bucket | passed | hook_extraction_f1 | selling_point_recall | schema_validity_rate | failed |
|---|---|---|---|---|---|---|
| dev-food-01 | dev | ❌ | 0.455 | 0.250 | 1.000 | hook_extraction_f1:0.455<0.750, selling_point_recall:0.250<0.700, strategy_brief_quality:missing |
| dev-food-02 | dev | ❌ | 0.500 | 0.267 | 1.000 | hook_extraction_f1:0.500<0.750, selling_point_recall:0.267<0.700, strategy_brief_quality:missing |
| dev-vlog-01 | dev | ❌ | 0.533 | 0.250 | 1.000 | hook_extraction_f1:0.533<0.750, selling_point_recall:0.250<0.700, strategy_brief_quality:missing |
| dev-travel-01 | dev | ❌ | 0.571 | 0.769 | 1.000 | hook_extraction_f1:0.571<0.750, strategy_brief_quality:missing |
| dev-culture-01 | dev | ❌ | 0.471 | 0.200 | 1.000 | hook_extraction_f1:0.471<0.750, selling_point_recall:0.200<0.700, strategy_brief_quality:missing |
| dev-food-03 | dev | ❌ | 0.133 | 0.222 | 1.000 | hook_extraction_f1:0.133<0.750, selling_point_recall:0.222<0.700, strategy_brief_quality:missing |
| dev-vlog-02 | dev | ❌ | 0.615 | 0.571 | 1.000 | hook_extraction_f1:0.615<0.750, selling_point_recall:0.571<0.700, strategy_brief_quality:missing |
| dev-travel-02 | dev | ❌ | 0.353 | 0.636 | 1.000 | hook_extraction_f1:0.353<0.750, selling_point_recall:0.636<0.700, strategy_brief_quality:missing |
| dev-culture-02 | dev | ❌ | 0.421 | 0.750 | 1.000 | hook_extraction_f1:0.421<0.750, strategy_brief_quality:missing |
| dev-nature-01 | dev | ❌ | 0.533 | 0.462 | 1.000 | hook_extraction_f1:0.533<0.750, selling_point_recall:0.462<0.700, strategy_brief_quality:missing |
| dev-vlog-03 | dev | ❌ | 0.500 | 0.571 | 1.000 | hook_extraction_f1:0.500<0.750, selling_point_recall:0.571<0.700, strategy_brief_quality:missing |
| dev-history-01 | dev | ❌ | 0.267 | 0.444 | 1.000 | hook_extraction_f1:0.267<0.750, selling_point_recall:0.444<0.700, strategy_brief_quality:missing |
| dev-travel-03 | dev | ❌ | 0.500 | 0.700 | 1.000 | hook_extraction_f1:0.500<0.750, strategy_brief_quality:missing |
| dev-culture-03 | dev | ❌ | 0.267 | 0.375 | 1.000 | hook_extraction_f1:0.267<0.750, selling_point_recall:0.375<0.700, strategy_brief_quality:missing |
| dev-food-04 | dev | ❌ | 0.400 | 0.400 | 1.000 | hook_extraction_f1:0.400<0.750, selling_point_recall:0.400<0.700, strategy_brief_quality:missing |
