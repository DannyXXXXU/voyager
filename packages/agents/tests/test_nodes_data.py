"""Tests for data-subgraph nodes (fully offline, mocked voyager_tools)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from voyager_agents.eric import nodes_data
from voyager_agents.eric.state import EricState
from voyager_db import Comment, LLMStatus, Transcript, Video
from voyager_tools.errors import AuthRequiredError, VideoUnavailableError
from voyager_tools.models import AudioFile, CommentItem, TranscriptResult, VideoSearchResult


def _vsr(vid: str, title: str = "t") -> VideoSearchResult:
    return VideoSearchResult(
        video_id=vid,
        title=title,
        channel_id="UC1",
        channel_title="ch",
        published_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
    )


def test_plan_search_fills_keywords() -> None:
    state = EricState(topic="yunnan")
    out = nodes_data.node_plan_search(state)
    assert len(out.keywords) >= 3
    assert "yunnan" in out.keywords[0]


def test_plan_search_respects_existing_keywords() -> None:
    state = EricState(topic="yunnan", keywords=["custom kw"])
    out = nodes_data.node_plan_search(state)
    assert out.keywords == ["custom kw"]


def test_fetch_metadata_dedupes_and_caps(mocker: Any) -> None:
    calls: list[str] = []

    def fake_search(query: str, **kw: Any) -> list[VideoSearchResult]:
        calls.append(query)
        # same video_id appears across keywords to exercise dedup
        return [_vsr("dup", query), _vsr(f"uniq-{len(calls)}", query)]

    mocker.patch.object(nodes_data.youtube_search, "search_videos", side_effect=fake_search)

    state = EricState(topic="yunnan", keywords=["a", "b", "c"], max_videos=3)
    out = nodes_data.node_fetch_metadata(state)
    ids = [v.video_id for v in out.search_results]
    assert "dup" in ids
    assert len(ids) == len(set(ids))
    assert len(ids) <= 3


def test_download_audio_skips_unavailable_and_auth(mocker: Any, tmp_path: Path) -> None:
    def fake_dl(video_id: str, output_dir: Path, **kw: Any) -> AudioFile:
        if video_id == "priv":
            raise VideoUnavailableError("private video")
        if video_id == "age":
            raise AuthRequiredError("sign in to confirm your age")
        return AudioFile(
            video_id=video_id,
            path=output_dir / f"{video_id}.m4a",
            duration_s=60.0,
            size_bytes=1024,
            sample_rate=16000,
        )

    mocker.patch.object(nodes_data.yt_dlp_audio, "download_audio", side_effect=fake_dl)

    state = EricState(
        topic="t",
        search_results=[_vsr("ok"), _vsr("priv"), _vsr("age")],
    )
    out = nodes_data.node_download_audio(state, output_dir=tmp_path)
    assert [a.video_id for a in out.downloaded] == ["ok"]
    assert len(out.errors) == 2


def test_transcribe_fills_transcripts(mocker: Any, tmp_path: Path) -> None:
    async def fake_transcribe(audio_path: Path, **kw: Any) -> TranscriptResult:
        return TranscriptResult(
            text=f"text for {audio_path.name}", language="en", duration_s=60.0
        )

    mocker.patch.object(nodes_data.whisper_client, "transcribe", side_effect=fake_transcribe)

    state = EricState(topic="t")
    state.downloaded = [
        AudioFile(
            video_id="v1",
            path=tmp_path / "v1.m4a",
            duration_s=60.0,
            size_bytes=1024,
            sample_rate=16000,
        ),
        AudioFile(
            video_id="v2",
            path=tmp_path / "v2.m4a",
            duration_s=60.0,
            size_bytes=1024,
            sample_rate=16000,
        ),
    ]
    out = nodes_data.node_transcribe(state)
    assert set(out.transcripts.keys()) == {"v1", "v2"}
    assert "v1.m4a" in out.transcripts["v1"].text


def test_fetch_comments_per_video(mocker: Any) -> None:
    def fake_fetch(video_id: str, max_comments: int = 50, **kw: Any) -> list[CommentItem]:
        return [
            CommentItem(
                comment_id=f"{video_id}-c1",
                author="u",
                text="nice",
                like_count=1,
                published_at=datetime(2024, 6, 2, tzinfo=timezone.utc),
            )
        ]

    mocker.patch.object(
        nodes_data.comments_fetch, "fetch_top_comments", side_effect=fake_fetch
    )

    state = EricState(topic="t", search_results=[_vsr("v1"), _vsr("v2")])
    out = nodes_data.node_fetch_comments(state)
    assert set(out.comments.keys()) == {"v1", "v2"}
    assert out.comments["v1"][0].comment_id == "v1-c1"


def test_persist_writes_rows_to_sqlite() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    state = EricState(
        topic="yunnan",
        search_results=[_vsr("v1", "Yunnan"), _vsr("v2", "Dali")],
        transcripts={
            "v1": TranscriptResult(text="hello v1", language="en", duration_s=60.0)
        },
        comments={
            "v1": [
                CommentItem(
                    comment_id="c1",
                    author="u",
                    text="great",
                    like_count=2,
                    published_at=datetime(2024, 6, 2, tzinfo=timezone.utc),
                )
            ]
        },
    )

    with Session(engine) as session:
        nodes_data.node_persist(state, session)

    with Session(engine) as session:
        vids = session.exec(select(Video)).all()
        trs = session.exec(select(Transcript)).all()
        cms = session.exec(select(Comment)).all()

    assert {v.video_id for v in vids} == {"v1", "v2"}
    assert all(v.llm_status == LLMStatus.pending for v in vids)
    assert len(trs) == 1 and trs[0].video_id == "v1"
    assert len(cms) == 1 and cms[0].text == "great"


def test_persist_is_idempotent_on_duplicate_video_id() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    state = EricState(topic="t", search_results=[_vsr("v1")])
    with Session(engine) as session:
        nodes_data.node_persist(state, session)
        nodes_data.node_persist(state, session)  # should not error

    with Session(engine) as session:
        vids = session.exec(select(Video)).all()
    assert len(vids) == 1
