"""Tests for the AI Chat panel's "Continue My Work" button (M1 Memory UX)."""

from __future__ import annotations

import pytest

from aether.core.command_bus import CommandBus
from aether.core.event_bus_v2 import EventBus
from aether.ui.panel.ai_chat_widget import AIChatPanelWidget


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def buses():
    return CommandBus(), EventBus(queued=False)


def _make_widget(qapp, command_bus=None, event_bus=None):
    widget = AIChatPanelWidget("chat1", "ai_chat", "AI Chat")
    if command_bus is not None or event_bus is not None:
        widget.wire_services(command_bus, event_bus)
    return widget


class TestContinueButtonPresence:
    def test_build_content_creates_continue_button(self, qapp):
        widget = _make_widget(qapp)
        assert widget._continue_btn is not None
        assert widget._continue_btn.text() == "Continue My Work"
        widget.deleteLater()

    def test_button_click_without_bus_is_graceful(self, qapp):
        widget = _make_widget(qapp)
        widget._continue_btn.click()
        text = widget._history.toPlainText()
        assert "Continue My Work" in text
        widget.deleteLater()


class TestContinueButtonDispatch:
    def test_click_dispatches_memory_continue_and_appends(self, qapp, buses):
        command_bus, event_bus = buses
        command_bus.register_handler(
            "memory.continue",
            lambda c: {
                "message": (
                    "You were working on C3 cleanup in the Aether repo. "
                    "Remembered: Need to fix layout manager paths. Ready to continue."
                )
            },
        )
        widget = _make_widget(qapp, command_bus, event_bus)
        widget._continue_btn.click()
        text = widget._history.toPlainText()
        assert "You were working on C3 cleanup in the Aether repo." in text
        assert "Need to fix layout manager paths" in text
        assert "Ready to continue." in text
        widget.deleteLater()

    def test_click_renders_no_session_guidance(self, qapp, buses):
        command_bus, event_bus = buses
        command_bus.register_handler(
            "memory.continue", lambda c: {"message": "No work session found. Start one..."}
        )
        widget = _make_widget(qapp, command_bus, event_bus)
        widget._continue_btn.click()
        assert "No work session found" in widget._history.toPlainText()
        widget.deleteLater()

    def test_click_handles_empty_result(self, qapp, buses):
        command_bus, event_bus = buses
        command_bus.register_handler("memory.continue", lambda c: {})
        widget = _make_widget(qapp, command_bus, event_bus)
        widget._continue_btn.click()
        assert "no work context was recovered" in widget._history.toPlainText()
        widget.deleteLater()