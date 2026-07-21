#!/usr/bin/env python3
"""
Aether Brain V1 — Interactive Spatial Assistant

Entry point: python brain_main.py

Architecture:
  Gesture → EventBus → UIManager → CursorOverlay + HomeMenu
"""

import sys
import math
import time
import logging
import signal

from core.engine import AetherEngine, create_engine
from core.event_bus import EventBus, EventType
from core.cursor_manager import CursorManager
from command.command import Command
from command.handler import CommandHandler
from memory.storage import MemoryStorage
from context.context_manager import ContextManager
from interface.ui import AetherUI, create_system_panel, create_developer_panel, create_settings_panel
from interface.ui_manager import UIManager


# ── Globals ──────────────────────────────────────────────────────
_engine = None
_ui = None
_hotkey_listener = None
_ui_manager = None
_command_handler = None
_last_gesture = None
_last_gesture_time = 0.0
GESTURE_COOLDOWN = 1.5
_was_pinching = False


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/aether_brain.log", encoding="utf-8")
        ]
    )


def create_brain(config: dict = None) -> AetherEngine:
    global _engine, _ui, _ui_manager, _command_handler

    if config is None:
        config = {"modules": {}}

    engine = create_engine(config)
    _engine = engine
    bus = engine.event_bus

    memory = MemoryStorage()
    context = ContextManager()
    command_handler = CommandHandler(bus)
    _command_handler = command_handler

    # ── PySide6 App ──────────────────────────────────────────────
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # ── UI panels ────────────────────────────────────────────────
    ui = AetherUI(context_manager=context, memory_storage=memory)
    _ui = ui
    ui.register_panel("system", "SYSTEM", create_system_panel(context))
    ui.register_panel("developer", "DEVELOPER", create_developer_panel())
    ui.register_panel("settings", "SETTINGS", create_settings_panel(memory))
    ui.show_panel("system")

    # ── UIManager (owns cursor overlay + home menu) ─────────────
    cursor_manager = CursorManager()
    _ui_manager = UIManager(cursor_manager, bus)
    _ui_manager.show()

    # ── Wire events ──────────────────────────────────────────────
    _wire_events(engine, ui, command_handler, context, memory, bus)

    saved_mode = memory.get("mode", "normal")
    ui.set_mode(saved_mode)
    context.set_mode(saved_mode)

    return engine


def _wire_events(engine, ui, command_handler, context, memory, bus):
    # UI events
    def on_ui_open(event):
        ui.show()
        ui.raise_()
        ui.activateWindow()
        ui.show_panel("system")

    def on_ui_close(event):
        ui.hide()
        _ui_manager.home_menu.hide_menu()

    def on_panel_show(event):
        ui.show_panel(event.data.get("panel", "system"))

    def on_panel_hide(event):
        ui.hide_panel(event.data.get("panel", "system"))

    def on_mode_change(event):
        mode = event.data.get("mode", "normal")
        ui.set_mode(mode)
        context.set_mode(mode)
        memory.set("mode", mode)

    bus.subscribe(EventType.UI_OPEN, on_ui_open)
    bus.subscribe(EventType.UI_CLOSE, on_ui_close)
    bus.subscribe(EventType.PANEL_SHOW_REQUESTED, on_panel_show)
    bus.subscribe(EventType.PANEL_HIDE_REQUESTED, on_panel_hide)
    bus.subscribe(EventType.MODE_CHANGED, on_mode_change)

    # Command execution
    def on_command_event(event):
        cmd_data = event.data.get("command")
        if cmd_data:
            cmd = Command(**cmd_data)
            command_handler.execute(cmd)

    bus.subscribe(EventType.COMMAND_EXECUTE, on_command_event)

    # Context
    def on_context_update(event):
        context.update(**event.data)

    bus.subscribe(EventType.CONTEXT_CHANGED, on_context_update)
    bus.subscribe(EventType.CONTEXT_APP_CHANGED, on_context_update)

    # Keyboard
    def on_hotkey(event):
        key = event.data.get("key", "").lower()
        _handle_hotkey(key, event.data.get("source", "keyboard"), command_handler)

    bus.subscribe(EventType.INPUT_HOTKEY, on_hotkey)

    # ── HAND_DETECTED → cursor + gesture actions ─────────────────
    def on_hand_detected(event):
        global _was_pinching, _last_gesture, _last_gesture_time

        hands = event.data.get("hands", [])
        if not hands:
            _ui_manager.cursor_manager.hide()
            if _ui_manager.home_menu.is_visible:
                bus.emit_simple(EventType.MENU_CLOSE, {})
            _was_pinching = False
            return

        hand = hands[0]
        lm = hand.get("landmarks", [])
        gesture = hand.get("gesture", "Unknown")
        gesture_score = hand.get("gesture_score", 0.0)

        if not lm or len(lm) < 21:
            _ui_manager.cursor_manager.hide()
            return

        idx_tip = lm[8]
        thumb_tip = lm[4]

        # Pinch
        dx = thumb_tip["x"] - idx_tip["x"]
        dy = thumb_tip["y"] - idx_tip["y"]
        pinch = math.sqrt(dx * dx + dy * dy) < 0.04

        # Update cursor via UIManager
        _ui_manager.update_cursor(
            hand_x=idx_tip["x"],
            hand_y=idx_tip["y"],
            gesture=gesture,
            gesture_score=gesture_score,
            is_pinch=pinch,
        )

        # Gesture → Action
        now = time.time()
        cooldown_ok = (gesture != _last_gesture) or (now - _last_gesture_time) > GESTURE_COOLDOWN

        if gesture == "Open_Palm" and cooldown_ok:
            if _ui_manager.home_menu.is_visible:
                bus.emit_simple(EventType.MENU_OPEN, {})
            else:
                bus.emit_simple(EventType.UI_OPEN, {})
            _last_gesture = gesture
            _last_gesture_time = now

        elif gesture == "Closed_Fist" and cooldown_ok:
            bus.emit_simple(EventType.MENU_CLOSE, {})
            bus.emit_simple(EventType.UI_CLOSE, {})
            _last_gesture = gesture
            _last_gesture_time = now

        elif gesture == "Victory" and cooldown_ok:
            bus.emit_simple(EventType.PANEL_SHOW_REQUESTED, {"panel": "developer"})
            _last_gesture = gesture
            _last_gesture_time = now

        elif gesture == "ILoveYou" and cooldown_ok:
            bus.emit_simple(EventType.PANEL_SHOW_REQUESTED, {"panel": "settings"})
            _last_gesture = gesture
            _last_gesture_time = now

        elif gesture == "Thumb_Up" and cooldown_ok:
            bus.emit_simple(EventType.MODE_CHANGED, {"mode": "normal"})
            _last_gesture = gesture
            _last_gesture_time = now

        elif gesture == "Thumb_Down" and cooldown_ok:
            bus.emit_simple(EventType.MODE_CHANGED, {"mode": "developer"})
            _last_gesture = gesture
            _last_gesture_time = now

        # Pinch → Click
        if pinch and not _was_pinching:
            action = _ui_manager.handle_pinch_click()
            if action:
                logging.getLogger("Aether.Main").info(f"Pinch click: {action}")
        _was_pinching = pinch

    bus.subscribe(EventType.HAND_DETECTED, on_hand_detected)


def _handle_hotkey(key: str, source: str, command_handler: CommandHandler):
    key = key.lower().replace("ctrl+", "").replace("control+", "").strip()
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
    from pynput import keyboard
    def on_press(key):
        try:
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
        except Exception:
            pass
    listener = keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()
    return listener


def signal_handler(sig, frame):
    if _engine:
        _engine.shutdown()
    sys.exit(0)


def main():
    setup_logging()
    logger = logging.getLogger("Aether.Main")
    logger.info("=" * 50)
    logger.info("AETHER BRAIN V1 — Interactive Spatial Assistant")
    logger.info("=" * 50)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    engine = create_brain()
    if not engine.initialize():
        logger.error("Failed to initialize engine")
        return 1
    if not engine.start():
        logger.error("Failed to start engine")
        return 1

    global _hotkey_listener
    _hotkey_listener = start_hotkey_listener(engine.event_bus)

    logger.info("Gestures:")
    logger.info("  Open Palm   → Toggle Home Menu")
    logger.info("  Point       → Move cursor")
    logger.info("  Pinch       → Click menu button")
    logger.info("  Fist        → Close / Cancel")
    logger.info("  Thumb Up    → Normal mode")
    logger.info("  Thumb Down  → Developer mode")
    logger.info("  Victory     → Developer panel")
    logger.info("  ILY         → Settings panel")

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
