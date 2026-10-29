# ARCHITECTURE_AUDIT.md (Read-only Code Map)
Generated: 2026-10-24 (repo: D:\3CS\5Aether)  
Scope: aether/ + tests/ (read-only). Read-only cross-check of config/, docs/ per instructions.  
Constraints observed: no edits to aether/__main__.py, start.py, tests/test_venv_autoselect.py, docs/PHASE4_SPEC.md, folder_structure.txt, systems/; no pytest/cache; no commit.

## 1) Git / Working Tree (evidence)
- Branch/commits: git history 61 commits, single author ApirakSa; last 10 commits are continuous web P1→P4→acceptance (as reported).
- Tracked: ~340 files (aether/205, tests/90, config/10, docs/9, scripts/6, web/3, data/3, models/3)
- Working tree: `M aether/__main__.py (+67)`, `M start.py (+4/-1)`; untracked: `docs/PHASE4_SPEC.md`, `folder_structure.txt` (36,929 lines), `systems/` (5 files), `tests/test_venv_autoselect.py`. No staged changes.
- Diff theme (static): venv auto re-exec in `aether/__main__.py` + `start.py` server extras + `tests/test_venv_autoselect.py` — coherent (not random). **Untouched per constraints**.

## 2) Entry Points & Orchestration (evidence)
| File:Line | Role | Evidence/Notes |
|---|---|---|
| `aether/__main__.py:136,150,157,301-308` | CLI/main | Modes: `tick` → `AetherApplication` (`core/application.py`), `vision` → `_run_vision` uses `AetherApplication`, otherwise `AetherApp` (`app.py`), web via `api/server.py`. Auto-selects config for vision/web. |
| `aether/app.py:27,49,83-88` | AetherApp (Phase A boot orchestrator) | Creates `ServiceContainer`, `EventBus` (v1), `ResultPipeline`, `CommandBus`, registers `event_bus`/`result_pipeline`/`command_bus`. Loads plugins via `PluginLoader`. Headless runs via `_run_headless`. Uses v1 `EventBus`. |
| `aether/core/application.py:91,123` | AetherApplication | Registers `application` instance; used by tick/vision paths. Different orchestrator from `AetherApp` (two entry orchestrators). |
| `aether/api/server.py:1-70` | Web server (`--mode web`) | Imports `uvicorn`, `create_app`, starts loaded plugins, serves API, shuts down on stop. Local-only (127.0.0.1). |
| `start.py` | Entry wrapper | Modified in working tree (server extras / venv hints) — **untouched**. |

Confidence: Verified callable (static).

## 3) Event Bus: v1 vs v2 (evidence)
| Component | Usage | Notes |
|---|---|---|
| `aether/core/event_bus.py` (v1) | Imported by `aether/app.py:27`, `aether/core/reasoning_service.py:23`, `aether/phase_b/command_executor.py:16`; tests `tests/phase_a/test_event_bus.py`. | Legacy/simple; limited production reach relative to v2. |
| `aether/core/event_bus_v2.py` | Referenced/imported widely (70 matches across aether/tests). | Production-heavy in modern paths (plugins/tests use v2). |
| `aether/core/event_type.py` vs `aether/phase_c/event_type.py` | Two different `EventType` enums (v2 unified vs phase_c smaller set). | Different schemas; coexist. |
| `aether/app.py` uses v1 `EventBus` explicitly (`EventBus()` created and registered). | Orchestrator choice differs from v2-heavy paths. | Coexistence / migration boundary (not obviously broken statically).

Evidence level: Verified callable (static). Confidence: High (imports + instantiation traced).

## 4) Plugin System & Config Wiring (evidence)
| File:Line | Finding | Evidence |
|---|---|---|
| `aether/core/plugin_loader.py:81-120` | Loader behavior | Loads by module/class from config specs, validates subclass of `PluginBase`, deduplicates/instantiates; no obvious global dedup beyond load logic. |
| `config/default.yaml:1-10` | 10 modules | system_commands, performance, gui, rule_intent, intent_resolver, memory, task, ai, keyboard, interaction. |
| `config/vision.yaml:1-21` (with duplicates) | 21 entries (has duplicates) | system, gui, interaction, memory, ai, system_commands, rule_intent, intent_resolver, result_formatter, cli, phase_d.hand_plugin (x2), baseline, voice_input, task, vision.plugins (x2), phase_d.camera_plugin, phase_d.hand_plugin, phase_d.object_plugin, phase_d.cursor_plugin, gesture_plugin. Duplicates: `aether.phase_d.hand_plugin` x2, `aether.vision.plugins` x2. |
| `config/web.yaml:1-33` | 1 module | `aether.plugins.task_plugin` only (Track B). |
| `config/task.yaml` | (present) | Referenced; minimal wiring context. |

Notes: duplicates exist in vision config (loader behavior determines effect — static). 

Evidence level: Verified callable (static).

## 5) Commands: Advertised vs Handled (evidence)
- Advertised (CommandInfo): 58 (across aether/plugins)  
- Handled (register_handler/register): 74  
- Union: 75

| Category | Details | Evidence |
|---|---|---|
| Advertised-no-handler | `vision.scan` only | `aether/plugins/system_commands_plugin.py:88` advertised, no handler registered (grep). |
| Handled-no-advertised | `cursor_click`, `cursor_move`, `system.info`, `ui.camera.*` (6), `ui.layout.load`, `ui.panel.focus`, `ui.panel.toggle`, `ui.shell.*` (4) | `system_commands_plugin.py:310-311`; `system_info_plugin.py:36`; `gui_plugin.py:109-120,123-126`. |
| Duplicates (handlers) | `system.info` (system_info_plugin + system_plugin), `system.ping` (3 places), `system.shutdown` (2 places) | `system_info_plugin.py:36-37`, `system_plugin.py:37-39`, `system_commands_plugin.py:306-307`. CommandBus logs override on duplicate registration. |
| Duplicates (advertised) | `memory.recall/remember/forget/list` advertised in both `memory_plugin.py` and `system_commands_plugin.py` | `memory_plugin.py:46,53,60,67`, `system_commands_plugin.py:93,100,107,114`. |

Whitelist (AI tools): `aether/ai/tools.py:26-104` allows `ui.panel.toggle`, `memory.recall`, `memory.search`, `system.ping`, `system.info` (5). Note `memory.search` appears in whitelist but not in advertised/handled sets above (static check) — treat as capability declared by whitelist, not necessarily advertised/handled by command registry.

Evidence level: Verified callable (static).

## 6) GUI / Panels / Layout / Theme (evidence)
| Item | Evidence | Notes |
|---|---|---|
| GUI plugin wiring | `aether/plugins/gui_plugin.py:105-437` registers instances: `overlay_model`, `panel_registry`, `notification_manager`, `workspace_manager`; resolves services; registers handlers for `ui.panel.focus/toggle`, `ui.layout.load`, camera/shell commands. | Central GUI wiring. |
| Panels: two memory panel systems | `aether/panels/memory_panel.py` + `aether/panels/__init__.py` exports it; `aether/ui/panel/memory_panel.py` + `aether/ui/panel/__init__.py` exports it. Importers differ (panels used by gui_plugin; ui.panel used by tests/integration). | Duplication of panel implementations/classes across `panels/` vs `ui/panel/`. |
| Layout/Theme | `aether/ui/panel/layout_manager.py`, `aether/ui/panel/theme_manager.py` exported from `aether/ui/panel/__init__.py`. Used by `system_commands_plugin.py:470-560` (handlers layout.save/load/list/delete/reset, theme.apply/list) and tested in `tests/test_layout_manager.py`, `tests/test_integration_phase3a5.py`. | Managed via container (`layout_manager`, `theme_manager`) resolved in handlers. |
| SystemCommands GUI handlers | `system_commands_plugin.py:466-560` show handlers that resolve `layout_manager`/`theme_manager`/`panel_registry` from container when available. | GUI-integrated command handlers. |
| Status widgets | `aether/ui/status_widget.py`, `aether/ui/hand_status_widget.py`, `aether/ui/status_bar_widget.py` used by `ui_shell.py` and tests. | UI components present. |

Evidence level: Verified callable (static) for wiring; duplication noted.

## 7) API (Web Mode) (evidence)
| Route | File:Line | Notes |
|---|---|---|
| `GET /health` | `aether/api/main.py:86` | Health endpoint. |
| `GET /` | `aether/api/main.py:95` | Root. |
| Calendar | `aether/api/routes/calendar.py:28 (/day)`, `44 (/week)`, `54 (/month)` | Calendar routes. |
| Tasks | `aether/api/routes/tasks.py:27 ("") GET`, `44 (/{item_id}) GET`, `54 ("") POST`, `81 (/{item_id}) PATCH`, `129 (/{item_id}/complete) POST`, `139 (/{item_id}/cancel) POST`, `150 (/{item_id}) DELETE`, `160 (/{item_id}/history) GET` | Full CRUD + actions + history. |
| Static | `web/app.js` (15304), `web/index.html` (4260), `web/styles.css` (5127) | Web UI assets present. |

Evidence level: Verified callable (static).

## 8) Memory / Task / AI (evidence)
| Area | Key files | Notes |
|---|---|---|
| Memory | `aether/memory/memory_manager.py` (MemoryManager), `aether/memory/memory_service.py` (MemoryService), models/repo present. Interfaces used: `aether/core/interfaces/i_schedule_repository.py` imported by `aether/task/repository.py:21`, `aether/task/service.py:27`. | Memory core exists; commands advertised twice (duplication). |
| Task (Schedule) | `aether/plugins/task_plugin.py` in web/default configs; API routes for tasks present; DB path `data/tasks.db` per web.yaml. | Track B uses TaskPlugin; API exposes tasks. |
| AI | `aether/plugins/ai_plugin.py` owns `ai.chat`; `aether/ai/tools.py` whitelist present; providers/service/models present. | AI integrated via plugin/commands/tools. |

Evidence level: Verified callable (static).

## 9) Dead/Orphan/Dormant/Conflict (static reachability)
Scan: 296 modules (205 `aether` + 91 `tests`). Reachability by imports (static).

### Syntax/parse issues
| File:Line | Issue | Notes |
|---|---|---|
| `aether/core/reasoning_service.py:177` | Unterminated string literal (syntax error) | Not importable; no importers found. Treat as **Dormant/Unparsable**. |

### Orphans (no importers found in aether/tests static scan)
19 files with 0 references:
- `aether/core/plugin_manager.py` (self-import at line 15 `from aether.core.plugin_manager import PluginManager` — circular/self-import pattern)
- `aether/core/plugin_registry.py` (0 importers)
- `aether/core/pointer_event.py` (exported from `aether/core/__init__.py` but no other importers found in aether/tests scan)
- `aether/core/reasoning_service.py` (syntax error, 0 importers)
- `aether/history/service.py` (0 importers)
- `aether/phase_b/command_executor.py` (only defines classes; `aether/phase_b/__init__.py` tries to import from it and others — see below)
- `aether/phase_c/event.py`, `aether/phase_c/event_type.py`, `aether/phase_c/gesture_input_plugin.py`, `aether/phase_c/keyboard_input_plugin.py`, `aether/phase_c/mouse_input_plugin.py`, `aether/phase_c/voice_input_plugin.py` (4 input plugins not wired in configs)
- `aether/plugins/history_plugin.py`, `aether/plugins/system_info_plugin.py` (handlers registered but wiring/usage context mixed; see notes)
- `aether/presentation/banner.py` (0 importers)
- `aether/ui/panel/workspace_widget.py` (0 importers)
- `aether/workspace/i_interaction_target.py`, `aether/workspace/i_layout.py`, `aether/workspace/i_workspace.py` (interfaces, 0 importers found)

### Structural conflicts/integrity issues
| Item | Evidence | Assessment |
|---|---|---|
| `aether/phase_b/__init__.py:9-14` imports 5 modules that don't exist as files | `from .context_manager_plugin`, `from .notification_handler`, `from .history_handler`, `from .layout_handler`, `from .memory_service` — only `command_executor.py` and `__init__.py` exist in `aether/phase_b/`. | **Broken import chain** (would fail on import). |
| `aether/core/plugin_manager.py:15` self-import | Circular/self-import pattern; no importers. | **Dormant/Problematic**. |
| `aether/core/plugin_registry.py` | No importers. | **Dormant**. |
| `aether/core/startup_validator.py` | Defined, no prod importers found in static scan (present as module). | **Structure only / possibly unused**. |
| Panels duplication | `aether/panels/memory_panel.py` vs `aether/ui/panel/memory_panel.py` (different import paths, both used by different parts). | **Duplicate implementations** (potential confusion). |
| Entry points | `aether/app.py` (v1 EventBus) vs `aether/core/application.py` (AetherApplication) — two orchestrators used by different modes. | **Coexistence** (not necessarily dead; different code paths). |
| EventBus v1 vs v2 | Coexist, different importers. | **Migration boundary**. |
| Config duplicates | vision.yaml has duplicate module entries (`hand_plugin` x2, `vision.plugins` x2). | **Redundant wiring** (effect depends on loader). |
| Command duplication | handlers for `system.info/ping/shutdown` in multiple plugins; memory commands advertised twice. | **Conflict/duplication** (CommandBus overrides on register). |

Evidence level: Structure only / Dormant / Conflict as indicated. Note: dynamic/config-based imports could affect reachability (static scan limitation stated).

## 10) Tests (static summary)
- Test files: 91 (`tests/` tree). Module-level test functions: ~1467, test classes: ~276 (ast scan).  
- Files with zero test functions/classes (structural only): `tests/__init__.py`, `tests/conftest.py`, `tests/contracts/__init__.py`, `tests/phase_a/__init__.py`, `tests/test_dataflow.py`.  
- `__main__` blocks: `tests/test_shutdown.py`, `tests/test_virtual_cursor.py` (runnable as scripts).  
- **Test counts in docs conflict (must not guess):** `docs/ACCEPTANCE.md` states 1,446; `docs/REVIEW_AUDIT.md` states 1,091 passed; `docs/AI_ASSISTANT_BASELINE.md` states 691 — treated as **document claims only**, not verified (pytest not run per constraints).

Evidence level: Structure only.

## Appendix A: Evidence references (key)
- Git: `git status --short`, `git log --oneline -5` (context)  
- Commands: AST scan of aether/plugins for CommandInfo/register_handler  
- Imports: grep across aether,tests for key symbols  
- Config: `config/*.yaml`  
- API: `aether/api/main.py`, `aether/api/routes/*`  
- Syntax: `aether/core/reasoning_service.py:177`

**Read-only audit complete. No files modified.**
