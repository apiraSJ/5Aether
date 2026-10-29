# CAPABILITY_INVENTORY.md (Read-only)
Generated: 2026-10-24 (repo: D:\3CS\5Aether)  
Scope: aether/ + tests/ + config/ cross-check. No runtime test execution.  
Evidence levels: `Verified callable (static)`, `Test-only`, `Structure only`, `Dormant`, `Conflict`.

## 1) Capability Groups (16)
| # | Capability Group | Status | Key Paths | Evidence | Notes |
|---|---|---|---|---|---|
| 1 | Baseline/Core Boot & Orchestration | Verified callable (static) | `aether/__main__.py`, `aether/app.py`, `aether/core/application.py`, `aether/core/service_container.py`, `aether/core/plugin_loader.py` | Modes tick/vision/web; AetherApp (v1 EventBus) vs AetherApplication; plugin loading from config. | Two orchestrators coexist. |
| 2 | Event/Command/Result Pipeline | Verified callable (static) | `aether/core/event_bus.py`(v1), `aether/core/event_bus_v2.py`(v2), `aether/core/command_bus.py`, `aether/core/result_pipeline.py`, `aether/core/event_type.py` | v1 used by app/reasoning/phase_b; v2 widely used (70 refs). CommandBus override-on-duplicate. | Coexistence/migration boundary. |
| 3 | Plugin System & Config Wiring | Verified callable (static) | `aether/core/plugin_base.py`, `aether/core/plugin_loader.py`, `config/default.yaml`, `config/vision.yaml`, `config/web.yaml` | 10/21/1 modules; vision has duplicates (hand_plugin x2, vision.plugins x2). | Redundant entries. |
| 4 | CLI / System Commands | Verified callable (static) | `aether/plugins/system_commands_plugin.py`, `aether/plugins/system_plugin.py`, `aether/plugins/system_info_plugin.py`, `aether/plugins/cli_plugin.py` | 58 advertised, 74 handled, union 75. Duplicates: system.info/ping/shutdown. Advertised-no-handler: vision.scan. | Command registry conflicts. |
| 5 | GUI / Panels / Workspace | Verified callable (static) | `aether/plugins/gui_plugin.py`, `aether/panels/*`, `aether/ui/panel/*`, `aether/ui/ui_shell.py` | Panel registry/workspace/overlay registered; two memory panel implementations (`panels/` vs `ui/panel/`). Handlers ui.panel.focus/toggle, ui.layout.load registered. | Duplication. |
| 6 | Layout / Theme | Verified callable (static) | `aether/ui/panel/layout_manager.py`, `aether/ui/panel/theme_manager.py`, `aether/plugins/system_commands_plugin.py:466-560` | Handlers layout.save/load/list/delete/reset, theme.apply/list; tested. Container-resolved. | Integrated via commands. |
| 7 | Interaction / Input / Cursor | Verified callable (static) | `aether/plugins/interaction_plugin.py`, `aether/core/virtual_cursor.py`, `aether/core/pointer_event.py`, `aether/phase_c/*`(plugins) | VirtualCursor present (tests + impl); PointerEvent exported from core but no other importers found. Phase_c input plugins not wired in configs. | Partially wired/orphaned. |
| 8 | Vision / Camera / Gesture | Verified callable (static) | `aether/phase_d/*`, `aether/plugins/gesture_plugin.py`, `aether/vision/*`, `config/vision.yaml` | Wired in vision config; phase_d plugins present. vision.scan advertised but no handler. | Mixed wiring. |
| 9 | Memory Core | Verified callable (static) | `aether/memory/*`, `aether/plugins/memory_plugin.py`, `aether/plugins/system_commands_plugin.py` | MemoryManager/MemoryService/models/repo present. Commands advertised twice (memory_plugin + system_commands). | Duplication. |
| 10 | Task / Calendar (Schedule) | Verified callable (static) | `aether/plugins/task_plugin.py`, `aether/task/*`, `aether/api/routes/tasks.py`, `aether/api/routes/calendar.py`, `config/web.yaml` | API CRUD+actions+history for tasks; calendar routes; web mode uses TaskPlugin only. DB `data/tasks.db`. | Web track integrated. |
| 11 | AI Assistant | Verified callable (static) | `aether/plugins/ai_plugin.py`, `aether/ai/*`, `aether/ai/tools.py` | ai.chat owned by AIPlugin; tool whitelist 5 commands. Providers/service present. | Wired in default/vision. |
| 12 | Intent/Rule/Result Formatting | Verified callable (static) | `aether/plugins/rule_intent_plugin.py`, `aether/plugins/intent_resolver_plugin.py`, `aether/plugins/result_formatter_plugin.py` | Wired in default/vision configs. | Integrated. |
| 13 | API / Web Server | Verified callable (static) | `aether/api/main.py`, `aether/api/server.py`, `aether/api/routes/*`, `web/*` | Health/root, calendar, tasks routes; uvicorn server, local-only; static assets present. | Track B present. |
| 14 | History / Presentation / UI Extras | Structure only/Dormant | `aether/history/service.py`, `aether/presentation/banner.py`, `aether/plugins/history_plugin.py`, `aether/ui/panel/workspace_widget.py` | Some files exist but no importers found (or minimal). cli.history handled/advertised. | Largely unused/orphaned. |
| 15 | Sandbox/Catalog/Performance/Voice/Baseline | Verified callable (static)/Structure only | `aether/plugins/performance_plugin.py`, `aether/plugins/voice_input_plugin.py`, `aether/plugins/baseline_plugin.py`, `aether/sandbox/*` | Wired in configs; tests exist for sandbox/baseline/voice. | Mixed. |
| 16 | Legacy/Phase Modules & Orphans | Dormant/Conflict | `aether/phase_b/*` (broken __init__), `aether/phase_c/*` (mostly orphan plugins), `aether/core/plugin_manager.py` (self-import), `aether/core/plugin_registry.py`, `aether/core/reasoning_service.py` (syntax error), `aether/core/startup_validator.py`, `aether/workspace/*` interfaces | Many unused/orphaned; some broken imports; syntax error blocks reasoning_service. | Cleanup candidates (read-only). |

## 2) Command Appendix (union 75)
### Advertised (58) — from CommandInfo
`system.help`, `system.status`, `system.plugins`, `system.commands`, `system.ping`, `system.shutdown`, `cli.history`, `cli.clear`, `vision.scan`, `memory.recall`, `memory.remember`, `memory.forget`, `memory.list`, `system.panel.show`, `system.panel.hide`, `system.panel.toggle`, `system.panel.list`, `system.layout.save`, `system.layout.load`, `system.layout.list`, `system.layout.delete`, `system.layout.reset`, `system.theme.apply`, `system.theme.list`, `interaction.cursor.enable`, `interaction.cursor.disable`, `interaction.cursor.click`, `interaction.mode.cursor`, `interaction.mode.panel`, `interaction.mode.reset`, `panel.select`, `panel.focus`, `panel.move`, `panel.resize`, `panel.reset`, `interaction.debug`, `system.boot.profile` + memory commands duplicated in `memory_plugin.py` (see above) → total distinct advertised 58 (some duplicates advertised).

### Handled (74) — registered
From grep/AST: `cli.history`, `system.shutdown`, `system.ping`, `system.info` (dup), `cursor_click`, `cursor_move`, `ui.panel.focus`, `ui.panel.toggle`, `ui.layout.load`, `ui.camera.hide/show/toggle/mode.*`, `ui.shell.hide/show/toggle/is_visible`, plus system_commands handlers for system.* (many), cli.*, vision.scan? (advertised no handler), memory.* via both plugins, layout/theme, interaction/cursor/panel/boot.profile, etc. Full union 75 distinct command names.

### Key mappings
| Command | Advertised | Handled | Config-wired | Callers/Notes | Evidence Level |
|---|---|---|---|---|---|
| `system.ping` | yes (syscmd) | yes (3) | plugins load | tests/boot proof; duplicate handlers (override) | Verified callable (static) |
| `system.info` | no (syscmd) | yes (2) | plugins load | `system_info_plugin`, `system_plugin` duplicate | Verified callable (static) |
| `system.shutdown` | yes | yes (2) | plugins load | duplicate | Verified callable (static) |
| `vision.scan` | yes (syscmd) | no | vision config has syscmd plugin | advertised only | Conflict (advertised-no-handler) |
| `memory.recall/remember/forget/list` | yes (2 places) | yes (likely) | memory plugins wired | advertised twice | Conflict (dup advertised) |
| `ai.chat` | not in CommandInfo list above | (plugin owned) | ai_plugin wired | `aether/plugins/ai_plugin.py` owns command | Verified callable (static) |
| `ui.panel.toggle` | no | yes (gui_plugin) | gui_plugin wired | also in AI whitelist | Verified callable (static) |
| `ui.layout.load` | no | yes (gui_plugin) | gui_plugin wired | gui_plugin registers handler | Verified callable (static) |
| `layout.save/load/list/delete/reset` | yes (syscmd) | yes (syscmd) | syscmd wired | resolve layout_manager from container | Verified callable (static) |
| `theme.apply/list` | yes (syscmd) | yes (syscmd) | syscmd wired | resolve theme_manager from container | Verified callable (static) |
| `cursor_click/cursor_move` | no | yes (syscmd) | syscmd wired | handled directly | Verified callable (static) |

### AI Tool Whitelist (separate from CommandInfo)
`aether/ai/tools.py`: `ui.panel.toggle`, `memory.recall`, `memory.search`, `system.ping`, `system.info` — `memory.search` not present in advertised/handled command sets above (static). Treat as declared capability.

## 3) API Surface
| Endpoint | Path/File | Evidence Level |
|---|---|---|
| GET /health | `aether/api/main.py:86` | Verified callable (static) |
| GET / | `aether/api/main.py:95` | Verified callable (static) |
| GET /calendar/day | `aether/api/routes/calendar.py:28` | Verified callable (static) |
| GET /calendar/week | `aether/api/routes/calendar.py:44` | Verified callable (static) |
| GET /calendar/month | `aether/api/routes/calendar.py:54` | Verified callable (static) |
| GET /tasks | `aether/api/routes/tasks.py:27` | Verified callable (static) |
| GET /tasks/{item_id} | `aether/api/routes/tasks.py:44` | Verified callable (static) |
| POST /tasks | `aether/api/routes/tasks.py:54` | Verified callable (static) |
| PATCH /tasks/{item_id} | `aether/api/routes/tasks.py:81` | Verified callable (static) |
| POST /tasks/{item_id}/complete | `aether/api/routes/tasks.py:129` | Verified callable (static) |
| POST /tasks/{item_id}/cancel | `aether/api/routes/tasks.py:139` | Verified callable (static) |
| DELETE /tasks/{item_id} | `aether/api/routes/tasks.py:150` | Verified callable (static) |
| GET /tasks/{item_id}/history | `aether/api/routes/tasks.py:160` | Verified callable (static) |

## 4) Config Wiring Summary
| Config | Plugins (count) | Notes | Evidence Level |
|---|---|---|---|
| `config/default.yaml` | 10 | system_commands, performance, gui, rule_intent, intent_resolver, memory, task, ai, keyboard, interaction | Verified callable (static) |
| `config/vision.yaml` | 21 (with duplicates) | system, gui, interaction, memory, ai, system_commands, rule_intent, intent_resolver, result_formatter, cli, phase_d.hand_plugin(x2), baseline, voice_input, task, vision.plugins(x2), phase_d.camera_plugin, phase_d.hand_plugin, phase_d.object_plugin, phase_d.cursor_plugin, gesture_plugin | Verified callable (static) |
| `config/web.yaml` | 1 | task_plugin only | Verified callable (static) |
| `config/task.yaml` | (present) | task-related config | Structure only |

## 5) Orphan/Dead/Dormant Inventory (key)
| File/Module | Category | Evidence | Recommendation (read-only) |
|---|---|---|---|
| `aether/core/reasoning_service.py:177` | Dormant/Unparsable | SyntaxError (unterminated string); 0 importers | Do not import; requires fix outside read-only scope. |
| `aether/phase_b/__init__.py` + missing modules | Conflict/Broken | Imports 5 non-existent modules; only command_executor.py exists | Broken import chain. |
| `aether/core/plugin_manager.py` | Dormant/Conflict | Self-import line 15; 0 importers | Likely unused. |
| `aether/core/plugin_registry.py` | Dormant | 0 importers | Unused. |
| `aether/core/pointer_event.py` | Structure only | Exported from core.__init__ but 0 other importers | Exported API surface unused internally. |
| `aether/core/startup_validator.py` | Structure only | Defined, no prod importers | Unused validator. |
| `aether/phase_c/*` (6 files) | Dormant | 4 input plugins not wired; 0/low importers | Legacy/unused. |
| `aether/history/service.py`, `aether/presentation/banner.py`, `aether/plugins/history_plugin.py` | Dormant/Structure only | 0 importers found | Unused. |
| `aether/ui/panel/workspace_widget.py` | Dormant | 0 importers | Unused. |
| `aether/workspace/i_*` interfaces | Structure only | 0 importers | Unused interfaces. |
| `aether/panels/memory_panel.py` vs `aether/ui/panel/memory_panel.py` | Conflict/Duplicate | Both exist, different import paths used | Consolidate conceptually (read-only noted). |

## 6) Test Evidence (static)
- Files: 91 test files (tests/ + subdirs). Module-level test funcs: ~1467, classes: ~276.  
- Structural-only (0 funcs/classes): `tests/__init__.py`, `tests/conftest.py`, `tests/contracts/__init__.py`, `tests/phase_a/__init__.py`, `tests/test_dataflow.py`.  
- Script-style tests: `tests/test_shutdown.py`, `tests/test_virtual_cursor.py` have `__main__`.  
- **Doc claims (not verified):** `docs/ACCEPTANCE.md` 1,446; `docs/REVIEW_AUDIT.md` 1,091 passed; `docs/AI_ASSISTANT_BASELINE.md` 691 — treat as document claims only.

## Appendix: Key Evidence Files
- Config: `config/default.yaml`, `config/vision.yaml`, `config/web.yaml`  
- Entry: `aether/__main__.py`, `aether/app.py`, `aether/core/application.py`  
- Commands: `aether/plugins/system_commands_plugin.py`, `aether/core/command_bus.py`  
- GUI: `aether/plugins/gui_plugin.py`, `aether/ui/panel/*`, `aether/panels/*`  
- API: `aether/api/main.py`, `aether/api/routes/*`, `aether/api/server.py`  
- Web: `web/app.js`, `web/index.html`, `web/styles.css`  
- AI: `aether/plugins/ai_plugin.py`, `aether/ai/tools.py`  
- Docs cross-ref: `docs/ACCEPTANCE.md`, `docs/PHASE4_SPEC.md`, `docs/ROADMAP.md`, `docs/REVIEW_AUDIT.md`, `docs/structure-audit.md` (read-only)

**Read-only inventory complete. No files modified.**
