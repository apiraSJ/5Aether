"""Tests for UI Interaction Visual Layer (Phase 3A.5A).

Tests:
- InteractionBridge sync
- CursorState mapping
- InteractionStatus and HUD state
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from aether.ui.overlay_model import (
    OverlayModel,
    InteractionStatus,
    CursorState,
)
from aether.interaction.interaction_controller import InteractionController
from aether.interaction.interaction_state import InteractionState, CursorMode
from aether.ui.panel.panel_registry import PanelRegistry
from aether.ui.panel.panel_info import PanelInfo


class TestOverlayModelInteractionStatus:
    """Test OverlayModel interaction status for HUD display."""

    def test_update_interaction_status(self):
        model = OverlayModel()
        status = InteractionStatus(
            state="DRAGGING",
            cursor_mode="GRABBING",
            target_panel="memory",
            action="Dragging",
        )
        model.update_interaction_status(status)
        result = model.interaction_status
        assert result.state == "DRAGGING"
        assert result.cursor_mode == "GRABBING"
        assert result.target_panel == "memory"
        assert result.action == "Dragging"

    def test_default_interaction_status(self):
        model = OverlayModel()
        status = model.interaction_status
        assert status.state == "IDLE"
        assert status.cursor_mode == "TRACKING"
        assert status.target_panel == ""
        assert status.action == ""

    def test_clear_resets_status(self):
        model = OverlayModel()
        model.update_interaction_status(InteractionStatus(state="DRAGGING"))
        model.clear()
        assert model.interaction_status.state == "IDLE"


# ── InteractionBridge ──────────────────────────────────────────────


class TestInteractionBridge:
    """Test InteractionBridge sync from InteractionController to OverlayModel."""

    def _make_registry_with_panel(self, panel_id: str = "memory") -> PanelRegistry:
        registry = PanelRegistry()
        info = PanelInfo(
            id=panel_id,
            type="memory",
            label="Memory Panel",
            visible=True,
            x=100,
            y=200,
            w=400,
            h=300,
        )
        registry.register(info)
        return registry

    def test_sync_cursor_tracking(self):
        from aether.ui.interaction_bridge import InteractionBridge

        registry = self._make_registry_with_panel()
        ic = InteractionController(registry)
        model = OverlayModel()
        bridge = InteractionBridge(ic, model, screen_width=1920, screen_height=1080)

        # Update cursor position
        ic.cursor_controller.update(960, 540)
        bridge.update()

        cursor = model.cursor
        assert cursor.visible is True
        assert abs(cursor.x - 0.5) < 0.01  # 960/1920
        assert abs(cursor.y - 0.5) < 0.01  # 540/1080

    def test_sync_cursor_state_hover(self):
        from aether.ui.interaction_bridge import InteractionBridge

        registry = self._make_registry_with_panel()
        ic = InteractionController(registry)
        model = OverlayModel()
        bridge = InteractionBridge(ic, model, screen_width=1920, screen_height=1080)

        # Move cursor over panel to trigger HOVER
        ic.on_cursor_move(150, 250)
        bridge.update()

        cursor = model.cursor
        assert cursor.state == CursorState.HOVER

    def test_sync_status_idle(self):
        from aether.ui.interaction_bridge import InteractionBridge

        registry = self._make_registry_with_panel()
        ic = InteractionController(registry)
        model = OverlayModel()
        bridge = InteractionBridge(ic, model, screen_width=1920, screen_height=1080)

        bridge.update()

        status = model.interaction_status
        assert status.state == "IDLE"
        assert status.action == "Idle"

    def test_sync_status_hover(self):
        from aether.ui.interaction_bridge import InteractionBridge

        registry = self._make_registry_with_panel()
        ic = InteractionController(registry)
        model = OverlayModel()
        bridge = InteractionBridge(ic, model, screen_width=1920, screen_height=1080)

        ic.on_cursor_move(150, 250)
        bridge.update()

        status = model.interaction_status
        assert status.state == "HOVER"
        assert status.action == "Hovering"

    def test_set_screen_size(self):
        from aether.ui.interaction_bridge import InteractionBridge

        registry = self._make_registry_with_panel()
        ic = InteractionController(registry)
        model = OverlayModel()
        bridge = InteractionBridge(ic, model, screen_width=1920, screen_height=1080)

        bridge.set_screen_size(2560, 1440)
        ic.cursor_controller.update(1280, 720)
        bridge.update()

        cursor = model.cursor
        assert abs(cursor.x - 0.5) < 0.01  # 1280/2560
        assert abs(cursor.y - 0.5) < 0.01  # 720/1440


# ── CursorState Mapping ────────────────────────────────────────────


class TestCursorStateMapping:
    """Test CursorMode to CursorState mapping in InteractionBridge."""

    def _make_bridge(self):
        from aether.ui.interaction_bridge import InteractionBridge

        registry = PanelRegistry()
        ic = InteractionController(registry)
        model = OverlayModel()
        return InteractionBridge(ic, model, screen_width=1920, screen_height=1080), ic, model

    def test_tracking_to_default(self):
        bridge, ic, model = self._make_bridge()
        ic.cursor_controller.update(100, 100)
        bridge.update()
        assert model.cursor.state == CursorState.DEFAULT

    def test_frozen_to_pinch(self):
        bridge, ic, model = self._make_bridge()
        ic.cursor_controller.update(100, 100)
        ic.cursor_controller.freeze(100, 100)
        bridge.update()
        assert model.cursor.state == CursorState.PINCH

    def test_grabbing_to_dragging(self):
        bridge, ic, model = self._make_bridge()
        ic.cursor_controller.update(100, 100)
        ic.cursor_controller.start_grab(50, 50)
        bridge.update()
        assert model.cursor.state == CursorState.DRAGGING


# ── InteractionStatus ──────────────────────────────────────────────


class TestInteractionStatus:
    """Test InteractionStatus dataclass."""

    def test_default_values(self):
        status = InteractionStatus()
        assert status.state == "IDLE"
        assert status.cursor_mode == "TRACKING"
        assert status.target_panel == ""
        assert status.action == ""

    def test_with_values(self):
        status = InteractionStatus(
            state="DRAGGING",
            cursor_mode="GRABBING",
            target_panel="memory",
            action="Dragging",
        )
        assert status.state == "DRAGGING"
        assert status.cursor_mode == "GRABBING"
        assert status.target_panel == "memory"
        assert status.action == "Dragging"
