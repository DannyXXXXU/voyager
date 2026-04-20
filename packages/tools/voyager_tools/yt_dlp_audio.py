"""yt-dlp wrapper: download audio-only stream and return AudioFile metadata."""

from __future__ import annotations

from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from voyager_tools.errors import AuthRequiredError, VideoUnavailableError
from voyager_tools.models import AudioFile


_UNAVAILABLE_TOKENS = (
    "video unavailable",
    "has been removed",
    "private video",
    "this video is not available",
    "content isn't available",
)
_AUTH_TOKENS = (
    "sign in to confirm your age",
    "sign in to confirm you",
    "login required",
    "members-only",
    "join this channel",
)


def _classify_download_error(exc: DownloadError) -> Exception:
    msg = str(exc).lower()
    if any(t in msg for t in _AUTH_TOKENS):
        return AuthRequiredError(str(exc))
    if any(t in msg for t in _UNAVAILABLE_TOKENS):
        return VideoUnavailableError(str(exc))
    return exc


def _resolve_output_path(info: dict, fallback: Path) -> Path:
    downloads = info.get("requested_downloads") or []
    if downloads:
        fp = downloads[0].get("filepath")
        if fp:
            return Path(fp)
    fp = info.get("filepath") or info.get("_filename")
    if fp:
        return Path(fp)
    return fallback


def download_audio(
    video_id: str,
    output_dir: Path,
    format: str = "m4a",
) -> AudioFile:
    """Download audio-only stream for the given YouTube video_id.

    Returns AudioFile metadata (path, duration, size, sample_rate, bitrate).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    outtmpl = str(output_dir / f"{video_id}.%(ext)s")
    fallback_path = output_dir / f"{video_id}.{format}"
    url = f"https://www.youtube.com/watch?v={video_id}"

    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "writeinfojson": False,
        "extract_flat": False,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except DownloadError as exc:
        raise _classify_download_error(exc) from exc

    if info is None:
        raise VideoUnavailableError(f"yt-dlp returned no info for {video_id}")

    path = _resolve_output_path(info, fallback_path)

    size_bytes = (
        info.get("filesize")
        or info.get("filesize_approx")
        or (path.stat().st_size if path.exists() else 0)
    )
    duration_s = float(info.get("duration") or 0.0)
    sample_rate = int(info.get("asr") or 0)
    abr = info.get("abr")
    bitrate = int(abr) if abr is not None else None

    return AudioFile(
        video_id=video_id,
        path=path,
        duration_s=duration_s,
        size_bytes=int(size_bytes),
        sample_rate=sample_rate,
        bitrate=bitrate,
    )
