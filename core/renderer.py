import cv2
import numpy as np
from vision.geometry import draw_3d_axes

class Renderer:
    """Renders 2D detection boxes, 3D pose axes, distances, and telemetry HUD on image frames."""
    def __init__(self, hud_config: dict, camera_matrix: np.ndarray, dist_coeffs: np.ndarray):
        self.show_fps = hud_config.get("show_fps", True)
        self.show_telemetry = hud_config.get("show_telemetry", True)
        self.camera_matrix = camera_matrix
        self.dist_coeffs = dist_coeffs

    def render(self, frame, detections, telemetry):
        """Draws visual HUD overlays on the frame using precalculated telemetry and poses."""
        out_frame = frame.copy()
        
        # Iterate over detections to draw 2D/3D visual elements
        for det in detections:
            box = det["box"]
            x1, y1, x2, y2 = box
            label = det["label"]
            conf = det["confidence"]
            track_id = det.get("track_id", 0)
            
            # Draw standard 2D Bounding Box (Green)
            cv2.rectangle(out_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(out_frame, f"[{track_id}] {label} {conf:.2f}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            # Retrieve precalculated pose
            rvec = det.get("rvec")
            tvec = det.get("tvec")
            dist = det.get("distance", 0.0)
            
            if tvec is not None and rvec is not None:
                # Draw 3D axis at the object's origin
                out_frame = draw_3d_axes(out_frame, self.camera_matrix, self.dist_coeffs, rvec, tvec, length=15.0)
                
                # Draw distance labels below the bounding box
                dist_str = f"Z-Dist: {dist:.1f} cm"
                cv2.putText(out_frame, dist_str, (x1, y2 + 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
        
        # Overlay overall FPS
        if self.show_fps:
            fps_text = f"FPS: {telemetry.fps:.1f}"
            cv2.putText(out_frame, fps_text, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                        
        # Overlay system latencies (inference & PnP solver execution times)
        if self.show_telemetry:
            inf_ms = telemetry.inference_time * 1000.0
            pnp_ms = telemetry.pnp_time * 1000.0
            telemetry_text = f"INF: {inf_ms:.1f}ms | PNP: {pnp_ms:.1f}ms"
            cv2.putText(out_frame, telemetry_text, (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                        
        return out_frame
