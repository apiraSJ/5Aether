"""AIProvider — pluggable backend for Aether's AI chat.

Phase 1 shipped EchoProvider, a deterministic offline backend that echoes the
user message. It lets the full pipeline (service, plugin, command bus, UI) be
exercised without any external API key or model download.

Phase 2 defines the provider contract that real backends implement:

    respond(messages, tools=[]) -> AIResponse

where ``AIResponse`` carries text and/or provider-neutral ``ToolCall`` objects.
Providers raise ``ProviderError`` on any failure (timeout, malformed response,
missing API key); the service layer maps that to the ``ai.error`` event.

Real backends (OpenAI, local LM) live in ``aether.ai.providers`` and are
selected via config ``ai.provider``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from aether.ai.models import AIResponse, ChatMessage, ChatRole
from aether.ai.tools import ToolDef


class ProviderError(Exception):
    """Raised when a provider cannot serve a request (API failure, malformed
    response, missing key, unknown provider name, ...)."""


class AIProvider(ABC):
    """Interface for a chat-completion backend."""

    name: str = "abstract"

    @property
    @abstractmethod
    def available(self) -> bool:
        """True when the backend can serve requests right now."""

    @abstractmethod
    def respond(
        self, messages: List[ChatMessage], tools: List[ToolDef]
    ) -> AIResponse:
        """Return an assistant response — text and/or tool calls."""


class EchoProvider(AIProvider):
    """Deterministic offline backend. Echoes the user's last message."""

    name = "echo"

    @property
    def available(self) -> bool:
        return True

    def respond(
        self, messages: List[ChatMessage], tools: List[ToolDef]
    ) -> AIResponse:
        user = [m for m in messages if m.role == ChatRole.USER]
        text = user[-1].content if user else ""
        return AIResponse(text=f"[Echo] {text}".strip(), finish_reason="stop")
