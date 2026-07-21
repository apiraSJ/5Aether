"""
UI Manager — Centralized owner of all UI widgets

Single source of truth for HomeMenu, HelpOverlay, CursorOverlay.
Subscribes to EventBus and routes gesture events to the right widget.

Architecture:
  Gesture → EventBus (MENU_OPEN) → UIManager → home_menu.show_at()
"""

import logging
from typing import Optional

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, QTimer

from core.event_bus import EventBus, EventType
from core.cursor_manager import CursorManager
from interface.cursor_overlay import CursorOverlay
from interface.home_menu import HomeMenu


class UIManager(QObject):
    """Owns all UI widgets. Subscribes to EventBus for gesture-driven actions."""

    def __init__(self, cursor_manager: CursorManager, bus: EventBus, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("Aether.UIManager")
        self.bus = bus
        self.cursor_manager = cursor_manager

        # ── Create widgets (once, shared) ────────────────────────
        self.cursor_overlay = CursorOverlay(cursor_manager)
        self.home_menu = HomeMenu()

        # ── Subscribe to EventBus ────────────────────────────────
        bus.subscribe(EventType.MENU_OPEN, self._on_menu_open)
        bus.subscribe(EventType.MENU_CLOSE, self._on_menu_close)

        self.logger.info("UIManager initialized")

    def show(self):
        """Show the cursor overlay."""
        self.cursor_overlay.show()

    def hide(self):
        """Hide everything."""
        self.cursor_overlay.hide()
        self.home_menu.hide_menu()

    # ── EventBus handlers ────────────────────────────────────────
    def _on_menu_open(self, event):
        cx, cy = self.cursor_manager.position
        self.home_menu.show_at(cx, cy, on_select=self._on_menu_select)
        self.logger.info("Home menu opened")

    def _on_menu_close(self, event):
        self.home_menu.hide_menu()
        self.logger.info("Home menu closed")

    def _on_menu_select(self, action: str):
        """Called when user pinch-clicks a menu item."""
        self.logger.info(f"Menu action: {action}")

        if action == "close_ui":
            self.bus.emit_simple(EventType.UI_CLOSE, {})
        elif action == "open_memory":
            self.bus.emit_simple(EventType.PANEL_SHOW_REQUESTED, {"panel": "system"})
        elif action == "open_tasks":
            self.bus.emit_simple(EventType.PANEL_SHOW_REQUESTED, {"panel": "system"})
        elif action == "open_settings":
            self.bus.emit_simple(EventType.PANEL_SHOW_REQUESTED, {"panel": "settings"})
        elif action == "open_camera":
            self.bus.emit_simple(EventType.PANEL_SHOW_REQUESTED, {"panel": "system"})
        elif action == "open_help":
            self.bus.emit_simple(EventType.PANEL_SHOW_REQUESTED, {"panel": "system"})

    # ── Called from gesture pipeline ─────────────────────────────
    def update_cursor(self, hand_x: float, hand_y: float, gesture: str,
                      gesture_score: float = 0.0, is_pinch: bool = False):
        """Update cursor and menu hover. Called from main loop."""
        self.cursor_manager.update(
            hand_x=hand_x,
            hand_y=hand_y,
            gesture=gesture,
            gesture_score=gesture_score,
            is_pinch=is_pinch,
        )

        cx, cy = self.cursor_manager.position

        # Update menu hover
        if self.home_menu.is_visible:
            self.home_menu.update_hover(cx, cy)

    def handle_pinch_click(self):
        """Handle pinch-to-click. Returns action if something was clicked."""
        if self.home_menu.is_visible:
            return self.home_menu.select_hovered()
        return None
