from datetime import datetime, timezone
from pathlib import Path

from voyager_agents.eric.state import EricState
from voyager_tools.models import AudioFile, CommentItem, TranscriptResult, VideoSearchResult


def _vsr(vid: str = "abc123") -> VideoSearchResult:
    return VideoSearchResult(
        video_id=vid,
        title="Yunnan in 4K",
        channel_id="UCxxx",
        channel_title="Travel Ch",
        published_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
    )


def test_eric_state_defaults_and_run_id() -> None:
    s = EricState(topic="yunnan")
    assert s.topic == "yunnan"
    assert s.region_code == "US"
    assert s.language == "en"
    assert s.max_videos == 20
    assert s.keywords == []
    assert s.search_results == []
    assert s.brief_md is None
    assert isinstance(s.run_id, str) and len(s.run_id) >= 32


def test_eric_state_roundtrip() -> None:
    orig = EricState(
        topic="sichuan",
        keywords=["chengdu"],
        search_results=[_vsr("v1")],
        downloaded=[
            AudioFile(
                video_id="v1",
                path=Path("/tmp/v1.m4a"),
                duration_s=120.0,
                size_bytes=1024,
                sample_rate=16000,
            )
        ],
        transcripts={"v1": TranscriptResult(text="hello", language="en", duration_s=120.0)},
        comments={
            "v1": [
                CommentItem(
                    comment_id="c1",
                    author="u1",
                    text="great",
                    like_count=3,
                    published_at=datetime(2024, 6, 2, tzinfo=timezone.utc),
                )
            ]
        },
        hooks=[{"video_id": "v1", "hook_text": "wow"}],
    )
    dumped = orig.model_dump()
    restored = EricState.model_validate(dumped)
    assert restored.topic == "sichuan"
    assert restored.search_results[0].video_id == "v1"
    assert restored.transcripts["v1"].text == "hello"
    assert restored.comments["v1"][0].author == "u1"
    assert restored.hooks[0]["hook_text"] == "wow"
