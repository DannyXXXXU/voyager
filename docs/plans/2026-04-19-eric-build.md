# Eric (Competitor Analyst) Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. Load `voyager-scraper-stack`, `azure-cost-cap-setup`, `langgraph-agent-eval-gate`, and `test-driven-development` skills first.

**Goal:** Build Eric — the first of three Voyager agents — who searches YouTube for competitor 川西 (West Sichuan) travel videos, transcribes them, extracts hooks/selling-points/comments, clusters insights, and produces a Strategy Brief that downstream agents (Mike, Dana) will consume. Must pass an eval gate (hook F1 ≥ 0.75, selling-point recall ≥ 0.70, brief LLM-judge ≥ 4/5 on 8/10 runs) before Mike work begins.

**Architecture:** LangGraph StateGraph. Nodes: `plan_search → fetch_metadata → download_audio → transcribe → extract_hooks → extract_selling_points → fetch_comments → cluster_insights → write_brief`. State persisted in Azure Postgres. Tools: YouTube Data API v3, yt-dlp, youtube-comment-downloader, Azure OpenAI Whisper, Claude (via Copilot) for extraction. Traces to self-hosted Langfuse.

**Tech Stack:** Python 3.12, LangGraph, FastAPI, pydantic v2, SQLModel, uv (package mgr), pytest + VCR.py, Bicep for Azure infra, Next.js 14 (UI tab only — minimal in M1).

**Budget watermark for M1:** ≤ $20 of the $150 Azure cap (Postgres + Blob + Whisper + small Container App).

---

## Phase 0 — Prereqs (M0)

### Task 0.1: Initialize monorepo

**Objective:** Create the Voyager monorepo skeleton.

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.python-version`, `README.md`
- Create dirs: `apps/api/`, `apps/web/`, `packages/agents/`, `packages/tools/`, `packages/evals/`, `packages/db/`, `infra/`, `docs/plans/`

**Step 1:** `cd ~/projects/voyager && git init && echo "3.12" > .python-version`

**Step 2:** Create `pyproject.toml` with workspace setup using uv:
```toml
[project]
name = "voyager"
version = "0.1.0"
requires-python = ">=3.12"

[tool.uv.workspace]
members = ["apps/api", "packages/*"]
```

**Step 3:** `.gitignore` — standard Python + Node + .env + .venv + /storage + /langfuse-data.

**Step 4:** Commit.
```
git add -A && git commit -m "chore: init voyager monorepo"
```

**Verification:** `uv sync` succeeds (empty workspace).

---

### Task 0.2: Provision Azure baseline

**Objective:** Create the resource group + cost cap + Key Vault + Postgres + Blob.

Follow `azure-cost-cap-setup` skill. Specifically:

**Step 1:** `az group create -n rg-voyager-prod -l japaneast`

**Step 2:** Set the $150 budget with alerts at 50/80/95% actual + 100% forecasted (exact `az consumption budget create` command in the skill).

**Step 3:** Write `infra/main.bicep` provisioning: Key Vault, Postgres Flex B1ms, Storage Account with 4 containers (`videos-raw`, `audio`, `transcripts`, `videos-final`), Service Bus Basic with queues `ingest`/`transcribe`, Log Analytics, Container Apps Environment.

**Step 4:** `az deployment group create -g rg-voyager-prod -f infra/main.bicep`

**Step 5:** Commit infra.

**Verification:**
- `az consumption budget list -g rg-voyager-prod` shows budget.
- `az postgres flexible-server show -n psql-voyager -g rg-voyager-prod` returns Ready.
- Test alert: portal shows pending notification.

---

### Task 0.3: Secrets in Key Vault

**Objective:** Store all credentials centrally.

**Step 1:** Get a YouTube Data API v3 key from Google Cloud Console (new project: voyager-prod).

**Step 2:** Store in Key Vault:
```bash
az keyvault secret set --vault-name kv-voyager-prod --name youtube-api-key --value "<key>"
az keyvault secret set --vault-name kv-voyager-prod --name pg-conn --value "<connection-string>"
az keyvault secret set --vault-name kv-voyager-prod --name azure-openai-key --value "<key>"
az keyvault secret set --vault-name kv-voyager-prod --name blob-conn --value "<connection-string>"
```

**Step 3:** Local dev: `.env.example` lists required vars (no values). Devs run `scripts/pull-secrets.sh` which uses `az keyvault secret show` to populate `.env`.

**Verification:** `uv run python -c "from packages.db.secrets import get_secret; print(get_secret('youtube-api-key')[:6])"` prints first 6 chars.

---

### Task 0.4: Postgres schema + Alembic

**Objective:** Schema for videos, transcripts, comments, insights, briefs.

**Files:**
- Create: `packages/db/models.py`, `packages/db/__init__.py`, `packages/db/migrations/`, `alembic.ini`

**Step 1: RED** — write `packages/db/tests/test_models.py`:
```python
from packages.db.models import Video, Transcript, Comment, Insight, Brief

def test_video_required_fields():
    v = Video(platform="youtube", external_id="abc", url="https://...", title="t")
    assert v.platform == "youtube"
```
Run `pytest packages/db/tests/test_models.py` → FAIL (module not found).

**Step 2: GREEN** — write SQLModel definitions:
```python
# packages/db/models.py
from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional

class Video(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    platform: str
    external_id: str = Field(index=True)
    url: str
    title: str
    channel: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    duration_s: Optional[int] = None
    published_at: Optional[datetime] = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)

class Transcript(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id")
    text: str
    language: str
    model: str

class Comment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id")
    external_id: str
    text: str
    like_count: int = 0
    parent_id: Optional[str] = None

class Insight(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id")
    kind: str  # "hook" | "selling_point" | "comment_theme"
    text: str
    confidence: float

class Brief(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    campaign: str
    markdown: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    eric_run_id: str
```
Run pytest → PASS.

**Step 3:** `alembic init packages/db/migrations`, edit `env.py` to import models, generate first migration, apply.

**Step 4:** Commit.

**Verification:** `psql $PG_CONN -c "\dt"` shows 5 tables.

---

### Task 0.5: Langfuse Cloud (free tier)

**Objective:** Get traces + datasets infrastructure with zero infra cost.

**Step 1:** Sign up at https://cloud.langfuse.com (free tier: 50k observations/month, plenty for MVP).

**Step 2:** Create project "voyager-eric". Copy public + secret keys.

**Step 3:** Store `LANGFUSE_HOST=https://cloud.langfuse.com`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` in Key Vault.

**Verification:** Run `uv run python -c "from langfuse import Langfuse; Langfuse().trace(name='ping')"` and see it in the cloud dashboard.

---

## Phase 1 — Eric (M1)

### Task 1.1: YouTube Data API client

**Objective:** Typed wrapper for video search + metadata fetch.

**Files:**
- Create: `packages/tools/youtube/__init__.py`, `packages/tools/youtube/client.py`
- Test: `packages/tools/youtube/tests/test_client.py`

**Step 1: RED** — test:
```python
import vcr
from packages.tools.youtube.client import search_videos

@vcr.use_cassette("packages/tools/youtube/tests/cassettes/search_chuanxi.yaml")
def test_search_videos_returns_typed_results():
    results = search_videos("West Sichuan travel", max_results=5)
    assert len(results) == 5
    assert all(r.video_id and r.title and r.channel for r in results)
```
Run → FAIL.

**Step 2: GREEN**:
```python
# packages/tools/youtube/client.py
from googleapiclient.discovery import build
from pydantic import BaseModel
from packages.db.secrets import get_secret

class SearchResult(BaseModel):
    video_id: str
    title: str
    channel: str
    published_at: str
    description: str

def _client():
    return build("youtube", "v3", developerKey=get_secret("youtube-api-key"))

def search_videos(query: str, max_results: int = 25, order: str = "viewCount") -> list[SearchResult]:
    resp = _client().search().list(
        q=query, part="snippet", type="video",
        maxResults=max_results, order=order,
    ).execute()
    return [
        SearchResult(
            video_id=item["id"]["videoId"],
            title=item["snippet"]["title"],
            channel=item["snippet"]["channelTitle"],
            published_at=item["snippet"]["publishedAt"],
            description=item["snippet"]["description"],
        )
        for item in resp["items"]
    ]
```
Run with real key once → cassette recorded → re-run test → PASS.

**Step 3:** Add `get_video_details(video_ids: list[str])` method (uses `videos().list`), with its own test + cassette.

**Step 4:** Commit.

---

### Task 1.2: yt-dlp audio downloader

**Objective:** Download mp3 audio for any YouTube URL → upload to Azure Blob.

**Files:**
- Create: `packages/tools/ytdlp/downloader.py`
- Test: `packages/tools/ytdlp/tests/test_downloader.py`

**Step 1: RED**:
```python
def test_download_audio_uploads_to_blob(tmp_path, fake_blob):
    blob_url = download_audio("https://youtu.be/dQw4w9WgXcQ", workdir=tmp_path)
    assert blob_url.startswith("https://stvoyager")
    assert blob_url.endswith(".mp3")
```
Run → FAIL.

**Step 2: GREEN**:
```python
# packages/tools/ytdlp/downloader.py
import yt_dlp
from pathlib import Path
from packages.tools.blob import upload_file

def download_audio(url: str, workdir: Path) -> str:
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(workdir / "%(id)s.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=True)
    mp3 = workdir / f"{info['id']}.mp3"
    return upload_file(mp3, container="audio", blob_name=mp3.name)
```
Implement `packages/tools/blob.py` with `upload_file(path, container, blob_name) -> url` using `azure-storage-blob`.

**Step 3:** Run integration test against one short Creative Commons video → PASS.

**Step 4:** Pin `yt-dlp` version in `pyproject.toml` (per skill pitfall #1).

**Step 5:** Commit.

---

### Task 1.3: Azure OpenAI Whisper transcription

**Objective:** mp3 → transcript text + language.

**Files:**
- Create: `packages/tools/whisper/transcribe.py`
- Test: `packages/tools/whisper/tests/test_transcribe.py`

**Step 1: RED**:
```python
def test_transcribe_returns_text_and_language(short_mp3_blob_url):
    result = transcribe(short_mp3_blob_url)
    assert len(result.text) > 20
    assert result.language in {"en", "zh"}
```

**Step 2: GREEN**: use `openai` SDK pointed at Azure OpenAI Whisper deployment. Stream blob into the SDK without re-downloading to disk where possible. Return pydantic `TranscriptResult(text, language, duration_s)`.

**Step 3:** Commit.

**Verification:** Transcribe a known 30s clip → text contains expected phrase.

---

### Task 1.4: youtube-comment-downloader wrapper

**Objective:** Pull deep comment trees for a video ID.

**Files:**
- Create: `packages/tools/youtube/comments.py`
- Test: `packages/tools/youtube/tests/test_comments.py`

**Step 1: RED**: test asserts ≥ 50 comments for a known viral video, with replies present.

**Step 2: GREEN**:
```python
from youtube_comment_downloader import YoutubeCommentDownloader, SORT_BY_POPULAR

def fetch_comments(video_id: str, max_comments: int = 200) -> list[dict]:
    d = YoutubeCommentDownloader()
    out = []
    for c in d.get_comments(video_id, sort_by=SORT_BY_POPULAR):
        out.append({
            "id": c["cid"],
            "text": c["text"],
            "like_count": int(c.get("votes", "0") or 0),
            "parent_id": c.get("parent"),
        })
        if len(out) >= max_comments:
            break
    return out
```

**Step 3:** Throttle (sleep 0.5s between videos in caller). Commit.

---

### Task 1.5: LLM router (Copilot Claude + Azure OpenAI fallback)

**Objective:** Single `get_llm(task)` function used by every Eric node.

**Files:**
- Create: `packages/agents/_shared/llm.py`
- Test: `packages/agents/_shared/tests/test_llm.py`

**Step 1: RED**: assert `get_llm("extract")` returns a `BaseChatModel` instance, and that the routing config is read from `config.toml`, not from environment secrets directly.

**Step 2: GREEN**: small selector returning `ChatAnthropic` (via Copilot proxy URL) when configured, else `AzureChatOpenAI`. For `task="bulk_classify"` always return `gpt-4o-mini`.

**Step 3:** Commit.

---

### Task 1.6: Eric state schema + graph skeleton

**Files:**
- Create: `packages/agents/eric/state.py`, `packages/agents/eric/graph.py`, `packages/agents/eric/__init__.py`
- Test: `packages/agents/eric/tests/test_graph_compiles.py`

**Step 1: RED**: test imports `eric_graph` and asserts `.compile()` returns a runnable.

**Step 2: GREEN**:
```python
# state.py
from typing import TypedDict, Annotated
import operator

class EricState(TypedDict):
    campaign: str
    query: str
    search_results: list[dict]
    videos: list[dict]
    transcripts: dict[str, str]   # video_id -> text
    comments: dict[str, list[dict]]
    hooks: Annotated[list[dict], operator.add]
    selling_points: Annotated[list[dict], operator.add]
    comment_themes: list[dict]
    brief_md: str

# graph.py
from langgraph.graph import StateGraph, END
from .state import EricState

def build_graph():
    g = StateGraph(EricState)
    g.add_node("plan_search", lambda s: s)        # placeholder
    g.add_node("fetch_metadata", lambda s: s)
    g.add_node("download_audio", lambda s: s)
    g.add_node("transcribe", lambda s: s)
    g.add_node("extract_hooks", lambda s: s)
    g.add_node("extract_selling_points", lambda s: s)
    g.add_node("fetch_comments", lambda s: s)
    g.add_node("cluster_insights", lambda s: s)
    g.add_node("write_brief", lambda s: s)
    g.set_entry_point("plan_search")
    for a, b in [
        ("plan_search","fetch_metadata"),
        ("fetch_metadata","download_audio"),
        ("download_audio","transcribe"),
        ("transcribe","extract_hooks"),
        ("extract_hooks","extract_selling_points"),
        ("extract_selling_points","fetch_comments"),
        ("fetch_comments","cluster_insights"),
        ("cluster_insights","write_brief"),
    ]:
        g.add_edge(a, b)
    g.add_edge("write_brief", END)
    return g

eric_graph = build_graph()
```
Run test → PASS.

**Step 3:** Commit.

---

### Tasks 1.7 – 1.14: Implement each node (TDD per node)

Each node gets its own RED-GREEN-REFACTOR + commit. Pattern:

**1.7 plan_search** — Claude prompt that turns `campaign` (e.g. "West Sichuan travel, hooks for English-speaking foodies") into `query` + filters. Test: 3 fixture campaigns produce sensible queries (LLM-judge ≥ 4/5).

**1.8 fetch_metadata** — calls `youtube.client.search_videos` + `get_video_details`, dedupes, sorts by view_count, persists to `videos` table. Test: with VCR cassette, state has 25 videos, all with view_count.

**1.9 download_audio** — for top 10 videos, call `ytdlp.downloader.download_audio` (parallel with `asyncio.gather`, max 3 concurrent). Test: state.audio_blob_urls has 10 entries.

**1.10 transcribe** — for each audio, `whisper.transcribe`, save to `transcripts` table. Test: transcripts dict has 10 entries, each ≥ 50 chars.

**1.11 extract_hooks** — Claude prompt extracting "hooks" (first-3-second attention grabbers) per transcript. Output schema: `{video_id, hook_text, hook_type: question|claim|visual|stat, timestamp_s}`. Persist to `insights`. Test: F1 ≥ 0.75 against 5 hand-labeled transcripts (golden in `packages/evals/eric/fixtures/hooks/`).

**1.12 extract_selling_points** — similar, "selling_points" = differentiated value props ("hidden monastery", "no tourists", etc). Test: recall ≥ 0.70 vs gold.

**1.13 fetch_comments** — top 10 videos × top 100 comments, persist. Use `youtube.comments.fetch_comments`. Test: ≥ 800 total comments stored.

**1.14 cluster_insights** — embed comments with `text-embedding-3-small`, HDBSCAN cluster, label each cluster with Claude. Test: produces 5-15 themed clusters from 1000 comments fixture.

**1.15 write_brief** — Claude prompt taking hooks + selling_points + comment_themes → markdown Strategy Brief with sections: TL;DR, Top 5 Hooks, Top 5 Selling Points, Audience Pain Points, Recommended Angles for Mike. Persist to `briefs` table. Test: LLM-judge mean ≥ 4.0 on 10 fixture runs.

For each node, use VCR.py for LLM call recording. Commit after each.

---

### Task 1.16: FastAPI router

**Files:**
- Create: `apps/api/routers/eric.py`, `apps/api/main.py`

**Step 1: RED**: test `POST /eric/run {campaign:"..."}` returns 202 + `run_id`.

**Step 2: GREEN**: route enqueues onto Service Bus `ingest` queue. A worker (later task) drains it.

**Step 3:** Add `GET /eric/runs/{run_id}` returning state from Postgres.

**Step 4:** Add `GET /eric/runs/{run_id}/stream` SSE endpoint emitting node-completion events from Langfuse callback.

---

### Task 1.17: Worker process

**Files:**
- Create: `apps/api/worker.py`

Drains Service Bus, hydrates state, runs `eric_graph.invoke(initial_state)`, persists final state. Deploy as a separate Container App with `minReplicas: 0`, `maxReplicas: 3`.

Test: end-to-end test posts a campaign, polls until status=done, asserts brief exists.

---

### Task 1.18: Web UI — "Discovered Videos" tab

**Files:**
- Create: `apps/web/app/eric/page.tsx`, `apps/web/components/VideoTable.tsx`, `apps/web/components/BriefViewer.tsx`

Minimal: campaign input, "Run Eric" button, live SSE log of node completion, table of discovered videos with hook/sellingpoint chips, full brief markdown rendered with `react-markdown`.

Tests: component snapshot tests only. Visual QA via `dogfood` skill.

---

### Task 1.19: Eric eval harness

**Objective:** The gate.

Follow `langgraph-agent-eval-gate` skill exactly.

**Files:**
- Create: `packages/evals/eric/run_eval.py`, `packages/evals/eric/thresholds.yaml`, `packages/evals/eric/fixtures/` (20 hand-labeled videos), `packages/evals/eric/judges/brief_rubric.md`

**Step 1:** Hand-label 20 川西 travel videos in a Google Sheet:
- 5 used for hook extraction gold (timestamps + hook text)
- 5 for selling-point gold (lists)
- 10 full campaigns for end-to-end brief evaluation (5 dev, 5 held-out)

Export to `fixtures/{hooks,selling_points,campaigns}.yaml`.

**Step 2:** Write `run_eval.py` per the skill: loads fixtures, invokes Eric graph (with VCR'd downstream LLM calls for determinism), computes:
- `hook_extraction_f1`
- `selling_point_recall`
- `strategy_brief_quality` (gpt-4o judge, temperature=0, run 3x median)

**Step 3:** `thresholds.yaml`:
```yaml
agent: eric
required_pass_rate: 0.80
metrics:
  hook_extraction_f1: { threshold: 0.75, type: deterministic }
  selling_point_recall: { threshold: 0.70, type: deterministic }
  strategy_brief_quality: { threshold: 4.0, type: llm_judge, judge_model: gpt-4o, runs: 3, aggregation: median }
```

**Step 4:** Wire into `.github/workflows/agent-gate.yml` running on every PR touching `packages/agents/eric/**` or `packages/evals/eric/**`.

**Step 5:** Run locally. If any threshold fails → iterate prompts in `packages/agents/eric/prompts/` (using only the 5 dev held-in fixtures, never held-out). Commit each prompt iteration.

**Step 6:** When green, push to main, gate runs in CI.

**Verification:** CI run shows all metrics green; Langfuse dataset run tagged with merge-commit SHA.

---

## Exit criteria for M1 (Eric promoted)

- [ ] All 0.x and 1.x tasks committed.
- [ ] Eric eval gate green on `main`.
- [ ] Manual eyeball of 3 random fixture briefs by user → "looks useful for Mike".
- [ ] Azure cost dashboard shows month-to-date < $20.
- [ ] Langfuse contains ≥ 30 successful end-to-end runs.

Once all checked → merge `release/eric-v1` tag → start Mike plan (`docs/plans/YYYY-MM-DD-mike-build.md`).

---

## Estimated effort

- Phase 0: ~1 day
- Tasks 1.1 – 1.6: ~1 day
- Tasks 1.7 – 1.15 (9 nodes, TDD each): ~3-4 days
- Tasks 1.16 – 1.18 (API + worker + UI): ~1.5 days
- Task 1.19 (eval gate + labeling): ~1.5 days (the labeling is the long pole)

**Total: ~8-9 working days for one developer.** Halve with `subagent-driven-development` running tasks in parallel where independent (1.1/1.2/1.3/1.4 are independent; 1.7-1.15 are sequential).

---

## Confirmed decisions (2026-04-19)

1. No GitHub repo — code lives in Linux sandbox at `~/projects/voyager/`.
2. Langfuse Cloud free tier (saves Container App + ops time).
3. Fixture labeling: Danny labels 5 held-out campaigns; agent labels 15 dev fixtures.
