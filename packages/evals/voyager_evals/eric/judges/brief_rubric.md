# Strategy Brief Quality Rubric (v1)

You are an independent evaluator scoring a Strategy Brief produced by the Eric agent.
The brief is meant to be consumed by Mike (video editor) to plan an overseas-growth
travel video about China.

Score each of the 5 dimensions on a 1-5 integer scale. Then return the JSON:

```
{
  "specificity": <1-5>,
  "actionability": <1-5>,
  "evidence_grounding": <1-5>,
  "completeness": <1-5>,
  "consumability": <1-5>,
  "total": <average, 1 decimal>,
  "reasoning": "<=3 sentences justifying the lowest-scored dimension"
}
```

## Dimensions

1. **specificity** — Concrete places/dishes/angles vs vague generalities.
   1 = generic ("beautiful scenery"); 5 = specific ("Leshan Giant Buddha sunrise, 20min boat ride from Taoyuan pier").

2. **actionability** — Mike can turn this into shot-list / script directly.
   1 = pure analysis no guidance; 5 = names exact hooks, selling points, pacing, shot types.

3. **evidence_grounding** — Claims tied to observed hooks / comments / competitor data.
   1 = all opinion; 5 = every claim cites a source hook or comment theme.

4. **completeness** — All six sections present and non-trivial: Executive Summary, Audience,
   Top Hooks, Positioning, Content Plan, Risks.
   1 = <3 sections or >=3 are <50 words; 5 = all six sections >=100 words.

3 is the minimum "usable" threshold per dimension; 4.0 total is the gate.

## Rules for the judge model

- Do not reward verbosity; reward density.
- If the brief is blank or under 300 words total, total <= 2.0 regardless of dimensions.
- If any section is completely missing, cap completeness at 2.
- Be deterministic: prefer consistent scoring across re-runs.

## Judge meta

- Judge model: Copilot GPT-5 (distinct from the agent's Claude)
- Rubric version: 1
- Cache key: sha256(brief_text + rubric_version + judge_model)
- Median of 3 runs is the final score (abs output).
