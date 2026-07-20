#!/usr/bin/env python3
"""
Aether Brain - Core System Entry Point

This is the brain without eyes. It runs the core system:
- Event bus (nervous system)
- Command system
- Memory
- Context engine
- Smart UI (PySide6)
- Hotkey listener

No camera, no computer vision - just the intelligent foundation.
"""

import sys
import logging
import signal
import threading

from core.engine import AetherEngine, create_engine
from core.event_bus import EventBus, EventType
from command.command import Command, CommandRegistry, create_default_registry
from command.handler import CommandHandler
from memory.storage import MemoryStorage
from context.context_manager import ContextManager
from interface.ui import AetherUI, create_system_panel, create_developer_panel, create_settings_panel


# Global references for signal handling
_engine = None
_ui = None
_hotkey_listener = None


def setup_logging():
    """Configure logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/aether_brain.log", encoding="utf-8")
        ]
    )


def create_brain(config: dict = None) -> AetherEngine:
    """Create and wire up the complete Aether brain."""
    global _engine, _ui
    
    # Default config
    if config is None:
        config = {
            "modules": {}
        }
    
    # Create engine
    engine = create_engine(config)
    _engine = engine
    
    # Create core services
    event_bus = engine.event_bus
    memory = MemoryStorage()
    context = ContextManager()
    command_handler = CommandHandler(event_bus)
    
    # Create UI
    app = sys.modules.get('PySide6.QtWidgets.QApplication')
    if not app:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
    
    ui = AetherUI(context_manager=context, memory_storage=memory)
    _ui = ui
    
    # Register UI panels
    ui.register_panel("system", "SYSTEM", create_system_panel(context))
    ui.register_panel("developer", "DEVELOPER", create_developer_panel())
    ui.register_panel("settings", "SETTINGS", create_settings_panel(memory))
    
    # Show system panel by default
    ui.show_panel("system")
    
    # Wire up event handlers
    _wire_events(engine, ui, command_handler, context, memory)
    
    # Load saved mode
    saved_mode = memory.get("mode", "normal")
    ui.set_mode(saved_mode)
    context.set_mode(saved_mode)
    
    return engine


def _wire_events(engine, ui, command_handler, context, memory):
    """Connect all event handlers."""
    event_bus = engine.event_bus
    
    # UI events
    def on_ui_open(event):
        ui.show()
        ui.raise_()
        ui.activateWindow()
        ui.show_panel("system")
    
    def on_ui_close(event):
        ui.hide()
    
    def on_panel_show(event):
        panel = event.data.get("panel", "system")
        ui.show_panel(panel)
    
    def on_panel_hide(event):
        panel = event.data.get("panel", "system")
        ui.hide_panel(panel)
    
    def on_mode_change(event):
        mode = event.data.get("mode", "normal")
        ui.set_mode(mode)
        context.set_mode(mode)
        memory.set("mode", mode)
    
    event_bus.subscribe(EventType.UI_OPEN, on_ui_open)
    event_bus.subscribe(EventType.UI_CLOSE, on_ui_close)
    event_bus.subscribe(EventType.PANEL_SHOW_REQUESTED, on_panel_show)
    event_bus.subscribe(EventType.PANEL_HIDE_REQUESTED, on_panel_hide)
    event_bus.subscribe(EventType.MODE_CHANGED, on_mode_change)
    
    # Command execution from events
    def on_command_event(event):
        cmd_data = event.data.get("command")
        if cmd_data:
            cmd = Command(**cmd_data)
            command_handler.execute(cmd)
    
    event_bus.subscribe(EventType.COMMAND_EXECUTE, on_command_event)
    
    # Context updates
    def on_context_update(event):
        context.update(**event.data)
    
    event_bus.subscribe(EventType.CONTEXT_CHANGED, on_context_update)
    event_bus.subscribe(EventType.CONTEXT_APP_CHANGED, on_context_update)
    
    # Keyboard/hotkey events
    def on_hotkey(event):
        key = event.data.get("key", "").lower()
        source = event.data.get("source", "keyboard")
        
        _handle_hotkey(key, source, command_handler)
    
    event_bus.subscribe(EventType.INPUT_HOTKEY, on_hotkey)


def _handle_hotkey(key: str, source: str, command_handler: CommandHandler):
    """Map hotkeys to commands."""
    key = key.lower().replace("ctrl+", "").replace("control+", "").strip()
    
    # Map hotkeys to commands
    hotkey_map = {
        "space": Command(name="open_ui", source=source, params={"panel": "system"}),
        "escape": Command(name="close_ui", source=source),
        "1": Command(name="switch_panel", source=source, params={"panel": "system"}),
        "2": Command(name="switch_panel", source=source, params={"panel": "developer"}),
        "3": Command(name="switch_panel", source=source, params={"panel": "settings"}),
        "tab": Command(name="set_mode", source=source, params={"mode": "developer"}),
        "m": Command(name="set_mode", source=source, params={"mode": "normal"}),
        "p": Command(name="set_mode", source=source, params={"mode": "presentation"}),
    }
    
    cmd = hotkey_map.get(key)
    if cmd:
        command_handler.execute(cmd)


def start_hotkey_listener(event_bus):
    """Start global hotkey listener in background thread."""
    from pynput import keyboard
    
    def on_press(key):
        try:
            # Handle special keys
            if hasattr(key, 'char') and key.char:
                k = key.char
            elif key == keyboard.Key.space:
                k = "space"
            elif key == keyboard.Key.esc:
                k = "escape"
            elif key == keyboard.Key.tab:
                k = "tab"
            else:
                return
            
            event_bus.emit_simple(EventType.INPUT_HOTKEY, {"key": k, "source": "keyboard"})
        except Exception as e:
            logging.getLogger("Aether.Hotkeys").debug(f"Hotkey error: {e}")
    
    listener = keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()
    return listener


def start_gesture_bridge(event_bus):
    """Start gesture input bridge — listens for gesture events on the bus
    and translates them to the same command path as keyboard hotkeys.
    This allows gesture input in the brain-only (no camera) path when
    hand data arrives via network or other means."""
    from vision.gesture_engine import GestureEngine
    from vision.gesture_executor import GestureActionExecutor

    engine = GestureEngine()
    executor = GestureActionExecutor(event_bus, engine)

    def on_hand_data(event):
        """Receive hand landmark data and run gesture recognition."""
        hand_results = event.data.get("hand_results")
        if hand_results:
            gesture_events = engine.update(hand_results)
            executor.process_events(gesture_events)

    event_bus.subscribe(EventType.HAND_DETECTED, on_hand_data)
    return executor


def signal_handler(sig, frame):
    """Handle shutdown signals."""
    logging.getLogger("Aether.Main").info("Shutdown signal received")
    if _engine:
        _engine.shutdown()
    sys.exit(0)


def main():
    """Main entry point - starts the Aether brain."""
    setup_logging()
    logger = logging.getLogger("Aether.Main")
    
    logger.info("=" * 50)
    logger.info("AETHER BRAIN STARTING")
    logger.info("=" * 50)
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create the brain
    engine = create_brain()
    
    # Initialize and start
    if not engine.initialize():
        logger.error("Failed to initialize engine")
        return 1
    
    if not engine.start():
        logger.error("Failed to start engine")
        return 1
    
    # Start hotkey listener
    global _hotkey_listener
    _hotkey_listener = start_hotkey_listener(engine.event_bus)
    
    # Start gesture bridge (for network-received hand data)
    gesture_executor = start_gesture_bridge(engine.event_bus)
    
    logger.info("Aether Brain is running!")
    logger.info("Hotkeys:")
    logger.info("  CTRL+SPACE  - Open UI")
    logger.info("  ESC         - Close UI")
    logger.info("  CTRL+1/2/3  - Switch panels (System/Dev/Settings)")
    logger.info("  CTRL+TAB    - Developer mode")
    logger.info("  CTRL+M      - Normal mode")
    logger.info("  CTRL+P      - Presentation mode")
    logger.info("Gestures (via camera/network):")
    logger.info("  Open Palm   - Toggle UI")
    logger.info("  Point       - Move cursor")
    logger.info("  Pinch       - Click/select")
    logger.info("  Fist        - Cancel")
    logger.info("  Peace       - Next panel")
    logger.info("  Swipe L/R   - Navigate panels")
    logger.info("  Swipe U/D   - Scroll")
    logger.info("  Grab        - Drag window")
    logger.info("  Thumbs Up   - Confirm")
    
    # Run the Qt event loop
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())