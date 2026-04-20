"""YouTube Data API commentThreads fetcher (paginated, graceful on disabled)."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from voyager_tools.errors import ConfigError, QuotaExceededError, ToolError
from voyager_tools.models import CommentItem


class _RetryableHttpError(ToolError):
    pass


class _CommentsDisabled(ToolError):
    pass


def _classify_http_error(exc: HttpError) -> Exception:
    status = getattr(exc.resp, "status", None)
    reason = ""
    try:
        data = json.loads(exc.content.decode("utf-8"))
        errors = data.get("error", {}).get("errors", [])
        if errors:
            reason = errors[0].get("reason", "")
    except Exception:
        pass

    if status == 403 and reason in ("commentsDisabled", "videoNotFound"):
        return _CommentsDisabled(reason or "commentsDisabled")
    if status == 403 and reason == "quotaExceeded":
        return QuotaExceededError("YouTube Data API quota exceeded")
    if status == 403:
        return QuotaExceededError(f"YouTube Data API 403 ({reason or 'forbidden'})")
    if status and status >= 500:
        return _RetryableHttpError(f"YouTube 5xx: {status}")
    return exc


@retry(
    retry=retry_if_exception_type(_RetryableHttpError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    reraise=True,
)
def _execute(request: Any) -> dict:
    try:
        return request.execute()
    except HttpError as exc:
        raise _classify_http_error(exc) from exc


def _parse_thread(thread: dict) -> CommentItem:
    top = thread["snippet"]["topLevelComment"]
    snip = top["snippet"]
    return CommentItem(
        comment_id=top.get("id", thread.get("id", "")),
        author=snip.get("authorDisplayName", ""),
        text=snip.get("textDisplay", ""),
        like_count=int(snip.get("likeCount", 0) or 0),
        published_at=datetime.fromisoformat(
            snip["publishedAt"].replace("Z", "+00:00")
        ),
        reply_count=int(thread["snippet"].get("totalReplyCount", 0) or 0),
    )


def fetch_top_comments(
    video_id: str,
    max_comments: int = 100,
    order: str = "relevance",
    api_key: str | None = None,
) -> list[CommentItem]:
    """Fetch up to max_comments top-level comments for a YouTube video.

    Returns [] if comments are disabled. Raises QuotaExceededError on other 403.
    """
    key = api_key or os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise ConfigError(
            "YouTube API key is required (pass api_key= or set YOUTUBE_API_KEY)"
        )

    youtube = build("youtube", "v3", developerKey=key, cache_discovery=False)

    results: list[CommentItem] = []
    page_token: str | None = None

    while len(results) < max_comments:
        params: dict[str, Any] = {
            "part": "snippet,replies",
            "videoId": video_id,
            "order": order,
            "textFormat": "plainText",
            "maxResults": min(100, max_comments - len(results)),
        }
        if page_token:
            params["pageToken"] = page_token

        request = youtube.commentThreads().list(**params)
        try:
            response = _execute(request)
        except _CommentsDisabled:
            return []

        for item in response.get("items", []) or []:
            results.append(_parse_thread(item))
            if len(results) >= max_comments:
                break

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return results
