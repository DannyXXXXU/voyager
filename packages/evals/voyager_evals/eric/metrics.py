"""Deterministic metrics for Eric eval.

Phase 1.3 scaffold — implementations land in Task 1.9.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

# --- fuzzy string match ------------------------------------------------------

# Default cosine threshold for sentence-transformers match.
# >= 0.75 counts as the same concept for hook/selling-point matching.
DEFAULT_SEMANTIC_THRESHOLD: float = 0.75

# Lazy singleton so importing metrics.py doesn't download a 400MB model.
_EMBEDDER = None


def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        from sentence_transformers import SentenceTransformer  # noqa: WPS433

        _EMBEDDER = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _EMBEDDER


def semantic_match(
    a: str,
    b_candidates: Sequence[str],
    threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
) -> tuple[int, float] | None:
    """Return (best_index, cos_sim) if any candidate >= threshold, else None.

    Not implemented yet — Task 1.9.
    """
    raise NotImplementedError("semantic_match — Task 1.9")


# --- hook / selling-point F1 --------------------------------------------------

@dataclass
class MatchResult:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    matched_pairs: list[tuple[int, int, float]] = field(default_factory=list)

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


def match_hooks(
    predicted: Sequence[str],
    gold: Sequence[dict],  # each: {text, aliases:[...]}
    threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
) -> MatchResult:
    """Hungarian-style 1:1 match predicted→gold via semantic_match.

    Each gold hook's aliases count as equivalent surface forms — match against
    text + aliases, take max cos sim.

    Not implemented yet — Task 1.9.
    """
    raise NotImplementedError("match_hooks — Task 1.9")


def selling_point_recall(
    predicted: Sequence[str],
    gold: Sequence[dict],
    threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
) -> float:
    """Fraction of gold selling points that have a predicted semantic match.

    Recall-only metric — Eric over-producing selling points is not penalized
    (downstream Mike filters). Under-producing is the failure mode.
    """
    raise NotImplementedError("selling_point_recall — Task 1.9")


# --- schema validity ----------------------------------------------------------

def schema_validity(
    outputs: Iterable[dict],
    pydantic_model,  # type: ignore[no-untyped-def]
) -> float:
    """Fraction of outputs that parse cleanly into the target pydantic model."""
    raise NotImplementedError("schema_validity — Task 1.9")
