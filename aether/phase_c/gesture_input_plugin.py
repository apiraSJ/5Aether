"""
Gesture Input Plugin (Phase C) - Converts hand gesture events to Commands.

This is the PRIMARY input plugin for vision-based interaction.
Subscribes to HAND_DETECTED events from Phase D hand perception plugin
and maps gestures to Commands.
"""

from aether.core.plugin import PluginBase
from aether.core.command import Command


class GestureInputPlugin(PluginBase):
    """Gesture input plugin - maps MediaPipe gestures to Commands.
    
    This plugin replaces the legacy GestureRouter by subscribing to
    hand detection events and directly dispatching Commands.
    """
    
    name = "gesture_input"
    
    # MediaPipe gesture -> Command mapping
    GESTURE_COMMANDS = {
        "Open_Palm": "gesture_open_palm",
        "Closed_Fist": "gesture_closed_fist", 
        "Pointing_Up": "gesture_pointing_up",
        "Thumb_Up": "gesture_thumb_up",
        "Thumb_Down": "gesture_thumb_down",
        "Victory": "gesture_victory",
        "ILoveYou": "gesture_iloveyou",
    }
    
    def __init__(self):
        self.event_bus = None
        self.command_bus = None
        self._running = False
        self._last_gesture = {}
        self._gesture_cooldown = 0.8  # seconds
        self._last_time = {}
    
    def initialize(self, container):
        self.event_bus = container.resolve("event_bus")
        self.command_bus = container.resolve("command_bus")
        
        self._running = True
        # Subscribe to hand detection events from Phase D plugin
        self.event_bus.subscribe("vision_hand_detected", self._on_hand_detected)
    
    def shutdown(self):
        self._running = False
        if self.event_bus:
            self.event_bus.unsubscribe("vision_hand_detected", self._on_hand_detected)
    
    def _on_hand_detected(self, event):
        """Process hand detection event and dispatch gesture commands."""
        if not self._running or not self.command_bus:
            return
        
        hands = event.data.get("hands", [])
        
        for hand in hands:
            gesture = hand.get("gesture", "Unknown")
            score = hand.get("gesture_score", 0.0)
            label = hand.get("label", "Unknown")  # Left/Right
            
            # Only process recognized gestures with sufficient confidence
            if gesture == "Unknown" or score < 0.5:
                continue
            
            # Cooldown check per gesture type
            import time
            now = time.time()
            key = f"{label}_{gesture}"
            
            if key in self._last_time:
                if now - self._last_time[key] < self._gesture_cooldown:
                    continue
            
            self._last_time[key] = now
            
            # Map gesture to command
            cmd_name = self.GESTURE_COMMANDS.get(gesture)
            if cmd_name:
                self._dispatch(cmd_name, {
                    "gesture": gesture,
                    "hand": label,
                    "confidence": score,
                    "landmarks": hand.get("landmarks", [])
                })
    
    def _dispatch(self, cmd_name, params):
        """Dispatch command with gesture data."""
        if self.command_bus:
            cmd = Command(
                name=cmd_name,
                source="gesture",
                params=params
            )
            self.command_bus.dispatch(cmd)


class PinchGesturePlugin(PluginBase):
    """Specialized plugin for pinch gesture detection (click/selection)."""
    
    name = "pinch_gesture"
    
    PINCH_THRESHOLD = 0.08  # Normalized distance
    
    def __init__(self):
        self.event_bus = None
        self.command_bus = None
        self._running = False
        self._was_pinch = {}
    
    def initialize(self, container):
        self.event_bus = container.resolve("event_bus")
        self.command_bus = container.resolve("command_bus")
        
        self._running = True
        self.event_bus.subscribe("vision_hand_detected", self._on_hand_detected)
    
    def shutdown(self):
        self._running = False
        if self.event_bus:
            self.event_bus.unsubscribe("vision_hand_detected", self._on_hand_detected)
    
    def _on_hand_detected(self, event):
        if not self._running or not self.command_bus:
            return
        
        hands = event.data.get("hands", [])
        
        for hand in hands:
            landmarks = hand.get("landmarks", [])
            label = hand.get("label", "Unknown")
            
            if len(landmarks) >= 21:
                # Index tip (8) and thumb tip (4)
                index_tip = landmarks[8]
                thumb_tip = landmarks[4]
                
                # Calculate pinch distance
                dx = index_tip["x"] - thumb_tip["x"]
                dy = index_tip["y"] - thumb_tip["y"]
                distance = (dx*dx + dy*dy) ** 0.5
                
                is_pinch = distance < self.PINCH_THRESHOLD
                was_pinch = self._was_pinch.get(label, False)
                
                # Edge-triggered pinch (click on pinch start)
                if is_pinch and not was_pinch:
                    self._dispatch("gesture_pinch", {
                        "hand": label,
                        "distance": distance,
                        "position": {
                            "x": (index_tip["x"] + thumb_tip["x"]) / 2,
                            "y": (index_tip["y"] + thumb_tip["y"]) / 2
                        }
                    })
                
                self._was_pinch[label] = is_pinch
    
    def _dispatch(self, cmd_name, params):
        if self.command_bus:
            cmd = Command(name=cmd_name, source="gesture", params=params)
            self.command_bus.dispatch(cmd)