"""
Input sources (Phase C) that convert legacy input modes to new command system.

These plugins provide the bridge between raw input devices/user actions
and the new command-driven architecture.
"""

from .keyboard_input_plugin import KeyboardInputPlugin, KeyboardEventPlugin
from .mouse_input_plugin import MouseInputPlugin, MouseEventPlugin
from .gesture_input_plugin import GestureInputPlugin, PinchGesturePlugin
from .voice_input_plugin import VoiceInputPlugin, VoiceCommandPlugin

__all__ = [
    "KeyboardInputPlugin",
    "KeyboardEventPlugin",
    "MouseInputPlugin", 
    "MouseEventPlugin",
    "GestureInputPlugin",
    "PinchGesturePlugin",
    "VoiceInputPlugin",
    "VoiceCommandPlugin",
]