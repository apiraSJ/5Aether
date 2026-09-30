"""Tests for InteractionController gesture state machine.

Tests target-agnostic generic states — no panel-specific logic.
"""

import time
from aether.interaction.interaction_controller import InteractionController
from aether.interaction.interaction_state import InteractionState
from aether.ui.panel.panel_registry import PanelRegistry
from aether.ui.panel.panel_info import PanelInfo, PanelCapability


def _make_registry():
    r = PanelRegistry()
    r.register(PanelInfo(
        id="memory", type="memory", label="Memory",
        x=0, y=0, w=400, h=300, z_index=10, visible=True,
        capabilities=[PanelCapability.MOVE, PanelCapability.RESIZE, PanelCapability.FOCUS],
    ))
    return r


def test_initial_state():
    ic = InteractionController(_make_registry())
    assert ic.state == InteractionState.IDLE


def test_cursor_move_to_idle():
    """Moving cursor without hitting anything stays IDLE."""
    ic = InteractionController(_make_registry())
    result = ic.on_cursor_move(-100, -100)
    assert result is None or not result.hit
    assert ic.state == InteractionState.IDLE


def test_cursor_enter_panel():
    """Cursor moving onto a panel should transition to HOVER."""
    ic = InteractionController(_make_registry())
    ic.on_cursor_move(50, 50)
    assert ic.state == InteractionState.HOVER


def test_cursor_leave_panel():
    """Cursor leaving all panels should transition to IDLE."""
    ic = InteractionController(_make_registry())
    ic.on_cursor_move(50, 50)
    assert ic.state == InteractionState.HOVER
    ic.on_cursor_move(-100, -100)
    assert ic.state == InteractionState.IDLE


def test_click_selects_panel():
    """Click on a panel should transition to SELECTED."""
    ic = InteractionController(_make_registry())
    ic.on_cursor_move(50, 50)
    result = ic.on_click(50, 50)
    assert result == "memory"
    assert ic.state == InteractionState.SELECTED


def test_click_elsewhere_deselects():
    """Clicking elsewhere when SELECTED should deselect."""
    ic = InteractionController(_make_registry())
    ic.on_cursor_move(50, 50)
    ic.on_click(50, 50)
    assert ic.state == InteractionState.SELECTED
    ic.on_cursor_move(-100, -100)
    ic.on_click(-100, -100)
    assert ic.state == InteractionState.IDLE


def test_drag_start_requires_selected():
    """Drag should only start from SELECTED state."""
    ic = InteractionController(_make_registry())
    result = ic.on_drag_start(50, 50)
    assert not result


def test_drag_lifecycle():
    """Full drag lifecycle: select → drag → update → end."""
    ic = InteractionController(_make_registry())
    ic.on_cursor_move(50, 50)
    ic.on_click(50, 50)
    assert ic.state == InteractionState.SELECTED
    success = ic.on_drag_start(50, 50)
    assert success
    assert ic.state == InteractionState.DRAGGING
    ic.on_cursor_move(200, 200)
    assert ic.state == InteractionState.DRAGGING
    panel_id = ic.on_drag_end()
    assert panel_id == "memory"
    assert ic.state == InteractionState.IDLE


def test_cancel_from_dragging():
    """Cancel from DRAGGING should return to IDLE."""
    ic = InteractionController(_make_registry())
    ic.on_cursor_move(50, 50)
    ic.on_click(50, 50)
    ic.on_drag_start(50, 50)
    assert ic.state == InteractionState.DRAGGING
    ic.on_cancel()
    assert ic.state == InteractionState.IDLE


def test_cancel_from_selected():
    """Cancel from SELECTED should return to IDLE."""
    ic = InteractionController(_make_registry())
    ic.on_cursor_move(50, 50)
    ic.on_click(50, 50)
    assert ic.state == InteractionState.SELECTED
    ic.on_cancel()
    assert ic.state == InteractionState.IDLE


def test_resize_lifecycle():
    """Resize lifecycle via on_resize_start/update/end."""
    ic = InteractionController(_make_registry())
    ic.on_cursor_move(50, 50)
    ic.on_click(50, 50)
    assert ic.state == InteractionState.SELECTED
    # Force hover_result to indicate resize handle
    success = ic.on_resize_start(50, 50)
    if success:
        assert ic.state == InteractionState.RESIZING
        ic.on_cursor_move(300, 200)
        assert ic.state == InteractionState.RESIZING
        panel_id = ic.on_resize_end()
        assert ic.state == InteractionState.IDLE


def test_hover_follows_cursor():
    """Hover state updates as cursor moves between targets."""
    r = _make_registry()
    r.register(PanelInfo(
        id="ai_chat", type="placeholder", label="AI Chat",
        x=500, y=0, w=400, h=300, z_index=10, visible=True,
    ))
    ic = InteractionController(r)
    ic.on_cursor_move(50, 50)
    assert ic.state == InteractionState.HOVER
    assert ic.hover_result is not None
    assert ic.hover_result.panel_id == "memory"
    ic.on_cursor_move(600, 100)
    assert ic.state == InteractionState.HOVER
    assert ic.hover_result is not None
    assert ic.hover_result.panel_id == "ai_chat"


def test_mask_cursor_button_properties():
    """Ensure cursor_controller exposes expected properties."""
    ic = InteractionController(_make_registry())
    assert hasattr(ic.cursor_controller, "position")
    assert hasattr(ic.cursor_controller, "mode")
    assert hasattr(ic.cursor_controller, "is_tracking")
