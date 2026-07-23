"""
UI Manager — Centralized owner of all UI widgets

Single source of truth for HomeMenu, StatusBar, CursorOverlay.
Subscribes to EventBus and routes gesture events to widgets.

Architecture:
  Gesture → EventBus (MENU_OPEN) → UIManager → home_menu.show_at()
  Cursor  → update_hover() → home_menu.update_hover() + sub-panel
  Pinch   → handle_pinch_click() → home_menu.select_hovered()
"""

import logging
from typing import Optional

from PySide6.QtCore import QObject

from core.event_bus import EventBus, EventType
from core.cursor_manager import CursorManager
from interface.home_menu import HomeMenu
from interface.status_bar import StatusBar


class UIManager(QObject):
    """Owns HomeMenu + StatusBar. Subscribes to EventBus for gesture-driven actions."""

    def __init__(self, cursor_manager: CursorManager, bus: EventBus, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("Aether.UIManager")
        self.bus = bus
        self.cursor_manager = cursor_manager

        # ── Create widgets ────────────────────────────────────────
        self.home_menu = HomeMenu()
        self.status_bar = StatusBar()

        # ── Subscribe to EventBus ────────────────────────────────
        bus.subscribe(EventType.MENU_OPEN, self._on_menu_open)
        bus.subscribe(EventType.MENU_CLOSE, self._on_menu_close)
        bus.subscribe(EventType.UI_OPEN, self._on_ui_open)
        bus.subscribe(EventType.UI_CLOSE, self._on_ui_close)

        self.logger.info("UIManager initialized")

    def hide(self):
        self.home_menu.hide_menu()
        self.status_bar.hide_bar()

    # ─── EventBus handlers ────────────────────────────────────────

    def _on_menu_open(self, event):
        cx, cy = self.cursor_manager.position
        self.home_menu.show_at(cx, cy, on_select=self._on_menu_select)
        self.status_bar.show_bar()
        self.logger.info(f"Home menu opened at ({cx:.0f}, {cy:.0f})")

    def _on_menu_close(self, event):
        self.home_menu.hide_menu()
        self.logger.info("Home menu closed")

    def _on_ui_open(self, event):
        self.status_bar.show_bar()

    def _on_ui_close(self, event):
        self.home_menu.hide_menu()
        self.status_bar.hide_bar()

    def _on_menu_select(self, action: str):
        """Called when user pinch-clicks a menu item or sub-panel item."""
        self.logger.info(f"Menu action: {action}")

        # Main menu actions
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
        # Sub-panel actions (emit as MENU_ITEM_SELECTED)
        else:
            self.bus.emit_simple(EventType.MENU_ITEM_SELECTED, {"action": action})

    # ─── Called from render loop ──────────────────────────────────

    def update_hover(self):
        """Update HomeMenu hover based on current cursor position."""
        if self.home_menu.is_visible:
            cx, cy = self.cursor_manager.position
            self.home_menu.update_hover(cx, cy)

    def handle_pinch_click(self):
        """Handle pinch-to-click. Returns action if something was clicked."""
        if self.home_menu.is_visible:
            return self.home_menu.select_hovered()
        return None

    def update_status(self, **kwargs):
        """Update status bar stats."""
        self.status_bar.update_stats(**kwargs)
