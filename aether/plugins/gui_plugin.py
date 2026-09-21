"""GUIPlugin — thin UI orchestrator.

The plugin's job is DI: build a UIContext from the container, create a
UIShell, and drive its lifecycle (start / tick / stop). All widget
creation, layout, rendering, and teardown live in UIShell; all shared
UI dependencies are bundled in UIContext.

Architecture:
    GUIPlugin ──builds──> UIContext ──> UIShell ──owns──> widgets
    EventBus → OverlayController → OverlayModel → Widgets → HUDManager → Screen
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Optional

from aether.core.plugin import TickablePlugin, PluginMetadata
from aether.core.service_container import ServiceContainer

logger = logging.getLogger("Aether.GUIPlugin")


class GUIPlugin(TickablePlugin):
    """DI composition root. Builds UIContext + UIShell, drives lifecycle."""

    name = "gui_plugin"

    def __init__(self) -> None:
        self._container: Optional[ServiceContainer] = None
        self._event_bus = None
        self._command_bus = None
        self._app = None
        self._overlay_model = None
        self._overlay_controller = None
        self._hud_manager = None
        self._panel_registry = None
        self._workspace_manager = None
        self._context = None
        self._shell = None
        self._running = False
        self._boot_time = time.time()
        self._is_vision_mode = False

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="GUI", version="3.0", category="ui",
            description="Vision HUD overlay with EventBus-driven state"
        )

    def initialize(self, container: ServiceContainer) -> None:
        self._container = container
        self._command_bus = container.resolve("command_bus")
        self._event_bus = container.resolve("event_bus")

        # Register palette-driven UI commands
        self._command_bus.register_handler("ui.panel.focus", self._handle_panel_focus)
        self._command_bus.register_handler("ui.panel.toggle", self._handle_panel_toggle)
        self._command_bus.register_handler("ui.layout.load", self._handle_layout_load)

        # Camera commands
        self._command_bus.register_handler("ui.camera.toggle", self._handle_camera_toggle)
        self._command_bus.register_handler("ui.camera.show", self._handle_camera_show)
        self._command_bus.register_handler("ui.camera.hide", self._handle_camera_hide)
        self._command_bus.register_handler("ui.camera.mode.background", lambda c: self._handle_camera_mode(c, "background"))
        self._command_bus.register_handler("ui.camera.mode.pip", lambda c: self._handle_camera_mode(c, "pip"))
        self._command_bus.register_handler("ui.camera.mode.minimal", lambda c: self._handle_camera_mode(c, "minimal"))
        self._command_bus.register_handler("ui.camera.mode.hidden", lambda c: self._handle_camera_mode(c, "hidden"))

        # UI-1: Shell show / hide commands
        self._command_bus.register_handler("ui.shell.show", lambda c: self.show_ui())
        self._command_bus.register_handler("ui.shell.hide", lambda c: self.hide_ui())
        self._command_bus.register_handler("ui.shell.toggle", lambda c: self.toggle_ui())
        self._command_bus.register_handler("ui.shell.is_visible", lambda c: self.is_ui_visible())

        # Detect vision mode from config
        config = container.resolve("config") if container.has("config") else None
        if config:
            self._is_vision_mode = config.get("app.mode", "") == "vision"

        # Create overlay model
        from aether.ui.overlay_model import OverlayModel
        self._overlay_model = OverlayModel()

        # Register overlay model in DI container for other plugins
        container.register_instance("overlay_model", self._overlay_model)

        # Create overlay controller (subscribes to EventBus)
        from aether.ui.overlay_controller import OverlayController
        self._overlay_controller = OverlayController(self._event_bus, self._overlay_model)

        # Create HUD manager
        from aether.ui.hud_manager import HUDManager
        self._hud_manager = HUDManager()

        # Create PanelRegistry and register workspace panels
        from aether.ui.panel.panel_registry import PanelRegistry
        from aether.ui.panel.panel_info import PanelInfo
        from aether.panels.memory_panel import MemoryPanel

        self._panel_registry = PanelRegistry(event_bus=self._event_bus)

        # Camera panel (existing, uses FrameBroker)
        self._panel_registry.register(PanelInfo(
            id="camera_panel", type="camera",
            label="Camera Feed",
            x=0, y=0, w=1920, h=540,
            z_index=0, visible=True,
        ))

        # Memory panel (view-only, dispatches commands + subscribes to events)
        self._memory_panel = MemoryPanel(x=0, y=560, width=950, height=520)
        self._memory_panel.wire_services(self._command_bus, self._event_bus)
        self._panel_registry.register(PanelInfo(
            id="memory", type="memory",
            label="Memory",
            x=0, y=560, w=950, h=520,
            z_index=10, visible=True,
            widget=self._memory_panel,
        ))

        # AI Chat panel (real widget, created by factory)
        self._panel_registry.register(PanelInfo(
            id="ai_chat", type="ai_chat",
            label="AI Chat",
            x=970, y=560, w=950, h=520,
            z_index=10, visible=True,
        ))

        # Tasks panel (real widget, created by factory)
        self._panel_registry.register(PanelInfo(
            id="tasks", type="tasks",
            label="Tasks",
            x=0, y=1100, w=950, h=460,
            z_index=10, visible=True,
        ))

        # Dashboard panel (real widget, created by factory)
        self._panel_registry.register(PanelInfo(
            id="dashboard", type="dashboard",
            label="Dashboard",
            x=970, y=1100, w=950, h=460,
            z_index=10, visible=True,
        ))

        # Register PanelRegistry in DI container
        container.register_instance("panel_registry", self._panel_registry)

        # NotificationManager — DI service, EventBus aggregator
        from aether.ui.panel.notification_manager import NotificationManager
        self._notification_manager = NotificationManager(self._event_bus)
        container.register_instance("notification_manager", self._notification_manager)

        # WorkspaceManager — layout persistence (needed by palette + shell)
        from aether.workspace.workspace_manager import WorkspaceManager
        self._workspace_manager = WorkspaceManager(self._panel_registry)
        container.register_instance("workspace_manager", self._workspace_manager)

        # Register camera commands in CommandRegistry (for palette discovery)
        self._register_camera_commands(container)

        # Build the single UIContext bundle handed to the UIShell + widgets
        from aether.ui.ui_context import UIContext
        self._context = UIContext.from_container(
            container,
            overlay_model=self._overlay_model,
            overlay_controller=self._overlay_controller,
            hud_manager=self._hud_manager,
        )

        logger.info("GUIPlugin initialized (vision=%s) — %d panels registered",
                    self._is_vision_mode, self._panel_registry.panel_count())

    def start(self) -> None:
        try:
            from PySide6.QtWidgets import QApplication
            self._app = QApplication.instance() or QApplication(sys.argv)
            self._app.setQuitOnLastWindowClosed(False)

            # UI-0: background-capable runtime — window stays hidden unless
            # config explicitly asks for it. Core/AI/EventBus/Memory/Vision
            # are unaffected by UI visibility.
            show_window = False
            if self._context is not None and self._context.config is not None:
                show_window = bool(self._context.config.get("gui.start_visible", False))

            from aether.ui.ui_shell import UIShell
            self._shell = UIShell(self._context)
            self._shell.build(app=self._app, vision_mode=self._is_vision_mode, show_window=show_window)

            self._running = True
            logger.info("GUIPlugin UI started (visible=%s)", show_window)
        except ImportError:
            logger.warning("PySide6 not available, running headless")
            self._running = True
        except Exception as e:
            logger.exception("GUIPlugin start failed: %s", e)

    # ── Lifecycle ───────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        if self._app and self._running and self._shell is not None:
            self._shell.update()

    def stop(self) -> None:
        self._running = False
        if self._shell is not None:
            self._shell.shutdown()

    def shutdown(self) -> None:
        self.stop()
        logger.info("GUIPlugin shutdown")

    # ── Command Handlers ─────────────────────────────────────────────

    def _handle_panel_focus(self, command) -> dict:
        """Focus a panel (palette / command entry)."""
        panel_id = command.params.get("panel_id", "")
        if not panel_id:
            return {"message": "Usage: ui.panel.focus panel_id=<id>"}
        if self._panel_registry and self._panel_registry.focus_panel(panel_id):
            return {"message": f"Focused panel '{panel_id}'"}
        return {"message": f"Panel '{panel_id}' not found"}

    def _handle_panel_toggle(self, command) -> dict:
        """Toggle a panel's visibility (palette / command entry)."""
        panel_id = command.params.get("panel_id", "")
        if not panel_id:
            return {"message": "Usage: ui.panel.toggle panel_id=<id>"}
        if self._panel_registry and self._panel_registry.toggle_panel(panel_id):
            state = "visible" if self._panel_registry.get(panel_id).visible else "hidden"
            return {"message": f"Panel '{panel_id}' {state}"}
        return {"message": f"Panel '{panel_id}' not found"}

    def _handle_layout_load(self, command) -> dict:
        """Load a saved layout (palette / command entry)."""
        name = command.params.get("name", "")
        if not name:
            return {"message": "Usage: ui.layout.load name=<layout>"}
        if self._workspace_manager and self._workspace_manager.load_layout(name):
            return {"message": f"Loaded layout '{name}'"}
        return {"message": f"Layout '{name}' not found"}

    # ── Camera Commands ───────────────────────────────────────────

    def _handle_camera_toggle(self, command) -> dict:
        if self._shell is None:
            return {"message": "Shell not ready"}
        self._shell.toggle_camera()
        mode = self._shell.camera_state.mode.value if self._shell.camera_state else "unknown"
        return {"message": f"Camera → {mode}"}

    def _handle_camera_show(self, command) -> dict:
        if self._shell is None:
            return {"message": "Shell not ready"}
        self._shell.show_camera()
        return {"message": "Camera shown"}

    def _handle_camera_hide(self, command) -> dict:
        if self._shell is None:
            return {"message": "Shell not ready"}
        self._shell.hide_camera()
        return {"message": "Camera hidden"}

    def _handle_camera_mode(self, command, mode_str: str) -> dict:
        if self._shell is None:
            return {"message": "Shell not ready"}
        self._shell.set_camera_mode(mode_str)
        return {"message": f"Camera mode → {mode_str}"}

    # ── UI-1: Shell show / hide commands ────────────────────────────

    def show_ui(self) -> dict:
        """Show the shell window at runtime."""
        if self._shell is None:
            return {"message": "Shell not ready"}
        self._shell.show()
        return {"message": "UI shown"}

    def hide_ui(self) -> dict:
        """Hide the shell window without shutdown."""
        if self._shell is None:
            return {"message": "Shell not ready"}
        self._shell.hide()
        return {"message": "UI hidden"}

    def toggle_ui(self) -> dict:
        """Toggle shell window visibility."""
        if self._shell is None:
            return {"message": "Shell not ready"}
        self._shell.toggle()
        state = "visible" if self._shell.is_visible else "hidden"
        return {"message": f"UI toggled to {state}"}

    def is_ui_visible(self) -> dict:
        """Query current shell window visibility."""
        if self._shell is None:
            return {"message": "Shell not ready"}
        return {"message": "visible" if self._shell.is_visible else "hidden"}

    def _register_camera_commands(self, container) -> None:
        """Register camera commands in CommandRegistry (for palette + voice)."""
        if not container.has("command_registry"):
            return
        try:
            from aether.core.command_registry import CommandInfo
            registry = container.resolve("command_registry")
            cmds = [
                CommandInfo("ui.camera.toggle", "Toggle camera between PiP and background", "ui"),
                CommandInfo("ui.camera.show", "Show camera feed", "ui"),
                CommandInfo("ui.camera.hide", "Hide camera feed", "ui"),
                CommandInfo("ui.camera.mode.background", "Camera: full-screen background", "ui"),
                CommandInfo("ui.camera.mode.pip", "Camera: picture-in-picture", "ui"),
                CommandInfo("ui.camera.mode.minimal", "Camera: minimal PiP", "ui"),
                CommandInfo("ui.camera.mode.hidden", "Camera: hidden", "ui"),
                CommandInfo("ui.shell.show", "Show the Aether UI window", "ui"),
                CommandInfo("ui.shell.hide", "Hide the Aether UI window", "ui"),
                CommandInfo("ui.shell.toggle", "Toggle Aether UI window visibility", "ui"),
                CommandInfo("ui.shell.is_visible", "Check if Aether UI window is visible", "ui"),
            ]
            for cmd in cmds:
                registry.register(cmd)
            logger.info("Camera + shell commands registered in CommandRegistry")
        except Exception:
            logger.debug("Could not register camera commands in CommandRegistry")
