import os
import yaml
import logging


class Settings:
    def __init__(self, config_path: str = None):
        self.logger = logging.getLogger("Aether.Settings")
        self._config = {}
        self._defaults = {
            "camera": {
                "device_index": 0,
                "width": 640,
                "height": 480,
                "fps_target": 30
            },
            "model": {
                "weights": "yolov8n.pt",
                "confidence": 0.25,
                "enabled": True
            },
            "hand_tracking": {
                "enabled": True,
                "model_path": "models/hand_landmarker.task",
                "num_hands": 2,
                "min_detection_confidence": 0.7,
                "min_tracking_confidence": 0.5
            },
            "gesture_engine": {
                "enabled": True,
                "movement_stability_px": 8,
                "dwell_time_ms": 500
            },
            "interaction": {
                "default_mode": "passive",
                "activation_gesture": "OPEN_PALM",
                "activation_dwell_ms": 800,
                "preview_timeout_ms": 3000
            },
            "logging": {
                "level": "INFO",
                "file": "logs/aether.log"
            },
            "dashboard": {
                "theme": "dark",
                "show_hand_landmarks": True,
                "show_gesture_state": True,
                "sidebar_width": 280
            },
            "hud": {
                "show_fps": True,
                "show_telemetry": True
            }
        }

        if config_path and os.path.exists(config_path):
            self._load(config_path)
        else:
            self._config = self._defaults.copy()
            self.logger.info("Using default settings (no config file found)")

    def _load(self, config_path: str):
        try:
            with open(config_path, 'r') as f:
                user_config = yaml.safe_load(f) or {}
            self._config = self._merge(self._defaults, user_config)
            self.logger.info(f"Loaded settings from {config_path}")
        except Exception as e:
            self.logger.error(f"Failed to load {config_path}: {e}. Using defaults.")
            self._config = self._defaults.copy()

    def _merge(self, defaults: dict, user: dict) -> dict:
        result = defaults.copy()
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge(result[key], value)
            else:
                result[key] = value
        return result

    def get(self, section: str, key: str = None, default=None):
        if key:
            return self._config.get(section, {}).get(key, default)
        return self._config.get(section, default)

    def set(self, section: str, key: str, value):
        if section not in self._config:
            self._config[section] = {}
        self._config[section][key] = value

    def save(self, config_path: str):
        try:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, 'w') as f:
                yaml.dump(self._config, f, default_flow_style=False)
            self.logger.info(f"Settings saved to {config_path}")
        except Exception as e:
            self.logger.error(f"Failed to save settings: {e}")

    @property
    def all(self):
        return self._config
