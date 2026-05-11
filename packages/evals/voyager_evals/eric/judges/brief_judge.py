"""LLM judge for Strategy Brief quality (median-of-3, cached).

Uses the Copilot CLI client with model=gpt-5 (a different model than the
agent's Claude). The rubric (brief_rubric.md) instructs the judge to return
JSON with five 1-5 scores and a total.

Cache key = sha256(model + rubric_version + brief_text). Re-runs are free
once a brief has been judged.
"""
from __future__ import annotations

import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

from voyager_agents.eric.copilot_client import CopilotCLIError, CopilotClaudeClient

from .cache import JudgeCache, JudgeCacheEntry, compute_key, sha256_text


_JUDGES_DIR = Path(__file__).resolve().parent
_RUBRIC_PATH = _JUDGES_DIR / "brief_rubric.md"
RUBRIC_VERSION = "1"

_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")


def _load_rubric() -> str:
    return _RUBRIC_PATH.read_text(encoding="utf-8")


def _parse_judge_response(raw: str) -> dict[str, float] | None:
    """Extract the JSON block from the judge's reply."""
    m = _JSON_BLOCK.search(raw)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    # Coerce known fields to float
    out: dict[str, float] = {}
    for k in (
        "specificity",
        "actionability",
        "evidence_grounding",
        "completeness",
        "consumability",
        "total",
    ):
        v = obj.get(k)
        if isinstance(v, (int, float)):
            out[k] = float(v)
    return out or None


async def judge_brief(
    brief_md: str,
    judge_model: str = "gpt-5",
    median_of: int = 3,
    cache_path: Path | None = None,
) -> dict:
    """Return a dict with median total + raw scores; cached by (model+rubric+brief).

    Returns
    -------
    {
        "overall_median": float,        # gate metric
        "scores_runs": [dict, ...],     # per-run dicts of 5 dims + total
        "raw_responses": [str, ...],
        "cached": bool,
    }
    On total parse failure (after all retries), overall_median = 0.0 and
    raw_responses include the offending output.
    """
    if not brief_md.strip():
        return {
            "overall_median": 0.0,
            "scores_runs": [],
            "raw_responses": [],
            "cached": False,
            "error": "empty_brief",
        }

    cache = JudgeCache(cache_path) if cache_path else None
    key = compute_key(judge_model, RUBRIC_VERSION, brief_md)
    if cache:
        hit = cache.get(key)
        if hit:
            return {
                "overall_median": hit.get("overall_median", 0.0),
                "scores_runs": hit.get("scores", {}).get("runs", []),
                "raw_responses": hit.get("raw_responses", []),
                "cached": True,
            }

    rubric = _load_rubric()
    system = "You are an expert evaluator. Follow the rubric exactly. Return only JSON."
    user = (
        f"RUBRIC:\n{rubric}\n\n"
        f"STRATEGY_BRIEF_TO_SCORE:\n{brief_md}\n\n"
        "Return ONLY the JSON object specified in the rubric."
    )

    # Judge runs use the Copilot CLI client w/o pydantic schema (rubric defines shape).
    client = CopilotClaudeClient(model=judge_model, max_retries=1, timeout_s=180)

    raw_responses: list[str] = []
    scores_runs: list[dict[str, float]] = []
    totals: list[float] = []
    for _ in range(median_of):
        try:
            raw = await client.complete(system=system, user=user, schema=None)
        except CopilotCLIError as e:
            raw_responses.append(f"__error__: {e}")
            continue
        raw_str = raw if isinstance(raw, str) else str(raw)
        raw_responses.append(raw_str)
        parsed = _parse_judge_response(raw_str)
        if parsed is None:
            continue
        scores_runs.append(parsed)
        total = parsed.get("total")
        if total is None:
            # Compute total as mean of dims
            dims = [
                parsed.get(k)
                for k in (
                    "specificity",
                    "actionability",
                    "evidence_grounding",
                    "completeness",
                    "consumability",
                )
                if parsed.get(k) is not None
            ]
            if dims:
                total = sum(dims) / len(dims)
        if isinstance(total, (int, float)):
            totals.append(float(total))

    overall_median = float(statistics.median(totals)) if totals else 0.0

    if cache:
        cache.put(
            JudgeCacheEntry(
                key=key,
                model=judge_model,
                rubric_version=RUBRIC_VERSION,
                brief_sha256=sha256_text(brief_md),
                scores={"runs": scores_runs},
                overall_median=overall_median,
                raw_responses=raw_responses,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )

    return {
        "overall_median": overall_median,
        "scores_runs": scores_runs,
        "raw_responses": raw_responses,
        "cached": False,
    }


__all__ = ["judge_brief", "RUBRIC_VERSION"]
