"""Tests for ResultPipeline — process, handlers, remove_handler."""
from aether.core.command import Command
from aether.core.command_result import CommandResult
from aether.core.event_bus import EventBus, EventCategory
from aether.core.result_pipeline import ResultPipeline


def _make_command(name="test.cmd"):
    return Command(name=name, source="test")


def _ok_result(cmd):
    return CommandResult.ok(cmd.id, cmd.name, message="ok")


def _fail_result(cmd):
    return CommandResult.fail(cmd.id, cmd.name, error="fail")


class TestResultPipeline:
    def test_logs_and_publishes_event(self):
        bus = EventBus()
        pipeline = ResultPipeline(bus)
        events = []
        bus.subscribe_category(EventCategory.COMMAND, lambda e: events.append(e))

        cmd = _make_command()
        result = _ok_result(cmd)
        pipeline.process(cmd, result)
        assert len(events) == 1
        assert events[0].name == "CommandCompleted"

    def test_publishes_failure_event(self):
        bus = EventBus()
        pipeline = ResultPipeline(bus)
        events = []
        bus.subscribe_category(EventCategory.COMMAND, lambda e: events.append(e))

        cmd = _make_command()
        result = _fail_result(cmd)
        pipeline.process(cmd, result)
        assert events[0].name == "CommandFailed"

    def test_handler_called(self):
        bus = EventBus()
        pipeline = ResultPipeline(bus)
        calls = []
        pipeline.add_handler(lambda c, r: calls.append((c, r)))

        cmd = _make_command()
        result = _ok_result(cmd)
        pipeline.process(cmd, result)
        assert len(calls) == 1
        assert calls[0][0] is cmd

    def test_handler_exception_isolated(self):
        bus = EventBus()
        pipeline = ResultPipeline(bus)
        calls = []

        def bad(c, r):
            raise RuntimeError("oops")

        pipeline.add_handler(bad)
        pipeline.add_handler(lambda c, r: calls.append("ok"))

        cmd = _make_command()
        pipeline.process(cmd, _ok_result(cmd))
        assert calls == ["ok"]

    def test_remove_handler(self):
        bus = EventBus()
        pipeline = ResultPipeline(bus)
        calls = []
        handler = lambda c, r: calls.append(1)
        pipeline.add_handler(handler)
        assert pipeline.remove_handler(handler)

        cmd = _make_command()
        pipeline.process(cmd, _ok_result(cmd))
        assert calls == []

    def test_remove_nonexistent_handler(self):
        bus = EventBus()
        pipeline = ResultPipeline(bus)
        assert not pipeline.remove_handler(lambda c, r: None)
