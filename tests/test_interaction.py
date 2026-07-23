"""Tests for interaction module — StateMachine, FocusManager, InteractionManager."""

import pytest
from unittest.mock import MagicMock, patch
from interaction.state_machine import InteractionStateMachine, InteractionState
from interaction.focus_manager import FocusManager, FocusableWidget
from interaction.interaction_manager import InteractionManager
from core.cursor_manager import CursorManager
from interface.ui_manager import UIManager
from core.event_bus import EventBus, EventType


class TestStateMachine:
    def test_initial_state(self):
        sm = InteractionStateMachine()
        assert sm.state == InteractionState.IDLE
        assert sm.is_idle

    def test_hand_detected_transitions_to_tracking(self):
        sm = InteractionStateMachine()
        sm.hand_detected()
        assert sm.state == InteractionState.TRACKING

    def test_menu_open_transitions_to_menu_open(self):
        sm = InteractionStateMachine()
        sm.hand_detected()
        sm.menu_opened()
        assert sm.state == InteractionState.MENU_OPEN

    def test_menu_close_transitions_to_tracking(self):
        sm = InteractionStateMachine()
        sm.hand_detected()
        sm.menu_opened()
        sm.menu_closed()
        assert sm.state == InteractionState.TRACKING

    def test_panel_open(self):
        sm = InteractionStateMachine()
        sm.hand_detected()
        sm.panel_opened("system")
        assert sm.state == InteractionState.PANEL_OPEN
        assert sm.active_panel == "system"

    def test_panel_close(self):
        sm = InteractionStateMachine()
        sm.hand_detected()
        sm.panel_opened("system")
        sm.panel_closed()
        assert sm.state == InteractionState.TRACKING

    def test_hand_lost_from_tracking(self):
        sm = InteractionStateMachine()
        sm.hand_detected()
        sm.hand_lost()
        assert sm.state == InteractionState.IDLE

    def test_hand_lost_from_menu(self):
        sm = InteractionStateMachine()
        sm.hand_detected()
        sm.menu_opened()
        sm.hand_lost()
        assert sm.state == InteractionState.IDLE

    def test_handler_called(self):
        sm = InteractionStateMachine()
        handler = MagicMock()
        sm.on(InteractionState.TRACKING, handler)
        sm.hand_detected()
        handler.assert_called_once()

    def test_same_state_no_transition(self):
        sm = InteractionStateMachine()
        handler = MagicMock()
        sm.on(InteractionState.IDLE, handler)
        sm.hand_lost()  # Already IDLE
        handler.assert_not_called()


class TestFocusManager:
    def test_no_focus_initially(self):
        fm = FocusManager()
        assert not fm.has_focus
        assert fm.focused_name is None

    def test_register_and_hit_test(self):
        fm = FocusManager()
        widget = FocusableWidget("btn1", (100, 100, 200, 200))
        fm.register(widget)
        result = fm.update(150, 150)
        assert result == "btn1"
        assert fm.has_focus

    def test_outside_bounds(self):
        fm = FocusManager()
        widget = FocusableWidget("btn1", (100, 100, 200, 200))
        fm.register(widget)
        result = fm.update(50, 50)
        assert result is None
        assert not fm.has_focus

    def test_blur_on_leave(self):
        fm = FocusManager()
        blur_mock = MagicMock()
        widget = FocusableWidget("btn1", (100, 100, 200, 200), on_blur=blur_mock)
        fm.register(widget)
        fm.update(150, 150)
        fm.update(50, 50)
        blur_mock.assert_called_once()

    def test_select(self):
        fm = FocusManager()
        select_mock = MagicMock()
        widget = FocusableWidget("btn1", (100, 100, 200, 200), on_select=select_mock)
        fm.register(widget)
        fm.update(150, 150)
        result = fm.select()
        assert result == "btn1"
        select_mock.assert_called_once()

    def test_unregister(self):
        fm = FocusManager()
        widget = FocusableWidget("btn1", (100, 100, 200, 200))
        fm.register(widget)
        fm.unregister("btn1")
        result = fm.update(150, 150)
        assert result is None


class TestInteractionManager:
    @patch("interaction.interaction_manager.UIManager")
    @patch("interaction.interaction_manager.CursorManager")
    def test_init(self, mock_cursor, mock_ui):
        bus = EventBus()
        im = InteractionManager(mock_cursor, mock_ui, bus)
        assert im.state.is_idle

    @patch("interaction.interaction_manager.UIManager")
    @patch("interaction.interaction_manager.CursorManager")
    def test_menu_open_event(self, mock_cursor, mock_ui):
        bus = EventBus()
        im = InteractionManager(mock_cursor, mock_ui, bus)
        bus.emit_simple(EventType.MENU_OPEN, {})
        assert im.state.is_menu_open

    @patch("interaction.interaction_manager.UIManager")
    @patch("interaction.interaction_manager.CursorManager")
    def test_menu_close_event(self, mock_cursor, mock_ui):
        bus = EventBus()
        im = InteractionManager(mock_cursor, mock_ui, bus)
        bus.emit_simple(EventType.MENU_OPEN, {})
        bus.emit_simple(EventType.MENU_CLOSE, {})
        assert im.state.is_tracking

    @patch("interaction.interaction_manager.UIManager")
    @patch("interaction.interaction_manager.CursorManager")
    def test_update_tracks_hand(self, mock_cursor, mock_ui):
        bus = EventBus()
        mock_cursor.visible = True
        mock_cursor.position = (500, 500)
        im = InteractionManager(mock_cursor, mock_ui, bus)
        im.update()
        assert im.state.is_tracking

    @patch("interaction.interaction_manager.UIManager")
    @patch("interaction.interaction_manager.CursorManager")
    def test_update_hand_lost(self, mock_cursor, mock_ui):
        bus = EventBus()
        mock_cursor.visible = True
        mock_cursor.position = (500, 500)
        im = InteractionManager(mock_cursor, mock_ui, bus)
        im.update()
        mock_cursor.visible = False
        im.update()
        assert im.state.is_idle
