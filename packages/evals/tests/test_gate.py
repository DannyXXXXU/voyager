"""Tests for gate.py + reports.py + run_eval.py CLI."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from voyager_evals.eric.gate import (
    FixtureResult,
    ThresholdConfig,
    evaluate_fixture,
    evaluate_run,
)
from voyager_evals.eric.reports import write_reports


THRESHOLDS = Path(__file__).parent.parent / "voyager_evals" / "eric" / "thresholds.yaml"


def test_threshold_config_load():
    cfg = ThresholdConfig.load(THRESHOLDS)
    assert cfg.agent == "eric"
    assert cfg.required_pass_rate == 0.80
    assert cfg.holdout_required_pass_rate == 1.0
    names = {m.name for m in cfg.metrics}
    assert {
        "hook_extraction_f1",
        "selling_point_recall",
        "schema_validity_rate",
        "strategy_brief_quality",
    } <= names


def test_evaluate_fixture_pass():
    cfg = ThresholdConfig.load(THRESHOLDS)
    res = evaluate_fixture(
        "dev-food-01",
        "dev",
        {
            "hook_extraction_f1": 0.9,
            "selling_point_recall": 0.85,
            "schema_validity_rate": 1.0,
            "strategy_brief_quality": 4.5,
        },
        cfg,
    )
    assert res.passed
    assert res.failed_metrics == []


def test_evaluate_fixture_fail():
    cfg = ThresholdConfig.load(THRESHOLDS)
    res = evaluate_fixture(
        "dev-food-02",
        "dev",
        {
            "hook_extraction_f1": 0.5,  # below 0.75
            "selling_point_recall": 0.85,
            "schema_validity_rate": 1.0,
            "strategy_brief_quality": 4.5,
        },
        cfg,
    )
    assert not res.passed
    assert any("hook_extraction_f1" in f for f in res.failed_metrics)


def test_evaluate_fixture_missing_metric():
    cfg = ThresholdConfig.load(THRESHOLDS)
    res = evaluate_fixture("x", "dev", {"hook_extraction_f1": 0.9}, cfg)
    assert not res.passed
    assert "selling_point_recall:missing" in res.failed_metrics


def test_evaluate_fixture_error():
    cfg = ThresholdConfig.load(THRESHOLDS)
    res = evaluate_fixture("x", "dev", {}, cfg, error="copilot_timeout")
    assert not res.passed
    assert res.failed_metrics == ["__error__"]


def _good_scores() -> dict:
    return {
        "hook_extraction_f1": 0.9,
        "selling_point_recall": 0.85,
        "schema_validity_rate": 1.0,
        "strategy_brief_quality": 4.5,
    }


def test_evaluate_run_pass():
    cfg = ThresholdConfig.load(THRESHOLDS)
    fixtures = [
        evaluate_fixture(f"dev-{i}", "dev", _good_scores(), cfg, cost_usd=0.01, wall_seconds=20)
        for i in range(15)
    ] + [
        evaluate_fixture(f"hold-{i}", "holdout", _good_scores(), cfg, cost_usd=0.01, wall_seconds=20)
        for i in range(5)
    ]
    run = evaluate_run(fixtures, cfg, label="baseline")
    assert run.passed
    assert run.dev_pass_rate == 1.0
    assert run.holdout_pass_rate == 1.0
    assert run.total_cost_usd == pytest.approx(0.20)


def test_evaluate_run_dev_pass_rate_fail():
    cfg = ThresholdConfig.load(THRESHOLDS)
    bad = {
        "hook_extraction_f1": 0.5,
        "selling_point_recall": 0.85,
        "schema_validity_rate": 1.0,
        "strategy_brief_quality": 4.5,
    }
    fixtures = (
        [evaluate_fixture(f"dev-{i}", "dev", bad, cfg) for i in range(5)]  # all fail
        + [evaluate_fixture(f"dev-{i}", "dev", _good_scores(), cfg) for i in range(10)]
    )
    run = evaluate_run(fixtures, cfg, label="baseline")
    # 10/15 = 0.66 < 0.80
    assert not run.passed
    assert any("dev_pass_rate" in f for f in run.failures)


def test_evaluate_run_holdout_must_be_perfect():
    cfg = ThresholdConfig.load(THRESHOLDS)
    fixtures = [
        evaluate_fixture(f"dev-{i}", "dev", _good_scores(), cfg) for i in range(15)
    ] + [
        evaluate_fixture("hold-0", "holdout", _good_scores(), cfg),
        evaluate_fixture(
            "hold-1",
            "holdout",
            {**_good_scores(), "hook_extraction_f1": 0.5},
            cfg,
        ),
    ]
    run = evaluate_run(fixtures, cfg)
    assert not run.passed
    assert any("holdout_pass_rate" in f for f in run.failures)


def test_evaluate_run_cost_cap():
    cfg = ThresholdConfig.load(THRESHOLDS)
    fixtures = [
        evaluate_fixture(f"dev-{i}", "dev", _good_scores(), cfg, cost_usd=0.10)
        for i in range(15)  # 15 * 0.10 = $1.50 > $0.50
    ]
    run = evaluate_run(fixtures, cfg)
    assert not run.passed
    assert any("cost" in f for f in run.failures)


def test_evaluate_run_wall_cap():
    cfg = ThresholdConfig.load(THRESHOLDS)
    fixtures = [
        evaluate_fixture(f"dev-{i}", "dev", _good_scores(), cfg, wall_seconds=100)
        for i in range(15)  # 15 * 100 = 1500 > 900
    ]
    run = evaluate_run(fixtures, cfg)
    assert not run.passed
    assert any("wall" in f for f in run.failures)


def test_write_reports_roundtrip(tmp_path):
    cfg = ThresholdConfig.load(THRESHOLDS)
    fixtures = [
        evaluate_fixture(f"dev-{i}", "dev", _good_scores(), cfg, cost_usd=0.01, wall_seconds=20)
        for i in range(3)
    ]
    run = evaluate_run(fixtures, cfg, label="baseline")
    out = write_reports(run, reports_root=tmp_path, run_id="test-run")
    assert (out / "summary.md").exists()
    summary = json.loads((out / "summary.json").read_text())
    assert summary["passed"] is True
    assert summary["fixture_count"] == 3
    fx = json.loads((out / "fixtures.json").read_text())
    assert len(fx) == 3
    md = (out / "summary.md").read_text()
    assert "PASS" in md
    assert "dev-0" in md


def test_run_eval_cli_dry_run(tmp_path):
    res = subprocess.run(
        [
            sys.executable,
            "-m",
            "voyager_evals.eric.run_eval",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "dry-run" in res.stdout


def test_run_eval_cli_pass_fail_exit_codes(tmp_path):
    # PASS scenario: all 15 dev good
    good_payload = [
        {
            "fixture_id": f"dev-{i}",
            "bucket": "dev",
            "scores": _good_scores(),
            "cost_usd": 0.01,
            "wall_seconds": 20,
        }
        for i in range(15)
    ] + [
        {
            "fixture_id": f"hold-{i}",
            "bucket": "holdout",
            "scores": _good_scores(),
            "cost_usd": 0.01,
            "wall_seconds": 20,
        }
        for i in range(5)
    ]
    pass_path = tmp_path / "pass.json"
    pass_path.write_text(json.dumps(good_payload))
    res = subprocess.run(
        [
            sys.executable,
            "-m",
            "voyager_evals.eric.run_eval",
            "--label", "baseline",
            "--scores-file", str(pass_path),
            "--reports-root", str(tmp_path / "reports"),
            "--run-id", "pass-run",
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stderr

    # FAIL scenario: cost overrun
    bad_payload = [
        {
            "fixture_id": f"dev-{i}",
            "bucket": "dev",
            "scores": _good_scores(),
            "cost_usd": 1.0,
            "wall_seconds": 20,
        }
        for i in range(15)
    ]
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(bad_payload))
    res2 = subprocess.run(
        [
            sys.executable,
            "-m",
            "voyager_evals.eric.run_eval",
            "--label", "baseline",
            "--scores-file", str(bad_path),
            "--reports-root", str(tmp_path / "reports"),
            "--run-id", "fail-run",
        ],
        capture_output=True,
        text=True,
    )
    assert res2.returncode == 1
