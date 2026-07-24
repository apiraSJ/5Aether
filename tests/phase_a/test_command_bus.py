"""Tests for CommandBus — dispatch, async handlers, exceptions, ResultPipeline."""
from aether.core.command import Command
from aether.core.command_bus import CommandBus, CommandNotRegisteredError
from aether.core.command_result import CommandResult
from aether.core.event_bus import EventBus, EventCategory
from aether.core.result_pipeline import ResultPipeline


def _make_command(name="test.cmd"):
    return Command(name=name, source="test")


class TestCommandBusSync:
    def test_dispatch_success(self):
        bus = CommandBus()
        bus.register("test.cmd", lambda c: CommandResult.ok(c.id, c.name, message="done"))
        result = bus.dispatch(_make_command())
        assert result.success
        assert result.message == "done"

    def test_dispatch_unregistered(self):
        bus = CommandBus()
        result = bus.dispatch(_make_command("nope"))
        assert not result.success
        assert "No handler" in result.error

    def test_dispatch_handler_exception(self):
        bus = CommandBus()

        def bad(c):
            raise RuntimeError("boom")

        bus.register("test.cmd", bad)
        result = bus.dispatch(_make_command())
        assert not result.success
        assert "boom" in result.error

    def test_dispatch_wrong_return_type(self):
        bus = CommandBus()
        bus.register("test.cmd", lambda c: "not a result")
        result = bus.dispatch(_make_command())
        assert not result.success
        assert "CommandResult" in result.error

    def test_unregister(self):
        bus = CommandBus()
        bus.register("test.cmd", lambda c: CommandResult.ok(c.id, c.name))
        bus.unregister("test.cmd")
        assert not bus.is_registered("test.cmd")

    def test_is_registered(self):
        bus = CommandBus()
        assert not bus.is_registered("x")
        bus.register("x", lambda c: CommandResult.ok(c.id, c.name))
        assert bus.is_registered("x")

    def test_duration_ms_set(self):
        bus = CommandBus()
        bus.register("test.cmd", lambda c: CommandResult.ok(c.id, c.name))
        result = bus.dispatch(_make_command())
        assert result.duration_ms >= 0

    def test_result_pipeline_called(self):
        bus_evt = EventBus()
        pipeline = ResultPipeline(bus_evt)
        bus = CommandBus(pipeline)

        events = []
        bus_evt.subscribe_category(EventCategory.COMMAND, lambda e: events.append(e))

        bus.register("test.cmd", lambda c: CommandResult.ok(c.id, c.name))
        bus.dispatch(_make_command())
        assert len(events) == 1
        assert events[0].name == "CommandCompleted"


class TestCommandBusAsync:
    def test_async_handler(self):
        bus = CommandBus()

        async def handler(c):
            return CommandResult.ok(c.id, c.name, message="async_ok")

        bus.register("test.cmd", handler)
        result = bus.dispatch(_make_command())
        assert result.success
        assert result.message == "async_ok"

    def test_async_handler_exception(self):
        bus = CommandBus()

        async def bad(c):
            raise RuntimeError("async_boom")

        bus.register("test.cmd", bad)
        result = bus.dispatch(_make_command())
        assert not result.success
        assert "async_boom" in result.error
