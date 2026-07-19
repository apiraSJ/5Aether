import sys
import logging
import time
import numpy as np
import cv2

from core.app import AetherApp
from core.event_bus import EventType
from core.camera_thread import CameraThread
from core.perception_pipeline import PerceptionPipeline
from vision.gesture_engine import GestureEngine
from vision.command_confirmation import CommandConfirmation
from memory.object_memory import ObjectMemory
from tasks.manager import TaskManager
from commands import CommandRegistry
from commands.remember import RememberCommand
from commands.find import FindCommand
from commands.forget import ForgetCommand
from commands.list_cmd import ListCommand
from commands.status import StatusCommand
from commands.task import TaskCommand
from database.objects import ObjectStore
from database.tasks import TaskStore


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    )
    logger = logging.getLogger("Aether.Main")
    logger.info("Starting Aether...")

    # 1. Initialize core
    app = AetherApp("config/desktop.yaml")
    app.initialize()

    # 2. Initialize memory, tasks, commands
    memory = ObjectMemory(ObjectStore())
    task_manager = TaskManager(TaskStore())

    registry = CommandRegistry()
    registry.register(RememberCommand(memory))
    registry.register(FindCommand(memory))
    registry.register(ForgetCommand(memory))
    registry.register(ListCommand(memory, task_manager))
    registry.register(StatusCommand(memory))
    registry.register(TaskCommand(task_manager))

    gesture_engine = GestureEngine(app.settings.get("gesture_engine"))
    command_confirmation = CommandConfirmation(app.settings.get("interaction"))
    perception = PerceptionPipeline(app.event_bus, app.plugin_manager)

    # 3. Register perception plugins
    from plugins.yolo_plugin import YoloPlugin
    from plugins.hand_plugin import HandPlugin
    app.plugin_manager.register(YoloPlugin())
    app.plugin_manager.register(HandPlugin())
    app.plugin_manager.initialize_all(app.settings.all)

    # 4. Start camera thread
    camera = None
    camera_config = app.settings.get("camera")
    try:
        camera = CameraThread(camera_config)
        camera.start()
        logger.info("Camera started")
    except Exception as e:
        logger.warning(f"Camera unavailable: {e}. Running without camera feed.")

    # 5. Try DearPyGui dashboard
    use_dpg = True
    try:
        import dearpygui.dearpygui as dpg
        dpg.create_context()
        dpg.create_viewport(title="Aether Spatial Assistant", width=1280, height=720)

        # Create placeholder texture (RGBA — 4 channels per pixel)
        placeholder = np.zeros((480, 640, 4), dtype=np.float32)
        placeholder[..., 3] = 1.0
        with dpg.texture_registry():
            dpg.add_dynamic_texture(640, 480, placeholder.flatten().tolist(), tag="camera_texture")

        with dpg.window(tag="main_window"):
            with dpg.group(horizontal=True):
                # Sidebar
                with dpg.group(width=280):
                    dpg.add_text("AETHER", tag="app_title")
                    dpg.add_separator()
                    dpg.add_text("Navigation")
                    dpg.add_button(label="Dashboard")
                    dpg.add_button(label="Objects")
                    dpg.add_button(label="Tasks")
                    dpg.add_button(label="Perception")
                    dpg.add_button(label="Logs")
                    dpg.add_separator()
                    dpg.add_text("Perception Status")
                    cam_status = "Connected" if (camera and camera.is_running) else "Disconnected"
                    dpg.add_text(f"Camera: {cam_status}", tag="status_camera")
                    dpg.add_text("YOLO: Ready", tag="status_yolo")
                    dpg.add_text("Hands: Ready", tag="status_hands")

                # Main area
                with dpg.group():
                    dpg.add_text("Camera Feed")
                    dpg.add_image("camera_texture", width=640, height=480)
                    dpg.add_separator()
                    dpg.add_text("Detected Objects")
                    dpg.add_text("No objects detected", tag="objects_text")

                # Status panel
                with dpg.group(width=200):
                    dpg.add_text("System Status")
                    dpg.add_separator()
                    dpg.add_text("FPS: 0.0", tag="fps_display")
                    dpg.add_text("Gesture: None", tag="gesture_display")
                    dpg.add_text("Mode: Passive", tag="mode_display")
                    dpg.add_separator()
                    dpg.add_text("Tasks")
                    dpg.add_text("0 active", tag="tasks_display")

        dpg.set_primary_window("main_window", True)

        # Frame counter for FPS
        frame_count = [0]
        last_fps_time = [time.time()]

        def on_frame(sender, app_data):
            nonlocal frame_count, last_fps_time

            # Grab frame from camera
            if camera:
                frame = camera.get_frame()
                if frame is not None:
                    # Update texture
                    try:
                        rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
                        resized = cv2.resize(rgba, (640, 480))
                        texture_data = (resized.astype(np.float32) / 255.0).flatten().tolist()
                        if dpg.does_item_exist("camera_texture"):
                            dpg.set_value("camera_texture", texture_data)
                    except Exception as e:
                        logger.error(f"Texture error: {e}")

                    # Run perception
                    try:
                        result = perception.process(frame)
                        if result.detections:
                            labels = [d.get("label", "?") for d in result.detections[:5]]
                            obj_text = ", ".join(labels)
                            if dpg.does_item_exist("objects_text"):
                                dpg.set_value("objects_text", obj_text)
                    except Exception as e:
                        logger.error(f"Perception error: {e}")

                    # Update FPS
                    frame_count[0] += 1
                    now = time.time()
                    if now - last_fps_time[0] >= 1.0:
                        fps = frame_count[0] / (now - last_fps_time[0])
                        frame_count[0] = 0
                        last_fps_time[0] = now
                        if dpg.does_item_exist("fps_display"):
                            dpg.set_value("fps_display", f"FPS: {fps:.1f}")

        dpg.setup_dearpygui()
        dpg.show_viewport()
        logger.info("Dashboard ready. Window should be visible.")

        while dpg.is_dearpygui_running():
            on_frame(None, None)
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

    # 6. OpenCV fallback if DearPyGui failed
    if not use_dpg:
        logger.info("Using OpenCV window. Press 'q' to exit.")
        try:
            while True:
                frame = camera.get_frame() if camera else None
                if frame is None:
                    time.sleep(0.01)
                    continue

                display = frame.copy()
                result = perception.process(frame)

                for det in result.detections:
                    x1, y1, x2, y2 = det.get("box", (0, 0, 0, 0))
                    label = det.get("label", "?")
                    conf = det.get("confidence", 0)
                    cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(display, f"{label} {conf:.2f}", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                if result.hand_results:
                    for hand in result.hand_results.hands:
                        for lm in hand.landmarks:
                            x = int(lm.x * display.shape[1])
                            y = int(lm.y * display.shape[0])
                            cv2.circle(display, (x, y), 3, (0, 0, 255), -1)

                cv2.putText(display, "Aether Spatial Assistant", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.putText(display, "Press 'q' to exit", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

                cv2.imshow("Aether", display)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        except KeyboardInterrupt:
            pass
        finally:
            cv2.destroyAllWindows()

    # 7. Cleanup
    if camera:
        camera.stop()
    app.plugin_manager.shutdown_all()
    app.shutdown()
    logger.info("Aether shutdown complete")


if __name__ == "__main__":
    main()
