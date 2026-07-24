"""
Keyboard Input Plugin (Phase C) - Converts keyboard events to Commands.

Subscribes to keyboard events from legacy hotkey system and dispatches
corresponding Commands through the new CommandBus.
"""

import threading
from pynput import keyboard

from aether.core.plugin import PluginBase
from aether.core.command import Command


class KeyboardInputPlugin(PluginBase):
    """Keyboard input plugin using pynput for global hotkey detection."""
    
    name = "keyboard_input"
    
    # Hotkey -> Command mapping
    HOTKEY_MAP = {
        # UI toggle
        "<ctrl>+<space>": "ui_toggle",
        "<escape>": "ui_close",
        
        # Panel switching
        "<ctrl>+1": "panel_system",
        "<ctrl>+2": "panel_developer", 
        "<ctrl>+3": "panel_settings",
        
        # Mode switching
        "<tab>": "mode_developer",
        "m": "mode_normal",
        "p": "mode_presentation",
        
        # Gesture equivalents
        "g": "gesture_open_palm",      # Toggle menu
        "f": "gesture_closed_fist",    # Cancel/close
    }
    
    def __init__(self):
        self.event_bus = None
        self.command_bus = None
        self._listener = None
        self._running = False
    
    def initialize(self, container):
        self.event_bus = container.resolve("event_bus")
        self.command_bus = container.resolve("command_bus")
        
        # Start global hotkey listener
        self._running = True
        self._listener = keyboard.GlobalHotKeys(self.HOTKEY_MAP)
        self._listener.start()
    
    def shutdown(self):
        self._running = False
        if self._listener:
            self._listener.stop()
            self._listener = None
    
    def _on_hotkey(self, hotkey_name):
        """Callback when hotkey is pressed - dispatch corresponding command."""
        if not self._running:
            return
        
        cmd_name = self.HOTKEY_MAP.get(hotkey_name)
        if cmd_name and self.command_bus:
            cmd = Command(
                name=cmd_name,
                source="keyboard",
                params={"hotkey": hotkey_name}
            )
            self.command_bus.dispatch(cmd)


class KeyboardEventPlugin(PluginBase):
    """Alternative: Subscribes to legacy keyboard events on EventBus."""
    
    name = "keyboard_event"
    
    def __init__(self):
        self.event_bus = None
        self.command_bus = None
        self._running = False
    
    def initialize(self, container):
        self.event_bus = container.resolve("event_bus")
        self.command_bus = container.resolve("command_bus")
        
        # Subscribe to legacy keyboard events
        self._running = True
        self.event_bus.subscribe("input_keyboard", self._on_keyboard_event)
        self.event_bus.subscribe("input_hotkey", self._on_hotkey_event)
    
    def shutdown(self):
        self._running = False
        if self.event_bus:
            self.event_bus.unsubscribe("input_keyboard", self._on_keyboard_event)
            self.event_bus.unsubscribe("input_hotkey", self._on_hotkey_event)
    
    def _on_keyboard_event(self, event):
        """Handle generic keyboard event."""
        if not self._running:
            return
        
        key = event.data.get("key", "")
        action = event.data.get("action", "press")
        
        # Map key to command
        cmd_map = {
            "space": "ui_toggle",
            "escape": "ui_close",
            "tab": "mode_developer",
            "m": "mode_normal",
            "p": "mode_presentation",
        }
        
        if key in cmd_map and self.command_bus:
            cmd = Command(
                name=cmd_map[key],
                source="keyboard",
                params={"key": key, "action": action}
            )
            self.command_bus.dispatch(cmd)
    
    def _on_hotkey_event(self, event):
        """Handle hotkey event from legacy system."""
        if not self._running:
            return
        
        hotkey = event.data.get("hotkey", "")
        # Could map complex hotkeys here
        pass