# Voyager

Multi-agent platform for overseas growth of China travel videos.

Three agents:
- **Eric** — competitor analyst (M1, in progress)
- **Mike** — editor (M2)
- **Dana** — distribution + analytics (M3)

## Layout

```
apps/
  api/          FastAPI backend
  web/          Next.js 14 frontend
packages/
  agents/       LangGraph agents
  tools/        YouTube, yt-dlp, Whisper, Blob clients
  evals/        Hand-labeled fixtures + eval harnesses (the gates)
  db/           SQLModel models + Alembic migrations
infra/          Bicep templates for Azure
docs/
  PRD.md        Product requirements
  plans/        Per-milestone implementation plans
```

## Build order

Strict gate: each agent must pass its eval harness on `main` before the next is built.

## Budget

Hard cap: **$150/month on Azure**. LLMs via GitHub Copilot Claude (free) + Azure OpenAI (fallback). No proxies, no Apify, no ElevenLabs in MVP.

See `docs/PRD.md` for full spec and `docs/plans/2026-04-19-eric-build.md` for the current implementation plan.
