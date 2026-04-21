# Voyager Operations

This document describes how to run the services locally and deploy the cloud
worker. It assumes the Azure resources provisioned in `infra/` already exist:

    kv-voyager-sexwh5   (Key Vault)
    psql-voyager-sexwh5 (Postgres Flexible Server)
    sb-voyager-sexwh5   (Service Bus, queue "ingest")
    aoai-voyager-sexwh5 (Azure OpenAI)
    stvoyagersexwh5b5   (Storage account)
    cae-voyager-sexwh5  (Container Apps environment)

## Python environment

    export PATH="$HOME/.local/bin:$PATH"
    cd ~/projects/voyager
    uv sync --all-packages --all-groups

## Fetching secrets into env vars

The services auto-load from Key Vault when `KEY_VAULT_NAME` is set and env
vars are absent (see `voyager_common.config.get_settings`). You can also
export them manually:

    export KEY_VAULT_NAME=kv-voyager-sexwh5
    az login
    export DATABASE_URL=$(az keyvault secret show --vault-name $KEY_VAULT_NAME --name pg-conn --query value -o tsv)
    export SERVICE_BUS_CONN=$(az keyvault secret show --vault-name $KEY_VAULT_NAME --name servicebus-conn --query value -o tsv)
    export YOUTUBE_API_KEY=$(az keyvault secret show --vault-name $KEY_VAULT_NAME --name youtube-api-key --query value -o tsv)
    export AZURE_OPENAI_ENDPOINT=$(az keyvault secret show --vault-name $KEY_VAULT_NAME --name azure-openai-endpoint --query value -o tsv)
    export AZURE_OPENAI_KEY=$(az keyvault secret show --vault-name $KEY_VAULT_NAME --name azure-openai-key --query value -o tsv)
    export BLOB_CONN=$(az keyvault secret show --vault-name $KEY_VAULT_NAME --name blob-conn --query value -o tsv)
    export APIFY_TOKEN=$(az keyvault secret show --vault-name $KEY_VAULT_NAME --name apify-token --query value -o tsv)

## Audio download backend

Audio downloads use the Apify actor
``lurkapi/youtube-to-mp3-audio-downloader`` by default because YouTube now
challenges yt-dlp from Azure egress IPs with "Sign in to confirm you're not
a bot". The actor runs behind residential proxies and returns a direct MP3
URL that we pull into ``voyager_audio``.

Requires the ``apify-token`` Key Vault secret (also exposed to Settings as
``apify_token`` and env ``APIFY_TOKEN``). If the token is missing the
downloader falls back to local yt-dlp. A yt-dlp fallback is also attempted
per-video if Apify errors out.

Override via env:

    VOYAGER_DOWNLOAD_BACKEND=ytdlp   # force local yt-dlp
    VOYAGER_DOWNLOAD_BACKEND=apify   # force Apify


## Running the API server

    uv run uvicorn voyager_api.main:app --host 0.0.0.0 --port 8000

Open http://localhost:8000/docs for the Swagger UI.

## Running the local CLI

    uv run voyager --help
    uv run voyager eric submit "west sichuan travel" --max-videos 10
    uv run voyager eric status
    uv run voyager eric process --limit 20
    uv run voyager eric brief "west sichuan travel"

## Running the worker locally

    uv run python -m voyager_worker

This connects to live Azure Service Bus and blocks on the `ingest` queue.
Ctrl-C to exit.

## Building the worker container image

    docker build -f apps/worker/Dockerfile -t voyager-worker:latest .

## Deploying the worker to Container Apps

Build and push to an ACR (create one with `az acr create` if needed), then:

    az containerapp create \
      --name ca-voyager-worker \
      --resource-group rg-voyager \
      --environment cae-voyager-sexwh5 \
      --image <acr-name>.azurecr.io/voyager-worker:latest \
      --min-replicas 1 --max-replicas 3 \
      --env-vars KEY_VAULT_NAME=kv-voyager-sexwh5 ENV=prod \
      --system-assigned \
      --registry-server <acr-name>.azurecr.io

Then grant the managed identity access to Key Vault:

    principal=$(az containerapp show -n ca-voyager-worker -g rg-voyager --query identity.principalId -o tsv)
    az keyvault set-policy --name kv-voyager-sexwh5 --object-id $principal --secret-permissions get list

## Smoke test (manual)

    uv run python scripts/smoke_local.py

Enqueues one IngestJob and polls Postgres for up to 5 minutes waiting for
Video rows.
