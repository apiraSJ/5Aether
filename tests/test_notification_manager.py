"""Tests for Step 0.4: Notification System — NotificationManager."""

import time

from aether.ui.panel.notification_manager import NotificationManager, Notification
from aether.core.event_bus_v2 import EventBus
from aether.core.event_type import EventType


# ── Fixtures ────────────────────────────────────────────────────────

def _make_manager(with_bus=False):
    bus = EventBus(queued=True) if with_bus else None
    return NotificationManager(event_bus=bus), bus


# ── Publish tests ───────────────────────────────────────────────────

def test_publish_creates_notification():
    mgr, _ = _make_manager()
    notif = mgr.publish("Hello")
    assert notif.text == "Hello"
    assert notif.type == "info"
    assert notif.duration > 0


def test_publish_default_type():
    mgr, _ = _make_manager()
    notif = mgr.publish("test")
    assert notif.type == "info"


def test_publish_warning():
    mgr, _ = _make_manager()
    notif = mgr.publish("careful", "warning")
    assert notif.type == "warning"
    assert notif.duration == 5.0


def test_publish_error_manual_dismiss():
    mgr, _ = _make_manager()
    notif = mgr.publish("critical", "error")
    assert notif.duration <= 0  # manual dismiss only
    assert not notif.expired  # never auto-expires


def test_publish_success():
    mgr, _ = _make_manager()
    notif = mgr.publish("done", "success")
    assert notif.type == "success"
    assert notif.duration == 3.0


# ── Convenience methods ─────────────────────────────────────────────

def test_info_convenience():
    mgr, _ = _make_manager()
    notif = mgr.info("info msg")
    assert notif.type == "info"
    assert notif.text == "info msg"


def test_success_convenience():
    mgr, _ = _make_manager()
    notif = mgr.success("ok")
    assert notif.type == "success"


def test_warning_convenience():
    mgr, _ = _make_manager()
    notif = mgr.warning("warn")
    assert notif.type == "warning"


def test_error_convenience():
    mgr, _ = _make_manager()
    notif = mgr.error("err")
    assert notif.type == "error"


# ── Query tests ─────────────────────────────────────────────────────

def test_get_active():
    mgr, _ = _make_manager()
    mgr.info("a")
    mgr.info("b")
    active = mgr.get_active()
    assert len(active) == 2


def test_get_all():
    mgr, _ = _make_manager()
    mgr.info("a")
    mgr.error("b")  # error never auto-expires
    all_n = mgr.get_all()
    assert len(all_n) == 2


def test_count():
    mgr, _ = _make_manager()
    assert mgr.count() == 0
    mgr.info("a")
    assert mgr.count() == 1
    mgr.info("b")
    assert mgr.count() == 2


# ── Dismiss tests ───────────────────────────────────────────────────

def test_dismiss():
    mgr, _ = _make_manager()
    notif = mgr.info("dismiss me")
    assert mgr.dismiss(notif.id) is True
    assert len(mgr.get_active()) == 0


def test_dismiss_nonexistent():
    mgr, _ = _make_manager()
    assert mgr.dismiss(999999) is False


def test_dismiss_already_dismissed():
    mgr, _ = _make_manager()
    notif = mgr.info("once")
    mgr.dismiss(notif.id)
    assert mgr.dismiss(notif.id) is False  # already dismissed


# ── Clear tests ─────────────────────────────────────────────────────

def test_clear():
    mgr, _ = _make_manager()
    mgr.info("a")
    mgr.info("b")
    mgr.info("c")
    count = mgr.clear()
    assert count == 3
    assert mgr.count() == 0


def test_clear_empty():
    mgr, _ = _make_manager()
    assert mgr.clear() == 0


# ── Expire tests ────────────────────────────────────────────────────

def test_expire_stale():
    mgr, _ = _make_manager()
    notif = mgr.info("expires soon")
    # Force expired by backdating
    notif.created_at = time.time() - 10
    expired = mgr.expire_stale()
    assert expired == 1
    assert len(mgr.get_active()) == 0


def test_expire_error_not_expired():
    mgr, _ = _make_manager()
    notif = mgr.error("never expires")
    notif.created_at = time.time() - 100
    expired = mgr.expire_stale()
    assert expired == 0  # error never auto-expires


# ── EventBus integration ────────────────────────────────────────────

def test_publish_emits_event():
    mgr, bus = _make_manager(with_bus=True)
    events = []
    bus.subscribe(EventType.NOTIFICATION_SHOW, lambda e: events.append(e))
    mgr.info("event test")
    bus.flush()
    assert len(events) == 1
    assert events[0].payload["text"] == "event test"
    assert events[0].payload["type"] == "info"


def test_dismiss_emits_event():
    mgr, bus = _make_manager(with_bus=True)
    notif = mgr.info("dismiss event")
    events = []
    bus.subscribe(EventType.NOTIFICATION_DISMISS, lambda e: events.append(e))
    mgr.dismiss(notif.id)
    bus.flush()
    assert len(events) == 1
    assert events[0].payload["text"] == "dismiss event"


def test_publish_no_bus():
    """Publish works even without EventBus."""
    mgr, _ = _make_manager(with_bus=False)
    notif = mgr.info("no bus")
    assert notif is not None
    assert mgr.count() == 1


# ── Notification dataclass ──────────────────────────────────────────

def test_notification_to_dict():
    notif = Notification("test msg", "warning")
    d = notif.to_dict()
    assert d["text"] == "test msg"
    assert d["type"] == "warning"
    assert "id" in d
    assert "elapsed" in d
    assert "expired" in d


def test_notification_expired():
    notif = Notification("expires", "info", duration=0.01)
    time.sleep(0.02)
    assert notif.expired is True


def test_notification_not_expired_error():
    notif = Notification("no expire", "error")
    time.sleep(0.01)
    assert notif.expired is False
