"""Deterministic metrics for Eric eval.

Implemented Task 1.19f (2026-04-22):
- semantic_match via sentence-transformers cosine >= threshold
- match_hooks: greedy 1:1 match predicted→gold (text + aliases)
- selling_point_recall: fraction of gold covered by any predicted
- schema_validity: fraction of outputs that parse into a pydantic model
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


def _normalize(s: str) -> str:
    return " ".join(s.lower().strip().split())


def _embed(texts: Sequence[str]):
    # returns (N, D) numpy array, L2-normalized
    import numpy as np  # noqa: WPS433

    texts = [t if t else " " for t in texts]
    emb = _get_embedder().encode(
        list(texts), convert_to_numpy=True, normalize_embeddings=True
    )
    return np.asarray(emb)


def semantic_match(
    a: str,
    b_candidates: Sequence[str],
    threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
) -> tuple[int, float] | None:
    """Return (best_index, cos_sim) if any candidate >= threshold, else None.

    Short-circuits on exact normalized match (cos sim = 1.0).
    """
    if not b_candidates:
        return None
    a_n = _normalize(a)
    for i, b in enumerate(b_candidates):
        if a_n and a_n == _normalize(b):
            return (i, 1.0)

    import numpy as np  # noqa: WPS433

    emb = _embed([a, *b_candidates])
    a_vec = emb[0]
    b_mat = emb[1:]
    sims = b_mat @ a_vec  # cosine since normalized
    best = int(np.argmax(sims))
    best_sim = float(sims[best])
    if best_sim >= threshold:
        return (best, best_sim)
    return None


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


def _gold_surfaces(gold_item: dict) -> list[str]:
    """For a gold hook/selling-point dict, return text + aliases as list."""
    if isinstance(gold_item, str):
        return [gold_item]
    text = gold_item.get("text", "")
    aliases = gold_item.get("aliases", []) or []
    out = [text] if text else []
    out.extend(a for a in aliases if a)
    return out or [""]


def match_hooks(
    predicted: Sequence[str],
    gold: Sequence[dict],
    threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
) -> MatchResult:
    """Greedy 1:1 match predicted→gold via max cosine over (text + aliases).

    Algorithm:
      1. For each (pred_i, gold_j), compute max cos sim over gold_j's surfaces.
      2. Sort all pairs by sim desc; greedily assign if neither endpoint taken.
      3. tp = assigned pairs with sim>=threshold; fp = unmatched preds;
         fn = unmatched golds.
    """
    result = MatchResult()
    n_pred = len(predicted)
    n_gold = len(gold)
    if n_pred == 0 and n_gold == 0:
        return result
    if n_pred == 0:
        result.fn = n_gold
        return result
    if n_gold == 0:
        result.fp = n_pred
        return result

    # Build a flat list of (gold_idx, surface) to batch-embed once.
    gold_surfaces: list[list[str]] = [_gold_surfaces(g) for g in gold]

    # Compute cos sim matrix between predicted[i] and surfaces of gold[j];
    # take max over each gold's surface list.
    import numpy as np  # noqa: WPS433

    all_surfaces = [s for sl in gold_surfaces for s in sl]
    pred_list = list(predicted)
    emb = _embed(pred_list + all_surfaces)
    pred_mat = emb[: len(pred_list)]
    surf_mat = emb[len(pred_list) :]
    sim_flat = pred_mat @ surf_mat.T  # (P, S_total)

    # Reduce to (P, G) by max over each gold's surface group.
    sim_pg = np.zeros((n_pred, n_gold), dtype=float)
    offset = 0
    for j, sl in enumerate(gold_surfaces):
        k = len(sl)
        if k > 0:
            sim_pg[:, j] = sim_flat[:, offset : offset + k].max(axis=1)
        offset += k

    # Greedy assignment by descending sim.
    pairs = [
        (sim_pg[i, j], i, j) for i in range(n_pred) for j in range(n_gold)
    ]
    pairs.sort(key=lambda x: x[0], reverse=True)
    taken_p: set[int] = set()
    taken_g: set[int] = set()
    for sim, i, j in pairs:
        if i in taken_p or j in taken_g:
            continue
        if sim >= threshold:
            taken_p.add(i)
            taken_g.add(j)
            result.tp += 1
            result.matched_pairs.append((i, j, float(sim)))

    result.fp = n_pred - len(taken_p)
    result.fn = n_gold - len(taken_g)
    return result


def selling_point_recall(
    predicted: Sequence[str],
    gold: Sequence[dict],
    threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
) -> float:
    """Fraction of gold selling points covered by any predicted (recall-only).

    Eric over-producing selling points is not penalized (Mike filters
    downstream). Under-producing is the failure mode.
    """
    if not gold:
        return 1.0
    if not predicted:
        return 0.0

    import numpy as np  # noqa: WPS433

    gold_surfaces = [_gold_surfaces(g) for g in gold]
    all_surfaces = [s for sl in gold_surfaces for s in sl]
    pred_list = list(predicted)
    emb = _embed(pred_list + all_surfaces)
    pred_mat = emb[: len(pred_list)]
    surf_mat = emb[len(pred_list) :]
    sim_flat = pred_mat @ surf_mat.T  # (P, S_total)

    covered = 0
    offset = 0
    for sl in gold_surfaces:
        k = len(sl)
        # max over (surfaces, predicted) — gold_j covered if any predicted >= threshold
        if k > 0 and sim_flat[:, offset : offset + k].max() >= threshold:
            covered += 1
        offset += k
    return covered / len(gold)


# --- schema validity ----------------------------------------------------------

def schema_validity(
    outputs: Iterable[dict],
    pydantic_model,  # type: ignore[no-untyped-def]
) -> float:
    """Fraction of outputs that parse cleanly into the target pydantic model."""
    outputs = list(outputs)
    if not outputs:
        return 1.0
    from pydantic import ValidationError  # noqa: WPS433

    ok = 0
    for o in outputs:
        try:
            pydantic_model.model_validate(o)
            ok += 1
        except (ValidationError, Exception):  # noqa: BLE001
            continue
    return ok / len(outputs)
