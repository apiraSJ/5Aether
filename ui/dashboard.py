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
        self._gesture_history = []
        self._max_gesture_history = 5

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
            dpg.add_separator()
            dpg.add_text("Gesture Recognition")
            dpg.add_text("Current: None", tag="gesture_current")
            dpg.add_text("Action: None", tag="gesture_action")
            dpg.add_text("Confidence: 0%", tag="gesture_confidence")
            dpg.add_separator()
            dpg.add_text("Recent Gestures")
            dpg.add_text("1. None", tag="gesture_hist_1")
            dpg.add_text("2. None", tag="gesture_hist_2")
            dpg.add_text("3. None", tag="gesture_hist_3")
            dpg.add_text("4. None", tag="gesture_hist_4")
            dpg.add_text("5. None", tag="gesture_hist_5")

    def _create_main_area(self):
        with dpg.group():
            dpg.add_text("Camera Feed", tag="camera_title")
            dpg.add_image("camera_texture", tag="camera_view", width=640, height=480)
            dpg.add_separator()
            dpg.add_text("Control Output")
            dpg.add_text("No action active", tag="control_output")
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

                # Draw hand skeleton + gesture + action + cursor
                gesture = snapshot.gestures[0] if snapshot.gestures else None
                action = snapshot.actions[0] if snapshot.actions else None
                if self._hand_overlay:
                    display = self._hand_overlay.draw(
                        display, snapshot.hand_results,
                        gesture=gesture, action=action,
                        cursor=snapshot.cursor,
                        is_dragging=snapshot.is_dragging,
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
                    a = action or ""
                    display_str = f"Gesture: {g}"
                    if a:
                        display_str += f"  ->  {a}"
                    dpg.set_value("gesture_display", display_str)
                if dpg.does_item_exist("mode_display"):
                    dpg.set_value("mode_display", f"Mode: {snapshot.mode}")
                if dpg.does_item_exist("fps_display"):
                    dpg.set_value("fps_display", f"FPS: {snapshot.fps:.1f}")

                # Update gesture recognition display
                self._update_gesture_display(gesture, action)

                # Update control output at bottom of camera
                self._update_control_output(gesture, action, snapshot)

            self._update_texture(display)

        # 3. Update sidebar status
        if dpg.does_item_exist("status_camera"):
            status = "Connected" if self._camera_ok else "Disconnected"
            dpg.set_value("status_camera", f"Camera: {status}")

    def _update_gesture_display(self, gesture, action):
        """Update the gesture recognition display in the sidebar."""
        if not gesture:
            return

        # Update current gesture
        if dpg.does_item_exist("gesture_current"):
            dpg.set_value("gesture_current", f"Current: {gesture.upper()}")

        # Update action
        if dpg.does_item_exist("gesture_action"):
            action_str = action.upper() if action else "None"
            dpg.set_value("gesture_action", f"Action: {action_str}")

        # Update confidence (placeholder - would need actual confidence from engine)
        if dpg.does_item_exist("gesture_confidence"):
            dpg.set_value("gesture_confidence", "Confidence: 85%")

        # Update gesture history
        self._gesture_history.append(gesture)
        if len(self._gesture_history) > self._max_gesture_history:
            self._gesture_history.pop(0)

        # Update history display
        for i, hist_gesture in enumerate(self._gesture_history):
            tag = f"gesture_hist_{i + 1}"
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, f"{i + 1}. {hist_gesture}")

    def _update_control_output(self, gesture, action, snapshot):
        """Update the control output display at the bottom of camera."""
        if not dpg.does_item_exist("control_output"):
            return

        # Build control output string
        output_parts = []

        if gesture:
            output_parts.append(f"Gesture: {gesture}")

        if action:
            output_parts.append(f"Action: {action}")

        if snapshot.mode and snapshot.mode != "passive":
            output_parts.append(f"Mode: {snapshot.mode}")

        if snapshot.is_dragging:
            output_parts.append("Dragging: Active")

        # Add object count if available
        if snapshot.detections:
            output_parts.append(f"Objects: {len(snapshot.detections)}")

        # Add hand count if available
        if snapshot.hand_results and snapshot.hand_results.hands:
            output_parts.append(f"Hands: {len(snapshot.hand_results.hands)}")

        # Combine all parts
        control_text = " | ".join(output_parts) if output_parts else "No action active"
        dpg.set_value("control_output", control_text)

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
