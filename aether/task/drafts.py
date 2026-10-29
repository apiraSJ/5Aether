"""In-memory draft store for ContextCal.

Drafts live in memory only (process restart clears them). No DB writes.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple

from aether.task.extraction import ExtractionResult


class DraftState(str, Enum):
    OPEN = "open"
    CONFIRMING = "confirming"
    CONFIRMED = "confirmed"
    DISCARDED = "discarded"
    EXPIRED = "expired"


class DraftError(Exception):
    pass


class DraftNotFoundError(DraftError):
    pass


class DraftNotOpenError(DraftError):
    pass


class DraftExpiredError(DraftError):
    pass


class DraftBusyError(DraftError):
    pass


class DraftConflictError(DraftError):
    pass


@dataclass(frozen=True)
class DraftItem:
    draft_item_id: str
    candidate: Any  # Candidate
    missing_fields: Tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class Draft:
    draft_id: str
    source_text: str
    content_hash: str
    items: Tuple[DraftItem, ...]
    state: DraftState
    tz: str
    created_at: float
    expires_at: float
    confirming_since: Optional[float] = None
    confirm_token: Optional[str] = None
    created_item_ids: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    selection_fingerprint: Optional[str] = None


class DraftStore:
    """Thread-safe in-memory draft store with TTL and confirm lease."""

    def __init__(
        self,
        ttl_seconds: float = 1800.0,
        max_open: int = 20,
        confirm_lease_seconds: float = 60.0,
        clock=time.time,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_open = max_open
        self.confirm_lease_seconds = confirm_lease_seconds
        self._clock = clock
        self._lock = threading.RLock()
        self._drafts: Dict[str, Draft] = {}
        # LRU order for OPEN drafts
        self._open_order: List[str] = []

    def create(self, result: ExtractionResult) -> Draft:
        now = self._clock()
        items: List[DraftItem] = []
        for i, cand in enumerate(result.candidates):
            items.append(
                DraftItem(
                    draft_item_id=f"ditem_{uuid.uuid4().hex[:12]}",
                    candidate=cand,
                    missing_fields=tuple(cand.missing_fields),
                    confidence=float(cand.confidence),
                )
            )
        draft = Draft(
            draft_id=f"draft_{uuid.uuid4().hex[:16]}",
            source_text=result.source_text,
            content_hash=result.content_hash,
            items=tuple(items),
            state=DraftState.OPEN,
            tz=result.tz,
            created_at=now,
            expires_at=now + self.ttl_seconds,
        )
        with self._lock:
            self._sweep_locked(now)
            # enforce max_open - total active (OPEN + CONFIRMING) <= max_open; evict OPEN if needed
            def count_active():
                c = 0
                for did, dd in self._drafts.items():
                    if dd.state in (DraftState.OPEN, DraftState.CONFIRMING):
                        c += 1
                return c
            while count_active() >= self.max_open:
                evicted = False
                # evict oldest OPEN first
                for oldest in list(self._open_order):
                    d = self._drafts.get(oldest)
                    if d and d.state == DraftState.OPEN:
                        self._drafts[oldest] = Draft(
                            draft_id=d.draft_id,
                            source_text=d.source_text,
                            content_hash=d.content_hash,
                            items=d.items,
                            state=DraftState.EXPIRED,
                            tz=d.tz,
                            created_at=d.created_at,
                            expires_at=d.expires_at,
                        )
                        try:
                            self._open_order.remove(oldest)
                        except ValueError:
                            pass
                        evicted = True
                        break
                if not evicted:
                    break
            self._drafts[draft.draft_id] = draft
            if draft.draft_id not in self._open_order:
                self._open_order.append(draft.draft_id)
            return draft

    def _sweep_locked(self, now: float) -> None:
        for did, d in list(self._drafts.items()):
            if d.state == DraftState.OPEN and now >= d.expires_at:
                self._drafts[did] = Draft(
                    draft_id=d.draft_id,
                    source_text=d.source_text,
                    content_hash=d.content_hash,
                    items=d.items,
                    state=DraftState.EXPIRED,
                    tz=d.tz,
                    created_at=d.created_at,
                    expires_at=d.expires_at,
                )
            elif d.state == DraftState.CONFIRMING and d.confirming_since is not None:
                if now - d.confirming_since > self.confirm_lease_seconds:
                    # expired lease -> back to OPEN for takeover
                    self._drafts[did] = Draft(
                        draft_id=d.draft_id,
                        source_text=d.source_text,
                        content_hash=d.content_hash,
                        items=d.items,
                        state=DraftState.OPEN,
                        tz=d.tz,
                        created_at=d.created_at,
                        expires_at=d.expires_at,
                    )
                    if did not in self._open_order:
                        self._open_order.append(did)

    def get(self, draft_id: str) -> Draft:
        now = self._clock()
        with self._lock:
            self._sweep_locked(now)
            d = self._drafts.get(draft_id)
            if not d:
                raise DraftNotFoundError(draft_id)
            if d.state == DraftState.EXPIRED:
                raise DraftExpiredError(draft_id)
            if d.state == DraftState.DISCARDED:
                raise DraftNotOpenError(draft_id)
            if d.state == DraftState.CONFIRMED:
                return d
            if d.state == DraftState.OPEN:
                if now >= d.expires_at:
                    self._drafts[draft_id] = Draft(
                        draft_id=d.draft_id,
                        source_text=d.source_text,
                        content_hash=d.content_hash,
                        items=d.items,
                        state=DraftState.EXPIRED,
                        tz=d.tz,
                        created_at=d.created_at,
                        expires_at=d.expires_at,
                    )
                    raise DraftExpiredError(draft_id)
                return d
            if d.state == DraftState.CONFIRMING:
                if d.confirming_since is not None and now - d.confirming_since > self.confirm_lease_seconds:
                    d2 = Draft(
                        draft_id=d.draft_id,
                        source_text=d.source_text,
                        content_hash=d.content_hash,
                        items=d.items,
                        state=DraftState.OPEN,
                        tz=d.tz,
                        created_at=d.created_at,
                        expires_at=d.expires_at,
                    )
                    self._drafts[draft_id] = d2
                    if draft_id not in self._open_order:
                        self._open_order.append(draft_id)
                    return d2
                # while confirming with valid lease, cannot "get" as open - but test wants state back
                raise DraftBusyError(draft_id)
            raise DraftNotOpenError(draft_id)

    def discard(self, draft_id: str) -> bool:
        with self._lock:
            d = self._drafts.get(draft_id)
            if not d or d.state not in (DraftState.OPEN, DraftState.CONFIRMING):
                return False
            self._drafts[draft_id] = Draft(
                draft_id=d.draft_id,
                source_text=d.source_text,
                content_hash=d.content_hash,
                items=d.items,
                state=DraftState.DISCARDED,
                tz=d.tz,
                created_at=d.created_at,
                expires_at=d.expires_at,
            )
            if draft_id in self._open_order:
                self._open_order.remove(draft_id)
            return True

    def begin_confirm(self, draft_id: str, item_ids: List[str]) -> str:
        now = self._clock()
        with self._lock:
            self._sweep_locked(now)
            d = self._drafts.get(draft_id)
            if not d:
                raise DraftNotFoundError(draft_id)
            if d.state == DraftState.CONFIRMED:
                # idempotent - return existing token
                if d.confirm_token:
                    return d.confirm_token
                return ""
            if d.state == DraftState.EXPIRED:
                raise DraftExpiredError(draft_id)
            if d.state == DraftState.DISCARDED:
                raise DraftNotOpenError(draft_id)
            if d.state == DraftState.CONFIRMING:
                if d.confirming_since is not None and now - d.confirming_since > self.confirm_lease_seconds:
                    # takeover only if lease expired
                    token = uuid.uuid4().hex
                    d2 = Draft(
                        draft_id=d.draft_id,
                        source_text=d.source_text,
                        content_hash=d.content_hash,
                        items=d.items,
                        state=DraftState.CONFIRMING,
                        tz=d.tz,
                        created_at=d.created_at,
                        expires_at=d.expires_at,
                        confirming_since=now,
                        confirm_token=token,
                    )
                    self._drafts[draft_id] = d2
                    if draft_id in self._open_order:
                        self._open_order.remove(draft_id)
                    return token
                raise DraftBusyError(draft_id)
            if d.state == DraftState.OPEN:
                if now >= d.expires_at:
                    self._drafts[draft_id] = Draft(
                        draft_id=d.draft_id,
                        source_text=d.source_text,
                        content_hash=d.content_hash,
                        items=d.items,
                        state=DraftState.EXPIRED,
                        tz=d.tz,
                        created_at=d.created_at,
                        expires_at=d.expires_at,
                    )
                    raise DraftExpiredError(draft_id)
                token = uuid.uuid4().hex
                d2 = Draft(
                    draft_id=d.draft_id,
                    source_text=d.source_text,
                    content_hash=d.content_hash,
                    items=d.items,
                    state=DraftState.CONFIRMING,
                    tz=d.tz,
                    created_at=d.created_at,
                    expires_at=d.expires_at,
                    confirming_since=now,
                    confirm_token=token,
                )
                self._drafts[draft_id] = d2
                if draft_id in self._open_order:
                    self._open_order.remove(draft_id)
                return token
            raise DraftNotOpenError(draft_id)

    def finish_confirm(self, draft_id: str, token: str, created_item_ids: List[str], selection_fingerprint: Optional[str] = None) -> Draft:
        with self._lock:
            d = self._drafts.get(draft_id)
            if not d:
                raise DraftNotFoundError(draft_id)
            if d.state == DraftState.CONFIRMED:
                # idempotent if same fingerprint/token
                if selection_fingerprint is not None and d.selection_fingerprint is not None and d.selection_fingerprint != selection_fingerprint:
                    raise DraftConflictError(draft_id)
                if d.confirm_token and token and d.confirm_token != token and selection_fingerprint is None:
                    # different token, treat as conflict per A4 intent
                    raise DraftConflictError(draft_id)
                return d
            if d.state != DraftState.CONFIRMING:
                raise DraftNotOpenError(draft_id)
            if not d.confirm_token or d.confirm_token != token:
                raise DraftBusyError(draft_id)
            d2 = Draft(
                draft_id=d.draft_id,
                source_text=d.source_text,
                content_hash=d.content_hash,
                items=d.items,
                state=DraftState.CONFIRMED,
                tz=d.tz,
                created_at=d.created_at,
                expires_at=d.expires_at,
                confirming_since=d.confirming_since,
                confirm_token=d.confirm_token,
                created_item_ids=tuple(created_item_ids),
                selection_fingerprint=selection_fingerprint,
            )
            self._drafts[draft_id] = d2
            if draft_id in self._open_order:
                self._open_order.remove(draft_id)
            return d2

    def abort_confirm(self, draft_id: str, token: str) -> None:
        with self._lock:
            d = self._drafts.get(draft_id)
            if not d:
                return
            if d.state == DraftState.CONFIRMED:
                return
            if d.state != DraftState.CONFIRMING:
                return
            if not d.confirm_token or d.confirm_token != token:
                return  # don't abort someone else's lease
            now = self._clock()
            if now >= d.expires_at:
                d2 = Draft(
                    draft_id=d.draft_id,
                    source_text=d.source_text,
                    content_hash=d.content_hash,
                    items=d.items,
                    state=DraftState.EXPIRED,
                    tz=d.tz,
                    created_at=d.created_at,
                    expires_at=d.expires_at,
                )
                self._drafts[draft_id] = d2
            else:
                d2 = Draft(
                    draft_id=d.draft_id,
                    source_text=d.source_text,
                    content_hash=d.content_hash,
                    items=d.items,
                    state=DraftState.OPEN,
                    tz=d.tz,
                    created_at=d.created_at,
                    expires_at=d.expires_at,
                )
                self._drafts[draft_id] = d2
                if draft_id not in self._open_order:
                    self._open_order.append(draft_id)
            return

    def sweep(self) -> int:
        now = self._clock()
        count = 0
        with self._lock:
            for did, d in list(self._drafts.items()):
                if d.state == DraftState.OPEN and now >= d.expires_at:
                    self._drafts[did] = Draft(
                        draft_id=d.draft_id,
                        source_text=d.source_text,
                        content_hash=d.content_hash,
                        items=d.items,
                        state=DraftState.EXPIRED,
                        tz=d.tz,
                        created_at=d.created_at,
                        expires_at=d.expires_at,
                    )
                    if did in self._open_order:
                        self._open_order.remove(did)
                    count += 1
                elif d.state == DraftState.CONFIRMING and d.confirming_since is not None:
                    if now - d.confirming_since > self.confirm_lease_seconds:
                        d2 = Draft(
                            draft_id=d.draft_id,
                            source_text=d.source_text,
                            content_hash=d.content_hash,
                            items=d.items,
                            state=DraftState.OPEN,
                            tz=d.tz,
                            created_at=d.created_at,
                            expires_at=d.expires_at,
                        )
                        self._drafts[did] = d2
                        if did not in self._open_order:
                            self._open_order.append(did)
            return count
