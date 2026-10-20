"""Tests for Sprint 2.5 performance measurement tooling.

Covers:
    Profiler 1-second window semantics (non-destructive snapshot, rolling)
    Profiler repaint counter + Qt event-loop timing
    EventBus metrics (published/delivered/orphans, per-type, rates)
    HUDManager layer-4 throttling
    CameraWidget timer pause when hidden
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ── Profiler window semantics ───────────────────────────────────────


class TestProfilerWindows:
    def test_snapshot_is_non_destructive(self):
        from aether.core.profiler import Profiler

        p = Profiler()
        p._record_stage("camera", 5.0)
        p._record_stage("camera", 15.0)

        snap1 = p.snapshot()
        assert snap1.stages["camera"]["avg_ms"] == 10.0
        assert snap1.stages["camera"]["fps"] == 2.0

        # Reading again must NOT reset the window
        snap2 = p.snapshot()
        assert snap2.stages["camera"]["avg_ms"] == 10.0
        assert snap2.stages["camera"]["fps"] == 2.0

    def test_windows_roll_on_one_second_cadence(self):
        from aether.core.profiler import Profiler

        p = Profiler()
        p._record_stage("camera", 5.0)
        p._record_stage("camera", 15.0)
        p._record_stage("camera", 25.0)

        # Backdate the roll start so the next snapshot closes the window
        p._window_roll_start -= 1.5
        snap = p.snapshot()
        assert snap.stages["camera"]["avg_ms"] == 15.0  # avg of all three
        assert snap.stages["camera"]["fps"] == 3.0

        # After the roll, new samples begin a fresh window
        p._record_stage("camera", 40.0)
        p._window_roll_start -= 1.5
        snap2 = p.snapshot()
        assert snap2.stages["camera"]["avg_ms"] == 40.0
        assert snap2.stages["camera"]["fps"] == 1.0

    def test_reset_windows_forces_roll(self):
        from aether.core.profiler import Profiler

        p = Profiler()
        p._record_stage("yolo", 12.0)
        p.reset_windows()
        snap = p.snapshot()
        assert snap.stages["yolo"]["avg_ms"] == 12.0

    def test_repaint_counter(self):
        from aether.core.profiler import Profiler

        p = Profiler()
        p.record_repaint()
        p.record_repaint()
        p.record_repaint()

        snap = p.snapshot()
        assert snap.total_repaints == 3
        assert snap.repaints_per_sec == 3.0

        # Roll keeps cumulative total, snaps per-sec to the closed window
        p._window_roll_start -= 1.5
        snap2 = p.snapshot()
        assert snap2.total_repaints == 3
        assert snap2.repaints_per_sec == 3.0

    def test_event_loop_timing(self):
        from aether.core.profiler import Profiler

        p = Profiler()
        p.record_event_loop(2.0)
        p.record_event_loop(4.0)
        assert p.snapshot().qt_events_ms == 3.0


# ── EventBus metrics ────────────────────────────────────────────────


class TestEventBusMetrics:
    def test_totals_and_per_type_stats(self):
        from aether.core.event_bus_v2 import Event, EventBus
        from aether.core.event_type import EventType

        bus = EventBus(queued=True)
        received = []
        bus.subscribe(EventType.SYSTEM_TICK, received.append)

        bus.publish(Event(type=EventType.SYSTEM_TICK))
        bus.publish(Event(type=EventType.SYSTEM_TICK))
        bus.publish(Event(type=EventType.COMMAND_COMPLETED))  # no subscriber -> orphan

        assert bus.flush() == 3
        assert len(received) == 2

        totals = bus.get_totals()
        assert totals["published"] == 3
        assert totals["delivered"] == 2
        assert totals["orphans"] == 1

        stats = bus.get_event_stats()
        assert stats["system.tick"]["published"] == 2
        assert stats["system.tick"]["delivered"] == 2
        assert stats["system.tick"]["orphans"] == 0
        assert stats["command.completed"]["published"] == 1
        assert stats["command.completed"]["orphans"] == 1
        assert bus.get_orphan_event_types() == ["command.completed"]

    def test_delivered_counts_multiple_subscribers(self):
        from aether.core.event_bus_v2 import Event, EventBus
        from aether.core.event_type import EventType

        bus = EventBus(queued=True)
        calls = []
        bus.subscribe(EventType.SYSTEM_TICK, lambda e: calls.append(1))
        bus.subscribe(EventType.SYSTEM_TICK, lambda e: calls.append(2))
        bus.publish(Event(type=EventType.SYSTEM_TICK))
        bus.flush()

        assert bus.get_totals()["delivered"] == 2  # one callback per subscriber
        assert len(calls) == 2

    def test_immediate_mode_and_publish_now(self):
        from aether.core.event_bus_v2 import Event, EventBus
        from aether.core.event_type import EventType

        bus = EventBus(queued=False)
        received = []
        bus.subscribe(EventType.SYSTEM_TICK, lambda e: received.append(e))
        bus.publish(Event(type=EventType.SYSTEM_TICK))
        assert len(received) == 1
        assert bus.get_totals() == {"published": 1, "delivered": 1, "orphans": 0}

        bus2 = EventBus(queued=True)
        got = []
        bus2.subscribe(EventType.SYSTEM_READY, lambda e: got.append(e))
        bus2.publish_now(EventType.SYSTEM_READY)
        assert len(got) == 1
        assert bus2.get_totals()["published"] == 1
        assert bus2.get_totals()["delivered"] == 1

    def test_rates_roll_into_profiler_queue(self):
        from aether.core.event_bus_v2 import Event, EventBus
        from aether.core.event_type import EventType
        from aether.core.profiler import profiler

        bus = EventBus(queued=True)
        bus.subscribe(EventType.SYSTEM_TICK, lambda e: None)
        bus.publish(Event(type=EventType.SYSTEM_TICK))
        bus._window_start -= 1.5  # backdate so the rate window closes
        bus.flush()

        snap = profiler.snapshot()
        queue = snap.queues["eventbus"]
        assert queue["events_per_sec"] > 0
        assert queue["delivered_per_sec"] > 0
        assert queue["total_published"] >= 1
        assert snap.events_per_sec > 0


# ── HUDManager layer-4 throttling ───────────────────────────────────


class _CountWidget:
    def __init__(self) -> None:
        self.calls = 0

    def update(self) -> None:
        self.calls += 1

    def paint(self) -> None:
        pass

    def is_visible(self) -> bool:
        return True

    def get_dirty_rect(self):
        return None


class TestHUDLayer4:
    def test_default_interval_is_5hz(self):
        from aether.ui.hud_manager import DEFAULT_LAYER_INTERVALS, HUDManager

        assert DEFAULT_LAYER_INTERVALS[4] == 0.2
        hm = HUDManager()
        hm.enable_adaptive(False)
        assert hm._get_effective_interval(4) == 0.2

    def test_layer4_widget_is_throttled(self):
        from aether.ui.hud_manager import HUDManager

        hm = HUDManager()
        hm.enable_adaptive(False)
        w = _CountWidget()
        hm.add_widget(w, layer=4)
        hm.update()
        hm.update()
        assert w.calls == 1

    def test_scheduler_provides_layer4(self):
        from aether.core.adaptive_scheduler import adaptive_scheduler

        s = adaptive_scheduler.get_state()
        assert 4 in s.layer_intervals
        assert s.layer_intervals[4] > 0


# ── CameraWidget timer pause ────────────────────────────────────────


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


class _FakeBroker:
    def get_frame(self):
        return None


class TestCameraWidgetPause:
    def test_timer_stops_when_hidden(self, qapp):
        from aether.ui.camera_widget import CameraWidget

        cam = CameraWidget(_FakeBroker())
        cam.show()
        assert cam._timer.isActive()
        cam.hide()
        assert not cam._timer.isActive()
        cam.show()
        assert cam._timer.isActive()
        cam.stop()
