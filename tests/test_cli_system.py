"""Tests for Phase 3A: CLI + Intent Resolver + CommandRegistry."""

import time

from aether.core.command_registry import CommandRegistry, CommandInfo
from aether.core.intent_resolver import IntentResult
from aether.core.event_bus_v2 import EventBus, Event
from aether.core.event_type import EventType
from aether.core.command import Command
from aether.core.command_bus import CommandBus
from aether.core.result_pipeline import ResultPipeline
from aether.core.service_container import ServiceContainer
from aether.plugins.rule_intent_plugin import RuleIntentPlugin
from aether.plugins.intent_resolver_plugin import IntentResolverPlugin
from aether.plugins.system_commands_plugin import SystemCommandPlugin


# ── Fixtures ──────────────────────────────────────────────────────────

def _make_container():
    c = ServiceContainer()
    bus = EventBus(queued=True)
    pipeline = ResultPipeline()
    cmd_bus = CommandBus(result_pipeline=pipeline, event_bus=bus)
    c.register_instance("event_bus", bus)
    c.register_instance("command_bus", cmd_bus)
    c.register_instance("result_pipeline", pipeline)
    c.register_instance("config", {})
    return c, bus, cmd_bus


# ── CommandRegistry tests ─────────────────────────────────────────────

def test_registry_register_and_lookup():
    reg = CommandRegistry()
    c, _, _ = _make_container()
    reg.initialize(c)

    reg.register_simple("test.cmd", description="A test command", category="test")
    assert reg.is_registered("test.cmd")
    assert not reg.is_registered("nonexistent")
    info = reg.resolve("test.cmd")
    assert info is not None
    assert info.name == "test.cmd"
    assert info.description == "A test command"


def test_registry_aliases():
    reg = CommandRegistry()
    c, _, _ = _make_container()
    reg.initialize(c)

    reg.register(CommandInfo(
        name="system.help", aliases=("h", "?"), category="system"
    ))
    assert reg.is_registered("h")
    assert reg.is_registered("?")
    assert reg.resolve("h").name == "system.help"


def test_registry_autocomplete():
    reg = CommandRegistry()
    c, _, _ = _make_container()
    reg.initialize(c)

    reg.register_simple("memory.recall", category="memory")
    reg.register_simple("memory.remember", category="memory")
    reg.register_simple("memory.delete", category="memory")
    reg.register_simple("system.help", category="system")

    matches = reg.complete("mem")
    assert len(matches) == 3
    assert "memory.recall" in matches
    assert "memory.remember" in matches

    matches = reg.complete("sys")
    assert len(matches) == 1
    assert "system.help" in matches


def test_registry_help():
    reg = CommandRegistry()
    c, _, _ = _make_container()
    reg.initialize(c)

    reg.register_simple("test.a", description="Alpha", category="test")
    reg.register_simple("test.b", description="Beta", category="test")
    reg.register_simple("other.c", description="Gamma", category="other")

    # All help
    help_text = reg.get_help()
    assert "test.a" in help_text
    assert "other.c" in help_text

    # Category filter
    help_text = reg.get_help("test")
    assert "test.a" in help_text
    assert "other.c" not in help_text


def test_registry_unregister():
    reg = CommandRegistry()
    c, _, _ = _make_container()
    reg.initialize(c)

    reg.register(CommandInfo(name="x.cmd", aliases=("x",)))
    assert reg.is_registered("x.cmd")
    assert reg.is_registered("x")

    reg.unregister("x.cmd")
    assert not reg.is_registered("x.cmd")
    assert not reg.is_registered("x")


# ── RuleIntentPlugin tests ────────────────────────────────────────────

def test_rule_intent_find():
    plugin = RuleIntentPlugin()
    c, _, _ = _make_container()
    plugin.initialize(c)

    result = plugin.resolve("find phone")
    assert result is not None
    assert result.command_name == "memory.recall"
    assert result.params.get("query") == "phone"
    assert result.source == "rule"
    assert result.confidence > 0.8


def test_rule_intent_where_is():
    plugin = RuleIntentPlugin()
    c, _, _ = _make_container()
    plugin.initialize(c)

    result = plugin.resolve("where is my keys")
    assert result is not None
    assert result.command_name == "memory.recall"
    assert result.params.get("query") == "my keys"


def test_rule_intent_remember():
    plugin = RuleIntentPlugin()
    c, _, _ = _make_container()
    plugin.initialize(c)

    result = plugin.resolve("remember bottle at desk")
    assert result is not None
    assert result.command_name == "memory.remember"
    assert result.params.get("name") == "bottle"
    assert result.params.get("location") == "desk"


def test_rule_intent_forget():
    plugin = RuleIntentPlugin()
    c, _, _ = _make_container()
    plugin.initialize(c)

    result = plugin.resolve("forget bottle")
    assert result is not None
    assert result.command_name == "memory.forget"
    assert result.params.get("query") == "bottle"


def test_rule_intent_help():
    plugin = RuleIntentPlugin()
    c, _, _ = _make_container()
    plugin.initialize(c)

    result = plugin.resolve("help")
    assert result is not None
    assert result.command_name == "system.help"

    result = plugin.resolve("help memory")
    assert result is not None
    assert result.params.get("category") == "memory"


def test_rule_intent_quit():
    plugin = RuleIntentPlugin()
    c, _, _ = _make_container()
    plugin.initialize(c)

    for word in ("quit", "exit", "shutdown"):
        result = plugin.resolve(word)
        assert result is not None, f"'{word}' should resolve"
        assert result.command_name == "system.shutdown"


def test_rule_intent_status():
    plugin = RuleIntentPlugin()
    c, _, _ = _make_container()
    plugin.initialize(c)

    result = plugin.resolve("status")
    assert result is not None
    assert result.command_name == "system.status"


def test_rule_intent_scan():
    plugin = RuleIntentPlugin()
    c, _, _ = _make_container()
    plugin.initialize(c)

    result = plugin.resolve("scan")
    assert result is not None
    assert result.command_name == "vision.scan"


def test_rule_intent_unknown():
    plugin = RuleIntentPlugin()
    c, _, _ = _make_container()
    plugin.initialize(c)

    result = plugin.resolve("xyzzy foobar")
    assert result is None


def test_rule_intent_empty():
    plugin = RuleIntentPlugin()
    c, _, _ = _make_container()
    plugin.initialize(c)

    assert plugin.resolve("") is None
    assert plugin.resolve("   ") is None


def test_rule_intent_can_resolve():
    plugin = RuleIntentPlugin()
    c, _, _ = _make_container()
    plugin.initialize(c)

    assert plugin.can_resolve("find phone")
    assert not plugin.can_resolve("xyzzy foobar")


# ── IntentResolverPlugin integration tests ─────────────────────────────

def test_intent_resolver_integration():
    c, bus, cmd_bus = _make_container()

    # Load dependencies
    sys_plugin = SystemCommandPlugin()
    sys_plugin.initialize(c)

    rule_plugin = RuleIntentPlugin()
    rule_plugin.initialize(c)

    resolver_plugin = IntentResolverPlugin()
    resolver_plugin.initialize(c)

    # Emit CLI_INPUT_RECEIVED
    bus.publish(Event(
        type=EventType.CLI_INPUT_RECEIVED,
        payload={"text": "help", "context": ""},
        source="cli",
    ))

    bus.flush()
    cmd_bus.update()

    # Check that command was dispatched and processed
    assert cmd_bus.processed_count >= 1


def test_intent_resolver_unknown_input():
    c, bus, cmd_bus = _make_container()

    sys_plugin = SystemCommandPlugin()
    sys_plugin.initialize(c)

    rule_plugin = RuleIntentPlugin()
    rule_plugin.initialize(c)

    resolver_plugin = IntentResolverPlugin()
    resolver_plugin.initialize(c)

    failed_events = []
    bus.subscribe(EventType.INTENT_FAILED, lambda e: failed_events.append(e))

    bus.publish(Event(
        type=EventType.CLI_INPUT_RECEIVED,
        payload={"text": "xyzzy foobar", "context": ""},
        source="cli",
    ))
    bus.flush()  # delivers CLI_INPUT_RECEIVED → IntentResolver publishes INTENT_FAILED to queue
    bus.flush()  # delivers INTENT_FAILED to subscriber
    cmd_bus.update()

    assert len(failed_events) == 1
    assert "No matching intent" in failed_events[0].payload.get("reason", "")


def test_intent_resolver_dispatches_command():
    c, bus, cmd_bus = _make_container()

    sys_plugin = SystemCommandPlugin()
    sys_plugin.initialize(c)

    rule_plugin = RuleIntentPlugin()
    rule_plugin.initialize(c)

    resolver_plugin = IntentResolverPlugin()
    resolver_plugin.initialize(c)

    completed = []
    bus.subscribe(EventType.COMMAND_COMPLETED, lambda e: completed.append(e))

    bus.publish(Event(
        type=EventType.CLI_INPUT_RECEIVED,
        payload={"text": "ping", "context": ""},
        source="cli",
    ))
    bus.flush()  # CLI_INPUT_RECEIVED → IntentResolver → dispatch
    bus.flush()  # any cascade events
    cmd_bus.update()  # process command → publishes COMMAND_COMPLETED
    bus.flush()  # deliver COMMAND_COMPLETED

    assert len(completed) >= 1
    assert completed[0].payload.get("command") == "system.ping"


# ── CommandRegistry status ─────────────────────────────────────────────

def test_registry_status():
    reg = CommandRegistry()
    c, _, _ = _make_container()
    reg.initialize(c)

    reg.register_simple("a", category="x")
    reg.register_simple("b", category="x")
    reg.register_simple("c", category="y")

    status = reg.get_status()
    assert status["commands_registered"] == 3
    assert "x" in status["categories"]
    assert "y" in status["categories"]


# ── IntentResult dataclass ─────────────────────────────────────────────

def test_intent_result_fields():
    r = IntentResult(
        intent="memory.find",
        command_name="memory.recall",
        params={"query": "phone"},
        confidence=0.95,
        source="rule",
        raw_input="find phone",
    )
    assert r.intent == "memory.find"
    assert r.confidence == 0.95
    assert r.raw_input == "find phone"
