"""Runtime validation — boots Aether and tests memory commands end-to-end."""

from aether.core.application import AetherApplication
from aether.core.command import Command


def test_boot_and_memory_commands():
    app = AetherApplication()
    app.boot()

    try:
        plugins = app.plugin_loader.loaded_plugins
        memory_plugin = [p for p in plugins if p.name == "memory_plugin"]
        assert len(memory_plugin) == 1, "MemoryPlugin not loaded"

        # Boot profiler should be available in AetherApplication
        bp = app.container.resolve("boot_profiler")
        assert bp.get_total_ms() > 0
        assert bp.get_stage_ms("boot_complete") is not None
        print(f"Boot total: {bp.get_total_ms():.1f}ms")

        cmd = app.command_bus

        # memory.remember
        result = cmd.dispatch_sync(Command(
            name="memory.remember", source="test",
            params={"key": "bottle", "value": '{"location": "desk", "color": "blue"}'},
        ))
        assert "Stored" in result["message"], f"remember failed: {result}"

        # memory.recall
        result = cmd.dispatch_sync(Command(
            name="memory.recall", source="test",
            params={"key": "bottle"},
        ))
        assert "Found" in result["message"], f"recall failed: {result}"

        # memory.stats
        result = cmd.dispatch_sync(Command(
            name="memory.stats", source="test",
            params={},
        ))
        assert "Memory Stats" in result["message"]

        # memory.search
        result = cmd.dispatch_sync(Command(
            name="memory.search", source="test",
            params={"query": "desk"},
        ))
        assert "result" in result["message"] or "No results" in result["message"]

        # memory.list
        result = cmd.dispatch_sync(Command(
            name="memory.list", source="test",
            params={},
        ))
        assert "keys" in result["message"]

        # system.boot.profile
        result = cmd.dispatch_sync(Command(
            name="system.boot.profile", source="test",
            params={},
        ))
        assert "Total boot time" in result["message"]

        # interaction.debug
        result = cmd.dispatch_sync(Command(
            name="interaction.debug", source="test",
            params={},
        ))
        assert "cursor" in result["message"].lower() or "Interaction" in result["message"]

        print("All runtime validation passed!")

    finally:
        app.shutdown()
