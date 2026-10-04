"""Tests for the Baseline panel widget — slots, capture, catalog rendering (M1)."""

from __future__ import annotations

import pytest

from aether.core.command import Command
from aether.core.command_bus import CommandBus
from aether.core.event_bus_v2 import EventBus
from aether.sandbox.catalog import COMPONENTS
from aether.ui.panel.baseline_widget import BaselinePanelWidget


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def buses():
    return CommandBus(), EventBus(queued=False)


def _make_widget(qapp, command_bus=None, event_bus=None):
    widget = BaselinePanelWidget("baseline", "baseline", "Baseline")
    if command_bus is not None or event_bus is not None:
        widget.wire_services(command_bus, event_bus)
    return widget


def _register_list_handler(command_bus, entries):
    command_bus.register_handler("baseline.list", lambda c: {"baselines": entries})


class TestWidgetPresence:
    def test_build_content_creates_slots_for_each_component(self, qapp):
        widget = _make_widget(qapp)
        for comp in COMPONENTS:
            slot = getattr(widget, f"_slot_{comp['id']}")
            assert slot is not None
            assert slot.text() == comp["id"]
        widget.deleteLater()

    def test_build_content_creates_capture_button(self, qapp):
        widget = _make_widget(qapp)
        assert widget._capture_btn is not None
        assert widget._capture_btn.text() == "Capture"
        widget.deleteLater()

    def test_build_content_shows_status_label(self, qapp):
        widget = _make_widget(qapp)
        assert widget._status is not None
        assert "No component selected" in widget._status.text()
        widget.deleteLater()


class TestSelectInteraction:
    def test_click_slot_dispatches_select_and_updates_status(self, qapp, buses):
        command_bus, event_bus = buses
        command_bus.register_handler(
            "baseline.select",
            lambda c: {"message": "Selected component 1: Circuit Breaker Panel (CB-100)"},
        )
        widget = _make_widget(qapp, command_bus, event_bus)
        widget._slot_1.click()
        assert "Circuit Breaker" in widget._status.text()
        assert widget._selected_id == "1"
        widget.deleteLater()

    def test_click_without_bus_is_graceful(self, qapp):
        widget = _make_widget(qapp)
        widget._slot_1.click()
        assert "Selected component 1" in widget._status.text()
        widget.deleteLater()

    def test_capture_without_selection_asks_to_select(self, qapp, buses):
        command_bus, event_bus = buses
        widget = _make_widget(qapp, command_bus, event_bus)
        widget._capture_btn.click()
        assert "Select a component" in widget._status.text()
        widget.deleteLater()


class TestCaptureInteraction:
    def test_capture_dispatches_and_renders(self, qapp, buses):
        command_bus, event_bus = buses
        _register_list_handler(command_bus, [])
        command_bus.register_handler(
            "baseline.select",
            lambda c: {"message": f"Selected component {c.params['component_id']}: X"},
        )
        command_bus.register_handler(
            "baseline.capture",
            lambda c: {"message": "Captured X → data/baseline_snapshots/1.png"},
        )
        widget = _make_widget(qapp, command_bus, event_bus)
        widget._slot_1.click()
        widget._capture_btn.click()
        assert "Captured X" in widget._status.text()
        assert "Baseline catalog:" in widget._list.toPlainText()
        widget.deleteLater()


class TestRefreshRendering:
    def test_refresh_renders_entries(self, qapp, buses):
        command_bus, event_bus = buses
        _register_list_handler(command_bus, [
            {"component_id": "1", "name": "Circuit Breaker Panel (CB-100)", "captured": True},
            {"component_id": "2", "name": "Backup Power Supply (BPS-200)", "captured": False},
        ])
        widget = _make_widget(qapp, command_bus, event_bus)
        widget.refresh()
        text = widget._list.toPlainText()
        assert "Circuit Breaker" in text
        assert "captured" in text
        widget.deleteLater()

    def test_refresh_without_handler_is_graceful(self, qapp, buses):
        command_bus, event_bus = buses
        widget = _make_widget(qapp, command_bus, event_bus)
        widget.refresh()
        assert widget._list.toPlainText() == ""
        widget.deleteLater()

    def test_captured_event_triggers_refresh(self, qapp, buses):
        command_bus, event_bus = buses
        _register_list_handler(command_bus, [
            {"component_id": "1", "name": "Circuit Breaker Panel (CB-100)", "captured": True},
        ])
        widget = _make_widget(qapp, command_bus, event_bus)
        from aether.core.event_bus_v2 import Event
        from aether.core.event_type import EventType
        event_bus.publish(Event(
            type=EventType.BASELINE_CAPTURED,
            payload={"component_id": "1", "name": "Circuit Breaker Panel (CB-100)",
                     "snapshot_path": "data/baseline_snapshots/1.png", "captured_at": "t"},
            source="baseline_plugin",
        ))
        assert "Circuit Breaker" in widget._list.toPlainText()
        widget.deleteLater()