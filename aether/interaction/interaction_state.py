"""Interaction states and cursor modes for the Interaction Layer.

States are generic (not panel-specific) to support any target type:
panels, memory cards, object nodes, timeline items, etc.
"""

from __future__ import annotations

from enum import Enum, auto


class InteractionState(Enum):
    """Central state machine for interaction with any target type.

    Transitions:
        IDLE → HOVER      (cursor enters a target)
        HOVER → SELECTED  (click/pinch on target)
        SELECTED → DRAGGING (hold + move on selected target)
        SELECTED → RESIZING (hold on edge/handle of selected target)
        DRAGGING → IDLE   (release)
        RESIZING → IDLE   (release)
        SELECTED → IDLE   (click elsewhere / Escape)
        HOVER → IDLE      (cursor leaves all targets)
    """

    IDLE = auto()
    HOVER = auto()
    SELECTED = auto()
    DRAGGING = auto()
    RESIZING = auto()


class CursorMode(Enum):
    """Cursor behavior mode."""

    TRACKING = auto()    # Normal: index finger controls cursor
    FROZEN = auto()      # Frozen: cursor position locked (during click)
    GRABBING = auto()    # Grabbing: movement controls selected target
