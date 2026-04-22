# Eric Eval Harness

Offline, reproducible eval gate for the Eric agent. Must pass before Mike can start.

## Layout

```
voyager_evals/eric/
  fixtures/
    dev/          # 15 agent-drafted, human-spot-checked
    holdout/      # 5 human-labeled only; NEVER iterated against
  gold/
    transcripts/  # <video_id>.txt prefetched via scripts/prefetch_gold.py
    comments/     # <video_id>.jsonl
    manifest.yaml # sha256 checksums
  judges/         # LLM-judge rubrics + cache
  reports/        # per-run artifacts (summary.md, report.html, scores.json)
  seed.yaml       # 20 video ids to prefetch
  thresholds.yaml # pass/fail criteria
  schema.py       # EricFixture pydantic model
  metrics.py      # deterministic metrics (F1, recall, schema validity)
  run_eval.py     # main entry point
  regression.py   # sparkline across past runs
```

## Usage

Prefetch gold (one-time, needs cloud creds for Whisper + YouTube):
```bash
uv run python scripts/prefetch_gold.py --seed packages/evals/voyager_evals/eric/seed.yaml
```

Run eval (offline, only Copilot CLI needed):
```bash
uv run python -m voyager_evals.eric.run_eval --label baseline
```

Regression:
```bash
uv run python -m voyager_evals.eric.regression --last 10
```

## Fixture conventions

- Each fixture: `id`, `video_id`, `topic`, `difficulty` (easy/medium/hard),
  `content_type` (vlog/food/culture/citytour/...), `holdout` (bool),
  `gold_hooks[]`, `gold_selling_points[]`, `transcript_sha256`.
- Use `aliases` in gold items so fuzzy matching via sentence-transformers
  accepts paraphrases.
- **Never iterate prompts against holdout.** If you peek, discard it and
  relabel from fresh sources.

## Thresholds

See `thresholds.yaml`. M1 exit:
- hook_extraction_f1 >= 0.75
- selling_point_recall >= 0.70
- schema_validity_rate >= 0.99
- strategy_brief_quality >= 4.0 (judge: Copilot GPT-5, 1-5 scale, median of 3)
- required_pass_rate 0.80 on dev; 1.0 on holdout.
