"""
Hand Perception Plugin (Phase D) - MediaPipe GestureRecognizer as a plugin.

Rewrites legacy perception/hand_plugin.py as a PluginBase that emits
hand detection events to EventBus for Phase C gesture input plugin to consume.
"""

import threading
import time
import cv2
import mediapipe as mp
import numpy as np

from aether.core.plugin import PluginBase
from aether.core.event_bus import EventBus


class FrameBroker:
    """Thread-safe frame broker for sharing camera frames between plugins."""
    
    def __init__(self):
        self._frame = None
        self._lock = threading.Lock()
        self._consumers = {}
        self._event = threading.Event()
    
    def update_frame(self, frame):
        with self._lock:
            self._frame = frame.copy() if frame is not None else None
        self._event.set()
        # Notify all consumers
        for ev in self._consumers.values():
            ev.set()
    
    def get_frame(self):
        with self._lock:
            return self._frame.copy() if self._frame is not None else None
    
    def register_consumer(self, name):
        """Register a consumer and return its event."""
        ev = threading.Event()
        self._consumers[name] = ev
        return ev
    
    def unregister_consumer(self, name):
        self._consumers.pop(name, None)


class HandPerceptionPlugin(PluginBase):
    """MediaPipe GestureRecognizer running as a daemon plugin.
    
    Consumes frames from FrameBroker, runs gesture recognition,
    emits HAND_DETECTED events with landmarks + gesture classification.
    """
    
    name = "hand_perception"
    
    def __init__(self, model_path="models/gesture_recognizer.task", config=None):
        super().__init__()
        self.model_path = model_path
        self.config = config or {}
        self._broker = None
        self._running = False
        self._thread = None
        self._frame_event = None
    
    def initialize(self, container):
        """Initialize plugin with container dependencies."""
        self.event_bus = container.resolve("event_bus")
        self._broker = container.resolve("frame_broker", default=FrameBroker())
        
        # Register as consumer
        self._frame_event = self._broker.register_consumer("hand_perception")
        
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
    
    def shutdown(self):
        self._running = False
        if self._frame_event:
            self._frame_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._broker:
            self._broker.unregister_consumer("hand_perception")
    
    def _run(self):
        """Main recognition loop."""
        try:
            # Load MediaPipe GestureRecognizer
            base_options = mp.tasks.BaseOptions(model_asset_path=self.model_path)
            options = mp.tasks.vision.GestureRecognizerOptions(
                base_options=base_options,
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_hands=self.config.get("num_hands", 2),
                min_hand_detection_confidence=self.config.get("min_hand_detection_confidence", 0.5),
                min_hand_presence_confidence=self.config.get("min_hand_presence_confidence", 0.5),
                min_tracking_confidence=self.config.get("min_tracking_confidence", 0.5),
            )
            
            recognizer = mp.tasks.vision.GestureRecognizer.create_from_options(options)
            
            while self._running:
                self._frame_event.wait(timeout=1.0)
                if not self._running:
                    break
                self._frame_event.clear()
                
                frame = self._broker.get_frame()
                if frame is None:
                    continue
                
                # Convert BGR to RGB
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                timestamp = int(time.time() * 1000)
                
                # Recognize
                result = recognizer.recognize_for_video(mp_image, timestamp)
                
                # Convert to event format
                observations = []
                if result.hand_landmarks:
                    for idx, landmarks in enumerate(result.hand_landmarks):
                        label = "Unknown"
                        if result.handedness and idx < len(result.handedness):
                            label = result.handedness[idx][0].category_name
                        
                        pts = [{"x": lm.x, "y": lm.y, "z": lm.z} for lm in landmarks]
                        
                        gesture_name = "Unknown"
                        gesture_score = 0.0
                        if result.gestures and idx < len(result.gestures):
                            top = result.gestures[idx][0]
                            gesture_name = top.category_name
                            gesture_score = top.score
                        
                        observations.append({
                            "label": label,
                            "landmarks": pts,
                            "gesture": gesture_name,
                            "gesture_score": gesture_score,
                        })
                
                # Emit event
                if self.event_bus:
                    self.event_bus.publish("vision_hand_detected", {"hands": observations})
        
        except Exception as e:
            if self.event_bus:
                self.event_bus.publish("system_error", {"source": "hand_perception", "error": str(e)})


class FrameBrokerPlugin(PluginBase):
    """Provides FrameBroker as a shared service."""
    
    name = "frame_broker"
    
    def __init__(self):
        self._broker = FrameBroker()
    
    def initialize(self, container):
        container.register_instance("frame_broker", self._broker)
    
    def shutdown(self):
        pass