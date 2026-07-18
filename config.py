import yaml
import os

def load_config(config_path="config/default.yaml"):
    """Loads configuration from a YAML file, falling back to defaults if not found."""
    defaults = {
        "camera": {
            "device_index": 0,
            "width": 640,
            "height": 480
        },
        "model": {
            "weights": "yolov8n.pt",
            "confidence": 0.25
        },
        "logging": {
            "level": "INFO",
            "file": "logs/aether.log"
        },
        "hud": {
            "show_fps": True,
            "show_telemetry": True
        }
    }
    
    if not os.path.exists(config_path):
        return defaults
        
    try:
        with open(config_path, 'r') as f:
            user_config = yaml.safe_load(f)
        if user_config:
            # Merge defaults with user_config
            for section, values in defaults.items():
                if section in user_config:
                    if isinstance(values, dict) and isinstance(user_config[section], dict):
                        defaults[section].update(user_config[section])
                    else:
                        defaults[section] = user_config[section]
        return defaults
    except Exception as e:
        print(f"Error loading config file {config_path}: {e}. Using defaults.")
        return defaults
