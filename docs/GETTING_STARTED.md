# Getting Started with Aether

## Installation

### Prerequisites

- Python 3.12+
- Windows 10/11
- Webcam (for vision pipeline)

### Setup

```bash
git clone <repo-url> Aether
cd Aether

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
```

### Verify Installation

```bash
python -m pytest tests/ -v
```

---

## Configuration

All settings in `config/desktop.yaml`:

```yaml
camera:
  device_index: 0        # Camera device ID
  width: 640
  height: 480
  fps_target: 30

model:
  weights: "yolov8n.pt"  # YOLO weights
  confidence: 0.25       # Detection threshold

hand_tracking:
  model_path: "models/gesture_recognizer.task"  # MediaPipe model
  num_hands: 2

perception:
  fps_target: 15          # ML pipeline throttle

spatial:
  object_width_cm: 21.0   # A4 paper width
  object_height_cm: 29.7  # A4 paper height
  focal_length: 640

cursor:
  smoothing: 0.15
  dead_zone: 1
  sensitivity: 2.0
  prediction: 0.12
```

---

## Running

### Vision Pipeline (Camera Required)

```bash
python main.py
```

Starts:
1. Camera capture (640×480 @ 30 FPS)
2. MediaPipe GestureRecognizer (8 native gestures)
3. YOLOv8 object detection with solvePnP distance
4. DearPyGui dashboard with camera feed + HUD overlay
5. Cursor overlay with holographic reticle

**Controls**: Press `q` in the OpenCV fallback window to quit.

### Brain-Only Mode (No Camera)

```bash
python brain_main.py
```

Starts:
1. PySide6 floating overlay (frameless, translucent, always-on-top)
2. Global hotkey listener (pynput)
3. Command system (open_ui, close_ui, switch_panel, set_mode, get_status)
4. Context detection (active window, CPU, memory)
5. Gesture-driven HomeMenu

---

## Gesture Reference

| Gesture | Action | Description |
|---------|--------|-------------|
| `Open_Palm` | Toggle UI | Show/hide home menu |
| `Closed_Fist` | Cancel/Close | Cancel action, close UI |
| `Pointing_Up` | Move Cursor | Control cursor via index fingertip |
| `Thumb_Up` | Confirm | Confirm pending action |
| `Thumb_Down` | Reject | Reject pending action |
| `Victory` | Developer Panel | Open developer tools |
| `ILoveYou` | Settings Panel | Open settings |
| `Pinch` (thumb+index) | Click | Select menu item or widget |

Gestures are classified by MediaPipe's GestureRecognizer model (`models/gesture_recognizer.task`).

---

## Keyboard Hotkeys (brain_main.py)

| Hotkey | Action |
|--------|--------|
| `Ctrl+Space` | Open/close UI overlay |
| `Escape` | Close UI |
| `Ctrl+1` | System panel |
| `Ctrl+2` | Developer panel |
| `Ctrl+3` | Settings panel |
| `Tab` | Developer mode |
| `M` | Normal mode |
| `P` | Presentation mode |

---

## Running Tests

```bash
pytest -v                                        # All tests
pytest tests/test_gesture_actions.py -v           # Gesture system
pytest tests/test_event_bus.py -v                 # EventBus
pytest tests/test_spatial.py -v                   # Spatial/PnP
pytest tests/test_database.py -v                  # Database storage
pytest tests/test_memory.py -v                    # Memory system
pytest tests/test_tasks.py -v                     # Task manager
pytest tests/test_perception_worker.py -v         # Perception worker
pytest tests/test_interaction.py -v               # Interaction system
```

---

## Troubleshooting

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| "No camera found" | Wrong device index | Set `camera.device_index` in config to 1 or 2 |
| "Feedback manager requires..." | MediaPipe warning | Safe to ignore — cosmetic |
| "landmark_projection_calculator" | Non-square ROI | Safe to ignore — cosmetic |
| DPG fails to open | GPU/driver issue | Falls back to OpenCV automatically |
| YOLO is slow | CPU-only inference | Reduce `perception.fps_target` in config |
| Cursor jumpy | Smoothing too low | Increase `cursor.smoothing` in config |
| Menu not appearing | Gesture cooldown | Wait 1.5s or use different gesture |
| Hotkeys not working | pynput permission | Run as administrator if needed |
