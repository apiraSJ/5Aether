"""
HUD Renderer — Draws overlays on camera frames

Extracted from main.py. Handles:
- Hand skeleton drawing (21 landmarks, connections)
- Cursor drawing on camera frame
- Pinch line between index+thumb
- Object bounding boxes
- Status bar text
"""

import math
import logging
import numpy as np
import cv2


logger = logging.getLogger("Aether.HUDRenderer")

# ─── Config ──────────────────────────────────────────────────────
PINCH_THRESHOLD = 0.06

# ─── Hand landmark connections ───────────────────────────────────
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
]

TIP_INDICES = {4, 8, 12, 16, 20}


def draw_cursor_on_frame(frame, cx_norm, cy_norm, is_pinch, gesture, mirror=False):
    """Draw the virtual cursor on a camera frame."""
    h, w = frame.shape[:2]
    cx = int((1.0 - cx_norm) * w) if mirror else int(cx_norm * w)
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


def draw_pinch_line(frame, lm, is_pinch, mirror=False):
    """Draw a line between index tip and thumb tip when pinching."""
    if not is_pinch or not lm or len(lm) < 21:
        return
    h, w = frame.shape[:2]
    idx = lm[8]
    thumb = lm[4]
    p1 = (int((1.0 - idx["x"]) * w) if mirror else int(idx["x"] * w), int(idx["y"] * h))
    p2 = (int((1.0 - thumb["x"]) * w) if mirror else int(thumb["x"] * w), int(thumb["y"] * h))
    cv2.line(frame, p1, p2, (0, 0, 255), 2, cv2.LINE_AA)
    cv2.circle(frame, p1, 6, (0, 0, 255), -1, cv2.LINE_AA)
    cv2.circle(frame, p2, 6, (0, 0, 255), -1, cv2.LINE_AA)


def process_hud_overlays(frame, hands, objects, mirror=False):
    """Draw all HUD overlays on the camera frame. Returns the frame."""
    h, w = frame.shape[:2]

    # ── Object bounding boxes ────────────────────────────────────
    for obj in objects:
        x1, y1, x2, y2 = obj["box"]
        if mirror:
            x1, x2 = w - x2, w - x1
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
        lbl = f"{obj['name']} ({obj['conf']:.2f}) {obj.get('distance_z', 0):.1f}m"
        cv2.putText(frame, lbl, (x1, max(y1 - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

    # ── Hand skeletons ───────────────────────────────────────────
    for hand in hands:
        lm = hand.get("landmarks", [])
        if not lm or len(lm) < 21:
            continue

        if mirror:
            pts = np.array([[int((1.0 - l["x"]) * w), int(l["y"] * h)] for l in lm])
        else:
            pts = np.array([[int(l["x"] * w), int(l["y"] * h)] for l in lm])

        for a, b in HAND_CONNECTIONS:
            cv2.line(frame, tuple(pts[a]), tuple(pts[b]), (255, 180, 0), 1, cv2.LINE_AA)

        for i, pt in enumerate(pts):
            radius = 5 if i in TIP_INDICES else 3
            cv2.circle(frame, tuple(pt), radius, (0, 255, 0), -1, cv2.LINE_AA)

        idx = lm[8]
        thumb = lm[4]
        dx = idx["x"] - thumb["x"]
        dy = idx["y"] - thumb["y"]
        hand_pinch = math.sqrt(dx * dx + dy * dy) < PINCH_THRESHOLD
        draw_pinch_line(frame, lm, hand_pinch, mirror=mirror)

        cv2.putText(frame, hand.get("label", ""), tuple(pts[0]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)

    return frame


def draw_status_bar(frame, gesture, is_pinch, hand_count):
    """Draw status text at bottom of frame."""
    h, w = frame.shape[:2]

    gesture_text = gesture if gesture != "Unknown" else "None"
    cv2.putText(frame, f"Gesture: {gesture_text}", (10, h - 36),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)

    pinch_text = "CLICK" if is_pinch else "No"
    pinch_color = (0, 0, 255) if is_pinch else (200, 200, 200)
    cv2.putText(frame, f"Pinch: {pinch_text}", (10, h - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, pinch_color, 1, cv2.LINE_AA)

    cv2.putText(frame, f"Hands: {hand_count}", (w - 150, h - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
