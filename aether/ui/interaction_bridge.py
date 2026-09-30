"""InteractionBridge — connects InteractionController state to OverlayModel.

Architecture:
    InteractionController → InteractionBridge → OverlayModel → Widgets

This bridge syncs interaction state each frame so widgets can render
hover highlights, selection borders, drag previews, resize handles,
snap indicators, focus rings, and smooth animations.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from aether.interaction.interaction_controller import InteractionController
from aether.interaction.interaction_state import InteractionState, CursorMode
from aether.interaction.snap_zones import SnapZoneManager, SnapType
from aether.interaction.animation import AnimationManager
from aether.ui.overlay_model import (
    OverlayModel,
    CursorState,
    InteractionStatus,
    AnimatedPanelState,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger("Aether.InteractionBridge")


class InteractionBridge:
    """Bridges InteractionController state to OverlayModel for rendering.

    Called each frame to sync:
        - Cursor position and mode
        - Panel hover/selection/drag/resize state
        - Snap zone indicators during drag
        - Focus ring rendering
        - Smooth panel animations
        - Overall interaction status for HUD

    Does NOT modify InteractionController — read-only sync.
    """

    def __init__(
        self,
        interaction_controller: InteractionController,
        overlay_model: OverlayModel,
        snap_zone_manager: Optional[SnapZoneManager] = None,
        animation_manager: Optional[AnimationManager] = None,
        screen_width: int = 1920,
        screen_height: int = 1080,
    ) -> None:
        self._ic = interaction_controller
        self._model = overlay_model
        self._snap = snap_zone_manager or SnapZoneManager(
            interaction_controller._registry,
            screen_width, screen_height,
        )
        self._anim = animation_manager or AnimationManager()
        self._screen_w = screen_width
        self._screen_h = screen_height

    @property
    def snap_zone_manager(self) -> SnapZoneManager:
        return self._snap

    @property
    def animation_manager(self) -> AnimationManager:
        return self._anim

    def set_screen_size(self, width: int, height: int) -> None:
        self._screen_w = width
        self._screen_h = height
        self._snap.set_screen_size(width, height)

    def update(self, dt: float = 1.0 / 60.0) -> None:
        """Sync InteractionController state to OverlayModel.

        Call this each frame before widgets paint.
        """
        self._sync_cursor()
        self._sync_snap_indicator()
        self._sync_focus_ring()
        self._sync_animations(dt)
        self._sync_status()

    def _sync_cursor(self) -> None:
        """Sync cursor position and state from CursorController."""
        cursor_ctrl = self._ic.cursor_controller
        pos = cursor_ctrl.position

        nx = pos.x / self._screen_w if self._screen_w > 0 else 0.5
        ny = pos.y / self._screen_h if self._screen_h > 0 else 0.5

        cursor_state = self._map_cursor_state(cursor_ctrl.mode)
        self._model.update_cursor(nx, ny, cursor_state)

    def _map_cursor_state(self, mode: CursorMode) -> CursorState:
        ic_state = self._ic.state
        if mode == CursorMode.GRABBING:
            return CursorState.DRAGGING
        elif mode == CursorMode.FROZEN:
            return CursorState.PINCH
        elif ic_state == InteractionState.HOVER:
            return CursorState.HOVER
        elif ic_state == InteractionState.SELECTED:
            return CursorState.PINCH
        else:
            return CursorState.DEFAULT


    def _sync_snap_indicator(self) -> None:
        """Show snap indicator when dragging near a snap zone."""
        ic_state = self._ic.state
        if ic_state != InteractionState.DRAGGING:
            self._model.clear_snap_indicator()
            return

        selected_id = self._ic.selected_panel_id
        if not selected_id:
            self._model.clear_snap_indicator()
            return

        panel = self._ic._registry.get(selected_id)
        if not panel:
            self._model.clear_snap_indicator()
            return

        result = self._snap.find_snap(panel.x, panel.y, panel.w, panel.h, selected_id)
        if result.active:
            self._model.update_snap_indicator(
                active=True,
                snap_type=result.snap_type.value,
                x=result.indicator_x,
                y=result.indicator_y,
                w=result.indicator_w,
                h=result.indicator_h,
            )
        else:
            self._model.clear_snap_indicator()

    def _sync_focus_ring(self) -> None:
        """Show focus ring on focused panel."""
        focused_id = self._ic.focused_panel_id
        if not focused_id:
            self._model.clear_focus_ring()
            return

        panel = self._ic._registry.get(focused_id)
        if not panel:
            self._model.clear_focus_ring()
            return

        self._model.update_focus_ring(
            active=True,
            x=panel.x, y=panel.y, w=panel.w, h=panel.h,
        )

    def _sync_animations(self, dt: float) -> None:
        """Sync animation state for smooth panel transitions."""
        panels = self._ic._registry.list_all()

        for panel in panels:
            self._anim.set_geometry(panel.id, panel.x, panel.y, panel.w, panel.h)

        dirty_set = self._anim.update(dt)
        anim_panels: dict[str, AnimatedPanelState] = {}
        for pid, anim in self._anim.panels.items():
            if pid in dirty_set or anim.visible:
                anim_panels[pid] = AnimatedPanelState(
                    panel_id=pid,
                    x=anim.current_x,
                    y=anim.current_y,
                    w=anim.current_w,
                    h=anim.current_h,
                    opacity=anim.opacity,
                    visible=anim.visible,
                )

        self._model.update_animated_panels(anim_panels)

    def _sync_status(self) -> None:
        """Sync overall interaction status for HUD display."""
        ic_state = self._ic.state
        cursor_mode = self._ic.cursor_controller.mode
        selected_id = self._ic.selected_panel_id or ""
        hover = self._ic.hover_result

        action = ""
        if ic_state == InteractionState.DRAGGING:
            action = "Dragging"
        elif ic_state == InteractionState.RESIZING:
            action = "Resizing"
        elif ic_state == InteractionState.SELECTED:
            action = "Selected"
        elif ic_state == InteractionState.HOVER and hover:
            action = "Hovering"
        else:
            action = "Idle"

        status = InteractionStatus(
            state=ic_state.name,
            cursor_mode=cursor_mode.name,
            target_panel=selected_id,
            action=action,
        )

        self._model.update_interaction_status(status)
