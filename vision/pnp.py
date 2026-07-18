import cv2
import numpy as np

def estimate_pose(box, camera_matrix, dist_coeffs, physical_width=21.0, physical_height=29.7):
    """Estimates 3D translation (tvec) and rotation (rvec) vectors of an object.
    
    Parameters
    ----------
    box : tuple or list
        Bounding box as (x1, y1, x2, y2).
    camera_matrix : ndarray
        Camera intrinsic matrix.
    dist_coeffs : ndarray
        Camera distortion coefficients.
    physical_width : float
        Known physical width of the object in world units (e.g. cm).
    physical_height : float
        Known physical height of the object in world units (e.g. cm).
    """
    x1, y1, x2, y2 = box
    
    # 3D model points in the object coordinate space (assuming flat rectangular object)
    object_points = np.array([
        [0.0, 0.0, 0.0],
        [physical_width, 0.0, 0.0],
        [physical_width, physical_height, 0.0],
        [0.0, physical_height, 0.0]
    ], dtype=np.float32)
    
    # Matching 2D image points from the bounding box corners
    image_points = np.array([
        [x1, y1], # Top-Left
        [x2, y1], # Top-Right
        [x2, y2], # Bottom-Right
        [x1, y2]  # Bottom-Left
    ], dtype=np.float32)
    
    success, rvec, tvec = cv2.solvePnP(
        object_points,
        image_points,
        camera_matrix,
        dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE
    )
    
    if success:
        return rvec, tvec
    return None, None
