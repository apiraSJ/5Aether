"""Local (offline) provider — Phase 2 stub.

The canonical model loader will land in a later phase. For now the stub keeps
``ai.provider: local`` a first-class config option without pretending to work.
"""

from __future__ import annotations

from typing import List

from aether.ai.models import AIResponse, ChatMessage
from aether.ai.provider import AIProvider, ProviderError
from aether.ai.tools import ToolDef


class LocalProvider(AIProvider):
    """Stub backend for local model inference (not implemented in Phase 2)."""

    name = "local"

    @property
    def available(self) -> bool:
        return False

    def respond(
        self, messages: List[ChatMessage], tools: List[ToolDef]
    ) -> AIResponse:
        raise ProviderError("local provider is not implemented yet")
