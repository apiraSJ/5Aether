"""Test virtual cursor service and widget."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from aether.core.virtual_cursor import VirtualCursor, CursorState
from aether.ui.cursor_widget import CursorWidget
from aether.ui.overlay_model import OverlayModel
from aether.core.service_container import ServiceContainer

app = QApplication.instance() or QApplication([])


class MockEventBus:
    """Mock event bus for testing."""
    def subscribe(self, topic, handler):
        pass


class MockCommandBus:
    """Mock command bus for testing."""
    def __init__(self):
        self.dispatched = []

    def dispatch(self, cmd):
        self.dispatched.append(cmd)


def test_virtual_cursor_initialization():
    """Test VirtualCursor initialization."""
    container = ServiceContainer()

    cursor = VirtualCursor()
    cursor.initialize(MockEventBus(), MockCommandBus())

    # Test initial state
    assert cursor._dragging == False
    assert cursor._drag_target is None
    print("✓ VirtualCursor initialization test passed")


def test_virtual_cursor_position_update():
    """Test cursor position update."""
    container = ServiceContainer()
    cursor = VirtualCursor()
    cursor.initialize(MockEventBus(), MockCommandBus())

    # Update position
    cursor.update_position(0.5, 0.5, 1920, 1080)

    assert cursor._position.x == 0.5
    assert cursor._position.y == 0.5
    assert cursor._position.screen_x == 960
    assert cursor._position.screen_y == 540
    print("✓ VirtualCursor position update test passed")


def test_virtual_cursor_drag_start():
    """Test drag start handling."""
    container = ServiceContainer()
    mock_cmd_bus = MockCommandBus()
    cursor = VirtualCursor()
    cursor.initialize(MockEventBus(), mock_cmd_bus)

    # Start drag
    cursor.set_drag_state(CursorState.DRAG_START, None)

    assert cursor._dragging == True
    assert len(mock_cmd_bus.dispatched) == 1
    assert mock_cmd_bus.dispatched[0].name == "cursor_drag_start"
    print("✓ VirtualCursor drag start test passed")


def test_virtual_cursor_drag_end():
    """Test drag end handling."""
    container = ServiceContainer()
    mock_cmd_bus = MockCommandBus()
    cursor = VirtualCursor()
    cursor.initialize(MockEventBus(), mock_cmd_bus)

    # End drag
    cursor.set_drag_state(CursorState.DRAG_END, None)

    assert cursor._dragging == False
    assert len(mock_cmd_bus.dispatched) == 1
    assert mock_cmd_bus.dispatched[0].name == "cursor_drag_end"
    print("✓ VirtualCursor drag end test passed")


def test_cursor_widget_initialization():
    """Test CursorWidget initialization."""
    model = OverlayModel()
    widget = CursorWidget(model)

    assert widget._cursor_x == 0.5
    assert widget._cursor_y == 0.5
    assert widget._cursor_state == "idle"
    print("✓ CursorWidget initialization test passed")


def test_cursor_widget_set_state():
    """Test CursorWidget state updates."""
    model = OverlayModel()
    widget = CursorWidget(model)

    model.update_cursor(0.3, 0.7, state=model.cursor.state.__class__.DRAG_START)
    model._cursor.selection_glow = False
    widget.update()

    assert widget._cursor_state == "drag_start"
    assert widget._cursor_x == 0.3
    assert widget._cursor_y == 0.7
    print("✓ CursorWidget state update test passed")


def test_cursor_widget_mouse_events():
    """Test that widget ignores mouse events."""
    model = OverlayModel()
    widget = CursorWidget(model)

    # Widget should have transparent mouse events
    assert widget.testAttribute(Qt.WA_TransparentForMouseEvents) is True
    print("✓ CursorWidget mouse event transparency test passed")


if __name__ == "__main__":
    # Run tests
    test_virtual_cursor_initialization()
    test_virtual_cursor_position_update()
    test_virtual_cursor_drag_start()
    test_virtual_cursor_drag_end()
    test_cursor_widget_initialization()
    test_cursor_widget_set_state()
    test_cursor_widget_mouse_events()

    print("\n✅ All virtual cursor tests passed!")