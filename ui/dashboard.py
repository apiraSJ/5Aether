import logging
import time
import numpy as np
import cv2

import dearpygui.dearpygui as dpg
from core.event_bus import EventType


class Dashboard:
    def __init__(self, event_bus=None, config: dict = None):
        self.logger = logging.getLogger("Aether.Dashboard")
        self.event_bus = event_bus
        self.config = config or {}
        self._camera = None
        self._perception = None
        self._gesture_engine = None
        self._command_confirmation = None
        self._perception_worker = None
        self._hand_overlay = None
        self._frame = None
        self._objects = []
        self._tasks = []
        self._fps = 0.0
        self._frame_count = 0
        self._last_fps_time = time.time()
        self._initialized = False
        self._camera_ok = False

    def set_camera(self, camera):
        self._camera = camera

    def set_perception(self, perception):
        self._perception = perception

    def set_gesture_engine(self, engine):
        self._gesture_engine = engine

    def set_command_confirmation(self, confirmer):
        self._command_confirmation = confirmer

    def set_perception_worker(self, worker):
        self._perception_worker = worker
        from ui.hand_overlay import HandOverlay
        self._hand_overlay = HandOverlay()

    def initialize(self):
        dpg.create_context()
        dpg.create_viewport(title="Aether Spatial Assistant", width=1280, height=720)

        # Create a placeholder texture (black frame, RGBA)
        placeholder = np.zeros((480, 640, 4), dtype=np.float32)
        placeholder[..., 3] = 1.0

        with dpg.texture_registry():
            dpg.add_dynamic_texture(
                640, 480,
                placeholder.flatten().tolist(),
                tag="camera_texture"
            )

        with dpg.window(tag="main_window"):
            with dpg.group(horizontal=True):
                self._create_sidebar()
                self._create_main_area()
                self._create_status_panel()

        dpg.set_primary_window("main_window", True)

        self._initialized = True
        self.logger.info("Dashboard initialized")

    def run(self):
        """Enter the DearPyGui render loop. Blocks until window is closed."""
        dpg.setup_dearpygui()
        dpg.show_viewport()
        while dpg.is_dearpygui_running():
            self._on_frame(None, None)
            dpg.render_dearpygui_frame()
        dpg.destroy_context()

    def _create_sidebar(self):
        with dpg.group(width=self.config.get("sidebar_width", 280)):
            dpg.add_text("AETHER", tag="app_title")
            dpg.add_separator()
            dpg.add_text("Navigation")
            dpg.add_button(label="Dashboard", tag="nav_dashboard")
            dpg.add_button(label="Objects", tag="nav_objects")
            dpg.add_button(label="Tasks", tag="nav_tasks")
            dpg.add_button(label="Perception", tag="nav_perception")
            dpg.add_button(label="Logs", tag="nav_logs")
            dpg.add_separator()
            dpg.add_text("Perception Status")
            cam_status = "Connected" if (self._camera and self._camera.is_running) else "Disconnected"
            dpg.add_text(f"Camera: {cam_status}", tag="status_camera")
            dpg.add_text("YOLO: Ready", tag="status_yolo")
            dpg.add_text("Hands: Ready", tag="status_hands")

    def _create_main_area(self):
        with dpg.group():
            dpg.add_text("Camera Feed", tag="camera_title")
            dpg.add_image("camera_texture", tag="camera_view", width=640, height=480)
            dpg.add_separator()
            dpg.add_text("Detected Objects")
            dpg.add_text("No objects detected", tag="objects_text")

    def _create_status_panel(self):
        with dpg.group(width=200):
            dpg.add_text("System Status")
            dpg.add_separator()
            dpg.add_text("FPS: 0.0", tag="fps_display")
            dpg.add_text("Gesture: None", tag="gesture_display")
            dpg.add_text("Mode: Passive", tag="mode_display")
            dpg.add_separator()
            dpg.add_text("Tasks")
            dpg.add_text("0 active", tag="tasks_display")

    def _on_frame(self, sender, app_data):
        """Called every DearPyGui frame. Pulls latest perception snapshot
        from the background worker and draws overlays onto the texture."""
        if not self._initialized:
            return

        # 1. Grab the latest camera frame for display
        frame = self._camera.get_frame() if self._camera else None
        if frame is not None:
            self._frame = frame
            self._camera_ok = True

            # 2. Pull perception results computed off-thread by the worker
            snapshot = None
            if self._perception_worker:
                snapshot = self._perception_worker.get_latest()

            display = frame.copy()
            if snapshot:
                # Draw YOLO boxes + PnP distance
                for item in snapshot.pnp:
                    box = item.get("box")
                    if not box:
                        continue
                    x1, y1, x2, y2 = map(int, box)
                    label = item.get("label", "?")
                    conf = item.get("confidence", 0.0)
                    cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    text = f"{label} {conf:.2f}"
                    if item.get("distance_cm") is not None:
                        text += f" {item['distance_cm']:.0f}cm"
                    cv2.putText(display, text, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                # Draw hand skeleton + gesture
                gesture = snapshot.gestures[0] if snapshot.gestures else None
                if self._hand_overlay:
                    display = self._hand_overlay.draw(
                        display, snapshot.hand_results, gesture
                    )

                # Update sidebar text
                labels = [d.get("label", "?") for d in snapshot.detections[:5]]
                obj_text = ", ".join(labels) if labels else "No objects detected"
                if len(snapshot.detections) > 5:
                    obj_text += f" (+{len(snapshot.detections) - 5} more)"
                if dpg.does_item_exist("objects_text"):
                    dpg.set_value("objects_text", obj_text)
                if dpg.does_item_exist("gesture_display"):
                    g = gesture or "None"
                    dpg.set_value("gesture_display", f"Gesture: {g}")
                if dpg.does_item_exist("mode_display"):
                    dpg.set_value("mode_display", f"Mode: {snapshot.mode}")
                if dpg.does_item_exist("fps_display"):
                    dpg.set_value("fps_display", f"FPS: {snapshot.fps:.1f}")

            self._update_texture(display)

        # 3. Update sidebar status
        if dpg.does_item_exist("status_camera"):
            status = "Connected" if self._camera_ok else "Disconnected"
            dpg.set_value("status_camera", f"Camera: {status}")

    def _update_texture(self, frame):
        """Convert BGR frame to DearPyGui texture format and push to GPU."""
        try:
            rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
            resized = cv2.resize(rgba, (640, 480))
            # DearPyGui expects flat float32 list in [0, 1]
            texture_data = (resized.astype(np.float32) / 255.0).flatten().tolist()
            if dpg.does_item_exist("camera_texture"):
                dpg.set_value("camera_texture", texture_data)
        except Exception as e:
            self.logger.error(f"Texture update error: {e}")

    def shutdown(self):
        if self._initialized:
            self._initialized = False
            try:
                import dearpygui.dearpygui as dpg
                if dpg.is_dearpygui_running():
                    dpg.stop_dearpygui()
                dpg.destroy_context()
            except Exception:
                pass
            self.logger.info("Dashboard shut down")
