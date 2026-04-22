"""Offline data layer for Eric eval.

During eval runs we do NOT hit YouTube / Apify / Whisper / Postgres. Instead
the eval harness pre-fetches transcript+comments for each seed video once
(via scripts/prefetch_gold.py) and stores them as JSON under:

    packages/evals/voyager_evals/eric/gold/transcripts/<video_id>.json
    packages/evals/voyager_evals/eric/gold/comments/<video_id>.json

This module loads those files and produces a fully-hydrated EricState so the
LLM subgraph (build_llm_graph) can run deterministically against fixed inputs.

Public API:
    load_gold_state(fixture_id, gold_dir, seed) -> EricState
    build_eval_graph(client)  — alias for build_llm_graph; marker for eval path
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from voyager_agents.eric.state import EricState
from voyager_tools.models import CommentItem, TranscriptResult, VideoSearchResult


class GoldMissingError(FileNotFoundError):
    """Raised when expected gold/ artifacts are missing for a video_id."""


def _load_seed(seed_path: Path) -> dict[str, Any]:
    return yaml.safe_load(seed_path.read_text(encoding="utf-8"))


def _find_fixture(seed: dict[str, Any], fixture_id: str) -> dict[str, Any]:
    for key in ("dev", "holdout"):
        for entry in seed.get(key, []):
            if entry["id"] == fixture_id:
                return entry
    raise KeyError(f"fixture_id {fixture_id!r} not found in seed.yaml")


def load_gold_state(
    fixture_id: str,
    gold_dir: Path,
    seed_path: Path,
    topic_override: str | None = None,
) -> EricState:
    """Build a pre-hydrated EricState for one fixture.

    Parameters
    ----------
    fixture_id : e.g. "dev-food-01"
    gold_dir   : path to .../eric/gold/
    seed_path  : path to .../eric/seed.yaml

    Returns
    -------
    EricState populated with search_results (1 entry), transcripts, comments.
    downloaded[] is left empty — the LLM subgraph does not read it.

    Raises
    ------
    GoldMissingError if transcripts/<vid>.json or comments/<vid>.json missing.
    KeyError if fixture_id not in seed.
    """
    seed = _load_seed(seed_path)
    entry = _find_fixture(seed, fixture_id)
    video_id = entry["video_id"]

    tr_path = gold_dir / "transcripts" / f"{video_id}.json"
    cm_path = gold_dir / "comments" / f"{video_id}.json"
    if not tr_path.exists():
        raise GoldMissingError(f"missing transcript gold: {tr_path}")
    if not cm_path.exists():
        raise GoldMissingError(f"missing comments gold: {cm_path}")

    tr_raw = json.loads(tr_path.read_text(encoding="utf-8"))
    cm_raw = json.loads(cm_path.read_text(encoding="utf-8"))

    # Transcripts gold schema: {text, language, duration_s, segments}
    transcript = TranscriptResult(**tr_raw)

    # Comments gold schema: list of CommentItem dicts
    comments = [CommentItem(**c) for c in cm_raw]

    # Minimal VideoSearchResult stub — title/channel filled from seed metadata.
    vsr = VideoSearchResult(
        video_id=video_id,
        title=topic_override or entry["topic"],
        channel_id="gold",
        channel_title="gold",
        published_at=datetime(2024, 1, 1),
        description=entry.get("notes", ""),
        thumbnail_url=None,
    )

    return EricState(
        topic=topic_override or entry["topic"],
        keywords=[entry["topic"]],
        max_videos=1,
        search_results=[vsr],
        transcripts={video_id: transcript},
        comments={video_id: comments},
    )


def build_eval_graph(client):  # type: ignore[no-untyped-def]
    """Return a compiled LLM-only graph for eval runs.

    Thin marker wrapper around build_llm_graph — gives the eval harness a
    distinct import path even though the graph topology is identical.
    """
    from voyager_agents.eric.graph import build_llm_graph

    return build_llm_graph(client)
