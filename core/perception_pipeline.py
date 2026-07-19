import logging
import time
from typing import Dict, Any, Optional
from core.event_bus import EventBus, EventType
from core.plugin_manager import PluginManager


class PerceptionResult:
    def __init__(self):
        self.detections = []
        self.hand_results = None
        self.frame = None
        self.timestamp = time.time()

    def set(self, key: str, value):
        setattr(self, key, value)

    def get(self, key: str, default=None):
        return getattr(self, key, default)


class PerceptionPipeline:
    def __init__(self, event_bus: EventBus, plugin_manager: PluginManager):
        self.event_bus = event_bus
        self.plugin_manager = plugin_manager
        self.logger = logging.getLogger("Aether.PerceptionPipeline")
        self._frame_count = 0

    def process(self, frame) -> PerceptionResult:
        result = PerceptionResult()
        result.frame = frame
        self._frame_count += 1

        plugin_results = self.plugin_manager.process_all(frame)

        for plugin_name, plugin_result in plugin_results.items():
            if plugin_result is None:
                continue

            if plugin_name == "yolo_plugin" and plugin_result:
                result.detections = plugin_result
                for det in plugin_result:
                    self.event_bus.emit(
                        EventType.OBJECT_DETECTED,
                        data=det,
                        source=plugin_name
                    )

            elif plugin_name == "hand_plugin" and plugin_result:
                result.hand_results = plugin_result
                self.event_bus.emit(
                    EventType.HAND_DETECTED,
                    data={"hands": plugin_result},
                    source=plugin_name
                )

        return result

    @property
    def frame_count(self):
        return self._frame_count
