"""Provider factory — selects a backend from config ``ai.provider``.

Unknown provider names raise ``ProviderError`` so the plugin can fall back to
echo with a clear warning instead of crashing at boot.
"""

from __future__ import annotations

from typing import Any, Dict

from aether.ai.provider import AIProvider, ProviderError
from aether.ai.providers.echo import EchoProvider
from aether.ai.providers.local import LocalProvider
from aether.ai.providers.openai import OpenAIProvider


def create_provider(name: str, config: Dict[str, Any]) -> AIProvider:
    """Instantiate the named provider using the given config section."""
    name = (name or "echo").strip().lower()
    if name == "echo":
        return EchoProvider()
    if name == "openai":
        return OpenAIProvider.from_config(config.get("openai", {}))
    if name == "local":
        return LocalProvider()
    raise ProviderError(f"unknown provider: '{name}'")


__all__ = ["create_provider", "EchoProvider", "LocalProvider", "OpenAIProvider"]
