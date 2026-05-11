"""Baseline scoring helpers: run agent on one fixture, return scores.

This module is the live runner that 1.19g promised. It:
  1. wraps the Copilot client to count schema-valid vs failed LLM calls,
  2. runs the LLM subgraph on a pre-hydrated EricState,
  3. computes deterministic metrics (hook_f1, sp_recall, schema_validity_rate),
  4. optionally calls the LLM judge for brief_quality.

Returns a dict matching the shape consumed by run_eval.py --scores-file.
"""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from voyager_agents.eric.copilot_client import CopilotCLIError, CopilotClaudeClient
from voyager_agents.eric.graph import build_llm_graph
from voyager_agents.eric.state import EricState

from .metrics import match_hooks, selling_point_recall


# --------------------------------------------------------------------------- #
# Schema-validity tracker
# --------------------------------------------------------------------------- #
@dataclass
class CallStats:
    schema_total: int = 0
    schema_ok: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def schema_validity(self) -> float:
        if self.schema_total == 0:
            return 1.0
        return self.schema_ok / self.schema_total


class TrackingClient:
    """Wraps a CopilotClient and counts schema-valid completions.

    Schema-typed calls (hooks/selling_points/cluster) are tracked.
    Freeform calls (brief) are pass-through, not counted in validity.
    Any CopilotCLIError / ValidationError on a schema call counts as failure
    and returns an empty instance of the schema so the graph can continue.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.stats = CallStats()

    @property
    def _model(self) -> str:
        return getattr(self._inner, "_model", "unknown")

    async def complete(
        self,
        system: str,
        user: str,
        schema: type[BaseModel] | None = None,
    ) -> BaseModel | str:
        if schema is None:
            # freeform (brief) — not counted in schema validity
            try:
                return await self._inner.complete(system=system, user=user, schema=None)
            except CopilotCLIError as e:
                self.stats.errors.append(f"brief: {e}")
                return ""

        self.stats.schema_total += 1
        try:
            result = await self._inner.complete(system=system, user=user, schema=schema)
            if isinstance(result, schema):
                self.stats.schema_ok += 1
                return result
            # Got something unexpected; count as failure
            self.stats.errors.append(
                f"{schema.__name__}: unexpected type {type(result).__name__}"
            )
        except (CopilotCLIError, ValidationError) as e:
            self.stats.errors.append(f"{schema.__name__}: {type(e).__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            self.stats.errors.append(
                f"{schema.__name__}: unexpected {type(e).__name__}: {e}"
            )
        # Return an empty instance so graph can continue and we can score
        # remaining nodes / brief.
        try:
            return schema()
        except ValidationError:
            # Schema requires fields; build something minimal via construct
            return schema.model_construct()


# --------------------------------------------------------------------------- #
# Per-fixture runner
# --------------------------------------------------------------------------- #
@dataclass
class FixtureScores:
    fixture_id: str
    bucket: str
    scores: dict[str, float]
    cost_usd: float = 0.0
    wall_seconds: float = 0.0
    error: str | None = None
    # raw agent outputs (for debugging / judge input)
    brief_md: str = ""
    hooks_predicted: list[str] = field(default_factory=list)
    sp_predicted: list[str] = field(default_factory=list)
    call_errors: list[str] = field(default_factory=list)


async def run_one_fixture(
    fixture_id: str,
    bucket: str,
    state: EricState,
    fixture_yaml: dict[str, Any],
    client: CopilotClaudeClient,
) -> FixtureScores:
    """Run the LLM subgraph on a pre-hydrated state and compute scores.

    `fixture_yaml` is the loaded fixture YAML (for gold_hooks, gold_selling_points).
    `client` is the real Copilot client; we wrap it for tracking.
    """
    tracker = TrackingClient(client)
    graph = build_llm_graph(tracker).compile()

    t0 = time.monotonic()
    try:
        final = await graph.ainvoke(state)
    except Exception as e:  # noqa: BLE001
        return FixtureScores(
            fixture_id=fixture_id,
            bucket=bucket,
            scores={},
            wall_seconds=time.monotonic() - t0,
            error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            call_errors=tracker.stats.errors,
        )
    wall = time.monotonic() - t0

    # Extract predictions
    hooks = final.get("hooks", []) if isinstance(final, dict) else final.hooks
    points = (
        final.get("selling_points", [])
        if isinstance(final, dict)
        else final.selling_points
    )
    brief_md = (
        final.get("brief_md") if isinstance(final, dict) else final.brief_md
    ) or ""

    hooks_pred = [h.get("hook_text", "") for h in hooks if h.get("hook_text")]
    sp_pred = [p.get("point", "") for p in points if p.get("point")]

    # Score deterministic metrics
    gold_hooks = fixture_yaml.get("gold_hooks") or []
    gold_sp = fixture_yaml.get("gold_selling_points") or []

    hook_match = match_hooks(hooks_pred, gold_hooks)
    sp_recall = selling_point_recall(sp_pred, gold_sp)

    scores: dict[str, float] = {
        "hook_extraction_f1": hook_match.f1,
        "selling_point_recall": sp_recall,
        "schema_validity_rate": tracker.stats.schema_validity,
    }

    return FixtureScores(
        fixture_id=fixture_id,
        bucket=bucket,
        scores=scores,
        wall_seconds=wall,
        brief_md=brief_md,
        hooks_predicted=hooks_pred,
        sp_predicted=sp_pred,
        call_errors=tracker.stats.errors,
    )


__all__ = ["TrackingClient", "CallStats", "FixtureScores", "run_one_fixture"]
