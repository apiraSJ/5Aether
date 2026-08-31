"""MemoryRetriever — storage-agnostic, explainable memory retrieval for the AI layer.

Phase 3.2 scope:
  - ``MemoryRetriever`` protocol with ``retrieve()`` / ``remember()`` /
    ``forget()`` / ``recall()``.
  - ``RankedMemory`` exposing sub-scores so ``score`` is never a black box.
  - Deterministic ranking v1 (no embeddings / no LLM): relevance + recency +
    importance + type_weight.
  - ``MemoryBudget`` + deterministic first-fit prompt-budget trimming.

The AI layer depends only on this module's contract; it never reaches into
SQLite, FTS5, embeddings, or any specific provider. Vision/CV stays untouched.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Aether.AI.Memory")

# Per-memory-type ranking bias (flat constants in v1; no tuning yet).
TYPE_WEIGHTS: Dict[str, float] = {
    "semantic": 0.20,
    "episodic": 0.15,
    "working": 0.10,
    "spatial": 0.05,
}

DEFAULT_TYPE_WEIGHT = 0.10
DEFAULT_IMPORTANCE = 0.5
DEFAULT_MAX_ITEMS = 5
DEFAULT_MAX_CHARS = 1500


# ── Data structures ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class MemoryBudget:
    """Prompt-budget guardrails applied after ranking."""

    max_items: int = DEFAULT_MAX_ITEMS
    max_chars: int = DEFAULT_MAX_CHARS


@dataclass(frozen=True)
class RankedMemory:
    """A memory record with an explainable ranking score.

    ``score`` is the blended total; the four sub-scores let callers and tests
    see *why* a record was selected rather than treating it as a black box.
    """

    memory: Dict[str, Any]      # record view (id, key, value, context, ...)
    score: float                # relevance + recency + importance + type_weight
    relevance_score: float      # 0..1  (text-match contribution)
    recency_score: float        # 0..1  (newest = ~1.0)
    importance_score: float     # 0..1  (metadata['importance'])
    type_weight: float          # per-memory_type bias
    memory_type: str            # "semantic" | "episodic" | "spatial" | "working"


# ── Protocol ────────────────────────────────────────────────────────────


class MemoryRetriever:
    """Retrieve and rank memory for the AI context layer.

    Storage-agnostic: callers only see ``List[RankedMemory]``. Implementations
    may wrap ``MemoryService`` / ``MemoryManager`` / a future vector store.

    All methods never raise for source failures — they degrade to empty / None
    and log a warning.
    """

    def retrieve(
        self,
        query: str = "",
        limit: int = DEFAULT_MAX_ITEMS,
        token_budget: int = DEFAULT_MAX_CHARS,
        memory_types: Optional[List[str]] = None,
    ) -> List[RankedMemory]:
        """Return memory ranked by relevance to ``query``.

        - ``query == ""`` → recency-ranked recent memory.
        - Never raises: emits a warning + returns [] on source failure.
        """
        raise NotImplementedError

    def remember(
        self,
        key: str,
        value: Any,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = DEFAULT_IMPORTANCE,
        memory_type: str = "semantic",
    ) -> Optional[str]:
        """Explicitly store a memory record. Returns record id or None."""
        raise NotImplementedError

    def forget(self, memory_id_or_key: str) -> int:
        """Explicitly delete memory. Returns number of records removed."""
        raise NotImplementedError

    def recall(self, memory_id_or_key: str) -> Optional[Dict[str, Any]]:
        """Explicit, deterministic lookup of a single record."""
        raise NotImplementedError


# ── Default implementation ──────────────────────────────────────────────


class DefaultMemoryRetriever(MemoryRetriever):
    """Wraps a MemoryService-like source with deterministic ranking v1.

    Source capabilities are discovered by duck typing, so either the
    ``aether.services.memory_service.MemoryService`` facade (search/recall/
    recent/stats) or the simple in-memory service (recall_facts/list_objects/
    get_stats) works.
    """

    def __init__(self, source: Any = None, type_weights: Optional[Dict[str, float]] = None) -> None:
        self._source = source
        self._type_weights = dict(type_weights) if type_weights else dict(TYPE_WEIGHTS)

    @property
    def source(self) -> Any:
        return self._source

    # ── Retrieval ────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str = "",
        limit: int = DEFAULT_MAX_ITEMS,
        token_budget: int = DEFAULT_MAX_CHARS,
        memory_types: Optional[List[str]] = None,
    ) -> List[RankedMemory]:
        if self._source is None:
            logger.warning("Memory retriever has no source; returning []")
            return []
        try:
            records = self._candidate_records(query, limit)
        except Exception as exc:
            logger.warning("Memory retrieval failed: %s", exc)
            return []
        return self._rank(records, query, limit)

    def _candidate_records(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Pull raw candidate records (as plain dicts) from the source."""
        src = self._source
        if query and query.strip():
            search = _getattr_opt(src, "search")
            if search is not None:
                return list(search(query.strip()))[: limit * 4]
            recall = _getattr_opt(src, "recall_facts")
            if recall is not None:
                return list(recall(query.strip().split()[0]))[: limit * 4]
        recent = _getattr_opt(src, "recent")
        if recent is not None:
            return list(recent(limit * 4))[: limit * 4]
        objects = _getattr_opt(src, "list_objects")
        if objects is not None:
            return list(objects)[: limit * 4]
        return []

    # ── Ranking v1 (deterministic) ───────────────────────────────────

    def _rank(
        self,
        records: List[Dict[str, Any]],
        query: str,
        limit: int,
    ) -> List[RankedMemory]:
        now = time.time()
        ranked: List[RankedMemory] = []
        for rec in records:
            mtype = str(rec.get("memory_type") or "semantic")
            relevance = self._relevance(rec, query)
            recency = self._recency(rec, now)
            importance = self._importance(rec)
            type_weight = self._type_weights.get(mtype, DEFAULT_TYPE_WEIGHT)
            score = relevance + recency + importance + type_weight
            ranked.append(RankedMemory(
                memory=rec,
                score=score,
                relevance_score=relevance,
                recency_score=recency,
                importance_score=importance,
                type_weight=type_weight,
                memory_type=mtype,
            ))
        # Deterministic: score DESC, then updated_at DESC, then id.
        ranked.sort(
            key=lambda r: (
                -r.score,
                -_ts(r.memory, "updated_at", "created_at"),
                str(r.memory.get("id", "")),
            ),
        )
        return ranked[:limit]

    @staticmethod
    def _relevance(rec: Dict[str, Any], query: str) -> float:
        """0..1 text-match contribution."""
        query_l = (query or "").strip().lower()
        if not query_l:
            return 0.0
        key = str(rec.get("key") or "").lower()
        title = str(
            (rec.get("context") or {}).get("title") or rec.get("title") or ""
        ).lower()
        content = str(
            (rec.get("context") or {}).get("summary")
            or (rec.get("context") or {}).get("content")
            or rec.get("summary") or rec.get("content") or ""
        ).lower()
        # Direct token overlap on key/title/content.
        toks = set(query_l.split())
        reldoc = f"{key} {title} {content}".split()
        matched = sum(1 for t in toks if any(t in w for w in reldoc))
        if matched == 0:
            return 0.0
        return min(1.0, matched / len(toks))

    @staticmethod
    def _recency(rec: Dict[str, Any], now: float) -> float:
        age_days = max(0.0, (now - _ts(rec, "updated_at", "created_at")) / 86400.0)
        return 1.0 / (1.0 + age_days)

    @staticmethod
    def _importance(rec: Dict[str, Any]) -> float:
        imp = rec.get("importance")
        if imp is None:
            imp = (rec.get("context") or {}).get("importance", DEFAULT_IMPORTANCE)
        try:
            return min(1.0, max(0.0, float(imp)))
        except (TypeError, ValueError):
            return DEFAULT_IMPORTANCE

    # ── Explicit user control ────────────────────────────────────────

    def remember(
        self,
        key: str,
        value: Any,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = DEFAULT_IMPORTANCE,
        memory_type: str = "semantic",
    ) -> Optional[str]:
        if not key or not key.strip():
            logger.warning("MemoryRetriever.remember: empty key rejected")
            return None
        if self._source is None:
            logger.warning("MemoryRetriever.remember: no source")
            return None
        try:
            add = _getattr_opt(self._source, "add")
            if add is not None:
                view = add({
                    "title": key,
                    "summary": value if isinstance(value, str) else json.dumps(value, ensure_ascii=False),
                    "content": "",
                    "importance": float(importance),
                    "source": "ai",
                })
                return (view or {}).get("id") if isinstance(view, dict) else None
            store = _getattr_opt(self._source, "store")
            if store is not None:
                return store(memory_type, key, value, context=metadata or {})
            return None
        except Exception as exc:
            logger.warning("MemoryRetriever.remember failed: %s", exc)
            return None

    def forget(self, memory_id_or_key: str) -> int:
        if self._source is None:
            logger.warning("MemoryRetriever.forget: no source")
            return 0
        try:
            delete = _getattr_opt(self._source, "delete")
            if delete is not None:
                return 1 if delete(memory_id_or_key) else 0
            forget = _getattr_opt(self._source, "forget")
            if forget is not None:
                return int(forget(memory_id_or_key) or 0)
            return 0
        except Exception as exc:
            logger.warning("MemoryRetriever.forget failed: %s", exc)
            return 0

    def recall(self, memory_id_or_key: str) -> Optional[Dict[str, Any]]:
        if self._source is None:
            logger.warning("MemoryRetriever.recall: no source")
            return None
        try:
            rec = _getattr_opt(self._source, "recall")
            if rec is not None:
                result = rec(memory_id_or_key)
                # MemoryService.recall returns a view dict or None.
                if isinstance(result, dict):
                    return result
                # MemoryManager.recall returns a RecallResult.
                converter = getattr(result, "records", None)
                if converter:
                    records = list(result.records)
                    return records[0] if records else None
                return None
            return None
        except Exception as exc:
            logger.warning("MemoryRetriever.recall failed: %s", exc)
            return None


# ── Budget trimming ─────────────────────────────────────────────────────


def trim_to_budget(
    ranked: List[RankedMemory],
    budget: MemoryBudget,
) -> tuple[List[Dict[str, Any]], int]:
    """Deterministic first-fit budget cut of already-ranked memory.

    - Keeps at most ``budget.max_items``.
    - Appends records in given (score) order while cumulative serialized char
      length stays ``<= max_chars``; stops as soon as the next would overflow.
    - Returns ``(kept_views, skipped_due_to_budget)``; never random.
    """
    if budget.max_items <= 0:
        return [], len(ranked)
    kept: List[Dict[str, Any]] = []
    used = 0
    skipped = 0
    for entry in ranked:
        if len(kept) >= budget.max_items:
            skipped += 1
            continue
        view = entry.memory
        length = len(_serialize(view))
        if used + length > budget.max_chars:
            skipped += 1
            continue
        kept.append(view)
        used += length
    return kept, skipped


def _serialize(view: Dict[str, Any]) -> str:
    try:
        return json.dumps(view, ensure_ascii=False, separators=(",", ":"), default=str)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return str(view)


def _getattr_opt(obj: Any, name: str) -> Any:
    try:
        return getattr(obj, name)
    except Exception:  # pragma: no cover - defensive
        return None


def _ts(rec: Dict[str, Any], *keys: str) -> float:
    for key in keys:
        val = rec.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return 0.0
