"""CameraMode — camera presentation modes for the UI shell.

BACKGROUND : full-screen feed behind all UI layers
PIP        : small floating preview window (default)
MINIMAL    : smallest PiP (no shadow, compact)
HIDDEN     : camera not visible at all

Values are config/command-friendly strings (CameraMode("pip") works).
"""

from enum import Enum


class CameraMode(Enum):
    BACKGROUND = "background"
    PIP = "pip"
    MINIMAL = "minimal"
    HIDDEN = "hidden"

    @classmethod
    def from_str(cls, value: str) -> "CameraMode":
        """Convert a string to CameraMode, defaulting to PIP on unknown."""
        try:
            return cls(value.lower())
        except ValueError:
            return cls.PIP
