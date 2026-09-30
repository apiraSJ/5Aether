"""Demo memory seed data for first-boot seeding.

Architecture:
    MemoryManager.seed_if_empty() → reads DEMO_MEMORIES → repository.store()

These records are demo content only — they give the Memory panel real,
searchable data on first boot so the product is usable immediately.
Once a user stores their own semantic memory, seeding stops (the store
is no longer empty).
"""

from __future__ import annotations

DEMO_MEMORIES = [
    {
        "title": "Sprint 1.5 infrastructure complete",
        "summary": "Core Aether foundation verified: plugins, EventBus, commands, workspace layout.",
        "content": (
            "Aether's Sprint 1.5 milestone is complete. The plugin architecture, "
            "EventBus v2, command registry, and workspace layout persistence were all "
            "implemented and verified. The system boots reliably with a 5-layer HUD "
            "and remembers panel positions across restarts."
        ),
        "tags": ["sprint", "infrastructure", "foundation"],
        "importance": 4,
        "pinned": False,
        "source": "workspace",
        "age_days": 9,
    },
    {
        "title": "Camera calibration successful",
        "summary": "Vision camera calibrated with 0.97 accuracy for hand and object tracking.",
        "content": (
            "The vision camera finished calibration with 0.97 accuracy. Hand tracking "
            "and object detection now use the calibrated intrinsics, improving 3D "
            "position estimates for the spatial memory store."
        ),
        "tags": ["camera", "calibration", "vision", "hardware"],
        "importance": 3,
        "pinned": False,
        "source": "vision",
        "age_days": 8,
    },
    {
        "title": "Hand tracking online",
        "summary": "Hand tracking running at 30 FPS with 21 landmarks per hand.",
        "content": (
            "Hand tracking is online at 30 FPS with 21 landmarks per hand. Pinch, "
            "drag, and swipe gestures are recognized reliably, driving the virtual "
            "cursor and workspace interactions."
        ),
        "tags": ["hand", "tracking", "vision"],
        "importance": 3,
        "pinned": False,
        "source": "vision",
        "age_days": 7,
    },
    {
        "title": "Gesture plugin initialized",
        "summary": "Gesture plugin loaded — pinch, drag, swipe, and hold all active.",
        "content": (
            "The gesture plugin initialized successfully. Pinch, drag, swipe, and "
            "hold gestures are registered with the interaction layer and mapped to "
            "workspace actions like panel focus, move, and resize."
        ),
        "tags": ["gesture", "interaction"],
        "importance": 2,
        "pinned": False,
        "source": "interaction",
        "age_days": 6,
    },
    {
        "title": "Layout persistence verified",
        "summary": "Panel geometry survives app restarts via layout files.",
        "content": (
            "Layout persistence was verified end-to-end. Moving and resizing panels "
            "saves their geometry immediately, and reopening Aether restores every "
            "panel to its previous position."
        ),
        "tags": ["layout", "persistence", "workspace"],
        "importance": 3,
        "pinned": False,
        "source": "workspace",
        "age_days": 5,
    },
    {
        "title": "Workspace restored",
        "summary": "Workspace restored from last session on boot.",
        "content": (
            "On the last boot, the workspace restored the previous session layout "
            "automatically. All panels returned to their saved positions with the "
            "same visibility and focus state."
        ),
        "tags": ["workspace", "restore"],
        "importance": 2,
        "pinned": False,
        "source": "workspace",
        "age_days": 4,
    },
    {
        "title": "Memory system online",
        "summary": "SQLite memory core running with WAL, FTS5, and R-Tree indexes.",
        "content": (
            "The memory system is online. SQLite is running in WAL mode with FTS5 "
            "full-text search and an R-Tree index for spatial queries. Semantic, "
            "episodic, spatial, and working memory tables are all live."
        ),
        "tags": ["memory", "core", "sqlite"],
        "importance": 3,
        "pinned": False,
        "source": "system",
        "age_days": 3,
    },
    {
        "title": "Vision architecture",
        "summary": "5-layer HUD: camera, vision overlay, workspace, HUD, debug.",
        "content": (
            "The vision HUD is organized into five layers: 0 Camera feed, "
            "1 Vision overlay (objects, hands, cursor), 2 Workspace panels "
            "(real Qt widgets), 3 HUD widgets, and 4 Debug tools."
        ),
        "tags": ["architecture", "vision", "hud"],
        "importance": 5,
        "pinned": True,
        "source": "workspace",
        "age_days": 12,
    },
    {
        "title": "Workspace design",
        "summary": "WindowManager owns focus, z-order, docking, and persistence.",
        "content": (
            "The workspace design centers on the WindowManager: it owns the focus "
            "stack, z-order, docking, and layout persistence while panel widgets "
            "stay thin and never initiate layout changes themselves."
        ),
        "tags": ["architecture", "workspace", "design"],
        "importance": 4,
        "pinned": True,
        "source": "workspace",
        "age_days": 11,
    },
    {
        "title": "AI roadmap",
        "summary": "Planned: memory search, chat, tasks, voice/gesture, AI layout manager.",
        "content": (
            "The AI roadmap: functional memory search and recent/pinned views, a "
            "chat panel (stub first, then real LLM), real tasks, dashboard metrics, "
            "voice and gesture control, and finally an AI layout manager that "
            "arranges panels by context."
        ),
        "tags": ["roadmap", "ai", "planning"],
        "importance": 5,
        "pinned": True,
        "source": "system",
        "age_days": 10,
    },
]

SUGGESTIONS = ["gesture", "camera", "workspace", "memory", "vision"]
