# Aether AI Assistant Development — Historical Baseline (2026-09-21)

> **This document is a historical snapshot** recorded before the Mark-1 Schedule Engine
> development began. It documents the state of the repository at commit `dfd5d36`
> (Sep 21, 2026) for reference. The current baseline is in `AI_ASSISTANT_BASELINE_CURRENT.md`.

## Baseline Metrics (Historical)

- **State Statement**: 691 tests passing before AI Assistant development.
- **Pytest Command**: `.venv\Scripts\python -m pytest`
- **Python Version**: `Python 3.12.9`
- **Pytest Version**: `9.1.1`
- **Test Count**: `691`
- **Passing Count**: `691`
- **Failing Count**: `0`
- **Execution Time**: `25.19 seconds`

---

## Current Status at Snapshot (Historical)

- **Test Count**: `921`
- **Passing Count**: `921`
- **Failing Count**: `0`
- **Latest Commit**: `dfd5d36` feat: add UI-1 shell show/hide API

### Commit History at Snapshot

```
dfd5d36 feat: add UI-1 shell show/hide API       (921 tests)
d73b82a feat: add background startup mode          (909 tests)
1f606d7 feat: add UIShell UI foundation            (909 tests)
f363b5c feat: Phase 3.3 Intent Reasoning
3ad8595 feat: Phase 3.2 Memory Retriever
```

---

## Git State at Snapshot

- **Current Branch**: `main`
- **Current Commit**: `dfd5d3600db0019dc04f0d8b3ed8e75922fd8a60`
- **Commit Date**: `Mon Sep 21 11:12:56 2026 +0700`
- **Commit Message**: `feat: add UI-1 shell show/hide API`
- **Working Tree Status**:
  - **Modified Files**: 21 (pre-existing work for future phases)
  - **Untracked Files**: 60+ (new features in progress)

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

---

## Notes

This baseline captures the state **before** Mark-1 Schedule Engine development (Phases 1-3)
and **before** the two-track Mark-1 plan (Track A = Schedule Engine, Track B = Web).
The current repository state has diverged significantly:

- Mark-1 Track A (Schedule Engine) Phases 1-3 + R1/R6 complete
- Test count: 1,349 (was 921)
- New components: `aether/task/`, `aether/plugins/task_plugin.py`, `config/task.yaml`
- Mark-1 Track B (Web) planned but not started
- Phase 4 Temporal Extraction spec exists as Draft (`docs/PHASE4_SPEC.md`)

See `AI_ASSISTANT_BASELINE_CURRENT.md` for the current baseline.