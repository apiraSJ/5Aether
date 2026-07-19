import logging
import time
import numpy as np
import cv2

import dearpygui.dearpygui as dpg


class Dashboard:
    def __init__(self, event_bus=None, config: dict = None):
        self.logger = logging.getLogger("Aether.Dashboard")
        self.event_bus = event_bus
        self.config = config or {}
        self._camera = None
        self._perception = None
        self._gesture_engine = None
        self._command_confirmation = None
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
        """Called every DearPyGui frame. Processes camera and updates texture."""
        if not self._initialized:
            return

        # 1. Grab frame from camera thread
        if self._camera:
            frame = self._camera.get_frame()
            if frame is not None:
                self._frame = frame
                self._camera_ok = True
                self._update_texture(frame)
                self._process_frame(frame)
                self._update_fps()

        # 2. Update sidebar status
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

    def _process_frame(self, frame):
        """Run perception pipeline on the frame."""
        if not self._perception:
            return
        try:
            result = self._perception.process(frame)

            # Update detected objects display
            if result.detections:
                self._objects = result.detections
                labels = [d.get("label", "?") for d in result.detections[:5]]
                obj_text = ", ".join(labels)
                if len(result.detections) > 5:
                    obj_text += f" (+{len(result.detections) - 5} more)"
                if dpg.does_item_exist("objects_text"):
                    dpg.set_value("objects_text", obj_text)

            # Run gesture engine
            if result.hand_results and self._gesture_engine:
                gestures = self._gesture_engine.update(result.hand_results)
                for gesture_event in gestures:
                    if self.event_bus:
                        self.event_bus.emit(
                            EventType.GESTURE_RECOGNIZED,
                            data={"gesture": gesture_event.gesture.value},
                            source="gesture_engine"
                        )
                    if dpg.does_item_exist("gesture_display"):
                        dpg.set_value("gesture_display", f"Gesture: {gesture_event.gesture.value}")

                    if self._command_confirmation:
                        actions = self._command_confirmation.handle_gesture(gesture_event)
                        for action in actions:
                            if action.type == "CANCEL":
                                self._command_confirmation.cancel()

        except Exception as e:
            self.logger.error(f"Perception error: {e}")

    def _update_fps(self):
        """Calculate and display FPS."""
        self._frame_count += 1
        now = time.time()
        elapsed = now - self._last_fps_time
        if elapsed >= 1.0:
            self._fps = self._frame_count / elapsed
            self._frame_count = 0
            self._last_fps_time = now
            if dpg.does_item_exist("fps_display"):
                dpg.set_value("fps_display", f"FPS: {self._fps:.1f}")

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
