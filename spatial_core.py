import cv2
import numpy as np
from ultralytics import YOLO

def initialize_spatial_engine():
    # Load lightweight pre-trained model for testing camera loop
    model = YOLO("yolov8n.pt")
    
    # Open default laptop webcam
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # Define the 3D real-world coordinates of our physical asset (in centimeters)
    # Target: Standard Document/Component Panel (21.0cm x 29.7cm)
    object_points = np.array([
        [0.0, 0.0, 0.0],         # Top-Left corner
        [21.0, 0.0, 0.0],        # Top-Right corner
        [21.0, 29.7, 0.0],       # Bottom-Right corner
        [0.0, 29.7, 0.0]         # Bottom-Left corner
    ], dtype=np.float32)

    # Approximate Camera Intrinsic Matrix (Assuming standard 640x480 webcam)
    # Replace with precise calibration parameters later for actual thesis benchmarks
    focal_length = 640
    center_x, center_y = 320, 240
    camera_matrix = np.array([
        [focal_length, 0, center_x],
        [0, focal_length, center_y],
        [0, 0, 1]
    ], dtype=np.float32)
    
    dist_coeffs = np.zeros(4, dtype=np.float32) # Assume zero lens distortion initially

    print("[Aether Engine] Streaming started. Press 'q' on the window to exit.")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Step A: Run inference to extract bounding boxes
        results = model(frame, verbose=False)[0]
        
        # Draw base detections
        for box in results.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            label = results.names[int(box.cls[0])]
            conf = float(box.conf[0])
            
            # Simple UI overlay tracking targets
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"{label} {conf:.2f}", (x1, y1 - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # Step B: Simulate dynamic tracking corners from bounding box
            # For demonstration, map box boundaries to PnP input points
            image_points = np.array([
                [x1, y1], # Top-Left
                [x2, y1], # Top-Right
                [x2, y2], # Bottom-Right
                [x1, y2]  # Bottom-Left
            ], dtype=np.float32)

            # Step C: Compute 3D Spatial Position vector Matrix
            success, rvec, tvec = cv2.solvePnP(
                object_points, image_points, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE
            )

            if success:
                # Extract Z axis distance from camera lens (in centimeters)
                distance_z = tvec[2][0]
                
                # Render the calculated spatial vector overlay on the screen
                metrics_str = f"Spatial Dist Z: {distance_z:.1f} cm"
                cv2.putText(frame, metrics_str, (x1, y2 + 20), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

        # Output the structural frame matrix to screen
        cv2.imshow("Aether V1 - Spatial HUD Core", frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[Aether Engine] Stream terminated gracefully.")

if __name__ == "__main__":
    initialize_spatial_engine()