# Per-bucket rescore (dev cos=0.65, holdout cos=0.75; gate honors per-bucket hook_f1)

- dev_pass_rate:    **0.00%** (gate 80%)
- holdout_pass_rate: **0.00%** (gate 100%)
- run_passed: **False**
- failures: ['dev_pass_rate 0.00 < 0.80', 'holdout_pass_rate 0.00 < 1.00', 'wall 7722s > 900s']

| bucket | fixture | hook_f1 | sp_recall | schema | passed | failed |
|---|---|---|---|---|---|---|
| dev | dev-culture-01 | 0.571 | 0.600 | 1.00 | ✗ | selling_point_recall:0.600<0.700,strategy_brief_quality:missing |
| dev | dev-culture-02 | 0.500 | 0.875 | 1.00 | ✗ | hook_extraction_f1:0.500<0.550,strategy_brief_quality:missing |
| dev | dev-culture-03 | 0.421 | 0.875 | 1.00 | ✗ | hook_extraction_f1:0.421<0.550,strategy_brief_quality:missing |
| dev | dev-food-01 | 0.563 | 0.875 | 1.00 | ✗ | strategy_brief_quality:missing |
| dev | dev-food-02 | 0.286 | 0.667 | 1.00 | ✗ | hook_extraction_f1:0.286<0.550,selling_point_recall:0.667<0.700,strategy_brief_quality:missing |
| dev | dev-food-03 | 0.333 | 0.778 | 1.00 | ✗ | hook_extraction_f1:0.333<0.550,strategy_brief_quality:missing |
| dev | dev-food-04 | 0.609 | 0.800 | 1.00 | ✗ | strategy_brief_quality:missing |
| dev | dev-history-01 | 0.381 | 0.778 | 1.00 | ✗ | hook_extraction_f1:0.381<0.550,strategy_brief_quality:missing |
| dev | dev-nature-01 | 0.375 | 0.615 | 1.00 | ✗ | hook_extraction_f1:0.375<0.550,selling_point_recall:0.615<0.700,strategy_brief_quality:missing |
| dev | dev-travel-01 | 0.667 | 0.846 | 1.00 | ✗ | strategy_brief_quality:missing |
| dev | dev-travel-02 | 0.526 | 0.727 | 1.00 | ✗ | hook_extraction_f1:0.526<0.550,strategy_brief_quality:missing |
| dev | dev-travel-03 | 0.571 | 0.800 | 1.00 | ✗ | strategy_brief_quality:missing |
| dev | dev-vlog-01 | 0.824 | 0.500 | 1.00 | ✗ | selling_point_recall:0.500<0.700,strategy_brief_quality:missing |
| dev | dev-vlog-02 | 0.714 | 0.143 | 1.00 | ✗ | selling_point_recall:0.143<0.700,strategy_brief_quality:missing |
| dev | dev-vlog-03 | 0.571 | 0.714 | 1.00 | ✗ | strategy_brief_quality:missing |
| holdout | hold-01 | 0.133 | 0.000 | 1.00 | ✗ | hook_extraction_f1:0.133<0.750,selling_point_recall:0.000<0.700,strategy_brief_quality:missing |
| holdout | hold-02 | 0.700 | 0.000 | 1.00 | ✗ | hook_extraction_f1:0.700<0.750,selling_point_recall:0.000<0.700,strategy_brief_quality:missing |
| holdout | hold-03 | 0.560 | 0.500 | 1.00 | ✗ | hook_extraction_f1:0.560<0.750,selling_point_recall:0.500<0.700,strategy_brief_quality:missing |
| holdout | hold-04 | 0.182 | 0.300 | 1.00 | ✗ | hook_extraction_f1:0.182<0.750,selling_point_recall:0.300<0.700,strategy_brief_quality:missing |
| holdout | hold-05 | 0.533 | 0.556 | 1.00 | ✗ | hook_extraction_f1:0.533<0.750,selling_point_recall:0.556<0.700,strategy_brief_quality:missing |

- DEV mean: hook_f1=0.527, sp_recall=0.706
- HOLDOUT mean: hook_f1=0.422, sp_recall=0.271