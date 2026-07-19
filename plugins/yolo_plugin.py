import logging
from typing import List, Dict, Any
from core.plugin_manager import Plugin
from core.detector import Detector


class YoloPlugin(Plugin):
    def __init__(self):
        self._config = {}
        self._detector = None
        self._initialized = False

    @property
    def name(self) -> str:
        return "yolo_plugin"

    def initialize(self, config: dict) -> None:
        self._config = config
        try:
            self._detector = Detector(config)
            self._initialized = True
            logging.getLogger("Aether.YoloPlugin").info("YOLO plugin initialized")
        except Exception as e:
            logging.getLogger("Aether.YoloPlugin").error(f"Failed to initialize YOLO: {e}")

    def process(self, frame, **kwargs) -> List[Dict[str, Any]]:
        if not self._initialized or self._detector is None:
            return []
        try:
            return self._detector.detect(frame)
        except Exception as e:
            logging.getLogger("Aether.YoloPlugin").error(f"Detection error: {e}")
            return []

    def shutdown(self) -> None:
        self._detector = None
        self._initialized = False
