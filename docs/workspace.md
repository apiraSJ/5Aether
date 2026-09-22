# Aether Workspace Architecture

## Overview

The Workspace system separates two concerns:

| Concept | Responsibility | Storage |
|---------|---------------|---------|
| **Workspace** | What panels exist, startup behavior, panel identity | `config/workspaces/{id}.yaml` |
| **Layout** | Where panels are positioned (geometry, z-order, dock) | `data/layouts/{name}.json` |

A Workspace **owns** a Layout reference but never embeds geometry.

### UIShell Integration

UIShell is the window owner. Workspace and Layout are managed by UIShell via WorkspaceManager:

```text
GUIPlugin ──builds──> UIContext ──> UIShell ──owns──> widgets
                                  │
                                  ├── CameraPanel
                                  ├── PanelRegistry
                                  └── WorkspaceManager (layout save/restore)
```

---

## Workspace vs Layout

### Workspace

A workspace definition describes:

- Available panel IDs and their types
- Default visibility per panel
- Z-index ordering
- Startup commands to run on load
- Reference to default layout name

```yaml
# config/workspaces/hand.yaml
name: "hand"
label: "Hand Workspace"
default_layout: "hand_default"
panels:
  - id: "memory"
    type: "memory"
    visible: true
    z_index: 10
startup_commands:
  - "interaction.cursor.enable"
```

### Layout

A layout stores only geometry:

```json
{
  "name": "hand_default",
  "workspace": "hand",
  "panels": [
    {"id": "memory", "x": 0, "y": 560, "w": 950, "h": 520, "z_index": 10, "visible": true}
  ]
}
```

Layout files live in `data/layouts/`. They are auto-saved on drag-end, resize-end, or explicit save.

---

## Workspace Lifecycle

```
Boot
  │
  ├── GUIPlugin.initialize()
  │     ├── Create PanelRegistry
  │     ├── Register all panels (5 for Hand workspace)
  │     └── Register PanelRegistry in DI container
  │
  ├── GUIPlugin.start()
  │     ├── Create UIShell (builds window + panels)
  │     ├── UIShell.build() → create WorkspaceManager
  │     ├── restore_last() → try loading last_session.json
  │     └── Fallback: load_workspace("hand")
  │
  ├── InteractionPlugin.start()
  │     ├── Resolve PanelRegistry from DI
  │     ├── Create InteractionController
  │     ├── Create InputRouter
  │     └── Create InteractionBridge
  │
  │     ── Interactive use ──
  │     ├── Drag end → WorkspaceManager.save_layout("last_session")
  │     ├── Resize end → WorkspaceManager.save_layout("last_session")
  │     └── Explicit save → WorkspaceManager.save_layout(name)
  │
  └── Shutdown
        └── GUIPlugin.stop() → WorkspaceManager.save_layout("last_session")
```

---

## Interaction State Machine

Generic (target-agnostic) state machine:

```
                    ┌─────────────────────────────────────────────┐
                    │                                             │
                    ▼                                             │
    ┌─────┐  enter  ┌───────┐  click/pinch  ┌──────────┐        │
    │ IDLE│ ──────→ │ HOVER │ ────────────→ │ SELECTED │        │
    └─────┘         └───────┘               └──────────┘        │
      ▲                                    │        │           │
      │                                    │        │           │
      │                              hold+move    edge+pinch    │
      │                                    │        │           │
      │                                    ▼        ▼           │
      │                             ┌──────────┐ ┌──────────┐   │
      │                             │ DRAGGING │ │ RESIZING │   │
      │                             └──────────┘ └──────────┘   │
      │                                    │        │           │
      │                              release    release         │
      │                                    │        │           │
      └────────────────────────────────────┴────────┴───────────┘
            cancel (CLOSED_FIST / Escape)
```

### States

| State | Meaning |
|-------|---------|
| `IDLE` | No interaction in progress |
| `HOVER` | Cursor over a target (panel) |
| `SELECTED` | Target selected (pinch/click) |
| `DRAGGING` | Target being moved (pinch hold + move) |
| `RESIZING` | Target edge being resized (pinch on handle) |

### Transitions

| Trigger | From | To | Event Emitted |
|---------|------|----|---------------|
| Cursor enters target | IDLE | HOVER | — |
| Cursor leaves all targets | HOVER | IDLE | — |
| Click/pinch on target | HOVER | SELECTED | `interaction.selection.changed` |
| Click elsewhere | SELECTED | IDLE | `interaction.selection.changed` |
| Hold + move on selected | SELECTED | DRAGGING | `interaction.drag.started` |
| Drag move update | DRAGGING | DRAGGING | `interaction.drag.updated` |
| Release | DRAGGING | IDLE | `interaction.drag.ended` |
| Pinch on edge handle | SELECTED | RESIZING | `interaction.resize.started` |
| Resize move update | RESIZING | RESIZING | `interaction.resize.updated` |
| Release | RESIZING | IDLE | `interaction.resize.ended` |
| Cancel (Fist/Escape) | any | IDLE | `interaction.drag/resize.ended` + `interaction.selection.changed` |

---

## Event Flow

All user actions follow the same pipeline:

```
User action
    │
    ▼
Panel (view-only)
    │  dispatches Command
    ▼
CommandBus.dispatch(name, params)
    │
    ▼
Plugin._handle_*(command)
    │  calls Service
    ▼
Service / Manager
    │  publishes Event
    ▼
EventBus.publish(type, payload)
    │
    ├── OverlayController → OverlayModel → Widgets re-render
    └── Panel._on_event() → update data → re-render
```

### Generic Interaction Events

| Event | Payload | Emitted When |
|-------|---------|-------------|
| `interaction.selection.changed` | `{target_id, action}` | Target selected/deselected/cancelled |
| `interaction.drag.started` | `{target_id, x, y}` | Drag begins |
| `interaction.drag.updated` | `{target_id, x, y}` | Drag position changes |
| `interaction.drag.ended` | `{target_id, cancelled}` | Drag ends |
| `interaction.resize.started` | `{target_id, x, y}` | Resize begins |
| `interaction.resize.updated` | `{target_id, x, y}` | Resize position changes |
| `interaction.resize.ended` | `{target_id, cancelled}` | Resize ends |

These events are **target-agnostic** — the same events are emitted for panels, cards, nodes, etc.

---

## Focus Rules

- A target gets focus when hovered or selected.
- Focus is exclusive: focusing one target unfocuses all others.
- Focus change emits `panel.focused` (or equivalent for other target types).
- Focus is indicated by a visual ring (2px accent border).
- Focus follows cursor during hover; locks on select; releases on deselect.

---

## Selection Rules

- Selection happens on click/pinch, not hover.
- Only one target can be selected at a time.
- Selected target becomes the target for drag/resize operations.
- Clicking elsewhere deselects. Clicking the same target toggles.
- CLOSED_FIST cancels selection (returns to IDLE).

---

## Drag Lifecycle

1. **Start**: `SELECTED` + pinch hold → `DRAGGING` (records grab offset)
2. **Update**: Every cursor move → calculate delta → apply to target position
3. **End**: Pinch release → finalize position → emit `drag.ended` → save layout
4. **Cancel**: CLOSED_FIST → revert to original position → emit `drag.ended{ cancelled: true }`

Drag data flow:
```
InteractionController.on_drag_start()
    → DragController.start(panel_id, cursor_x, cursor_y)
    → InteractionController._transition(DRAGGING)
    → emit DRAG_STARTED event

InteractionController.on_cursor_move() [while DRAGGING]
    → DragController.update(cursor_x, cursor_y)
    → DragController.apply()
    → emit DRAG_UPDATED event

InteractionController.on_drag_end()
    → DragController.end()
    → emit DRAG_ENDED event
    → GUIPlugin.save_layout("last_session")
```

---

## Resize Lifecycle

1. **Start**: `SELECTED` + pinch on 8px edge → `RESIZING`
2. **Update**: Every cursor move → recalculate geometry → apply
3. **End**: Pinch release → finalize → emit `resize.ended` → save layout
4. **Cancel**: CLOSED_FIST → revert to original geometry

Resize handles (8px from each edge):
```
┌──┬─────────────┬──┐
│  │             │  │
├──┤             ├──┤
│  │   Content   │  │
├──┤             ├──┤
│  │             │  │
└──┴─────────────┴──┘
```

Minimum size: 200×150 pixels.

---

## Z-Order

- Panels with lower z_index render behind panels with higher z_index.
- Floating panels always render above docked panels.
- Selecting a floating panel brings it to the top of its layer.
- Z-order is stored in the layout file.

```
z_index 0:       Camera feed (background)
z_index 10:      Docked panels (memory, AI chat, tasks, dashboard)
z_index 100+:    Floating panels (above docked)
```

---

## Panels — View-Only Contract

Panels in Aether MUST follow these rules:

### Panels MUST:
- Dispatch commands through `CommandBus` for user actions
- Subscribe to events through `EventBus` for data updates
- Be stateless renderers (receive data, display it)
- Implement `IPanel` interface

### Panels MUST NEVER:
- Access repositories, managers, or services directly
- Call `MemoryManager`, `SQLiteRepository`, or similar APIs
- Mutate application state
- Communicate with other panels directly
- Import or resolve service implementations

### Example: MemoryPanel

```python
# CORRECT
class MemoryPanel(AbstractPanel):
    def set_search_query(self, query: str):
        self._command_bus.dispatch(Command(
            name="memory.search", source="memory_panel",
            params={"query": query},
        ))

    def _on_query_completed(self, event):
        records = event.payload.get("records", [])
        self._items = [MemoryPanelItem(**r) for r in records]

# WRONG — never do this
class MemoryPanel(AbstractPanel):
    def set_search_query(self, query: str):
        from aether.memory.memory_manager import MemoryManager
        self._manager = container.resolve("memory_manager")  # NO!
        results = self._manager.search(query)  # NO!
```

---

## Future Architecture: PanelController (Presenter/ViewModel)

In Sprint 1, panels dispatch commands directly. In a future sprint, a
**PanelController** (Presenter) layer will sit between Panel and CommandBus:

```
Panel (View)
    │
    ▼
PanelController (Presenter/ViewModel)
    │
    ├── formats data for panel display
    ├── dispatches commands
    └── subscribes to events
    │
    ▼
CommandBus
```

This allows:
- Same Presenter used by PySide6, Web UI, and XR UI
- Panel is pure Widget (no logic at all)
- Presenter is testable without UI framework
- Unit tests on Presenter, integration tests on pipeline

Not implemented in Sprint 1. Documented here as target architecture.

---

## Architecture Rules (Preserved)

| Rule | Description |
|------|-------------|
| EventBus | Communication backbone — never call services directly |
| FrameBroker | Camera distribution layer — only camera widget subscribes |
| InteractionController | Single interaction state machine — all input goes through it |
| InputRouter | Single input normalization layer — converts all input to uniform events |
| HandController | Produces normalized HandInputEvents with Gesture enum only |
| Plugins | Communicate only through EventBus — no direct method calls |
| Panels | Stateless renderers — dispatch commands, subscribe to events |

---

## Performance Budget

| Metric | Target | Measurement |
|--------|--------|-------------|
| InteractionController.update() | < 1 ms | time.perf_counter() delta |
| Cursor latency (hand → screen) | < 30 ms | Hardware-to-overlay frame count |
| Drag rendering | ≥ 60 FPS | OverlayModel.dirty → paint cycle |
| Layout save frequency | On drag-end, resize-end, or explicit save only | Debounce at GUIPlugin level |
| Hand vs Mouse | Identical code path | Single InteractionController |

---

## WorkspaceManager API

```python
class WorkspaceManager:
    def load_workspace(self, workspace_id: str) -> bool
    def list_workspaces(self) -> List[str]
    def save_layout(self, name: str, description: str = "") -> dict
    def load_layout(self, name: str) -> bool
    def restore_last(self) -> bool
    def list_layouts(self) -> List[str]
    def delete_layout(self, name: str) -> bool
    def current_workspace(self) -> Optional[str]
    def current_layout(self) -> Optional[str]
```

---

## File Locations

```
config/
  workspaces/
    hand.yaml          ← Hand Workspace definition
    vision.yaml        ← Vision Workspace definition (future)
    memory.yaml        ← Memory Workspace definition (future)
    developer.yaml     ← Developer Workspace definition (future)

data/
  layouts/
    hand_default.json  ← Default geometry for Hand Workspace
    last_session.json  ← Auto-saved on shutdown
```

---

## Workspace Presets (Future)

Presets will allow switching workspaces in one click:

- **Vision Workspace**: Camera feed + object detection + hand tracking
- **Memory Workspace**: Memory search + recall + details + graph
- **AI Workspace**: AI chat + command palette + context
- **Developer Workspace**: Timing HUD + plugin list + event log + layout debug

Switching a workspace will:
1. Save current layout
2. Load new workspace definition
3. Show/hide panels as needed
4. Load default layout for new workspace
5. Run startup commands
