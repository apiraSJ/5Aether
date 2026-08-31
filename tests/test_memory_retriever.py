"""Unit tests for the MemoryRetriever contract (Phase 3.2).

Covers:
  - deterministic ranking v1 (relevance / recency / importance / type_weight)
  - explainable scores (no black-box ``score``)
  - deterministic prompt-budget trimming
  - explicit remember / forget / recall
  - graceful degradation when the source is missing or raising
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from aether.ai.memory import (
    DEFAULT_MAX_CHARS,
    TYPE_WEIGHTS,
    DefaultMemoryRetriever,
    MemoryBudget,
    RankedMemory,
    trim_to_budget,
)
from aether.memory.memory_manager import MemoryManager
from aether.services.memory_service import MemoryService


# ── Fake source (duck-typed MemoryService) ──────────────────────────────


class _FakeSource:
    """Simple duck-typed memory source with search/recent/add/delete/recall."""

    def __init__(self, records=None):
        self._records = list(records or [])

    def search(self, query):
        q = query.lower()
        return [r for r in self._records if q in str(r.get("key", "")).lower()
                or q in str((r.get("context") or {}).get("title", "")).lower()]

    def recent(self, limit=10):
        return list(self._records)[:limit]

    def add(self, memory):
        self._records.append({
            "id": f"id-{len(self._records)}",
            "key": memory.get("title", ""),
            "title": memory.get("title", ""),
            "importance": memory.get("importance", 0.5),
            "memory_type": "semantic",
        })
        return self._records[-1]

    def delete(self, record_id):
        for i, r in enumerate(self._records):
            if r.get("id") == record_id:
                self._records.pop(i)
                return True
        return False

    def recall(self, record_id):
        for r in self._records:
            if r.get("id") == record_id:
                return r
        return None

    def stats(self):
        return {"objects": len(self._records), "fact_keys": 0, "total_facts": 0}


def _rec(rid, key, **kw):
    d = {
        "id": rid,
        "key": key,
        "title": key,
        "importance": 0.5,
        "memory_type": "semantic",
        "updated_at": 0.0,
        "created_at": 0.0,
    }
    d.update(kw)
    return d


class TestRetrieveBasics:
    def test_retrieve_empty_query_returns_recent(self):
        src = _FakeSource([_rec("1", "b"), _rec("2", "a")])
        r = DefaultMemoryRetriever(src).retrieve("", limit=5)
        assert len(r) == 2
        # recency order (both updated_at=0 → newest first by id desc tie?)
        assert all(isinstance(x, RankedMemory) for x in r)

    def test_retrieve_nonempty_query_ranks_by_relevance(self):
        src = _FakeSource([
            _rec("1", "cat feeding"),
            _rec("2", "dog walking"),
            _rec("3", "cat vet"),
        ])
        ranked = DefaultMemoryRetriever(src).retrieve("cat", limit=5)
        names = [x.memory["key"] for x in ranked]
        # Both "cat" records outrank "dog"; order among ties by recency/id.
        assert names[0].startswith("cat") and names[1].startswith("cat")
        assert "dog" not in names[:2]

    def test_limit_constrains_results(self):
        src = _FakeSource([_rec(str(i), f"item {i}") for i in range(10)])
        listed = DefaultMemoryRetriever(src).retrieve("", limit=3)
        assert len(listed) == 3

    def test_empty_source_returns_empty(self):
        src = _FakeSource([])
        assert DefaultMemoryRetriever(src).retrieve("hi") == []


class TestExplainableScores:
    def test_score_not_black_box(self):
        src = _FakeSource([_rec("1", "aether memory project")])
        ranked = DefaultMemoryRetriever(src).retrieve("aether", limit=5)
        item = ranked[0]
        assert item.memory is not None
        assert item.score == pytest.approx(
            item.relevance_score + item.recency_score
            + item.importance_score + item.type_weight
        )
        for attr in ("relevance_score", "recency_score", "importance_score", "type_weight"):
            assert hasattr(item, attr)

    def test_type_weight_matrix_semantic_first(self):
        def make(mtype, key):
            return _rec(key, key, memory_type=mtype)

        src = _FakeSource([
            make("spatial", "z spatial hit"),
            make("working", "y working hit"),
            make("episodic", "x episodic hit"),
            make("semantic", "w semantic hit"),
        ])
        ranked = DefaultMemoryRetriever(src).retrieve("hit", limit=5)
        types = [x.memory_type for x in ranked]
        # semantic must appear before episodic before working before spatial
        assert types.index("semantic") < types.index("episodic") < types.index("working") < types.index("spatial")

    def test_importance_raises_score(self):
        src = _FakeSource([
            _rec("1", "low", importance=0.1),
            _rec("2", "high", importance=0.9),
        ])
        ranked = DefaultMemoryRetriever(src).retrieve("", limit=5)
        by_id = {x.memory["id"]: x for x in ranked}
        assert by_id["2"].score > by_id["1"].score


class TestRecency:
    def test_recency_prefers_newer(self):
        src = _FakeSource([
            _rec("1", "old", updated_at=1_000_000.0, created_at=1_000_000.0),
            _rec("2", "new", updated_at=2_000_000_000.0, created_at=2_000_000_000.0),
        ])
        ranked = DefaultMemoryRetriever(src).retrieve("", limit=5)
        assert ranked[0].memory["id"] == "2"
        assert ranked[0].recency_score > ranked[1].recency_score

    def test_recency_value_bounds(self):
        # Just-now record → recency close to 1.0
        import time
        now = time.time()
        src = _FakeSource([_rec("1", "fresh", updated_at=now, created_at=now)])
        ranked = DefaultMemoryRetriever(src).retrieve("", limit=5)
        assert 0.0 < ranked[0].recency_score <= 1.0
        assert ranked[0].recency_score > 0.9


class TestBudget:
    def test_budget_respects_max_items(self):
        src = _FakeSource([_rec(str(i), f"item {i}") for i in range(10)])
        ranked = DefaultMemoryRetriever(src).retrieve("", limit=5)
        kept, skipped = trim_to_budget(ranked, MemoryBudget(max_items=3, max_chars=10_000))
        assert len(kept) == 3
        assert skipped == len(ranked) - 3

    def test_budget_respects_max_chars(self):
        big = _rec("b", "x" * 5000)
        small = _rec("s", "tiny")
        ranked = [
            RankedMemory(big, 3.0, 1, 1, 1, TYPE_WEIGHTS["semantic"], "semantic"),
            RankedMemory(small, 2.0, 1, 1, 0, 0.1, "semantic"),
        ]
        kept, skipped = trim_to_budget(ranked, MemoryBudget(max_items=5, max_chars=1000))
        # "tiny" fits, "big" overflows → only tiny kept
        assert kept == [small]

    def test_budget_trims_deterministically(self):
        src = _FakeSource([_rec(str(i), f"item {i}") for i in range(10)])
        ranked = DefaultMemoryRetriever(src).retrieve("", limit=10)
        a, _ = trim_to_budget(ranked, MemoryBudget(max_items=4, max_chars=3000))
        b, _ = trim_to_budget(ranked, MemoryBudget(max_items=4, max_chars=3000))
        assert [x["id"] for x in a] == [x["id"] for x in b]

    def test_skipped_due_to_budget_reported(self):
        src = _FakeSource([_rec(str(i), f"item {i}") for i in range(6)])
        ranked = DefaultMemoryRetriever(src).retrieve("", limit=6)
        kept, skipped = trim_to_budget(ranked, MemoryBudget(max_items=2, max_chars=50_000))
        assert skipped == 4
        assert len(kept) == 2

    def test_zero_max_items_keeps_nothing(self):
        ranked = []
        src = _FakeSource([_rec("1", "a")])
        ranked = DefaultMemoryRetriever(src).retrieve("", limit=1)
        kept, skipped = trim_to_budget(ranked, MemoryBudget(max_items=0, max_chars=50_000))
        assert kept == []
        assert skipped == 1


class TestExplicitControl:
    def test_remember_forget_recall_roundtrip(self):
        src = _FakeSource([])
        r = DefaultMemoryRetriever(src)
        rid = r.remember("my fact", "hello world", importance=0.7)
        assert rid is not None
        view = r.recall(rid)
        assert view is not None
        assert view["key"] == "my fact"
        assert r.forget(rid) == 1
        assert r.recall(rid) is None

    def test_forget_missing_returns_zero(self):
        r = DefaultMemoryRetriever(_FakeSource([]))
        assert r.forget("nope") == 0

    def test_remember_empty_key_rejected(self):
        r = DefaultMemoryRetriever(_FakeSource([]))
        assert r.remember("   ", "v") is None


class TestDegradation:
    def test_source_missing_degrades_gracefully(self):
        r = DefaultMemoryRetriever(None)
        assert r.retrieve("hi") == []
        assert r.remember("k", "v") is None
        assert r.forget("x") == 0
        assert r.recall("x") is None

    def test_source_raising_degrades_gracefully(self):
        class _Boom:
            def search(self, q):
                raise RuntimeError("boom")
            def recent(self, limit=10):
                raise RuntimeError("boom")
            def stats(self):
                raise RuntimeError("boom")

        r = DefaultMemoryRetriever(_Boom())
        assert r.retrieve("hi") == []

    def test_deterministic_ties(self):
        src = _FakeSource([_rec("1", "same"), _rec("2", "same")])
        a = DefaultMemoryRetriever(src).retrieve("", limit=5)
        b = DefaultMemoryRetriever(src).retrieve("", limit=5)
        assert [x.memory["id"] for x in a] == [x.memory["id"] for x in b]
