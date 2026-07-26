"""
Vision perception plugins (Phase D) that integrate legacy CV pipeline
into the new architecture.

These plugins maintain the performance and accuracy of the original
hand/object detection systems while adapting them to the new
command-driven and plugin architecture.

Note: No eager imports here — vision plugins have heavy dependencies
(cv2, mediapipe, ultralytics) that should only load when actually used.
"""

__all__ = [
    "HandPerceptionPlugin",
    "FrameBroker",
    "ObjectSpatialPlugin",
    "CameraPlugin",
    "CursorPlugin",
    "PinchClickPlugin",
]
