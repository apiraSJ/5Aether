import logging
import threading
import time
import tkinter as tk
import numpy as np
import cv2

try:
    import dearpygui.dearpygui as dpg
except Exception:
    dpg = None

from core.app import AetherApp
from core.event_bus import EventType
from core.frame_broker import FrameBroker
from perception.hand_plugin import HandPerceptionPlugin
from perception.object_plugin import ObjectSpatialPlugin


logger = logging.getLogger("Aether.Main")

# ─── MediaPipe native gestures → commands ────────────────────────
GESTURE_COMMAND_MAP = {
    "Closed_Fist":  "Cancel / Close",
    "Open_Palm":    "Toggle UI",
    "Pointing_Up":  "Move Cursor",
    "Thumb_Up":     "Confirm / Accept",
    "Thumb_Down":   "Reject / Deny",
    "Victory":      "Copy / Select",
    "ILoveYou":     "Show Help",
    "Unknown":      "",
}

# Cooldown: prevent popup spam for same gesture (seconds)
_GESTURE_COOLDOWN = 1.5

# ─── Global runtime state ────────────────────────────────────────
runtime_hands = []
runtime_objects = []
runtime_cursor = (0.5, 0.5)
runtime_gesture = None
runtime_command = ""
_last_popup_gesture = None
_last_popup_time = 0.0
state_lock = threading.Lock()

# ─── Command popup (thread-safe) ─────────────────────────────────
_popup_queue = []


def _show_command_popup(gesture_name, command_name):
    _popup_queue.append((gesture_name, command_name))


def _process_popups():
    global _last_popup_gesture, _last_popup_time
    while _popup_queue:
        gesture_name, command_name = _popup_queue.pop(0)
        now = time.time()
        if gesture_name == _last_popup_gesture and (now - _last_popup_time) < _GESTURE_COOLDOWN:
            continue
        _last_popup_gesture = gesture_name
        _last_popup_time = now
        try:
            _create_popup_window(gesture_name, command_name)
        except Exception as e:
            logger.error(f"Popup error: {e}")


def _create_popup_window(gesture_name, command_name):
    win = tk.Tk()
    win.title("Aether Command")
    win.geometry("350x220")
    win.configure(bg="#1e1e2e")
    win.attributes("-topmost", True)
    win.resizable(False, False)

    tk.Label(win, text="AETHER COMMAND", font=("Segoe UI", 14, "bold"),
             fg="#00ffff", bg="#1e1e2e").pack(pady=(15, 5))

    gesture_frame = tk.Frame(win, bg="#2a2a3e", highlightbackground="#444", highlightthickness=1)
    gesture_frame.pack(padx=20, pady=5, fill="x")
    tk.Label(gesture_frame, text="Gesture", font=("Segoe UI", 10), fg="#888", bg="#2a2a3e").pack(anchor="w", padx=10, pady=(5, 0))
    tk.Label(gesture_frame, text=gesture_name, font=("Segoe UI", 16, "bold"), fg="#00ff88", bg="#2a2a3e").pack(anchor="w", padx=10, pady=(0, 5))

    command_frame = tk.Frame(win, bg="#2a2a3e", highlightbackground="#444", highlightthickness=1)
    command_frame.pack(padx=20, pady=5, fill="x")
    tk.Label(command_frame, text="Command", font=("Segoe UI", 10), fg="#888", bg="#2a2a3e").pack(anchor="w", padx=10, pady=(5, 0))
    tk.Label(command_frame, text=command_name, font=("Segoe UI", 14, "bold"), fg="#ffaa00", bg="#2a2a3e").pack(anchor="w", padx=10, pady=(0, 5))

    tk.Button(win, text="OK", command=win.destroy, font=("Segoe UI", 11, "bold"),
              bg="#3a3a5e", fg="white", activebackground="#5a5a8e", width=12, relief="flat").pack(pady=10)


# ─── Bus event handlers ──────────────────────────────────────────
def on_hand_update(event):
    global runtime_hands, runtime_gesture, runtime_command, runtime_cursor
    with state_lock:
        runtime_hands = event.data.get("hands", [])
        if runtime_hands:
            top = runtime_hands[0]
            runtime_gesture = top.get("gesture", "Unknown")
            cmd = GESTURE_COMMAND_MAP.get(runtime_gesture, "")
            runtime_command = cmd
            if runtime_gesture not in ("Unknown", "") and cmd:
                _show_command_popup(runtime_gesture, cmd)
            pts = top.get("landmarks", [])
            if pts and len(pts) > 8:
                runtime_cursor = (pts[8]["x"], pts[8]["y"])
        else:
            runtime_gesture = None
            runtime_command = ""


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


# ─── HUD drawing ─────────────────────────────────────────────────
def process_hud_overlays(frame, hands, objects):
    h, w = frame.shape[:2]

    for obj in objects:
        x1, y1, x2, y2 = obj["box"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
        lbl = f"{obj['name']} ({obj['conf']:.2f}) {obj['distance_z']:.1f}m"
        cv2.putText(frame, lbl, (x1, max(y1 - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

    connections = [
        (0, 1), (1, 2), (2, 3), (3, 4),
        (0, 5), (5, 6), (6, 7), (7, 8),
        (5, 9), (9, 10), (10, 11), (11, 12),
        (9, 13), (13, 14), (14, 15), (15, 16),
        (13, 17), (17, 18), (18, 19), (19, 20),
        (0, 17),
    ]
    for hand in hands:
        pts = np.array([[int(lm["x"] * w), int(lm["y"] * h)] for lm in hand["landmarks"]])
        for pt in pts:
            cv2.circle(frame, tuple(pt), 4, (0, 255, 0), -1)
        for a, b in connections:
            if a < len(pts) and b < len(pts):
                cv2.line(frame, tuple(pts[a]), tuple(pts[b]), (255, 0, 0), 1)
        cv2.putText(frame, hand["label"], tuple(pts[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    return frame


# ─── Main ────────────────────────────────────────────────────────
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    logger.info("Starting Aether...")

    app = AetherApp("config/desktop.yaml")
    app.initialize()

    bus = app.event_bus
    broker = FrameBroker()

    bus.subscribe(EventType.HAND_DETECTED, on_hand_update)
    bus.subscribe(EventType.OBJECT_DETECTED, on_object_update)

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

    # 3. DearPyGui UI
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
                    dpg.add_text("Command", color=[0, 255, 255])
                    dpg.add_text("None", tag="command_display")

        dpg.setup_dearpygui()
        dpg.show_viewport()
        logger.info("Dashboard ready.")

        # 4. Render loop
        while dpg.is_dearpygui_running():
            _process_popups()

            raw_frame = broker.get_frame()
            if raw_frame is not None:
                with state_lock:
                    current_hands = list(runtime_hands)
                    current_objects = list(runtime_objects)
                    current_cursor = runtime_cursor
                    current_gesture = runtime_gesture
                    current_command = runtime_command

                processed = process_hud_overlays(raw_frame.copy(), current_hands, current_objects)

                h, w = processed.shape[:2]
                cx = max(0, min(w - 1, int(current_cursor[0] * w)))
                cy = max(0, min(h - 1, int(current_cursor[1] * h)))
                cv2.line(processed, (cx - 12, cy), (cx + 12, cy), (0, 255, 255), 2)
                cv2.line(processed, (cx, cy - 12), (cx, cy + 12), (0, 255, 255), 2)
                cv2.circle(processed, (cx, cy), 16, (0, 255, 255), 1)
                cv2.circle(processed, (cx, cy), 2, (0, 0, 255), -1)

                if current_gesture and current_gesture != "Unknown":
                    cv2.putText(processed, f"{current_gesture} -> {current_command}", (10, h - 16),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

                mode_text = "ACTIVE" if current_gesture and current_gesture != "Unknown" else "PASSIVE"
                mode_color = (0, 255, 0) if mode_text == "ACTIVE" else (100, 100, 100)
                cv2.putText(processed, f"Mode: {mode_text}", (w - 200, h - 28),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, mode_color, 1)
                cv2.putText(processed, f"Hands: {len(current_hands)}", (w - 200, h - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

                rgba = cv2.cvtColor(processed, cv2.COLOR_BGR2RGBA)
                float_texture = np.ascontiguousarray(rgba, dtype=np.float32) / 255.0
                dpg.set_value("hud_texture", float_texture)

                if dpg.does_item_exist("obj_count"):
                    dpg.set_value("obj_count", f"Objects: {len(current_objects)}")
                if dpg.does_item_exist("hand_count"):
                    dpg.set_value("hand_count", f"Hands: {len(current_hands)}")
                if dpg.does_item_exist("gesture_display"):
                    dpg.set_value("gesture_display", current_gesture or "None")
                if dpg.does_item_exist("command_display"):
                    dpg.set_value("command_display", current_command or "None")

            dpg.render_dearpygui_frame()

        dpg.destroy_context()

    except Exception as e:
        logger.warning(f"DearPyGui failed ({e}). Using OpenCV fallback.")
        use_dpg = False
        try:
            dpg.destroy_context()
        except Exception:
            pass

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
                    current_gesture = runtime_gesture
                    current_command = runtime_command

                processed = process_hud_overlays(raw_frame.copy(), current_hands, current_objects)
                h, w = processed.shape[:2]
                cx = max(0, min(w - 1, int(current_cursor[0] * w)))
                cy = max(0, min(h - 1, int(current_cursor[1] * h)))
                cv2.line(processed, (cx - 12, cy), (cx + 12, cy), (0, 255, 255), 2)
                cv2.line(processed, (cx, cy - 12), (cx, cy + 12), (0, 255, 255), 2)
                cv2.circle(processed, (cx, cy), 16, (0, 255, 255), 1)

                if current_gesture and current_gesture != "Unknown":
                    cv2.putText(processed, f"{current_gesture} -> {current_command}", (10, h - 16),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

                cv2.putText(processed, "Press 'q' to exit", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

                cv2.imshow("Aether", processed)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
        except KeyboardInterrupt:
            pass
        finally:
            cv2.destroyAllWindows()

    hand_worker.stop()
    obj_worker.stop()
    app.plugin_manager.shutdown_all()
    app.shutdown()
    logger.info("Aether shutdown complete")


if __name__ == "__main__":
    main()
