"""InteractionController — central brain for interaction state machine.

Manages the flow:
    IDLE → HOVER → SELECTED → DRAGGING/RESIZING → IDLE

Target-agnostic: works with panels, memory cards, nodes, and any
IInteractionTarget. Emits generic events through EventBus:
    interaction.selection.changed
    interaction.drag.started / updated / ended
    interaction.resize.started / updated / ended

Coordinates FocusManager, SelectionManager, HitTest, DragController, ResizeController.
"""

from __future__ import annotations

import logging
from typing import Optional

from aether.interaction.interaction_state import InteractionState
from aether.interaction.focus_manager import FocusManager
from aether.interaction.selection_manager import SelectionManager
from aether.interaction.hit_test import HitTest, HitResult
from aether.interaction.drag_controller import DragController
from aether.interaction.resize_controller import ResizeController
from aether.interaction.cursor_controller import CursorController
from aether.ui.panel.panel_registry import PanelRegistry
from aether.interaction.snap_zones import SnapZoneManager

logger = logging.getLogger("Aether.InteractionController")


class InteractionController:
    """Central state machine for target interaction.

    Coordinates sub-controllers and manages state transitions.
    Emits generic interaction events through EventBus.
    Works with any target (panel, card, node — Sprint 1 uses panels).
    """

    def __init__(
        self,
        panel_registry: PanelRegistry,
        event_bus=None,
        snap_zone_manager: Optional[SnapZoneManager] = None,
        screen_width: int = 1920,
        screen_height: int = 1080,
    ) -> None:
        self._registry = panel_registry
        self._event_bus = event_bus
        self._state = InteractionState.IDLE
        self._hover_result: Optional[HitResult] = None

        # Sub-controllers
        self._focus = FocusManager(panel_registry)
        self._selection = SelectionManager(panel_registry)
        self._hit_test = HitTest()
        self._drag = DragController(panel_registry)
        self._resize = ResizeController(panel_registry)
        self._cursor = CursorController()
        self._snap = snap_zone_manager or SnapZoneManager(
            panel_registry, screen_width, screen_height,
        )

    @property
    def state(self) -> InteractionState:
        return self._state

    @property
    def focus_manager(self) -> FocusManager:
        return self._focus

    @property
    def selection_manager(self) -> SelectionManager:
        return self._selection

    @property
    def hit_test(self) -> HitTest:
        return self._hit_test

    @property
    def drag_controller(self) -> DragController:
        return self._drag

    @property
    def resize_controller(self) -> ResizeController:
        return self._resize

    @property
    def cursor_controller(self) -> CursorController:
        return self._cursor

    @property
    def hover_result(self) -> Optional[HitResult]:
        return self._hover_result

    @property
    def snap_zone_manager(self) -> SnapZoneManager:
        return self._snap

    @property
    def selected_panel_id(self) -> Optional[str]:
        return self._selection.selected_panel_id

    @property
    def focused_panel_id(self) -> Optional[str]:
        return self._focus.focused_panel_id

    # ── State transitions ──────────────────────────────────────────

    def on_cursor_move(self, cursor_x: float, cursor_y: float) -> Optional[HitResult]:
        """Process cursor movement.

        State transitions:
            IDLE → HOVER (cursor enters a target)
            HOVER → IDLE (cursor leaves all targets)
            DRAGGING → updates drag position + emits drag.updated
            RESIZING → updates resize position + emits resize.updated
        """
        from aether.core.event_bus_v2 import Event
        from aether.core.event_type import EventType

        panels = self._registry.list_all()

        if self._state == InteractionState.DRAGGING:
            self._drag.update(cursor_x, cursor_y)
            self._drag.apply()
            self._apply_snap_during_drag()
            self._emit_event(EventType.DRAG_UPDATED, {
                "target_id": self._selection.selected_panel_id,
                "x": cursor_x, "y": cursor_y,
            })
            return self._hover_result

        if self._state == InteractionState.RESIZING:
            self._resize.update(cursor_x, cursor_y)
            self._resize.apply()
            self._emit_event(EventType.RESIZE_UPDATED, {
                "target_id": self._selection.selected_panel_id,
                "x": cursor_x, "y": cursor_y,
            })
            return self._hover_result

        # Hit test
        result = self._hit_test.test(cursor_x, cursor_y, panels)
        self._hover_result = result

        if self._state == InteractionState.IDLE:
            if result.hit:
                self._transition(InteractionState.HOVER)
                self._focus.focus(result.panel_id)
                return result
        elif self._state == InteractionState.HOVER:
            if not result.hit:
                self._transition(InteractionState.IDLE)
                self._focus.unfocus()
            elif result.panel_id != self._focus.focused_panel_id:
                self._focus.focus(result.panel_id)
            return result
        elif self._state == InteractionState.SELECTED:
            if not result.hit:
                pass
            elif result.panel_id != self._selection.selected_panel_id:
                self._selection.deselect()
                self._emit_event(EventType.SELECTION_CHANGED, {
                    "target_id": None,
                    "action": "deselect",
                })
                self._selection.select(result.panel_id)
                self._focus.focus(result.panel_id)
                self._emit_event(EventType.SELECTION_CHANGED, {
                    "target_id": result.panel_id,
                    "action": "select",
                })
            return result

        return result

    def on_click(self, cursor_x: float, cursor_y: float) -> Optional[str]:
        """Process click/pinch. Returns target_id if a target was clicked.

        State transitions:
            HOVER → SELECTED (click on target)
            SELECTED → IDLE (click elsewhere)
            IDLE → SELECTED (click on target directly)
        """
        from aether.core.event_bus_v2 import Event
        from aether.core.event_type import EventType

        if self._state == InteractionState.DRAGGING:
            return self._end_drag()
        if self._state == InteractionState.RESIZING:
            return self._end_resize()

        panels = self._registry.list_all()
        result = self._hit_test.test(cursor_x, cursor_y, panels)

        if self._state == InteractionState.HOVER and result.hit:
            self._selection.select(result.panel_id)
            self._focus.focus(result.panel_id)
            self._transition(InteractionState.SELECTED)
            self._emit_event(EventType.SELECTION_CHANGED, {
                "target_id": result.panel_id,
                "action": "select",
            })
            return result.panel_id

        if self._state == InteractionState.SELECTED:
            if result.hit and result.panel_id == self._selection.selected_panel_id:
                self._selection.deselect()
                self._transition(InteractionState.IDLE)
                self._emit_event(EventType.SELECTION_CHANGED, {
                    "target_id": None,
                    "action": "deselect",
                })
                return None
            elif result.hit:
                self._selection.deselect()
                self._selection.select(result.panel_id)
                self._focus.focus(result.panel_id)
                self._emit_event(EventType.SELECTION_CHANGED, {
                    "target_id": result.panel_id,
                    "action": "select",
                })
                return result.panel_id
            else:
                self._selection.deselect()
                self._transition(InteractionState.IDLE)
                self._emit_event(EventType.SELECTION_CHANGED, {
                    "target_id": None,
                    "action": "deselect",
                })
                return None

        if self._state == InteractionState.IDLE and result.hit:
            self._selection.select(result.panel_id)
            self._focus.focus(result.panel_id)
            self._transition(InteractionState.SELECTED)
            self._emit_event(EventType.SELECTION_CHANGED, {
                "target_id": result.panel_id,
                "action": "select",
            })
            return result.panel_id

        return None

    def on_drag_start(self, cursor_x: float, cursor_y: float) -> bool:
        """Start dragging the selected target.

        State transitions:
            SELECTED → DRAGGING (emits drag.started)
        """
        from aether.core.event_bus_v2 import Event
        from aether.core.event_type import EventType

        if self._state != InteractionState.SELECTED:
            return False

        panel_id = self._selection.selected_panel_id
        if not panel_id:
            return False

        if self._hover_result and self._hover_result.is_resize_handle:
            return self.on_resize_start(cursor_x, cursor_y)

        success = self._drag.start(panel_id, cursor_x, cursor_y)
        if success:
            self._cursor.start_grab(
                float(self._registry.get(panel_id).x),
                float(self._registry.get(panel_id).y),
            )
            self._transition(InteractionState.DRAGGING)
            self._emit_event(EventType.DRAG_STARTED, {
                "target_id": panel_id,
                "x": cursor_x, "y": cursor_y,
            })
        return success

    def on_drag_end(self) -> Optional[str]:
        """End dragging. Emits drag.ended."""
        if self._state != InteractionState.DRAGGING:
            return None
        return self._end_drag()

    def on_resize_start(self, cursor_x: float, cursor_y: float) -> bool:
        """Start resizing the selected target.

        State transitions:
            SELECTED → RESIZING (emits resize.started)
        """
        from aether.core.event_bus_v2 import Event
        from aether.core.event_type import EventType

        if self._state != InteractionState.SELECTED:
            return False

        panel_id = self._selection.selected_panel_id
        if not panel_id:
            return False

        success = self._resize.start(panel_id, cursor_x, cursor_y)
        if success:
            self._transition(InteractionState.RESIZING)
            self._emit_event(EventType.RESIZE_STARTED, {
                "target_id": panel_id,
                "x": cursor_x, "y": cursor_y,
            })
        return success

    def on_resize_end(self) -> Optional[str]:
        """End resizing. Emits resize.ended."""
        if self._state != InteractionState.RESIZING:
            return None
        return self._end_resize()

    def on_cancel(self) -> None:
        """Cancel current interaction. Returns to IDLE."""
        from aether.core.event_bus_v2 import Event
        from aether.core.event_type import EventType

        if self._state == InteractionState.DRAGGING:
            self._drag.cancel()
            self._emit_event(EventType.DRAG_ENDED, {
                "target_id": self._selection.selected_panel_id,
                "cancelled": True,
            })
        elif self._state == InteractionState.RESIZING:
            self._resize.cancel()
            self._emit_event(EventType.RESIZE_ENDED, {
                "target_id": self._selection.selected_panel_id,
                "cancelled": True,
            })
        self._selection.deselect()
        self._cursor.unfreeze()
        self._emit_event(EventType.SELECTION_CHANGED, {
            "target_id": None,
            "action": "cancel",
        })
        self._transition(InteractionState.IDLE)

    def _apply_snap_during_drag(self) -> None:
        """Check snap zones and apply if panel is within threshold."""
        selected_id = self._selection.selected_panel_id
        if not selected_id:
            return

        panel = self._registry.get(selected_id)
        if not panel:
            return

        result = self._snap.find_snap(panel.x, panel.y, panel.w, panel.h, selected_id)
        if result.active:
            self._registry.move_panel(selected_id, result.target_x, result.target_y)
            if result.target_w is not None and result.target_h is not None:
                self._registry.resize_panel(selected_id, result.target_w, result.target_h)
            self._snap.clear_active_zones()

    # ── Internal ───────────────────────────────────────────────────

    def _end_drag(self) -> Optional[str]:
        from aether.core.event_bus_v2 import Event
        from aether.core.event_type import EventType

        panel_id = self._drag.end()
        self._cursor.end_grab()
        self._emit_event(EventType.DRAG_ENDED, {
            "target_id": panel_id,
            "cancelled": False,
        })
        self._selection.deselect()
        self._emit_event(EventType.SELECTION_CHANGED, {
            "target_id": None,
            "action": "deselect",
        })
        self._transition(InteractionState.IDLE)
        return panel_id

    def _end_resize(self) -> Optional[str]:
        from aether.core.event_bus_v2 import Event
        from aether.core.event_type import EventType

        panel_id = self._resize.end()
        self._emit_event(EventType.RESIZE_ENDED, {
            "target_id": panel_id,
            "cancelled": False,
        })
        self._selection.deselect()
        self._emit_event(EventType.SELECTION_CHANGED, {
            "target_id": None,
            "action": "deselect",
        })
        self._transition(InteractionState.IDLE)
        return panel_id

    def _transition(self, new_state: InteractionState) -> None:
        old = self._state
        self._state = new_state
        if old != new_state:
            logger.debug("Interaction: %s → %s", old.name, new_state.name)

    def _emit_event(self, event_type, payload: dict) -> None:
        if not self._event_bus:
            return
        try:
            from aether.core.event_bus_v2 import Event
            self._event_bus.publish(Event(
                type=event_type,
                payload=payload,
                source="interaction_controller",
            ))
        except Exception:
            logger.exception("Failed to emit interaction event: %s", event_type)
