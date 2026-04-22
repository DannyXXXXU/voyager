# Eric 输出稳定性研究 (2026-04-21)

**背景**：Eric 经 Copilot CLI 调 Claude，不能设 temperature / response_format / 强制 tool-use，只能靠 prompt + 解析侧做功夫。
**目标**：JSON 解析成功率从当前估计 ~85-92% 提到 99%+；brief 必含全部章节且长度合格。

---

## 现状硬伤（直接读 nodes_llm.py + copilot_client.py 看出）

1. `max_retries=1`，JSON 失败只给一次重试机会
2. `node_write_brief` 无 schema，返回裸字符串 → 长度/章节全靠模型心情
3. 全量 transcript 塞 prompt → 30 分钟视频可能触发 CLI 截断或 "lost in middle"
4. `node_cluster_insights` 用 `str(payload)`（Python dict repr）而非 JSON 传给模型
5. prompt 里塞完整 `model_json_schema()` — 冗长嵌套淹没指令
6. 零 few-shot，纯 zero-shot
7. 没做输出长度/结构守门
8. 没保留原始 stdout 日志 — 失败后无法 replay/diff
9. JSON 解析链路太朴素：失败直接挂，没用 json-repair 兜底
10. 无 prefill 指令（"reply starts with `{`"）

---

## 行动清单（按 ROI 排序，直接落地）

### P0 立刻做（工作量小、收益大）

- [ ] **max_retries 1 → 3**，加指数退避（1s / 4s / 10s）
- [ ] **加 json-repair 兜底**：`uv add json-repair`，解析链路改为 `json.loads → json_repair.loads → Pydantic validate → 带错误 re-prompt`
- [ ] **每个 JSON 节点 prompt 加 prefill 指令**："Your entire reply MUST start with the character `{` and end with `}`. No prose, no markdown fences, no explanations."
- [ ] **硬规则 block**：禁用 markdown fence、禁用尾逗号、禁用 N/A 占位、未知字段用 null
- [ ] **CLI stdout 原始日志**：每次调用落盘到 `logs/<run_id>/<node>_<attempt>.txt`，失败能 replay
- [ ] **prompt 里的 schema 从 `model_json_schema()` 换成 TypeScript interface 风格**（更紧凑，模型理解更好）
- [ ] **加确定性暗示**："Be deterministic; prefer the most likely phrasing; do not introduce creative variation."

### P1 结构级改造（Claude 专属加成）

- [ ] **改用 XML 标签输出**（Claude 强项）：`<hooks><hook><text>...</text></hook></hooks>`
  - 规避 transcript 中引号/换行/emoji 导致的 JSON 解析失败
  - 解析用 lxml，比 balance-brace 稳
  - JSON 作为 fallback
- [ ] **Chain-of-thought 走 `<scratchpad>` 标签**，输出只取 `<json>` / `<hooks>` 块
- [ ] **每节点加 2-3 个 few-shot 示例**（放在 `<example>` 标签里），**必须包含一个 empty list 边界例子**
- [ ] **每个节点都用 Pydantic field_validator**：timestamp 正则、score ge=0 le=1、text min/max_length、list min/max_length

### P2 长 transcript 处理（map-reduce）

- [ ] **chunking**：按 3 分钟窗口切，300 token overlap，按句子边界切不切词
- [ ] **extract_hooks / extract_selling_points 改 map-reduce**：
  - map：每个 chunk 独立抽取（用 LangGraph `Send` 并发）
  - reduce：rapidfuzz `token_set_ratio >= 88` 去重 → LLM rerank 选 top-K
- [ ] 每个 chunk prompt 前注入 `[chunk i/N, starts at mm:ss]` 保时间戳

### P3 cluster_insights 改架构

- [ ] **放弃 LLM 裸聚类**，改 embedding + HDBSCAN
  - 用 Azure OpenAI `text-embedding-3-small` 或本地 `bge-small`
  - HDBSCAN/k-means（k 用 silhouette 选）
  - **LLM 只负责给 cluster 起名 + 写 summary**（这任务 LLM 很稳）
- [ ] 如坚持纯 LLM：跑 3 次 self-consistency，选 pairwise label 重合度最高那次

### P4 write_brief 完整性保证

- [ ] **固定 6 个 H2 章节 skeleton**：Executive Summary / Audience / Top Hooks / Positioning / Content Plan / Risks
- [ ] **section-by-section 生成**：每章单独一次 LLM 调用，带全局 context + 上文已写章节
- [ ] **Pydantic 验证器**：
  - 正则检查 6 个 H2 header 全部存在
  - 每节 ≥100 词，≤300 词
- [ ] **critic pass**：写完后一次 LLM 调用返回 JSON `{missing:[], thin:[]}`，只 refill 被标出的章节（最多 2 轮）

### P5 可选增强

- [ ] write_brief 用 prompt cache（transcript chunks 跨 4 个节点复用） — 只在 Copilot CLI 支持 cache-control 时
- [ ] 关键节点加 self-consistency N=3
- [ ] 把 JSON 节点改直接走 Anthropic API（解锁 response_format + tool-use），write_brief 保留 Copilot — 超出"仅 CLI"约束，留作备选

---

## 关键引用

- Anthropic XML tags: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/use-xml-tags
- Anthropic prefill: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/prefill-claudes-response
- Anthropic CoT scratchpad: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/chain-of-thought
- json-repair: https://github.com/mangiucugna/json_repair
- LangGraph Send API（并发 map）: https://langchain-ai.github.io/langgraph/how-tos/map-reduce/
- LangChain OutputFixingParser: https://python.langchain.com/docs/how_to/output_parser_fixing/
- Self-consistency (Wang 2022): https://arxiv.org/abs/2203.11171
- Lost in the Middle (Liu 2024): https://arxiv.org/abs/2307.03172
- instructor retrying: https://python.useinstructor.com/concepts/retrying/

---

## 建议的落地顺序（增量提交，每步可跑 eval 对比）

1. P0 全部（半天）—— 先看 baseline 改善到哪
2. P1 XML + few-shot（一天）—— 通常这里就能到 99%+ 解析率
3. P4 brief 章节化（半天）—— 解决 brief 完整性
4. P2 map-reduce（一天）—— 长视频稳定性
5. P3 cluster embedding 改造（半天）—— 聚类一致性
6. P5 按需
