# Aether — Spatial Maintenance Assistant (Phase 1)

AI-powered Spatial Maintenance Assistant core desktop runtime. This is the foundation software stack running a localized computer vision pipeline.

## Features

- **Live Camera Capture**: Robust wrapper around OpenCV VideoCapture.
- **YOLOv8 Object Detection**: High-performance real-time object localization using Ultralytics YOLOv8.
- **3D Pose Estimation**: Real-time perspective-n-point (PnP) solver mapping 2D object bounding boxes to 3D spatial coordinate spaces.
- **Spatial Calculations**: Euclidean distance tracking of detected components.
- **Contextual HUD**: Real-time overlays displaying tracking IDs, bounding boxes, 3D axes, and performance telemetry (FPS, inference & solver latencies).
- **Modular Software Design**: Decoupled core and vision packages allowing easy overrides of individual modules.

---

## Directory Structure

```text
Aether/
├── main.py                   # Runtime pipeline executor
├── config.py                 # Configuration loader and parser
├── core/
│   ├── camera.py             # OpenCV camera interface wrapper
│   ├── detector.py           # YOLOv8 object detection wrapper
│   ├── renderer.py           # HUD drawing and overlay renderer
│   ├── telemetry.py          # Metric tracking (FPS, latency, etc.)
│   ├── logger.py             # Python logger configuration setup
│   └── performance.py        # Performance timing utilities
├── vision/
│   ├── pnp.py                # 3D pose estimator using solvePnP
│   ├── tracking.py           # Dummy/baseline object tracker
│   ├── calibration.py        # Camera matrix and lens distortion loader
│   └── geometry.py           # 3D projections and distance geometry
├── config/
│   └── default.yaml          # Pipeline settings, camera, and model weights
├── logs/                     # Log output directory
├── tests/
│   └── test_aether.py        # Automated unit verification tests
└── docs/                     # Additional documentation
```

---

## Setup Instructions

### 1. Create Virtual Environment
Ensure you have Python 3.12 installed on your system. Run:
```bash
python -m venv venv
venv\Scripts\activate
```

### 2. Install Dependencies
```bash
pip install ultralytics opencv-python numpy pyyaml
```

### 3. Run Verification Tests
```bash
python tests/test_aether.py
```

### 4. Launch the Program
To run the main spatial HUD pipeline:
```bash
python main.py
```

Press `q` on the window to exit cleanly.

---

## Configuration and Custom Overrides
All components are driven by the configuration parameters in `config/default.yaml`. To modify parameters (e.g., target camera index, model size, confidence threshold, or HUD display settings), edit `config/default.yaml` directly.
