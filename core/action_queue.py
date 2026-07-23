"""
Action Queue — Thread-safe queue for gesture→main thread communication

Extracted from main.py. Perception threads push actions here;
the main loop processes them on the Qt thread.

Processing order per frame:
  1. cursor_update → updates cursor_manager
  2. ui_manager.update_hover() → updates HomeMenu hover state
  3. pinch_click → selects hovered item (now has correct hover)
  4. emit_event → fires EventBus events on main thread (safe for Qt)
"""

import queue
import logging
from core.gesture_router import handle_gesture_action


logger = logging.getLogger("Aether.ActionQueue")


class ActionQueue:
    """Thread-safe action queue for gesture→UI communication."""

    def __init__(self):
        self._queue = queue.Queue()

    def put(self, action):
        """Push an action from any thread."""
        self._queue.put(action)

    def process(self, cursor_manager, ui, broker, ui_manager=None, event_bus=None):
        """Process all queued actions on the main thread. Call from render loop.

        Order: cursor_update → hover update → pinch_click → emit_event
        """
        has_cursor_update = False

        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break

            action_type = item[0]

            if action_type == "cursor_update":
                self._process_cursor_update(item[1], cursor_manager)
                has_cursor_update = True

            elif action_type == "pinch_click":
                # Update hover BEFORE processing pinch so _hover_index is current
                if ui_manager and has_cursor_update:
                    ui_manager.update_hover()
                    has_cursor_update = False
                self._handle_pinch_click(item[1], ui_manager)

            elif action_type == "no_hands":
                cursor_manager.hide()

            elif action_type == "gesture":
                handle_gesture_action(item[1], ui)

            elif action_type == "emit_event":
                self._handle_emit_event(item, event_bus, ui_manager)

        # Final hover update if we had cursor updates but no pinch
        if ui_manager and has_cursor_update:
            ui_manager.update_hover()

    def _handle_pinch_click(self, cursor, ui_manager):
        """Pinch = CLICK. Select hovered menu item if menu is open."""
        if ui_manager and ui_manager.home_menu.is_visible:
            action = ui_manager.handle_pinch_click()
            if action:
                logger.info(f"Pinch click selected: {action}")
        else:
            logger.debug(f"Pinch CLICK at {cursor}")

    def _process_cursor_update(self, data, cursor_manager):
        """Update cursor manager with hand position data."""
        cursor = data.get("cursor")
        gesture = data.get("gesture", "Unknown")
        is_pinch = data.get("is_pinch", False)

        if cursor:
            cursor_manager.update(
                hand_x=cursor[0],
                hand_y=cursor[1],
                gesture=gesture,
                is_pinch=is_pinch,
            )
        else:
            cursor_manager.hide()

    def _handle_emit_event(self, item, event_bus, ui_manager):
        """Fire EventBus event on main thread. Prevents MENU_OPEN re-emission."""
        if len(item) < 4:
            return

        event_type = item[1]
        event_data = item[2]
        skip_if_menu_open = item[3]

        if event_bus is None:
            return

        # Guard: don't re-emit MENU_OPEN if menu is already visible
        if skip_if_menu_open and ui_manager and ui_manager.home_menu.is_visible:
            return

        event_bus.emit_simple(event_type, event_data)

    def process_cursor_updates(self, cursor_manager):
        """Process only cursor updates (for OpenCV fallback without UI)."""
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break

            action_type = item[0]
            if action_type == "cursor_update":
                self._process_cursor_update(item[1], cursor_manager)
            elif action_type == "no_hands":
                cursor_manager.hide()

    def process_pinch_clicks(self, ui_manager):
        """Process any remaining pinch clicks (for OpenCV fallback)."""
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break

            if item[0] == "pinch_click":
                self._handle_pinch_click(item[1], ui_manager)
