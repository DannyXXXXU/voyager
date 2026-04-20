"""Tests for voyager_tools.comments_fetch (offline, mocked googleapiclient)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from voyager_tools.errors import QuotaExceededError
from voyager_tools.comments_fetch import fetch_top_comments


def _fake_thread(comment_id: str, text: str = "hi", reply_count: int = 0) -> dict:
    return {
        "id": comment_id,
        "snippet": {
            "topLevelComment": {
                "id": comment_id,
                "snippet": {
                    "authorDisplayName": "alice",
                    "textDisplay": text,
                    "likeCount": 3,
                    "publishedAt": "2025-01-01T00:00:00Z",
                },
            },
            "totalReplyCount": reply_count,
        },
    }


def _http_error(status: int, reason: str) -> HttpError:
    resp = MagicMock()
    resp.status = status
    resp.reason = "Forbidden"
    content = (
        b'{"error":{"code":' + str(status).encode() + b',"errors":[{"reason":"'
        + reason.encode()
        + b'"}]}}'
    )
    return HttpError(resp, content)


def test_fetch_paginates_over_two_pages(mocker):
    mock_build = mocker.patch("voyager_tools.comments_fetch.build")
    youtube = MagicMock()

    page1 = {
        "items": [_fake_thread("c1"), _fake_thread("c2")],
        "nextPageToken": "tok2",
    }
    page2 = {"items": [_fake_thread("c3")]}

    list_mock = youtube.commentThreads.return_value.list
    list_mock.return_value.execute.side_effect = [page1, page2]
    mock_build.return_value = youtube

    results = fetch_top_comments("vid", max_comments=10, api_key="fake")

    assert [c.comment_id for c in results] == ["c1", "c2", "c3"]
    assert results[0].author == "alice"
    assert results[0].like_count == 3
    assert list_mock.call_count == 2
    # Second call should include pageToken
    assert list_mock.call_args_list[1].kwargs.get("pageToken") == "tok2"


def test_fetch_returns_empty_on_comments_disabled(mocker):
    mock_build = mocker.patch("voyager_tools.comments_fetch.build")
    youtube = MagicMock()
    youtube.commentThreads.return_value.list.return_value.execute.side_effect = (
        _http_error(403, "commentsDisabled")
    )
    mock_build.return_value = youtube

    assert fetch_top_comments("vid", api_key="fake") == []


def test_fetch_raises_quota_exceeded(mocker):
    mock_build = mocker.patch("voyager_tools.comments_fetch.build")
    youtube = MagicMock()
    youtube.commentThreads.return_value.list.return_value.execute.side_effect = (
        _http_error(403, "quotaExceeded")
    )
    mock_build.return_value = youtube

    with pytest.raises(QuotaExceededError):
        fetch_top_comments("vid", api_key="fake")
