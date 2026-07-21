"""
Aether — CV Pipeline + Gesture Interaction

Camera → GestureRecognizer → cursor on camera feed + fullscreen overlay
Pinch = CLICK (both hands). Panels open via gestures.
"""

import sys
import math
import time
import logging
import threading
import queue

import numpy as np
import cv2

try:
    import dearpygui.dearpygui as dpg
except Exception:
    dpg = None

from core.app import AetherApp
from core.event_bus import EventBus, EventType
from core.frame_broker import FrameBroker
from core.cursor_manager import CursorManager
from perception.hand_plugin import HandPerceptionPlugin
from perception.object_plugin import ObjectSpatialPlugin
from memory.storage import MemoryStorage
from context.context_manager import ContextManager
from interface.cursor_overlay import CursorOverlay


logger = logging.getLogger("Aether.Main")

# ─── Runtime state ───────────────────────────────────────────────
runtime_hands = []
runtime_objects = []
runtime_cursor = None       # (x_norm, y_norm)
runtime_pinch = False
runtime_gesture = "Unknown"
state_lock = threading.Lock()

# ─── Thread-safe action queue ────────────────────────────────────
# Perception thread pushes actions here, main loop processes them
_action_queue = queue.Queue()

# ─── Config ──────────────────────────────────────────────────────
PINCH_THRESHOLD = 0.06
GESTURE_COOLDOWN = 1.2
_last_gesture = None
_last_gesture_time = 0.0
_was_pinching = False


# ─── Hand detection (checks ALL hands) ───────────────────────────
def on_hand_update(event):
    global runtime_hands, runtime_cursor, runtime_pinch, runtime_gesture
    global _last_gesture, _last_gesture_time, _was_pinching

    hands = event.data.get("hands", [])

    with state_lock:
        runtime_hands = hands

        if not hands:
            runtime_cursor = None
            runtime_pinch = False
            runtime_gesture = "Unknown"
            _was_pinching = False
            return

        # ── Check ALL hands for pinch + cursor ───────────────────
        any_pinching = False
        best_cursor = None
        best_gesture = "Unknown"

        for hand in hands:
            lm = hand.get("landmarks", [])
            if not lm or len(lm) < 21:
                continue

            idx = lm[8]
            thumb = lm[4]
            dx = idx["x"] - thumb["x"]
            dy = idx["y"] - thumb["y"]
            dist = math.sqrt(dx * dx + dy * dy)
            is_pinch = dist < PINCH_THRESHOLD

            if is_pinch:
                any_pinching = True

            if best_cursor is None:
                best_cursor = (idx["x"], idx["y"])
                best_gesture = hand.get("gesture", "Unknown")

        runtime_pinch = any_pinching
        runtime_cursor = best_cursor
        runtime_gesture = best_gesture

        # ── Gesture → action (queued to main thread) ─────────────
        now = time.time()
        gesture = best_gesture
        cooldown_ok = (gesture != _last_gesture) or (now - _last_gesture_time) > GESTURE_COOLDOWN

        if gesture != "Unknown" and gesture != "Pointing_Up" and cooldown_ok:
            _action_queue.put(("gesture", gesture))
            _last_gesture = gesture
            _last_gesture_time = now

        # ── Pinch = CLICK (any hand, edge-triggered) ─────────────
        if any_pinching and not _was_pinching:
            _action_queue.put(("pinch_click", runtime_cursor))
        _was_pinching = any_pinching


def on_object_update(event):
    global runtime_objects
    with state_lock:
        runtime_objects = event.data.get("objects", [])


# ─── Camera producer ─────────────────────────────────────────────
def camera_producer(broker, device_index=0, width=640, height=480):
    cap = cv2.VideoCapture(device_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if not cap.isOpened():
        logger.error(f"Failed to open camera {device_index}")
        return
    logger.info(f"Camera started (index={device_index})")
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break
        broker.update_frame(frame)
        time.sleep(0.016)
    cap.release()


# ─── Process queued actions on main thread ────────────────────────
def process_action_queue(cursor_mgr, ui, qapp):
    """Called from main loop — processes gesture actions on the Qt thread."""
    while not _action_queue.empty():
        try:
            action_type, data = _action_queue.get_nowait()
        except queue.Empty:
            break

        if action_type == "gesture":
            _handle_gesture_action(data, ui)
        elif action_type == "pinch_click":
            _handle_pinch_click(data, ui)


def _handle_gesture_action(gesture, ui):
    """Execute gesture action on the main thread (safe for Qt)."""
    if gesture == "Open_Palm":
        ui.show()
        ui.raise_()
        ui.activateWindow()
        ui.show_panel("system")
        logger.info("Gesture: Open_Palm → show system panel")
    elif gesture == "Victory":
        ui.show()
        ui.raise_()
        ui.show_panel("developer")
        logger.info("Gesture: Victory → show developer panel")
    elif gesture == "ILoveYou":
        ui.show()
        ui.raise_()
        ui.show_panel("settings")
        logger.info("Gesture: ILoveYou → show settings panel")
    elif gesture == "Closed_Fist":
        ui.hide()
        logger.info("Gesture: Closed_Fist → hide UI")
    elif gesture == "Thumb_Up":
        ui.set_mode("normal")
        logger.info("Gesture: Thumb_Up → normal mode")
    elif gesture == "Thumb_Down":
        ui.set_mode("developer")
        logger.info("Gesture: Thumb_Down → developer mode")


def _handle_pinch_click(cursor, ui):
    """Pinch = CLICK. Log it, could trigger button press."""
    logger.info(f"Pinch CLICK at {cursor}")


# ─── Draw cursor on camera frame ─────────────────────────────────
def draw_cursor_on_frame(frame, cx_norm, cy_norm, is_pinch, gesture):
    h, w = frame.shape[:2]
    cx = int((1.0 - cx_norm) * w)
    cy = int(cy_norm * h)
    cx = max(0, min(w - 1, cx))
    cy = max(0, min(h - 1, cy))

    if is_pinch:
        color = (0, 0, 255)
        glow_alpha = 0.8
        label_text = "CLICK"
    else:
        color = (0, 255, 200)
        glow_alpha = 0.4
        label_text = gesture.replace("_", " ") if gesture and gesture != "Unknown" else ""

    overlay = frame.copy()
    cv2.circle(overlay, (cx, cy), 28, color, -1)
    cv2.addWeighted(overlay, glow_alpha, frame, 1 - glow_alpha, 0, frame)
    cv2.circle(frame, (cx, cy), 20, color, 2, cv2.LINE_AA)
    cv2.circle(frame, (cx, cy), 4, (255, 255, 255), -1, cv2.LINE_AA)

    ch = 10
    cv2.line(frame, (cx - ch, cy), (cx - 6, cy), color, 1, cv2.LINE_AA)
    cv2.line(frame, (cx + 6, cy), (cx + ch, cy), color, 1, cv2.LINE_AA)
    cv2.line(frame, (cx, cy - ch), (cx, cy - 6), color, 1, cv2.LINE_AA)
    cv2.line(frame, (cx, cy + 6), (cx, cy + ch), color, 1, cv2.LINE_AA)

    if label_text:
        cv2.putText(frame, label_text, (cx + 26, cy + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


def draw_pinch_line(frame, lm, is_pinch):
    if not is_pinch or not lm or len(lm) < 21:
        return
    h, w = frame.shape[:2]
    idx = lm[8]
    thumb = lm[4]
    p1 = (int((1.0 - idx["x"]) * w), int(idx["y"] * h))
    p2 = (int((1.0 - thumb["x"]) * w), int(thumb["y"] * h))
    cv2.line(frame, p1, p2, (0, 0, 255), 2, cv2.LINE_AA)
    cv2.circle(frame, p1, 6, (0, 0, 255), -1, cv2.LINE_AA)
    cv2.circle(frame, p2, 6, (0, 0, 255), -1, cv2.LINE_AA)


# ─── HUD drawing ─────────────────────────────────────────────────
def process_hud_overlays(frame, hands, objects):
    h, w = frame.shape[:2]

    for obj in objects:
        x1, y1, x2, y2 = obj["box"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
        lbl = f"{obj['name']} ({obj['conf']:.2f}) {obj.get('distance_z', 0):.1f}m"
        cv2.putText(frame, lbl, (x1, max(y1 - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

    connections = [
        (0, 1), (1, 2), (2, 3), (3, 4),
        (0, 5), (5, 6), (6, 7), (7, 8),
        (5, 9), (9, 10), (10, 11), (11, 12),
        (9, 13), (13, 14), (14, 15), (15, 16),
        (13, 17), (17, 18), (18, 19), (19, 20),
        (0, 17),
    ]

    for hand in hands:
        lm = hand.get("landmarks", [])
        if not lm or len(lm) < 21:
            continue

        pts = np.array([[int((1.0 - l["x"]) * w), int(l["y"] * h)] for l in lm])

        for a, b in connections:
            cv2.line(frame, tuple(pts[a]), tuple(pts[b]), (255, 180, 0), 1, cv2.LINE_AA)

        for i, pt in enumerate(pts):
            radius = 5 if i in (4, 8, 12, 16, 20) else 3
            cv2.circle(frame, tuple(pt), radius, (0, 255, 0), -1, cv2.LINE_AA)

        idx = lm[8]
        thumb = lm[4]
        dx = idx["x"] - thumb["x"]
        dy = idx["y"] - thumb["y"]
        hand_pinch = math.sqrt(dx * dx + dy * dy) < PINCH_THRESHOLD
        draw_pinch_line(frame, lm, hand_pinch)

        cv2.putText(frame, hand.get("label", ""), tuple(pts[0]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)

    return frame


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

    # ── Core app ─────────────────────────────────────────────────
    app = AetherApp("config/desktop.yaml")
    app.initialize()
    bus = app.event_bus
    broker = FrameBroker()

    # ── Memory + Context ─────────────────────────────────────────
    memory = MemoryStorage()
    context = ContextManager()

    # ── Cursor manager + fullscreen overlay ──────────────────────
    cursor_manager = CursorManager()
    cursor_overlay = CursorOverlay(cursor_manager)
    cursor_overlay.show()

    # ── PySide6 panels ──────────────────────────────────────────
    from interface.ui import AetherUI, create_system_panel, create_developer_panel, create_settings_panel

    ui = AetherUI(context_manager=context, memory_storage=memory)
    ui.register_panel("system", "SYSTEM", create_system_panel(context))
    ui.register_panel("developer", "DEVELOPER", create_developer_panel())
    ui.register_panel("settings", "SETTINGS", create_settings_panel(memory))

    # ── Subscribe to perception ──────────────────────────────────
    bus.subscribe(EventType.HAND_DETECTED, on_hand_update)
    bus.subscribe(EventType.OBJECT_DETECTED, on_object_update)

    # ── Start perception ─────────────────────────────────────────
    cam_config = app.settings.get("camera") or {}
    hand_config = app.settings.get("hand_tracking") or {}
    model_config = app.settings.get("model") or {}
    model_path = hand_config.get("model_path", "models/gesture_recognizer.task")

    hand_worker = HandPerceptionPlugin(broker, bus, model_path, hand_config)
    obj_worker = ObjectSpatialPlugin(broker, bus, model_config.get("weights", "yolov8n.pt"), model_config)
    hand_worker.start()
    obj_worker.start()

    cam_thread = threading.Thread(
        target=camera_producer,
        args=(broker, cam_config.get("device_index", 0), cam_config.get("width", 640), cam_config.get("height", 480)),
        daemon=True,
    )
    cam_thread.start()

    # ── DearPyGui dashboard ──────────────────────────────────────
    use_dpg = True
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

        # ── Render loop ──────────────────────────────────────────
        while dpg.is_dearpygui_running():
            # Process Qt events + gesture actions on main thread
            qapp.processEvents()
            process_action_queue(cursor_manager, ui, qapp)

            raw_frame = broker.get_frame()
            if raw_frame is not None:
                with state_lock:
                    current_hands = list(runtime_hands)
                    current_objects = list(runtime_objects)
                    current_cursor = runtime_cursor
                    current_pinch = runtime_pinch
                    current_gesture = runtime_gesture

                # Update cursor overlay (fullscreen)
                if current_cursor:
                    cursor_manager.update(
                        hand_x=current_cursor[0],
                        hand_y=current_cursor[1],
                        gesture=current_gesture,
                        is_pinch=current_pinch,
                    )
                else:
                    cursor_manager.hide()

                # Draw camera frame
                processed = process_hud_overlays(raw_frame.copy(), current_hands, current_objects)
                if current_cursor:
                    draw_cursor_on_frame(processed, current_cursor[0], current_cursor[1],
                                         current_pinch, current_gesture)

                h, w = processed.shape[:2]
                gesture_text = current_gesture if current_gesture != "Unknown" else "None"
                cv2.putText(processed, f"Gesture: {gesture_text}", (10, h - 36),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
                pinch_text = "CLICK" if current_pinch else "No"
                pinch_color = (0, 0, 255) if current_pinch else (200, 200, 200)
                cv2.putText(processed, f"Pinch: {pinch_text}", (10, h - 14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, pinch_color, 1, cv2.LINE_AA)
                cv2.putText(processed, f"Hands: {len(current_hands)}", (w - 150, h - 14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)

                rgba = cv2.cvtColor(processed, cv2.COLOR_BGR2RGBA)
                float_texture = np.ascontiguousarray(rgba, dtype=np.float32) / 255.0
                dpg.set_value("hud_texture", float_texture)

                if dpg.does_item_exist("obj_count"):
                    dpg.set_value("obj_count", f"Objects: {len(current_objects)}")
                if dpg.does_item_exist("hand_count"):
                    dpg.set_value("hand_count", f"Hands: {len(current_hands)}")
                if dpg.does_item_exist("gesture_display"):
                    dpg.set_value("gesture_display", gesture_text)
                if dpg.does_item_exist("cursor_pos"):
                    dpg.set_value("cursor_pos", f"({current_cursor[0]:.2f}, {current_cursor[1]:.2f})" if current_cursor else "No hand")
                if dpg.does_item_exist("pinch_status"):
                    dpg.set_value("pinch_status", pinch_text)

            dpg.render_dearpygui_frame()

        dpg.destroy_context()

    except Exception as e:
        logger.warning(f"DearPyGui failed ({e}). Using OpenCV fallback.")
        use_dpg = False
        try:
            dpg.destroy_context()
        except Exception:
            pass

    # ── OpenCV fallback ──────────────────────────────────────────
    if not use_dpg:
        logger.info("Using OpenCV window. Press 'q' to exit.")
        try:
            while True:
                raw_frame = broker.get_frame()
                if raw_frame is None:
                    time.sleep(0.01)
                    continue

                with state_lock:
                    current_hands = list(runtime_hands)
                    current_objects = list(runtime_objects)
                    current_cursor = runtime_cursor
                    current_pinch = runtime_pinch
                    current_gesture = runtime_gesture

                # Update cursor overlay
                if current_cursor:
                    cursor_manager.update(
                        hand_x=current_cursor[0], hand_y=current_cursor[1],
                        gesture=current_gesture, is_pinch=current_pinch,
                    )
                else:
                    cursor_manager.hide()

                processed = process_hud_overlays(raw_frame.copy(), current_hands, current_objects)
                if current_cursor:
                    draw_cursor_on_frame(processed, current_cursor[0], current_cursor[1],
                                         current_pinch, current_gesture)

                cv2.putText(processed, "Press 'q' to exit", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                cv2.imshow("Aether", processed)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
        except KeyboardInterrupt:
            pass
        finally:
            cv2.destroyAllWindows()

    # ── Shutdown ─────────────────────────────────────────────────
    hand_worker.stop()
    obj_worker.stop()
    app.plugin_manager.shutdown_all()
    app.shutdown()
    logger.info("Aether shutdown complete")


if __name__ == "__main__":
    main()
