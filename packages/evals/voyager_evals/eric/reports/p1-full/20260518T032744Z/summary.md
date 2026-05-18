# Eric eval — p1-full — ❌ FAIL

- run_id: `20260518T032744Z`
- dev_pass_rate: **0.00%**
- holdout_pass_rate: **0.00%**
- total_cost_usd: $0.0000
- total_wall_seconds: 7721.6

## Run-level failures

- dev_pass_rate 0.00 < 0.80
- holdout_pass_rate 0.00 < 1.00
- wall 7722s > 900s

## Per-fixture results

| fixture | bucket | passed | hook_extraction_f1 | selling_point_recall | schema_validity_rate | failed |
|---|---|---|---|---|---|---|
| dev-food-01 | dev | ❌ | 0.563 | 0.875 | 1.000 | hook_extraction_f1:0.563<0.750, strategy_brief_quality:missing |
| dev-food-02 | dev | ❌ | 0.286 | 0.667 | 1.000 | hook_extraction_f1:0.286<0.750, selling_point_recall:0.667<0.700, strategy_brief_quality:missing |
| dev-vlog-01 | dev | ❌ | 0.824 | 0.500 | 1.000 | selling_point_recall:0.500<0.700, strategy_brief_quality:missing |
| dev-travel-01 | dev | ❌ | 0.667 | 0.846 | 1.000 | hook_extraction_f1:0.667<0.750, strategy_brief_quality:missing |
| dev-culture-01 | dev | ❌ | 0.571 | 0.600 | 1.000 | hook_extraction_f1:0.571<0.750, selling_point_recall:0.600<0.700, strategy_brief_quality:missing |
| dev-food-03 | dev | ❌ | 0.333 | 0.778 | 1.000 | hook_extraction_f1:0.333<0.750, strategy_brief_quality:missing |
| dev-vlog-02 | dev | ❌ | 0.714 | 0.143 | 1.000 | hook_extraction_f1:0.714<0.750, selling_point_recall:0.143<0.700, strategy_brief_quality:missing |
| dev-travel-02 | dev | ❌ | 0.526 | 0.727 | 1.000 | hook_extraction_f1:0.526<0.750, strategy_brief_quality:missing |
| dev-culture-02 | dev | ❌ | 0.500 | 0.875 | 1.000 | hook_extraction_f1:0.500<0.750, strategy_brief_quality:missing |
| dev-nature-01 | dev | ❌ | 0.375 | 0.615 | 1.000 | hook_extraction_f1:0.375<0.750, selling_point_recall:0.615<0.700, strategy_brief_quality:missing |
| dev-vlog-03 | dev | ❌ | 0.571 | 0.714 | 1.000 | hook_extraction_f1:0.571<0.750, strategy_brief_quality:missing |
| dev-history-01 | dev | ❌ | 0.381 | 0.778 | 1.000 | hook_extraction_f1:0.381<0.750, strategy_brief_quality:missing |
| dev-travel-03 | dev | ❌ | 0.571 | 0.800 | 1.000 | hook_extraction_f1:0.571<0.750, strategy_brief_quality:missing |
| dev-culture-03 | dev | ❌ | 0.421 | 0.875 | 1.000 | hook_extraction_f1:0.421<0.750, strategy_brief_quality:missing |
| dev-food-04 | dev | ❌ | 0.609 | 0.800 | 1.000 | hook_extraction_f1:0.609<0.750, strategy_brief_quality:missing |
| hold-01 | holdout | ❌ | 0.133 | 0.000 | 1.000 | hook_extraction_f1:0.133<0.750, selling_point_recall:0.000<0.700, strategy_brief_quality:missing |
| hold-02 | holdout | ❌ | 0.700 | 0.000 | 1.000 | hook_extraction_f1:0.700<0.750, selling_point_recall:0.000<0.700, strategy_brief_quality:missing |
| hold-03 | holdout | ❌ | 0.560 | 0.500 | 1.000 | hook_extraction_f1:0.560<0.750, selling_point_recall:0.500<0.700, strategy_brief_quality:missing |
| hold-04 | holdout | ❌ | 0.182 | 0.300 | 1.000 | hook_extraction_f1:0.182<0.750, selling_point_recall:0.300<0.700, strategy_brief_quality:missing |
| hold-05 | holdout | ❌ | 0.533 | 0.556 | 1.000 | hook_extraction_f1:0.533<0.750, selling_point_recall:0.556<0.700, strategy_brief_quality:missing |
