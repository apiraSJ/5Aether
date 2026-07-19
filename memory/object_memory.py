import logging
from typing import List, Optional
from memory.models import SpatialObject
from database.objects import ObjectStore


class ObjectMemory:
    def __init__(self, store: ObjectStore = None):
        self.logger = logging.getLogger("Aether.ObjectMemory")
        self.store = store or ObjectStore()
        self._load_all()

    def _load_all(self):
        raw = self.store.list_all()
        self._objects = {}
        for obj_id, obj_data in raw.items():
            try:
                self._objects[obj_id] = SpatialObject.from_dict(obj_data)
            except Exception as e:
                self.logger.warning(f"Failed to load object {obj_id}: {e}")

    def add(self, obj: SpatialObject) -> str:
        self._objects[obj.id] = obj
        self.store.save(obj.id, obj.to_dict())
        self.logger.info(f"Object added: {obj.id}")
        return obj.id

    def update(self, object_id: str, **kwargs) -> bool:
        if object_id not in self._objects:
            return False
        obj = self._objects[object_id]
        for key, value in kwargs.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        self.store.save(object_id, obj.to_dict())
        return True

    def remove(self, object_id: str) -> bool:
        if object_id in self._objects:
            del self._objects[object_id]
            self.store.delete(object_id)
            self.logger.info(f"Object removed: {object_id}")
            return True
        return False

    def get(self, object_id: str) -> Optional[SpatialObject]:
        return self._objects.get(object_id)

    def find(self, **kwargs) -> List[SpatialObject]:
        results = []
        for obj in self._objects.values():
            match = True
            for key, value in kwargs.items():
                if getattr(obj, key, None) != value:
                    match = False
                    break
            if match:
                results.append(obj)
        return results

    def list_all(self) -> List[SpatialObject]:
        return list(self._objects.values())

    def get_by_location(self, location: str) -> List[SpatialObject]:
        return self.find(location=location)

    def search_by_name(self, query: str) -> List[SpatialObject]:
        query_lower = query.lower()
        return [obj for obj in self._objects.values() if query_lower in obj.name.lower()]

    @property
    def count(self) -> int:
        return len(self._objects)
