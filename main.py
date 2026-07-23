"""
Aether — CV Pipeline + Gesture Interaction

Camera → GestureRecognizer → cursor on camera feed + fullscreen overlay
Pinch = CLICK (both hands). Panels open via gestures.
"""

import sys
import time
import logging
import threading

import numpy as np
import cv2

try:
    import dearpygui.dearpygui as dpg
except Exception:
    dpg = None

from core.app import AetherApp
from core.event_bus import EventType
from core.frame_broker import FrameBroker
from core.cursor_manager import CursorManager
from core.gesture_router import GestureRouter
from core.action_queue import ActionQueue
from core.camera_thread import CameraThread
from perception.hand_plugin import HandPerceptionPlugin
from perception.object_plugin import ObjectSpatialPlugin
from memory.storage import MemoryStorage
from context.context_manager import ContextManager
from interface.cursor_overlay import CursorOverlay
from interface.ui_manager import UIManager
from interaction.interaction_manager import InteractionManager
from interface.hud_renderer import process_hud_overlays, draw_cursor_on_frame, draw_status_bar


logger = logging.getLogger("Aether.Main")


# ─── Main ────────────────────────────────────────────────────────
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    logger.info("Starting Aether...")

    # ── PySide6 QApplication ─────────────────────────────────────
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)

    # ── Core app + perception ────────────────────────────────────
    app = AetherApp("config/desktop.yaml")
    app.initialize()
    bus = app.event_bus
    broker = FrameBroker()
    memory = MemoryStorage()
    context = ContextManager()

    # ── Gesture router + action queue ────────────────────────────
    action_queue = ActionQueue()
    gesture_router = GestureRouter(action_queue, event_bus=bus)

    # ── Cursor manager + UI ─────────────────────────────────────
    cursor_manager = CursorManager()
    cursor_overlay = CursorOverlay(cursor_manager)
    cursor_overlay.show()

    # ── UIManager (owns HomeMenu + StatusBar) ────────────────────
    ui_manager = UIManager(cursor_manager, bus)

    # ── InteractionManager (central coordinator) ─────────────────
    interaction = InteractionManager(cursor_manager, ui_manager, bus)

    from interface.ui import AetherUI, create_system_panel, create_developer_panel, create_settings_panel
    ui = AetherUI(context_manager=context, memory_storage=memory)
    ui.register_panel("system", "SYSTEM", create_system_panel(context))
    ui.register_panel("developer", "DEVELOPER", create_developer_panel())
    ui.register_panel("settings", "SETTINGS", create_settings_panel(memory))

    # ── Subscribe to perception ──────────────────────────────────
    bus.subscribe(EventType.HAND_DETECTED, gesture_router.on_hand_update)
    bus.subscribe(EventType.OBJECT_DETECTED, gesture_router.on_object_update)

    # ── Subscribe to UI events ───────────────────────────────────
    def on_panel_show(event):
        panel = event.data.get("panel", "system")
        ui.show()
        ui.raise_()
        ui.show_panel(panel)

    def on_ui_close(event):
        ui.hide()
        ui_manager.home_menu.hide_menu()

    def on_mode_change(event):
        mode = event.data.get("mode", "normal")
        ui.set_mode(mode)

    bus.subscribe(EventType.PANEL_SHOW_REQUESTED, on_panel_show)
    bus.subscribe(EventType.UI_CLOSE, on_ui_close)
    bus.subscribe(EventType.MODE_CHANGED, on_mode_change)

    # ── Start perception workers ─────────────────────────────────
    cam_config = app.settings.get("camera") or {}
    hand_config = app.settings.get("hand_tracking") or {}
    model_config = app.settings.get("model") or {}
    model_path = hand_config.get("model_path", "models/gesture_recognizer.task")

    hand_worker = HandPerceptionPlugin(broker, bus, model_path, hand_config)
    obj_worker = ObjectSpatialPlugin(broker, bus, model_config.get("weights", "yolov8n.pt"), model_config)
    hand_worker.start()
    obj_worker.start()

    # ── Camera → FrameBroker bridge ───────────────────────────────
    cam = CameraThread(cam_config)
    cam.start()

    def _camera_bridge():
        while cam.is_running:
            frame = cam.get_frame()
            if frame is not None:
                broker.update_frame(frame)
            else:
                time.sleep(0.005)

    _bridge_thread = threading.Thread(target=_camera_bridge, daemon=True)
    _bridge_thread.start()

    # ── DearPyGui dashboard ──────────────────────────────────────
    use_dpg = _setup_dpg()

    if use_dpg:
        _run_dpg_loop(qapp, action_queue, gesture_router, cursor_manager, broker, ui, ui_manager, interaction, bus)
    else:
        _run_opencv_fallback(action_queue, gesture_router, cursor_manager, broker, ui_manager)

    # ── Shutdown ─────────────────────────────────────────────────
    cam.stop()
    _bridge_thread.join(timeout=2.0)
    hand_worker.stop()
    obj_worker.stop()
    app.plugin_manager.shutdown_all()
    app.shutdown()
    logger.info("Aether shutdown complete")


def _setup_dpg():
    """Initialize DearPyGui. Returns True if successful."""
    try:
        dpg.create_context()
        dpg.create_viewport(title="Aether Spatial Assistant", width=1024, height=600)

        blank_texture = np.zeros((480, 640, 4), dtype=np.float32)
        blank_texture[..., 3] = 1.0
        with dpg.texture_registry(show=False):
            dpg.add_dynamic_texture(width=640, height=480, default_value=blank_texture, tag="hud_texture")

        with dpg.window(label="Aether Core Execution Platform", width=1024, height=600):
            with dpg.group(horizontal=True):
                dpg.add_image("hud_texture")
                with dpg.child_window(width=340, height=480, label="Metrics Dashboard"):
                    dpg.add_text("AETHER", color=[0, 255, 255])
                    dpg.add_separator()
                    dpg.add_text("Pipeline:")
                    dpg.add_text("  YOLO Object Detection")
                    dpg.add_text("  GestureRecognizer (MediaPipe)")
                    dpg.add_separator()
                    dpg.add_text("Objects: 0", tag="obj_count")
                    dpg.add_text("Hands: 0", tag="hand_count")
                    dpg.add_separator()
                    dpg.add_text("Gesture", color=[0, 255, 255])
                    dpg.add_text("None", tag="gesture_display")
                    dpg.add_separator()
                    dpg.add_text("Cursor", color=[0, 255, 255])
                    dpg.add_text("No hand", tag="cursor_pos")
                    dpg.add_text("Pinch: No", tag="pinch_status")

        dpg.setup_dearpygui()
        dpg.show_viewport()
        logger.info("Dashboard ready.")
        return True
    except Exception as e:
        logger.warning(f"DearPyGui failed ({e}). Using OpenCV fallback.")
        try:
            dpg.destroy_context()
        except Exception:
            pass
        return False


def _run_dpg_loop(qapp, action_queue, gesture_router, cursor_manager, broker, ui, ui_manager, interaction, event_bus):
    """Main DearPyGui render loop."""
    while dpg.is_dearpygui_running():
        qapp.processEvents()
        action_queue.process(cursor_manager, ui, broker, ui_manager, event_bus)

        # Safety net: ensure hover is always up-to-date
        ui_manager.update_hover()

        # Update interaction state (focus, state machine)
        interaction.update()

        raw_frame = broker.get_frame()
        if raw_frame is not None:
            current_hands = gesture_router.hands
            current_objects = gesture_router.objects

            # Get current cursor state from cursor manager
            cursor_state = cursor_manager.get_state()
            current_pinch = cursor_state.is_pinch
            current_gesture = cursor_state.gesture

            # Extract raw normalized hand position for camera-frame cursor
            # (screen coords from cursor_manager are for the overlay only)
            current_cursor_norm = None
            if gesture_router.hands:
                for hand in gesture_router.hands:
                    lm = hand.get("landmarks", [])
                    if lm and len(lm) >= 21:
                        idx = lm[8]  # index finger tip
                        current_cursor_norm = (idx["x"], idx["y"])
                        break

            # Draw camera frame (flipped so user sees mirror-like natural view)
            flipped = cv2.flip(raw_frame, 1)
            processed = process_hud_overlays(flipped, current_hands, current_objects, mirror=True)
            if current_cursor_norm:
                draw_cursor_on_frame(processed, current_cursor_norm[0], current_cursor_norm[1], current_pinch, current_gesture, mirror=True)
            draw_status_bar(processed, current_gesture, current_pinch, len(current_hands))

            rgba = cv2.cvtColor(processed, cv2.COLOR_BGR2RGBA)
            float_texture = np.ascontiguousarray(rgba, dtype=np.float32) / 255.0
            dpg.set_value("hud_texture", float_texture)

            _update_dpg_metrics(current_hands, current_objects, current_cursor_norm, current_pinch, current_gesture)

        dpg.render_dearpygui_frame()

    dpg.destroy_context()


def _update_dpg_metrics(hands, objects, cursor_norm, pinch, gesture):
    """Update DearPyGui metric displays."""
    gesture_text = gesture if gesture != "Unknown" else "None"
    pinch_text = "CLICK" if pinch else "No"

    if dpg.does_item_exist("obj_count"):
        dpg.set_value("obj_count", f"Objects: {len(objects)}")
    if dpg.does_item_exist("hand_count"):
        dpg.set_value("hand_count", f"Hands: {len(hands)}")
    if dpg.does_item_exist("gesture_display"):
        dpg.set_value("gesture_display", gesture_text)
    if dpg.does_item_exist("cursor_pos"):
        dpg.set_value("cursor_pos", f"({cursor_norm[0]:.3f}, {cursor_norm[1]:.3f})" if cursor_norm else "No hand")
    if dpg.does_item_exist("pinch_status"):
        dpg.set_value("pinch_status", pinch_text)


def _run_opencv_fallback(action_queue, gesture_router, cursor_manager, broker, ui_manager):
    """OpenCV fallback when DearPyGui fails."""
    logger.info("Using OpenCV window. Press 'q' to exit.")
    try:
        while True:
            raw_frame = broker.get_frame()
            if raw_frame is None:
                time.sleep(0.01)
                continue

            # Process cursor updates and pinch clicks
            action_queue.process_cursor_updates(cursor_manager)
            action_queue.process_pinch_clicks(ui_manager)

            # Update HomeMenu hover
            ui_manager.update_hover()

            current_hands = gesture_router.hands
            current_objects = gesture_router.objects

            cursor_state = cursor_manager.get_state()
            current_pinch = cursor_state.is_pinch
            current_gesture = cursor_state.gesture

            # Extract raw normalized hand position for camera-frame cursor
            current_cursor_norm = None
            if current_hands:
                for hand in current_hands:
                    lm = hand.get("landmarks", [])
                    if lm and len(lm) >= 21:
                        idx = lm[8]
                        current_cursor_norm = (idx["x"], idx["y"])
                        break

            flipped = cv2.flip(raw_frame, 1)
            processed = process_hud_overlays(flipped, current_hands, current_objects, mirror=True)
            if current_cursor_norm:
                draw_cursor_on_frame(processed, current_cursor_norm[0], current_cursor_norm[1], current_pinch, current_gesture, mirror=True)
            draw_status_bar(processed, current_gesture, current_pinch, len(current_hands))

            cv2.putText(processed, "Press 'q' to exit", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            cv2.imshow("Aether", processed)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
