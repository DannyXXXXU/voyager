"""Eric eval entry point.

Wiring (Task 1.19g): CLI surface + threshold gating + reports.
The actual agent invocation + scoring lands in baseline-run task — until then,
this loads pre-computed fixture scores from a JSON file (--scores-file)
so we can validate the gate end-to-end without burning LLM tokens.

Exit codes:
  0   run passed all thresholds
  1   run failed at least one threshold
  2   harness/setup error
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .gate import (
    FixtureResult,
    ThresholdConfig,
    evaluate_fixture,
    evaluate_run,
)
from .reports import write_reports


def _load_scores(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Eric eval harness.")
    parser.add_argument("--label", default="baseline", help="Report label (baseline/p0/p1)")
    parser.add_argument(
        "--thresholds",
        default=str(Path(__file__).parent / "thresholds.yaml"),
        help="Path to thresholds.yaml",
    )
    parser.add_argument(
        "--scores-file",
        type=Path,
        default=None,
        help=(
            "JSON list of {fixture_id, bucket, scores, cost_usd, wall_seconds, error}. "
            "Required until the live runner is wired in baseline-run task."
        ),
    )
    parser.add_argument(
        "--reports-root",
        default="reports",
        help="Where to write reports/<label>/<run_id>/",
    )
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        config = ThresholdConfig.load(args.thresholds)
    except Exception as e:  # noqa: BLE001
        print(f"[eric-eval] FATAL: cannot load thresholds: {e}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"[eric-eval] dry-run, label={args.label}, agent={config.agent}")
        return 0

    if not args.scores_file:
        print(
            "[eric-eval] FATAL: --scores-file required (live runner not wired yet; "
            "see baseline-run task)",
            file=sys.stderr,
        )
        return 2

    raw = _load_scores(args.scores_file)
    fixtures: list[FixtureResult] = []
    for item in raw:
        fixtures.append(
            evaluate_fixture(
                fixture_id=item["fixture_id"],
                bucket=item["bucket"],
                scores=item.get("scores") or {},
                config=config,
                cost_usd=float(item.get("cost_usd", 0.0)),
                wall_seconds=float(item.get("wall_seconds", 0.0)),
                error=item.get("error"),
            )
        )

    run = evaluate_run(fixtures, config, label=args.label)
    out = write_reports(run, reports_root=args.reports_root, run_id=args.run_id)
    print(f"[eric-eval] {'PASS' if run.passed else 'FAIL'} → {out}")
    if run.failures:
        for f in run.failures:
            print(f"  - {f}")
    return 0 if run.passed else 1


if __name__ == "__main__":
    sys.exit(main())
