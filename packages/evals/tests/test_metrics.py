"""Tests for voyager_evals.eric.metrics.

Uses monkeypatching on `_embed` so we don't pull the 400MB
sentence-transformers model during CI.
"""
from __future__ import annotations

import numpy as np
import pytest
from pydantic import BaseModel

from voyager_evals.eric import metrics as M


# --- fake embedder ------------------------------------------------------------

def _fake_embed_factory(mapping: dict[str, list[float]]):
    """Return an _embed replacement that looks up vectors by normalized text."""
    dim = len(next(iter(mapping.values())))

    def _fake_embed(texts):
        out = np.zeros((len(texts), dim), dtype=float)
        for i, t in enumerate(texts):
            key = " ".join((t or "").lower().strip().split())
            vec = mapping.get(key)
            if vec is None:
                # orthogonal-ish random-but-deterministic via hash
                h = abs(hash(key)) % (10**8)
                rng = np.random.default_rng(h)
                v = rng.standard_normal(dim)
                v /= np.linalg.norm(v) or 1.0
                out[i] = v
            else:
                v = np.asarray(vec, dtype=float)
                v /= np.linalg.norm(v) or 1.0
                out[i] = v
        return out

    return _fake_embed


# --- semantic_match -----------------------------------------------------------

def test_semantic_match_exact_shortcircuit(monkeypatch):
    # Even with no embedder, exact normalized match must hit.
    def _boom(_):
        raise AssertionError("should not embed on exact match")

    monkeypatch.setattr(M, "_embed", _boom)
    res = M.semantic_match("Hot pot is spicy", ["hot pot is spicy", "other"])
    assert res == (0, 1.0)


def test_semantic_match_above_threshold(monkeypatch):
    mapping = {
        "spicy hotpot": [1.0, 0.0],
        "fiery chongqing hotpot": [0.95, 0.05],
        "great wall hike": [0.0, 1.0],
    }
    monkeypatch.setattr(M, "_embed", _fake_embed_factory(mapping))
    res = M.semantic_match(
        "spicy hotpot",
        ["fiery chongqing hotpot", "great wall hike"],
        threshold=0.75,
    )
    assert res is not None
    idx, sim = res
    assert idx == 0
    assert sim > 0.75


def test_semantic_match_below_threshold(monkeypatch):
    mapping = {
        "spicy hotpot": [1.0, 0.0],
        "great wall hike": [0.0, 1.0],
    }
    monkeypatch.setattr(M, "_embed", _fake_embed_factory(mapping))
    assert M.semantic_match("spicy hotpot", ["great wall hike"], threshold=0.75) is None


def test_semantic_match_empty_candidates():
    assert M.semantic_match("anything", []) is None


# --- match_hooks --------------------------------------------------------------

def test_match_hooks_perfect_via_aliases(monkeypatch):
    mapping = {
        "you won't believe this food": [1.0, 0.0, 0.0],
        "most insane street food": [0.98, 0.02, 0.0],
        "cheapest meal in china": [0.0, 1.0, 0.0],
        "best budget eats": [0.02, 0.98, 0.0],
        "third thing": [0.0, 0.0, 1.0],
    }
    monkeypatch.setattr(M, "_embed", _fake_embed_factory(mapping))
    predicted = ["most insane street food", "best budget eats"]
    gold = [
        {"text": "you won't believe this food", "aliases": []},
        {"text": "cheapest meal in china", "aliases": ["budget eats in china"]},
    ]
    r = M.match_hooks(predicted, gold, threshold=0.75)
    assert r.tp == 2
    assert r.fp == 0
    assert r.fn == 0
    assert r.f1 == pytest.approx(1.0)


def test_match_hooks_partial(monkeypatch):
    mapping = {
        "a": [1.0, 0.0, 0.0],
        "a-similar": [0.99, 0.01, 0.0],
        "b": [0.0, 1.0, 0.0],
        "c-far": [0.0, 0.0, 1.0],
    }
    monkeypatch.setattr(M, "_embed", _fake_embed_factory(mapping))
    # 2 predicted, 2 gold; only one pair matches
    predicted = ["a-similar", "c-far"]
    gold = [{"text": "a", "aliases": []}, {"text": "b", "aliases": []}]
    r = M.match_hooks(predicted, gold, threshold=0.75)
    assert r.tp == 1
    assert r.fp == 1
    assert r.fn == 1


def test_match_hooks_empty_both():
    r = M.match_hooks([], [])
    assert r.tp == 0 and r.fp == 0 and r.fn == 0
    assert r.f1 == 0.0


def test_match_hooks_empty_predicted():
    r = M.match_hooks([], [{"text": "x", "aliases": []}])
    assert r.fn == 1 and r.tp == 0 and r.fp == 0


def test_match_hooks_empty_gold():
    r = M.match_hooks(["x"], [])
    assert r.fp == 1 and r.tp == 0 and r.fn == 0


def test_match_hooks_greedy_assignment(monkeypatch):
    # Two predicted both closer to gold_0; greedy must not double-book.
    mapping = {
        "g0": [1.0, 0.0],
        "g1": [0.0, 1.0],
        "p0": [0.99, 0.01],  # best for g0
        "p1": [0.95, 0.05],  # also closer to g0 but must get g1 (0.05 sim) → fp
    }
    monkeypatch.setattr(M, "_embed", _fake_embed_factory(mapping))
    gold = [{"text": "g0", "aliases": []}, {"text": "g1", "aliases": []}]
    r = M.match_hooks(["p0", "p1"], gold, threshold=0.75)
    # p0→g0 assigned; p1 has no remaining gold above threshold → fp+fn
    assert r.tp == 1
    assert r.fp == 1
    assert r.fn == 1


# --- selling_point_recall -----------------------------------------------------

def test_selling_point_recall_full(monkeypatch):
    mapping = {
        "hotpot is spicy": [1.0, 0.0],
        "spicy hotpot": [0.98, 0.02],
        "great scenery": [0.0, 1.0],
        "beautiful views": [0.02, 0.98],
    }
    monkeypatch.setattr(M, "_embed", _fake_embed_factory(mapping))
    predicted = ["spicy hotpot", "beautiful views"]
    gold = [
        {"text": "hotpot is spicy", "aliases": []},
        {"text": "great scenery", "aliases": []},
    ]
    assert M.selling_point_recall(predicted, gold) == pytest.approx(1.0)


def test_selling_point_recall_half(monkeypatch):
    mapping = {
        "hotpot is spicy": [1.0, 0.0],
        "spicy hotpot": [0.98, 0.02],
        "great scenery": [0.0, 1.0],
    }
    monkeypatch.setattr(M, "_embed", _fake_embed_factory(mapping))
    predicted = ["spicy hotpot"]
    gold = [
        {"text": "hotpot is spicy", "aliases": []},
        {"text": "great scenery", "aliases": []},
    ]
    assert M.selling_point_recall(predicted, gold) == pytest.approx(0.5)


def test_selling_point_recall_empty_gold():
    assert M.selling_point_recall(["anything"], []) == 1.0


def test_selling_point_recall_empty_predicted():
    assert M.selling_point_recall([], [{"text": "x", "aliases": []}]) == 0.0


# --- schema_validity ----------------------------------------------------------

class _FakeBrief(BaseModel):
    title: str
    score: int


def test_schema_validity_all_pass():
    outs = [{"title": "a", "score": 1}, {"title": "b", "score": 2}]
    assert M.schema_validity(outs, _FakeBrief) == 1.0


def test_schema_validity_partial():
    outs = [
        {"title": "a", "score": 1},
        {"title": "b"},  # missing score
        {"title": "c", "score": "not-an-int-and-not-coercible"},
    ]
    # pydantic v2 coerces "3" to 3 but not arbitrary strings
    rate = M.schema_validity(outs, _FakeBrief)
    assert 0.0 < rate < 1.0


def test_schema_validity_empty():
    assert M.schema_validity([], _FakeBrief) == 1.0
