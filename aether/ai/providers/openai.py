"""OpenAI-compatible provider — lazy import, injectable client.

Design (Phase 2):
  - ``openai`` is NOT a hard dependency. The module imports it lazily inside
    ``_client()`` so the app never crashes when the package or API key is
    missing — ``available`` is simply ``False``.
  - Tests inject a fake client via ``OpenAIProvider(client=...)``; no network
    access happens anywhere in the test suite.
  - All failures are normalized to ``ProviderError`` so the service layer can
    map them to the ``ai.error`` event.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from aether.ai.models import AIResponse, ChatMessage, ChatRole, ToolCall
from aether.ai.provider import AIProvider, ProviderError
from aether.ai.tools import ToolDef

logger = logging.getLogger("Aether.AI.OpenAI")

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT = 30.0


class OpenAIProvider(AIProvider):
    """Chat-completion backend against the OpenAI API (or a fake client)."""

    name = "openai"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
        client: Any = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._injected_client = client
        self._timeout = timeout

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]]) -> "OpenAIProvider":
        config = config or {}
        model = str(config.get("model", DEFAULT_MODEL))
        timeout = float(config.get("timeout", DEFAULT_TIMEOUT))
        api_key_env = config.get("api_key_env", "OPENAI_API_KEY")
        api_key = os.environ.get(api_key_env) if api_key_env else None
        return cls(model=model, api_key=api_key, timeout=timeout)

    @property
    def available(self) -> bool:
        try:
            return self._client() is not None
        except ProviderError:
            return False

    def _client(self) -> Any:
        """Return an injected fake client, or build a real one lazily."""
        if self._injected_client is not None:
            return self._injected_client
        if not self._api_key:
            return None
        try:
            import openai  # lazy import — package is optional
        except ImportError:
            logger.warning("OpenAI package is not installed; provider unavailable")
            return None
        return openai.OpenAI(api_key=self._api_key, timeout=self._timeout)

    # -- wire translation (OpenAI adapter, in one place) --------------------

    @staticmethod
    def _to_wire_tool(tool: ToolDef) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    @staticmethod
    def _to_wire_message(message: ChatMessage) -> Dict[str, Any]:
        d: Dict[str, Any] = {"role": message.role.value, "content": message.content}
        if message.tool_calls:
            d["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    },
                }
                for call in message.tool_calls
            ]
        if message.tool_call_id:
            d["tool_call_id"] = message.tool_call_id
        return d

    @staticmethod
    def _parse_response(raw: Any) -> AIResponse:
        choices = getattr(raw, "choices", None)
        if not choices:
            raise ProviderError("malformed response: missing choices")
        message = getattr(choices[0], "message", None)
        if message is None:
            raise ProviderError("malformed response: missing message")

        text = (getattr(message, "content", None) or "").strip()

        tool_calls: List[ToolCall] = []
        for raw_call in getattr(message, "tool_calls", None) or []:
            call_id = getattr(raw_call, "id", None) or "call_unknown"
            function = getattr(raw_call, "function", None) or {}
            name = getattr(function, "name", "") or ""
            arguments = getattr(function, "arguments", None) or ""
            if not name:
                raise ProviderError("malformed response: tool call missing name")
            try:
                parsed = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError as exc:
                raise ProviderError(
                    f"malformed response: invalid tool arguments JSON for '{name}'"
                ) from exc
            if not isinstance(parsed, dict):
                raise ProviderError(
                    f"malformed response: tool arguments must be an object for '{name}'"
                )
            tool_calls.append(ToolCall(id=call_id, name=name, arguments=parsed))

        finish_reason = getattr(choices[0], "finish_reason", None) or "stop"
        if finish_reason == "tool_calls":
            return AIResponse(text=text, tool_calls=tool_calls, finish_reason="tool_calls")
        return AIResponse(text=text, tool_calls=tool_calls, finish_reason="stop")

    # -- main entry --------------------------------------------------------

    def respond(
        self, messages: List[ChatMessage], tools: List[ToolDef]
    ) -> AIResponse:
        client = self._client()
        if client is None:
            raise ProviderError("openai provider unavailable (no key or package)")

        wire_messages = [self._to_wire_message(m) for m in messages]
        kwargs: Dict[str, Any] = {"model": self._model, "messages": wire_messages}
        if tools:
            kwargs["tools"] = [self._to_wire_tool(t) for t in tools]
            kwargs["tool_choice"] = "auto"

        try:
            raw = client.chat.completions.create(**kwargs)
        except ProviderError:
            raise
        except Exception as exc:
            detail = str(exc) or type(exc).__name__
            raise ProviderError(f"openai api call failed: {detail}") from exc

        return self._parse_response(raw)
