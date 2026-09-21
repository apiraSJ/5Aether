"""CameraAnchor — snap positions for a PiP camera window.

Used by CameraState to remember where the PiP is anchored on screen.
The UIShell repositions the PiP on window resize based on this anchor.

Values are config/state-friendly strings (CameraAnchor("bottom_right") works).
"""

from enum import Enum


class CameraAnchor(Enum):
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"
    FREE = "free"

    @classmethod
    def from_str(cls, value: str) -> "CameraAnchor":
        """Convert a string to CameraAnchor, defaulting to BOTTOM_RIGHT."""
        try:
            return cls(value.lower())
        except ValueError:
            return cls.BOTTOM_RIGHT
