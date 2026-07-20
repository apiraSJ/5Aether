# Aether — AI Spatial Assistant

> Build the brain before giving it better eyes.

Aether is a modular, event-driven AI Spatial Assistant for desktop today, architected for XR Smart Glasses tomorrow. It combines computer vision (MediaPipe GestureRecognizer + YOLOv8), spatial awareness (solvePnP), memory, task management, and a command system into a single extensible platform.

## Quick Start

```bash
# Vision pipeline (camera + YOLO + gestures + dashboard)
python main.py

# Brain-only mode (memory, commands, context, PySide6 overlay)
python brain_main.py

# Universal launcher
python main_brain.py --mode ui
```

## Architecture

```text
Camera ─→ FrameBroker ─→ HandPerceptionPlugin (GestureRecognizer)
                      ─→ ObjectSpatialPlugin   (YOLOv8 + solvePnP)
                              │
                              ▼
                         EventBus (69 event types)
                     ┌───────┼───────┬───────┐
                     │       │       │       │
                   Memory  Tasks  Commands  UI
```

Two independent entry points serve different use cases:

| Entry | UI | Purpose |
|-------|----|---------|
| `main.py` | DearPyGui + OpenCV | Camera → gestures → HUD → popups |
| `brain_main.py` | PySide6 overlay | Hotkeys → commands → memory (no camera) |

## Key Features

- **MediaPipe GestureRecognizer** — 8 native gestures (Closed_Fist, Open_Palm, Pointing_Up, Thumb_Up/Down, Victory, ILoveYou) with real-time classification
- **YOLOv8 Object Detection** — 80-class detection with distance estimation via solvePnP
- **Event Bus** — 69 event types, thread-safe pub/sub, global singleton
- **Command System** — remember, find, forget, list, status, task commands
- **Object & Task Memory** — JSON-persistent storage with CRUD and search
- **Plugin Architecture** — extendable via `Plugin` ABC with lifecycle hooks
- **Task Manager** — PENDING→RUNNING→COMPLETED/CANCELLED lifecycle
- **Context Awareness** — auto-detects active window (editor, terminal, presentation)
- **Command Popups** — tkinter dialogs triggered by gesture commands
- **Dual UI** — DearPyGui (GPU-accelerated dashboard) + PySide6 (floating overlay)
- **84 tests passing** across 9 test suites

## Project Structure

```text
core/          App lifecycle, EventBus, FrameBroker, Settings, Plugin/Module systems
perception/    Daemon threads: HandPerceptionPlugin, ObjectSpatialPlugin
vision/        Computer vision: hand tracker, gesture engine, spatial/PnP, calibration
ui/            DearPyGui dashboard, hand overlay, camera view, sidebar, status bar
interface/     PySide6 floating overlay and help reference
command/       Event-driven CommandHandler + CommandRegistry (brain path)
commands/      Direct-execution command implementations (remember, find, etc.)
memory/        SpatialObject, Task, EventRecord models with ObjectMemory cache
database/      JSON file storage: JsonStorage, ObjectStore, TaskStore, EventStore
plugins/       Plugin ABC implementations: YoloPlugin, HandPlugin
tasks/         TaskManager with status lifecycle
context/       Active window detection, CPU/memory monitoring
models/        MediaPipe gesture_recognizer.task, YOLOv8 weights
```

## Documentation

| File | Contents |
|------|----------|
| `TUTORIALS.md` | Installation, configuration, running |
| `docs/ARCHITECTURE.md` | Complete system architecture reference |
| `docs/ROADMAP.md` | Future development plan |
| `docs/PLUGINS.md` | Plugin development guide |
| `docs/COMMANDS.md` | Command framework reference |
| `docs/MEMORY.md` | Memory system reference |
| `docs/EVENTS.md` | EventBus event type reference |
| `docs/API.md` | Public API reference |
| `docs/CONTRIBUTING.md` | Contribution guide |

## Requirements

- Python 3.12+
- Windows (primary target)
- Webcam (for vision pipeline)
- ~2GB RAM for YOLO + MediaPipe

> **Philosophy**: Sensors are just input plugins — the intelligence layer is the core.
