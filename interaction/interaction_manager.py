"""
Interaction Manager — Central coordinator for gesture → intent → action

Flow:
  Hand → CursorManager (position)
       → FocusManager (which widget?)
       → StateMachine (what state?)
       → Action (execute)

This module wires everything together.
"""

import logging
from core.event_bus import EventBus, EventType
from core.cursor_manager import CursorManager
from interface.ui_manager import UIManager
from interaction.state_machine import InteractionStateMachine, InteractionState
from interaction.focus_manager import FocusManager


class InteractionManager:
    """Coordinates cursor, focus, state, and actions."""

    def __init__(
        self,
        cursor_manager: CursorManager,
        ui_manager: UIManager,
        bus: EventBus,
    ):
        self.logger = logging.getLogger("Aether.InteractionManager")
        self.cursor_manager = cursor_manager
        self.ui_manager = ui_manager
        self.bus = bus
        self.state = InteractionStateMachine()
        self.focus = FocusManager()

        self._wire_events()
        self.logger.info("InteractionManager initialized")

    def _wire_events(self):
        """Subscribe to EventBus events and wire state transitions."""
        # MENU_OPEN → state transition
        def on_menu_open(event):
            self.state.menu_opened()

        def on_menu_close(event):
            self.state.menu_closed()

        def on_panel_show(event):
            panel = event.data.get("panel", "unknown")
            self.state.panel_opened(panel)

        def on_ui_close(event):
            self.state.panel_closed()

        self.bus.subscribe(EventType.MENU_OPEN, on_menu_open)
        self.bus.subscribe(EventType.MENU_CLOSE, on_menu_close)
        self.bus.subscribe(EventType.PANEL_SHOW_REQUESTED, on_panel_show)
        self.bus.subscribe(EventType.UI_CLOSE, on_ui_close)

    def update(self):
        """Call each frame to update focus and state."""
        if self.cursor_manager.visible:
            self.state.hand_detected()
            cx, cy = self.cursor_manager.position
            self.focus.update(cx, cy)
        else:
            self.state.hand_lost()

    def handle_pinch(self):
        """Handle pinch-to-click. Dispatches based on current state."""
        if self.state.is_menu_open:
            action = self.ui_manager.handle_pinch_click()
            if action:
                self.logger.info(f"Pinch → menu select: {action}")
                return action
        elif self.state.is_tracking:
            focused = self.focus.select()
            if focused:
                self.logger.info(f"Pinch → select widget: {focused}")
                return focused
            else:
                self.logger.info("Pinch → no target")
        return None
