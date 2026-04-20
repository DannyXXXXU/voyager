"""Apify-backed audio downloader for YouTube videos.

Uses the `lurkapi/youtube-to-mp3-audio-downloader` actor which handles the
bot-check that currently blocks yt-dlp from Azure WSL egress IPs. The actor
writes an MP3 file to its run's default key-value store; we download it via
httpx using the Apify token for auth.

Input (per actor):
    {"videoUrls": ["https://www.youtube.com/watch?v=VIDEO_ID"]}

Output dataset item (relevant fields):
    status: "Success" | ...
    error: str | None
    videoId, title, duration (seconds), fileSize, audioFormat ("mp3")
    audioFileUrl: "https://api.apify.com/v2/key-value-stores/<kvs>/records/<key>"
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
from apify_client import ApifyClient
from apify_client.errors import ApifyApiError

from voyager_tools.errors import VideoUnavailableError
from voyager_tools.models import AudioFile

DEFAULT_ACTOR_ID = "lurkapi/youtube-to-mp3-audio-downloader"
DEFAULT_TIMEOUT_S = 600


_UNAVAILABLE_TOKENS = (
    "video unavailable",
    "removed",
    "private",
    "not available",
    "age-restricted",
    "members-only",
)


def _resolve_token(token: str | None) -> str:
    tok = token or os.environ.get("APIFY_TOKEN")
    if not tok:
        raise RuntimeError(
            "Apify token not provided; set APIFY_TOKEN env or pass token=..."
        )
    return tok


def download_audio_via_apify(
    video_id: str,
    output_dir: Path,
    token: str | None = None,
    actor_id: str = DEFAULT_ACTOR_ID,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    format: str = "mp3",
) -> AudioFile:
    """Run the Apify actor for a single video and return an AudioFile.

    Raises:
        VideoUnavailableError: if the actor reports the video unavailable.
        TimeoutError: if the run does not finish within timeout_s.
        RuntimeError: any other actor-side failure or missing audio URL.
    """
    tok = _resolve_token(token)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    client = ApifyClient(tok)
    url = f"https://www.youtube.com/watch?v={video_id}"

    try:
        run = client.actor(actor_id).call(
            run_input={"videoUrls": [url]}, timeout_secs=timeout_s
        )
    except ApifyApiError as exc:
        raise RuntimeError(f"apify actor call failed: {exc}") from exc

    if run is None:
        raise RuntimeError("apify actor returned no run object")
    status = run.get("status")
    if status == "TIMED-OUT":
        raise TimeoutError(f"apify run timed out after {timeout_s}s for {video_id}")
    if status != "SUCCEEDED":
        raise RuntimeError(f"apify run did not succeed: status={status}")

    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        raise RuntimeError("apify run missing defaultDatasetId")
    items = list(client.dataset(dataset_id).iterate_items())
    if not items:
        raise RuntimeError(f"apify dataset empty for {video_id}")

    item = items[0]
    err = item.get("error")
    if err:
        low = str(err).lower()
        if any(t in low for t in _UNAVAILABLE_TOKENS):
            raise VideoUnavailableError(f"apify: {err}")
        raise RuntimeError(f"apify actor error: {err}")

    status_field = str(item.get("status", "")).lower()
    if status_field and status_field != "success":
        raise RuntimeError(f"apify item non-success status: {item.get('status')}")

    audio_url = item.get("audioFileUrl")
    if not audio_url:
        raise RuntimeError(
            f"apify item missing audioFileUrl; keys={list(item.keys())}"
        )

    ext = (item.get("audioFormat") or format or "mp3").lstrip(".")
    out_path = output_dir / f"{video_id}.{ext}"

    # KVS records are downloadable with ?token=... (or anonymous for public KVS);
    # passing token covers both.
    sep = "&" if "?" in audio_url else "?"
    fetch_url = f"{audio_url}{sep}token={tok}"
    with httpx.stream("GET", fetch_url, timeout=120.0, follow_redirects=True) as resp:
        resp.raise_for_status()
        with open(out_path, "wb") as fh:
            for chunk in resp.iter_bytes(chunk_size=1 << 16):
                if chunk:
                    fh.write(chunk)

    size_bytes = int(item.get("fileSize") or out_path.stat().st_size)
    duration_s = float(item.get("duration") or 0.0)
    bitrate = item.get("audioBitrate")
    try:
        bitrate_i = int(bitrate) if bitrate and str(bitrate).isdigit() else None
    except Exception:
        bitrate_i = None

    return AudioFile(
        video_id=video_id,
        path=out_path,
        duration_s=duration_s,
        size_bytes=size_bytes,
        sample_rate=0,  # actor does not report; Whisper tolerates any rate
        bitrate=bitrate_i,
    )
