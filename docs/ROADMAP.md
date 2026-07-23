# Aether Roadmap

> Development phases for building the spatial AI assistant.

---

## Legend

- **Complete** — implemented, tested, and working
- **In Progress** — actively being developed
- **Planned** — designed but not started
- **Researching** — evaluating approaches

---

## Phase 1: Foundation (Complete)

| Feature | Status | Notes |
|---------|--------|-------|
| Project structure | Complete | Modular layout with core/, vision/, perception/, interface/ |
| Virtual environment | Complete | Python 3.12 on Windows |
| Event Bus | Complete | 69 event types, thread-safe, history |
| YAML Config | Complete | Deep merge, get/set/save |
| Logging | Complete | Console + file |
| CI/testing | Complete | pytest with passing tests |

---

## Phase 2: Perception (Complete)

| Feature | Status | Notes |
|---------|--------|-------|
| Camera capture | Complete | Synchronous + threaded wrappers |
| YOLO object detection | Complete | YOLOv8 nano with configurable confidence |
| MediaPipe hand tracking | Complete | HandLandmarker + GestureRecognizer |
| Gesture recognition (native) | Complete | GestureRecognizer — 8 built-in gestures |
| Gesture recognition (fallback) | Complete | Rule-based finger-counting (5 gestures) |
| Gesture→Action mapping | Complete | Executor with cooldown |
| solvePnP distance estimation | Complete | Configurable object dimensions |
| Hand skeleton overlay | Complete | 21 landmarks + connections |
| Object bounding boxes | Complete | With distance labels |
| FrameBroker | Complete | Thread-safe producer-consumer |
| Background perception threads | Complete | Daemon threads for hand + object |

---

## Phase 3: Brain & Memory (Complete)

| Feature | Status | Notes |
|---------|--------|-------|
| ObjectMemory | Complete | In-memory cache + JSON persistence |
| JsonStorage | Complete | Atomic file writes |
| TaskManager | Complete | PENDING→RUNNING→COMPLETED lifecycle |
| Context detection | Complete | Active window via win32gui |
| PySide6 UI | Complete | Frameless floating overlay |
| Command system | Complete | Event-driven CommandHandler |
| Hotkey listener | Complete | pynput global hooks |
| Brain entry point | Complete | brain_main.py |

---

## Phase 4: Dashboard & UI (Complete)

| Feature | Status | Notes |
|---------|--------|-------|
| DearPyGui real-time camera | Complete | GPU-accelerated texture |
| Sidebar metrics | Complete | Objects, hands, gesture, command |
| Manual render loop | Complete | while-running pattern |
| OpenCV fallback | Complete | Automatic if DPG fails |
| Cursor tracking | Complete | Crosshair from index fingertip |
| CursorOverlay (PySide6) | Complete | Holographic reticle with glow |
| HomeMenu | Complete | Gesture-driven vertical chain menu |
| StatusBar | Complete | Name, HP bar, CPU%, time |

---

## Phase 5: Interaction System (Complete)

| Feature | Status | Notes |
|---------|--------|-------|
| InteractionManager | Complete | Central coordinator for cursor + menu + state |
| State Machine | Complete | IDLE→TRACKING→MENU_OPEN/PANEL_OPEN |
| Focus Manager | Complete | Widget hit-testing for cursor hover |
| Action Queue | Complete | Thread-safe bridge perception → UI |
| Gesture Router | Complete | Gesture→action routing with cooldown |
| Cursor Manager | Complete | Camera→screen mapping + smoothing + prediction |

---

## Phase 6: Intelligence (Planned)

| Feature | Status | Notes |
|---------|--------|-------|
| AI reasoning engine | Researching | LLM integration for spatial queries |
| Voice commands | Planned | Speech-to-text pipeline |
| Natural language interface | Planned | "Find the hammer I was holding" |
| Object relationship mapping | Planned | "Hammer is on the workbench" |
| Spatial scene graph | Planned | 3D scene understanding |
| Predictive attention | Planned | Anticipate user needs |

---

## Phase 7: Desktop Agent (Planned)

| Feature | Status | Notes |
|---------|--------|-------|
| Desktop automation | Planned | Open files, run commands, control apps |
| Screen OCR | Planned | Read UI text via OCR |
| GUI automation | Planned | Click buttons, fill forms |
| Workflow recording | Planned | Record + replay user actions |
| System monitoring | Planned | CPU, RAM, disk, network |

---

## Phase 8: XR Integration (Planned)

| Feature | Status | Notes |
|---------|--------|-------|
| Smart glasses support | Researching | Researching form factor |
| AR HUD overlay | Planned | Real-world annotation |
| Spatial anchors | Planned | Persistent world-locked content |
| Eye tracking | Planned | Gaze-based interaction |
| Hand tracking (native XR) | Planned | Direct hand input for AR |

---

## Testing Roadmap

| Area | Current | Goal |
|------|---------|------|
| Unit tests | Passing | 100+ |
| Gesture system | Passing | 40+ |
| EventBus | Passing | 10+ |
| Spatial/PnP | Passing | 10+ |
| Memory | Passing | 10+ |
| Integration tests | — | 20+ |
| End-to-end tests | — | 10+ |

---

## Known Gaps

- **tracking.py** — placeholder only (sequential IDs, no real tracking)
- **Fusion Engine** — no hand+object spatial fusion yet
- **Face/Pose models** — MediaPipe models available but not integrated
- **Depth estimation** — no stereo or depth camera support
- **AI reasoning** — no LLM integration yet
- **Desktop automation** — no GUI control beyond hotkeys
