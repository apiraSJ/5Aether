"""ContextCal service - draft-first extraction and confirmation."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

import hashlib

from aether.task import extraction
from aether.task.drafts import Draft, DraftStore, DraftBusyError, DraftError, DraftExpiredError, DraftNotFoundError, DraftNotOpenError, DraftConflictError
from aether.task.models import Evidence, ItemKind
from aether.task.service import ScheduleService


@dataclass(frozen=True)
class ConfirmSelection:
    draft_item_id: str
    accept: bool = True
    fields: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfirmOutcome:
    draft_item_id: str
    ok: bool
    item_id: Optional[str] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class ConfirmResult:
    draft_id: str
    committed: bool
    outcomes: Tuple[ConfirmOutcome, ...]
    created_item_ids: Tuple[str, ...]


class ContextCalError(Exception):
    pass


class ContextCalConflictError(ContextCalError):
    pass


class ContextCalService:
    def __init__(
        self,
        service: ScheduleService,
        drafts: DraftStore,
        *,
        repository=None,
        extractor=extraction.analyze,
        clock=time.time,
    ) -> None:
        self._service = service
        self._drafts = drafts
        self._repo = repository
        self._extractor = extractor
        self._clock = clock

    def analyze(self, text: str, *, now=None, tz="Asia/Bangkok") -> Draft:
        result = self._extractor(text, now=now, tz=tz)
        draft = self._drafts.create(result)
        return draft

    def get_draft(self, draft_id: str) -> Draft:
        return self._drafts.get(draft_id)

    def confirm(
        self,
        draft_id: str,
        selections: List[ConfirmSelection],
        *,
        actor: str = "user",
    ) -> ConfirmResult:
        try:
            draft = self._drafts.get(draft_id)
        except DraftError as e:
            raise ContextCalError(str(e)) from e

        sel_map_all = {s.draft_item_id: s for s in selections}
        fp = hashlib.sha256(repr(sorted([(k, bool(v.accept), repr(dict(v.fields))) for k, v in sel_map_all.items()])).encode("utf-8")).hexdigest()

        if draft.state.name == "CONFIRMED":
            if draft.selection_fingerprint and draft.selection_fingerprint != fp:
                raise ContextCalConflictError("selection differs from confirmed draft")
            # idempotent
            return ConfirmResult(
                draft_id=draft_id,
                committed=True,
                outcomes=tuple(),
                created_item_ids=draft.created_item_ids,
            )

        # build selection map
        sel_map = {s.draft_item_id: s for s in selections if s.accept}
        to_create: List[tuple] = []  # (draft_item, cand, fields)
        for ditem in draft.items:
            if ditem.draft_item_id not in sel_map:
                continue
            sel = sel_map[ditem.draft_item_id]
            cand = ditem.candidate
            fields = dict(sel.fields)
            # check missing
            missing = set(ditem.missing_fields)
            # if missing date and fields provide due_date/start_at
            if "date" in missing or "due_date" in missing:
                if "due_date" in fields or "start_at" in fields:
                    missing.discard("date")
                    missing.discard("due_date")
            if "time" in missing:
                if "start_at" in fields:
                    missing.discard("time")
            if "tz" in missing:
                if "tz" in fields:
                    missing.discard("tz")
            if missing:
                return ConfirmResult(
                    draft_id=draft_id,
                    committed=False,
                    outcomes=(ConfirmOutcome(draft_item_id=ditem.draft_item_id, ok=False, error=f"missing:{','.join(sorted(missing))}"),),
                    created_item_ids=tuple(),
                )
            to_create.append((ditem, cand, fields))

        if not to_create:
            return ConfirmResult(
                draft_id=draft_id,
                committed=False,
                outcomes=tuple(),
                created_item_ids=tuple(),
            )

        item_ids_to_create = [d.draft_item_id for d, _, _ in to_create]
        try:
            token = self._drafts.begin_confirm(draft_id, item_ids_to_create)
        except DraftError as e:
            raise ContextCalError(str(e)) from e

        created_ids: List[str] = []
        outcomes: List[ConfirmOutcome] = []
        try:
            if self._repo is not None:
                with self._repo.transaction():
                    for ditem, cand, fields in to_create:
                        try:
                            kind = cand.kind
                            title = fields.get("title") if "title" in fields else cand.title
                            if not title or not str(title).strip():
                                raise ValueError("title empty")
                            desc = fields.get("description") if "description" in fields else cand.description
                            due_date = fields.get("due_date") if "due_date" in fields else cand.due_date
                            start_at = fields.get("start_at") if "start_at" in fields else cand.start_at
                            end_at = fields.get("end_at") if "end_at" in fields else cand.end_at
                            all_day = bool(fields.get("all_day", cand.all_day))
                            tz = fields.get("tz") or cand.tz or draft.tz
                            item = self._service.create(
                                kind,
                                title,
                                description=desc,
                                due_date=due_date,
                                start_at=start_at,
                                end_at=end_at,
                                all_day=all_day,
                                tz=tz,
                                source="extraction",
                                actor=actor,
                            )
                            self._service.attach_evidence(
                                item.id,
                                source="chat",
                                source_ref=draft.content_hash,
                                excerpt=cand.raw_excerpt or draft.source_text,
                                confidence=float(cand.confidence),
                            )
                            created_ids.append(item.id)
                            outcomes.append(ConfirmOutcome(draft_item_id=ditem.draft_item_id, ok=True, item_id=item.id))
                        except Exception:
                            raise
            else:
                # no repo injection - use service directly but still best effort
                for ditem, cand, fields in to_create:
                    try:
                        kind = cand.kind
                        title = fields.get("title") if "title" in fields else cand.title
                        if not title or not str(title).strip():
                            raise ValueError("title empty")
                        desc = fields.get("description") if "description" in fields else cand.description
                        due_date = fields.get("due_date") if "due_date" in fields else cand.due_date
                        start_at = fields.get("start_at") if "start_at" in fields else cand.start_at
                        end_at = fields.get("end_at") if "end_at" in fields else cand.end_at
                        all_day = bool(fields.get("all_day", cand.all_day))
                        tz = fields.get("tz") or cand.tz or draft.tz
                        item = self._service.create(
                            kind,
                            title,
                            description=desc,
                            due_date=due_date,
                            start_at=start_at,
                            end_at=end_at,
                            all_day=all_day,
                            tz=tz,
                            source="extraction",
                            actor=actor,
                        )
                        self._service.attach_evidence(
                            item.id,
                            source="chat",
                            source_ref=draft.content_hash,
                            excerpt=cand.raw_excerpt or draft.source_text,
                            confidence=float(cand.confidence),
                        )
                        created_ids.append(item.id)
                        outcomes.append(ConfirmOutcome(draft_item_id=ditem.draft_item_id, ok=True, item_id=item.id))
                    except Exception:
                        raise
            try:
                self._drafts.finish_confirm(draft_id, token, created_ids, selection_fingerprint=fp)
            except DraftConflictError as ce:
                raise ContextCalConflictError(str(ce)) from ce
            return ConfirmResult(
                draft_id=draft_id,
                committed=True,
                outcomes=tuple(outcomes),
                created_item_ids=tuple(created_ids),
            )
        except Exception as e:
            try:
                self._drafts.abort_confirm(draft_id, token)
            except Exception:
                pass
            # Do not leak IDs from rolled back transaction
            return ConfirmResult(
                draft_id=draft_id,
                committed=False,
                outcomes=tuple(ConfirmOutcome(draft_item_id=ditem.draft_item_id, ok=False, error=str(type(e).__name__)) for ditem, _, _ in to_create),
                created_item_ids=tuple(),
            )

    def discard(self, draft_id: str) -> bool:
        try:
            return self._drafts.discard(draft_id)
        except Exception:
            return False
