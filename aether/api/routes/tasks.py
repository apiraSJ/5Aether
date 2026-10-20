"""Task and Event CRUD endpoints for Aether API.

Implements Task/Event CRUD and lifecycle endpoints per API Contract v1.1.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Response, status

from aether.api.dependencies import get_schedule_service
from aether.api.schemas import (
    TaskItemCreate,
    TaskItemResponse,
    TaskItemUpdate,
    TaskListResponse,
)
from aether.task.models import InternalStatus, ItemKind, ItemStatus
from aether.task.service import ScheduleService


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    kind: Optional[str] = Query(None, pattern="^(task|event)$"),
    status: Optional[str] = Query(None, pattern="^(pending|completed|cancelled)$"),
    service: "ScheduleService" = Depends(get_schedule_service),
) -> TaskListResponse:
    """List tasks/events with optional filters."""
    kind_enum = ItemKind(kind) if kind else None
    status_enum = ItemStatus(status) if status else None

    items = service.list(kind=kind_enum, status=status_enum)
    return TaskListResponse(
        items=[TaskItemResponse.model_validate(item) for item in items],
        count=len(items),
    )


@router.get("/{item_id}", response_model=TaskItemResponse)
async def get_task(
    item_id: str,
    service: "ScheduleService" = Depends(get_schedule_service),
) -> TaskItemResponse:
    """Get a single task/event by ID."""
    item = service.get(item_id)
    return TaskItemResponse.model_validate(item)


@router.post("", response_model=TaskItemResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskItemCreate,
    service: "ScheduleService" = Depends(get_schedule_service),
) -> TaskItemResponse:
    """Create a new task or event.

    internal_status is forced to "confirmed" server-side for MVP.
    """
    kind_enum = ItemKind(payload.kind)
    # Server-side enforcement: internal_status = "confirmed" for MVP
    item = service.create(
        kind=kind_enum,
        title=payload.title,
        description=payload.description,
        due_date=payload.due_date,
        start_at=payload.start_at,
        end_at=payload.end_at,
        all_day=payload.all_day,
        tz=payload.tz,
        owner=payload.owner,
        source=payload.source,
        internal_status=InternalStatus.CONFIRMED,  # MVP: always confirmed
    )
    return TaskItemResponse.model_validate(item)


@router.patch("/{item_id}", response_model=TaskItemResponse)
async def update_task(
    item_id: str,
    payload: "TaskItemUpdate",
    if_match: Optional[str] = Header(None, alias="If-Match"),
    service: "ScheduleService" = Depends(get_schedule_service),
) -> TaskItemResponse:
    """Update a task/event (partial update).

    Uses PATCH for partial update per API Contract v1.1.
    Optimistic concurrency via If-Match header with exact updated_at float.
    internal_status cannot be modified by client in MVP.
    """
    from aether.api.schemas import TaskItemUpdate  # local import to avoid circular

    # Parse If-Match header for optimistic concurrency
    expected_updated_at = None
    if if_match:
        try:
            expected_updated_at = float(if_match)
        except ValueError:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=400,
                detail="If-Match header must be a valid float (updated_at value)",
            )

    # Build changes dict from payload (exclude unset fields)
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)

    # Server-side enforcement: reject internal_status changes in MVP
    if "internal_status" in changes:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail="internal_status cannot be modified via API in MVP",
        )

    # Coerce enum fields
    if "status" in changes:
        changes["status"] = ItemStatus(changes["status"])

    item = service.update(
        item_id=item_id,
        expected_updated_at=expected_updated_at,
        **changes,
    )
    return TaskItemResponse.model_validate(item)


@router.post("/{item_id}/complete", response_model=TaskItemResponse)
async def complete_task(
    item_id: str,
    service: "ScheduleService" = Depends(get_schedule_service),
) -> TaskItemResponse:
    """Mark a pending task as completed."""
    item = service.complete(item_id)
    return TaskItemResponse.model_validate(item)


@router.post("/{item_id}/cancel", response_model=TaskItemResponse)
async def cancel_task(
    item_id: str,
    reason: str = "",
    service: "ScheduleService" = Depends(get_schedule_service),
) -> TaskItemResponse:
    """Cancel a pending task or event."""
    item = service.cancel(item_id, reason=reason)
    return TaskItemResponse.model_validate(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    item_id: str,
    service: "ScheduleService" = Depends(get_schedule_service),
) -> Response:
    """Delete a task/event. Returns 204 No Content on success."""
    service.delete(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{item_id}/history")
async def get_task_history(
    item_id: str,
    limit: int = Query(100, ge=1, le=1000),
    service: "ScheduleService" = Depends(get_schedule_service),
):
    """Get audit history for a task/event."""
    entries = service.history(item_id, limit=limit)
    return {
        "entries": [
            {
                "id": e.id,
                "item_id": e.item_id,
                "action": e.action.value,
                "before": e.before,
                "after": e.after,
                "changed_fields": e.changed_fields,
                "note": e.note,
                "actor": e.actor,
                "created_at": e.created_at,
            }
            for e in entries
        ],
        "count": len(entries),
    }


# Evidence endpoint is excluded from Sprint 1 per API Contract v1.1
# @router.post("/{item_id}/evidence", ...)