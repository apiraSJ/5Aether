"""
MediaPipe Hand Landmark Definitions

21 knuckle keypoints per hand, detected by hand_landmarker.task.
Model trained on ~30K real-world images + rendered synthetic hands.

    8       12      16      20
    |       |       |       |
    7       11      15      19
    |       |       |       |
    6       10      14      18
    |       |       |       |
    5-------9-------13------17
           |
           |
    4------0------|
    |             |
    3             |
    |             |
    2             |
    |             |
    1
"""


class Landmark:
    WRIST = 0

    THUMB_CMC = 1
    THUMB_MCP = 2
    THUMB_IP = 3
    THUMB_TIP = 4

    INDEX_FINGER_MCP = 5
    INDEX_FINGER_PIP = 6
    INDEX_FINGER_DIP = 7
    INDEX_FINGER_TIP = 8

    MIDDLE_FINGER_MCP = 9
    MIDDLE_FINGER_PIP = 10
    MIDDLE_FINGER_DIP = 11
    MIDDLE_FINGER_TIP = 12

    RING_FINGER_MCP = 13
    RING_FINGER_PIP = 14
    RING_FINGER_DIP = 15
    RING_FINGER_TIP = 16

    PINKY_MCP = 17
    PINKY_PIP = 18
    PINKY_DIP = 19
    PINKY_TIP = 20


# Skeleton connections for overlay rendering
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),           # Thumb
    (0, 5), (5, 6), (6, 7), (7, 8),           # Index
    (5, 9), (9, 10), (10, 11), (11, 12),      # Middle
    (9, 13), (13, 14), (14, 15), (15, 16),    # Ring
    (13, 17), (17, 18), (18, 19), (19, 20),   # Pinky
    (0, 17),                                    # Palm base
]

# Finger tip and pip indices for extended-finger detection
FINGER_TIPS = [
    Landmark.THUMB_TIP,      # 4
    Landmark.INDEX_FINGER_TIP,   # 8
    Landmark.MIDDLE_FINGER_TIP,  # 12
    Landmark.RING_FINGER_TIP,    # 16
    Landmark.PINKY_TIP,          # 20
]

FINGER_PIPS = [
    Landmark.THUMB_IP,       # 3
    Landmark.INDEX_FINGER_PIP,   # 6
    Landmark.MIDDLE_FINGER_PIP,  # 10
    Landmark.RING_FINGER_PIP,    # 14
    Landmark.PINKY_PIP,          # 18
]

FINGER_MCPS = [
    Landmark.THUMB_MCP,      # 2
    Landmark.INDEX_FINGER_MCP,   # 5
    Landmark.MIDDLE_FINGER_MCP,  # 9
    Landmark.RING_FINGER_MCP,    # 13
    Landmark.PINKY_MCP,          # 17
]

# Per-finger label for overlay
FINGER_NAMES = ["Thumb", "Index", "Middle", "Ring", "Pinky"]
