import cv2
import numpy as np

def draw_3d_axes(img, camera_matrix, dist_coeffs, rvec, tvec, length=10.0):
    """Projects and draws 3D X (Red), Y (Green), Z (Blue) axes onto the image."""
    # Axes definition in 3D object coordinates: origin, X, Y, Z
    axis_pts = np.array([
        [0.0, 0.0, 0.0],
        [length, 0.0, 0.0],
        [0.0, length, 0.0],
        [0.0, 0.0, length]
    ], dtype=np.float32)
    
    # Project points to 2D image plane
    img_pts, _ = cv2.projectPoints(axis_pts, rvec, tvec, camera_matrix, dist_coeffs)
    img_pts = img_pts.squeeze().astype(int)
    
    # Ensure shape is correct (if only 1 detection, squeeze might result in 1D array)
    if img_pts.ndim == 1:
        img_pts = np.expand_dims(img_pts, axis=0)

    if len(img_pts) >= 4:
        origin = tuple(img_pts[0])
        x_axis = tuple(img_pts[1])
        y_axis = tuple(img_pts[2])
        z_axis = tuple(img_pts[3])
        
        cv2.line(img, origin, x_axis, (0, 0, 255), 3) # X - Red
        cv2.line(img, origin, y_axis, (0, 255, 0), 3) # Y - Green
        cv2.line(img, origin, z_axis, (255, 0, 0), 3) # Z - Blue
    return img

def calculate_distance(tvec):
    """Calculates translation distance from camera coordinate origin."""
    if tvec is None:
        return 0.0
    return float(np.linalg.norm(tvec))
