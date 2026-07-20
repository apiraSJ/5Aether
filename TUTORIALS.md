# Aether Tutorials

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
# 84 passed across 9 test suites
```

## Configuration

All settings in `config/desktop.yaml`:

```yaml
camera:
  device_index: 0        # Camera device ID
  width: 640
  height: 480

model:
  weights: "yolov8n.pt"  # YOLO weights
  confidence: 0.25       # Detection threshold

hand_tracking:
  model_path: "models/gesture_recognizer.task"  # MediaPipe model
  num_hands: 2

perception:
  fps_target: 15          # ML pipeline throttle
```

## Running

### Vision Pipeline (Camera Required)

```bash
python main.py
```

Starts:
1. Camera capture (640×480 @ 30 FPS)
2. MediaPipe GestureRecognizer (8 native gestures)
3. YOLOv8 object detection with solvePnP distance
4. DearPyGui dashboard with camera feed + HUD
5. Tkinter popup on gesture commands

**Controls**: Press `q` in the OpenCV fallback window to quit.

### Brain-Only Mode (No Camera)

```bash
python brain_main.py
```

Starts:
1. PySide6 floating overlay (frameless, translucent)
2. Global hotkey listener
3. Command system (remember/find/forget/list/status/task)
4. Context detection (active window, CPU, memory)

**Hotkeys**:

| Hotkey | Action |
|--------|--------|
| CTRL+SPACE | Open/close overlay |
| ESC | Close overlay |
| CTRL+1 | System panel |
| CTRL+2 | Developer panel |
| CTRL+3 | Settings panel |
| CTRL+TAB | Developer mode |

### Universal Launcher

```bash
python main_brain.py --mode ui       # PySide6 overlay
python main_brain.py --mode cli      # Interactive CLI
python main_brain.py --mode headless # Background service
```

## Gesture Reference

| Gesture | Command | Description |
|---------|---------|-------------|
| Closed_Fist | Cancel / Close | Cancel action, close UI |
| Open_Palm | Toggle UI | Show/hide dashboard |
| Pointing_Up | Move Cursor | Control cursor position |
| Thumb_Up | Confirm / Accept | Confirm action |
| Thumb_Down | Reject / Deny | Reject action |
| Victory | Copy / Select | Copy or select |
| ILoveYou | Show Help | Display help overlay |

Gestures are classified by MediaPipe's GestureRecognizer model (`models/gesture_recognizer.task`). A tkinter popup appears on each recognized gesture with a 1.5s cooldown.

## Running Tests

```bash
pytest -v                    # All 84 tests
pytest tests/test_gesture_actions.py -v   # Gesture system only
pytest tests/test_event_bus.py -v         # EventBus only
```

## Troubleshooting

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| "No camera found" | Wrong device index | Set `camera.device_index` in config to 1 or 2 |
| "Feedback manager requires..." | MediaPipe warning | Safe to ignore — cosmetic |
| "landmark_projection_calculator" | Non-square ROI | Safe to ignore — cosmetic |
| DPG fails to open | GPU/driver issue | Falls back to OpenCV automatically |
| YOLO is slow | CPU-only inference | Reduce `perception.fps_target` in config |
| Popup doesn't appear | Gesture cooldown active | Wait 1.5s or trigger different gesture |
