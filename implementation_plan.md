# Aether Vision Assistant Implementation Plan

## Goal Description
Create a full desktop Python program that captures live camera frames, runs YOLOv8 object detection, estimates 3D pose using solvePnP, calculates distances, and renders a HUD overlay. The program should be modular, configurable via YAML, and include logging, performance monitoring, and error handling. All source files should reside under the `Aether/` directory as specified, and the code should be ready to run on Windows.

## User Review Required
[!IMPORTANT]
The plan includes several configurable parameters that need user confirmation:
- Camera device index (default 0). If you have multiple cameras, specify the correct index.
- Path to the YOLOv8 model weights (default `models/yolov8n.pt`). Ensure the model file exists or specify an alternative.
- Desired output resolution (default 640x480).
- Whether to enable optional performance profiling.

## Open Questions
[!QUESTION]
- Which YOLO model variant do you prefer (nano, small, medium, large)?
- Do you want the HUD to display additional telemetry (FPS, latency)?
- Should the program log to console only, or also write to rotating log files in `logs/`?
- Any specific objects to focus detection on (e.g., `person, chair`)?

## Proposed Changes
---
### Root Files
#### [NEW] [main.py](file:///d:/3CS/5Aether/main.py)
Entry point that parses command‑line arguments, loads configuration, initializes core components, and runs the main loop.

#### [NEW] [config.py](file:///d:/3CS/5Aether/config.py)
Utility to load YAML configuration, expose defaults, and allow runtime overrides via command‑line.

---
### core package
#### [NEW] [core/camera.py](file:///d:/3CS/5Aether/core/camera.py)
Wrapper around OpenCV `VideoCapture` handling frame retrieval, device selection, and graceful shutdown.

#### [NEW] [core/detector.py](file:///d:/3CS/5Aether/core/detector.py)
Loads YOLOv8 model (Ultralytics), runs inference on frames, and returns bounding boxes, class IDs, and confidence scores.

#### [NEW] [core/renderer.py](file:///d:/3CS/5Aether/core/renderer.py)
Uses OpenCV drawing functions to overlay bounding boxes, pose axes, distance text, and optional telemetry on the frame.

#### [NEW] [core/telemetry.py](file:///d:/3CS/5Aether/core/telemetry.py)
Collects per‑frame performance metrics (FPS, inference time) and exposes them to the renderer.

#### [NEW] [core/logger.py](file:///d:/3CS/5Aether/core/logger.py)
Configures Python `logging` with console and rotating file handlers under `logs/`.

#### [NEW] [core/performance.py](file:///d:/3CS/5Aether/core/performance.py)
Simple timing utilities (context manager) used by other modules.

---
### vision package
#### [NEW] [vision/pnp.py](file:///d:/3CS/5Aether/vision/pnp.py)
Implements `solvePnP` based pose estimation given 2D‑3D correspondences derived from detection bounding boxes.

#### [NEW] [vision/tracking.py](file:///d:/3CS/5Aether/vision/tracking.py)
Placeholder for future object tracking; currently provides a thin wrapper for detection results.

#### [NEW] [vision/calibration.py](file:///d:/3CS/5Aether/vision/calibration.py)
Loads/creates camera intrinsic matrix and distortion coefficients from a YAML file.

#### [NEW] [vision/geometry.py](file:///d:/3CS/5Aether/vision/geometry.py)
Utility functions for distance calculation, coordinate transformations, and drawing 3‑D axes.

---
### assets, models, config, logs, tests, docs
Create empty directories to satisfy the layout. Add a sample `config/default.yaml` with keys for camera, model, resolution, and HUD options.

## Verification Plan
- Run `python -m venv venv && venv\Scripts\activate && pip install ultralytics opencv-python-headless numpy pyyaml`.
- Execute `python main.py --config config/default.yaml`.
- Verify that a window opens showing live video with YOLO boxes and pose axes.
- Check `logs/aether.log` for start‑up and error entries.
- Confirm FPS stays above 15 FPS on a typical webcam.

**Note**: All files will be created under `d:/3CS/5Aether/` which maps to the workspace `apiraSJ/5Aether`.
