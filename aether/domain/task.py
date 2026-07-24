"""Task — a unit of work tracked by the system.

Lifecycle: PENDING → RUNNING → COMPLETED | CANCELLED

This is the domain model for task management. Tasks can be created
by commands, gestures, voice, or automated workflows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class TaskStatus(Enum):
    """Task lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class Task:
    """A unit of work tracked by the system.

    Example:
        task = Task(
            name="remember laptop position",
            description="Store laptop spatial data from camera feed",
            source="gesture",
        )
    """

    id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    name: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    source: str = "unknown"  # "gesture" | "voice" | "keyboard" | "auto"
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Any = None
    error: Optional[str] = None
    priority: int = 0  # higher = more important
    tags: list[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def start(self) -> Task:
        """Return new task with status=RUNNING."""
        return Task(
            id=self.id,
            name=self.name,
            description=self.description,
            status=TaskStatus.RUNNING,
            source=self.source,
            created_at=self.created_at,
            started_at=datetime.now(),
            completed_at=None,
            result=None,
            error=None,
            priority=self.priority,
            tags=list(self.tags),
            metadata=dict(self.metadata),
        )

    def complete(self, result: Any = None) -> Task:
        """Return new task with status=COMPLETED."""
        return Task(
            id=self.id,
            name=self.name,
            description=self.description,
            status=TaskStatus.COMPLETED,
            source=self.source,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=datetime.now(),
            result=result,
            error=None,
            priority=self.priority,
            tags=list(self.tags),
            metadata=dict(self.metadata),
        )

    def cancel(self, reason: str = "") -> Task:
        """Return new task with status=CANCELLED."""
        return Task(
            id=self.id,
            name=self.name,
            description=self.description,
            status=TaskStatus.CANCELLED,
            source=self.source,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=datetime.now(),
            result=None,
            error=reason or None,
            priority=self.priority,
            tags=list(self.tags),
            metadata=dict(self.metadata),
        )

    @property
    def is_active(self) -> bool:
        return self.status in (TaskStatus.PENDING, TaskStatus.RUNNING)

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.started_at is None:
            return None
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()
