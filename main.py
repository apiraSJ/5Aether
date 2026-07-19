import logging
import threading
import time
import numpy as np
import cv2

from core.app import AetherApp
from core.event_bus import EventType
from core.frame_broker import FrameBroker
from perception.hand_plugin import HandPerceptionPlugin
from perception.object_plugin import ObjectSpatialPlugin

# Global runtime state updated by bus subscribers
runtime_hands = []
runtime_objects = []
state_lock = threading.Lock()


def on_hand_update(event):
    global runtime_hands
    with state_lock:
        runtime_hands = event.data.get("hands", [])


def on_object_update(event):
    global runtime_objects
    with state_lock:
        runtime_objects = event.data.get("objects", [])


def camera_producer(broker: FrameBroker, device_index: int = 0, width: int = 640, height: int = 480):
    """Camera capture loop feeding frames into the FrameBroker."""
    cap = cv2.VideoCapture(device_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if not cap.isOpened():
        logging.getLogger("Aether.Main").error(f"Failed to open camera {device_index}")
        return
    logging.getLogger("Aether.Main").info(f"Camera started (index={device_index})")
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break
        broker.update_frame(frame)
        time.sleep(0.016)
    cap.release()


def process_hud_overlays(frame, hands, objects):
    """Draws tracking assets, skeletal vectors, and spatial metrics onto output frames."""
    h, w = frame.shape[:2]

    # Render YOLO objects with bounding boxes and distance
    for obj in objects:
        x1, y1, x2, y2 = obj["box"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
        lbl = f"{obj['name']} ({obj['conf']:.2f}) Z: {obj['distance_z']:.2f}m"
        cv2.putText(frame, lbl, (x1, max(y1 - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

    # Render hand landmarks + connections
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


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    logger = logging.getLogger("Aether.Main")
    logger.info("Starting Aether...")

    # 1. Initialize core
    app = AetherApp("config/desktop.yaml")
    app.initialize()

    # 2. Initialize infrastructural components
    bus = app.event_bus
    broker = FrameBroker()

    bus.subscribe(EventType.HAND_DETECTED, on_hand_update)
    bus.subscribe(EventType.OBJECT_DETECTED, on_object_update)

    # 3. Spawn concurrent perception pipelines
    cam_config = app.settings.get("camera") or {}
    hand_config = app.settings.get("hand_tracking") or {}
    model_config = app.settings.get("model") or {}

    hand_worker = HandPerceptionPlugin(broker, bus, hand_config.get("model_path", "models/hand_landmarker.task"), hand_config)
    obj_worker = ObjectSpatialPlugin(broker, bus, model_config.get("weights", "yolov8n.pt"), model_config)

    hand_worker.start()
    obj_worker.start()

    cam_thread = threading.Thread(
        target=camera_producer,
        args=(broker, cam_config.get("device_index", 0), cam_config.get("width", 640), cam_config.get("height", 480)),
        daemon=True,
    )
    cam_thread.start()

    # 4. DearPyGui UI
    use_dpg = True
    try:
        import dearpygui.dearpygui as dpg
        dpg.create_context()
        dpg.create_viewport(title="Aether Framework - Phase 2 Engine", width=1024, height=600)

        blank_texture = np.zeros((480, 640, 4), dtype=np.float32)
        blank_texture[..., 3] = 1.0
        with dpg.texture_registry(show=False):
            dpg.add_dynamic_texture(width=640, height=480, default_value=blank_texture, tag="hud_texture")

        with dpg.window(label="Aether Core Execution Platform", width=1024, height=600):
            with dpg.group(horizontal=True):
                dpg.add_image("hud_texture")
                with dpg.child_window(width=340, height=480, label="Metrics Dashboard"):
                    dpg.add_text("Aether Perception Engine", color=[0, 255, 255])
                    dpg.add_separator()
                    dpg.add_text("Spatial Pipeline Nodes:")
                    dpg.add_text("  YOLO Object Detection: Running")
                    dpg.add_text("  MediaPipe Hand Tracking: Running")
                    dpg.add_text("  PnP Spatial Estimation: Running")
                    dpg.add_separator()
                    dpg.add_text("Objects: 0", tag="obj_count")
                    dpg.add_text("Hands: 0", tag="hand_count")

        dpg.setup_dearpygui()
        dpg.show_viewport()
        logger.info("Dashboard ready.")

        # 5. Render loop
        while dpg.is_dearpygui_running():
            raw_frame = broker.get_frame()
            if raw_frame is not None:
                with state_lock:
                    current_hands = list(runtime_hands)
                    current_objects = list(runtime_objects)

                processed = process_hud_overlays(raw_frame.copy(), current_hands, current_objects)

                rgba = cv2.cvtColor(processed, cv2.COLOR_BGR2RGBA)
                float_texture = np.ascontiguousarray(rgba, dtype=np.float32) / 255.0
                dpg.set_value("hud_texture", float_texture)

                if dpg.does_item_exist("obj_count"):
                    dpg.set_value("obj_count", f"Objects: {len(current_objects)}")
                if dpg.does_item_exist("hand_count"):
                    dpg.set_value("hand_count", f"Hands: {len(current_hands)}")

            dpg.render_dearpygui_frame()

        dpg.destroy_context()

    except Exception as e:
        logger.warning(f"DearPyGui failed ({e}). Using OpenCV fallback.")
        use_dpg = False
        try:
            import dearpygui.dearpygui as dpg
            dpg.destroy_context()
        except Exception:
            pass

    # 6. OpenCV fallback
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

                processed = process_hud_overlays(raw_frame.copy(), current_hands, current_objects)

                cv2.putText(processed, "Aether Spatial Assistant", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.putText(processed, "Press 'q' to exit", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

                cv2.imshow("Aether", processed)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
        except KeyboardInterrupt:
            pass
        finally:
            cv2.destroyAllWindows()

    # 7. Cleanup
    hand_worker.stop()
    obj_worker.stop()
    app.plugin_manager.shutdown_all()
    app.shutdown()
    logger.info("Aether shutdown complete")


if __name__ == "__main__":
    main()
