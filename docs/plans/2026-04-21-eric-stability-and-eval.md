# Eric 稳定性改造 + Eval Harness 实施计划

> **For Hermes:** 按 writing-plans skill + langgraph-agent-eval-gate skill 执行。任务粒度 2-5 分钟。eval-first：先搭 harness 拿 baseline，再改造，每个阶段跑一次 eval 对比。

**Goal:** 给 Eric agent 建立离线可重放的 eval 网关，并按 P0→P1 顺序做稳定性改造，跑过 M1 exit 阈值（hook F1≥0.75 / 卖点召回≥0.70 / brief judge≥4.0，10 次 8 过）。

**Architecture:** (1) `packages/evals/eric/` 独立 harness，读 `gold/` 预抓资产离线注入 `nodes_data_eval.py`，LLM 节点仍真实调用 Copilot Claude；(2) `copilot_client.py` 与 `nodes_llm.py` 按 P0（重试/json-repair/prefill/日志/TS schema）→P1（XML/scratchpad/few-shot/validators）增量改造；(3) 每次改造后 rerun eval，baseline/P0/P1 三份 report 全部入库 `reports/`。

**Tech Stack:** Python 3.11 + uv + LangGraph + Pydantic v2 + pytest + json-repair + sentence-transformers + lxml；judge 用 Copilot GPT-5（免费，独立于 agent 的 Claude）。

**Not in scope:** P2 map-reduce / P3 embedding 聚类 / P4 brief 章节化 / Langfuse / CI workflow（留到 M1 收尾后）。

---

## 阶段 0 — Skill 载入 & 现状复核

### Task 0.1: 重读 langgraph-agent-eval-gate skill
**Objective:** 强制按 skill 标准结构落地，避免自创。
- Run: `skill_view name=langgraph-agent-eval-gate`
- 对齐要点记在 plan 本地：目录结构、offline injection、thresholds.yaml 示例、5 holdout 人标铁律。

### Task 0.2: git 状态清理
**Objective:** 开工前 main 干净。
- Run: `git status`
- Expected: working tree clean（`apps/worker/Dockerfile` / `.dockerignore` / `docs/research/` 若还未提交，先各自 `git add && commit` 归位到描述性 message）
- 如有未追踪：`git add docs/research/ && git commit -m "docs: add Eric stability research"`

---

## 阶段 1 — Eval Harness 脚手架（Task 1.19a-g）

### Task 1.1: 创建 evals/eric 目录骨架
**Files — Create:**
- `packages/evals/pyproject.toml`（若不存在）
- `packages/evals/voyager_evals/__init__.py`
- `packages/evals/voyager_evals/eric/__init__.py`
- `packages/evals/voyager_evals/eric/fixtures/.gitkeep`
- `packages/evals/voyager_evals/eric/gold/transcripts/.gitkeep`
- `packages/evals/voyager_evals/eric/gold/comments/.gitkeep`
- `packages/evals/voyager_evals/eric/judges/.gitkeep`
- `packages/evals/voyager_evals/eric/reports/.gitkeep`
- `packages/evals/voyager_evals/eric/README.md`（写用法 + 新增 fixture 流程）
- `packages/evals/voyager_evals/eric/thresholds.yaml`
- `packages/evals/voyager_evals/eric/run_eval.py`（占位 main）

**Run:** `uv sync && uv run python -c "import voyager_evals.eric"`
**Expected:** 无 error。
**Commit:** `feat(evals): scaffold eric eval package skeleton`

### Task 1.2: 写 thresholds.yaml
**File — Create:** `packages/evals/voyager_evals/eric/thresholds.yaml`

```yaml
agent: eric
required_pass_rate: 0.80        # 10 次 run 中 8 过
holdout_required_pass_rate: 1.0 # 5 holdout 必须 100%
cost_budget_usd: 0.50
wall_clock_cap_seconds: 900
metrics:
  hook_extraction_f1:
    threshold: 0.75
    type: deterministic
    weight: 2
  selling_point_recall:
    threshold: 0.70
    type: deterministic
    weight: 2
  schema_validity_rate:
    threshold: 0.99
    type: deterministic
    weight: 1
  strategy_brief_quality:
    threshold: 4.0
    type: llm_judge
    judge_model: copilot-gpt-5
    rubric: judges/brief_rubric.md
    weight: 2
```

**Commit:** `feat(evals): add eric thresholds.yaml`

### Task 1.3: 写 judges/brief_rubric.md
**File — Create:** `packages/evals/voyager_evals/eric/judges/brief_rubric.md`

内容：5 维打分（specificity / actionability / evidence grounding / completeness / consumability by Mike），每维 1-5，total = 平均。固定 header/prompt 前缀让 judge 稳定。

**Commit:** `feat(evals): add brief judge rubric`

### Task 1.4: 写 fixture 数据模型
**File — Create:** `packages/evals/voyager_evals/eric/schema.py`

```python
from pydantic import BaseModel, Field
from typing import Literal

class GoldHook(BaseModel):
    text: str
    aliases: list[str] = Field(default_factory=list)
    timestamp_s: float | None = None

class GoldSellingPoint(BaseModel):
    text: str
    aliases: list[str] = Field(default_factory=list)

class EricFixture(BaseModel):
    id: str
    video_id: str
    topic: str
    difficulty: Literal["easy", "medium", "hard"]
    content_type: str
    holdout: bool = False
    gold_hooks: list[GoldHook] = Field(default_factory=list)
    gold_selling_points: list[GoldSellingPoint] = Field(default_factory=list)
    notes: str = ""
    transcript_sha256: str
```

**Test — Create:** `packages/evals/tests/test_schema.py` 一条 roundtrip。
**Commit:** `feat(evals): add eric fixture schema`

### Task 1.5: 给 graph.py 加 eval_mode 注入点
**File — Modify:** `packages/agents/voyager_agents/eric/graph.py`

改 `build_data_graph` 签名，加 `data_nodes` 参数（默认 `None` → 生产节点；传入 `nodes_data_eval` 模块则改走离线）：

```python
def build_data_graph(session_factory=None, data_nodes=None):
    from voyager_agents.eric import nodes_data as default_nodes
    nd = data_nodes or default_nodes
    ...
    g.add_node("fetch_metadata", nd.node_fetch_metadata)
    # ... 对所有 data 节点做同样替换
```

**Commit:** `feat(eric): add data_nodes injection point for eval`

### Task 1.6: 写 nodes_data_eval.py
**File — Create:** `packages/agents/voyager_agents/eric/nodes_data_eval.py`

5 个节点同名，签名同；从 `gold/transcripts/<video_id>.txt` / `gold/comments/<video_id>.jsonl` 读，不触网。persist 节点写 no-op（eval 不入库）。

**Test:** 构造假 EricState 带一个 video_id，配合临时 gold 目录调用 `node_transcribe` 验证返回。
**Commit:** `feat(eric): offline data nodes reading from gold/`

### Task 1.7: 写 prefetch_gold.py
**File — Create:** `scripts/prefetch_gold.py`

输入一份 `seed.yaml`（20 个 video_id + topic）→ 调现有 tools 拉 metadata + 下载音频 + Whisper + comments → 写 `gold/transcripts/<vid>.txt`、`gold/comments/<vid>.jsonl`、`gold/manifest.yaml`（含 sha256 校验）。

**Commit:** `feat(evals): add prefetch_gold script`

### Task 1.8: 确定 20 seed videos
**File — Create:** `packages/evals/voyager_evals/eric/seed.yaml`

20 条 `{video_id, topic, difficulty, content_type, holdout}`；buckets: 短/长 × vlog/城市导览/美食/文化 × easy/medium/hard。5 条标 `holdout: true`。

**Run:** `uv run python scripts/prefetch_gold.py --seed seed.yaml`
**Expected:** 20 份 transcript 落盘，manifest.yaml 生成。
**Commit:** `data(evals): add 20 seed videos and prefetch gold assets`

### Task 1.9: Agent 自动 draft 15 dev fixtures
**Objective:** 让 Copilot Claude 读每条 transcript 生成金标草稿。

- 写 `scripts/draft_dev_fixtures.py`：for each non-holdout video → 调 CopilotClaudeClient 按专用 prompt 产出 `{gold_hooks, gold_selling_points}` → 存 `fixtures/dev/<id>.yaml`。
- Danny spot-check 3-5 条（备注：这一步人工，但不阻塞后续任务，可先用 draft 当占位）。
**Commit:** `data(evals): draft 15 dev fixtures via agent`

### Task 1.10: 5 holdout fixtures 空 stub
**File — Create:** `packages/evals/voyager_evals/eric/fixtures/holdout/<id>.yaml`

只填 `id / video_id / topic / difficulty / content_type / holdout: true / transcript_sha256 / gold_hooks: [] / gold_selling_points: []`，留 TODO 注释。
**Commit:** `data(evals): add holdout fixture stubs awaiting human labels`

### Task 1.11: 实现 deterministic metrics
**File — Create:** `packages/evals/voyager_evals/eric/metrics.py`

```python
from sentence_transformers import SentenceTransformer, util

_MODEL = None
def _enc():
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _MODEL

def fuzzy_match(pred: str, gold_aliases: list[str], thresh: float = 0.72) -> bool:
    m = _enc()
    p = m.encode(pred, convert_to_tensor=True)
    g = m.encode(gold_aliases, convert_to_tensor=True)
    return float(util.cos_sim(p, g).max()) >= thresh

def hook_f1(preds: list[str], golds: list[GoldHook]) -> float: ...
def selling_point_recall(preds: list[str], golds: list[GoldSellingPoint]) -> float: ...
def schema_validity(results: list[bool]) -> float: ...
```

**Test:** `tests/test_metrics.py` — 同义词匹配、完全错失、空 list 边界。
**Commit:** `feat(evals): add deterministic metrics with fuzzy matching`

### Task 1.12: 实现 LLM judge
**File — Create:** `packages/evals/voyager_evals/eric/judges/brief_judge.py`

- 读 `brief_rubric.md`，走 CopilotClaudeClient 但 `model="gpt-5"`（Copilot CLI 支持），schema = `BriefJudgement(score_per_dim, total, reasoning)`。
- **缓存**：key = `sha256(brief + rubric_version + judge_model)` → `judges/cache/<sha>.json`。
- 跑 3 次取 median 抗抖动。

**Test:** 给一个已知 brief + 固定 rubric，验证 score 在期待区间。
**Commit:** `feat(evals): add brief LLM judge with cache and median-3`

### Task 1.13: 写 run_eval.py 主程序
**File — Rewrite:** `packages/evals/voyager_evals/eric/run_eval.py`

伪码：
```
load fixtures (dev + holdout)
for each fixture:
    build EricState(topic=..., max_videos=1, transcripts injected via gold)
    compile build_data_graph(data_nodes=nodes_data_eval)
    compile build_llm_graph(client=CopilotClaudeClient())
    run both
    compute metrics
    append row
write reports/{iso}-{sha}/summary.md + report.html + scores.json + traces.jsonl
append row to eval_runs.sqlite
exit 0 if all thresholds met else 1
```

enforce cost_budget_usd + wall_clock_cap_seconds 提前中止。

**Run:** `uv run python -m voyager_evals.eric.run_eval --dry-run`（先 dry 不跑 LLM）
**Commit:** `feat(evals): implement eric run_eval entry point`

### Task 1.14: regression.py
**File — Create:** `packages/evals/voyager_evals/eric/regression.py`

`--last N` 读 eval_runs.sqlite 出 ASCII sparkline。简单即可。
**Commit:** `feat(evals): add regression sparkline`

### Task 1.15: 跑 baseline eval
**Run:** `uv run python -m voyager_evals.eric.run_eval --label baseline`
**Expected:** 会失败（P0 还没做）——预期记录 f1/recall/schema_validity 当前值。
**Commit:** `eval(eric): baseline report` + `git add reports/*-baseline/`

---

## 阶段 2 — P0 稳定性改造

### Task 2.1: P0.1 max_retries 1→3 + 指数退避
**File — Modify:** `packages/agents/voyager_agents/eric/copilot_client.py`

- 默认 `max_retries=3`
- 每次失败后 `await asyncio.sleep({1:1.0, 2:4.0, 3:10.0}[attempt])`
- `last_err` 带 traceback 原样存

**Test:** 用 monkey-patch `_invoke` 两次返 bad json 第三次 good，验证成功。
**Commit:** `fix(eric): bump retries to 3 with exponential backoff`

### Task 2.2: P0.2 json-repair fallback 链
**Run:** `cd packages/agents && uv add json-repair`

**Modify:** `copilot_client.py::complete` 解析段：

```python
import json_repair
for attempt in range(self._max_retries + 1):
    raw = await self._invoke(prompt)
    self._dump_raw(raw, attempt)  # 见 Task 2.4
    if schema is None:
        return raw
    body = _extract_json_text(raw)
    data, parse_err = None, None
    for loader in (json.loads, json_repair.loads):
        try:
            data = loader(body); break
        except Exception as e:
            parse_err = e
    if data is not None:
        try:
            return schema.model_validate(data)
        except ValidationError as e:
            last_err = e
    else:
        last_err = parse_err
    prompt = self._build_prompt(...) + f"\n\nPREVIOUS ATTEMPT FAILED: {last_err}..."
```

**Test:** 故意给带尾逗号 + 尾勺的 body，验证 json_repair 路径走通。
**Commit:** `fix(eric): json-repair fallback and extended retry chain`

### Task 2.3: P0.3 prefill + 硬规则 block + 确定性暗示
**Modify:** `copilot_client.py::_build_prompt`：

```python
_HARD_RULES = """HARD RULES:
- Your entire reply MUST start with `{` and end with `}`. NO prose, NO markdown fences.
- Use null for unknown fields; do NOT use "N/A" strings.
- No trailing commas. No comments.
- Be deterministic: prefer the most likely canonical phrasing; avoid creative variation.
"""
```

系统段追加 `_HARD_RULES`；`schema` 段保留占位，在 Task 2.5 换 TS 格式。

**Commit:** `fix(eric): add hard rules and determinism hints to prompt`

### Task 2.4: P0.4 原始 stdout 落盘
**Modify:** `copilot_client.py`：

- `__init__` 增 `log_dir: Path | None = None`（默认 `Path("logs/copilot")`）
- `_dump_raw(raw, attempt)` 按 `self._current_run_id` + node 名 + attempt 写 `logs/<run_id>/<node>_<attempt>.txt`
- `complete` 接受可选 `run_id` / `node_name` kwargs（由 nodes_llm 传入）

**Modify:** `nodes_llm.py` 每个 `client.complete(...)` 调用加 `run_id=state.run_id, node_name="extract_hooks"` 等。

**Test:** 调一次 stub，验证文件写出。
**Commit:** `feat(eric): persist raw CLI stdout for replay`

### Task 2.5: P0.5 schema → TypeScript interface
**Create:** `packages/agents/voyager_agents/eric/ts_schema.py`

```python
def pydantic_to_ts(model: type[BaseModel]) -> str:
    """Render Pydantic model as a compact TS interface string."""
    # 简化版：遍历 model_fields，输出 `interface X { foo: string; bar: number[]; }`
```

**Modify:** `_build_prompt` 的 schema 段：
```
RESPONSE FORMAT:
Return JSON matching this TypeScript interface exactly:

{pydantic_to_ts(schema)}
```

**Test:** `test_ts_schema.py` 三种常见结构（nested list、optional、literal）。
**Commit:** `fix(eric): replace JSON Schema with TypeScript interface in prompt`

### Task 2.6: P0 rerun eval
**Run:** `uv run python -m voyager_evals.eric.run_eval --label p0`
**Expected:** schema_validity_rate 显著抬升；f1/recall 小幅改善。
**Commit:** `eval(eric): P0 report` + `git add reports/*-p0/`

---

## 阶段 3 — P1 Claude 专属优化

### Task 3.1: P1.1 JSON 节点改 XML 输出（hooks / selling_points / cluster）
**Run:** `cd packages/agents && uv add lxml`

**Create:** `packages/agents/voyager_agents/eric/xml_parse.py`
- `parse_hooks_xml(text) -> HookExtraction`
- `parse_selling_points_xml(text) -> SellingPointExtraction`
- `parse_clusters_xml(text) -> ClusterOutput`
- 每个函数先 lxml `fromstring`（recover=True），失败回落到 json_repair JSON 分支。

**Modify:** `copilot_client.py::complete` 加 `output_format: Literal["json","xml"]="json"` 参数；XML 路径走 lxml 解析。

**Modify:** `nodes_llm.py` 三个 JSON 节点改 `output_format="xml"`，system prompt 改成：
```
Return ONLY:
<hooks>
  <hook>
    <text>...</text>
    <timestamp_s>12.3</timestamp_s>
    <confidence>0.8</confidence>
  </hook>
</hooks>
```

**Test:** `test_xml_parse.py` 含 emoji / 换行 / 空 list 三种 case。
**Commit:** `fix(eric): XML output for structured nodes with JSON fallback`

### Task 3.2: P1.2 `<scratchpad>` CoT
**Modify:** 三个抽取节点 system prompt 加：
```
Think step-by-step inside <scratchpad>...</scratchpad>. Only content OUTSIDE scratchpad
and INSIDE <hooks>/<selling_points>/<clusters> tags is parsed.
```
parser 先 strip `<scratchpad>.*?</scratchpad>` 再解析。
**Commit:** `fix(eric): use scratchpad tag for chain-of-thought`

### Task 3.3: P1.3 每节点 2-3 few-shot
**Create:** `packages/agents/voyager_agents/eric/prompts/`
- `extract_hooks.md`
- `extract_selling_points.md`
- `cluster_insights.md`

每个含 3 个 `<example>...</example>` 块，**必含一个 empty list 示例**。`nodes_llm.py` 读文件拼入 user prompt。

**Commit:** `fix(eric): add few-shot examples including empty-list edge case`

### Task 3.4: P1.4 Pydantic field_validator 收紧
**Modify:** `nodes_llm.py` models：

```python
from pydantic import field_validator
class Hook(BaseModel):
    hook_text: str = Field(min_length=3, max_length=200)
    timestamp_s: float = Field(ge=0, le=36000)
    confidence: float = Field(ge=0, le=1)
class HookExtraction(BaseModel):
    hooks: list[Hook] = Field(min_length=0, max_length=20)
# 同理 SellingPoint / Cluster
```

**Test:** 边界用例（负 confidence、超长 hook_text）应被拒。
**Commit:** `fix(eric): tighten pydantic validators on LLM outputs`

### Task 3.5: P1 rerun eval
**Run:** `uv run python -m voyager_evals.eric.run_eval --label p1`
**Expected:** hook_f1 ≥ 0.75、selling_point_recall ≥ 0.70、schema_validity ≥ 0.99；brief judge 尚未动 → 可能仍低（P4 再解）。
**Commit:** `eval(eric): P1 report` + `git add reports/*-p1/`

---

## 阶段 4 — Gate 判定与归档

### Task 4.1: 对比三份 report 生成 summary
**Create:** `packages/evals/voyager_evals/eric/reports/COMPARISON.md`
列 baseline / P0 / P1 三列每 metric delta。
**Commit:** `docs(evals): eric baseline vs P0 vs P1 comparison`

### Task 4.2: 判定 M1 exit
- 若 metric 全过 → 标记 M1.19 完成，更新 `docs/plans/2026-04-19-eric-build.md` 进度。
- 若 brief_judge 未过 → 触发 follow-up plan（P4 章节化），不在本 plan 范围。
**Commit:** `docs: mark Task 1.19 done (or note P4 followup)`

### Task 4.3: Push 到 DannyXXXXU/voyager
**Run:** `git push origin main`
**Expected:** 所有 commit 上云。

---

## 回顾清单

- [ ] 所有任务均 TDD（或至少 1 条断言）
- [ ] 每任务单独 commit，消息 conventional
- [ ] eval harness 可在 `unset AZURE_*` 下跑通（cloud creds 不依赖）
- [ ] holdout 5 条从未被 prompt 迭代见过
- [ ] reports/ 下三份产物归档
- [ ] Copilot judge 用 GPT-5，与 Claude agent 模型不同
- [ ] 单次 eval run 成本 < $0.50、耗时 < 15min

## 下一步（本 plan 外）

- P2 map-reduce（长 transcript）
- P3 cluster embedding + HDBSCAN
- P4 brief 章节化 + critic refill
- CI workflow `.github/workflows/agent-gate.yml`
- Mike 开工（M1 gate 过后）
