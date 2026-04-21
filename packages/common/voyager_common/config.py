"""Settings + Azure Key Vault loader.

Source precedence:
    1. Environment variables (pydantic-settings default).
    2. If KEY_VAULT_NAME is set AND required secrets are missing, fall back
       to Key Vault via DefaultAzureCredential.

Secret-name → settings-field map (Key Vault kebab-case → python snake_case):
    pg-conn                 -> database_url
    blob-conn               -> blob_conn
    servicebus-conn         -> service_bus_conn
    azure-openai-endpoint   -> azure_openai_endpoint
    azure-openai-key        -> azure_openai_key
    youtube-api-key         -> youtube_api_key
    langfuse-public-key     -> langfuse_public_key
    langfuse-secret-key     -> langfuse_secret_key
    langfuse-host           -> langfuse_host
    apify-token             -> apify_token
"""
from __future__ import annotations

import logging
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


# Secret name (KV) → Settings field
SECRET_MAP: dict[str, str] = {
    "pg-conn": "database_url",
    "blob-conn": "blob_conn",
    "servicebus-conn": "service_bus_conn",
    "azure-openai-endpoint": "azure_openai_endpoint",
    "azure-openai-key": "azure_openai_key",
    "youtube-api-key": "youtube_api_key",
    "langfuse-public-key": "langfuse_public_key",
    "langfuse-secret-key": "langfuse_secret_key",
    "langfuse-host": "langfuse_host",
    "apify-token": "apify_token",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        case_sensitive=False,
        extra="ignore",
    )

    # Core infra
    database_url: Optional[str] = None
    service_bus_conn: Optional[str] = None
    blob_conn: Optional[str] = None

    # Azure OpenAI
    azure_openai_endpoint: Optional[str] = None
    azure_openai_key: Optional[str] = None

    # YouTube
    youtube_api_key: Optional[str] = None

    # Langfuse (all optional)
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None
    langfuse_host: Optional[str] = None

    # Apify (audio download fallback that bypasses YouTube bot-check)
    apify_token: Optional[str] = None

    # Runtime meta
    key_vault_name: str = "kv-voyager-sexwh5"
    env: str = "dev"


REQUIRED_FIELDS = ("database_url", "service_bus_conn")


def load_from_keyvault(kv_name: str) -> Settings:
    """Pull 9 secrets from Key Vault and build Settings.

    Uses azure-identity DefaultAzureCredential; callers should be logged in
    via `az login` or running inside a managed identity.
    """
    # Imports are local so tests can stub these modules without needing the
    # packages installed or the network configured.
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    vault_url = f"https://{kv_name}.vault.azure.net"
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=vault_url, credential=credential)

    data: dict[str, str] = {"key_vault_name": kv_name}
    for secret_name, field in SECRET_MAP.items():
        try:
            secret = client.get_secret(secret_name)
            if secret.value is not None:
                data[field] = secret.value
        except Exception as exc:  # noqa: BLE001
            logger.warning("key vault: failed to read %s: %s", secret_name, exc)

    return Settings(**data)


def get_settings() -> Settings:
    """Return Settings, falling back to Key Vault if required fields missing.

    If required secrets are already in env vars, we never hit Key Vault.
    """
    s = Settings()
    missing = [f for f in REQUIRED_FIELDS if getattr(s, f) in (None, "")]
    if not missing:
        return s

    import os

    kv_name = os.environ.get("KEY_VAULT_NAME") or s.key_vault_name
    if not kv_name:
        return s

    logger.info(
        "settings: missing fields %s; loading from key vault %s", missing, kv_name
    )
    kv_settings = load_from_keyvault(kv_name)

    merged: dict[str, object] = {}
    for field in Settings.model_fields:
        env_val = getattr(s, field)
        kv_val = getattr(kv_settings, field)
        merged[field] = env_val if env_val not in (None, "") else kv_val
    return Settings(**merged)
