# Voyager — AI Agent-Driven China Travel Growth Platform

**Status:** Draft v0.1
**Owner:** Danny
**Last updated:** 2026-04-19

---

## 1. Product Overview

### 1.1 Mission
Grow overseas awareness of China travel destinations (e.g. 川西) by producing
and distributing short-form travel videos at scale, driven by a team of three
cooperating AI agents. Initial platform focus: YouTube (Shorts + long-form),
followed by TikTok and Instagram Reels.

### 1.2 Product Codename
**Voyager** — a multi-agent studio for overseas travel growth.

### 1.3 Users
- **Phase 1 (internal):** operator/marketer running the China-travel campaign.
- **Phase 2 (productized):** any brand/creator doing overseas short-video
  growth (travel, e-commerce, SaaS demos). The agents are generic; the
  knowledge base (voice.md / product.md / icp.md) is per-tenant.

### 1.4 Success Metrics (North Star)
- **Primary:** average watch-time per video on target platform.
- **Secondary:** video CTR, view count per impression, comment sentiment,
  cost per 1k qualified views.
- **System:** videos shipped per week, % of videos that clear the eval
  threshold without human edit, iteration cycle time.

---

## 2. The Three Agents

All three agents share a common runtime (see §4). Each has: a role prompt,
a toolbelt, a memory namespace, and an eval harness that must pass before
the agent is declared "production".

### 2.1 Eric — Competitive Research Analyst
**Role:** continuously mine overseas travel short-video space and produce
strategy briefs.

**Inputs:** target destination (川西), target audience ICP, language/region,
source platforms (YouTube first, then TikTok/IG).

**Core tasks:**
1. Discover top-performing China-travel videos (then broader overseas travel).
2. Rank by engagement signals (views, likes/views, comments/views,
   view-velocity, shelf-life).
3. Download audio → Whisper transcription → structure into
   `{hook, narrative_arc, selling_points, CTA}`.
4. Mine top comments to extract audience concerns / desires / objections.
5. Cluster findings and emit a **Strategy Brief** (markdown) with:
   - Top 10 hook patterns (first 3s).
   - Top selling points ranked by frequency × engagement.
   - Audience concerns from comments.
   - Recommended angles for Mike (next step).
6. Store every analyzed video in the **Video Library** with analysis.

**Output artifact:** `strategy_brief_{date}.md` + structured rows in DB.

**Eval (must pass before Mike starts):** see §7.1.

### 2.2 Mike — Editor / Video Producer
**Role:** given Eric's strategy brief, source raw footage from Chinese
platforms and assemble publish-ready short videos with captions, titles,
hooks and voiceover.

**Inputs:** strategy brief, destination keywords, target platform specs
(aspect ratio, duration, caption style).

**Core tasks:**
1. Search 抖音 / 小红书 / bilibili for raw footage matching selling points.
2. Download candidate clips (respecting platform ToS as far as practical —
   see §8 Compliance).
3. Tag clips by scene type, location, visual mood → **Material Library**.
4. For each brief angle, generate a **shot list** (JSON) mapping
   `hook → cut → selling point cuts → CTA` to specific clip IDs + in/out
   timestamps.
5. Render:
   - Cuts via FFmpeg (deterministic, scriptable).
   - Voiceover via ElevenLabs (multilingual).
   - Subtitles burned in via Whisper → styled ASS/SRT → FFmpeg overlay.
   - Title card + CTA overlay.
6. Produce 2 variants per angle: (a) straight translation of competitor
   angle, (b) re-written in brand voice.
7. Register each output in the **Generated Video Library**.

**Output artifact:** .mp4 files + metadata row (duration, angle,
source clips, voice params, subtitle file).

**Eval:** see §7.2.

### 2.3 Dana — Distribution & Analytics
**Role:** publish finished videos to target accounts and close the
learning loop.

**Core tasks:**
1. Schedule + publish to YouTube (Data API), TikTok (Content Posting API),
   Instagram (Graph API for business accounts).
2. Manage per-platform metadata (title, description, hashtags,
   thumbnails) — variants A/B.
3. Pull performance data on a cron: impressions, views, average watch
   time, retention curves, CTR, comments.
4. Normalize into a common schema and store in the **Metrics Store**.
5. Feed insights back to Eric as a **Learning Report** every N days:
   - Which hooks had the highest retention at 3s / 15s?
   - Which selling points correlated with longer watch-time?
   - Which comments reveal new angles?
6. Flag under-performers for takedown or re-upload with changes.

**Eval:** see §7.3.

### 2.4 Inter-Agent Communication
Agents communicate by writing structured artifacts (markdown + JSON) to
a shared **Project Workspace** + appending messages on a shared
**ConversationBus** (Postgres table + pub/sub). The UI chat tab shows this
bus. Humans can inject messages into the bus; any agent can be @-mentioned.

---

## 3. Business Flow (End-to-End)

```
[Operator picks destination]
        |
        v
  Eric → Strategy Brief
        |
        v
  Mike ← Brief, produces N videos
        |
        v
  Dana ← Videos, publishes + collects metrics
        |
        v
  Dana → Learning Report → Eric (loop closes)
```

Each loop = one "campaign cycle". Target cycle time: ≤ 7 days initially,
≤ 3 days at steady state.

---

## 4. Technical Architecture

### 4.1 Stack (decided — Azure-first, $150/month cap)

| Layer | Choice | Why |
|---|---|---|
| Agent framework | **LangGraph** (Python) | Graph-based, stateful, HITL, persistence built in |
| Agent LLM (primary) | **Claude via GitHub Copilot** (user-owned) | Already paid, no extra cost |
| Agent LLM (fallback) | **Azure OpenAI** (GPT-4o / o1) | Resilience when Copilot quota exhausted |
| Tool calling | LangGraph ToolNode + pydantic schemas | Type-safe tool boundary |
| **Video ingest — YouTube** | **YouTube Data API v3** + **yt-dlp** (as library) | Official API is free (10k units/day), yt-dlp handles audio download for transcription |
| **Video ingest — TikTok/IG** (Phase 2) | yt-dlp + **Evil0ctal/Douyin_TikTok_Download_API** + **instaloader** | Open-source, no Apify cost |
| **Video ingest — CN platforms** (Mike/M2) | **NanmiCoder/MediaCrawler** (Playwright-based) for 抖音/小红书/B站 | Unified project, survives signature changes, best-in-class CN comment extraction |
| Comments (YouTube) | YouTube Data API + **youtube-comment-downloader** | Deep comment trees |
| **Proxy/VPN** | **None required for MVP** — official APIs + user-cookie + rate-limit | Save $10-80/month; add Webshare ($6/mo) only if Mike gets rate-limited |
| Transcription | **Azure OpenAI Whisper** (primary) + local `whisper.cpp` (fallback for batch) | On Azure budget, multilingual |
| Voiceover | **Azure AI Speech Neural TTS** (MVP), upgrade to ElevenLabs later if needed | ~$5/month at MVP volume vs $22 for ElevenLabs |
| Video edit | **FFmpeg** (deterministic, scriptable) | Reproducible, free |
| Storage | **Azure Blob Storage** (Hot tier) | ~$5/month for ~100GB |
| Database | **Azure Database for PostgreSQL Flexible Server** (B1ms) | Managed, ~$13/month |
| Queue | **Azure Service Bus** (Basic) | Cheap, reliable; no Redis dependency |
| Backend API | **FastAPI** | Typed, async |
| Frontend | **Next.js 14 (App Router) + shadcn/ui + Tailwind** | Fastest to polished product |
| Realtime | **Server-Sent Events** | Simpler than WS for streaming agent messages |
| Auth | **Clerk** (MVP) or Azure AD B2C (later) | Multi-tenant-ready |
| Observability | **Langfuse** self-hosted on Azure Container Apps | Free, LLM-native tracing |
| Secrets | **Azure Key Vault** | Centralized keys (YouTube, Azure, Copilot tokens) |
| Infra | Docker Compose dev → **Azure Container Apps** + ACI for Playwright jobs | Consumption-based billing |
| Region | **East Asia** or **Japan East** | Proximity to CN platforms + reasonable global latency |
| Budget guard | Azure Cost Alerts at $80 / $120 / $140 | Hard cap $150/month |

### 4.2 Repo Layout

```
voyager/
├── apps/
│   ├── api/              # FastAPI backend
│   ├── web/              # Next.js frontend
│   └── workers/          # Dramatiq workers (scraping, rendering, publish)
├── packages/
│   ├── agents/           # LangGraph agents: eric, mike, dana
│   │   ├── eric/
│   │   ├── mike/
│   │   └── dana/
│   ├── tools/            # Shared tool implementations (apify, whisper, ffmpeg...)
│   ├── schemas/          # Pydantic + TS shared schemas (via codegen)
│   └── evals/            # Eval harnesses per agent
├── infra/
│   ├── docker-compose.yml
│   └── migrations/       # Alembic
├── docs/
│   ├── PRD.md            # this file
│   └── plans/            # implementation plans per agent
└── .env.example
```

### 4.3 Data Model (core tables)

- `tenants(id, name, created_at)`
- `projects(id, tenant_id, destination, icp, voice, status)`
- `discovered_videos(id, project_id, platform, url, title, author,
  views, likes, comments, upload_date, transcript, analysis_json,
  thumbnail_url, discovered_at)` — Eric output
- `strategy_briefs(id, project_id, content_md, source_video_ids[], created_at)`
- `raw_clips(id, project_id, platform, url, local_path, tags[], scene_type,
  duration_s, metadata_json)` — Mike material library
- `generated_videos(id, project_id, brief_id, angle, variant, shot_list_json,
  output_path, duration_s, voice_profile, status)`
- `publications(id, generated_video_id, platform, account_id, platform_post_id,
  title, description, hashtags[], published_at, status)`
- `metrics(id, publication_id, snapshot_at, impressions, views,
  avg_watch_time_s, retention_curve_json, ctr, likes, comments_count,
  raw_json)`
- `agent_messages(id, project_id, agent, role, content, artifact_ids[],
  created_at)` — ConversationBus

### 4.4 UI (Phase 1 MVP)

Tabs in the product app:

1. **Chat** — multi-agent conversation. Left sidebar lists agents (Eric,
   Mike, Dana), main pane is threaded chat. Humans can @mention.
2. **Discovered Videos** (Eric's library) — grid: thumbnail, title, platform,
   views, hook summary, "analysis" expandable.
3. **Generated Videos** (Mike's library) — grid: preview, angle, variant,
   source clips, download button, "publish" action.
4. **Material Library** (Mike's raw clips) — grid with tags/filters.
5. **Distribution** (Dana) — table of publications + live metrics, per
   platform tabs, retention curve chart per video.

---

## 5. Build Order & Milestones

**Rule:** each agent must pass its eval harness before we start the next.

- **M0 — Project Skeleton (week 1)**
  - Monorepo, docker-compose, Postgres, auth stub, FastAPI health endpoint,
    Next.js hello page, CI.
- **M1 — Eric end-to-end (week 2-3)**
  - Scraping, transcription, analysis, strategy brief, UI "Discovered Videos"
    tab, Eric eval passes.
- **M2 — Mike end-to-end (week 4-5)**
  - CN scrapers (Playwright), clip tagging, FFmpeg pipeline, ElevenLabs
    voiceover, Whisper subtitles, Generated Videos tab, Mike eval passes.
- **M3 — Dana end-to-end (week 6-7)**
  - YouTube publish first, then TikTok + IG, metrics cron, Learning Report,
    Distribution tab, Dana eval passes.
- **M4 — Full loop + productization (week 8+)**
  - Multi-tenant, onboarding, billing stub, docs.

---

## 6. MVP Scope — Hard Cuts

**In scope for MVP:**
- English-language overseas audience, YouTube Shorts first.
- One destination: 川西.
- Three agents behind one UI.

**Out of scope for MVP (explicit):**
- Multi-tenant billing.
- TikTok + Instagram publishing (Phase 2 of Dana).
- Fine-tuned branded avatars (Arcads-style) — use ElevenLabs VO + stock
  footage for MVP.
- Automatic takedowns / moderation.

---

## 7. Evaluation Harnesses

Each agent has a golden dataset + LLM-judge + rule-based checks.

### 7.1 Eric Eval
- **Dataset:** 20 pre-labeled YouTube videos with human-annotated
  hooks + selling points.
- **Metrics:**
  - Hook extraction F1 ≥ 0.75 against human labels.
  - Selling-point recall ≥ 0.70.
  - Brief passes LLM-judge rubric (structure, specificity, actionability)
    with score ≥ 4/5 on 8/10 runs.
- **Gate:** must pass before Mike starts.

### 7.2 Mike Eval
- **Dataset:** 5 strategy briefs + pool of 200 raw clips.
- **Metrics:**
  - Shot list references valid clips 100% of the time.
  - Output video plays, audio-video in sync (FFprobe check).
  - Subtitles aligned within 300 ms of audio (Whisper re-check).
  - Human rating ≥ 4/5 on "watchable" for 7/10 outputs.
- **Gate:** must pass before Dana starts.

### 7.3 Dana Eval
- **Dataset:** 10 seeded publications in a sandbox account.
- **Metrics:**
  - 100% publish success to YouTube API (idempotent, no dupes).
  - Metrics pulled with <5% missing fields over 7 days.
  - Learning Report identifies top hook pattern matching ground-truth
    retention-curve winner in 8/10 seeded cases.

---

## 8. Compliance & Risk

- **Platform ToS:** downloading from 抖音/小红书/bilibili/YouTube has ToS
  implications. Voyager will: (a) prefer official APIs where available
  (YouTube, Meta), (b) use Apify or user-operated Playwright sessions
  with explicit rate limits, (c) document source attribution, (d) offer
  a fair-use / transformative-edit policy; the operator accepts
  responsibility per-tenant.
- **Copyright:** emphasize transformative editing (voiceover, re-cut,
  new narrative); Mike must compose from multiple sources, never
  republish a single creator's clip verbatim.
- **PII:** comments may contain PII — hash usernames in storage.
- **Rate-limits / bans:** Apify residential proxies + Playwright with
  realistic human behavior (mouse jitter, scroll, dwell time). Per-account
  action budgets.

---

## 9. Resolved Decisions (was: Open Questions)

1. **Languages:** English only for MVP. Revisit Spanish/Japanese post-M3.
2. **Accounts:** YouTube/TikTok/IG accounts deferred — Dana will use sandbox
   accounts for eval; real account warm-up is a Phase 2 concern.
3. **Budget:** Hard cap **$150/month on Azure**. LLM via user's GitHub
   Copilot Claude (free). No Apify. No ElevenLabs (use Azure Speech). No
   paid proxies for MVP.
4. **HITL:** Fully automatic. No human approval gate on Mike's shot list.
   Human only sets campaign rules at project creation.

---

## 10. Next Action

Proceed to **Eric's implementation plan** (`docs/plans/2026-04-19-eric-build.md`),
which breaks M1 into bite-sized TDD tasks ready for subagent-driven
development.
