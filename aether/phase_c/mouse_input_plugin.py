"""
Mouse Input Plugin (Phase C) - Converts mouse events to Commands.

Handles mouse clicks, movement, and scrolling from legacy mouse handlers
or direct pynput integration.
"""

from pynput import mouse

from aether.core.plugin import PluginBase
from aether.core.command import Command


class MouseInputPlugin(PluginBase):
    """Mouse input plugin using pynput for global mouse event detection."""
    
    name = "mouse_input"
    
    def __init__(self):
        self.event_bus = None
        self.command_bus = None
        self._listener = None
        self._running = False
    
    def initialize(self, container):
        self.event_bus = container.resolve("event_bus")
        self.command_bus = container.resolve("command_bus")
        
        self._running = True
        
        # Start mouse listener
        self._listener = mouse.Listener(
            on_click=self._on_click,
            on_move=self._on_move,
            on_scroll=self._on_scroll
        )
        self._listener.start()
    
    def shutdown(self):
        self._running = False
        if self._listener:
            self._listener.stop()
            self._listener = None
    
    def _on_click(self, x, y, button, pressed):
        """Handle mouse click events."""
        if not self._running or not self.command_bus:
            return
        
        if pressed:  # Only on press, not release
            cmd_name = "mouse_click"
            if button == mouse.Button.right:
                cmd_name = "mouse_right_click"
            elif button == mouse.Button.middle:
                cmd_name = "mouse_middle_click"
            
            cmd = Command(
                name=cmd_name,
                source="mouse",
                params={
                    "x": x,
                    "y": y,
                    "button": str(button)
                }
            )
            self.command_bus.dispatch(cmd)
    
    def _on_move(self, x, y):
        """Handle mouse movement - throttled to avoid spam."""
        # Only emit position updates periodically or on significant movement
        pass  # Could emit cursor position commands if needed
    
    def _on_scroll(self, x, y, dx, dy):
        """Handle mouse scroll events."""
        if not self._running or not self.command_bus:
            return
        
        cmd = Command(
            name="mouse_scroll",
            source="mouse",
            params={
                "x": x,
                "y": y,
                "dx": dx,
                "dy": dy
            }
        )
        self.command_bus.dispatch(cmd)


class MouseEventPlugin(PluginBase):
    """Alternative: Subscribes to legacy mouse events on EventBus."""
    
    name = "mouse_event"
    
    def __init__(self):
        self.event_bus = None
        self.command_bus = None
        self._running = False
    
    def initialize(self, container):
        self.event_bus = container.resolve("event_bus")
        self.command_bus = container.resolve("command_bus")
        
        self._running = True
        self.event_bus.subscribe("input_mouse", self._on_mouse_event)
    
    def shutdown(self):
        self._running = False
        if self.event_bus:
            self.event_bus.unsubscribe("input_mouse", self._on_mouse_event)
    
    def _on_mouse_event(self, event):
        """Handle legacy mouse event."""
        if not self._running or not self.command_bus:
            return
        
        action = event.payload.get("action", "")
        x = event.payload.get("x", 0)
        y = event.payload.get("y", 0)
        
        if action == "click":
            cmd = Command(
                name="mouse_click",
                source="mouse",
                params={"x": x, "y": y}
            )
            self.command_bus.dispatch(cmd)