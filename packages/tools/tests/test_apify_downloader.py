"""Unit tests for voyager_tools.apify_downloader (offline, mocked)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from voyager_tools import apify_downloader
from voyager_tools.errors import VideoUnavailableError


def _fake_client(items, status="SUCCEEDED"):
    """Build a mock ApifyClient whose .actor().call() returns a run dict
    and .dataset().iterate_items() yields `items`."""
    client = MagicMock()
    run = {
        "status": status,
        "defaultDatasetId": "ds-1",
        "defaultKeyValueStoreId": "kvs-1",
    }
    client.actor.return_value.call.return_value = run
    client.dataset.return_value.iterate_items.return_value = iter(items)
    return client


def test_happy_path(tmp_path: Path):
    item = {
        "status": "Success",
        "error": None,
        "videoId": "abc123",
        "duration": 42,
        "fileSize": 12345,
        "audioFormat": "mp3",
        "audioFileUrl": "https://api.apify.com/v2/key-value-stores/kvs-1/records/audio-abc123",
    }
    client = _fake_client([item])

    def fake_stream(method, url, timeout, follow_redirects):
        assert "token=" in url
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.iter_bytes.return_value = [b"ID3AUDIOBYTES"]
        cm = MagicMock()
        cm.__enter__.return_value = resp
        cm.__exit__.return_value = False
        return cm

    with patch.object(apify_downloader, "ApifyClient", return_value=client), \
         patch.object(apify_downloader.httpx, "stream", side_effect=fake_stream):
        af = apify_downloader.download_audio_via_apify(
            "abc123", tmp_path, token="TOK"
        )

    assert af.video_id == "abc123"
    assert af.path == tmp_path / "abc123.mp3"
    assert af.path.read_bytes() == b"ID3AUDIOBYTES"
    assert af.duration_s == 42.0
    assert af.size_bytes == 12345


def test_video_unavailable(tmp_path: Path):
    item = {"status": "Error", "error": "Video unavailable: removed by uploader"}
    client = _fake_client([item])
    with patch.object(apify_downloader, "ApifyClient", return_value=client):
        with pytest.raises(VideoUnavailableError):
            apify_downloader.download_audio_via_apify("zzz", tmp_path, token="TOK")


def test_missing_audio_url(tmp_path: Path):
    item = {"status": "Success", "error": None, "videoId": "x", "duration": 1}
    client = _fake_client([item])
    with patch.object(apify_downloader, "ApifyClient", return_value=client):
        with pytest.raises(RuntimeError, match="audioFileUrl"):
            apify_downloader.download_audio_via_apify("x", tmp_path, token="TOK")


def test_run_not_succeeded(tmp_path: Path):
    client = _fake_client([], status="FAILED")
    with patch.object(apify_downloader, "ApifyClient", return_value=client):
        with pytest.raises(RuntimeError, match="did not succeed"):
            apify_downloader.download_audio_via_apify("x", tmp_path, token="TOK")


def test_missing_token(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="Apify token"):
        apify_downloader.download_audio_via_apify("x", tmp_path, token=None)
