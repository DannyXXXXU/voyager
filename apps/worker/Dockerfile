# syntax=docker/dockerfile:1.7
# Multi-stage build for voyager-worker (uv workspace monorepo).
# Build context must be the repo root so workspace members are visible.

FROM ghcr.io/astral-sh/uv:0.5.11-python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /src

# Copy workspace manifests first for layer caching.
COPY pyproject.toml uv.lock ./
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/cli/pyproject.toml apps/cli/pyproject.toml
COPY packages/agents/pyproject.toml packages/agents/pyproject.toml
COPY packages/tools/pyproject.toml packages/tools/pyproject.toml
COPY packages/evals/pyproject.toml packages/evals/pyproject.toml
COPY packages/db/pyproject.toml packages/db/pyproject.toml
COPY packages/common/pyproject.toml packages/common/pyproject.toml

# Copy source (needed because workspace members are editable installs).
COPY apps apps
COPY packages packages

# Install only the worker package + its workspace deps, no dev group.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package voyager-worker

FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# ffmpeg needed for Whisper audio preprocessing.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /src /app

# Non-root user.
RUN groupadd -r app && useradd -r -g app -d /app app \
 && chown -R app:app /app
USER app

CMD ["python", "-m", "voyager_worker"]
