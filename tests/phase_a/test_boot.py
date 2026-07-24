"""Boot smoke test — verifies AetherApp boots, dispatches, and shuts down."""
from aether.app import AetherApp
from aether.core.command import Command
from aether.core.service_container import ServiceNames


class TestAetherBoot:
    def test_boot_and_shutdown(self):
        app = AetherApp()
        app.boot()
        assert app.is_booted
        app.shutdown()
        assert not app.is_booted

    def test_container_has_services(self):
        app = AetherApp()
        app.boot()
        assert app.container.has(ServiceNames.CONFIG)
        assert app.container.has(ServiceNames.EVENT_BUS)
        assert app.container.has(ServiceNames.COMMAND_BUS)
        assert app.container.has(ServiceNames.RESULT_PIPELINE)
        app.shutdown()

    def test_plugin_loaded(self):
        app = AetherApp()
        app.boot()
        plugins = app.plugin_loader.loaded_plugins
        assert len(plugins) >= 1
        assert plugins[0].name == "system_info_plugin"
        app.shutdown()

    def test_boot_proof_dispatch(self):
        app = AetherApp()
        app.boot()
        result = app.command_bus.dispatch(
            Command(name="system.ping", source="test", params={"echo": True})
        )
        assert result.success
        assert result.message == "pong"
        app.shutdown()

    def test_boot_idempotent(self):
        app = AetherApp()
        app.boot()
        app.boot()  # second call should be ignored
        assert app.is_booted
        app.shutdown()

    def test_shutdown_without_boot(self):
        app = AetherApp()
        app.shutdown()  # should not raise
        assert not app.is_booted
