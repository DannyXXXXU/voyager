"""Tests for voyager_tools.whisper_client (offline, mocked AzureOpenAI)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from voyager_tools.errors import AudioTooLargeError, ConfigError
from voyager_tools import whisper_client


def _fake_response():
    return SimpleNamespace(
        text="hello world",
        language="en",
        duration=12.5,
        segments=[
            {"start": 0.0, "end": 1.0, "text": "hello"},
            {"start": 1.0, "end": 2.0, "text": "world"},
        ],
    )


def _make_small_audio(tmp_path):
    p = tmp_path / "a.m4a"
    p.write_bytes(b"\x00" * 1024)
    return p


async def test_transcribe_parses_response(mocker, tmp_path):
    audio = _make_small_audio(tmp_path)

    client = MagicMock()
    client.audio.transcriptions.create.return_value = _fake_response()
    mock_cls = mocker.patch(
        "voyager_tools.whisper_client.AzureOpenAI", return_value=client
    )

    result = await whisper_client.transcribe(
        audio,
        language="en",
        endpoint="https://fake.openai.azure.com/",
        api_key="k",
        deployment="whisper",
    )

    assert result.text == "hello world"
    assert result.language == "en"
    assert result.duration_s == 12.5
    assert len(result.segments) == 2

    # Client was constructed with Azure endpoint + api_version
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["api_key"] == "k"
    assert "azure.com" in kwargs["azure_endpoint"]
    assert kwargs["api_version"].startswith("2024-")

    # create() was called with model=deployment, response_format=verbose_json
    call_kwargs = client.audio.transcriptions.create.call_args.kwargs
    assert call_kwargs["model"] == "whisper"
    assert call_kwargs["response_format"] == "verbose_json"
    assert call_kwargs["language"] == "en"


async def test_transcribe_raises_too_large(mocker, tmp_path):
    audio = tmp_path / "big.m4a"
    # sparse file: 26MB without real bytes
    with open(audio, "wb") as f:
        f.seek(26 * 1024 * 1024)
        f.write(b"\0")

    mocker.patch("voyager_tools.whisper_client.AzureOpenAI")

    with pytest.raises(AudioTooLargeError):
        await whisper_client.transcribe(
            audio, endpoint="https://fake/", api_key="k"
        )


async def test_transcribe_raises_config_error(mocker, tmp_path, monkeypatch):
    audio = _make_small_audio(tmp_path)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)

    with pytest.raises(ConfigError):
        await whisper_client.transcribe(audio)
