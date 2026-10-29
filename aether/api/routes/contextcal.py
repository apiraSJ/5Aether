"""ContextCal endpoints for Aether API.

Draft-first extraction and confirmation: analyze text into a draft,
review/edit, then confirm to create real tasks/events.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from aether.api.dependencies import get_contextcal_service
from aether.api.schemas import (
    ContextCalAnalyzeRequest,
    ContextCalAnalyzeResponse,
    ContextCalConfirmOutcome,
    ContextCalConfirmRequest,
    ContextCalConfirmResponse,
    ContextCalDraftItem,
    ContextCalDraftResponse,
    ContextCalCandidate,
)
from aether.task.contextcal import ContextCalService, ContextCalError, ContextCalConflictError
from aether.task.drafts import DraftError, DraftNotFoundError, DraftExpiredError, DraftNotOpenError


router = APIRouter(prefix="/contextcal", tags=["contextcal"])


def _serialize_candidate(cand: Any) -> ContextCalCandidate:
    return ContextCalCandidate(
        kind=cand.kind.value if hasattr(cand.kind, "value") else str(cand.kind),
        title=cand.title,
        description=cand.description or "",
        due_date=cand.due_date,
        start_at=cand.start_at,
        end_at=cand.end_at,
        all_day=bool(cand.all_day),
        tz=cand.tz,
        confidence=float(cand.confidence),
        rule_id=cand.rule_id or "",
        raw_excerpt=cand.raw_excerpt or "",
        needs_review=bool(cand.needs_review),
        review_reason=cand.review_reason,
        missing_fields=list(cand.missing_fields or ()),
    )


def _serialize_draft(draft: Any) -> dict:
    items = []
    for ditem in draft.items:
        cand = ditem.candidate
        items.append(
            ContextCalDraftItem(
                draft_item_id=ditem.draft_item_id,
                candidate=_serialize_candidate(cand),
                missing_fields=list(ditem.missing_fields or ()),
                confidence=float(ditem.confidence),
            )
        )
    return {
        "draft_id": draft.draft_id,
        "state": draft.state.value if hasattr(draft.state, "value") else str(draft.state),
        "expires_at": float(draft.expires_at),
        "tz": draft.tz,
        "source_text": draft.source_text,
        "items": items,
    }


@router.post("/analyze", response_model=ContextCalAnalyzeResponse)
async def analyze(
    body: ContextCalAnalyzeRequest,
    service: ContextCalService = Depends(get_contextcal_service),
) -> ContextCalAnalyzeResponse:
    try:
        draft = service.analyze(body.text, tz=body.tz)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    data = _serialize_draft(draft)
    return ContextCalAnalyzeResponse(**data)


@router.get("/drafts/{draft_id}", response_model=ContextCalDraftResponse)
async def get_draft(
    draft_id: str,
    service: ContextCalService = Depends(get_contextcal_service),
) -> ContextCalDraftResponse:
    try:
        draft = service.get_draft(draft_id)
    except DraftNotFoundError:
        raise HTTPException(status_code=404, detail="Draft not found")
    except DraftExpiredError:
        raise HTTPException(status_code=410, detail="Draft expired")
    except DraftError as e:
        raise HTTPException(status_code=400, detail=str(e))
    data = _serialize_draft(draft)
    return ContextCalDraftResponse(**data)


@router.post("/drafts/{draft_id}/confirm", response_model=ContextCalConfirmResponse)
async def confirm(
    draft_id: str,
    body: ContextCalConfirmRequest,
    service: ContextCalService = Depends(get_contextcal_service),
) -> ContextCalConfirmResponse:
    from aether.task.contextcal import ConfirmSelection

    selections = [
        ConfirmSelection(
            draft_item_id=s.draft_item_id,
            accept=s.accept,
            fields=s.fields or {},
        )
        for s in body.selections
    ]
    try:
        result = service.confirm(draft_id, selections)
    except ContextCalConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContextCalError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DraftNotFoundError:
        raise HTTPException(status_code=404, detail="Draft not found")
    except DraftExpiredError:
        raise HTTPException(status_code=410, detail="Draft expired")
    except DraftNotOpenError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except DraftError as e:
        raise HTTPException(status_code=400, detail=str(e))

    outcomes = [
        ContextCalConfirmOutcome(
            draft_item_id=o.draft_item_id,
            ok=o.ok,
            item_id=o.item_id,
            error=o.error,
        )
        for o in result.outcomes
    ]
    return ContextCalConfirmResponse(
        draft_id=result.draft_id,
        committed=result.committed,
        outcomes=outcomes,
        created_item_ids=list(result.created_item_ids),
    )


@router.delete("/drafts/{draft_id}")
async def discard(
    draft_id: str,
    service: ContextCalService = Depends(get_contextcal_service),
) -> dict:
    ok = service.discard(draft_id)
    return {"ok": ok}