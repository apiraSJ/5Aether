"""AIChatPanelWidget — real Qt widget for the AI Chat panel.

Layout:
    ┌─────────────────────────────────────────────────┐
    │ ┌─────────────────────────────────────────────┐ │
    │ │ I am Aether. I can see your hands.          │ │
    │ └─────────────────────────────────────────────┘ │
    │ ┌─────────────────────────────────────────────┐ │
    │ │ Show workspace panels                       │ │
    │ └─────────────────────────────────────────────┘ │
    │ ┌─────────────────────────────────────────────┐ │
    │ │ You have 5 panels: Memory, AI Chat, Tasks…  │ │
    │ └─────────────────────────────────────────────┘ │
    │ [Type a message...]                             │
    └─────────────────────────────────────────────────┘

Backend: dispatches ai.chat via CommandBus,
         receives streaming tokens via EventBus.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QPushButton, QTextBrowser, QTextEdit, QVBoxLayout, QWidget,
)

from aether.ui.panel.panel_widget import PanelWidget
from aether.ui.ui_context import UIContext


class AIChatPanelWidget(PanelWidget):
    """AI Chat panel with conversation history and text input."""

    def __init__(self, panel_id: str, panel_type: str, label: str, parent=None) -> None:
        self._command_bus = None
        self._event_bus = None
        self._ai_worker = None
        super().__init__(panel_id, panel_type, label, parent)

    def _build_content(self) -> None:
        layout = self._content_layout

        # Chat history
        self._history = QTextBrowser()
        self._history.setStyleSheet(self._history_style())
        self._history.setOpenExternalLinks(False)
        layout.addWidget(self._history, 1)

        # M1 Memory UX: one click reconstructs the user's last work context.
        self._continue_btn = QPushButton("Continue My Work")
        self._continue_btn.setFixedHeight(26)
        self._continue_btn.setStyleSheet(self._continue_style())
        self._continue_btn.clicked.connect(self._on_continue_work)
        layout.addWidget(self._continue_btn)

        # Input area
        self._input = QTextEdit()
        self._input.setPlaceholderText("Type a message...")
        self._input.setFixedHeight(60)
        self._input.setStyleSheet(self._input_style())
        self._input.installEventFilter(self)
        layout.addWidget(self._input)

        # Mock welcome message
        self._append_bot("I am Aether. I can see your hands.\n"
                         "Ask me about what I see or what I remember.")

    def _append_user(self, text: str) -> None:
        self._history.append(
            f'<div style="color:rgba(96,165,250,200);margin:4px 0;">'
            f'▸ {text}</div>'
        )

    def _append_bot(self, text: str) -> None:
        self._history.append(
            f'<div style="color:rgba(200,210,230,200);margin:4px 0;">'
            f'{text}</div>'
        )

    def eventFilter(self, obj, event) -> bool:
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        if obj is self._input and event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_Return and not (event.modifiers() & Qt.ShiftModifier):
                self._send_message()
                return True
        return super().eventFilter(obj, event)

    def _send_message(self) -> None:
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._input.clear()
        self._append_user(text)

        # Phase B1: async path — submit to the background AI worker so the
        # GUI thread is never blocked on the LLM / agent loop. The reply is
        # appended when ai.response.ready arrives (marshaled to the main
        # thread by EventBus.flush() inside the tick).
        if self._ai_worker is not None:
            self._ai_worker.submit(text, session_id="default")
        elif self._command_bus:
            # Fallback (tests / headless): synchronous command path.
            from aether.core.command import Command
            result = self._command_bus.dispatch_sync(Command(
                name="ai.chat", source="gui", params={"message": text}
            ))
            response = result.get("message", "[no response]")
            self._append_bot(response)
        else:
            # Fallback: local echo
            self._append_bot(f"[echo] {text}")

    def wire_services(self, command_bus: Any, event_bus: Any) -> None:
        """Backward-compatible alias for bind_context()."""
        self.bind_context(UIContext(command_bus=command_bus, event_bus=event_bus))

    def bind_context(self, context: UIContext) -> None:
        self._command_bus = context.command_bus
        self._event_bus = context.event_bus
        self._ai_worker = context.ai_worker

        if self._event_bus is not None:
            # Subscribe once (idempotent) — replies arrive on the main thread
            # via EventBus.flush() inside the tick.
            self._event_bus.subscribe("ai.response.ready", self._on_ai_response)

    def _on_ai_response(self, event) -> None:
        """Append an assistant reply received asynchronously from the worker."""
        payload = event.payload if hasattr(event, "payload") else {}
        reply = payload.get("response") or payload.get("message") or ""
        if reply:
            self._append_bot(reply)

    def _on_continue_work(self) -> None:
        """Reconstruct the last work session into the chat (M1 Memory UX).

        Dispatches memory.continue (no params) synchronously via the
        CommandBus and renders the reconstructed context as a bot message —
        the user continues work without re-explaining their context.
        """
        if self._command_bus is None:
            self._append_bot("[Continue My Work] command bus not bound.")
            return
        from aether.core.command import Command
        result = self._command_bus.dispatch_sync(Command(
            name="memory.continue", source="gui", params={},
        ))
        response = result.get("message", "") if isinstance(result, dict) else ""
        if response:
            self._append_bot(response)
        else:
            self._append_bot("[Continue My Work] no work context was recovered.")

    # ── Styles ────────────────────────────────────────────────────

    @staticmethod
    def _history_style() -> str:
        return (
            "QTextBrowser{background:transparent;border:1px solid rgba(60,65,85,100);"
            "border-radius:4px;color:rgba(200,210,230,200);font-size:9px;padding:6px;}"
        )

    @staticmethod
    def _continue_style() -> str:
        return (
            "QPushButton{background:rgba(45,55,80,200);border:1px solid "
            "rgba(96,165,250,140);border-radius:4px;color:rgba(200,210,230,220);"
            "font-size:9px;}"
            "QPushButton:hover{background:rgba(60,75,110,220);}"
        )

    @staticmethod
    def _input_style() -> str:
        return (
            "QTextEdit{background:rgba(20,22,35,200);border:1px solid rgba(60,65,85,160);"
            "border-radius:4px;padding:4px 8px;color:rgba(200,210,230,220);"
            "font-size:9px;}"
        )
