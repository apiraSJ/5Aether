# Aether Mark-1 System Map & Repository Structure

This document provides a comprehensive operational map of the Aether Mark-1 repository, outlining the purpose and responsibilities of every major directory, subpackage, and critical file.

---

## 1\. Top-Level Directory Overview

| Path | Duty |
| :---- | :---- |
| `aether/` | Main Python package — the entire Aether runtime (core, plugins, vision, UI, task engine, API, AI, etc.) |
| `systems/` | Host-platform "Function Menu" adapter layer — discovers system modules via `manifest.yaml` (currently wraps Aether Mark-1 without moving code) |
| `config/` | YAML configuration (base \+ vision/task/memory/gesture/ai/web \+ archived variants \+ workspace presets) |
| `data/` | Runtime data: SQLite DBs (`memory.db`, `tasks.db`), saved layouts, themes (mostly gitignored/generated) |
| `models/` | ML weights (YOLOv8, MediaPipe hand landmarker/gesture recognizer) — gitignored, downloaded separately |
| `assets/` | Static assets (currently empty) |
| `docs/` | Architecture, roadmap, acceptance, phase specs, audits |
| `scripts/` | Windows launchers (`setup.bat`, `start.bat`, `tick.bat`, `profile.bat`) \+ debug helpers |
| `tests/` | Test suite (phase\_a, contracts, feature tests; \~1,300+ tests) |
| `web/` | Mark-1 Web UI (HTML/CSS/JS) — Track B frontend; `frontend/` is a packaged copy, `frontend.zip` archive |
| `.opencode/` | OpenCode harness config (`plans/`, `package.json`) \+ vendored `node_modules` (tooling, not project source) |
| `.vscode/` | Editor settings (gitignored) |
| `main.py` | Legacy entry point |
| `start.py` | Alternate launcher (modified in working tree) |
| `aether/__main__.py` | CLI entry (`aether = "aether.__main__:main"`) — boot modes (vision/background/profile) |
| `pyproject.toml` | Build metadata, optional deps (`gui`/`perception`/`dev`/`server`/`full`), pytest config |
| `requirements*.txt` | Pip dependency lists |
| `README.md` | Project overview, quick start, architecture, config, gestures, testing |
| `folder_structure.txt` | Generated tree dump (includes node\_modules — not authoritative) |
| `yolov8n.pt` | YOLOv8 nano weights (gitignored) |

---

## 2\. `aether/` Subpackages

### Core Runtime Foundation (`aether/core/`)

* **`application.py`**: Boot → Tick → Shutdown lifecycle orchestrator  
* **`command.py` / `command_bus.py` / `command_registry.py` / `command_result.py`**: Command dataclass, dispatch \+ handler registry, autocomplete/help, result dataclass  
* **`event_bus.py` / `event_bus_v2.py` / `event_type.py`**: Pub/sub (v2 queued \+ flush); 70+ event type constants  
* **`frame_broker.py`**: Central frame distribution \+ consumer registry \+ overwrite tracking  
* **`intent_resolver.py`**: Protocol for resolving text → Command  
* **`profiler.py` / `adaptive_scheduler.py` / `performance_snapshot.py` / `boot_profiler.py`**: Pipeline timing, hardware budgets, dynamic rate control  
* **`plugin.py` / `plugin_loader.py` / `plugin_manager.py` / `plugin_registry.py`**: Plugin base classes, loading, lifecycle management  
* **`service_container.py`**: Dependency Injection (DI) container  
* **`result_pipeline.py`**: Routes `CommandResult` → notifications/history/layout  
* **`virtual_cursor.py` / `pointer_event.py`**: Cursor position \+ pointer event types  
* **`interfaces/`**: Protocols: context provider, memory repo/service, reasoning service, schedule repository  
* **`spatial_object.py` (in domain)**: Spatial object domain model

### AI (`aether/ai/`)

* **`context.py`**: Context engine  
* **`intent.py` / `models.py` / `provider.py` / `providers/` (echo/local/openai)**: Intent classification, AI models, provider abstraction  
* **`memory.py` / `service.py` / `stream.py` / `tools.py`**: AI memory, service orchestration, streaming, tool calling

### API (`aether/api/`)

* **`main.py` / `server.py`**: FastAPI app \+ server bootstrap (Track A exposed over HTTP for Web UI)  
* **`routes/tasks.py` / `routes/calendar.py`**: Task & calendar REST endpoints  
* **`schemas.py` / `dependencies.py` / `errors.py` / `middleware.py`**: Pydantic schemas, DI deps, error handling, middleware

### Task / Schedule Engine (`aether/task/`) — Mark-1 Track A

* **`models.py`**: `TaskItem`, `Evidence`, `HistoryEntry`, `ReviewEntry`, `ImportBatch`, enums, datetime normalization, tz registry  
* **`schema.py`**: SQLite DDL (`items`, `evidence`, `item_history`, `review_queue`, `import_batches`)  
* **`migrations.py`**: Append-only `user_version` migrations  
* **`repository.py`**: `SqliteScheduleRepository` implementing `IScheduleRepository`  
* **`service.py`**: `ScheduleService` — validated CRUD, optimistic concurrency, audit history  
* **`calendar_query.py`**: Day/week/month views, overlap detection (pure functions)  
* **`json_adapter.py`**: Canonical import/export, dedupe, conflict policies  
* **`extraction.py`**: Temporal extraction helper

### Memory, Services & Domain (`aether/memory/`, `aether/services/`, `aether/domain/`)

* **`memory/`**: `memory_manager.py`, `models.py`, `schema.py`, `sqlite_repository.py`, `seed_data.py` (SQLite WAL memory persistence \+ models \+ seed data)  
* **`services/memory_service.py`**: Memory service implementation  
* **`domain/`**: `memory_record.py`, `context_snapshot.py`, `task.py`, `spatial_object.py`

### Plugins (`aether/plugins/`)

Feature plugins: system, CLI, GUI, task, memory, voice, gesture, interaction, AI, baseline, history, performance, result formatter, intent resolver, system commands/info, keyboard. Each registers handlers/commands and subscribes to events. (`task_plugin.py` exposes task/calendar CLI \+ `TASK_*` events.)

### Vision (`aether/vision/`)

* **`plugins.py`**: `VisionAdapterPlugin` (perception state → events)  
* **`tracker.py` / `state_builder.py` / `event_adapter.py`**: Tracking, state construction, event adaptation

### Phase Layers

* **`phase_b/`**: Legacy bridge (`CommandExecutor`)  
* **`phase_c/`**: Input adapters: gesture/keyboard/mouse/voice input plugins  
* **`phase_d/`**: Perception \+ cursor: camera, hand, object (YOLO \+ solvePnP), cursor plugins

### UI (`aether/ui/`)

* **`ui_shell.py`**: Owns window, camera, panels; show/hide/toggle lifecycle  
* **`ui_context.py`**: DI bundle for widgets  
* **`overlay_controller.py` / `overlay_model.py` / `overlay_widget.py`**: Overlay rendering pipeline  
* **HUD Widgets**: `camera_widget.py`, `cursor_widget.py`, `gesture_widget.py`, `status_widget.py`, `timeline_widget.py`, `object_list_widget.py`, `performance_hud.py`, `notification_widget.py`, `command_palette_widget.py`  
* **`hud_manager.py`**: Multi-layer throttle scheduler  
* **Camera state**: `camera_anchor.py`, `camera_mode.py`, `camera_state.py`  
* **`interaction_bridge.py` / `repaint_monitor.py`**: UI bridging \+ repaint diagnostics  
* **`panel/`**: Panel framework: abstract panel, registry, controller, session, layout manager, theme manager, widget factory, and concrete panels (tasks, memory, dashboard, system, baseline, AI chat, notifications, vision, placeholder, workspace)

### Interaction (`aether/interaction/`)

Gesture, mouse, keyboard, drag, resize, snap, selection, focus, hit-test, cursor mapping, filter, animation, and state controllers.

### Workspace & Layout (`aether/workspace/`)

Workspace manager \+ interfaces (`i_workspace`, `i_layout`, `i_interaction_target`).

### Voice (`aether/voice/`)

Audio capture, STT, recognizers, intent parser.

### Baseline, History, Sandbox

* **`baseline/`**: `baseline_service.py` \+ `plugins/baseline_plugin.py` (Baseline metrics/info commands)  
* **`history/`**: `service.py` \+ `plugins/history_plugin.py` (Command history persistence/service)  
* **`sandbox/`**: `catalog.py` (Sandbox catalog)

### Presentation, Config, App

* **`presentation/banner.py`**: Startup banner  
* **`config/loader.py`**: YAML config loading  
* **`app.py`**: Application bootstrap/wiring  
* **`__init__.py`**: Package version (`1.0.0`)

---

## 3\. Systems Layer (`systems/`)

* **`manifest_discovery.py`**: Discovers & loads system modules via `manifest.yaml`, independent of `PluginLoader`.  
* **`mark1/manifest.yaml`**: Declares Aether Mark-1 system (id, version, capabilities, entrypoint, lifecycle).  
* **`mark1/adapter.py`**: `Mark1Adapter` implementing `SystemModule` protocol (start/stop/health), delegating to existing Aether services.  
* **`mark1/__init__.py`**: Package initialization.

---

## 4\. Configuration, Data, Models & Docs

* **`config/`**: `default.yaml`, `vision.yaml`, `task.yaml`, `memory.yaml`, `gesture.yaml`, `ai.yaml`, `web.yaml`, workspace presets (`workspaces/hand.yaml`), and archives (`archive/desktop.yaml`, `archive/test.yaml`).  
* **`data/`**: Runtime SQLite stores (`memory.db`, `tasks.db`), saved UI/workspace layouts (`layouts/*.json`), themes (`themes/*.json`).  
* **`models/`**: ML weights (YOLOv8, MediaPipe hand landmarker/gesture recognizer).  
* **`docs/`**: Architecture, roadmap, UI-2 plan, workspace, review audit, structure audit, acceptance checklist, phase 4 spec, AI assistant baseline, capability inventory, and architecture audits.  
* **`tests/`**: Core runtime tests (`phase_a/`), interface contract tests (`contracts/`), and integration/feature tests (`test_*.py`).  
* **`web/`**: Track B web frontend (`index.html`, `app.js`, `styles.css`), packaged copy (`frontend/`), and archive (`frontend.zip`).

---

## 5\. Entry Points & Scripts

* `python -m aether` / `aether` console script → `aether.__main__:main` (vision/background/profile modes).  
* `main.py` → Legacy entry point.  
* `start.py` → Alternate launcher.  
* `scripts/*.bat` → Windows one-click setup/start/tick/profile utilities.

---

## 6\. Design Notes

* Event-driven, one-way data flow (`Camera` → `FrameBroker` → `perception` → `EventBus` → `UI`).  
* Plugin-based and config-driven modular architecture.  
* Thread-safe and designed for low-latency operations with zero mandatory external AI egress (supports local/echo providers).

---

*Last updated: October 2026*