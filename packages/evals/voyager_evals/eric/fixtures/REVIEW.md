# Eric Fixtures — 打标指引

读这一份就够。

## 0. 你要做什么

给 5 个 holdout 视频手工写 `gold_hooks` + `gold_selling_points`。这 5 个 fixture 是 Eric agent **永远看不到的考试题**，agent 跑出来的结果会和你写的金标对照，所以必须你亲手填，不能让 agent 自己 draft。

另外，过一遍 15 个 dev fixtures（agent 自动 draft 的），改对错，把 `review_status` 从 `pending` 改成 `approved`。

## 1. 文件在哪

```
packages/evals/voyager_evals/eric/fixtures/
├── dev-food-01.yaml          ← agent draft，你 review
├── dev-food-01.brief.md      ← brief 也 review 一下
├── ...（15 个 dev）
├── hold-food-01.yaml         ← 空 stub，你从零填
├── hold-food-01.transcript.txt  ← 配套 transcript（只读参考）
├── ...（5 个 holdout）
└── REVIEW.md                 ← 本文件
```

## 2. Holdout 打标流程（5 个，每个 ~15 分钟）

### Step 1：读 transcript

打开 `hold-xxx-01.transcript.txt`，通读一遍。这是 Whisper 转的英文稿，可能有错字，但够用。

### Step 2：标 hooks（钩子）

**定义**：视频里抓人眼球的具体句子 / 画面描述 / 反差点。一般是开头 30 秒 + 转场处。

**标准**：
- 必须是 transcript 里**真实出现的原话**或紧贴原话的描述
- 4-12 个之间（太少说明视频弱，太多说明你在凑）
- 每个带 `timestamp_s`（看 transcript JSON 里 segments 的时间，没有就估）
- `aliases` 写 1-3 个改写变体，给 agent F1 评分留余地

**例子**（dev-food-01 已 draft 的样式）：
```yaml
gold_hooks:
  - text: "world's spiciest hot pot challenge"
    aliases:
      - "extreme spicy hot pot"
      - "death-level spice challenge"
    timestamp_s: 8.5
  - text: "Chinese Trump look-alike serving food"
    aliases: ["Trump impersonator restaurant"]
    timestamp_s: 142.0
```

### Step 3：标 selling_points（卖点）

**定义**：抽象一层，"为什么观众会看完 / 转发"的理由。不是原话，是你提炼的价值点。

**标准**：
- 5-10 个
- 抽象层次：比 hook 高一级，比"中国旅游真好"低一级
- 不要堆形容词，要可执行的差异点

**例子**：
```yaml
gold_selling_points:
  - text: "extreme food challenge with measurable danger"
    aliases: ["spice level escalation", "physical reaction shots"]
  - text: "local guide as cultural translator"
    aliases: ["insider access", "translator-host dynamic"]
  - text: "cyberpunk city aesthetic at night"
    aliases: ["neon urban visuals"]
```

### Step 4：改 meta

```yaml
_meta:
  drafted_by: human
  drafted_at_utc: 2026-04-27T15:00:00Z   # 改成你打标的时间
  review_status: approved                 # stub → approved
  labeler: danny
```

### Step 5：保存，下一个

## 3. Dev fixtures review 流程（15 个，每个 ~5 分钟）

agent 已经 draft 好了，你只需要：

1. 打开 `dev-xxx-NN.yaml`
2. 扫一遍 hooks：明显错的删掉，缺的补一两条
3. 扫一遍 selling_points：抽象层次不对的改写
4. 打开 `dev-xxx-NN.brief.md`：读一遍，能不能给 Mike 用？不能就改
5. **已知缺陷**：`timestamp_s` 全是 0.0 — 暂时不用管，P0 阶段会修代码后重 draft
6. 改 meta：
   ```yaml
   _meta:
     review_status: approved   # pending → approved
     reviewed_by: danny
     reviewed_at_utc: 2026-04-27T...
   ```

如果某个 dev fixture agent 错得离谱（hooks 全是幻觉之类），把 `review_status` 标 `rejected`，写个 `reject_reason` 字段，我会重新跑那一条。

## 4. 进度追踪

打完一个就 commit 一次，方便回滚：

```
git add packages/evals/voyager_evals/eric/fixtures/hold-food-01.yaml
git commit -m "labels(eric): hand-label hold-food-01"
git push
```

或者一次性全打完再 commit 也行。

## 5. 完事之后

跟我说一声"打完了"，我跑 baseline eval 看 agent 当前分数 vs 你的金标。
