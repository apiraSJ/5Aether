# Phase 2 — Real LLM + Agent Tool Loop

Status: **Approved for implementation** · Decisions locked by review.
Baseline: **738 passed** · Target: **~765+**.

## Locked decisions (review)

1. **Breaking provider API** — `AIProvider.respond(messages, tools=[]) -> AIResponse`. Single path; update all tests.
2. **Transient tool messages** — tool calls/results exist only inside the turn; session history stays `user → assistant`.
3. **Fake OpenAI client injection** — `OpenAIProvider(client=...)` for tests; no `openai` package required, no network in CI. `available=False` when package/key missing — never crashes the app.

## Architecture target

```
User → AIPlugin → AIService
                    ├── ContextBuilder (System/Workspace/Task/Memory; Vision optional)
                    ├── ToolRegistry → ToolExecutor → CommandBus
                    └── AIProvider (Echo | OpenAI | Local-stub)
                          → AIResponse {text, tool_calls, finish_reason}
```

---

## A. `aether/ai/models.py` — canonical models

- `ToolCall` dataclass: `id: str`, `name: str`, `arguments: Dict[str, Any]` (parsed JSON object, never raw string) + `to_dict()`.
- `AIResponse` dataclass: `text: str`, `tool_calls: List[ToolCall] = []`, `finish_reason: str = "stop"` (`"stop" | "tool_calls"`).
- `ChatRole.TOOL = "tool"`.
- `ChatMessage` gains optional `tool_calls: List[ToolCall]` (assistant) and `tool_call_id: Optional[str]` (tool result); `to_dict()` serializes them.
- `AIResult` gains `tool_rounds: int = 0`.
- **No OpenAI-specific types in this module.**

## B. `aether/ai/provider.py` — contract

- `ProviderError(Exception)` — raised on timeout / malformed response / missing key / API failure.
- `AIProvider`:
  ```python
  @abstractmethod
  def respond(self, messages: List[ChatMessage], tools: List[ToolDef]) -> AIResponse
  ```
- `EchoProvider` — returns `AIResponse(text=f"[Echo] {text}", finish_reason="stop")`, never tool calls. Stays in `provider.py` for backward-compat imports.

## C. `aether/ai/providers/` — implementations + factory

- `echo.py` — thin re-export of `EchoProvider` (satisfies the package layout).
- `openai.py` — `OpenAIProvider`:
  - `__init__(model="gpt-4o-mini", api_key=None, client=None, timeout=30.0)`; `from_config({"model","api_key_env","timeout"})` reads key from env.
  - `_client()` — returns injected fake if present; else lazy-imports `openai` (returns `None` if missing or no key). `available` = client is not None.
  - Canonical `ToolDef` → OpenAI `{type:"function", function:{name,description,parameters}}` (adapter only).
  - `respond()` → `client.chat.completions.create(model=..., messages=..., tools=..., tool_choice="auto")`; wraps exceptions in `ProviderError`; parses `message.content` + `message.tool_calls` (`json.loads`; malformed → `ProviderError`).
  - Wire message serialization includes `tool_calls` (assistant) and `tool_call_id` (tool) so the loop is replayable.
- `local.py` — stub: `available=False`, `respond()` raises `ProviderError("local provider not implemented in Phase 2")`.
- `__init__.py` — `create_provider(name, config) -> AIProvider`:
  `echo` → EchoProvider · `openai` → `OpenAIProvider.from_config(config.get("openai", {}))` · `local` → LocalProvider · unknown → `ProviderError`.

## D. `aether/ai/context.py` — sections

- `ContextBuilder.build(..., workspace=None, tasks=None)` adds optional `workspace`/`tasks` dicts.
- New `system_text(workspace=None, tasks=None) -> str` composes system prompt + optional `[Workspace]` / `[Tasks]` JSON blocks.
- All sections optional; **no camera / vision / CV import anywhere**. AIService passes `None` for now (extension + tests only).

## E. `aether/ai/tools.py` — argument validation

- In `ToolExecutor.execute`, after whitelist + registration checks, validate `required` keys from `ToolDef.parameters`:
  `missing = [k for k in required if k not in args]` → `ToolResult(success=False, error="invalid arguments: missing required key '<k>'")`.
- Only when a registry is present; existing registry-less executor tests unaffected.

## F. `aether/ai/service.py` — bounded agent loop

- `__init__` gains `max_tool_rounds: int = 5`.
- `chat()`:
  - empty message → ERROR (unchanged).
  - `provider_available is False` → short-circuit `AIState.ERROR`, emit `ai.error {error: "provider_unavailable"}`, `AIResult(ERROR)`.
  - else build context + messages, call `_run_agent_loop(messages, session_id)`, append final `ASSISTANT` text to history, emit `ai.thinking.completed` + `ai.response.ready`.
- `_run_agent_loop(messages, session_id)`:
  ```python
  tools = self._tool_registry.list_for_llm() if self._tool_registry else []
  rounds = 0
  while True:
      response = self._provider.respond(messages, tools)
      if not response.tool_calls:
          return response.text, rounds
      rounds += 1
      if rounds > self._max_tool_rounds:
          raise ProviderError(f"max tool rounds exceeded ({self._max_tool_rounds})")
      messages.append(ChatMessage(ASSISTANT, response.text, tool_calls=response.tool_calls))
      for call in response.tool_calls:
          emit ai.tool.started
          result = self.execute_tool(call.name, call.arguments)   # structured, never raises
          emit ai.tool.completed {success, duration_ms}
          messages.append(ChatMessage(TOOL, json.dumps(result.to_dict()), tool_call_id=call.id))
  ```
  - No `while True`. Loop exhaustion → `ProviderError` → caught by `chat()` → `AIState.ERROR` + `ai.error`.
  - Tool messages are **transient** — never written to session history.
- `stream()` unchanged (still `started → delta → completed` / `started → error`), now driven by the loop's final text.

## G. `aether/core/event_type.py`

- Add `AI_TOOL_STARTED = "ai.tool.started"` and `AI_TOOL_COMPLETED = "ai.tool.completed"` to the AI section.

## H. `aether/plugins/ai_plugin.py` + `config/ai.yaml`

- Use `create_provider(name, config)`; catch `ProviderError` from the factory → log error, fall back to echo (boot resilience).
- Read `ai.max_tool_rounds` (default 5) → pass to `AIService`.
- Metadata version → `"2.0"`, description mentions agent tool loop.
- `config/ai.yaml`: add `max_tool_rounds: 5`. `default.yaml`/`vision.yaml` unchanged (still `provider: echo`).

## I. Tests

- Update `tests/test_ai_plugin.py`:
  - `_FailingProvider.respond(self, messages, tools)` signature; `available = True` (so the exception path in `chat()` is exercised).
  - Existing provider-failure / stream / session tests keep passing.
- New `tests/test_ai_providers.py`:
  - Echo: text, no tool_calls, finish_reason stop.
  - OpenAI (fake client): success text; tool_calls parse; API failure → `ProviderError`; malformed response (no choices) → `ProviderError`; malformed tool arguments → `ProviderError`; timeout → `ProviderError`; missing key / missing package → `available is False`; `from_config` reads model + env key; wire translation (tools schema, assistant tool_calls, tool messages).
  - Local: `available is False`, `respond` raises.
  - Factory: echo/openai/local/unknown → `ProviderError`.
- New `tests/test_ai_agent_loop.py`:
  - `ScriptedProvider` helper (returns scripted `AIResponse`s; can inspect the message list).
  - text → done (`tool_rounds == 0`); one tool → final; multiple tools (2+ rounds); max rounds → `AIResult ERROR`; provider failure after tool → `ERROR`; tool failure → LLM receives structured `TOOL` message with `{success:false}`; tools are passed to provider as canonical `list_for_llm()`.
  - Real `ToolRegistry` + `ToolExecutor` wired via fake dispatcher to prove CommandBus execution path.
- Vision independence test (in agent-loop file):
  - Scan `aether/ai/**` for forbidden import tokens (`mediapipe`, `ultralytics`, `yolo`, `cv2`, `camera`); assert none.

## Files touched

- Modify: `aether/ai/models.py`, `provider.py`, `service.py`, `context.py`, `tools.py`, `aether/plugins/ai_plugin.py`, `aether/core/event_type.py`, `config/ai.yaml`, `tests/test_ai_plugin.py`
- New: `aether/ai/providers/{__init__,echo,openai,local}.py`, `tests/test_ai_providers.py`, `tests/test_ai_agent_loop.py`

## Definition of done

- `chat()` runs a bounded agent loop; tool calls route through registry → executor → CommandBus; results return to the LLM as structured `TOOL` messages.
- OpenAI provider works against an injected client; app never crashes when `openai`/key missing.
- Vision fully off — AI tests pass with no CV imports in `aether/ai/`.
- Full suite ≥ 765 passing.
