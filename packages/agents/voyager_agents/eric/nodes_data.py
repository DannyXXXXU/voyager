"""Data-subgraph nodes for the Eric agent (cloud-worker pipeline).

Flow:
    plan_search -> fetch_metadata -> download_audio -> transcribe
                 -> fetch_comments -> persist -> END

Nodes perform pure data IO via voyager_tools and never call LLMs.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import structlog

from voyager_agents.eric.state import EricState
from voyager_db import Comment, LLMStatus, Transcript, Video
from voyager_tools import comments_fetch, whisper_client, youtube_search, yt_dlp_audio
from voyager_tools.errors import (
    AudioTooLargeError,
    AuthRequiredError,
    QuotaExceededError,
    VideoUnavailableError,
)

log = structlog.get_logger()

# TODO(langfuse): decorate each node with @observe once langfuse wiring lands.


# --------------------------------------------------------------------------- #
# plan_search
# --------------------------------------------------------------------------- #
def node_plan_search(state: EricState) -> EricState:
    """Expand state.topic into 3-5 search keywords.

    TODO: replace with Copilot-generated query fan-out once the local CLI
    integration is proven. For now a deterministic template is used.
    """
    if state.keywords:
        return state
    topic = state.topic.strip()
    kws = [topic, f"{topic} travel", f"{topic} vlog", f"{topic} guide", f"{topic} tips"]
    state.keywords = kws[:5]
    log.info("plan_search", topic=topic, keywords=state.keywords)
    return state


# --------------------------------------------------------------------------- #
# fetch_metadata
# --------------------------------------------------------------------------- #
def node_fetch_metadata(state: EricState) -> EricState:
    """Run YouTube search per keyword; dedupe by video_id; keep top N."""
    seen: set[str] = set()
    collected: list[Any] = []
    per_kw = max(5, state.max_videos // max(1, len(state.keywords or [state.topic])))
    for kw in state.keywords or [state.topic]:
        try:
            items = youtube_search.search_videos(
                query=kw,
                max_results=per_kw,
                region_code=state.region_code,
                relevance_language=state.language,
            )
        except QuotaExceededError as exc:
            state.errors.append({"node": "fetch_metadata", "keyword": kw, "error": str(exc)})
            log.warning("fetch_metadata.quota_exceeded", keyword=kw)
            break
        except Exception as exc:  # noqa: BLE001
            state.errors.append({"node": "fetch_metadata", "keyword": kw, "error": str(exc)})
            continue
        for item in items:
            if item.video_id in seen:
                continue
            seen.add(item.video_id)
            collected.append(item)
            if len(collected) >= state.max_videos:
                break
        if len(collected) >= state.max_videos:
            break
    state.search_results = collected[: state.max_videos]
    log.info("fetch_metadata.done", n=len(state.search_results))
    return state


# --------------------------------------------------------------------------- #
# download_audio
# --------------------------------------------------------------------------- #
def node_download_audio(state: EricState, output_dir: Path | None = None) -> EricState:
    """Download audio for each search result; skip unavailable/auth-gated videos."""
    out = Path(output_dir) if output_dir is not None else Path(tempfile.gettempdir()) / "voyager_audio"
    out.mkdir(parents=True, exist_ok=True)
    for vsr in state.search_results:
        try:
            audio = yt_dlp_audio.download_audio(video_id=vsr.video_id, output_dir=out)
            state.downloaded.append(audio)
        except (VideoUnavailableError, AuthRequiredError) as exc:
            state.errors.append(
                {"node": "download_audio", "video_id": vsr.video_id, "error": str(exc)}
            )
            log.info("download_audio.skip", video_id=vsr.video_id, reason=type(exc).__name__)
            continue
        except Exception as exc:  # noqa: BLE001
            state.errors.append(
                {"node": "download_audio", "video_id": vsr.video_id, "error": str(exc)}
            )
            log.warning("download_audio.error", video_id=vsr.video_id, error=str(exc))
    return state


# --------------------------------------------------------------------------- #
# transcribe
# --------------------------------------------------------------------------- #
def node_transcribe(state: EricState) -> EricState:
    """Run Azure OpenAI Whisper on each downloaded audio."""
    for audio in state.downloaded:
        try:
            result = asyncio.run(whisper_client.transcribe(audio_path=audio.path))
        except AudioTooLargeError as exc:
            state.errors.append(
                {"node": "transcribe", "video_id": audio.video_id, "error": str(exc)}
            )
            continue
        except Exception as exc:  # noqa: BLE001
            state.errors.append(
                {"node": "transcribe", "video_id": audio.video_id, "error": str(exc)}
            )
            continue
        state.transcripts[audio.video_id] = result
    return state


# --------------------------------------------------------------------------- #
# fetch_comments
# --------------------------------------------------------------------------- #
def node_fetch_comments(state: EricState, max_comments: int = 50) -> EricState:
    """Fetch top comments for each discovered video."""
    for vsr in state.search_results:
        try:
            items = comments_fetch.fetch_top_comments(
                video_id=vsr.video_id, max_comments=max_comments
            )
        except QuotaExceededError as exc:
            state.errors.append(
                {"node": "fetch_comments", "video_id": vsr.video_id, "error": str(exc)}
            )
            break
        except Exception as exc:  # noqa: BLE001
            state.errors.append(
                {"node": "fetch_comments", "video_id": vsr.video_id, "error": str(exc)}
            )
            continue
        state.comments[vsr.video_id] = items
    return state


# --------------------------------------------------------------------------- #
# persist
# --------------------------------------------------------------------------- #
def node_persist(state: EricState, session: Any) -> EricState:
    """Upsert Video/Transcript/Comment rows; mark llm_status=pending.

    `session` is any SQLModel/SQLAlchemy Session. The cloud-worker passes a
    Postgres session; tests pass an in-memory SQLite session.
    """
    for vsr in state.search_results:
        existing = session.get(Video, vsr.video_id)
        if existing is None:
            session.add(
                Video(
                    video_id=vsr.video_id,
                    title=vsr.title,
                    channel_id=vsr.channel_id,
                    channel_title=vsr.channel_title,
                    published_at=vsr.published_at,
                    thumbnail_url=vsr.thumbnail_url,
                    description=vsr.description or None,
                    lang=state.language,
                    region=state.region_code,
                    source_query=state.topic,
                    llm_status=LLMStatus.pending,
                )
            )
    session.commit()

    for video_id, tr in state.transcripts.items():
        session.add(
            Transcript(
                video_id=video_id,
                text=tr.text,
                segments=tr.segments or None,
                language=tr.language,
            )
        )
    for video_id, items in state.comments.items():
        for c in items:
            session.add(
                Comment(
                    video_id=video_id,
                    author=c.author,
                    text=c.text,
                    like_count=c.like_count,
                    published_at=c.published_at,
                )
            )
    session.commit()
    log.info(
        "persist.done",
        videos=len(state.search_results),
        transcripts=len(state.transcripts),
        comments=sum(len(v) for v in state.comments.values()),
    )
    return state
