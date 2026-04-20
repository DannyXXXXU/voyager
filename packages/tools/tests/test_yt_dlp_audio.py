"""Tests for voyager_tools.yt_dlp_audio (offline, mocked yt_dlp)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from yt_dlp.utils import DownloadError

from voyager_tools.errors import AuthRequiredError, VideoUnavailableError
from voyager_tools.yt_dlp_audio import download_audio


def _fake_info_dict(video_id: str, path: Path) -> dict:
    return {
        "id": video_id,
        "duration": 123.4,
        "filesize": 1024 * 500,
        "asr": 44100,
        "abr": 128,
        "ext": "m4a",
        "requested_downloads": [{"filepath": str(path)}],
    }


def test_download_audio_returns_audiofile(mocker, tmp_path):
    video_id = "abc123"
    expected_path = tmp_path / f"{video_id}.m4a"
    expected_path.write_bytes(b"fake audio")

    info = _fake_info_dict(video_id, expected_path)

    ydl_instance = MagicMock()
    ydl_instance.extract_info.return_value = info
    ydl_instance.__enter__ = MagicMock(return_value=ydl_instance)
    ydl_instance.__exit__ = MagicMock(return_value=False)

    mocker.patch("voyager_tools.yt_dlp_audio.YoutubeDL", return_value=ydl_instance)

    result = download_audio(video_id, tmp_path)

    assert result.video_id == video_id
    assert result.path == expected_path
    assert result.duration_s == 123.4
    assert result.sample_rate == 44100
    assert result.bitrate == 128
    assert result.size_bytes > 0


def test_download_audio_raises_video_unavailable(mocker, tmp_path):
    ydl_instance = MagicMock()
    ydl_instance.extract_info.side_effect = DownloadError("Video unavailable")
    ydl_instance.__enter__ = MagicMock(return_value=ydl_instance)
    ydl_instance.__exit__ = MagicMock(return_value=False)
    mocker.patch("voyager_tools.yt_dlp_audio.YoutubeDL", return_value=ydl_instance)

    with pytest.raises(VideoUnavailableError):
        download_audio("xxx", tmp_path)


def test_download_audio_raises_auth_required(mocker, tmp_path):
    ydl_instance = MagicMock()
    ydl_instance.extract_info.side_effect = DownloadError(
        "Sign in to confirm your age"
    )
    ydl_instance.__enter__ = MagicMock(return_value=ydl_instance)
    ydl_instance.__exit__ = MagicMock(return_value=False)
    mocker.patch("voyager_tools.yt_dlp_audio.YoutubeDL", return_value=ydl_instance)

    with pytest.raises(AuthRequiredError):
        download_audio("xxx", tmp_path)
