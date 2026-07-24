"""ContextSnapshot — the "state of mind" for reasoning.

This is NOT raw perception data. It is the distilled context that
ReasoningService needs to make decisions.

Rule from KNOWLEDGE.md:
    "Context is the state used for decision-making, not raw perception data."

Things that belong here:
    - active application/window
    - interaction mode
    - focused object
    - current task
    - user intent

Things that DO NOT belong here:
    - OpenCV frames
    - YOLO results
    - MediaPipe landmarks
    - Mouse coordinates
    - UI widgets
    - Database handles
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class InteractionMode(Enum):
    """The current interaction mode.

    Mode drives reasoning: "developer mode" means different things
    than "normal mode" or "presentation mode".
    """

    NORMAL = "normal"
    DEVELOPER = "developer"
    PRESENTATION = "presentation"
    AI = "ai"
    PASSIVE = "passive"


@dataclass(frozen=True)
class ContextSnapshot:
    """Immutable snapshot of the current context for reasoning.

    Created by IContextProvider.snapshot(), consumed by IReasoningService.

    Example:
        ctx = ContextSnapshot(
            interaction_mode=InteractionMode.DEVELOPER,
            active_window="aether/core/interfaces/i_memory_repository.py - VS Code",
            focused_object="obj_laptop",
            session_id="session_abc123",
            user_intent="modify memory service interface",
        )
    """

    timestamp: datetime = field(default_factory=datetime.now)
    interaction_mode: InteractionMode = InteractionMode.NORMAL
    active_window: Optional[str] = None
    focused_object: Optional[str] = None
    selected_task: Optional[str] = None
    session_id: str = ""
    user_intent: Optional[str] = None

    def with_mode(self, mode: InteractionMode) -> ContextSnapshot:
        """Return new snapshot with updated mode."""
        return ContextSnapshot(
            timestamp=self.timestamp,
            interaction_mode=mode,
            active_window=self.active_window,
            focused_object=self.focused_object,
            selected_task=self.selected_task,
            session_id=self.session_id,
            user_intent=self.user_intent,
        )

    def with_focus(self, object_id: Optional[str]) -> ContextSnapshot:
        """Return new snapshot with updated focus."""
        return ContextSnapshot(
            timestamp=self.timestamp,
            interaction_mode=self.interaction_mode,
            active_window=self.active_window,
            focused_object=object_id,
            selected_task=self.selected_task,
            session_id=self.session_id,
            user_intent=self.user_intent,
        )

    @property
    def is_developer(self) -> bool:
        return self.interaction_mode == InteractionMode.DEVELOPER

    @property
    def is_focused(self) -> bool:
        return self.focused_object is not None
