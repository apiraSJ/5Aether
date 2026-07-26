# Aether Roadmap

## Current Status

**Backend v1.0.0** — Architecture Stable (tagged `backend-v1.0.0`)

- Core runtime: Boot/Tick/Shutdown, EventBus, CommandBus, Plugin System
- Vision pipeline: Camera, YOLO, MediaPipe, FrameBroker, AdaptiveScheduler
- UI: PySide6 HUD with 4-layer throttle, per-object caching
- CLI: Event-driven with IntentResolver, CommandRegistry, tab-completion
- Tests: 128 passing

---

## Phase 3A — AI Command Interface

**Goal:** User can control Aether via natural language in the CLI.

### Sprint 1 — CLI Polish (Current)

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
4. **Test everything** — 128+ tests, run before every commit
