"""
Cursor Plugin (Phase D) - Converts hand landmarks to cursor commands.

Maps normalized hand coordinates to screen coordinates and emits cursor commands.
Integrates with the existing cursor_manager logic from legacy.
"""

import numpy as np
from aether.core.plugin import PluginBase
from aether.core.command import Command
from aether.core.event_bus import EventBus


class CursorPlugin(PluginBase):
    """Handles cursor position from hand landmarks.
    
    Subscribes to vision_hand_detected, extracts index finger tip,
    maps to screen coordinates, emits cursor_move commands.
    """
    
    name = "cursor"
    
    def __init__(self):
        self.event_bus = None
        self.command_bus = None
        self._running = False
        
        # Screen mapping config
        self._screen_w = 1920
        self._screen_h = 1080
        self._camera_w = 640
        self._camera_h = 480
        self._mirror_x = True
        self._smoothing = 0.15
        self._sensitivity = 2.0
        self._dead_zone = 1
        
        # Smoothing state
        self._smoothed_x = self._screen_w // 2
        self._smoothed_y = self._screen_h // 2
        self._last_raw = None
    
    def initialize(self, container):
        self.event_bus = container.resolve("event_bus")
        self.command_bus = container.resolve("command_bus")
        
        config = container.resolve("config") if container.has("config") else None
        if config:
            cursor_cfg = config.get("cursor", {})
            self._screen_w = cursor_cfg.get("screen_width", self._screen_w)
            self._screen_h = cursor_cfg.get("screen_height", self._screen_h)
            self._camera_w = cursor_cfg.get("camera_width", self._camera_w)
            self._camera_h = cursor_cfg.get("camera_height", self._camera_h)
            self._mirror_x = cursor_cfg.get("mirror_x", self._mirror_x)
            self._smoothing = cursor_cfg.get("smoothing", self._smoothing)
            self._sensitivity = cursor_cfg.get("sensitivity", self._sensitivity)
            self._dead_zone = cursor_cfg.get("dead_zone", self._dead_zone)
        
        self.event_bus.subscribe("vision_hand_detected", self._on_hand_detected)
        self._running = True
    
    def shutdown(self):
        self._running = False
        if self.event_bus:
            self.event_bus.unsubscribe("vision_hand_detected", self._on_hand_detected)
    
    def _on_hand_detected(self, event):
        if not self._running:
            return
        
        hands = event.data.get("hands", [])
        if not hands:
            return
        
        # Use first hand with Pointing_Up gesture for cursor
        for hand in hands:
            gesture = hand.get("gesture", "")
            if gesture == "Pointing_Up":
                landmarks = hand.get("landmarks", [])
                if len(landmarks) > 8:
                    self._process_cursor(landmarks[8], hand.get("label", "Right"))
                break
    
    def _process_cursor(self, index_tip, hand_label):
        """Map index fingertip to screen coordinates."""
        # Normalized camera coordinates [0,1]
        cx = index_tip.get("x", 0.5)
        cy = index_tip.get("y", 0.5)
        
        # Mirror X if needed (camera is mirrored)
        if self._mirror_x:
            cx = 1.0 - cx
        
        # Apply sensitivity (zoom around center)
        cx = 0.5 + (cx - 0.5) * self._sensitivity
        cy = 0.5 + (cy - 0.5) * self._sensitivity
        
        # Clamp
        cx = max(0.0, min(1.0, cx))
        cy = max(0.0, min(1.0, cy))
        
        # Aspect ratio correction (contain mode: 4:3 camera -> 16:9 screen)
        cam_ar = self._camera_w / self._camera_h
        scr_ar = self._screen_w / self._screen_h
        
        if cam_ar > scr_ar:
            # Camera wider - letterbox vertically
            scale = self._screen_w / self._camera_w
            offset_y = (self._screen_h - self._camera_h * scale) / 2
            sx = cx * self._screen_w
            sy = cy * self._camera_h * scale + offset_y
        else:
            # Camera taller - pillarbox horizontally
            scale = self._screen_h / self._camera_h
            offset_x = (self._screen_w - self._camera_w * scale) / 2
            sx = cx * self._camera_w * scale + offset_x
            sy = cy * self._screen_h
        
        # Dead zone
        if self._last_raw:
            dx = abs(sx - self._last_raw[0])
            dy = abs(sy - self._last_raw[1])
            if dx < self._dead_zone and dy < self._dead_zone:
                return
        self._last_raw = (sx, sy)
        
        # Exponential smoothing
        self._smoothed_x = self._smoothed_x + self._smoothing * (sx - self._smoothed_x)
        self._smoothed_y = self._smoothed_y + self._smoothing * (sy - self._smoothed_y)
        
        # Clamp to screen
        self._smoothed_x = max(0, min(self._screen_w - 1, self._smoothed_x))
        self._smoothed_y = max(0, min(self._screen_h - 1, self._smoothed_y))
        
        # Emit cursor move command
        if self.command_bus:
            cmd = Command(
                name="cursor_move",
                source="hand_cursor",
                params={
                    "x": int(self._smoothed_x),
                    "y": int(self._smoothed_y),
                    "hand": hand_label
                }
            )
            self.command_bus.dispatch(cmd)


class PinchClickPlugin(PluginBase):
    """Detects pinch gesture and emits click commands."""
    
    name = "pinch_click"
    
    def __init__(self):
        self.event_bus = None
        self.command_bus = None
        self._running = False
        self._pinch_threshold = 0.08
        self._pinch_active = {}
    
    def initialize(self, container):
        self.event_bus = container.resolve("event_bus")
        self.command_bus = container.resolve("command_bus")
        
        self.event_bus.subscribe("vision_hand_detected", self._on_hand_detected)
        self._running = True
    
    def shutdown(self):
        self._running = False
        if self.event_bus:
            self.event_bus.unsubscribe("vision_hand_detected", self._on_hand_detected)
    
    def _on_hand_detected(self, event):
        if not self._running:
            return
        
        hands = event.data.get("hands", [])
        for hand in hands:
            label = hand.get("label", "Unknown")
            landmarks = hand.get("landmarks", [])
            
            if len(landmarks) < 9:
                continue
            
            # Check pinch: thumb tip (4) to index tip (8)
            thumb = landmarks[4]
            index = landmarks[8]
            
            dx = thumb.get("x", 0) - index.get("x", 0)
            dy = thumb.get("y", 0) - index.get("y", 0)
            dz = thumb.get("z", 0) - index.get("z", 0)
            dist = (dx*dx + dy*dy + dz*dz) ** 0.5
            
            is_pinching = dist < self._pinch_threshold
            was_pinching = self._pinch_active.get(label, False)
            
            if is_pinching and not was_pinching:
                # Pinch started - emit click
                self._pinch_active[label] = True
                if self.command_bus:
                    cmd = Command(
                        name="cursor_click",
                        source="hand_pinch",
                        params={
                            "hand": label,
                            "position": {"x": index.get("x", 0.5), "y": index.get("y", 0.5)}
                        }
                    )
                    self.command_bus.dispatch(cmd)
            elif not is_pinching and was_pinching:
                # Pinch released
                self._pinch_active[label] = False