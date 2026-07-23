"""
State Machine — Tracks which UI context is active

States:
  IDLE       — No hand detected, nothing shown
  TRACKING   — Hand visible, cursor moving
  MENU_OPEN  — HomeMenu is visible
  PANEL_OPEN — A panel (system/developer/settings) is visible

Transitions:
  IDLE → TRACKING       (hand detected)
  TRACKING → MENU_OPEN  (Open_Palm gesture)
  TRACKING → IDLE       (hand lost)
  MENU_OPEN → PANEL_OPEN (menu item selected)
  MENU_OPEN → TRACKING  (Closed_Fist or menu close)
  PANEL_OPEN → TRACKING (Closed_Fist)
  PANEL_OPEN → IDLE     (hand lost)
"""

import logging
from enum import Enum
from typing import Optional, Callable


class InteractionState(Enum):
    IDLE = "idle"
    TRACKING = "tracking"
    MENU_OPEN = "menu_open"
    PANEL_OPEN = "panel_open"


class InteractionStateMachine:
    """Tracks UI context state for the interaction loop."""

    def __init__(self):
        self.logger = logging.getLogger("Aether.StateMachine")
        self._state = InteractionState.IDLE
        self._prev_state = InteractionState.IDLE
        self._handlers: dict[InteractionState, list[Callable]] = {}
        self._active_panel: Optional[str] = None

    @property
    def state(self) -> InteractionState:
        return self._state

    @property
    def active_panel(self) -> Optional[str]:
        return self._active_panel

    @property
    def is_idle(self) -> bool:
        return self._state == InteractionState.IDLE

    @property
    def is_tracking(self) -> bool:
        return self._state == InteractionState.TRACKING

    @property
    def is_menu_open(self) -> bool:
        return self._state == InteractionState.MENU_OPEN

    @property
    def is_panel_open(self) -> bool:
        return self._state == InteractionState.PANEL_OPEN

    def on(self, state: InteractionState, handler: Callable):
        """Register a handler for when we enter a state."""
        if state not in self._handlers:
            self._handlers[state] = []
        self._handlers[state].append(handler)

    def transition(self, new_state: InteractionState, **kwargs):
        """Transition to a new state and fire handlers."""
        if self._state == new_state:
            return

        self._prev_state = self._state
        old = self._state
        self._state = new_state

        if "panel" in kwargs:
            self._active_panel = kwargs["panel"]
        elif new_state == InteractionState.TRACKING:
            self._active_panel = None

        self.logger.info(f"State: {old.value} → {new_state.value}")

        for handler in self._handlers.get(new_state, []):
            try:
                handler(old, new_state, **kwargs)
            except Exception as e:
                self.logger.error(f"Handler error: {e}")

    def hand_detected(self):
        """Called when hand is first detected."""
        if self._state == InteractionState.IDLE:
            self.transition(InteractionState.TRACKING)

    def hand_lost(self):
        """Called when hand is lost."""
        if self._state == InteractionState.TRACKING:
            self.transition(InteractionState.IDLE)
        elif self._state == InteractionState.MENU_OPEN:
            self.transition(InteractionState.IDLE)

    def menu_opened(self):
        """Called when HomeMenu is shown."""
        self.transition(InteractionState.MENU_OPEN)

    def menu_closed(self):
        """Called when HomeMenu is hidden."""
        if self._state == InteractionState.MENU_OPEN:
            self.transition(InteractionState.TRACKING)

    def panel_opened(self, panel_name: str):
        """Called when a panel is shown."""
        self.transition(InteractionState.PANEL_OPEN, panel=panel_name)

    def panel_closed(self):
        """Called when a panel is hidden."""
        if self._state == InteractionState.PANEL_OPEN:
            self.transition(InteractionState.TRACKING)
