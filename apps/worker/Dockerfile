FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy

# ffmpeg is required by yt-dlp and whisper audio preprocessing.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && ln -s /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app

# Copy workspace manifests first for layer caching
COPY pyproject.toml uv.lock ./
COPY packages/common/pyproject.toml packages/common/pyproject.toml
COPY packages/db/pyproject.toml packages/db/pyproject.toml
COPY packages/tools/pyproject.toml packages/tools/pyproject.toml
COPY packages/agents/pyproject.toml packages/agents/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml

# Full source
COPY packages packages
COPY apps/worker apps/worker

RUN uv sync --package voyager-worker --frozen --no-dev || uv sync --package voyager-worker --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

CMD ["python", "-m", "voyager_worker"]
