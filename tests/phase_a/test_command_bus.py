"""Tests for CommandBus — dispatch, async handlers, exceptions, ResultPipeline."""
from aether.core.command import Command
from aether.core.command_bus import CommandBus
from aether.core.command_result import CommandResult
from aether.core.event_bus_v2 import EventBus, Event
from aether.core.result_pipeline import ResultPipeline


def _make_command(name="test.cmd"):
    return Command(name=name, source="test")


class TestCommandBusSync:
    def test_dispatch_handler_exception(self):
        bus = CommandBus()

        def bad(c):
            raise RuntimeError("boom")

        bus.register_handler("test.cmd", bad)
        cmd = _make_command()
        try:
            bus.dispatch_sync(cmd, timeout=5.0)
            assert False, "Should have raised"
        except RuntimeError as e:
            assert "boom" in str(e)
        assert cmd.status == "FAILED"
        assert "boom" in cmd.error

    def test_unregister(self):
        bus = CommandBus()
        bus.register_handler("test.cmd", lambda c: "ok")
        bus.unregister_handler("test.cmd")
        assert not bus.is_registered("test.cmd")

    def test_is_registered(self):
        bus = CommandBus()
        assert not bus.is_registered("x")
        bus.register_handler("x", lambda c: "ok")
        assert bus.is_registered("x")

    def test_queue_depth(self):
        bus = CommandBus()
        assert bus.queue_depth == 0
        bus.dispatch(_make_command())
        assert bus.queue_depth == 1

    def test_update_processes_queue(self):
        bus = CommandBus()
        bus.register_handler("test.cmd", lambda c: "ok")
        bus.dispatch(_make_command())
        processed = bus.update()
        assert processed == 1
        assert bus.queue_depth == 0

    def test_clear_history(self):
        bus = CommandBus()
        bus.register_handler("test.cmd", lambda c: "ok")
        bus.dispatch_sync(_make_command())
        removed = bus.clear_history(max_age=-1)
        assert removed >= 1


class TestCommandBusResultPipeline:
    def test_result_pipeline_called_on_success(self):
        pipeline = ResultPipeline()
        bus = CommandBus(result_pipeline=pipeline)

        results = []
        pipeline.add_handler("success", lambda r: results.append(r))

        bus.register_handler("test.cmd", lambda c: "ok")
        bus.dispatch_sync(_make_command())
        assert len(results) == 1
        assert results[0].success

    def test_result_pipeline_called_on_failure(self):
        pipeline = ResultPipeline()
        bus = CommandBus(result_pipeline=pipeline)

        results = []
        pipeline.add_handler("error", lambda r: results.append(r))

        def bad(c):
            raise RuntimeError("boom")

        bus.register_handler("test.cmd", bad)
        try:
            bus.dispatch_sync(_make_command())
        except RuntimeError:
            pass
        assert len(results) == 1
        assert not results[0].success
