# Eric (Competitor Analyst) Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. Load `voyager-scraper-stack`, `azure-cost-cap-setup`, `langgraph-agent-eval-gate`, and `test-driven-development` skills first.

**Goal:** Build Eric — the first of three Voyager agents — who searches YouTube for competitor 川西 (West Sichuan) travel videos, transcribes them, extracts hooks/selling-points/comments, clusters insights, and produces a Strategy Brief that downstream agents (Mike, Dana) will consume. Must pass an eval gate (hook F1 ≥ 0.75, selling-point recall ≥ 0.70, brief LLM-judge ≥ 4/5 on 8/10 runs) before Mike work begins.

**Architecture:** Split execution between a **cloud worker** (Azure Container App) and a **local CLI** (user's Windows machine running GitHub Copilot Claude).

- **Cloud worker (data-only pipeline):** `plan_search → fetch_metadata → download_audio → transcribe → fetch_comments`. Uses YouTube Data API v3, yt-dlp, youtube-comment-downloader, and **Azure OpenAI Whisper** (the only Azure AI service). Writes rows to Postgres with `llm_status='pending'` once Whisper is done.
- **Local CLI (LLM pipeline):** `extract_hooks → extract_selling_points → cluster_insights → write_brief`. Polls Postgres for `llm_status='pending'` rows, uses **GitHub Copilot Claude** via the Copilot CLI, writes `insights` + `briefs` rows back, flips `llm_status` to `done` (or `failed`).

```
         ┌──────────────────── cloud worker (Azure Container Apps) ────────────────────┐
operator │  plan_search → fetch_metadata → download_audio → transcribe → fetch_comments │
  │      │                      (Whisper = aoai-voyager-sexwh5)                         │
  │      └──────────────────┬──────────────────────────────────┬───────────────────────┘
  │                         │ writes videos/transcripts/        │
  │                         │ comments, sets llm_status=pending │
  │                         ▼                                    │
  │                  ┌────────────────┐                          │
  └─────────────────►│  Azure Postgres │◄─────────────────────────┘
                     └────────┬───────┘
                              │ local CLI polls llm_status=pending
                              ▼
         ┌──────────── local CLI (Windows, GitHub Copilot Claude) ────────────┐
         │  extract_hooks → extract_selling_points → cluster_insights → write_brief │
         │         writes insights/briefs, flips llm_status to done                 │
         └──────────────────────────────────────────────────────────────────────────┘
```

No Azure OpenAI GPT-4o. No cloud LLM cost. All generative-LLM calls on operator's machine.

**Graph nodes (9 total):** `plan_search` (cloud; uses heuristic keyword expansion, no LLM), `fetch_metadata` (cloud), `download_audio` (cloud), `transcribe` (cloud/Whisper), `fetch_comments` (cloud), `extract_hooks` (local), `extract_selling_points` (local), `cluster_insights` (local), `write_brief` (local).

**Tech Stack:** Python 3.12, LangGraph, FastAPI, pydantic v2, SQLModel, uv, pytest + VCR.py, Bicep, Alembic, Next.js 14 (minimal).

**Budget watermark for M1:** ≤ $20 of the $150 Azure cap (Postgres + Blob + Whisper + small Container App).

---

## Phase 0 — Prereqs (M0)

### Task 0.1: Initialize monorepo ✅ DONE (2026-04-19)

uv workspace at `~/projects/voyager` with members `apps/api`, `packages/agents`, `packages/tools`, `packages/evals`, `packages/db`. Python 3.12 pinned via `.python-version`. Initial commit: `9b559f3 chore: init voyager monorepo`.

---

### Task 0.2: Provision Azure baseline ✅ DONE (2026-04-19)

Bicep templates in `infra/main.bicep` + `infra/aoai.bicep`, deployed to resource group `rg-voyager` in swedencentral (region chosen because Whisper is only GA in swedencentral/northcentralus/westeurope). 6 resources live:

| Resource | Name | Notes |
|---|---|---|
| Key Vault | `kv-voyager-sexwh5` | RBAC model, soft-delete on |
| Postgres Flex B1ms | `psql-voyager-sexwh5` | database `voyager`, sslmode=require |
| Storage Account | `stvoyagersexwh5b5` | containers: `audio`, `transcripts` (videos-raw/final deferred to M2) |
| Service Bus Basic | `sb-voyager-sexwh5` | queues `ingest`, `transcribe` |
| Container Apps Env | `cae-voyager-sexwh5` | consumption plan, for worker |
| Azure OpenAI | `aoai-voyager-sexwh5` | Whisper-only deployment; no GPT-4o |

Commits: `fbb66cb infra: bicep templates + powershell deploy script for azure baseline`, `9a4bf4b infra: aoai whisper-only (copilot handles llm)`.

---

### Task 0.3: Secrets in Key Vault ✅ DONE (2026-04-19)

All 6 secrets live in `kv-voyager-sexwh5`:

- `pg-conn` — full `postgresql+psycopg://voyageradmin:<pwd>@psql-voyager-sexwh5.postgres.database.azure.com:5432/voyager?sslmode=require`
- `pg-admin-pwd` — raw password (for rotation scripts)
- `blob-conn` — storage account connection string
- `servicebus-conn` — Service Bus root SAS
- `azure-openai-key` — Whisper endpoint key
- `azure-openai-endpoint` — `https://aoai-voyager-sexwh5.openai.azure.com/`

YouTube Data API key + Langfuse keys deferred to Task 0.5.

Local dev: `az keyvault secret show --vault-name kv-voyager-sexwh5 --name <name> --query value -o tsv`.

---

### Task 0.4: Postgres schema + SQLModel + Alembic ✅ DONE (2026-04-19)

**Objective:** Schema for `videos`, `transcripts`, `comments`, `insights`, `briefs` — designed for the cloud-worker / local-CLI split. Every table that requires LLM processing has an `llm_status` column (enum `pending|processing|done|failed`) so the local CLI can poll for work.

**Delivered:**

- `packages/db/pyproject.toml` — SQLModel, Alembic, psycopg[binary], python-dotenv, SQLAlchemy.
- `packages/db/voyager_db/__init__.py` — `get_engine()`, `sync_engine()`, `get_session()` reading `DATABASE_URL` env var.
- `packages/db/voyager_db/models.py` — five SQLModel tables plus `LLMStatus` and `InsightKind` enums.
- `packages/db/alembic.ini`, `packages/db/alembic/env.py`, `packages/db/alembic/script.py.mako`.
- `packages/db/alembic/versions/0001_initial_schema.py` — hand-written initial revision (not autogenerated; Azure Postgres not reachable from sandbox due to firewall).

**Schema highlights:**

| Table | PK | Notable cols | Written by |
|---|---|---|---|
| `videos` | `video_id` (YouTube 11-char ID) | `view_count`, `like_count`, `duration_s`, `lang`, `region`, `source_query`, `llm_status` | cloud worker |
| `transcripts` | `id` | `video_id` FK, `text`, `segments JSONB`, `language`, `model_name` | cloud worker (Whisper) |
| `comments` | `id` | `video_id` FK, `author`, `text`, `like_count` | cloud worker |
| `insights` | `id` | `video_id` FK, `kind` enum{hook,selling_point,cluster}, `payload JSONB`, `model_name` | **local CLI** |
| `briefs` | `id` | `topic`, `video_ids TEXT[]`, `content_md`, `llm_status` | **local CLI** |

The cloud worker sets `videos.llm_status='pending'` after Whisper completes. The local CLI `SELECT ... WHERE llm_status='pending' FOR UPDATE SKIP LOCKED`, claims rows by flipping to `processing`, runs Copilot Claude, inserts into `insights`, then flips to `done`. Same pattern for `briefs.llm_status`.

**Verification performed in sandbox:**

```
uv sync                                                    # clean
uv run python -c "from voyager_db.models import Video, \
  Transcript, Comment, Insight, Brief; print('ok')"        # ok
DATABASE_URL=postgresql+psycopg://u:p@localhost/voyager \
  uv run alembic upgrade head --sql                        # valid SQL dump
```

**To apply on live Azure Postgres (run from Windows — sandbox has no network route):**

```
cd packages\db
$env:DATABASE_URL = (az keyvault secret show --vault-name kv-voyager-sexwh5 --name pg-conn --query value -o tsv)
uv run alembic upgrade head
```

Commit: `db: initial schema (videos/transcripts/comments/insights/briefs) + alembic`.

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

### Task 1.5: Copilot Claude CLI wrapper (local only)

**Objective:** Single `run_copilot(prompt, schema)` helper used by every LLM node. Executes `gh copilot ...` (or `claude-code` / equivalent Copilot CLI) as a subprocess, captures JSON output, validates against a pydantic schema, retries on parse error. No Azure OpenAI client, no fallback — if Copilot is unavailable the local CLI simply exits and the `llm_status='pending'` rows stay pending until next run.

**Files:**
- Create: `packages/agents/_shared/copilot.py`
- Test: `packages/agents/_shared/tests/test_copilot.py`

**Step 1: RED**: test mocks `subprocess.run` returning a JSON fixture, asserts pydantic validation + retry-on-bad-json.

**Step 2: GREEN**: ~40 LoC wrapper; config in `config.toml` (cli path, max retries, timeout).

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

# graph.py — note the pipeline order reflects the cloud/local split:
#   cloud worker:  plan_search → fetch_metadata → download_audio → transcribe → fetch_comments → END(cloud)
#                  (sets videos.llm_status='pending' on exit)
#   local CLI:     extract_hooks → extract_selling_points → cluster_insights → write_brief
#                  (picks up any video with llm_status='pending')
from langgraph.graph import StateGraph, END
from .state import EricState

def build_cloud_graph():
    g = StateGraph(EricState)
    for n in ["plan_search", "fetch_metadata", "download_audio",
              "transcribe", "fetch_comments"]:
        g.add_node(n, lambda s: s)  # placeholder
    g.set_entry_point("plan_search")
    for a, b in [
        ("plan_search","fetch_metadata"),
        ("fetch_metadata","download_audio"),
        ("download_audio","transcribe"),
        ("transcribe","fetch_comments"),
    ]:
        g.add_edge(a, b)
    g.add_edge("fetch_comments", END)
    return g

def build_local_graph():
    g = StateGraph(EricState)
    for n in ["extract_hooks", "extract_selling_points",
              "cluster_insights", "write_brief"]:
        g.add_node(n, lambda s: s)
    g.set_entry_point("extract_hooks")
    for a, b in [
        ("extract_hooks","extract_selling_points"),
        ("extract_selling_points","cluster_insights"),
        ("cluster_insights","write_brief"),
    ]:
        g.add_edge(a, b)
    g.add_edge("write_brief", END)
    return g

cloud_graph = build_cloud_graph()
local_graph = build_local_graph()
```
Run test → PASS.

**Step 3:** Commit.

---

### Tasks 1.7 – 1.15: Implement each node (TDD per node)

Each node gets its own RED-GREEN-REFACTOR + commit. The split between cloud worker and local CLI is explicit:

**Cloud worker nodes (data-only, no LLM):**

**1.7 plan_search** (cloud) — deterministic keyword expansion: takes `campaign` (e.g. "West Sichuan travel, hooks for English-speaking foodies"), applies a small rulebook (`templates/plan_search.yaml`) to produce `query` + YouTube filters (order, region, language). No LLM. Test: 3 fixture campaigns → expected queries (golden strings).

**1.8 fetch_metadata** (cloud) — calls `youtube.client.search_videos` + `get_video_details`, dedupes, sorts by view_count, persists to `videos` table with `llm_status='pending'`. Test: with VCR cassette, 25 videos inserted.

**1.9 download_audio** (cloud) — for top 10 videos, `ytdlp.downloader.download_audio` (parallel asyncio, max 3 concurrent). Test: 10 blob URLs.

**1.10 transcribe** (cloud) — for each audio, `whisper.transcribe` against `aoai-voyager-sexwh5`, save row to `transcripts`. Test: 10 transcripts, each ≥ 50 chars.

**1.11 fetch_comments** (cloud) — top 10 videos × top 100 comments, persist. Test: ≥ 800 rows. After this node the cloud graph terminates; `videos.llm_status` stays `pending`.

**Local CLI nodes (LLM via Copilot Claude):**

**1.12 extract_hooks** (local) — Copilot Claude prompt extracting "hooks" (first-3-second attention grabbers) per transcript. Output schema: `{video_id, hook_text, hook_type: question|claim|visual|stat, timestamp_s, confidence}`. Persist to `insights` (`kind='hook'`). Polls `SELECT video_id FROM videos WHERE llm_status='pending'`. Test: F1 ≥ 0.75 against 5 hand-labeled transcripts (golden in `packages/evals/eric/fixtures/hooks/`).

**1.13 extract_selling_points** (local) — similar; writes `insights` (`kind='selling_point'`). Test: recall ≥ 0.70 vs gold.

**1.14 cluster_insights** (local) — embeds comments locally (sentence-transformers, e.g. `all-MiniLM-L6-v2`, CPU-only; no Azure embeddings), HDBSCAN cluster, labels each cluster with Copilot Claude. Persist to `insights` (`kind='cluster'`). Test: 5-15 themed clusters from a 1000-comment fixture.

**1.15 write_brief** (local) — Copilot Claude prompt takes hooks + selling_points + clusters → markdown Strategy Brief (TL;DR, Top 5 Hooks, Top 5 Selling Points, Audience Pain Points, Recommended Angles for Mike). Insert into `briefs` with `llm_status='done'`; flip source `videos.llm_status='done'`. Test: LLM-judge mean ≥ 4.0 on 10 fixture runs.

For each node, use VCR.py for recording (and for the Copilot nodes, fixture JSON captured from a real CLI run). Commit after each.

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

**Step 2:** Write `run_eval.py` per the skill: loads fixtures, invokes Eric graph (with VCR'd Copilot CLI output for determinism), computes:
- `hook_extraction_f1`
- `selling_point_recall`
- `strategy_brief_quality` (Copilot Claude judge, temperature=0, run 3x median)

**Step 3:** `thresholds.yaml`:
```yaml
agent: eric
required_pass_rate: 0.80
metrics:
  hook_extraction_f1:     { threshold: 0.75, type: deterministic }
  selling_point_recall:   { threshold: 0.70, type: deterministic }
  strategy_brief_quality: { threshold: 4.0,  type: llm_judge, judge: copilot-claude, runs: 3, aggregation: median }
```

Note: judge also runs via Copilot Claude (local). No GPT-4o cost.

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

1. Code lives at `~/projects/voyager/` and is mirrored to private GitHub repo `DannyXXXXU/voyager` (main branch).
2. Langfuse Cloud free tier (saves Container App + ops time).
3. Fixture labeling: Danny labels 5 held-out campaigns; agent labels 15 dev fixtures.
4. **LLM execution is local only.** No Azure OpenAI GPT-4o deployment. Only Azure OpenAI Whisper (`aoai-voyager-sexwh5`) is provisioned. Eric's LangGraph is split into a cloud worker (data-IO) and a local CLI (Copilot Claude) that coordinate through Postgres `llm_status` columns.
