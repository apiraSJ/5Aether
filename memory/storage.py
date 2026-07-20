import json
import os
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict
import logging


@dataclass
class AetherMemory:
    """Aether's persistent memory."""
    mode: str = "normal"
    last_panel: str = "system"
    theme: str = "dark"
    ui_position: Dict[str, int] = None
    user_preferences: Dict[str, Any] = None
    recent_activity: list = None
    
    def __post_init__(self):
        if self.ui_position is None:
            self.ui_position = {"x": 100, "y": 100}
        if self.user_preferences is None:
            self.user_preferences = {}
        if self.recent_activity is None:
            self.recent_activity = []


class MemoryStorage:
    """Handles Aether's persistent memory."""
    
    def __init__(self, storage_path: str = "memory/aether_memory.json"):
        self.logger = logging.getLogger("Aether.Memory")
        self.storage_path = storage_path
        self._memory = AetherMemory()
        self._ensure_dir()
        self.load()
    
    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
    
    def load(self) -> AetherMemory:
        """Load memory from disk."""
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    self._memory = AetherMemory(**data)
                self.logger.info(f"Memory loaded from {self.storage_path}")
            else:
                self.logger.info("No memory file found, starting fresh")
        except Exception as e:
            self.logger.error(f"Failed to load memory: {e}")
        return self._memory
    
    def save(self) -> bool:
        """Save memory to disk."""
        try:
            with open(self.storage_path, 'w') as f:
                json.dump(asdict(self._memory), f, indent=2)
            self.logger.debug(f"Memory saved to {self.storage_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save memory: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a memory value."""
        return getattr(self._memory, key, default)
    
    def set(self, key: str, value: Any) -> bool:
        """Set a memory value."""
        if hasattr(self._memory, key):
            setattr(self._memory, key, value)
            return self.save()
        return False
    
    def update(self, **kwargs) -> bool:
        """Update multiple memory values."""
        for key, value in kwargs.items():
            if hasattr(self._memory, key):
                setattr(self._memory, key, value)
        return self.save()
    
    def add_activity(self, activity: Dict[str, Any]):
        """Add to recent activity."""
        self._memory.recent_activity.insert(0, activity)
        if len(self._memory.recent_activity) > 50:
            self._memory.recent_activity = self._memory.recent_activity[:50]
        self.save()
    
    def get_memory(self) -> AetherMemory:
        return self._memory