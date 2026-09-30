"""Tests for Sprint 2.1A.5 UI features:
    PerformancePlugin (SYSTEM_METRICS snapshot)
    Dashboard widget (pure view renders snapshot)
    Tasks panel (add + PanelSession persistence)
    Command palette (entries + dispatch)
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from aether.core.event_bus_v2 import Event, EventBus
from aether.core.event_type import EventType
from aether.core.performance_snapshot import PerformanceSnapshot
from aether.core.service_container import ServiceContainer

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


# ── PerformancePlugin ──────────────────────────────────────────────


class TestPerformancePlugin:
    def test_publishes_snapshot_on_interval(self):
        from aether.plugins.performance_plugin import PerformancePlugin

        bus = EventBus(queued=True)
        container = ServiceContainer()
        container.register_instance("event_bus", bus)

        class _Loader:
            loaded_plugins = ["a", "b", "c"]

        container.register_instance("plugin_loader", _Loader())

        class _Registry:
            def panel_count(self):
                return 4

        container.register_instance("panel_registry", _Registry())

        plugin = PerformancePlugin()
        plugin.initialize(container)

        # < interval → no snapshot yet
        plugin.update(0.2)
        assert plugin.last_snapshot is None

        # accumulate past interval → snapshot published
        plugin.update(0.31)
        assert plugin.last_snapshot is not None
        assert bus.queue_size() == 1

        event = bus._queue[0]
        assert event.type == EventType.SYSTEM_METRICS
        payload = event.payload
        assert isinstance(payload, PerformanceSnapshot)
        assert payload.plugins == 3
        assert payload.panels == 4

    def test_snapshot_missing_services_defaults_zero(self):
        from aether.plugins.performance_plugin import PerformancePlugin

        bus = EventBus(queued=False)
        container = ServiceContainer()
        container.register_instance("event_bus", bus)

        received = []

        def _on(event):
            received.append(event.payload)

        bus.subscribe(EventType.SYSTEM_METRICS, _on)

        plugin = PerformancePlugin()
        plugin.initialize(container)
        plugin.update(0.5)
        assert received
        assert received[0].plugins == 0
        assert received[0].panels == 0


# ── Dashboard widget ───────────────────────────────────────────────


class TestDashboardWidget:
    def test_renders_snapshot(self, qapp):
        from aether.ui.panel.dashboard_widget import DashboardPanelWidget

        widget = DashboardPanelWidget("dashboard", "dashboard", "Dashboard")
        snapshot = PerformanceSnapshot(
            cpu_percent=12.7, memory_percent=44.2, plugins=6, panels=5
        )
        widget.set_data(snapshot)
        assert widget._cards["cpu_percent"]._value_widget.text() == "13"
        assert widget._cards["memory_percent"]._value_widget.text() == "44"
        assert widget._cards["plugins"]._value_widget.text() == "6"
        assert widget._cards["panels"]._value_widget.text() == "5"

    def test_subscribes_and_updates_on_event(self, qapp):
        from aether.ui.panel.dashboard_widget import DashboardPanelWidget

        bus = EventBus(queued=False)
        widget = DashboardPanelWidget("dashboard", "dashboard", "Dashboard")
        widget.wire_services(None, bus)

        bus.publish(Event(
            type=EventType.SYSTEM_METRICS,
            payload=PerformanceSnapshot(cpu_percent=33.3, plugins=8),
            source="test",
        ))
        assert widget._cards["cpu_percent"]._value_widget.text() == "33"
        assert widget._cards["plugins"]._value_widget.text() == "8"


# ── Tasks panel ────────────────────────────────────────────────────


class TestTasksPanel:
    def test_add_task_and_save_session(self, qapp):
        from aether.ui.panel.panel_session import PanelSession
        from aether.ui.panel.tasks_widget import TasksPanelWidget

        widget = TasksPanelWidget("tasks", "tasks", "Tasks")
        session = PanelSession(panel_id="tasks", panel_type="tasks")
        widget.bind_session(session)

        count_before = widget._list.count()
        widget._input.setText("Ship 2.1A.5")
        widget._on_add_task()

        saved = session.load_state("tasks")
        assert len(saved) == count_before + 1
        assert saved[-1]["label"] == "Ship 2.1A.5"
        assert saved[-1]["done"] is False

    def test_restores_from_session(self, qapp):
        from aether.ui.panel.panel_session import PanelSession
        from aether.ui.panel.tasks_widget import TasksPanelWidget

        session = PanelSession(panel_id="tasks", panel_type="tasks")
        session.save_state("tasks", [{"label": "Persisted", "done": True}])

        widget = TasksPanelWidget("tasks", "tasks", "Tasks")
        widget.bind_session(session)
        assert widget._list.count() == 1
        item = widget._list.item(0)
        assert item.text() == "Persisted"

    def test_toggle_persists(self, qapp):
        from PySide6.QtCore import Qt

        from aether.ui.panel.panel_session import PanelSession
        from aether.ui.panel.tasks_widget import TasksPanelWidget

        widget = TasksPanelWidget("tasks", "tasks", "Tasks")
        session = PanelSession(panel_id="tasks", panel_type="tasks")
        widget.bind_session(session)

        # "Memory panel content" (index 2) starts Unchecked → toggle fires itemChanged
        item = widget._list.item(2)
        assert item.checkState() == Qt.Unchecked
        item.setCheckState(Qt.Checked)
        saved = session.load_state("tasks")
        assert saved[2]["done"] is True


# ── Command palette ────────────────────────────────────────────────


class _FakeCommandBus:
    def __init__(self):
        self.dispatched = []

    def dispatch(self, command):
        self.dispatched.append((command.name, dict(command.params)))


class _FakeCommandRegistry:
    def get_categories(self):
        return ["system"]

    def get_commands_in_category(self, category):
        return ["system.status"]

    def resolve(self, name):
        from aether.core.command_registry import CommandInfo
        return CommandInfo(name=name, description="Check status", category="system")


class _FakePanelRegistry:
    def list_all(self):
        from aether.ui.panel.panel_info import PanelInfo
        return [
            PanelInfo(id="memory", type="memory", label="Memory", x=0, y=0, w=10, h=10, visible=True),
            PanelInfo(id="camera_panel", type="camera", label="Camera", x=0, y=0, w=10, h=10, visible=True),
        ]


class _FakeWorkspaceManager:
    def list_layouts(self):
        return ["default"]

    def current_layout(self):
        return "default"

    def load_layout(self, name):
        return True


class TestCommandPalette:
    def test_collects_entries_from_services(self, qapp):
        from aether.ui.command_palette_widget import CommandPaletteWidget

        palette = CommandPaletteWidget()
        palette.wire_services(
            command_bus=_FakeCommandBus(),
            command_registry=_FakeCommandRegistry(),
            panel_registry=_FakePanelRegistry(),
            workspace_manager=_FakeWorkspaceManager(),
        )
        palette.refresh()

        sections = {e.section for e in palette.entries}
        assert "Commands" in sections
        assert "Panels" in sections
        assert "Layouts" in sections
        assert "Memory" in sections
        # camera_panel is excluded from palette
        assert not any(e.title == "camera_panel" for e in palette.entries)

    def test_filter_by_query(self, qapp):
        from aether.ui.command_palette_widget import CommandPaletteWidget

        palette = CommandPaletteWidget()
        palette.wire_services(
            command_bus=_FakeCommandBus(),
            command_registry=_FakeCommandRegistry(),
            panel_registry=_FakePanelRegistry(),
            workspace_manager=_FakeWorkspaceManager(),
        )
        palette.refresh()
        palette._search.setText("system")
        assert palette._results.count() >= 1
        for i in range(palette._results.count()):
            assert "system" in palette._results.item(i).text().lower()

    def test_execute_dispatches_command(self, qapp):
        from aether.ui.command_palette_widget import CommandPaletteWidget, PaletteEntry

        bus = _FakeCommandBus()
        palette = CommandPaletteWidget()
        palette.wire_services(command_bus=bus)
        palette._execute(PaletteEntry(
            section="Commands", title="system.status",
            command="system.status",
        ))
        assert bus.dispatched == [("system.status", {})]
        assert palette._recent == ["system.status"]

    def test_recent_appears_in_entries(self, qapp):
        from aether.ui.command_palette_widget import CommandPaletteWidget, PaletteEntry

        palette = CommandPaletteWidget()
        palette.wire_services(command_bus=_FakeCommandBus())
        palette._execute(PaletteEntry(section="Commands", title="a.cmd", command="a.cmd"))
        palette.refresh()
        assert any(e.section == "Recent" and e.command == "a.cmd" for e in palette.entries)
