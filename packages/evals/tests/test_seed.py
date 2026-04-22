"""Sanity checks for seed.yaml — 15 dev + 5 holdout, unique ids."""
from __future__ import annotations

from pathlib import Path

import yaml

SEED = Path(__file__).resolve().parents[1] / "voyager_evals" / "eric" / "seed.yaml"


def load_seed() -> dict:
    return yaml.safe_load(SEED.read_text(encoding="utf-8"))


def test_seed_counts():
    data = load_seed()
    assert len(data["dev"]) == 15, "expected 15 dev videos"
    assert len(data["holdout"]) == 5, "expected 5 holdout videos"


def test_seed_unique_ids():
    data = load_seed()
    ids = [e["id"] for e in data["dev"] + data["holdout"]]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"


def test_seed_holdout_flag():
    data = load_seed()
    assert all(e["holdout"] is False for e in data["dev"])
    assert all(e["holdout"] is True for e in data["holdout"])


def test_seed_difficulty_mix_dev():
    data = load_seed()
    diffs = [e["difficulty"] for e in data["dev"]]
    for level in ("easy", "medium", "hard"):
        assert diffs.count(level) >= 3, f"need ≥3 {level} dev videos, got {diffs.count(level)}"
