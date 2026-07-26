"""
EventType — unified event type enum for the v2 EventBus.

This replaces both:
- v1 core/event_bus.py EventType (69 types, many unused)
- v2 phase_c/event_type.py EventType (25 types, incomplete)

Design principles:
1. One event type per concept (no duplicates with different names)
2. Hierarchical naming: domain.action (e.g., command.executed, vision.hand_detected)
3. Only events that actually flow through the bus are included
4. New events require ADR approval
"""

from __future__ import annotations

from enum import Enum, auto


class EventType(str, Enum):
    """All event types that flow through the v2 EventBus.

    Organized by domain. Each event type maps to a specific payload schema.
    """

    # ── System ──────────────────────────────────────────────────────────────
    SYSTEM_BOOT = "system.boot"
    SYSTEM_READY = "system.ready"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"
    SYSTEM_TICK = "system.tick"

    # ── Command Lifecycle ───────────────────────────────────────────────────
    COMMAND_ISSUED = "command.issued"
    COMMAND_STARTED = "command.started"
    COMMAND_COMPLETED = "command.completed"
    COMMAND_FAILED = "command.failed"
    COMMAND_CANCELLED = "command.cancelled"

    # ── Input (raw, pre-intent) ────────────────────────────────────────────
    INPUT_KEYBOARD = "input.keyboard"
    INPUT_MOUSE = "input.mouse"
    INPUT_HOTKEY = "input.hotkey"
    INPUT_POINTER = "input.pointer"  # Unified pointer event (mouse/hand/XR)
    INPUT_GESTURE = "input.gesture"
    INPUT_VOICE = "input.voice"

    # ── Vision (perception output) ─────────────────────────────────────────
    VISION_CAMERA_STARTED = "vision.camera.started"
    VISION_CAMERA_STOPPED = "vision.camera.stopped"
    VISION_FRAME_READY = "vision.frame.ready"
    VISION_FRAME_PROCESSED = "vision.frame.processed"
    VISION_HAND_DETECTED = "vision.hand.detected"
    VISION_HAND_UPDATED = "vision.hand.updated"
    VISION_HAND_LOST = "vision.hand.lost"
    VISION_HAND_TRACKING = "vision.hand.tracking"
    VISION_OBJECT_DETECTED = "vision.object.detected"
    VISION_OBJECT_TRACKED = "vision.object.tracked"
    VISION_OBJECT_LOST = "vision.object.lost"
    VISION_OBJECT_SELECTED = "vision.object.selected"
    VISION_OBJECT_HOVERED = "vision.object.hovered"
    VISION_CURSOR_MOVED = "vision.cursor.moved"
    VISION_GESTURE_STARTED = "vision.gesture.started"
    VISION_GESTURE_HOLDING = "vision.gesture.holding"
    VISION_GESTURE_ENDED = "vision.gesture.ended"
    VISION_SCENE_UPDATED = "vision.scene.updated"
    VISION_DEPTH_UPDATED = "vision.depth.updated"
    VISION_TRACKING_LOST = "vision.tracking.lost"
    VISION_TRACKING_RECOVERED = "vision.tracking.recovered"

    # ── Intent (resolved from input) ───────────────────────────────────────
    INTENT_RESOLVED = "intent.resolved"
    INTENT_FAILED = "intent.failed"

    # ── Workspace / Layout ─────────────────────────────────────────────────
    WORKSPACE_WINDOW_OPENED = "workspace.window.opened"
    WORKSPACE_WINDOW_CLOSED = "workspace.window.closed"
    WORKSPACE_WINDOW_FOCUSED = "workspace.window.focused"
    WORKSPACE_WINDOW_MOVED = "workspace.window.moved"
    WORKSPACE_WINDOW_RESIZED = "workspace.window.resized"
    WORKSPACE_LAYOUT_CHANGED = "workspace.layout.changed"
    WORKSPACE_THEME_CHANGED = "workspace.theme.changed"

    # ── Notification ───────────────────────────────────────────────────────
    NOTIFICATION_SHOW = "notification.show"
    NOTIFICATION_DISMISS = "notification.dismiss"
    NOTIFICATION_CLICKED = "notification.clicked"

    # ── History / Undo ─────────────────────────────────────────────────────
    HISTORY_RECORD_ADDED = "history.record.added"
    HISTORY_UNDO = "history.undo"
    HISTORY_REDO = "history.redo"

    # ── Memory ─────────────────────────────────────────────────────────────
    MEMORY_STORED = "memory.stored"
    MEMORY_RECALLED = "memory.recalled"
    MEMORY_DELETED = "memory.deleted"

    # ── Task ───────────────────────────────────────────────────────────────
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_COMPLETED = "task.completed"
    TASK_CANCELLED = "task.cancelled"

    # ── Context ────────────────────────────────────────────────────────────
    CONTEXT_CHANGED = "context.changed"
    CONTEXT_APP_CHANGED = "context.app.changed"
    CONTEXT_FOCUS_CHANGED = "context.focus.changed"

    # ── Plugin ─────────────────────────────────────────────────────────────
    PLUGIN_LOADED = "plugin.loaded"
    PLUGIN_UNLOADED = "plugin.unloaded"
    PLUGIN_ERROR = "plugin.error"

    # ── Service ────────────────────────────────────────────────────────────
    SERVICE_STARTED = "service.started"
    SERVICE_STOPPED = "service.stopped"
    SERVICE_ERROR = "service.error"

    # ── Desktop Automation ─────────────────────────────────────────────────
    DESKTOP_APP_LAUNCHED = "desktop.app.launched"
    DESKTOP_APP_CLOSED = "desktop.app.closed"
    DESKTOP_WINDOW_CHANGED = "desktop.window.changed"

    # ── AI ─────────────────────────────────────────────────────────────────
    AI_THINKING_STARTED = "ai.thinking.started"
    AI_THINKING_COMPLETED = "ai.thinking.completed"
    AI_RESPONSE_READY = "ai.response.ready"

    # ── Workflow ───────────────────────────────────────────────────────────
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_STEP_COMPLETED = "workflow.step.completed"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"

    @classmethod
    def from_v1(cls, v1_type: str) -> "EventType":
        """Map a v1 event type string to v2 EventType.

        Used during migration for backward compatibility.
        """
        _V1_TO_V2_MAP = {
            # System
            "system_start": cls.SYSTEM_BOOT,
            "system_startup": cls.SYSTEM_BOOT,
            "system_shutdown": cls.SYSTEM_SHUTDOWN,
            "system_error": cls.SYSTEM_ERROR,
            # UI
            "ui_open": cls.WORKSPACE_WINDOW_OPENED,
            "ui_close": cls.WORKSPACE_WINDOW_CLOSED,
            "ui_open_requested": cls.WORKSPACE_WINDOW_OPENED,
            "ui_close_requested": cls.WORKSPACE_WINDOW_CLOSED,
            "ui_panel_switch": cls.WORKSPACE_LAYOUT_CHANGED,
            "ui_update": cls.WORKSPACE_LAYOUT_CHANGED,
            "panel_show_requested": cls.WORKSPACE_WINDOW_OPENED,
            "panel_hide_requested": cls.WORKSPACE_WINDOW_CLOSED,
            "mode_changed": cls.CONTEXT_CHANGED,
            # Input
            "input_keyboard": cls.INPUT_KEYBOARD,
            "input_mouse": cls.INPUT_MOUSE,
            "input_hotkey": cls.INPUT_HOTKEY,
            # Command
            "command_execute": cls.COMMAND_ISSUED,
            "command_complete": cls.COMMAND_COMPLETED,
            "command_failed": cls.COMMAND_FAILED,
            # Tasks
            "task_created": cls.TASK_CREATED,
            "task_updated": cls.TASK_UPDATED,
            "task_completed": cls.TASK_COMPLETED,
            "task_cancelled": cls.TASK_CANCELLED,
            # Plugins
            "plugin_started": cls.PLUGIN_LOADED,
            "plugin_stopped": cls.PLUGIN_UNLOADED,
            # Vision
            "hand_detected": cls.VISION_HAND_DETECTED,
            "hand_lost": cls.VISION_HAND_LOST,
            "object_detected": cls.VISION_OBJECT_DETECTED,
            "object_tracked": cls.VISION_OBJECT_TRACKED,
            "object_lost": cls.VISION_OBJECT_LOST,
            "gesture_recognized": cls.INPUT_GESTURE,
            "gesture_stable": cls.INPUT_GESTURE,
            "gesture_lost": cls.INPUT_GESTURE,
            "help_requested": cls.INTENT_RESOLVED,
            # Context
            "context_changed": cls.CONTEXT_CHANGED,
            "context_app_changed": cls.CONTEXT_APP_CHANGED,
            # Memory
            "memory_store": cls.MEMORY_STORED,
            "memory_recall": cls.MEMORY_RECALLED,
            # Menu
            "menu_open": cls.WORKSPACE_WINDOW_OPENED,
            "menu_close": cls.WORKSPACE_WINDOW_CLOSED,
            "menu_item_selected": cls.COMMAND_ISSUED,
            # Status
            "status_requested": cls.INTENT_RESOLVED,
        }
        return _V1_TO_V2_MAP.get(v1_type, cls.SYSTEM_ERROR)
