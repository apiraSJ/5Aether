"""Tests for EventBus — sync + async handlers, categories, subscribe/unsubscribe."""
import asyncio

from aether.core.event_bus import Event, EventBus, EventCategory


class TestEventBusSync:
    def test_subscribe_and_publish(self):
        bus = EventBus()
        received = []
        bus.subscribe("test", lambda e: received.append(e))
        bus.publish(Event(name="test", category=EventCategory.SYSTEM))
        assert len(received) == 1
        assert received[0].name == "test"

    def test_multiple_subscribers(self):
        bus = EventBus()
        received = []
        bus.subscribe("test", lambda e: received.append("a"))
        bus.subscribe("test", lambda e: received.append("b"))
        bus.publish(Event(name="test", category=EventCategory.SYSTEM))
        assert received == ["a", "b"]

    def test_unsubscribe(self):
        bus = EventBus()
        received = []
        cb = lambda e: received.append(1)
        bus.subscribe("test", cb)
        bus.unsubscribe("test", cb)
        bus.publish(Event(name="test", category=EventCategory.SYSTEM))
        assert received == []

    def test_category_subscribe(self):
        bus = EventBus()
        received = []
        bus.subscribe_category(EventCategory.DATA, lambda e: received.append(e))
        bus.publish(Event(name="anything", category=EventCategory.DATA))
        assert len(received) == 1

    def test_category_does_not_fire_wrong_category(self):
        bus = EventBus()
        received = []
        bus.subscribe_category(EventCategory.DATA, lambda e: received.append(1))
        bus.publish(Event(name="x", category=EventCategory.UI))
        assert received == []

    def test_publish_simple(self):
        bus = EventBus()
        received = []
        bus.subscribe("Ping", lambda e: received.append(e))
        event = bus.publish_simple("Ping", EventCategory.SYSTEM, {"key": "val"})
        assert event.name == "Ping"
        assert event.payload == {"key": "val"}
        assert len(received) == 1

    def test_subscriber_exception_isolated(self):
        bus = EventBus()
        received = []

        def bad(e):
            raise RuntimeError("oops")

        bus.subscribe("test", bad)
        bus.subscribe("test", lambda e: received.append("ok"))
        bus.publish(Event(name="test", category=EventCategory.SYSTEM))
        assert received == ["ok"]

    def test_publisher_called_outside_lock(self):
        """Publish should not hold the lock during callbacks."""
        bus = EventBus()
        order = []

        def cb(e):
            order.append("callback")
            # Publishing from inside a callback should not deadlock
            bus.publish(Event(name="inner", category=EventCategory.SYSTEM))

        bus.subscribe("outer", cb)
        bus.subscribe("inner", lambda e: order.append("inner"))
        bus.publish(Event(name="outer", category=EventCategory.SYSTEM))
        assert "inner" in order

    def test_unsubscribe_category(self):
        bus = EventBus()
        received = []
        cb = lambda e: received.append(1)
        bus.subscribe_category(EventCategory.SYSTEM, cb)
        bus.unsubscribe_category(EventCategory.SYSTEM, cb)
        bus.publish(Event(name="x", category=EventCategory.SYSTEM))
        assert received == []


class TestEventBusAsync:
    def test_async_handler_called(self):
        bus = EventBus()
        received = []

        async def handler(e):
            received.append(e)

        bus.subscribe("test", handler)
        bus.publish(Event(name="test", category=EventCategory.SYSTEM))
        assert len(received) == 1

    def test_async_handler_exception_isolated(self):
        bus = EventBus()
        received = []

        async def bad(e):
            raise RuntimeError("oops")

        async def good(e):
            received.append("ok")

        bus.subscribe("test", bad)
        bus.subscribe("test", good)
        bus.publish(Event(name="test", category=EventCategory.SYSTEM))
        assert received == ["ok"]
