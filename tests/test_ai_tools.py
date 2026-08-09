"""Tests for canonical AI tools — ToolDef, ToolRegistry, ToolExecutor.

Phase 1.5 decisions under test:
  - Explicit whitelist: non-whitelisted commands are never registered or run.
  - Structured results: {success, data, error}; no internal exception details.
  - ToolExecutor decoupled from CommandBus via an injected dispatcher.
"""

from __future__ import annotations

import pytest

from aether.ai.tools import (
    DEFAULT_TOOL_SAFE_COMMANDS,
    ToolDef,
    ToolExecutor,
    ToolRegistry,
)
from aether.core.command import Command

EXPECTED_TOOLS = {"ui.panel.toggle", "memory.recall", "memory.search", "system.ping", "system.info"}


def make_dispatcher(handlers: dict, fail: tuple = ()) -> callable:
    """Build a fake CommandBus-like dispatcher for tests."""
    def dispatch(command: Command):
        if command.name in fail:
            raise TimeoutError("simulated timeout")
        if command.name in handlers:
            return handlers[command.name](command)
        cmd = Command(name=command.name, source="test")
        cmd.status = "COMPLETED"
        cmd.error = "No handler registered"
        return cmd
    return dispatch


class TestToolDef:
    def test_to_dict_contains_schema_fields(self):
        tool = ToolDef("system.ping", "desc", {"type": "object"})
        d = tool.to_dict()
        assert d == {"name": "system.ping", "description": "desc", "parameters": {"type": "object"}}


class TestToolRegistry:
    def test_default_allowlist_is_explicit(self):
        assert DEFAULT_TOOL_SAFE_COMMANDS == frozenset(EXPECTED_TOOLS)

    def test_preloads_whitelisted_schemas(self):
        reg = ToolRegistry()
        assert reg.count == 5
        for name in EXPECTED_TOOLS:
            assert reg.get(name) is not None

    def test_get_unknown_returns_none(self):
        reg = ToolRegistry()
        assert reg.get("totally.missing") is None

    def test_register_refuses_non_whitelisted(self):
        reg = ToolRegistry()
        ok = reg.register(ToolDef("system.shutdown", "quit", {"type": "object"}))
        assert ok is False
        assert reg.get("system.shutdown") is None

    def test_register_allows_whitelisted(self):
        reg = ToolRegistry()
        custom = ToolDef(
            "system.ping", "custom ping", {"type": "object", "properties": {}},
        )
        assert reg.register(custom) is True
        assert reg.get("system.ping").description == "custom ping"

    def test_list_for_llm_is_provider_agnostic(self):
        reg = ToolRegistry()
        items = reg.list_for_llm()
        assert {i["name"] for i in items} == EXPECTED_TOOLS
        for item in items:
            assert "description" in item
            assert "parameters" in item

    def test_custom_allowlist_restricts_preload(self):
        reg = ToolRegistry(allowlist=["memory.search"])
        assert reg.get("memory.search") is not None
        assert reg.get("system.ping") is None
        assert reg.count == 1


class TestToolExecutor:
    def test_execute_success_wraps_result(self):
        ex = ToolExecutor(make_dispatcher({"system.ping": lambda c: {"message": "pong"}}))
        result = ex.execute("system.ping")
        assert result.success is True
        assert result.data == {"message": "pong"}
        assert result.error is None
        assert result.tool == "system.ping"

    def test_execute_passes_args_as_params(self):
        seen = {}

        def handler(cmd):
            seen["params"] = cmd.params
            seen["source"] = cmd.source
            return {"ok": True}

        ex = ToolExecutor(make_dispatcher({"memory.recall": handler}))
        ex.execute("memory.recall", {"key": "bottle"})
        assert seen["params"] == {"key": "bottle"}
        assert seen["source"] == "ai.tool"

    def test_execute_empty_name(self):
        ex = ToolExecutor(make_dispatcher({}))
        result = ex.execute("   ")
        assert result.success is False
        assert result.error == "empty tool name"

    def test_execute_non_whitelisted_blocked(self):
        ex = ToolExecutor(make_dispatcher({}), registry=ToolRegistry())
        result = ex.execute("system.shutdown")
        assert result.success is False
        assert "not tool-safe" in result.error
        assert result.data is None

    def test_execute_whitelisted_but_unregistered(self):
        reg = ToolRegistry(allowlist=["system.shutdown", "memory.search"])
        ex = ToolExecutor(make_dispatcher({}), registry=reg)
        result = ex.execute("system.shutdown")
        assert result.success is False
        assert "not registered" in result.error

    def test_execute_no_handler_returns_failure(self):
        ex = ToolExecutor(make_dispatcher({}))
        result = ex.execute("system.info")  # no handler registered
        assert result.success is False
        assert "handler" in result.error.lower()

    def test_execute_dispatcher_raises_returns_type_name_only(self):
        ex = ToolExecutor(make_dispatcher({}, fail=("system.ping",)))
        result = ex.execute("system.ping")
        assert result.success is False
        assert result.error == "TimeoutError"
        assert "simulated timeout" not in result.error  # internals not leaked

    def test_execute_dispatcher_returns_none_is_failure(self):
        ex = ToolExecutor(make_dispatcher({"system.ping": lambda c: None}))
        result = ex.execute("system.ping")
        assert result.success is False
        assert result.error == "tool returned no result"
