# Aether Tutorial

## This guide explains how to set up and run the Aether spatial maintenance assistant project.
o Run the App
python main.py
The app will:

-Start camera thread (30 FPS)
-Load YOLO plugin (object detection)
-Load MediaPipe hand plugin (21 landmarks)
-Process frames through perception pipeline
-Emit events to Event Bus
-Recognize gestures from hand landmarks
-Handle command confirmation flow
-The camera window will show detected objects and hand landmarks. Press q or Ctrl+C to exit.
## 1. Prerequisites

Make sure you have:
- Python 3.10 or newer
- A camera connected to your computer (or a webcam)
- Internet access for installing dependencies

## 2. Create a Virtual Environment

On Windows PowerShell:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On Git Bash:
```bash
python -m venv .venv
source .venv/Scripts/activate
```

## 3. Install Dependencies

Run:
```bash
pip install ultralytics opencv-python numpy pyyaml
```

## 4. Run the Tests

Verify everything is working:
```bash
python tests/test_aether.py
```

## 5. Start the Application

Run:
```bash
python main.py
```

A window will open showing the live spatial HUD.

## 6. Exit the App

Press the q key while the window is focused to quit.

## 7. Configuration

You can adjust camera settings and model behavior in:
- config/default.yaml

Common settings include:
- camera device index
- frame width and height
- detection confidence threshold
- logging options

## 8. Troubleshooting

If you get an import error such as `ModuleNotFoundError: No module named 'cv2'`, install the dependencies again inside the activated virtual environment.

If the camera does not open, try changing the device index in the configuration file.
