"""Tests for Phase 7A/7B — Shell UI (Status Bar + Notification Center).

Covers:
    PerformanceSnapshot v2 readiness flags
    Plugin is_ready() implementations
    PerformancePlugin readiness aggregation
    StatusBarWidget (pure view renders snapshot + indicators)
    NotificationManager (event aggregator, ring buffer, dedupe)
    NotificationWidget (toast stack, FIFO, click -> command dispatch)
"""

from __future__ import annotations

import os

import pytest

from aether.core.event_bus_v2 import Event, EventBus
from aether.core.event_type import EventType
from aether.core.performance_snapshot import PerformanceSnapshot

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _flush(bus: EventBus) -> None:
    """Flush twice — events published during delivery land on the next flush."""
    bus.flush()
    bus.flush()


# ── PerformanceSnapshot v2 ─────────────────────────────────────────


class TestPerformanceSnapshotV2:
    def test_readiness_defaults_false(self):
        snap = PerformanceSnapshot()
        assert snap.camera_ready is False
        assert snap.vision_ready is False
        assert snap.memory_ready is False
        assert snap.ai_ready is False
        assert snap.voice_ready is False

    def test_readiness_can_be_set(self):
        snap = PerformanceSnapshot(camera_ready=True, memory_ready=True)
        assert snap.camera_ready is True
        assert snap.memory_ready is True
        assert snap.vision_ready is False

    def test_v1_fields_still_work(self):
        snap = PerformanceSnapshot(cpu_percent=50.0, plugins=4)
        assert snap.cpu_percent == 50.0
        assert snap.plugins == 4


# ── Plugin is_ready() ──────────────────────────────────────────────


class TestPluginReadiness:
    def test_camera_plugin_not_ready_before_initialize(self):
        from aether.phase_d.camera_plugin import CameraPlugin

        plugin = CameraPlugin()
        assert plugin.is_ready() is False

    def test_vision_adapter_not_ready_before_initialize(self):
        from aether.vision.plugins import VisionAdapterPlugin

        plugin = VisionAdapterPlugin()
        assert plugin.is_ready() is False

    def test_memory_plugin_not_ready_before_initialize(self):
        from aether.plugins.memory_plugin import MemoryPlugin

        plugin = MemoryPlugin()
        assert plugin.is_ready() is False


# ── PerformancePlugin readiness aggregation ────────────────────────


class _ReadyPlugin:
    def __init__(self, name, ready):
        self.name = name
        self._ready = ready

    def is_ready(self):
        return self._ready


class _NotReadyPlugin:
    name = "no_checker"


class TestPerformancePluginAggregation:
    def _make_plugin(self, loaded_plugins, queued=False):
        from aether.plugins.performance_plugin import PerformancePlugin

        bus = EventBus(queued=queued)
        from aether.core.service_container import ServiceContainer
        container = ServiceContainer()
        container.register_instance("event_bus", bus)

        class _Loader:
            def __init__(self):
                self.loaded_plugins = loaded_plugins

        container.register_instance("plugin_loader", _Loader())

        class _Registry:
            def panel_count(self):
                return 5

        container.register_instance("panel_registry", _Registry())

        plugin = PerformancePlugin()
        plugin.initialize(container)
        return plugin

    def test_aggregates_readiness_by_plugin_name(self):
        plugin = self._make_plugin([
            _ReadyPlugin("camera", True),
            _ReadyPlugin("vision_adapter", True),
            _ReadyPlugin("memory_plugin", True),
            _ReadyPlugin("ai", False),
            _ReadyPlugin("voice", False),
        ])
        snap = plugin._collect()
        assert snap.camera_ready is True
        assert snap.vision_ready is True
        assert snap.memory_ready is True
        assert snap.ai_ready is False
        assert snap.voice_ready is False

    def test_missing_plugins_default_false(self):
        plugin = self._make_plugin([])
        snap = plugin._collect()
        assert snap.camera_ready is False
        assert snap.vision_ready is False
        assert snap.memory_ready is False

    def test_plugins_without_checker_are_ignored(self):
        plugin = self._make_plugin([_NotReadyPlugin()])
        snap = plugin._collect()
        assert snap.camera_ready is False


# ── StatusBarWidget ────────────────────────────────────────────────


class TestStatusBarWidget:
    def test_renders_snapshot_metrics(self, qapp):
        from aether.ui.status_bar_widget import StatusBarWidget

        widget = StatusBarWidget()
        snap = PerformanceSnapshot(
            cpu_percent=42.3, memory_percent=33.0, camera_fps=30.0, hand_fps=0.0
        )
        widget.set_data(snap)
        assert widget._metrics["cpu_percent"].text() == "CPU 42"
        assert widget._metrics["memory_percent"].text() == "MEM 33"
        assert widget._metrics["camera_fps"].text() == "CAM 30"
        assert widget._metrics["hand_fps"].text() == "HAND 0"

    def test_indicator_colors_track_readiness(self, qapp):
        from aether.ui.status_bar_widget import StatusBarWidget

        widget = StatusBarWidget()
        snap = PerformanceSnapshot(camera_ready=True, memory_ready=True, vision_ready=False)
        widget.set_data(snap)
        assert "#22c55e" in widget._indicators["camera_ready"].styleSheet()
        assert "#22c55e" in widget._indicators["memory_ready"].styleSheet()
        assert "rgba(90, 100, 130, 160)" in widget._indicators["vision_ready"].styleSheet()

    def test_updates_on_metrics_event(self, qapp):
        from aether.ui.status_bar_widget import StatusBarWidget

        bus = EventBus(queued=False)
        widget = StatusBarWidget()
        widget.wire_services(None, bus)

        bus.publish(Event(
            type=EventType.SYSTEM_METRICS,
            payload=PerformanceSnapshot(cpu_percent=77.7, camera_ready=True),
            source="test",
        ))
        assert widget._metrics["cpu_percent"].text() == "CPU 78"
        assert "#22c55e" in widget._indicators["camera_ready"].styleSheet()

    def test_updates_layout_label_on_event(self, qapp):
        from aether.ui.status_bar_widget import StatusBarWidget

        bus = EventBus(queued=False)
        widget = StatusBarWidget()
        widget.wire_services(None, bus)

        bus.publish(Event(
            type=EventType.WORKSPACE_LOADED,
            payload={"name": "hand"},
            source="test",
        ))
        assert widget._layout_label.text() == "Layout: hand"

    def test_has_fixed_height(self, qapp):
        from aether.ui.status_bar_widget import StatusBarWidget

        widget = StatusBarWidget()
        assert widget.height() == StatusBarWidget.STATUS_HEIGHT


# ── NotificationManager (event aggregator) ─────────────────────────


class TestNotificationManagerAggregation:
    def test_translates_memory_created_event(self):
        mgr, bus = self._make_aggregator()
        received = []
        bus.subscribe(EventType.NOTIFICATION_CREATED, lambda e: received.append(e.payload))

        bus.publish(Event(
            type=EventType.MEMORY_CREATED,
            payload={"record": {"title": "My Note"}},
            source="test",
        ))
        _flush(bus)

        assert len(received) == 1
        assert received[0]["level"] == "success"
        assert "My Note" in received[0]["text"]
        assert received[0]["action"]["command"] == "ui.panel.focus"

    def test_translates_layout_loaded(self):
        mgr, bus = self._make_aggregator()
        received = []
        bus.subscribe(EventType.NOTIFICATION_CREATED, lambda e: received.append(e.payload))

        bus.publish(Event(type=EventType.LAYOUT_LOADED, payload={"name": "focus"}, source="test"))
        _flush(bus)

        assert received and "focus" in received[0]["text"]
        assert received[0]["level"] == "info"

    def test_translates_error_levels(self):
        mgr, bus = self._make_aggregator()
        received = []
        bus.subscribe(EventType.NOTIFICATION_CREATED, lambda e: received.append(e.payload))

        bus.publish(Event(type=EventType.PLUGIN_ERROR, payload={"message": "boom"}, source="test"))
        _flush(bus)

        assert received and received[0]["level"] == "error"
        assert "boom" in received[0]["text"]

    def test_ignores_unmapped_events(self):
        mgr, bus = self._make_aggregator()
        received = []
        bus.subscribe(EventType.NOTIFICATION_CREATED, lambda e: received.append(e.payload))

        bus.publish(Event(type=EventType.SYSTEM_TICK, payload={}, source="test"))
        _flush(bus)

        assert received == []

    def test_notify_publishes_created_event(self):
        mgr, bus = self._make_aggregator()
        received = []
        bus.subscribe(EventType.NOTIFICATION_CREATED, lambda e: received.append(e.payload))

        mgr.notify("Manual message", level="warning")
        _flush(bus)

        assert len(received) == 1
        assert received[0]["text"] == "Manual message"
        assert received[0]["level"] == "warning"

    def test_ring_buffer_caps_history(self):
        from aether.ui.panel.notification_manager import NotificationManager

        mgr = NotificationManager()
        for i in range(150):
            mgr.publish(f"msg {i}")
        assert len(mgr.get_all()) == NotificationManager.RING_BUFFER_SIZE

    def test_dedupe_within_window(self):
        from aether.ui.panel.notification_manager import NotificationManager

        mgr = NotificationManager()
        a = mgr.publish("same text")
        b = mgr.publish("same text")
        assert a.id == b.id  # duplicate suppressed
        assert mgr.count() == 1

    def test_notify_with_action(self):
        mgr, bus = self._make_aggregator()
        notif = mgr.notify("Go to memory", action={"command": "ui.panel.focus", "params": {}})
        assert notif.action["command"] == "ui.panel.focus"

    @staticmethod
    def _make_aggregator():
        from aether.ui.panel.notification_manager import NotificationManager

        bus = EventBus(queued=True)
        mgr = NotificationManager(event_bus=bus)
        return mgr, bus


# ── NotificationWidget ─────────────────────────────────────────────


class _FakeCommandBus:
    def __init__(self):
        self.dispatched = []

    def dispatch(self, command):
        self.dispatched.append((command.name, dict(command.params), command.source))


class TestNotificationWidget:
    def test_add_notification_creates_toast(self, qapp):
        from PySide6.QtWidgets import QWidget

        from aether.ui.notification_widget import NotificationWidget

        parent = QWidget()
        widget = NotificationWidget(parent)
        widget.add_notification({"text": "Hello", "level": "info", "duration": 0})
        assert widget.toast_count == 1

    def test_max_visible_fifo_eviction(self, qapp):
        from PySide6.QtWidgets import QWidget

        from aether.ui.notification_widget import NotificationWidget

        parent = QWidget()
        widget = NotificationWidget(parent)
        widget.configure(max_visible=3)
        for i in range(5):
            widget.add_notification({"text": f"toast {i}", "level": "info", "duration": 0})
        assert widget.toast_count == 3
        # FIFO — oldest were evicted
        assert widget._toasts[0]._payload["text"] == "toast 2"

    def test_clear(self, qapp):
        from PySide6.QtWidgets import QWidget

        from aether.ui.notification_widget import NotificationWidget

        parent = QWidget()
        widget = NotificationWidget(parent)
        widget.add_notification({"text": "a", "level": "info", "duration": 0})
        widget.add_notification({"text": "b", "level": "info", "duration": 0})
        assert widget.clear() == 2
        assert widget.toast_count == 0

    def test_click_dispatches_action_command(self, qapp):
        from PySide6.QtWidgets import QWidget

        from aether.ui.notification_widget import NotificationWidget

        parent = QWidget()
        widget = NotificationWidget(parent)
        bus = _FakeCommandBus()
        widget.wire_services(bus, None)
        widget.add_notification({
            "text": "Open memory",
            "level": "success",
            "duration": 0,
            "action": {"command": "ui.panel.focus", "params": {"panel_id": "memory"}},
        })
        toast = widget._toasts[0]
        toast._activate()
        assert bus.dispatched == [("ui.panel.focus", {"panel_id": "memory"}, "notification")]

    def test_subscribes_to_created_event(self, qapp):
        from PySide6.QtWidgets import QWidget

        from aether.ui.notification_widget import NotificationWidget

        parent = QWidget()
        widget = NotificationWidget(parent)
        bus = EventBus(queued=False)
        widget.wire_services(_FakeCommandBus(), bus)

        bus.publish(Event(
            type=EventType.NOTIFICATION_CREATED,
            payload={"text": "from event", "level": "info", "duration": 0},
            source="test",
        ))
        assert widget.toast_count == 1
