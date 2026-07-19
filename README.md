# Aether — AI Spatial Assistant

Modular AI Spatial Assistant for Desktop and XR Smart Glasses.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — Full system architecture reference

## Features

- **Live Camera Capture**: Robust wrapper around OpenCV VideoCapture.
- **YOLOv8 Object Detection**: Real-time object localization using Ultralytics YOLOv8.
- **3D Pose Estimation**: PnP solver mapping 2D bounding boxes to 3D spatial coordinates.
- **Spatial Calculations**: Euclidean distance tracking of detected components.
- **Contextual HUD**: Real-time overlays with tracking IDs, bounding boxes, 3D axes, and telemetry.
- **Modular Design**: Decoupled core and vision packages for easy extension.

## Directory Structure

```text
Aether/
├── main.py                   # Runtime pipeline executor
├── config.py                 # Configuration loader
├── requirements.txt          # Dependencies
├── core/                     # Core runtime modules
├── vision/                   # Computer vision modules
├── memory/                   # Object memory system
├── tasks/                    # Task management
├── commands/                 # Command system
├── database/                 # JSON persistence
├── plugins/                  # Perception plugins
├── ui/                       # Dear PyGui dashboard
├── config/                   # Configuration files
├── models/                   # Model weights
├── tests/                    # Unit tests
├── logs/                     # Log output
├── assets/                   # Static assets
└── docs/                     # Documentation
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

Press `q` to exit.

## Configuration

Edit `config/default.yaml` to modify camera, model, logging, and HUD settings.
