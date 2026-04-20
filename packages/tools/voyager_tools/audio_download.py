"""Backend dispatcher for audio downloads.

Default backend is "apify" when APIFY_TOKEN is available (or explicitly passed);
otherwise falls back to "ytdlp". Callers can force via env
``VOYAGER_DOWNLOAD_BACKEND`` or kwarg ``backend=``.
"""
from __future__ import annotations

import os
from pathlib import Path

from voyager_tools.models import AudioFile


def _pick_default(token: str | None) -> str:
    env = os.environ.get("VOYAGER_DOWNLOAD_BACKEND")
    if env:
        return env.lower()
    if token or os.environ.get("APIFY_TOKEN"):
        return "apify"
    return "ytdlp"


def download_audio(
    video_id: str,
    output_dir: Path,
    format: str = "m4a",
    backend: str | None = None,
    token: str | None = None,
) -> AudioFile:
    """Dispatch to the configured audio-download backend.

    backend: "apify" | "ytdlp" | None (auto)
    token:   Apify API token (only used by apify backend).
    """
    be = (backend or _pick_default(token)).lower()
    if be == "apify":
        from voyager_tools import apify_downloader

        return apify_downloader.download_audio_via_apify(
            video_id=video_id,
            output_dir=Path(output_dir),
            token=token,
            format=format if format != "m4a" else "mp3",
        )
    if be == "ytdlp":
        from voyager_tools import yt_dlp_audio

        return yt_dlp_audio.download_audio(
            video_id=video_id, output_dir=Path(output_dir), format=format
        )
    raise ValueError(f"unknown download backend: {be!r}")
