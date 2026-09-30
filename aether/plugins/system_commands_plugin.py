"""SystemCommandPlugin — registers system-level commands in CommandRegistry.

Commands registered:
  - system.help [category]     — show help
  - system.status              — system status
  - system.plugins             — list plugins
  - system.commands            — list all commands
  - system.ping                — health check
  - system.shutdown            — shutdown aether
  - cli.history                — command history
  - cli.clear                  — clear screen
  - system.panel.show <id>     — show a panel
  - system.panel.hide <id>     — hide a panel
  - system.panel.toggle <id>   — toggle panel visibility
  - system.panel.list          — list all panels
  - system.layout.save <name>  — save current layout
  - system.layout.load <name>  — load a layout
  - system.layout.list         — list available layouts
  - system.layout.delete <name>— delete a layout
  - system.layout.reset        — reset to defaults
  - system.theme.apply <name>  — apply a theme
  - system.theme.list          — list available themes
"""

from __future__ import annotations

import logging
import os
import platform
import time
from typing import Any

from aether.core.command import Command
from aether.core.command_registry import CommandRegistry, CommandInfo
from aether.core.plugin import PluginBase, PluginMetadata
from aether.core.service_container import ServiceContainer

logger = logging.getLogger("Aether.SystemCommands")

_SYSTEM_COMMANDS = [
    CommandInfo(
        name="system.help",
        description="Show help for a command or category",
        category="system",
        aliases=("h", "?"),
        params_help="[category]",
        examples=("help", "help memory", "help vision"),
    ),
    CommandInfo(
        name="system.status",
        description="Show system status",
        category="system",
        aliases=("st",),
    ),
    CommandInfo(
        name="system.plugins",
        description="List loaded plugins",
        category="system",
    ),
    CommandInfo(
        name="system.commands",
        description="List all registered commands",
        category="system",
    ),
    CommandInfo(
        name="system.ping",
        description="Health check",
        category="system",
        aliases=("p",),
    ),
    CommandInfo(
        name="system.shutdown",
        description="Shutdown Aether",
        category="system",
        aliases=("quit", "exit", "q"),
    ),
    CommandInfo(
        name="cli.history",
        description="Show command history",
        category="cli",
    ),
    CommandInfo(
        name="cli.clear",
        description="Clear the screen",
        category="cli",
        aliases=("cls",),
    ),
    CommandInfo(
        name="vision.scan",
        description="Scan the room with camera",
        category="vision",
    ),
    CommandInfo(
        name="memory.recall",
        description="Find a remembered object",
        category="memory",
        params_help="<query>",
        examples=("find phone", "where is my keys"),
    ),
    CommandInfo(
        name="memory.remember",
        description="Remember an object and its location",
        category="memory",
        params_help="<name> [at <location>]",
        examples=("remember bottle", "save keys at desk"),
    ),
    CommandInfo(
        name="memory.forget",
        description="Forget an object from memory",
        category="memory",
        params_help="<name>",
        aliases=("delete", "remove"),
    ),
    CommandInfo(
        name="memory.list",
        description="List all remembered objects",
        category="memory",
        aliases=("ls",),
    ),
    # ── Panel commands ──────────────────────────────────────────────
    CommandInfo(
        name="system.panel.show",
        description="Show a panel",
        category="ui",
        params_help="<panel_id>",
        examples=("panel.show memory",),
    ),
    CommandInfo(
        name="system.panel.hide",
        description="Hide a panel",
        category="ui",
        params_help="<panel_id>",
    ),
    CommandInfo(
        name="system.panel.toggle",
        description="Toggle panel visibility",
        category="ui",
        params_help="<panel_id>",
    ),
    CommandInfo(
        name="system.panel.list",
        description="List all registered panels",
        category="ui",
    ),
    # ── Layout commands ─────────────────────────────────────────────
    CommandInfo(
        name="system.layout.save",
        description="Save current panel layout",
        category="ui",
        params_help="<name>",
    ),
    CommandInfo(
        name="system.layout.load",
        description="Load a saved layout",
        category="ui",
        params_help="<name>",
    ),
    CommandInfo(
        name="system.layout.list",
        description="List available layouts",
        category="ui",
    ),
    CommandInfo(
        name="system.layout.delete",
        description="Delete a saved layout",
        category="ui",
        params_help="<name>",
    ),
    CommandInfo(
        name="system.layout.reset",
        description="Reset layout to defaults",
        category="ui",
    ),
    # ── Theme commands ──────────────────────────────────────────────
    CommandInfo(
        name="system.theme.apply",
        description="Apply a theme to all panels",
        category="ui",
        params_help="<name>",
    ),
    CommandInfo(
        name="system.theme.list",
        description="List available themes",
        category="ui",
    ),
    # ── Interaction commands ───────────────────────────────────────
    CommandInfo(
        name="interaction.cursor.enable",
        description="Enable cursor tracking",
        category="interaction",
    ),
    CommandInfo(
        name="interaction.cursor.disable",
        description="Disable cursor tracking",
        category="interaction",
    ),
    CommandInfo(
        name="interaction.cursor.click",
        description="Click at current cursor position",
        category="interaction",
    ),
    CommandInfo(
        name="interaction.mode.cursor",
        description="Set interaction mode to cursor-based",
        category="interaction",
    ),
    CommandInfo(
        name="interaction.mode.panel",
        description="Set interaction mode to panel-based",
        category="interaction",
    ),
    CommandInfo(
        name="interaction.mode.reset",
        description="Reset interaction to idle state",
        category="interaction",
    ),
    CommandInfo(
        name="panel.select",
        description="Select a panel",
        category="interaction",
        params_help="<panel_id>",
    ),
    CommandInfo(
        name="panel.focus",
        description="Focus a panel (bring to front)",
        category="interaction",
        params_help="<panel_id>",
    ),
    CommandInfo(
        name="panel.move",
        description="Start dragging a panel",
        category="interaction",
        params_help="<panel_id>",
    ),
    CommandInfo(
        name="panel.resize",
        description="Start resizing a panel",
        category="interaction",
        params_help="<panel_id>",
    ),
    CommandInfo(
        name="panel.reset",
        description="Reset panel position and size",
        category="interaction",
        params_help="<panel_id>",
    ),
    # ── Debug commands ─────────────────────────────────────────────
    CommandInfo(
        name="interaction.debug",
        description="Show current interaction state (debug info)",
        category="debug",
        aliases=("id",),
    ),
    CommandInfo(
        name="system.boot.profile",
        description="Show boot time profile",
        category="debug",
    ),
]


class SystemCommandPlugin(PluginBase):
    """Registers system commands and their handlers in CommandRegistry + CommandBus."""

    name = "system_commands_plugin"

    def __init__(self) -> None:
        self._command_registry: CommandRegistry | None = None
        self._command_bus = None
        self._event_bus = None
        self._container: ServiceContainer | None = None
        self._boot_time: float = 0.0

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="System Commands",
            version="1.0",
            category="system",
            commands=[c.name for c in _SYSTEM_COMMANDS],
            description="System-level commands: help, status, plugins, quit",
        )

    def initialize(self, container: ServiceContainer) -> None:
        self._container = container
        self._command_bus = container.resolve("command_bus")
        self._event_bus = container.resolve("event_bus")
        self._boot_time = time.time()

        # Create CommandRegistry if not already present
        if container.has("command_registry"):
            self._command_registry = container.resolve("command_registry")
        else:
            self._command_registry = CommandRegistry()
            self._command_registry.initialize(container)

        # Register all system commands in the registry
        for cmd_info in _SYSTEM_COMMANDS:
            self._command_registry.register(cmd_info)

        # Register handlers on CommandBus
        self._command_bus.register_handler("system.help", self._handle_help)
        self._command_bus.register_handler("system.status", self._handle_status)
        self._command_bus.register_handler("system.plugins", self._handle_plugins)
        self._command_bus.register_handler("system.commands", self._handle_commands)
        self._command_bus.register_handler("system.ping", self._handle_ping)
        self._command_bus.register_handler("system.shutdown", self._handle_shutdown)
        self._command_bus.register_handler("cli.history", self._handle_history)
        self._command_bus.register_handler("cli.clear", self._handle_clear)
        self._command_bus.register_handler("cursor_click", self._handle_cursor_click)
        self._command_bus.register_handler("cursor_move", self._handle_cursor_move)
        self._command_bus.register_handler("system.panel.show", self._handle_panel_show)
        self._command_bus.register_handler("system.panel.hide", self._handle_panel_hide)
        self._command_bus.register_handler("system.panel.toggle", self._handle_panel_toggle)
        self._command_bus.register_handler("system.panel.list", self._handle_panel_list)
        self._command_bus.register_handler("system.layout.save", self._handle_layout_save)
        self._command_bus.register_handler("system.layout.load", self._handle_layout_load)
        self._command_bus.register_handler("system.layout.list", self._handle_layout_list)
        self._command_bus.register_handler("system.layout.delete", self._handle_layout_delete)
        self._command_bus.register_handler("system.layout.reset", self._handle_layout_reset)
        self._command_bus.register_handler("system.theme.apply", self._handle_theme_apply)
        self._command_bus.register_handler("system.theme.list", self._handle_theme_list)

        # Interaction command handlers
        self._command_bus.register_handler("interaction.cursor.enable", self._handle_cursor_enable)
        self._command_bus.register_handler("interaction.cursor.disable", self._handle_cursor_disable)
        self._command_bus.register_handler("interaction.cursor.click", self._handle_cursor_click_interaction)
        self._command_bus.register_handler("interaction.mode.cursor", self._handle_mode_cursor)
        self._command_bus.register_handler("interaction.mode.panel", self._handle_mode_panel)
        self._command_bus.register_handler("interaction.mode.reset", self._handle_mode_reset)
        self._command_bus.register_handler("panel.select", self._handle_panel_select)
        self._command_bus.register_handler("panel.focus", self._handle_panel_focus)
        self._command_bus.register_handler("panel.move", self._handle_panel_move)
        self._command_bus.register_handler("panel.resize", self._handle_panel_resize)
        self._command_bus.register_handler("panel.reset", self._handle_panel_reset)

        # Debug command handlers
        self._command_bus.register_handler("interaction.debug", self._handle_interaction_debug)
        self._command_bus.register_handler("system.boot.profile", self._handle_boot_profile)

        logger.info("System commands registered (%d commands)", len(_SYSTEM_COMMANDS))

    # ── Handlers ──────────────────────────────────────────────────────

    def _handle_help(self, command: Command) -> dict:
        category = command.params.get("category")
        help_text = self._command_registry.get_help(category)
        return {"message": help_text}

    def _handle_status(self, command: Command) -> dict:
        uptime = time.time() - self._boot_time
        status = {
            "uptime": f"{uptime:.0f}s",
            "platform": platform.system(),
            "commands_registered": self._command_registry.command_count,
        }
        if self._container and self._container.has("event_bus"):
            eb = self._container.resolve("event_bus")
            status["event_queue_depth"] = eb.queue_size()
        if self._container and self._container.has("command_bus"):
            cb = self._container.resolve("command_bus")
            status["commands_processed"] = cb.processed_count
        return {"message": "System status", **status}

    def _handle_plugins(self, command: Command) -> dict:
        if self._container and self._container.has("plugin_loader"):
            loader = self._container.resolve("plugin_loader")
            plugins = [
                {"name": getattr(p, "name", "?"), "type": type(p).__name__}
                for p in loader.loaded_plugins
            ]
            return {"message": f"{len(plugins)} plugins loaded", "plugins": plugins}
        return {"message": "Plugin loader not available"}

    def _handle_commands(self, command: Command) -> dict:
        categories = self._command_registry.get_categories()
        total = self._command_registry.command_count
        lines = [f"{total} commands registered across {len(categories)} categories:"]
        for cat in categories:
            cmds = self._command_registry.get_commands_in_category(cat)
            lines.append(f"  [{cat}] {', '.join(cmds)}")
        return {"message": "\n".join(lines)}

    def _handle_ping(self, command: Command) -> dict:
        return {"message": "pong", "timestamp": time.time()}

    def _handle_shutdown(self, command: Command) -> dict:
        if self._container and self._container.has("application"):
            self._container.resolve("application").request_shutdown()
        return {"message": "Shutting down..."}

    def _handle_history(self, command: Command) -> dict:
        if self._command_bus:
            recent = self._command_bus.get_recent(20)
            if not recent:
                return {"message": "No command history."}
            lines = []
            for cmd in recent:
                status_icon = "✓" if cmd.status == "COMPLETED" else "✗"
                lines.append(f"  {status_icon} {cmd.name} (source={cmd.source})")
            return {"message": "Recent commands:\n" + "\n".join(lines)}
        return {"message": "Command bus not available"}

    def _handle_clear(self, command: Command) -> dict:
        os.system("cls" if os.name == "nt" else "clear")
        return {"message": ""}

    def _handle_cursor_click(self, command: Command) -> dict:
        return {"message": "click", "hand": command.params.get("hand", "?")}

    def _handle_cursor_move(self, command: Command) -> dict:
        return None

    # ── Panel handlers ────────────────────────────────────────────────

    def _handle_panel_show(self, command: Command) -> dict:
        panel_id = command.params.get("panel_id", "")
        if not panel_id:
            return {"message": "Usage: panel.show <panel_id>"}
        if not self._container or not self._container.has("panel_registry"):
            return {"message": "Panel system not initialized"}
        reg = self._container.resolve("panel_registry")
        if reg.show_panel(panel_id):
            return {"message": f"Panel '{panel_id}' shown"}
        return {"message": f"Panel '{panel_id}' not found"}

    def _handle_panel_hide(self, command: Command) -> dict:
        panel_id = command.params.get("panel_id", "")
        if not panel_id:
            return {"message": "Usage: panel.hide <panel_id>"}
        if not self._container or not self._container.has("panel_registry"):
            return {"message": "Panel system not initialized"}
        reg = self._container.resolve("panel_registry")
        if reg.hide_panel(panel_id):
            return {"message": f"Panel '{panel_id}' hidden"}
        return {"message": f"Panel '{panel_id}' not found"}

    def _handle_panel_toggle(self, command: Command) -> dict:
        panel_id = command.params.get("panel_id", "")
        if not panel_id:
            return {"message": "Usage: panel.toggle <panel_id>"}
        if not self._container or not self._container.has("panel_registry"):
            return {"message": "Panel system not initialized"}
        reg = self._container.resolve("panel_registry")
        visible = reg.toggle_panel(panel_id)
        if visible is None:
            return {"message": f"Panel '{panel_id}' not found"}
        state = "shown" if visible else "hidden"
        return {"message": f"Panel '{panel_id}' {state}"}

    def _handle_panel_list(self, command: Command) -> dict:
        if not self._container or not self._container.has("panel_registry"):
            return {"message": "Panel system not initialized"}
        reg = self._container.resolve("panel_registry")
        panels = reg.list_all()
        if not panels:
            return {"message": "No panels registered"}
        lines = []
        for p in panels:
            vis = "visible" if p.visible else "hidden"
            lines.append(f"  {p.id} ({p.type}) z={p.z_index} [{vis}]")
        return {"message": f"{len(panels)} panels:\n" + "\n".join(lines)}

    # ── Layout handlers ───────────────────────────────────────────────

    def _handle_layout_save(self, command: Command) -> dict:
        name = command.params.get("name", "")
        if not name:
            return {"message": "Usage: layout.save <name>"}
        if not self._container or not self._container.has("layout_manager"):
            return {"message": "Layout system not initialized"}
        mgr = self._container.resolve("layout_manager")
        layout = mgr.save(name)
        return {"message": f"Layout '{name}' saved ({len(layout.get('panels', []))} panels)"}

    def _handle_layout_load(self, command: Command) -> dict:
        name = command.params.get("name", "")
        if not name:
            return {"message": "Usage: layout.load <name>"}
        if not self._container or not self._container.has("layout_manager"):
            return {"message": "Layout system not initialized"}
        mgr = self._container.resolve("layout_manager")
        if mgr.load(name):
            return {"message": f"Layout '{name}' loaded"}
        return {"message": f"Layout '{name}' not found"}

    def _handle_layout_list(self, command: Command) -> dict:
        if not self._container or not self._container.has("layout_manager"):
            return {"message": "Layout system not initialized"}
        mgr = self._container.resolve("layout_manager")
        layouts = mgr.list_layouts()
        current = mgr.current_layout
        if not layouts:
            return {"message": "No saved layouts"}
        lines = []
        for name in layouts:
            marker = " *" if name == current else ""
            lines.append(f"  {name}{marker}")
        return {"message": f"{len(layouts)} layouts:\n" + "\n".join(lines)}

    def _handle_layout_delete(self, command: Command) -> dict:
        name = command.params.get("name", "")
        if not name:
            return {"message": "Usage: layout.delete <name>"}
        if not self._container or not self._container.has("layout_manager"):
            return {"message": "Layout system not initialized"}
        mgr = self._container.resolve("layout_manager")
        if mgr.delete(name):
            return {"message": f"Layout '{name}' deleted"}
        return {"message": f"Layout '{name}' not found"}

    def _handle_layout_reset(self, command: Command) -> dict:
        if not self._container or not self._container.has("layout_manager"):
            return {"message": "Layout system not initialized"}
        mgr = self._container.resolve("layout_manager")
        mgr.reset()
        return {"message": "Layout reset to defaults"}

    # ── Theme handlers ────────────────────────────────────────────────

    def _handle_theme_apply(self, command: Command) -> dict:
        name = command.params.get("name", "")
        if not name:
            return {"message": "Usage: theme.apply <name>"}
        if not self._container or not self._container.has("theme_manager"):
            return {"message": "Theme system not initialized"}
        mgr = self._container.resolve("theme_manager")
        if mgr.load_theme(name):
            if self._container.has("panel_registry"):
                reg = self._container.resolve("panel_registry")
                count = mgr.apply_to_registry(reg)
                return {"message": f"Theme '{name}' applied ({count} panels)"}
            return {"message": f"Theme '{name}' loaded (no panels to apply)"}
        return {"message": f"Theme '{name}' not found"}

    def _handle_theme_list(self, command: Command) -> dict:
        if not self._container or not self._container.has("theme_manager"):
            return {"message": "Theme system not initialized"}
        mgr = self._container.resolve("theme_manager")
        themes = mgr.list_themes()
        current = mgr.current_name
        lines = []
        for name in themes:
            marker = " *" if name == current else ""
            lines.append(f"  {name}{marker}")
        return {"message": f"{len(themes)} themes:\n" + "\n".join(lines)}

    # ── Interaction handlers ────────────────────────────────────────

    def _get_interaction_controller(self):
        """Get InteractionController from container."""
        if self._container and self._container.has("interaction_controller"):
            return self._container.resolve("interaction_controller")
        return None

    def _handle_cursor_enable(self, command: Command) -> dict:
        ic = self._get_interaction_controller()
        if not ic:
            return {"message": "Interaction system not initialized"}
        ic.cursor_controller.unfreeze()
        return {"message": "Cursor tracking enabled"}

    def _handle_cursor_disable(self, command: Command) -> dict:
        ic = self._get_interaction_controller()
        if not ic:
            return {"message": "Interaction system not initialized"}
        ic.cursor_controller.freeze()
        return {"message": "Cursor tracking disabled"}

    def _handle_cursor_click_interaction(self, command: Command) -> dict:
        ic = self._get_interaction_controller()
        if not ic:
            return {"message": "Interaction system not initialized"}
        pos = ic.cursor_controller.position
        result = ic.on_click(pos.x, pos.y)
        if result:
            return {"message": f"Clicked panel: {result}"}
        return {"message": "Click at cursor position (no panel hit)"}

    def _handle_mode_cursor(self, command: Command) -> dict:
        ic = self._get_interaction_controller()
        if not ic:
            return {"message": "Interaction system not initialized"}
        ic.on_cancel()
        return {"message": "Mode set to CURSOR"}

    def _handle_mode_panel(self, command: Command) -> dict:
        ic = self._get_interaction_controller()
        if not ic:
            return {"message": "Interaction system not initialized"}
        return {"message": "Mode set to PANEL"}

    def _handle_mode_reset(self, command: Command) -> dict:
        ic = self._get_interaction_controller()
        if not ic:
            return {"message": "Interaction system not initialized"}
        ic.on_cancel()
        return {"message": "Interaction reset to IDLE"}

    def _handle_panel_select(self, command: Command) -> dict:
        panel_id = command.params.get("panel_id", "")
        if not panel_id:
            return {"message": "Usage: panel.select <panel_id>"}
        ic = self._get_interaction_controller()
        if not ic:
            return {"message": "Interaction system not initialized"}
        success = ic.selection_manager.select(panel_id)
        if success:
            ic.focus_manager.focus(panel_id)
            return {"message": f"Panel '{panel_id}' selected"}
        return {"message": f"Panel '{panel_id}' not found"}

    def _handle_panel_focus(self, command: Command) -> dict:
        panel_id = command.params.get("panel_id", "")
        if not panel_id:
            return {"message": "Usage: panel.focus <panel_id>"}
        ic = self._get_interaction_controller()
        if not ic:
            return {"message": "Interaction system not initialized"}
        success = ic.focus_manager.focus(panel_id)
        if success:
            return {"message": f"Panel '{panel_id}' focused"}
        return {"message": f"Panel '{panel_id}' not found"}

    def _handle_panel_move(self, command: Command) -> dict:
        panel_id = command.params.get("panel_id", "")
        if not panel_id:
            return {"message": "Usage: panel.move <panel_id>"}
        ic = self._get_interaction_controller()
        if not ic:
            return {"message": "Interaction system not initialized"}
        ic.selection_manager.select(panel_id)
        pos = ic.cursor_controller.position
        success = ic.on_drag_start(pos.x, pos.y)
        if success:
            return {"message": f"Dragging panel '{panel_id}'"}
        return {"message": f"Cannot move panel '{panel_id}'"}

    def _handle_panel_resize(self, command: Command) -> dict:
        panel_id = command.params.get("panel_id", "")
        if not panel_id:
            return {"message": "Usage: panel.resize <panel_id>"}
        ic = self._get_interaction_controller()
        if not ic:
            return {"message": "Interaction system not initialized"}
        ic.selection_manager.select(panel_id)
        pos = ic.cursor_controller.position
        success = ic.on_resize_start(pos.x, pos.y)
        if success:
            return {"message": f"Resizing panel '{panel_id}'"}
        return {"message": f"Cannot resize panel '{panel_id}'"}

    def _handle_panel_reset(self, command: Command) -> dict:
        panel_id = command.params.get("panel_id", "")
        if not panel_id:
            return {"message": "Usage: panel.reset <panel_id>"}
        if not self._container or not self._container.has("panel_registry"):
            return {"message": "Panel system not initialized"}
        reg = self._container.resolve("panel_registry")
        info = reg.get(panel_id)
        if not info:
            return {"message": f"Panel '{panel_id}' not found"}
        info.x = 0
        info.y = 0
        info.w = 400
        info.h = 300
        return {"message": f"Panel '{panel_id}' reset to defaults"}

    # ── Debug handlers ──────────────────────────────────────────────

    def _handle_interaction_debug(self, command: Command) -> dict:
        """Show current interaction state for debugging."""
        ic = self._get_interaction_controller()
        if not ic:
            return {"message": "Interaction system not initialized"}

        # Gather interaction state
        state = ic.state
        cursor = ic.cursor_controller
        hover = ic.hover_result
        selected = ic.selection_manager.selected_panel_id
        focused = ic.focus_manager.focused_panel_id

        lines = [
            "=== Interaction State ===",
            f"  State: {state.value}",
            f"  Cursor Position: ({cursor.position.x:.1f}, {cursor.position.y:.1f})",
            f"  Cursor Mode: {cursor.mode.value}",
        ]

        if hover:
            lines.append(f"  Hover Panel: {hover.panel_id}")
            lines.append(f"    Position: ({hover.x:.0f}, {hover.y:.0f})")
            lines.append(f"    Size: {hover.w:.0f} x {hover.h:.0f}")
            lines.append(f"    Is Resize Handle: {hover.is_resize_handle}")
        else:
            lines.append("  Hover Panel: None")

        lines.append(f"  Selected Panel: {selected or 'None'}")
        lines.append(f"  Focused Panel: {focused or 'None'}")

        # Drag state
        if ic.drag_controller.is_dragging:
            lines.append(f"  Dragging: {ic.drag_controller.dragged_panel_id}")
            delta = ic.drag_controller.delta
            lines.append(f"    Delta: ({delta.dx:.0f}, {delta.dy:.0f})")
        else:
            lines.append("  Dragging: No")

        # Resize state
        if ic.resize_controller.is_resizing:
            lines.append(f"  Resizing: {ic.resize_controller.resized_panel_id}")
        else:
            lines.append("  Resizing: No")

        return {"message": "\n".join(lines)}

    def _handle_boot_profile(self, command: Command) -> dict:
        """Show boot time profile."""
        if self._container and self._container.has("boot_profiler"):
            profiler = self._container.resolve("boot_profiler")
            total = profiler.get_total_ms()
            lines = [f"Total boot time: {total:.1f}ms"]
            for mark in profiler._marks:
                delta = profiler.get_delta_ms(mark.name)
                lines.append(f"  {mark.name}: {mark.elapsed_ms:.1f}ms (delta: {delta:.1f}ms)")
            return {"message": "\n".join(lines)}
        return {"message": "Boot profiler not available"}
