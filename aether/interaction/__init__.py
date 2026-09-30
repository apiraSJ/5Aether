"""Aether Interaction Layer — connects input to UI control.

Architecture:
    Input → InteractionLayer → CommandBus → Service → EventBus → UI

The Interaction Layer is the ONLY layer that translates raw input
(mouse, hand, gesture) into UI actions. It never modifies state directly —
it dispatches commands through CommandBus.

Target-agnostic state machine — works with panels, memory cards,
nodes, and any IInteractionTarget.

Key components:
    InteractionController: central state machine (IDLE → HOVER → SELECTED → DRAGGING)
    FocusManager: tracks which target has input focus
    SelectionManager: tracks which target is selected
    HitTest: maps cursor position to target under cursor
    DragController: handles drag with geometry tracking
    ResizeController: handles resize with min/max constraints
    CursorController: manages cursor freeze/unfreeze during interaction
    CursorFilter: smooths raw landmark data (One Euro, dead zone, sensitivity)
    CursorMapper: maps hand input to stable cursor positions (EMA + anchor)
    HandController: converts MediaPipe hand output into HandInputEvents
    InputRouter: routes input events to the appropriate controller
"""

from aether.interaction.interaction_state import InteractionState, CursorMode
from aether.interaction.interaction_controller import InteractionController
from aether.interaction.focus_manager import FocusManager
from aether.interaction.selection_manager import SelectionManager
from aether.interaction.hit_test import HitTest, HitResult
from aether.interaction.drag_controller import DragController, DragState
from aether.interaction.resize_controller import ResizeController, ResizeHandle
from aether.interaction.cursor_controller import CursorController, CursorMode as CursorControllerMode
from aether.interaction.cursor_filter import CursorFilter
from aether.interaction.cursor_mapper import CursorMapper, MapperConfig
from aether.interaction.hand_controller import HandController, HandInputEvent, HandGesture
from aether.interaction.gestures import Gesture
from aether.interaction.input_router import InputRouter
from aether.interaction.snap_zones import SnapZoneManager, SnapResult, SnapType
from aether.interaction.animation import AnimationManager, AnimatedPanel

__all__ = [
    "InteractionState",
    "CursorMode",
    "InteractionController",
    "FocusManager",
    "SelectionManager",
    "HitTest",
    "HitResult",
    "DragController",
    "DragState",
    "ResizeController",
    "ResizeHandle",
    "CursorController",
    "CursorControllerMode",
    "CursorFilter",
    "CursorMapper",
    "MapperConfig",
    "HandController",
    "HandInputEvent",
    "HandGesture",
    "Gesture",
    "InputRouter",
    "SnapZoneManager",
    "SnapResult",
    "SnapType",
    "AnimationManager",
    "AnimatedPanel",
]
