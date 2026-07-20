# Aether — AI Spatial Assistant

Modular AI Spatial Assistant for Desktop and XR Smart Glasses.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — Full system architecture reference
- [Tutorials](TUTORIALS.md) — Step-by-step setup and usage guide

## Features

- **Live Camera Capture**: Robust wrapper around OpenCV VideoCapture.
- **YOLOv8 Object Detection**: Real-time object localization using Ultralytics YOLOv8.
- **3D Pose Estimation**: PnP solver mapping 2D bounding boxes to 3D spatial coordinates.
- **Spatial Calculations**: Euclidean distance tracking of detected components.
- **Context HUD**: Real-time overlays with tracking IDs, bounding boxes, 3D axes, and telemetry.
- **Gaze-Direct UI**: Frame-of-reference-driven navigation using head positioning.
- **Modular Design**: Decoupled core and vision packages for easy extension.

## Directory Structure

```text
Aether/
├── main.py                                   # Runtime pipeline executor
├── core/                                     # Core runtime modules
│   ├── __init__.py
│   ├── app.py                                # Application lifecycle
│   ├── event_bus.py                           # Pub-sub event system
│   ├── frame_broker.py                        # Thread-safe frame storage
│   ├── camera_thread.py                       # Threaded camera capture
│   └── perception_worker.py                   # Background perception worker
├── perception/                                # Computer vision modules
│   ├── __init__.py
│   ├── __pycache__/                          # Compiled .pyc files
│   ├── hand_plugin.py                         # MediaPipe hand tracking
│   └── object_plugin.py                       # YOLO + PnP spatial estimation
├── vision/                                   # Vision utilities
│   ├── __init__.py
│   ├── hand_tracker.py                        # MediaPipe hand landmarker
│   ├── gesture_engine.py                       # Gesture classifier
│   ├── command_confirmation.py               # Point→preview→confirm flow
│   └── spatial.py                             # PnP distance solver
├── ui/                                       # UI modules
│   ├── __init__.py
│   ├── dashboard.py                           # DearPyGui UI
│   ├── hand_overlay.py                        # Hand landmark rendering
│   └── __pycache__/                          # Compiled .pyc files
├── memory/                                    # Persistence layers
│   ├── __init__.py
│   ├── models.py                              # Data structures
│   ├── object_memory.py                       # SpatialObject CRUD
│   ├── task_manager.py                        # Task lifecycle
├── tasks/                                    # Task system
│   └── manager.py                             # Task CRUD
├── commands/                                 # Command system
│   ├── __init__.py
│   ├── __pycache__/                          # Compiled .pyc files
│   ├── __pycache__/                          # Compiled .pyc files
│   ├── __pycache__/                          # Compiled .pyc files
│   ├── base.py                               # Command base class
│   ├── __pycache__/                          # Compiled .pyc files
│   ├── __pycache__/                          # Compiled .pyc files
│   ├── __pycache__/                          # Compiled .pyc files
│   ├── remember.py                            # Remember object
│   └── __pycache__/                          # Compiled .pyc files
├── database/                                 # JSON persistence
│   ├── __init__.py
│   ├── objects.py                            # ObjectStore
│   └── tasks.py                               # TaskStore
├── plugins/                                  # Plugin system
│   ├── __init__.py
│   ├── __pycache__/                          # Compiled .pyc files
│   ├── yolo_plugin.py                        # YOLO plugin
│   ├── hand_plugin.py                         # MediaPipe plugin
│   └── __pycache__/                          # Compiled .pyc files
├── config/                                    # Configuration
│   └── desktop.yaml                           # Desktop profile
├── models/                                   # Model weights
│   └── hand_landmarker.task                  # MediaPipe HandLandmarker
├── tests/                                    # Unit tests
├── logs/                                     # Log output
├── assets/                                   # Static assets
└── docs/                                     # Documentation
```

## Setup

### 1. Create Virtual Environment

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run Verification Tests

```bash
python -m pytest tests/ -v
```

### 4. Launch

```bash
python main.py
```

Press `q` or CTRL-C to exit.

## Configuration

Edit `config/desktop.yaml` to modify:
- Camera settings (resolution, FPS)
- Model weights path
- Perception worker config (YOLO + MediaPipe settings)
- Spatial estimator intrinsics/object size
- HUD parameters (overlay style, theme)

## Running

### Desktop

```bash
python main.py
```

Opens a 1024x600 DearPyGui window showing the camera feed with:
- YOLO object detections
- 3D spatial distance overlays
- Hand landmarks (if detected)
- Gaze-driven navigation (via IMU simulator)

### OpenCV Fallback

If DearPyGui fails, a second OpenCV window opens showing the same overlays.

Press 'q' to exit.

### Modes

- **Normal Mode**: See live sensor feed with all overlays
- **Developer Mode**: Focus on tools/data for advanced use
