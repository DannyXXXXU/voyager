# Eric Eval Harness — Implementation Plan

**Agent:** Eric (Competitive Research Analyst)
**Milestone:** M1 Exit Gate (Task 1.19 of eric-build)
**Created:** 2026-04-21
**Owner:** Danny
**Status:** Ready to execute
**Related skills:** `langgraph-agent-eval-gate`, `test-driven-development`, `writing-plans`

---

## Why this plan exists

Voyager rule: **no next agent until current agent clears its eval gate.**
Eric's end-to-end pipeline is built (M1.1-M1.8 merged). Now we prove it works
well enough to hand off to Mike. A flaky Eric poisons the entire downstream
(bad briefs → bad shot lists → bad videos → wasted budget → wrong learning
signal back to Eric).

A "very good" eval for Eric means:

1. **Multi-dimensional metrics** — hook F1, selling-point recall, brief quality
   rubric, comment-insight usefulness. No single number can be gamed.
2. **Held-out discipline** — 5 videos Eric NEVER sees during prompt iteration.
3. **Judge independence** — LLM-judge uses a different model (GPT-4o via Azure)
   than the agent (Copilot Claude), run 3× with median, temperature=0.
4. **Real data** — fixtures are real YouTube videos of actual 川西 / 中国 travel
   content, not synthetic.
5. **Cost budget** — full eval run ≤ $0.50 and ≤ 15 min wall time, so it runs on
   every PR without friction.
6. **Regression detection** — results stored with git SHA; nightly job compares
   last 7 days; prompt changes that tank a metric are reverted.
7. **Human-in-loop sanity** — you eyeball 3 random briefs before the gate is
   declared "truly" green. LLM judges are fallible.
8. **Reproducible** — fixtures versioned in repo; same seed; deterministic
   unless LLM is in the loop.
9. **Drill-down debuggability** — per-fixture report showing WHICH hook was
   missed, WHY judge scored low, links to raw agent outputs.
10. **Prompt iteration is tracked** — every change to a prompt is a commit with
    the diff in its eval scores noted in the message.

---

## Architecture of the eval

```
┌─────────────────────────────────────────────────────────────┐
│  packages/evals/eric/                                       │
│                                                             │
│  fixtures/                                                  │
│    hooks.yaml             ← 10 fixtures, hook-only gold     │
│    selling_points.yaml    ← 10 fixtures, SP-only gold       │
│    campaigns_dev.yaml     ← 5 full campaigns (tune on)      │
│    campaigns_heldout.yaml ← 5 full campaigns (NEVER tune)   │
│                                                             │
│  gold/                                                      │
│    transcripts/           ← pre-fetched Whisper outputs     │
│    comments/              ← pre-fetched comment snapshots   │
│    (so eval is deterministic, no scraping during CI)        │
│                                                             │
│  judges/                                                    │
│    brief_rubric.md        ← 5-dimension rubric for briefs   │
│    hook_match.md          ← is Eric's hook ≡ gold hook?     │
│    sp_match.md            ← does gold SP appear in output?  │
│                                                             │
│  metrics/                                                   │
│    hook_f1.py             ← deterministic F1                │
│    sp_recall.py           ← deterministic recall@k          │
│    brief_quality.py       ← LLM-judge wrapper               │
│    comment_coverage.py    ← % comments reflected in brief   │
│                                                             │
│  run_eval.py              ← entry point, CLI                │
│  report.py                ← renders HTML + markdown reports │
│  thresholds.yaml          ← pass/fail criteria              │
│  README.md                ← how-to-add-fixture guide        │
└─────────────────────────────────────────────────────────────┘
```

Report output:
```
packages/evals/eric/reports/
  2026-04-21-abc123def/
    summary.md        ← human-readable pass/fail table
    report.html       ← drill-down per-fixture view
    traces.jsonl      ← one line per fixture, full I/O
    scores.json       ← structured scores for regression DB
```

---

## Phase E1 — Fixture construction (the long pole)

### Task E1.1 — Candidate video harvest

**Objective:** assemble a pool of ~40 candidate YouTube videos to cherry-pick 20 fixtures from.

**Files:**
- Create: `packages/evals/eric/scripts/harvest_candidates.py`

**Steps:**
1. Queries: `"Sichuan travel"`, `"China travel vlog"`, `"Chengdu food"`, `"西藏 travel"`, `"川西 自驾"`, `"China hidden gem travel"` (EN + ZH).
2. Use the existing YouTube Data API client (`packages/tools/youtube_search`).
3. Filter: duration 30s-12min, uploaded in last 18 months, views ≥ 50k.
4. Dump `candidates.csv` with `video_id, title, channel, views, likes, duration, url`.

**Verify:** ≥ 40 rows, mix of Shorts + long-form, mix of native-Chinese vs Western creators.

### Task E1.2 — Manual fixture selection

**Objective:** pick 20 videos that span difficulty + content types.

**Steps:**
1. Open `candidates.csv` in a sheet.
2. Label each candidate with `difficulty ∈ {easy, medium, hard}` and
   `content_type ∈ {scenic, food, cultural, adventure, family}`.
3. Pick 20 to cover: 6 easy / 10 medium / 4 hard, ≥ 3 of each content type.
4. Mark 5 as `holdout=true` — these NEVER inform prompt iteration.
5. Export selections as `packages/evals/eric/fixtures/_master_list.yaml`.

**Verify:** master list has `id, url, difficulty, content_type, holdout, notes`.

### Task E1.3 — Pre-fetch transcripts + comments (determinism)

**Objective:** cache Whisper + comment outputs so CI doesn't re-scrape.

**Files:**
- Create: `packages/evals/eric/scripts/prefetch_gold.py`

**Steps:**
1. For each of the 20 fixtures: run existing `yt_dlp_audio` + `whisper_client` + `comments_fetch`.
2. Save to `gold/transcripts/{video_id}.txt` and `gold/comments/{video_id}.jsonl`.
3. Add SHA256 of each to `_master_list.yaml` so tampering is caught.

**Verify:** 20 transcripts + 20 comment files; re-run produces identical SHA.

### Task E1.4 — Gold label: hooks (10 fixtures)

**Objective:** human-annotated hooks for F1 metric.

**Files:**
- Create: `packages/evals/eric/fixtures/hooks.yaml`

**For each of 10 chosen fixtures** (6 dev + 4 holdout), annotate:
```yaml
- id: yt_abc123
  hook:
    text: "What if I told you there's a place in China where..."
    timestamp_start: 0.0
    timestamp_end: 4.3
    type: intrigue_question    # one of: intrigue_question, bold_claim,
                                #        visual_reveal, pain_point,
                                #        number_stat, quote, ...
    keyphrases: ["hidden valley", "nobody goes"]  # bag-of-words for fuzzy F1
  difficulty: medium
  notes: "Hook uses both question and visual reveal; accept either"
```

**Verify:** 10 entries; each has at least 3 keyphrases; Danny (you) labels the 4 holdout, Claude drafts the 6 dev which Danny spot-checks.

### Task E1.5 — Gold label: selling points (10 fixtures)

**Objective:** list of 3-5 SPs per fixture for recall metric.

**Files:**
- Create: `packages/evals/eric/fixtures/selling_points.yaml`

For each fixture:
```yaml
- id: yt_abc123
  selling_points:
    - id: sp1
      text: "Untouched nature — no crowds"
      aliases: ["no tourists", "remote", "pristine", "empty"]
      importance: primary   # primary | secondary
    - id: sp2
      text: "Food culture — Tibetan tea and yak"
      aliases: ["local food", "yak meat", "butter tea"]
      importance: primary
    ...
```

**Verify:** 10 fixtures × 3-5 SPs each; aliases allow fuzzy match.

### Task E1.6 — Gold label: full campaigns (10 fixtures)

**Objective:** end-to-end brief quality gold.

**Files:**
- Create: `packages/evals/eric/fixtures/campaigns_dev.yaml` (5)
- Create: `packages/evals/eric/fixtures/campaigns_heldout.yaml` (5)

Each campaign spec:
```yaml
- id: campaign_chuanxi_01
  input:
    destination: "川西"
    language: en
    icp: "US millennials into adventure travel"
    seed_video_ids: [yt_abc123, yt_def456, yt_ghi789]  # 3 seeds per campaign
  gold:
    must_mention_hooks: [hook_type_visual_reveal, hook_type_bold_claim]
    must_mention_sps: ["remote landscape", "Tibetan culture", "accessible"]
    must_cite_comments: true
    brief_min_length_words: 500
    brief_max_length_words: 1200
  notes: "Danny-authored gold; holdout unless id ends _dev"
```

**Verify:** 10 campaigns; 3 seed videos each drawn from the 20 fixtures.

---

## Phase E2 — Metrics (deterministic)

### Task E2.1 — Hook F1

**Files:**
- Create: `packages/evals/eric/metrics/hook_f1.py`, `packages/evals/eric/tests/test_hook_f1.py`

**Algorithm:**
1. For each fixture, Eric outputs `hook_text`, `hook_type`, `hook_keyphrases`.
2. Score = max of:
   - exact type match (1.0 or 0.0)
   - keyphrase F1 on gold keyphrases (normalized, lowercase, stemmed)
   - LLM-judge "do these hooks mean the same thing?" (tie-breaker only)
3. Aggregate: macro F1 across fixtures.

**Tests (TDD, RED first):**
- `test_exact_match` — identical hooks score 1.0
- `test_keyphrase_partial` — 2/4 keyphrases score 0.5
- `test_type_mismatch_but_same_meaning` — falls back to judge
- `test_empty_hook` — scores 0.0

**Verify:** `pytest packages/evals/eric/tests/test_hook_f1.py -v` green.

### Task E2.2 — Selling-point recall@k

**Files:**
- Create: `packages/evals/eric/metrics/sp_recall.py`, tests.

**Algorithm:**
1. Eric's brief contains candidate SPs.
2. For each gold SP, check if any Eric SP's text (or alias) has ≥ 0.7 cosine
   similarity (using `sentence-transformers/all-MiniLM-L6-v2`, local, free).
3. Recall = matched / |gold|.
4. Weighted: primary SPs count 2x secondary.

**Tests:**
- `test_exact_sp_match`
- `test_alias_match`
- `test_semantic_similarity_threshold`
- `test_primary_weighting`

### Task E2.3 — Comment coverage

**Objective:** brief should cite audience concerns from top comments.

**Files:**
- Create: `packages/evals/eric/metrics/comment_coverage.py`, tests.

**Algorithm:**
1. Extract top 20 comments per seed video (by likes).
2. Cluster to ~5 themes using MiniLM + agglomerative clustering.
3. Score = % of themes that appear in Eric's brief's "audience concerns" section,
   measured by cosine ≥ 0.6 against theme centroid.

### Task E2.4 — Schema validity (quick sanity)

**Files:**
- Create: `packages/evals/eric/metrics/schema_validity.py`

Eric's brief must be valid against a Pydantic schema (sections: executive_summary, top_hooks, selling_points, audience_concerns, recommended_angles, source_videos). Score: 1.0 if parses, 0.0 if not. This catches catastrophic failures.

---

## Phase E3 — Metrics (LLM judge)

### Task E3.1 — Brief quality rubric

**Files:**
- Create: `packages/evals/eric/judges/brief_rubric.md`

5-dimension rubric, 1-5 each, averaged:
1. **Structure & completeness** — all 6 required sections present and substantive.
2. **Specificity** — concrete, not generic ("scenic views of mountains" = 1; "7am light on Siguniang Mountain peaks from Rilong viewpoint" = 5).
3. **Actionability for Mike** — can Mike generate a shot list from this?
4. **Evidence grounding** — claims reference source videos or comments.
5. **Insight quality** — non-obvious observations about why hooks work.

### Task E3.2 — Judge runner

**Files:**
- Create: `packages/evals/eric/metrics/brief_quality.py`, tests.

**Algorithm:**
1. Use **Copilot CLI with `--model gpt-5`** (different model family from Eric's Claude Sonnet — eliminates self-preference bias).
2. Reuse existing `packages/agents/voyager_agents/eric/copilot_client.py` but parameterize the model.
3. Temperature=0 where supported (pass `--no-stream` for determinism).
4. Run judge 3 times, take median per dimension.
5. Return per-dimension scores + average.
6. Cache by `hash(brief + rubric_version + model)` to avoid re-billing Copilot premium requests on replay.
7. No extra $ cost — uses Danny's existing Copilot subscription.

**Tests:**
- `test_judge_deterministic_with_cache`
- `test_judge_returns_all_5_dimensions`
- `test_judge_median_of_3`

### Task E3.3 — Pairwise judge (bonus, regression)

**Objective:** compare two brief versions (before/after prompt change).

Shown 2 briefs for the same campaign, judge picks winner. Useful for prompt
iteration — you don't need absolute scores, just "is it better?".

---

## Phase E4 — Runner + thresholds

### Task E4.1 — `run_eval.py`

**Files:**
- Create: `packages/evals/eric/run_eval.py`

**CLI:**
```
python -m packages.evals.eric.run_eval \
    --fixtures dev|heldout|all \
    --agent-version git|<sha> \
    --output-dir reports/{date}-{sha}/ \
    --cost-cap-usd 1.0
```

**Steps:**
1. Load fixtures (filter by holdout flag).
2. For each fixture: invoke Eric's LangGraph using pre-fetched transcripts (inject via a fake `fetch_audio` node that reads from `gold/transcripts/`).
3. Collect all raw outputs → `traces.jsonl`.
4. Run each metric module.
5. Compare against `thresholds.yaml`.
6. Emit: `summary.md`, `report.html`, `scores.json`.
7. Exit 0 on all-pass, 1 on any fail.
8. Track USD spend (judge calls) — fail early if cap exceeded.

**Important:** does NOT call YouTube API or scrapers during eval. All inputs
come from the pre-fetched gold/ files. Eval must run offline.

### Task E4.2 — `thresholds.yaml`

```yaml
agent: eric
version: 1
fixtures:
  dev: 15          # 6 hook + 5 SP + ... but you get the idea; see fixture files
  heldout: 5       # held-out campaigns
required_pass_rate: 0.80   # 80% of dev must pass; 100% of heldout must pass
metrics:
  hook_extraction_f1:
    threshold: 0.75
    type: deterministic
  selling_point_recall:
    threshold: 0.70
    type: deterministic
    primary_weight: 2
  schema_validity:
    threshold: 1.0     # hard requirement
    type: deterministic
  comment_coverage:
    threshold: 0.50
    type: deterministic
  strategy_brief_quality:
    threshold: 4.0
    type: llm_judge
    judge_model: copilot/gpt-5
    runs: 3
    aggregation: median
    temperature: 0
cost_budget_usd: 0.1    # judge is Copilot (no $), only Whisper/Azure egress counts
wall_clock_cap_seconds: 900
```

### Task E4.3 — Fake `fetch_audio` node

**Files:**
- Create: `packages/agents/voyager_agents/eric/nodes_data_eval.py`
- Modify: `packages/agents/voyager_agents/eric/graph.py` (accept an injection point)

**Why:** we don't want the eval to scrape YouTube or call Azure Whisper — both are flaky, cost money, and make CI slow.

In eval mode, the data node reads from `gold/transcripts/{id}.txt` instead.
Guard via `state.eval_mode=True` flag + env var `ERIC_EVAL_MODE=1`.

**Test:** eval runs offline (simulate by `unset` Azure env vars, should still complete).

---

## Phase E5 — Reporting

### Task E5.1 — `report.py` (markdown + HTML)

**Files:**
- Create: `packages/evals/eric/report.py`
- Create: `packages/evals/eric/templates/report.html.j2` (Jinja2 template)

**Markdown summary example:**
```
# Eric eval — 2026-04-21 (SHA abc123def)

Status: ❌ FAIL (1 of 5 metrics below threshold)

| Metric                         | Score | Threshold | Pass |
|--------------------------------|-------|-----------|------|
| hook_extraction_f1             | 0.82  | 0.75      | ✅   |
| selling_point_recall           | 0.68  | 0.70      | ❌   |
| schema_validity                | 1.00  | 1.00      | ✅   |
| comment_coverage               | 0.54  | 0.50      | ✅   |
| strategy_brief_quality         | 4.2   | 4.0       | ✅   |

Cost: $0.38  Wall time: 8m 12s  Fixtures: 15 dev + 5 heldout

Failing fixtures:
  - campaign_chuanxi_03 (sp_recall=0.60): missed "Tibetan tea culture"
  - campaign_food_02 (sp_recall=0.55): missed "street food affordability"
```

**HTML report:** per-fixture drill-down with:
- seed videos + thumbnails
- Eric's raw output
- judge reasoning per dimension
- diff vs gold
- one-click "mark this judge call as wrong" to build a judge-disagreement set

### Task E5.2 — Regression DB (simple)

**Files:**
- Create: `packages/evals/eric/regression.py`
- DB table: `eval_runs(id, agent, git_sha, ran_at, scores_json, passed)`

After every `run_eval.py`, append a row. A companion script shows trend:
```
python -m packages.evals.eric.regression --last 10
```
Prints a sparkline per metric to spot regressions fast.

---

## Phase E6 — CI + iteration workflow

### Task E6.1 — GitHub Actions gate

**Files:**
- Create: `.github/workflows/eric-eval.yml`

Triggers:
- PR touches `packages/agents/voyager_agents/eric/**` or `packages/evals/eric/**`
- Nightly cron at 05:00 UTC on main

Runs `run_eval.py --fixtures dev` on PRs (fast), `--fixtures all` nightly.

Uploads `reports/` as artifact. Comments summary table on PR.

### Task E6.2 — Prompt iteration playbook

**Files:**
- Create: `packages/evals/eric/README.md`

Section: "How to improve Eric when eval fails"

1. Look at failing fixtures in the HTML report.
2. Hypothesize which prompt is at fault (hook extraction? SP extraction? Brief synthesis?).
3. Edit prompt in `packages/agents/voyager_agents/eric/prompts/` — versioned commit.
4. Re-run `run_eval.py --fixtures dev` only. DO NOT look at heldout.
5. Commit with message: `eric(prompt): <change>  [hook_f1: 0.78→0.83, sp_recall: 0.68→0.71]`
6. After 3 successful dev iterations, run `--fixtures heldout` once. If holdout passes, gate is green. If holdout regresses, you've overfit; revert.

**Rule:** you may NOT iterate on prompts against the holdout set. If you do, discard and regenerate the holdout from new videos.

### Task E6.3 — Human eyeball check

**Files:**
- Create: `packages/evals/eric/scripts/eyeball.py`

Picks 3 random fixtures from the latest green run, opens the brief in `less` / your editor, asks "would this be useful for Mike? [y/N]". Recorded in `eyeball_log.jsonl` with SHA. Eric is NOT promoted until 3 consecutive green runs each get ≥ 2 of 3 human yeses.

---

## Exit criteria (Eric promoted)

- [ ] `run_eval.py --fixtures all` exits 0 on latest `main`.
- [ ] CI workflow green on 3 consecutive commits.
- [ ] Eyeball check: ≥ 2/3 yes on 3 independent runs (9 eyeballs, ≥ 6 yes).
- [ ] Azure cost dashboard shows eval-driven spend < $5 total this month.
- [ ] `packages/evals/eric/reports/` has at least one full report checked in as a baseline.
- [ ] Holdout set has been used exactly once successfully (not iterated on).

Once all checked → tag `release/eric-v1`, open `docs/plans/YYYY-MM-DD-mike-build.md`.

---

## Estimated effort

| Phase | Work | Est. |
|---|---|---|
| E1 Fixtures | Harvest + label (you) + prefetch | 1 day (labeling is the long pole) |
| E2 Deterministic metrics | 4 files + tests (TDD) | 0.5 day |
| E3 LLM judge | Rubric + runner + cache | 0.5 day |
| E4 Runner | Offline invocation + fake fetcher | 0.5 day |
| E5 Reporting | MD + HTML + regression DB | 0.5 day |
| E6 CI + playbook | Workflow + eyeball + docs | 0.5 day |
| **Prompt iteration loop** | Until dev passes (unbounded) | 0.5-2 days realistic |
| **Total** | | **3-5 days** |

Use `subagent-driven-development` to parallelize E2/E3/E5 (independent).

---

## Execution approach

1. Kick off E1.1 (harvest) now — it's purely mechanical, start script in background.
2. While candidates harvest, build E2 (deterministic metrics) in parallel — no fixtures needed yet, just test-first on synthetic data.
3. Once E1.2-E1.6 done (labeling), wire everything in E4.
4. First full run will FAIL — that's good, it means we learn what to iterate.
5. Iterate on prompts with dev set only.
6. Holdout run = the real gate.

---

## Open questions for Danny before we start E1

1. **Judge model**: I specced **Azure OpenAI GPT-4o** for independence from
   Copilot Claude. This will cost money on Azure (~$0.30/eval run). OK? Or
   prefer Azure OpenAI gpt-4o-mini (cheaper, slightly noisier judge)?
2. **Holdout labeling**: you personally label 5 holdout (highest quality),
   Claude drafts 15 dev fixtures, you spot-check. OK?
3. **How much of your time for labeling**: realistic estimate is ~2 hours for
   you to do the 5 holdout + spot-check the 15 dev. OK to block on that?
4. **Harvest queries**: I listed EN + ZH queries above. Want to add anything
   specific to what your future product will actually promote? (e.g., if you
   care more about Tibet than Sichuan, let's weight it.)
