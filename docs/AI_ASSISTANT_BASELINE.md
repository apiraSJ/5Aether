# Aether AI Assistant Development Golden Baseline

This document records the baseline state of the Aether repository before beginning the AI Assistant Core integration.

## Baseline Metrics
- **State Statement**: 691 tests passing before AI Assistant development.
- **Pytest Command**: `.venv\Scripts\python -m pytest`
- **Python Version**: `Python 3.12.9`
- **Pytest Version**: `9.1.1`
- **Test Count**: `691`
- **Passing Count**: `691`
- **Failing Count**: `0`
- **Execution Time**: `25.19 seconds`

---

## Git State
- **Current Branch**: `main`
- **Current Commit**: `ad1b480906ec025b04034dcc8e1cd3ad29102639`
- **Commit Date**: `Mon Jul 27 03:38:20 2026 +0700`
- **Commit Message**: `docs: update README, ARCHITECTURE, ROADMAP for Backend v1.0.0`
- **Working Tree Status**:
  - **Modified Files**:
    - `README.md`
    - `aether/__main__.py`
    - `aether/core/adaptive_scheduler.py`
    - `aether/core/application.py`
    - `aether/core/event_bus_v2.py`
    - `aether/core/event_type.py`
    - `aether/core/plugin.py`
    - `aether/core/profiler.py`
    - `aether/memory/__init__.py`
    - `aether/phase_d/camera_plugin.py`
    - `aether/plugins/gui_plugin.py`
    - `aether/plugins/memory_plugin.py`
    - `aether/plugins/system_commands_plugin.py`
    - `aether/ui/camera_widget.py`
    - `aether/ui/hud_manager.py`
    - `aether/ui/overlay_model.py`
    - `aether/ui/overlay_widget.py`
    - `aether/ui/performance_hud.py`
    - `aether/vision/plugins.py`
    - `config/default.yaml`
    - `config/vision.yaml`
    - `tests/phase_a/test_boot.py`
    - `tests/test_virtual_cursor.py`

---

## Frozen Vision / Computer Vision Boundaries
The following Computer Vision components, entry points, and pipelines are frozen:

1. **Camera Interface**:
   - `aether/phase_d/camera_plugin.py`
   - `aether/core/frame_broker.py`
2. **YOLO Bounding Box / Spatial Detections**:
   - `aether/phase_d/object_plugin.py`
3. **MediaPipe Hand Landmarking / Gesture Processing**:
   - `aether/phase_d/hand_plugin.py`
   - `aether/plugins/gesture_plugin.py`
4. **Virtual Cursor Input Adapter**:
   - `aether/phase_d/cursor_plugin.py`
   - `aether/core/virtual_cursor.py`
5. **Perception and Event Adapters**:
   - `aether/vision/` (all files: `plugins.py`, `event_adapter.py`, `state_builder.py`, `tracker.py`, `vision_state.py`)
