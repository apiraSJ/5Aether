"""
Vision perception plugins (Phase D) that integrate legacy CV pipeline
into the new architecture.

These plugins maintain the performance and accuracy of the original
hand/object detection systems while adapting them to the new
command-driven and plugin architecture.
"""

from .hand_plugin import HandPerceptionPlugin, FrameBroker
from .object_plugin import ObjectSpatialPlugin, CameraPlugin
from .cursor_plugin import CursorPlugin, PinchClickPlugin

__all__ = [
    "HandPerceptionPlugin",
    "FrameBroker",
    "ObjectSpatialPlugin",
    "CameraPlugin",
    "CursorPlugin",
    "PinchClickPlugin",
]