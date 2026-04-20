"""YouTube Data API search wrapper."""

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
from voyager_tools.models import VideoSearchResult


class _RetryableHttpError(ToolError):
    """Internal: wrap transient HttpError so tenacity only retries on these."""


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


def _parse_item(item: dict) -> VideoSearchResult:
    snippet = item["snippet"]
    thumbs = snippet.get("thumbnails", {}) or {}
    # Prefer high, fall back to default
    thumb_url: str | None = None
    for key in ("high", "medium", "default"):
        if key in thumbs and thumbs[key].get("url"):
            thumb_url = thumbs[key]["url"]
            break
    return VideoSearchResult(
        video_id=item["id"]["videoId"],
        title=snippet["title"],
        channel_id=snippet["channelId"],
        channel_title=snippet["channelTitle"],
        published_at=datetime.fromisoformat(
            snippet["publishedAt"].replace("Z", "+00:00")
        ),
        description=snippet.get("description", ""),
        thumbnail_url=thumb_url,
    )


def search_videos(
    query: str,
    max_results: int = 50,
    published_after: datetime | None = None,
    region_code: str = "US",
    relevance_language: str = "en",
    api_key: str | None = None,
) -> list[VideoSearchResult]:
    """Search YouTube videos via Data API v3.

    Raises:
        ConfigError: if api_key is not provided and YOUTUBE_API_KEY is unset.
        QuotaExceededError: on 403 quotaExceeded / other 403.
    """
    key = api_key or os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise ConfigError(
            "YouTube API key is required (pass api_key= or set YOUTUBE_API_KEY)"
        )

    youtube = build("youtube", "v3", developerKey=key, cache_discovery=False)

    params: dict[str, Any] = {
        "q": query,
        "type": "video",
        "part": "snippet",
        "maxResults": min(max_results, 50),
        "regionCode": region_code,
        "relevanceLanguage": relevance_language,
    }
    if published_after is not None:
        params["publishedAfter"] = published_after.strftime("%Y-%m-%dT%H:%M:%SZ")

    request = youtube.search().list(**params)
    response = _execute(request)

    items = response.get("items", []) or []
    return [_parse_item(it) for it in items[:max_results]]
