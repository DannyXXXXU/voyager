"""Tests for voyager_tools.youtube_search (offline, mocked googleapiclient)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from voyager_tools.errors import ConfigError, QuotaExceededError
from voyager_tools.youtube_search import search_videos


def _fake_search_response(num: int = 2) -> dict:
    items = []
    for i in range(num):
        items.append(
            {
                "id": {"videoId": f"vid{i}"},
                "snippet": {
                    "title": f"Title {i}",
                    "channelId": f"ch{i}",
                    "channelTitle": f"Channel {i}",
                    "publishedAt": "2025-01-01T00:00:00Z",
                    "description": f"Desc {i}",
                    "thumbnails": {
                        "high": {"url": f"https://img/{i}.jpg"}
                    },
                },
            }
        )
    return {"items": items}


def _make_build_mock(response: dict) -> MagicMock:
    """Build a mock googleapiclient.discovery.build returning the given response."""
    youtube = MagicMock()
    youtube.search.return_value.list.return_value.execute.return_value = response
    return youtube


def _http_error(status: int, reason: str = "quotaExceeded") -> HttpError:
    resp = MagicMock()
    resp.status = status
    resp.reason = "Forbidden"
    content = (
        b'{"error":{"code":' + str(status).encode() + b',"errors":[{"reason":"'
        + reason.encode()
        + b'"}]}}'
    )
    return HttpError(resp, content)


def test_search_returns_parsed_list(mocker):
    mock_build = mocker.patch("voyager_tools.youtube_search.build")
    mock_build.return_value = _make_build_mock(_fake_search_response(2))

    results = search_videos("shanghai travel", max_results=2, api_key="fake")

    assert len(results) == 2
    assert results[0].video_id == "vid0"
    assert results[0].title == "Title 0"
    assert results[0].channel_id == "ch0"
    assert results[0].thumbnail_url == "https://img/0.jpg"


def test_search_raises_config_error_when_no_api_key(mocker, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        search_videos("q")


def test_search_raises_quota_exceeded(mocker):
    mock_build = mocker.patch("voyager_tools.youtube_search.build")
    youtube = MagicMock()
    youtube.search.return_value.list.return_value.execute.side_effect = _http_error(
        403, "quotaExceeded"
    )
    mock_build.return_value = youtube

    with pytest.raises(QuotaExceededError):
        search_videos("q", api_key="fake")
