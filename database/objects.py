import os
import logging
from database.storage import JsonStorage


class ObjectStore:
    def __init__(self, filepath: str = "database/objects.json"):
        self.logger = logging.getLogger("Aether.ObjectStore")
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        self.storage = JsonStorage(filepath)

    def save(self, object_id: str, obj_data: dict):
        self.storage.set(object_id, obj_data)

    def load(self, object_id: str) -> dict:
        return self.storage.get(object_id)

    def delete(self, object_id: str) -> bool:
        return self.storage.delete(object_id)

    def list_all(self) -> dict:
        return self.storage.all()

    def search(self, **kwargs) -> list:
        results = []
        for obj_id, obj_data in self.storage.items():
            match = True
            for key, value in kwargs.items():
                if obj_data.get(key) != value:
                    match = False
                    break
            if match:
                results.append(obj_data)
        return results
