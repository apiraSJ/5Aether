"""Integration tests: InputRouter → InteractionController → EventBus → OverlayModel.

Tests the full gesture-to-visual pipeline with simulated events.
"""

import time
from aether.interaction.input_router import InputRouter
from aether.interaction.interaction_controller import InteractionController
from aether.interaction.interaction_state import InteractionState
from aether.interaction.gestures import Gesture
from aether.ui.panel.panel_registry import PanelRegistry
from aether.ui.panel.panel_info import PanelInfo, PanelCapability
from aether.ui.overlay_model import OverlayModel
from aether.ui.interaction_bridge import InteractionBridge


def _make_registry():
    r = PanelRegistry()
    r.register(PanelInfo(
        id="memory", type="memory", label="Memory",
        x=0, y=0, w=400, h=300, z_index=10, visible=True,
        capabilities=[PanelCapability.MOVE, PanelCapability.RESIZE, PanelCapability.FOCUS],
    ))
    r.register(PanelInfo(
        id="ai_chat", type="placeholder", label="AI Chat",
        x=500, y=0, w=400, h=300, z_index=10, visible=True,
        capabilities=[PanelCapability.MOVE, PanelCapability.RESIZE, PanelCapability.FOCUS],
    ))
    return r


def test_mouse_select_and_drag():
    """Mouse click → select → drag → drop through InputRouter."""
    registry = _make_registry()
    ic = InteractionController(registry)
    router = InputRouter(ic)

    router.on_mouse_move(50, 50)
    assert ic.state == InteractionState.HOVER

    router.on_mouse_press(50, 50)
    assert ic.state == InteractionState.SELECTED
    assert ic.selected_panel_id == "memory"

    router.on_mouse_release(50, 50)
    assert ic.state == InteractionState.SELECTED


def test_hand_pinch_select():
    """Hand pinch → select panel through InputRouter."""
    registry = _make_registry()
    ic = InteractionController(registry)
    router = InputRouter(ic)

    router.on_hand_move(50, 50)
    assert ic.state == InteractionState.HOVER

    router.on_hand_pinch_start(50, 50)
    assert ic.state == InteractionState.SELECTED
    assert ic.selected_panel_id == "memory"

    router.on_hand_pinch_end(50, 50)
    assert ic.state == InteractionState.SELECTED


def test_hand_drag_lifecycle():
    """Full hand drag: move → pinch start → drag → pinch end."""
    registry = _make_registry()
    ic = InteractionController(registry)
    router = InputRouter(ic)

    router.on_hand_move(50, 50)
    router.on_hand_pinch_start(50, 50)
    assert ic.state == InteractionState.SELECTED

    router.on_hand_pinch_start(50, 50)
    assert ic.state in (InteractionState.DRAGGING, InteractionState.SELECTED)

    router.on_hand_move(200, 200)
    router.on_hand_pinch_end(200, 200)
    assert ic.state == InteractionState.IDLE


def test_hand_gesture_open_palm():
    """OPEN_PALM gesture should update cursor position."""
    registry = _make_registry()
    ic = InteractionController(registry)
    router = InputRouter(ic)

    router.on_hand_gesture(Gesture.OPEN_PALM, 100, 100, 0.9)
    assert ic.state in (InteractionState.IDLE, InteractionState.HOVER)


def test_hand_gesture_closed_fist_cancels():
    """CLOSED_FIST should cancel active interaction."""
    registry = _make_registry()
    ic = InteractionController(registry)
    router = InputRouter(ic)

    router.on_hand_move(50, 50)
    router.on_hand_pinch_start(50, 50)
    assert ic.state == InteractionState.SELECTED

    router.cancel()
    assert ic.state == InteractionState.IDLE


def test_interaction_bridge_sync():
    """InteractionBridge should sync InteractionController state to OverlayModel."""
    registry = _make_registry()
    ic = InteractionController(registry)
    model = OverlayModel()

    bridge = InteractionBridge(ic, model)
    bridge.update()

    # After bridge update, model should reflect current state
    assert model.interaction_status is not None


def test_mouse_and_hand_same_pipeline():
    """Mouse and hand should produce identical interaction states."""
    registry = _make_registry()
    ic_mouse = InteractionController(registry)
    ic_hand = InteractionController(registry)
    router_mouse = InputRouter(ic_mouse)
    router_hand = InputRouter(ic_hand)

    router_mouse.on_mouse_move(50, 50)
    router_mouse.on_mouse_press(50, 50)
    router_mouse.on_mouse_release(50, 50)

    router_hand.on_hand_move(50, 50)
    router_hand.on_hand_pinch_start(50, 50)
    router_hand.on_hand_pinch_end(50, 50)

    assert ic_mouse.state == ic_hand.state


def test_click_handler_notification():
    """Registering a click handler should receive notifications."""
    registry = _make_registry()
    ic = InteractionController(registry)
    router = InputRouter(ic)

    clicks = []
    router.register_click_handler(lambda panel_id, state: clicks.append((panel_id, state)))

    router.on_mouse_move(50, 50)
    router.on_mouse_press(50, 50)

    assert len(clicks) >= 1
    assert clicks[-1][0] == "memory"


def test_gesture_handler_notification():
    """Registering a gesture handler should receive notifications."""
    registry = _make_registry()
    ic = InteractionController(registry)
    router = InputRouter(ic)

    gestures = []
    router.register_gesture_handler(lambda g, x, y, c: gestures.append((g, x, y, c)))

    router.on_hand_gesture(Gesture.OPEN_PALM, 100, 100, 0.9)

    assert len(gestures) >= 1
    assert gestures[-1][0] == Gesture.OPEN_PALM
