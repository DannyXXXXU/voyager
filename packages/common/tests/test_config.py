"""Tests for voyager_common.config."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from voyager_common import config as cfg_mod
from voyager_common.config import SECRET_MAP, Settings, get_settings, load_from_keyvault


ENV_KEYS = [
    "DATABASE_URL",
    "SERVICE_BUS_CONN",
    "BLOB_CONN",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_KEY",
    "YOUTUBE_API_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST",
    "KEY_VAULT_NAME",
    "ENV",
]


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    yield


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://env/db")
    monkeypatch.setenv("SERVICE_BUS_CONN", "Endpoint=sb://env/")
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt-env-key")
    monkeypatch.setenv("ENV", "prod")

    s = Settings()
    assert s.database_url == "postgresql://env/db"
    assert s.service_bus_conn == "Endpoint=sb://env/"
    assert s.youtube_api_key == "yt-env-key"
    assert s.env == "prod"
    assert s.key_vault_name == "kv-voyager-sexwh5"


def test_get_settings_env_only_no_kv_call(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://env/db")
    monkeypatch.setenv("SERVICE_BUS_CONN", "Endpoint=sb://env/")

    called = {"n": 0}

    def _fake_load(name):
        called["n"] += 1
        return Settings()

    monkeypatch.setattr(cfg_mod, "load_from_keyvault", _fake_load)
    s = get_settings()
    assert s.database_url == "postgresql://env/db"
    assert called["n"] == 0


def test_get_settings_falls_back_to_keyvault(monkeypatch):
    # Required fields missing → should call load_from_keyvault
    def _fake_load(name):
        return Settings(
            database_url="postgresql://kv/db",
            service_bus_conn="Endpoint=sb://kv/",
            youtube_api_key="yt-kv-key",
            key_vault_name=name,
        )

    monkeypatch.setattr(cfg_mod, "load_from_keyvault", _fake_load)
    monkeypatch.setenv("KEY_VAULT_NAME", "kv-test")

    s = get_settings()
    assert s.database_url == "postgresql://kv/db"
    assert s.service_bus_conn == "Endpoint=sb://kv/"
    assert s.youtube_api_key == "yt-kv-key"


def test_load_from_keyvault_reads_all_secrets(monkeypatch):
    """Mock SecretClient + DefaultAzureCredential to verify KV mapping."""
    fake_values = {
        "pg-conn": "postgresql://kv/db",
        "blob-conn": "BlobEndpoint=https://kv/",
        "servicebus-conn": "Endpoint=sb://kv/",
        "azure-openai-endpoint": "https://aoai.openai.azure.com",
        "azure-openai-key": "aoai-k",
        "youtube-api-key": "yt-k",
        "langfuse-public-key": "lf-pub",
        "langfuse-secret-key": "lf-sec",
        "langfuse-host": "https://langfuse",
    }

    class FakeSecret:
        def __init__(self, v):
            self.value = v

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        def get_secret(self, name):
            return FakeSecret(fake_values[name])

    import azure.identity as az_identity
    import azure.keyvault.secrets as az_kv

    monkeypatch.setattr(az_identity, "DefaultAzureCredential", lambda *a, **kw: MagicMock())
    monkeypatch.setattr(az_kv, "SecretClient", FakeClient)

    s = load_from_keyvault("kv-test")
    for secret, field in SECRET_MAP.items():
        assert getattr(s, field) == fake_values[secret]
    assert s.key_vault_name == "kv-test"
