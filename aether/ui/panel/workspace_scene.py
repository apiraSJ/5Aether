"""WorkspaceScene — Runtime Window Manager for Aether panels.

Architecture:
    Mouse/Hand/Voice → WorkspaceScene → InteractionController (tool)
                                       → WorkspaceManager (persistence)
                                       → PanelWidget (rendering)

Responsibilities:
    - Focus management (focus stack, active window, keyboard nav)
    - Z-order management (bring to front, send to back)
    - Window operations (close, minimize, maximize, pin, restore)
    - Docking (edge/center snap during drag)
    - Animation (smooth geometry transitions)
    - Layout persistence (save/restore via WorkspaceManager)

Does NOT:
    - Render panel content (PanelWidget does that)
    - Handle vision overlay (OverlayWidget does that)
    - Persist layout directly (WorkspaceManager does that)
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QWidget, QVBoxLayout

from aether.ui.panel.panel_widget import PanelWidget
from aether.ui.panel.panel_session import PanelSession

logger = logging.getLogger("Aether.WorkspaceScene")

# Snap threshold in pixels
SNAP_THRESHOLD = 20
EDGE_MARGIN = 4
AUTO_SAVE_DEBOUNCE_MS = 400


class WindowManager:
    """Manages focus, z-order, and window state for panel widgets."""

    def __init__(self) -> None:
        self._focus_stack: list[str] = []
        self._z_order: list[str] = []
        self._active_panel: Optional[str] = None
        self._panels: dict[str, PanelWidget] = {}

    def register(self, panel_id: str, widget: PanelWidget) -> None:
        """Register a panel widget."""
        self._panels[panel_id] = widget
        self._z_order.append(panel_id)
        logger.debug("Window registered: '%s'", panel_id)

    def unregister(self, panel_id: str) -> None:
        """Unregister a panel widget."""
        self._panels.pop(panel_id, None)
        self._z_order = [pid for pid in self._z_order if pid != panel_id]
        self._focus_stack = [pid for pid in self._focus_stack if pid != panel_id]
        if self._active_panel == panel_id:
            self._active_panel = None
            if self._focus_stack:
                self._activate(self._focus_stack[-1])

    def focus(self, panel_id: str) -> None:
        """Bring panel to focus (top of z-order, input priority)."""
        if panel_id not in self._panels:
            return

        # Remove from focus stack if present
        self._focus_stack = [pid for pid in self._focus_stack if pid != panel_id]
        self._focus_stack.append(panel_id)

        # Update z-order (bring to front)
        self._z_order = [pid for pid in self._z_order if pid != panel_id]
        self._z_order.append(panel_id)

        # Blur previous active
        if self._active_panel and self._active_panel in self._panels:
            self._panels[self._active_panel].blur_widget()

        # Activate new
        self._activate(panel_id)

    def _activate(self, panel_id: str) -> None:
        """Activate a panel (set as active, raise widget)."""
        self._active_panel = panel_id
        widget = self._panels.get(panel_id)
        if widget:
            widget.focus_widget()
            widget.raise_()

    def blur(self, panel_id: str) -> None:
        """Remove focus from a panel."""
        widget = self._panels.get(panel_id)
        if widget:
            widget.blur_widget()
        self._focus_stack = [pid for pid in self._focus_stack if pid != panel_id]
        if self._active_panel == panel_id:
            self._active_panel = None
            if self._focus_stack:
                self._activate(self._focus_stack[-1])

    def close(self, panel_id: str) -> None:
        """Close a panel (hide, remove from focus)."""
        widget = self._panels.get(panel_id)
        if widget:
            widget.hide()
        self.blur(panel_id)

    def minimize(self, panel_id: str) -> None:
        """Minimize a panel (hide, keep in z-order)."""
        widget = self._panels.get(panel_id)
        if widget:
            widget.hide()

    def maximize(self, panel_id: str) -> None:
        """Maximize a panel (fill parent)."""
        widget = self._panels.get(panel_id)
        if widget and widget.parentWidget():
            parent = widget.parentWidget()
            widget.setGeometry(0, 0, parent.width(), parent.height())
            widget.show()

    def restore(self, panel_id: str) -> None:
        """Restore panel to previous geometry."""
        widget = self._panels.get(panel_id)
        if widget:
            widget.show()

    def pin(self, panel_id: str) -> None:
        """Toggle pin state (keep on top)."""
        widget = self._panels.get(panel_id)
        if widget:
            widget.raise_()

    def bring_to_front(self, panel_id: str) -> None:
        """Bring panel to front of z-order."""
        self._z_order = [pid for pid in self._z_order if pid != panel_id]
        self._z_order.append(panel_id)
        widget = self._panels.get(panel_id)
        if widget:
            widget.raise_()

    def send_to_back(self, panel_id: str) -> None:
        """Send panel to back of z-order."""
        self._z_order = [pid for pid in self._z_order if pid != panel_id]
        self._z_order.insert(0, panel_id)

    @property
    def active_panel(self) -> Optional[str]:
        return self._active_panel

    @property
    def focus_stack(self) -> list[str]:
        return list(self._focus_stack)

    @property
    def z_order(self) -> list[str]:
        return list(self._z_order)

    def get_panel(self, panel_id: str) -> Optional[PanelWidget]:
        return self._panels.get(panel_id)

    def list_panels(self) -> list[str]:
        return list(self._panels.keys())


class WorkspaceScene(QWidget):
    """Central window manager for all workspace panels.

    Contains:
        - WindowManager: focus, z-order, window operations
        - Dock logic: edge/center snap during drag
        - Animation: smooth geometry transitions
        - Persistence: save/restore via WorkspaceManager
    """

    # Emitted when panel geometry/visibility changes (debounced for moves)
    layout_changed = Signal()
    # Emitted when the active panel changes (panel_id)
    focus_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setMouseTracking(True)

        self._window_manager = WindowManager()
        self._workspace_manager = None
        self._sessions: dict[str, PanelSession] = {}
        self._dragging: Optional[str] = None
        self._drag_offset = (0, 0)
        self._resizing: Optional[str] = None
        self._resize_edge = ""
        self._animations: dict[str, QPropertyAnimation] = {}
        self._suppress_save = False

        # Debounced auto-save timer
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(AUTO_SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(self._emit_layout_changed)

    @property
    def window_manager(self) -> WindowManager:
        return self._window_manager

    def bind_workspace_manager(self, manager) -> None:
        """Attach a persistence manager; layout changes are saved to it."""
        self._workspace_manager = manager

    # ── Panel lifecycle ─────────────────────────────────────────────

    def add_panel(self, widget: PanelWidget, session: Optional[PanelSession] = None) -> None:
        """Add a panel widget to the scene."""
        pid = widget.panel_id

        # Create or reuse session
        if session is None:
            session = self._sessions.get(pid)
        if session is None:
            session = PanelSession(
                panel_id=pid,
                panel_type=widget.panel_type,
                x=widget.x(), y=widget.y(),
                w=widget.width(), h=widget.height(),
            )
        self._sessions[pid] = session

        # Register with window manager
        self._window_manager.register(pid, widget)

        # Set parent and geometry
        widget.setParent(self)
        widget.set_geometry(session.x, session.y, session.w, session.h)
        widget.set_pinned_state(session.pinned)
        widget.setVisible(session.visible)
        widget.mount()

        # Connect mouse signals for drag/resize
        widget.mouse_pressed.connect(self._on_pointer_down)
        widget.mouse_dragged.connect(self._on_pointer_move)
        widget.mouse_released.connect(self._on_pointer_up)

        # Connect window ops + geometry tracking (auto-save)
        widget.window_op.connect(self._on_window_op)
        widget.geometry_changed.connect(self._on_geometry_changed)

        logger.info("Scene: panel '%s' added (%dx%d at %d,%d)",
                     pid, session.w, session.h, session.x, session.y)

    def remove_panel(self, panel_id: str) -> Optional[PanelWidget]:
        """Remove a panel from the scene."""
        widget = self._window_manager.get_panel(panel_id)
        if widget:
            self._window_manager.unregister(panel_id)
            widget.setParent(None)
        return widget

    def get_session(self, panel_id: str) -> Optional[PanelSession]:
        return self._sessions.get(panel_id)

    # ── Window operations ───────────────────────────────────────────

    def focus_panel(self, panel_id: str) -> None:
        self._window_manager.focus(panel_id)
        session = self._sessions.get(panel_id)
        if session:
            session.on_focus()
        self.focus_changed.emit(panel_id)

    def close_panel(self, panel_id: str) -> None:
        self._window_manager.close(panel_id)
        session = self._sessions.get(panel_id)
        if session:
            session.visible = False
        self._request_save()

    def minimize_panel(self, panel_id: str) -> None:
        self._window_manager.minimize(panel_id)
        session = self._sessions.get(panel_id)
        if session:
            session.minimized = True
        self._request_save()

    def maximize_panel(self, panel_id: str) -> None:
        self._window_manager.maximize(panel_id)
        session = self._sessions.get(panel_id)
        if session:
            session.maximized = True
        self._request_save()

    def restore_panel(self, panel_id: str) -> None:
        self._window_manager.restore(panel_id)
        session = self._sessions.get(panel_id)
        if session:
            session.minimized = False
            session.maximized = False
            widget = self._window_manager.get_panel(panel_id)
            if widget:
                widget.set_geometry(session.x, session.y, session.w, session.h)
        self._request_save()

    def pin_panel(self, panel_id: str) -> None:
        self._window_manager.pin(panel_id)
        session = self._sessions.get(panel_id)
        if session:
            session.pinned = not session.pinned
            widget = self._window_manager.get_panel(panel_id)
            if widget:
                widget.set_pinned_state(session.pinned)
        self._request_save()

    # ── Window op + geometry tracking (from PanelWidget signals) ─────

    def _on_window_op(self, panel_id: str, op: str) -> None:
        if op == "pin":
            self.pin_panel(panel_id)
        elif op == "minimize":
            self.minimize_panel(panel_id)
        elif op == "maximize":
            self.maximize_panel(panel_id)
        elif op == "close":
            self.close_panel(panel_id)

    def _on_geometry_changed(self, panel_id: str, x: int, y: int, w: int, h: int) -> None:
        session = self._sessions.get(panel_id)
        if session:
            session.x, session.y, session.w, session.h = x, y, w, h
        if not self._suppress_save:
            self._save_timer.start()

    # ── Input handling (Pointer abstraction) ────────────────────────

    def _on_pointer_down(self, panel_id: str, x: int, y: int, region: str) -> None:
        """Handle pointer down on a panel."""
        # Focus the panel
        self.focus_panel(panel_id)

        # Determine action from region
        if region == "resize":
            self._start_resize(panel_id, x, y)
        elif region == "title":
            self._start_drag(panel_id, x, y)

    def _on_pointer_move(self, panel_id: str, x: int, y: int) -> None:
        """Handle pointer move on a panel."""
        if self._dragging == panel_id:
            self._update_drag(panel_id, x, y)
        elif self._resizing == panel_id:
            self._update_resize(panel_id, x, y)

    def _on_pointer_up(self, panel_id: str, x: int, y: int) -> None:
        """Handle pointer up on a panel."""
        if self._dragging == panel_id:
            self._finish_drag(panel_id, x, y)
        elif self._resizing == panel_id:
            self._finish_resize(panel_id, x, y)

    # ── Drag ────────────────────────────────────────────────────────

    def _start_drag(self, panel_id: str, x: int, y: int) -> None:
        widget = self._window_manager.get_panel(panel_id)
        if not widget:
            return
        self._dragging = panel_id
        self._drag_offset = (x, y)
        widget.set_state("dragging")
        logger.debug("Drag start: '%s'", panel_id)

    def _update_drag(self, panel_id: str, x: int, y: int) -> None:
        widget = self._window_manager.get_panel(panel_id)
        if not widget:
            return
        dx = x - self._drag_offset[0]
        dy = y - self._drag_offset[1]
        new_x = widget.x() + dx
        new_y = widget.y() + dy

        # Check snap
        snap_result = self._check_snap(panel_id, new_x, new_y, widget.width(), widget.height())
        if snap_result:
            new_x, new_y = snap_result

        # Clamp to parent bounds
        if widget.parentWidget():
            pw = widget.parentWidget().width()
            ph = widget.parentWidget().height()
            new_x = max(0, min(new_x, pw - widget.width()))
            new_y = max(0, min(new_y, ph - widget.height()))

        widget.move(new_x, new_y)
        self._drag_offset = (x, y)

    def _finish_drag(self, panel_id: str, x: int, y: int) -> None:
        widget = self._window_manager.get_panel(panel_id)
        if not widget:
            return
        self._dragging = None
        widget.set_state("idle")

        # Update session
        session = self._sessions.get(panel_id)
        if session:
            session.x = widget.x()
            session.y = widget.y()

        self._request_save()
        logger.debug("Drag finish: '%s' at (%d, %d)", panel_id, widget.x(), widget.y())

    # ── Resize ──────────────────────────────────────────────────────

    def _start_resize(self, panel_id: str, x: int, y: int) -> None:
        widget = self._window_manager.get_panel(panel_id)
        if not widget:
            return
        self._resizing = panel_id
        self._drag_offset = (x, y)
        widget.set_state("resizing")

    def _update_resize(self, panel_id: str, x: int, y: int) -> None:
        widget = self._window_manager.get_panel(panel_id)
        if not widget:
            return
        dx = x - self._drag_offset[0]
        dy = y - self._drag_offset[1]
        new_w = max(200, widget.width() + dx)
        new_h = max(150, widget.height() + dy)
        widget.resize(new_w, new_h)
        self._drag_offset = (x, y)

    def _finish_resize(self, panel_id: str, x: int, y: int) -> None:
        widget = self._window_manager.get_panel(panel_id)
        if not widget:
            return
        self._resizing = None
        widget.set_state("idle")

        session = self._sessions.get(panel_id)
        if session:
            session.w = widget.width()
            session.h = widget.height()

        self._request_save()

    # ── Snap ────────────────────────────────────────────────────────

    def _check_snap(self, exclude_id: str, x: int, y: int, w: int, h: int) -> Optional[tuple[int, int]]:
        """Check if panel should snap to edges or other panels."""
        if not self.parentWidget():
            return None

        pw = self.parentWidget().width()
        ph = self.parentWidget().height()
        snap_x, snap_y = x, y
        snapped = False

        # Edge snapping
        if abs(x) < SNAP_THRESHOLD:
            snap_x = 0
            snapped = True
        elif abs(x + w - pw) < SNAP_THRESHOLD:
            snap_x = pw - w
            snapped = True

        if abs(y) < SNAP_THRESHOLD:
            snap_y = 0
            snapped = True
        elif abs(y + h - ph) < SNAP_THRESHOLD:
            snap_y = ph - h
            snapped = True

        return (snap_x, snap_y) if snapped else None

    # ── Persistence ─────────────────────────────────────────────────

    def save_sessions(self) -> list[dict]:
        """Serialize all sessions for persistence."""
        return [s.serialize() for s in self._sessions.values()]

    def restore_sessions(self, data: list[dict]) -> None:
        """Restore sessions from serialized data."""
        for d in data:
            session = PanelSession.deserialize(d)
            self._sessions[session.panel_id] = session

    def apply_sessions(self, data: list[dict]) -> int:
        """Apply session geometry/visibility/pin to existing panel widgets.

        Used at startup to restore the previous layout. Sets _suppress_save
        during application so restoring does not immediately re-save.
        Returns the number of panels updated.
        """
        if not data:
            return 0
        self.restore_sessions(data)
        self._suppress_save = True
        applied = 0
        try:
            for session in self._sessions.values():
                widget = self._window_manager.get_panel(session.panel_id)
                if not widget:
                    continue
                widget.set_geometry(session.x, session.y, session.w, session.h)
                widget.set_pinned_state(session.pinned)
                widget.setVisible(session.visible)
                applied += 1
        finally:
            self._suppress_save = False
        if applied:
            logger.info("Workspace restored %d panel(s) from sessions", applied)
        return applied

    def request_layout_save(self) -> None:
        """Immediately serialize sessions and persist via WorkspaceManager."""
        if self._workspace_manager is not None and self._sessions:
            self._workspace_manager.save_layout_sessions("last", self.save_sessions())
        self.layout_changed.emit()

    def _request_save(self) -> None:
        """Debounced trigger for auto-save + layout_changed signal."""
        if self._suppress_save:
            return
        if self._workspace_manager is None:
            self.layout_changed.emit()
            return
        self._save_timer.start()

    def _emit_layout_changed(self) -> None:
        self.request_layout_save()
