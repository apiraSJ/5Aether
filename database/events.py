import os
import logging
import time
from database.storage import JsonStorage


class EventStore:
    def __init__(self, filepath: str = "database/events.json"):
        self.logger = logging.getLogger("Aether.EventStore")
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        self.storage = JsonStorage(filepath)
        self._counter = len(self.storage)

    def log(self, event_type: str, data: dict = None, source: str = ""):
        self._counter += 1
        event_id = f"evt_{self._counter}_{int(time.time() * 1000)}"
        event_data = {
            "id": event_id,
            "type": event_type,
            "data": data or {},
            "source": source,
            "timestamp": time.time(),
        }
        self.storage.set(event_id, event_data)

    def get_recent(self, limit: int = 50) -> list:
        items = self.storage.items()
        sorted_items = sorted(items, key=lambda x: x[1].get("timestamp", 0), reverse=True)
        return [item[1] for item in sorted_items[:limit]]

    def get_by_type(self, event_type: str) -> list:
        return [
            item[1] for item in self.storage.items()
            if item[1].get("type") == event_type
        ]

    def clear(self):
        self.storage.clear()
