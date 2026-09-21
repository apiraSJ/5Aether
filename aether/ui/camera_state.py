"""CameraState — persistent PiP position and mode for the camera widget.

UIShell owns one CameraState instance. CameraWidget is not aware of it.

State file: aether/data/ui/camera_pip.json
  {"mode": "pip", "anchor": "bottom_right", "x": 1580, "y": 820, "width": 320, "height": 180}

Loading is best-effort (missing file → defaults). Saving creates directories as needed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from aether.ui.camera_mode import CameraMode
from aether.ui.camera_anchor import CameraAnchor

logger = logging.getLogger("Aether.CameraState")

_DEFAULT_STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "ui" / "camera_pip.json"


@dataclass
class CameraState:
    """Mutable state for camera PiP mode and position."""

    mode: CameraMode = CameraMode.PIP
    anchor: CameraAnchor = CameraAnchor.BOTTOM_RIGHT
    x: int = -1
    y: int = -1
    width: int = 320
    height: int = 180

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "CameraState":
        """Load state from JSON, returning defaults on any error."""
        path = path or _DEFAULT_STATE_PATH
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                mode=CameraMode.from_str(data.get("mode", "pip")),
                anchor=CameraAnchor.from_str(data.get("anchor", "bottom_right")),
                x=int(data.get("x", -1)),
                y=int(data.get("y", -1)),
                width=int(data.get("width", 320)),
                height=int(data.get("height", 180)),
            )
        except Exception:
            logger.debug("No camera state found at %s; using defaults", path)
            return cls()

    def save(self, path: Optional[Path] = None) -> None:
        """Persist state to JSON."""
        path = path or _DEFAULT_STATE_PATH
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "mode": self.mode.value,
                "anchor": self.anchor.value,
                "x": self.x,
                "y": self.y,
                "width": self.width,
                "height": self.height,
            }
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("Failed to save camera state to %s", path)
