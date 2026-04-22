"""Test load_gold_state with a synthetic gold fixture."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from voyager_evals.eric.nodes_data_eval import GoldMissingError, load_gold_state


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, default=str), encoding="utf-8")


@pytest.fixture
def tmp_gold(tmp_path: Path) -> tuple[Path, Path]:
    gold_dir = tmp_path / "gold"
    seed_path = tmp_path / "seed.yaml"
    seed = {
        "dev": [
            {
                "id": "dev-test-01",
                "video_id": "ABC123",
                "topic": "Test video",
                "content_type": "vlog",
                "difficulty": "easy",
                "holdout": False,
                "notes": "",
            }
        ],
        "holdout": [],
    }
    seed_path.write_text(yaml.safe_dump(seed), encoding="utf-8")

    _write(
        gold_dir / "transcripts" / "ABC123.json",
        {"text": "hello world", "language": "en", "duration_s": 12.5, "segments": []},
    )
    _write(
        gold_dir / "comments" / "ABC123.json",
        [
            {
                "comment_id": "c1",
                "author": "alice",
                "text": "great video",
                "like_count": 3,
                "published_at": "2024-05-01T00:00:00",
                "reply_count": 0,
            }
        ],
    )
    return gold_dir, seed_path


def test_load_gold_state_happy_path(tmp_gold: tuple[Path, Path]):
    gold_dir, seed_path = tmp_gold
    state = load_gold_state("dev-test-01", gold_dir, seed_path)
    assert state.topic == "Test video"
    assert len(state.search_results) == 1
    assert state.search_results[0].video_id == "ABC123"
    assert "ABC123" in state.transcripts
    assert state.transcripts["ABC123"].text == "hello world"
    assert len(state.comments["ABC123"]) == 1


def test_load_gold_state_missing_transcript(tmp_path: Path):
    seed_path = tmp_path / "seed.yaml"
    seed_path.write_text(
        yaml.safe_dump(
            {
                "dev": [
                    {
                        "id": "dev-x",
                        "video_id": "ZZZ",
                        "topic": "t",
                        "content_type": "vlog",
                        "difficulty": "easy",
                        "holdout": False,
                    }
                ],
                "holdout": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(GoldMissingError):
        load_gold_state("dev-x", tmp_path / "gold", seed_path)


def test_load_gold_state_unknown_fixture(tmp_gold: tuple[Path, Path]):
    gold_dir, seed_path = tmp_gold
    with pytest.raises(KeyError):
        load_gold_state("nonexistent", gold_dir, seed_path)
