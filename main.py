import cv2
import sys
import logging
from config import load_config
from core.logger import setup_logger
from core.camera import Camera
from core.detector import Detector
from core.renderer import Renderer
from core.telemetry import Telemetry
from core.performance import PerformanceTimer
from vision.calibration import Calibration
from vision.geometry import calculate_distance
from vision.pnp import estimate_pose
from vision.tracking import Tracker

def main():
    # Load configuration
    cfg = load_config()
    
    # Setup logging
    logger = setup_logger(cfg.get("logging", {}))
    logger.info("Initializing Aether desktop runtime...")
    
    try:
        # Load camera calibration
        camera_cfg = cfg.get("camera", {})
        width = camera_cfg.get("width", 640)
        height = camera_cfg.get("height", 480)
        calibration = Calibration(width=width, height=height)
        
        # Initialize components
        camera = Camera(camera_cfg)
        detector = Detector(cfg.get("model", {}))
        tracker = Tracker()
        telemetry = Telemetry()
        renderer = Renderer(cfg.get("hud", {}), calibration.camera_matrix, calibration.dist_coeffs)
        
        logger.info("Aether startup successful. Starting pipeline loop.")
        
        while True:
            # Update frame-to-frame FPS telemetry
            telemetry.update_fps()
            
            # 1. Capture frame
            ret, frame = camera.read()
            if not ret:
                logger.error("Failed to capture frame from camera source.")
                break
                
            # 2. YOLO object detection (timed)
            with PerformanceTimer("YOLO Detection") as t_det:
                detections = detector.detect(frame)
            telemetry.inference_time = t_det.elapsed
            
            # 3. Object tracking
            tracked = tracker.update(detections)
            
            # 4. Pose estimation & spatial calculations (timed)
            with PerformanceTimer("Pose Estimation") as t_pnp:
                for det in tracked:
                    box = det["box"]
                    # Perform perspective-n-point pose estimation
                    rvec, tvec = estimate_pose(box, calibration.camera_matrix, calibration.dist_coeffs)
                    det["rvec"] = rvec
                    det["tvec"] = tvec
                    det["distance"] = calculate_distance(tvec) if tvec is not None else 0.0
            telemetry.pnp_time = t_pnp.elapsed
            
            # 5. HUD Rendering
            hud_frame = renderer.render(frame, tracked, telemetry)
            
            # 6. Display
            cv2.imshow("Aether Spatial HUD", hud_frame)
            
            # Handle key events: exit on 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                logger.info("Exit command received. Shutting down Aether.")
                break
                
    except KeyboardInterrupt:
        logger.info("Interrupt received. Shutting down.")
    except Exception as e:
        logger.exception(f"Unhandled runtime exception in main pipeline: {e}")
        sys.exit(1)
    finally:
        # Cleanup
        if 'camera' in locals():
            try:
                camera.release()
            except Exception as ce:
                logger.error(f"Error releasing camera: {ce}")
        cv2.destroyAllWindows()
        logger.info("Aether cleanup completed. Clean exit.")

if __name__ == "__main__":
    main()
