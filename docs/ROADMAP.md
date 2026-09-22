# Aether Roadmap

## Current Status

**Backend v1.0.0** — Architecture Stable (tagged `backend-v1.0.0`)

- Core runtime: Boot/Tick/Shutdown, EventBus, CommandBus, Plugin System
- Vision pipeline: Camera, YOLO, MediaPipe, FrameBroker, AdaptiveScheduler
- UI: UIShell with camera, panels, workspace, lifecycle (show/hide/toggle)
- CLI: Event-driven with IntentResolver, CommandRegistry, tab-completion
- Tests: 921 passing

### Commit History (UI Lifecycle)

```
dfd5d36 feat: add UI-1 shell show/hide API       (921 tests)
d73b82a feat: add background startup mode          (909 tests)
1f606d7 feat: add UIShell UI foundation            (909 tests)
f363b5c feat: Phase 3.3 Intent Reasoning
3ad8595 feat: Phase 3.2 Memory Retriever
```

---

## Phase 3A — AI Command Interface

**Goal:** User can control Aether via natural language in the CLI.

### Sprint 1 — CLI Polish ✅

- [x] CLI Plugin (event-driven, readline with fallback)
- [x] IntentResolver interface + RuleEngine (14 patterns)
- [x] CommandRegistry (autocomplete, help, categories)
- [x] ResultFormatter (colored output, silent filter)
- [x] SystemCommandPlugin (help, status, plugins, ping, quit)

### Sprint 2 — Spatial Memory MVP

- [ ] Memory Service (SQLite WAL)
- [ ] `memory.remember <name> [at <location>]`
- [ ] `memory.recall <query>`
- [ ] `memory.forget <name>`
- [ ] `memory.list`
- [ ] Location tracking with timestamps

### Sprint 3 — Memory Panel

- [ ] MemoryPanelWidget (PySide6)
- [ ] Objects / Places / History tabs
- [ ] Connected to Memory Service
- [ ] F3 toggle shortcut

---

## UI Lifecycle — Desktop UX Foundation

**Goal:** Aether behaves as a normal desktop application with opt-in background mode.

### Lifecycle Semantics (locked)

```
Background ≠ Shutdown
Hide ≠ Shutdown
Quit = real graceful shutdown
```

| Action | Result |
|--------|--------|
| Normal boot | UI visible, runtime active |
| `--background` | UI hidden, runtime active |
| Hide (button/tray/hotkey) | UI hidden, runtime active |
| Quit (system.shutdown) | Real graceful shutdown |

### Execution Order

```
UI-0 → UI-1 → UI-3 → UI-4 → UI-2 → UI-5 → UI-6
```

### UI-0: Startup Visibility ✅

**Commit:** `d73b82a` feat: add background startup mode
**Tests:** 909 → 909 (18 UI-0 tests added)

Scope:
- [x] `gui.start_visible: true` default in config/default.yaml
- [x] `ConfigLoader.set(dotted, value)` method
- [x] `Application.boot(background=False)` param + override
- [x] `app.py` + `__main__.py` `--background` CLI flag
- [x] `setQuitOnLastWindowClosed(False)` stays
- [x] UI visibility does NOT determine runtime lifecycle

### UI-1: Runtime Control ✅

**Commit:** `dfd5d36` feat: add UI-1 shell show/hide API
**Tests:** 909 → 921 (12 UI-1 tests added)

Scope:
- [x] `UIShell.show()`, `hide()`, `toggle()`, `is_visible`
- [x] `GUIPlugin.show_ui()`, `hide_ui()`, `toggle_ui()`, `is_ui_visible()`
- [x] `ui.shell.show`, `ui.shell.hide`, `ui.shell.toggle`, `ui.shell.is_visible` commands
- [x] `CommandInfo` entries for palette discovery
- [x] Integration with `gui_plugin.py` rewrite (UIShell composition root)

### UI-2: Global Hotkey 🔄 (planned)

**Plan:** `docs/UI-2-plan.md`

Scope (locked):
- [ ] Ctrl+Alt+Space via Win32 `RegisterHotKey` (ctypes)
- [ ] `GUIPlugin._parse_hotkey()`, `_register_hotkey()`, `_poll_hotkey()`, `_unregister_hotkey()`
- [ ] Calls `GUIPlugin.toggle_ui()` → `UIShell.toggle()`
- [ ] 12 tests (parser, registration, dispatch)

NOT in scope: system tray, window −/×, Alt+F4, persistence, shutdown, UI redesign, panel changes.

### UI-3: Window Controls (planned)

- [ ] Custom `−` (hide) and `×` (quit) buttons
- [ ] Frameless `Qt.Tool` window
- [ ] `−` → `GUIPlugin.hide_ui()` → `UIShell.hide()`
- [ ] `×` → `system.shutdown` → `app.request_shutdown()`

### UI-4: System Tray (planned)

- [ ] QSystemTrayIcon with context menu
- [ ] Show / Hide / Quit actions
- [ ] Tray → Hide → `GUIPlugin.hide_ui()`

### UI-5: Persistence (planned)

- [ ] `data/ui_state.json` (git-ignored)
- [ ] Save/restore window position, visibility
- [ ] Auto-save on shutdown

### UI-6: Polish & Edge Cases (planned)

- [ ] Alt+F4 → `system.shutdown` (not hide)
- [ ] Taskbar behavior
- [ ] Multi-monitor support
- [ ] Focus restore after show()

---

## Phase 3B — Ollama Integration

**Goal:** Natural language → Command via local LLM.

- [ ] `OllamaIntentResolver` implementing `IIntentResolver`
- [ ] Prompt templates for Aether commands
- [ ] Fallback to RuleEngine when Ollama unavailable
- [ ] Configurable model selection

---

## Phase 3C — AI Chat

**Goal:** Conversational interface for Aether.

- [ ] ChatPanelWidget (PySide6)
- [ ] Chat history with context
- [ ] Multi-turn conversations
- [ ] Voice input integration

---

## Phase 4 — Workflow Engine

**Goal:** Automate multi-step tasks.

- [ ] Workflow definition (YAML/JSON)
- [ ] Step executor with conditionals
- [ ] Loop/retry support
- [ ] Integration with memory + vision

---

## Phase 5 — Desktop Automation

**Goal:** Control desktop applications via gestures/voice.

- [ ] pywinauto integration
- [ ] Window management commands
- [ ] Application launching
- [ ] Keyboard/mouse simulation

---

## Phase 6 — XR Interface

**Goal:** Port to smart glasses.

- [ ] OpenXR integration
- [ ] Spatial UI rendering
- [ ] Hand tracking in 3D space
- [ ] Voice-first interaction

---

## Design Principles (Post-v1)

1. **Every commit adds user-facing capability** — no more infrastructure-only changes
2. **Backend v1 is frozen** — fix only bugs or security issues
3. **Feature-first** — Memory → AI → Automation → XR
4. **Test everything** — 921+ tests, run before every commit
