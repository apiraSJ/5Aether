"""GUIPlugin — PySide6 overlay UI with toast notifications and command history."""

from __future__ import annotations

import logging
import sys
import time
from collections import deque
from typing import Any, Deque, Optional

from aether.core.command import Command
from aether.core.plugin import TickablePlugin, PluginMetadata
from aether.core.service_container import ServiceContainer

logger = logging.getLogger("Aether.GUIPlugin")

# Lazy Qt imports — stored as None until start() succeeds
_QWidgets = None
_QCore = None
_QGui = None


def _import_qt():
    global _QWidgets, _QCore, _QGui
    if _QWidgets is not None:
        return
    from PySide6 import QtWidgets, QtCore, QtGui
    _QWidgets = QtWidgets
    _QCore = QtCore
    _QGui = QtGui


class GUIPlugin(TickablePlugin):
    name = "gui_plugin"

    def __init__(self) -> None:
        self._command_bus = None
        self._event_bus = None
        self._container = None
        self._app = None
        self._ui = None
        self._running = False
        self._boot_time = time.time()
        self._toasts: Deque[tuple] = deque(maxlen=5)
        self._history: Deque[dict] = deque(maxlen=100)

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(label="GUI", version="1.0", category="ui",
                              description="PySide6 floating overlay interface")

    def initialize(self, container: ServiceContainer) -> None:
        self._container = container
        self._command_bus = container.resolve("command_bus")
        self._event_bus = container.resolve("event_bus")
        self._event_bus.subscribe("command.completed", self._on_command_event)
        self._event_bus.subscribe("command.failed", self._on_command_event)
        self._boot_time = time.time()
        logger.info("GUIPlugin initialized")

    def start(self) -> None:
        try:
            from PySide6.QtWidgets import QApplication
            _import_qt()
            self._app = QApplication.instance() or QApplication(sys.argv)
            self._app.setQuitOnLastWindowClosed(False)
            self._create_ui()
            self._ui.show()
            self._running = True
            logger.info("GUIPlugin UI started")
        except ImportError:
            logger.warning("PySide6 not available, running headless")
            self._running = True
        except Exception as e:
            logger.exception("GUIPlugin start failed: %s", e)

    # ── UI Construction ────────────────────────────────────────────

    def _create_ui(self) -> None:
        W = _QWidgets
        Qt = _QCore.Qt
        QFont = _QGui.QFont

        ui = W.QWidget()
        ui.setWindowTitle("Aether")
        ui.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        ui.setAttribute(Qt.WA_TranslucentBackground)
        ui.resize(420, 600)
        self._ui = ui

        frame = W.QFrame()
        frame.setStyleSheet("QFrame{background:rgba(20,24,32,0.95);border:1px solid rgba(0,255,255,0.3);border-radius:12px;}")
        layout = W.QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        # Header
        hdr = W.QLabel("AETHER")
        hdr.setFont(QFont("Consolas", 11, QFont.Bold))
        hdr.setStyleSheet("color:#00ffff;")
        hdr.setAlignment(Qt.AlignCenter)
        layout.addWidget(hdr)

        # Tabs
        tab_bar = W.QHBoxLayout()
        self._tab_btns = []
        self._tab_style = "QPushButton{color:#888;border:none;padding:4px 8px;}"
        self._tab_active = "QPushButton{color:#00ffff;border:none;padding:4px 8px;border-bottom:2px solid #00ffff;}"
        for label in ["Objects", "History", "Log", "Dashboard"]:
            btn = W.QPushButton(label)
            btn.setStyleSheet(self._tab_style)
            btn.clicked.connect(lambda _, b=btn: self._switch_tab(b))
            tab_bar.addWidget(btn)
            self._tab_btns.append(btn)
        layout.addLayout(tab_bar)

        self._stack = W.QStackedWidget()

        # Tab 0: Objects
        obj_w = W.QWidget()
        obj_l = W.QVBoxLayout(obj_w)
        obj_l.setContentsMargins(0, 4, 0, 0)
        obj_l.setSpacing(4)
        obj_l.addWidget(self._lbl("Objects", "#88ff88"))
        self._objects_list = W.QListWidget()
        self._objects_list.setStyleSheet(self._ls())
        obj_l.addWidget(self._objects_list, 1)
        obj_l.addWidget(self._lbl("Facts", "#ffaa00"))
        self._facts_list = W.QListWidget()
        self._facts_list.setStyleSheet(self._ls())
        obj_l.addWidget(self._facts_list, 1)
        self._stack.addWidget(obj_w)

        # Tab 1: History
        hist_w = W.QWidget()
        hist_l = W.QVBoxLayout(hist_w)
        hist_l.setContentsMargins(0, 4, 0, 0)
        hist_l.setSpacing(4)
        hist_l.addWidget(self._lbl("Command History", "#00ffff"))
        self._history_list = W.QListWidget()
        self._history_list.setStyleSheet(self._ls())
        hist_l.addWidget(self._history_list, 1)
        self._stack.addWidget(hist_w)

        # Tab 2: Log
        log_w = W.QWidget()
        log_l = W.QVBoxLayout(log_w)
        log_l.setContentsMargins(0, 4, 0, 0)
        log_l.addWidget(self._lbl("Event Log", "#ff6666"))
        self._log = W.QTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet("QTextEdit{background:rgba(0,0,0,0.4);border:1px solid rgba(255,100,100,0.2);border-radius:4px;color:#ffaaaa;font-family:Consolas;font-size:10px;}")
        log_l.addWidget(self._log)
        self._stack.addWidget(log_w)

        # Tab 3: Dashboard
        dash_w = W.QWidget()
        dash_l = W.QVBoxLayout(dash_w)
        dash_l.setContentsMargins(0, 4, 0, 0)
        dash_l.setSpacing(6)
        dash_l.addWidget(self._lbl("System Dashboard", "#ffaa00"))

        def _metric_row(label, color="#e0e0e0"):
            row = W.QHBoxLayout()
            lbl = W.QLabel(label)
            lbl.setStyleSheet(f"color:#888;font-family:Consolas;font-size:10px;")
            lbl.setFixedWidth(110)
            val = W.QLabel("--")
            val.setStyleSheet(f"color:{color};font-family:Consolas;font-size:11px;font-weight:bold;")
            row.addWidget(lbl)
            row.addWidget(val, 1)
            return row, val

        self._d_uptime_row, self._d_uptime = _metric_row("Uptime", "#00ffff")
        self._d_cmds_row, self._d_cmds = _metric_row("Commands/min", "#88ff88")
        self._d_events_row, self._d_events = _metric_row("Events/sec", "#ffaa00")
        self._d_mem_obj_row, self._d_mem_obj = _metric_row("Memory Objects", "#ff66ff")
        self._d_mem_fact_row, self._d_mem_fact = _metric_row("Memory Facts", "#ff66ff")
        self._d_plugins_row, self._d_plugins = _metric_row("Plugins", "#88ff88")

        for row in [self._d_uptime_row, self._d_cmds_row, self._d_events_row,
                    self._d_mem_obj_row, self._d_mem_fact_row, self._d_plugins_row]:
            dash_l.addLayout(row)

        dash_l.addWidget(self._lbl("Plugin Status", "#00ffff"))
        self._d_plugin_list = W.QListWidget()
        self._d_plugin_list.setStyleSheet(self._ls())
        dash_l.addWidget(self._d_plugin_list, 1)

        self._stack.addWidget(dash_w)

        self._stack.setCurrentIndex(0)
        layout.addWidget(self._stack, 1)

        # Toast
        self._toast_label = W.QLabel("")
        self._toast_label.setAlignment(Qt.AlignCenter)
        self._toast_label.setStyleSheet("QLabel{background:rgba(0,200,100,0.9);color:white;border-radius:6px;padding:6px;font-family:Consolas;font-size:10px;}")
        self._toast_label.hide()
        layout.addWidget(self._toast_label)

        # Command input
        inp = W.QHBoxLayout()
        self._cmd_input = W.QLineEdit()
        self._cmd_input.setPlaceholderText("Command...")
        self._cmd_input.setStyleSheet("QLineEdit{background:rgba(0,0,0,0.5);border:1px solid rgba(0,255,255,0.3);border-radius:4px;color:#fff;padding:6px;font-family:Consolas;font-size:11px;}")
        self._cmd_input.returnPressed.connect(self._send_command)
        send = W.QPushButton("Send")
        send.setFixedWidth(55)
        send.setStyleSheet("QPushButton{background:rgba(0,255,255,0.2);border:1px solid #00ffff;border-radius:4px;color:#00ffff;font-family:Consolas;}QPushButton:hover{background:rgba(0,255,255,0.4);}")
        send.clicked.connect(self._send_command)
        inp.addWidget(self._cmd_input)
        inp.addWidget(send)
        layout.addLayout(inp)

        # Toast timer
        QTimer = _QCore.QTimer
        self._toast_timer = QTimer()
        self._toast_timer.timeout.connect(self._dismiss_toast)
        self._toast_timer.setSingleShot(True)

        # Dashboard refresh timer (every 1s)
        self._dash_timer = QTimer()
        self._dash_timer.timeout.connect(self._update_dashboard)
        self._dash_timer.start(1000)

        main = W.QVBoxLayout(ui)
        main.setContentsMargins(0, 0, 0, 0)
        main.addWidget(frame)

        screen = self._app.primaryScreen().geometry()
        ui.move(screen.width() - 440, 40)

        self._objects_list.addItem("  (empty)")
        self._facts_list.addItem("  (empty)")
        self._history_list.addItem("  (no commands yet)")
        self._switch_tab(self._tab_btns[0])

    def _lbl(self, text, color):
        W = _QWidgets
        lbl = W.QLabel(text)
        lbl.setStyleSheet(f"color:{color};font-family:Consolas;font-size:10px;font-weight:bold;")
        return lbl

    def _ls(self):
        return "QListWidget{background:rgba(0,0,0,0.3);border:1px solid rgba(0,255,255,0.2);border-radius:6px;color:#e0e0e0;font-family:Consolas;font-size:10px;}QListWidget::item{padding:3px;}QListWidget::item:selected{background:rgba(0,255,255,0.15);}"

    def _switch_tab(self, active):
        for btn in self._tab_btns:
            btn.setStyleSheet(self._tab_style)
        active.setStyleSheet(self._tab_active)
        self._stack.setCurrentIndex(self._tab_btns.index(active))

    # ── Command Input ──────────────────────────────────────────────

    def _send_command(self):
        text = self._cmd_input.text().strip()
        if not text:
            return
        self._cmd_input.clear()
        parts = text.split()
        cmd, args = parts[0].lower(), parts[1:]

        if cmd == "remember" and len(args) >= 2:
            data = {}
            for a in args[1:]:
                if "=" in a:
                    k, v = a.split("=", 1)
                    try: data[k] = float(v) if "." in v else int(v)
                    except ValueError: data[k] = v
            self._command_bus.dispatch(Command(name="memory.remember", source="gui", params={"object_id": args[0], "data": data}))
        elif cmd == "recall" and args:
            self._command_bus.dispatch(Command(name="memory.recall", source="gui", params={"object_id": args[0]}))
        elif cmd == "forget" and args:
            self._command_bus.dispatch(Command(name="memory.forget", source="gui", params={"object_id": args[0]}))
        elif cmd == "list":
            self._command_bus.dispatch(Command(name="memory.list", source="gui"))
        elif cmd == "stats":
            self._command_bus.dispatch(Command(name="memory.stats", source="gui"))
        else:
            self._log.append(f"Unknown: {cmd}")

    # ── Events ─────────────────────────────────────────────────────

    def _on_command_event(self, event):
        p = event.payload
        cmd = p.get("command", "?")
        error = p.get("error")
        result = p.get("result")
        source = p.get("source", "")

        # Toast
        if event.type == "command.completed":
            self._show_toast(self._fmt_ok(cmd, result), "ok")
        elif event.type == "command.failed":
            self._show_toast(self._fmt_err(cmd, error), "error")

        # History — skip internal refresh commands
        if not source.startswith("gui_refresh"):
            ts = time.strftime("%H:%M:%S")
            st = "OK" if event.type == "command.completed" else "FAIL"
            self._history.append({"ts": ts, "cmd": cmd, "status": st, "error": error})
            self._update_history()

        # Auto-refresh memory views — only from user commands, not self-triggered
        if source not in ("gui_refresh", "gui") and cmd in ("memory.remember", "memory.forget"):
            self._command_bus.dispatch(Command(name="memory.list", source="gui_refresh"))
            self._command_bus.dispatch(Command(name="memory.stats", source="gui_refresh"))

    def _fmt_ok(self, cmd, result):
        if cmd == "memory.remember":
            oid = result.get("object_id", "") if isinstance(result, dict) else ""
            return f"Remembered {oid}" if oid else "Remembered"
        elif cmd == "memory.recall":
            if isinstance(result, dict) and result.get("object"):
                return f"Found: {result['object'].get('id', '?')}"
            return "Not found"
        elif cmd == "memory.forget":
            return "Forgotten"
        elif cmd == "memory.list":
            c = result.get("count", 0) if isinstance(result, dict) else 0
            return f"{c} objects"
        return f"{cmd} done"

    def _fmt_err(self, cmd, error):
        if "No handler" in (error or ""):
            return f"Unknown: {cmd}"
        return f"Failed: {cmd}"

    # ── Toast ──────────────────────────────────────────────────────

    def _show_toast(self, msg, level="ok"):
        if not self._toast_label:
            return
        colors = {"ok": "rgba(0,200,100,0.9)", "error": "rgba(220,50,50,0.9)",
                  "warning": "rgba(220,180,0,0.9)", "info": "rgba(0,150,255,0.9)"}
        self._toast_label.setStyleSheet(f"QLabel{{background:{colors.get(level, colors['ok'])};color:white;border-radius:6px;padding:6px;font-family:Consolas;font-size:10px;}}")
        self._toast_label.setText(msg)
        self._toast_label.show()
        self._toast_timer.start(3000)

    def _dismiss_toast(self):
        if self._toast_label:
            self._toast_label.hide()

    # ── History List ───────────────────────────────────────────────

    def _update_history(self):
        self._history_list.clear()
        entries = list(self._history)[-30:]
        if not entries:
            self._history_list.addItem("  (no commands yet)")
            return
        for e in reversed(entries):
            icon = "OK" if e["status"] == "OK" else "!!"
            txt = f"[{icon}] {e['ts']}  {e['cmd']}"
            if e.get("error"):
                txt += f"  {e['error']}"
            self._history_list.addItem(txt)

    # ── Objects ────────────────────────────────────────────────────

    def _update_objects(self, objects):
        self._objects_list.clear()
        if not objects:
            self._objects_list.addItem("  (empty)")
            return
        for obj in objects:
            pos = obj.get("position") or obj.get("data", {}).get("position", "")
            self._objects_list.addItem(f"  {obj.get('id', '?')}  {pos}")

    # ── Dashboard ─────────────────────────────────────────────────

    def _update_dashboard(self):
        if not self._running:
            return
        # Uptime
        secs = time.time() - self._boot_time
        h, rem = divmod(int(secs), 3600)
        m, s = divmod(rem, 60)
        self._d_uptime.setText(f"{h:02d}:{m:02d}:{s:02d}")

        # Commands/min — count from history (last 60s)
        now = time.time()
        recent_cmds = sum(
            1 for e in self._history
            if now - self._history_time(e) < 60
        ) if self._history else 0
        self._d_cmds.setText(str(recent_cmds))

        # Events/sec — approximate from history entries per second over last 10s
        recent_events = sum(
            1 for e in self._history
            if now - self._history_time(e) < 10
        ) if self._history else 0
        self._d_events.setText(f"{recent_events / 10:.1f}")

        # Memory stats
        mem = self._container.resolve("service.memory") if self._container else None
        if mem:
            objs = mem.list_objects()
            self._d_mem_obj.setText(str(len(objs)))
            facts = mem.list_facts() if hasattr(mem, 'list_facts') else []
            self._d_mem_fact.setText(str(len(facts)))
        else:
            self._d_mem_obj.setText("--")
            self._d_mem_fact.setText("--")

        # Plugin count + status list
        loader = self._container.resolve("plugin_loader") if self._container else None
        if loader:
            plugins = getattr(loader, 'loaded_plugins', [])
            self._d_plugins.setText(str(len(plugins)))
            self._d_plugin_list.clear()
            for p in plugins:
                label = getattr(p, 'name', '?')
                meta = getattr(p, 'metadata', None)
                ver = getattr(meta, 'version', '?') if meta else '?'
                cat = getattr(meta, 'category', '?') if meta else '?'
                self._d_plugin_list.addItem(f"  {label}  v{ver}  [{cat}]")
        else:
            self._d_plugins.setText("--")
            self._d_plugin_list.clear()

    def _history_time(self, entry):
        try:
            return time.mktime(time.strptime(entry["ts"], "%H:%M:%S"))
        except Exception:
            return 0

    # ── Lifecycle ──────────────────────────────────────────────────

    def update(self, dt):
        if self._app and self._running:
            self._app.processEvents()

    def stop(self):
        self._running = False
        if self._ui:
            self._ui.hide()

    def shutdown(self):
        self.stop()
        logger.info("GUIPlugin shutdown")