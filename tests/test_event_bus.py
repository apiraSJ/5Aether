import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.event_bus import EventBus, EventType, Event


class TestEventBus(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()

    def test_emit_and_subscribe(self):
        received = []
        self.bus.subscribe(EventType.OBJECT_DETECTED, lambda e: received.append(e))
        self.bus.emit(EventType.OBJECT_DETECTED, data={"label": "hammer"})
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].data["label"], "hammer")

    def test_unsubscribe(self):
        received = []
        handler = lambda e: received.append(e)
        self.bus.subscribe(EventType.HAND_DETECTED, handler)
        self.bus.unsubscribe(EventType.HAND_DETECTED, handler)
        self.bus.emit(EventType.HAND_DETECTED)
        self.assertEqual(len(received), 0)

    def test_multiple_subscribers(self):
        results = []
        self.bus.subscribe(EventType.GESTURE_RECOGNIZED, lambda e: results.append("a"))
        self.bus.subscribe(EventType.GESTURE_RECOGNIZED, lambda e: results.append("b"))
        self.bus.emit(EventType.GESTURE_RECOGNIZED)
        self.assertEqual(len(results), 2)

    def test_history(self):
        self.bus.emit(EventType.TASK_CREATED, data={"id": "t1"})
        self.bus.emit(EventType.TASK_UPDATED, data={"id": "t1"})
        history = self.bus.get_history()
        self.assertEqual(len(history), 2)

    def test_history_filter(self):
        self.bus.emit(EventType.OBJECT_DETECTED)
        self.bus.emit(EventType.HAND_DETECTED)
        self.bus.emit(EventType.OBJECT_DETECTED)
        history = self.bus.get_history(event_type=EventType.OBJECT_DETECTED)
        self.assertEqual(len(history), 2)

    def test_subscriber_count(self):
        self.bus.subscribe(EventType.OBJECT_DETECTED, lambda e: None)
        self.bus.subscribe(EventType.OBJECT_DETECTED, lambda e: None)
        self.bus.subscribe(EventType.HAND_DETECTED, lambda e: None)
        self.assertEqual(self.bus.subscriber_count(EventType.OBJECT_DETECTED), 2)
        self.assertEqual(self.bus.subscriber_count(), 3)


if __name__ == '__main__':
    unittest.main()
