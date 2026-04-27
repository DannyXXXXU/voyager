"""Markdown + JSON report writers for Eric eval runs.

Outputs:
  reports/<label>/<run_id>/summary.md        — human-readable
  reports/<label>/<run_id>/summary.json      — machine-parseable
  reports/<label>/<run_id>/fixtures.json     — per-fixture scores
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .gate import RunResult


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_reports(
    run: RunResult,
    reports_root: str | Path = "reports",
    run_id: str | None = None,
) -> Path:
    """Write summary.md / summary.json / fixtures.json. Returns run dir."""
    run_id = run_id or _utc_stamp()
    out = Path(reports_root) / run.label / run_id
    out.mkdir(parents=True, exist_ok=True)

    # summary.json
    summary = {
        "label": run.label,
        "run_id": run_id,
        "passed": run.passed,
        "dev_pass_rate": run.dev_pass_rate,
        "holdout_pass_rate": run.holdout_pass_rate,
        "total_cost_usd": run.total_cost_usd,
        "total_wall_seconds": run.total_wall_seconds,
        "failures": run.failures,
        "fixture_count": len(run.fixtures),
    }
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # fixtures.json
    (out / "fixtures.json").write_text(
        json.dumps(
            [asdict(f) for f in run.fixtures], indent=2, ensure_ascii=False
        ),
        encoding="utf-8",
    )

    # summary.md
    md = _render_markdown(run, run_id)
    (out / "summary.md").write_text(md, encoding="utf-8")
    return out


def _render_markdown(run: RunResult, run_id: str) -> str:
    status = "✅ PASS" if run.passed else "❌ FAIL"
    lines = [
        f"# Eric eval — {run.label} — {status}",
        "",
        f"- run_id: `{run_id}`",
        f"- dev_pass_rate: **{run.dev_pass_rate:.2%}**",
        f"- holdout_pass_rate: **{run.holdout_pass_rate:.2%}**",
        f"- total_cost_usd: ${run.total_cost_usd:.4f}",
        f"- total_wall_seconds: {run.total_wall_seconds:.1f}",
        "",
    ]
    if run.failures:
        lines += ["## Run-level failures", ""]
        for f in run.failures:
            lines.append(f"- {f}")
        lines.append("")

    # Per-fixture table
    metric_names: list[str] = []
    for f in run.fixtures:
        for k in f.scores.keys():
            if k not in metric_names:
                metric_names.append(k)

    if run.fixtures:
        lines.append("## Per-fixture results")
        lines.append("")
        header = ["fixture", "bucket", "passed"] + metric_names + ["failed"]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join("---" for _ in header) + "|")
        for fx in run.fixtures:
            row = [
                fx.fixture_id,
                fx.bucket,
                "✅" if fx.passed else "❌",
            ]
            for m in metric_names:
                v = fx.scores.get(m)
                row.append(f"{v:.3f}" if isinstance(v, (int, float)) else "—")
            row.append(", ".join(fx.failed_metrics) or "—")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    return "\n".join(lines)


__all__ = ["write_reports"]
