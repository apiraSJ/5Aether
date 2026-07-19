import json
import os
import logging
import shutil
import tempfile


class JsonStorage:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.logger = logging.getLogger(f"Aether.Storage.{os.path.basename(filepath)}")
        self._data = {}
        self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                self.logger.error(f"Failed to load {self.filepath}: {e}")
                self._data = {}
        else:
            self._data = {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            dir_name = os.path.dirname(self.filepath)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            shutil.move(tmp_path, self.filepath)
        except Exception as e:
            self.logger.error(f"Failed to save {self.filepath}: {e}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self._save()

    def delete(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]
            self._save()
            return True
        return False

    def keys(self):
        return list(self._data.keys())

    def values(self):
        return list(self._data.values())

    def items(self):
        return list(self._data.items())

    def all(self):
        return self._data.copy()

    def clear(self):
        self._data.clear()
        self._save()

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return key in self._data
