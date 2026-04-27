"""Threshold-gating logic for Eric eval.

Loads thresholds.yaml and decides pass/fail given per-fixture metric scores.

A fixture passes iff every deterministic threshold in `metrics:` is met
(e.g. hook_extraction_f1 >= 0.75) AND every llm_judge threshold is met
(median score >= rubric threshold).

The whole eval run passes iff:
  * dev pass-rate >= required_pass_rate
  * holdout pass-rate >= holdout_required_pass_rate
  * total cost <= cost_budget_usd
  * wall-clock <= wall_clock_cap_seconds
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# --- threshold loading --------------------------------------------------------

@dataclass
class MetricThreshold:
    name: str
    threshold: float
    type: str  # "deterministic" | "llm_judge"
    weight: int = 1
    judge_model: str | None = None
    rubric: str | None = None
    median_of: int = 1


@dataclass
class ThresholdConfig:
    agent: str
    required_pass_rate: float
    holdout_required_pass_rate: float
    cost_budget_usd: float
    wall_clock_cap_seconds: int
    metrics: list[MetricThreshold]

    @classmethod
    def load(cls, path: str | Path) -> "ThresholdConfig":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        metrics = [
            MetricThreshold(
                name=k,
                threshold=float(v["threshold"]),
                type=v["type"],
                weight=int(v.get("weight", 1)),
                judge_model=v.get("judge_model"),
                rubric=v.get("rubric"),
                median_of=int(v.get("median_of", 1)),
            )
            for k, v in (data.get("metrics") or {}).items()
        ]
        return cls(
            agent=data["agent"],
            required_pass_rate=float(data["required_pass_rate"]),
            holdout_required_pass_rate=float(data["holdout_required_pass_rate"]),
            cost_budget_usd=float(data["cost_budget_usd"]),
            wall_clock_cap_seconds=int(data["wall_clock_cap_seconds"]),
            metrics=metrics,
        )


# --- per-fixture & whole-run gating ------------------------------------------

@dataclass
class FixtureResult:
    fixture_id: str
    bucket: str  # "dev" | "holdout"
    scores: dict[str, float] = field(default_factory=dict)
    passed: bool = False
    failed_metrics: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    wall_seconds: float = 0.0
    error: str | None = None


@dataclass
class RunResult:
    label: str
    passed: bool
    dev_pass_rate: float
    holdout_pass_rate: float
    total_cost_usd: float
    total_wall_seconds: float
    fixtures: list[FixtureResult]
    failures: list[str]


def evaluate_fixture(
    fixture_id: str,
    bucket: str,
    scores: dict[str, float],
    config: ThresholdConfig,
    cost_usd: float = 0.0,
    wall_seconds: float = 0.0,
    error: str | None = None,
) -> FixtureResult:
    """Score-by-score check against thresholds."""
    res = FixtureResult(
        fixture_id=fixture_id,
        bucket=bucket,
        scores=dict(scores),
        cost_usd=cost_usd,
        wall_seconds=wall_seconds,
        error=error,
    )
    if error:
        res.passed = False
        res.failed_metrics = ["__error__"]
        return res
    failed = []
    for m in config.metrics:
        score = scores.get(m.name)
        if score is None:
            failed.append(f"{m.name}:missing")
            continue
        if score < m.threshold:
            failed.append(f"{m.name}:{score:.3f}<{m.threshold:.3f}")
    res.failed_metrics = failed
    res.passed = not failed
    return res


def evaluate_run(
    fixtures: list[FixtureResult],
    config: ThresholdConfig,
    label: str = "baseline",
) -> RunResult:
    dev = [f for f in fixtures if f.bucket == "dev"]
    hold = [f for f in fixtures if f.bucket == "holdout"]
    dev_rate = (sum(1 for f in dev if f.passed) / len(dev)) if dev else 1.0
    hold_rate = (sum(1 for f in hold if f.passed) / len(hold)) if hold else 1.0
    total_cost = sum(f.cost_usd for f in fixtures)
    total_wall = sum(f.wall_seconds for f in fixtures)

    failures: list[str] = []
    if dev_rate < config.required_pass_rate:
        failures.append(
            f"dev_pass_rate {dev_rate:.2f} < {config.required_pass_rate:.2f}"
        )
    if hold and hold_rate < config.holdout_required_pass_rate:
        failures.append(
            f"holdout_pass_rate {hold_rate:.2f} < {config.holdout_required_pass_rate:.2f}"
        )
    if total_cost > config.cost_budget_usd:
        failures.append(
            f"cost ${total_cost:.2f} > ${config.cost_budget_usd:.2f}"
        )
    if total_wall > config.wall_clock_cap_seconds:
        failures.append(
            f"wall {total_wall:.0f}s > {config.wall_clock_cap_seconds}s"
        )

    return RunResult(
        label=label,
        passed=not failures,
        dev_pass_rate=dev_rate,
        holdout_pass_rate=hold_rate,
        total_cost_usd=total_cost,
        total_wall_seconds=total_wall,
        fixtures=fixtures,
        failures=failures,
    )


__all__ = [
    "MetricThreshold",
    "ThresholdConfig",
    "FixtureResult",
    "RunResult",
    "evaluate_fixture",
    "evaluate_run",
]
