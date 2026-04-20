"""Azure OpenAI Whisper transcription client."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from openai import APIStatusError, AzureOpenAI, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from voyager_tools.errors import AudioTooLargeError, ConfigError
from voyager_tools.models import TranscriptResult

_MAX_BYTES = 25 * 1024 * 1024
_API_VERSION = "2024-06-01"


def _extract(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _to_dict(obj: Any) -> dict:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    return {k: getattr(obj, k) for k in dir(obj) if not k.startswith("_")}


@retry(
    retry=retry_if_exception_type((RateLimitError, APIStatusError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
    reraise=True,
)
def _call_create(client: Any, **kwargs: Any) -> Any:
    return client.audio.transcriptions.create(**kwargs)


def _transcribe_sync(
    audio_path: Path,
    language: str | None,
    endpoint: str,
    api_key: str,
    deployment: str,
) -> TranscriptResult:
    client = AzureOpenAI(
        api_key=api_key,
        azure_endpoint=endpoint,
        api_version=_API_VERSION,
    )

    with open(audio_path, "rb") as f:
        kwargs: dict[str, Any] = {
            "file": f,
            "model": deployment,
            "response_format": "verbose_json",
        }
        if language:
            kwargs["language"] = language
        resp = _call_create(client, **kwargs)

    segments_raw = _extract(resp, "segments", []) or []
    segments = [_to_dict(s) for s in segments_raw]

    return TranscriptResult(
        text=_extract(resp, "text", "") or "",
        language=_extract(resp, "language", language or "") or "",
        duration_s=float(_extract(resp, "duration", 0.0) or 0.0),
        segments=segments,
    )


async def transcribe(
    audio_path: Path,
    language: str | None = None,
    endpoint: str | None = None,
    api_key: str | None = None,
    deployment: str = "whisper",
) -> TranscriptResult:
    """Transcribe audio via Azure OpenAI Whisper deployment."""
    audio_path = Path(audio_path)

    ep = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
    key = api_key or os.environ.get("AZURE_OPENAI_KEY")
    if not ep or not key:
        raise ConfigError(
            "Azure OpenAI endpoint and api key are required "
            "(pass endpoint=/api_key= or set AZURE_OPENAI_ENDPOINT/AZURE_OPENAI_KEY)"
        )

    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    size = audio_path.stat().st_size
    if size > _MAX_BYTES:
        raise AudioTooLargeError(
            f"{audio_path.name} is {size} bytes; Whisper limit is {_MAX_BYTES}. "
            "Split the audio into smaller chunks (e.g., with ffmpeg) before retrying."
        )

    return await asyncio.to_thread(
        _transcribe_sync, audio_path, language, ep, key, deployment
    )
