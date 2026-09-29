# Structure Audit Report — `D:\3CS\5Aether` (2026-09-29)

> READ-ONLY audit. No files were modified, moved, deleted, or created during the audit. No tests were executed.

## Context: two tracks

This audit belongs to the **Engineering track** (foundation / hygiene). It runs alongside the **Product track** (Prototype P0 → Demo: AI Conversation → Memory → Capability → Agent → Vision → Demo). The two tracks proceed in parallel so that cleanup never blocks prototype progress and prototype work never bypasses hygiene gates.

```text
ENGINEERING TRACK          PRODUCT TRACK
Audit                      Prototype P0
  ↓                             ↓
UI-2                       AI Conversation
  ↓                             ↓
Structure Cleanup            Memory
  ↓                             ↓
...                        Capability → Agent → Vision → Demo
```

Clean structure ≠ architectural rewrite. No interface, EventBus, CommandBus, or lifecycle changes are part of cleanup.

## 1. Current tree summary

`aether/` has 22 top-level entries. Sizes that matter: `core/` 27 files, `ui/` 23, `plugins/` 16, `interaction/` 16 (all untracked), `memory/` 7, `panels/` 3 (all untracked), `phase_c/` 7 (legacy input, untouched), `phase_d/` 5, `vision/` 6, `workspace/` 5, `services/` 2 (untracked), `presentation/` 2, `domain/` 5, `history/` 2, `ai/` 9. `config/`: 7 files + `workspaces/` (1 file). `tests/`: ~51 files + `contracts/` (6) + `phase_a/` (8). Root has live clutter: `profile_results.txt`, `yolov8n.pt`, `main.py`, `start.py`, `aether.egg-info/`, `.pytest_cache/`.

## 2. Git classification (18 modified + 79 untracked)

**UI-2 bucket = 0 files.** Per locked scope (`gui_plugin.py` +~60 hotkey lines, `test_ui_lifecycle.py` +12 tests, nothing else), no dirty file matches — UI-2 is not present in the tree. Correct.

| Bucket | Files |
|---|---|
| Current stable architecture | `adaptive_scheduler`, `event_bus_v2`, `plugin` (+start/stop defaults), `profiler`, `camera_plugin` (+is_ready), `vision/plugins` (+is_ready), `hud_manager`, `performance_hud`, `system_commands_plugin` (+494 cmd expansion), `phase_a/test_boot`, `test_virtual_cursor`, `performance_plugin` |
| Future feature (wired, active) | `memory/__init__`, `ai_plugin` (+AIWorker), `memory_plugin` (115→352 lines), `camera_widget`, `overlay_model`, `overlay_widget`, `ai_worker`, `boot_profiler`, `startup_validator`, `interaction/` ×16, `memory/{manager,models,schema,sqlite_repository,seed_data}`, `panels/` ×3, `services/` ×2, `ui/interaction_bridge`, `gesture_plugin`, `interaction_plugin`, `config/{gesture,memory}.yaml`, `workspaces/hand.yaml`, `data/layouts/hand_default.json`, `data/themes/` ×2, 29 future test files |
| Runtime/generated artifact | `aether/data/layouts/` ×3 + `aether/data/ui/camera_pip.json`, `data/memory.db` (254 KB live SQLite), `tests/_test_shutdown/`, `tests/debug_boot_profiler.py`, `tests/debug_bp2.py` (debug scripts, not collected tests) |
| Legacy (dormant) | `aether/memory/service.py` (zero prod importers; superseded), `phase_b/` bridge (untouched) |
| Duplicate/obsolete candidate | `config/test.yaml` (Phase-A stub, no loader reference), `config/desktop.yaml` (no `plugins:` key, not bootable — help-text reference only) |
| Needs manual review | `application.py` (Tickable guard removed → start/stop on ALL plugins; hard untracked `boot_profiler` import), `performance_snapshot.py` (no importer found), `presentation/__init__.py` (docstring-only, banner committed without it), duplicate `memory.*` registration (`system_commands_plugin` stub vs `memory_plugin` real — overwrite order = plugin load order) |

Note: earlier session counts (20 modified/55 untracked) predate `00d1e41` + profile-run artifacts; the fresh numbers above govern.

## 3. Focus inspection highlights

- **`system_commands_plugin.py`**: HEAD had system/cli/vision/memory/cursor basics; working tree adds panel/layout/theme/interaction commands + `system.boot.profile`. Wired (both configs, tested). Risk is only the `memory.*` duplicate.
- **`memory_plugin.py`**: HEAD was in-memory demo; working tree is `MemoryManager(db)+MemoryService` facade, 7 commands, vision auto-store TTL 3600. The real Memory Core — wired, tested.
- **`interaction/` ×16**: actively wired via `interaction_plugin` (both configs) + `gesture_plugin` (vision) + `startup_validator`. Track immediately; not obsolete.
- **`memory/` ×5**: `Manager→SQLiteRepository→data/memory.db` is the only storage path; `service.py` is the dead predecessor.
- **`panels/`**: `memory_panel` imported by `GUIPlugin`; placeholder types referenced by `hand.yaml`. Active UI.
- **`presentation/`**: `banner.py` has **zero importers** (`__main__` uses its own BANNER, `application` logs instead). Dormant identity asset — wire or leave, don't delete unilaterally.
- **`services/memory_service.py`**: active facade, self-declares superseding `memory/service.py` — corroborates the legacy call.
- **Configs**: only `default.yaml`/`vision.yaml` boot; `gesture.yaml`/`ai.yaml` are CWD-relative direct-loads (fragile, §9); `test.yaml`/`desktop.yaml` dormant.
- **`aether/data/` + `data/`**: runtime writes (`last*.json`, `camera_pip.json`, `memory.db`) mixed with seeds (`hand_default.json`, themes). `.gitignore` covers neither `*.db` nor these JSONs — DB/layouts currently leak as untracked.

## 4. Commit `00d1e41` audit (no revert)

| File | Intentional (a) | Swept drift (b) | Verdict |
|---|---|---|---|
| `README.md`, `aether/__init__.py` | version strings only | — | remain |
| `banner.py` (new, 118 lines) | default `version="1.0.0"` param only | whole presentation layer, **unwired** | remain as dormant asset; wire-or-leave is a later decision |
| `default.yaml` | version + `mode: vision` | plugin-list rewrite, `memory:`/`ai:`/extended `gui:` sections | **remain** — live boot config; profile run + 921 tests executed against it |
| `vision.yaml` | version only | `interaction/memory/ai` plugins, gesture-plugin swap | **remain** — same reason |

Nothing in `00d1e41` requires revert. The swept changes are active/required; the only idle piece is `banner.py`.

## 5. Proposed target structure

```text
aether/
  core/          runtime/lifecycle/buses (EventBus, CommandBus, Application,
                 ServiceContainer, PluginBase/Loader, Profiler, FrameBroker)
  ai/            reasoning/context/intent (worker, services — existing)
  memory/        Memory Core (manager, models, schema, sqlite_repository,
                 seed_data; REMOVE service.py legacy → see §8)
  vision/        perception (existing; phase_d/ folds in later, not now)
  capabilities/  (FUTURE home, not this cleanup) tool/capability-gate code
  plugins/       integration/orchestration only (all 16 incl. gesture,
                 interaction, performance)
  interaction/   input pipeline (stays; already well-factored, one-way imports)
  ui/            presentation (shell, context, widgets; panels/ MERGES here
                 or stays as ui-adjacent package — decision point, §10)
  services/      application facades (memory_service; stays)
  presentation/  boot identity (banner; stays dormant until wired)
  config/        (loader only — already there)
  workspace/     workspace/layout managers (stays)
config/          boot configs (default, vision) + feature fragments
                 (gesture, memory, ai) + workspaces/
data/            SINGLE canonical runtime+seed dir (resolve split-brain, §9)
tests/           mirror source layout (see §10)
```

## 6. Migration map (move-only candidates)

| Current | Proposed | Reason / import impact / risk |
|---|---|---|
| `aether/panels/*` | `aether/ui/panels/*` (or keep + document) | Single presentation home; note duality with `ui/panel/*` widgets — **do not merge the two panel systems**, only relocate. Impact: `gui_plugin.py:102` lazy import + `hand.yaml` type refs (no path refs — safe). Risk: LOW-MED |
| `aether/services/*` | keep (already correct layer) | No move; just track. Risk: NONE |
| `aether/interaction/*` | keep package as-is | Internally clean one-way graph; 3 external importers use full paths. Risk: NONE (track only) |
| `aether/memory/service.py` | delete (after deprecation check) | Zero prod importers; superseded per `services/memory_service` docstring. Impact: none found. Risk: LOW (verify once more at cleanup time) |
| `config/test.yaml`, `config/desktop.yaml` | `config/archive/` or delete | Non-bootable. Impact: help-text cites `desktop.yaml` — update string. Risk: LOW |
| `tests/debug_*.py` | `scripts/debug/` or delete | Not collected as tests; superseded by real perf/dependency tests. Risk: LOW |
| `data/` ↔ `aether/data/` | canonicalize ONE dir | Split-brain confirmed (§9). Requires manager default updates + file migration. Risk: MED-HIGH — separate sub-phase |
| `profile_results.txt`, `*.db`, `last*.json`, `_test_shutdown/` | `.gitignore`, never track | Runtime exhaust. Risk: NONE |

## 7. DO-NOT-MOVE list

`EventBus`/`event_type`, `CommandBus`/`command`/`command_result`/`result_pipeline`/`command_registry`, `Application` boot→tick→shutdown (+ legacy `app.py` headless path), `ServiceContainer`/`IService`, `PluginBase`/`TickablePlugin`/`PluginMetadata`/`PluginLoader`, `UIShell`/`UIContext` (sole UI injection point, built only by `GUIPlugin`), `WorkspaceManager`/`LayoutManager`/`ThemeManager`/`CameraState`/`MemoryManager` ownership. Plugin discovery is **config-list-driven, no directory scan** — every `module:` string in both YAMLs must move in lockstep with its file.

## 8. Duplicate/obsolete candidates (identify only)

1. `memory/service.py` vs `services/memory_service.py` — old in-memory vs SQLite facade; evidence: zero importers of the former.
2. `system_commands_plugin` `memory.*` stubs vs `memory_plugin` real handlers — load-order overwrite; harmless today, resolve ownership in cleanup.
3. `panels/memory_panel.py` vs `ui/panel/memory_*.py` — two panel systems for the same concern; do not conflate, decide coexistence explicitly.
4. `phase_c/` input plugins vs `interaction/`+`gesture_plugin` pipeline — old vs new input; `phase_c` untouched, likely superseded but still needs a live-vs-dead check at cleanup.
5. `config/desktop.yaml` / `test.yaml`, `tests/debug_*` — as §6.

## 9. Risks (top)

- **Workspace/layout split-brain**: `config/workspaces/` (real file) vs `WorkspaceManager.WORKSPACES_DIR` (`aether/config/...`, empty); `data/layouts/` vs `aether/data/layouts/`. Auto-`mkdir` masks missing dirs → silent wrong-dir operation. Canonicalize first, migrate with compat args, assert `hand.yaml`+`hand_default.json` resolvable at boot.
- **CWD-relative loads**: `gesture.yaml`/`ai.yaml` via bare `Path("config/...")`, app defaults `config/default.yaml`, profiler `profile_results.txt`. Moving files or running outside root → silent fallback defaults. Anchor to `PROJECT_ROOT` (as `__main__` does) during cleanup.
- **Config-move lockstep**: any plugin-file move without YAML `module:` update = silent plugin absence (fatal only under `--strict-plugins`; recommend strict boot in CI for the cleanup PR).
- **Cycle introduction**: one-way rules hold today (plugins/ui→domain, never reverse; no package-root imports; lazy `gui_plugin→memory_panel`). Enforce: no `aether.ui` imports inside `interaction/`/`memory/`, keep submodule direct paths.
- **Test coupling**: all absolute `aether.*` imports — any source move needs matching test edits; `test_plugin_loader._MOD` is path-bound to its own file.
- **Data loss**: `memory.db` unignored + auto-created; back up before moves, never commit live DB.
- **Model weights**: `*.pt` ignored but vision config points at them — document fetch step.

## 10. Recommended cleanup phases

```text
Phase C0  .gitignore hygiene (*.db, aether/data/, data/layouts/last*.json,
          tests/_test_shutdown/) + track seed templates — 1 commit
Phase C1  Track active wired code as-is (interaction, panels, services,
          memory×5, 3 plugins, gesture/memory YAMLs, hand.yaml, seeds)
          + importer verification — 1 commit, tests gate
Phase C2  panels/ placement decision + legacy removals
          (memory/service.py, archive test/desktop YAMLs, debug scripts)
          + memory.* ownership resolution — 1 commit, tests gate
Phase C3  Path canonicalization (workspaces/layouts/themes dirs,
          CWD-relative anchors, strict-plugins CI) — 1 commit, boot gate
```

Open decisions: (a) `panels/` merge destination vs keep; (b) canonical runtime-data dir (`data/` vs `aether/data/`); (c) wire `banner.py` into boot or leave dormant; (d) `phase_c/` disposition. None block UI-2.

## Validation footer

- Files inspected: ~120 (tree, 18 diffs, 79 untracked listings, ~40 headers/import blocks, both boot configs + 4 fragments, `.gitignore`, `pyproject`, `__main__`, `application`, loader, managers).
- Files classified: 97 (18 modified + 79 untracked) into the 7 buckets; UI-2 bucket empty as expected.
- Unresolved: `performance_snapshot.py` importer (none found — likely orphan or next-phase helper); `phase_c/` live-vs-dead confirmation; panels-duality coexistence rule.
- Proposed cleanup scope: C0–C3 above, all move/track/ignore-only, zero interface changes.
- Confirmation: no source, config, or test file was modified during the audit. Zero writes performed.
