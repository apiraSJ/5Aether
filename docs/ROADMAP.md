# Aether Roadmap

> Development phases for building the spatial AI assistant.

---

## Legend

- ✅ **Complete** — implemented, tested, and working
- 🚧 **In Progress** — actively being developed
- ⏳ **Planned** — designed but not started
- 📝 **Researching** — evaluating approaches

---

## Phase 1: Foundation ✅

| Feature | Status | Notes |
|---------|--------|-------|
| Project structure | ✅ | Modular layout with core/, vision/, ui/, etc. |
| Virtual environment | ✅ | Python 3.12 on Windows |
| Event Bus | ✅ | 69 event types, thread-safe, history |
| YAML Config | ✅ | Deep merge, get/set/save |
| Logging | ✅ | Console + file with rotation |
| CI/testing | ✅ | pytest with 84 passing tests |

---

## Phase 2: Perception ✅

| Feature | Status | Notes |
|---------|--------|-------|
| Camera capture | ✅ | Synchronous + threaded wrappers |
| YOLO object detection | ✅ | YOLOv8 nano with configurable confidence |
| MediaPipe hand tracking | ✅ | HandLandmarker + GestureRecognizer |
| Gesture recognition (native) | ✅ | GestureRecognizer — 8 built-in gestures |
| Gesture recognition (fallback) | ✅ | Rule-based finger-counting (5 gestures) |
| Gesture→Action mapping | ✅ | Executor with cooldown |
| Gesture popups | ✅ | Tkinter windows on gesture command |
| solvePnP distance estimation | ✅ | Configurable object dimensions |
| Hand skeleton overlay | ✅ | 21 landmarks + connections |
| Object bounding boxes | ✅ | With distance labels |
| FrameBroker | ✅ | Thread-safe producer-consumer |
| Background perception threads | ✅ | Daemon threads for hand + object |

---

## Phase 3: Brain & Memory ✅

| Feature | Status | Notes |
|---------|--------|-------|
| ObjectMemory | ✅ | In-memory cache + JSON persistence |
| JsonStorage | ✅ | Atomic file writes |
| TaskManager | ✅ | PENDING→RUNNING→COMPLETED lifecycle |
| Context detection | ✅ | Active window via win32gui |
| PySide6 UI | ✅ | Frameless floating overlay |
| Command system (brain) | ✅ | Event-driven CommandHandler |
| Command system (CLI) | ✅ | Direct execution with registry |
| Help overlay | ✅ | Auto-hiding hotkey reference |
| Hotkey listener | ✅ | pynput global hooks |
| Brain entry point | ✅ | brain_main.py + main_brain.py |

---

## Phase 4: Dashboard ✅

| Feature | Status | Notes |
|--------|--------|-------|
| DearPyGui real-time camera | ✅ | GPU-accelerated texture |
| Sidebar metrics | ✅ | Objects, hands, gesture, command |
| Manual render loop | ✅ | while-running pattern |
| OpenCV fallback | ✅ | Automatic if DPG fails |
| Cursor tracking | ✅ | Crosshair from index fingertip |
| Mode indicator | ✅ | ACTIVE/PASSIVE display |
| Command popups | ✅ | Tkinter gesture confirmation |

---

## Phase 5: Fusion & Integration 🚧

| Feature | Status | Notes |
|---------|--------|-------|
| Hand+Object interaction | ⏳ | "Hand holds object" fusion |
| Fusion Engine | ⏳ | Decision-level + temporal fusion |
| Frame-to-frame tracking | ⏳ | Replace placeholder tracker |
| Batch object events | ⏳ | Reduce EventBus spam |
| PerceptionSnapshot | ✅ | Thread-safe state snapshot |

---

## Phase 6: Intelligence ⏳

| Feature | Status | Notes |
|---------|--------|-------|
| AI reasoning engine | 📝 | LLM integration for spatial queries |
| Voice commands | 📝 | Speech-to-text pipeline |
| Natural language interface | 📝 | "Find the hammer I was holding" |
| Object relationship mapping | 📝 | "Hammer is on the workbench" |
| Spatial scene graph | 📝 | 3D scene understanding |
| Predictive attention | 📝 | Anticipate user needs |

---

## Phase 7: Desktop Agent ⏳

| Feature | Status | Notes |
|---------|--------|-------|
| Desktop automation | 📝 | Open files, run commands, control apps |
| Screen OCR | 📝 | Read UI text via OCR |
| GUI automation | 📝 | Click buttons, fill forms |
| Workflow recording | 📝 | Record + replay user actions |
| System monitoring | 📝 | CPU, RAM, disk, network |

---

## Phase 8: XR Integration ⏳

| Feature | Status | Notes |
|---------|--------|-------|
| Smart glasses support | 📝 | Researching form factor |
| AR HUD overlay | 📝 | Real-world annotation |
| Spatial anchors | 📝 | Persistent world-locked content |
| Eye tracking | 📝 | Gaze-based interaction |
| Hand tracking (native XR) | 📝 | Direct hand input for AR |

---

## Testing Roadmap

| Area | Current | Goal |
|------|---------|------|
| Unit tests | 84 passing | 100+ |
| Gesture system | 28 tests | 40+ |
| EventBus | 5 tests | 10+ |
| Spatial/PnP | 4 tests | 10+ |
| Memory | 6 tests | 10+ |
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
