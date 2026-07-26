"""Tests for ResultPipeline — publish, handler groups, exception isolation."""
from aether.core.command import Command
from aether.core.command_result import CommandResult
from aether.core.result_pipeline import ResultPipeline


def _make_command(name="test.cmd"):
    return Command(name=name, source="test")


def _ok_result(cmd):
    return CommandResult.ok(cmd.id, cmd.name, message="ok", notification="toast")


def _fail_result(cmd):
    return CommandResult.fail(cmd.id, cmd.name, error="fail", notification="toast")


class TestResultPipeline:
    def test_handler_called_on_success(self):
        pipeline = ResultPipeline()
        calls = []
        pipeline.add_handler("success", lambda r: calls.append(r))

        cmd = _make_command()
        result = _ok_result(cmd)
        pipeline.publish(result)
        assert len(calls) == 1
        assert calls[0].success
        assert calls[0].command_name == "test.cmd"

    def test_handler_called_on_error(self):
        pipeline = ResultPipeline()
        calls = []
        pipeline.add_handler("error", lambda r: calls.append(r))

        cmd = _make_command()
        result = _fail_result(cmd)
        pipeline.publish(result)
        assert len(calls) == 1
        assert not calls[0].success

    def test_notification_handler_called_when_set(self):
        pipeline = ResultPipeline()
        calls = []
        pipeline.add_handler("notification", lambda r: calls.append(r))

        cmd = _make_command()
        result = _ok_result(cmd)
        pipeline.publish(result)
        assert len(calls) == 1

    def test_notification_handler_not_called_when_none(self):
        pipeline = ResultPipeline()
        calls = []
        pipeline.add_handler("notification", lambda r: calls.append(r))

        cmd = _make_command()
        result = CommandResult.ok(cmd.id, cmd.name)  # no notification
        pipeline.publish(result)
        assert len(calls) == 0

    def test_handler_exception_isolated(self):
        pipeline = ResultPipeline()
        calls = []

        def bad(r):
            raise RuntimeError("oops")

        pipeline.add_handler("success", bad)
        pipeline.add_handler("success", lambda r: calls.append("ok"))

        cmd = _make_command()
        pipeline.publish(_ok_result(cmd))
        assert calls == ["ok"]

    def test_multiple_handler_groups(self):
        pipeline = ResultPipeline()
        success_calls = []
        notification_calls = []
        pipeline.add_handler("success", lambda r: success_calls.append(1))
        pipeline.add_handler("notification", lambda r: notification_calls.append(1))

        cmd = _make_command()
        pipeline.publish(_ok_result(cmd))
        assert len(success_calls) == 1
        assert len(notification_calls) == 1

    def test_invalid_handler_group_raises(self):
        pipeline = ResultPipeline()
        try:
            pipeline.add_handler("nonexistent", lambda r: None)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_get_handlers(self):
        pipeline = ResultPipeline()
        handler = lambda r: None
        pipeline.add_handler("success", handler)
        handlers = pipeline.get_handlers("success")
        assert handler in handlers

    def test_get_all_handlers(self):
        pipeline = ResultPipeline()
        pipeline.add_handler("success", lambda r: None)
        pipeline.add_handler("error", lambda r: None)
        all_h = pipeline.get_all_handlers()
        assert "success" in all_h
        assert "error" in all_h
