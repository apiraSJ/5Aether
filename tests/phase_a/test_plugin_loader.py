"""Tests for PluginLoader — load, initialize, shutdown, failure isolation."""
import pytest
from aether.core.plugin import PluginBase
from aether.core.plugin_loader import PluginLoadError, PluginLoader
from aether.core.service_container import ServiceContainer

_MOD = "tests.phase_a.test_plugin_loader"


class GoodPlugin(PluginBase):
    name = "good_plugin"

    def __init__(self):
        self.initialized = False
        self.shut_down = False

    def initialize(self, container):
        self.initialized = True

    def shutdown(self):
        self.shut_down = True


class BadInitPlugin(PluginBase):
    name = "bad_init_plugin"

    def initialize(self, container):
        raise RuntimeError("init failed")


class NotAPlugin:
    pass


class TestPluginBase:
    def test_name_required(self):
        with pytest.raises(TypeError, match="must define a 'name'"):
            class _(PluginBase):
                pass

    def test_good_plugin_has_name(self):
        assert GoodPlugin.name == "good_plugin"


class TestPluginLoader:
    def test_load_module(self):
        container = ServiceContainer()
        loader = PluginLoader(container)
        plugin = loader.load_module(_MOD, "GoodPlugin")
        assert isinstance(plugin, GoodPlugin)

    def test_load_nonexistent_module(self):
        container = ServiceContainer()
        loader = PluginLoader(container)
        with pytest.raises(PluginLoadError):
            loader.load_module("nonexistent.module", "Foo")

    def test_load_nonexistent_class(self):
        container = ServiceContainer()
        loader = PluginLoader(container)
        with pytest.raises(PluginLoadError):
            loader.load_module(_MOD, "Nonexistent")

    def test_load_not_plugin_subclass(self):
        container = ServiceContainer()
        loader = PluginLoader(container)
        with pytest.raises(PluginLoadError):
            loader.load_module(_MOD, "NotAPlugin")

    def test_initialize_success(self):
        container = ServiceContainer()
        loader = PluginLoader(container)
        plugin = GoodPlugin()
        loader.initialize_all([plugin])
        assert plugin.initialized
        assert plugin in loader.loaded_plugins

    def test_initialize_failure_isolated(self):
        container = ServiceContainer()
        loader = PluginLoader(container)
        good = GoodPlugin()
        bad = BadInitPlugin()
        loader.initialize_all([good, bad])
        assert good.initialized
        assert bad not in loader.loaded_plugins

    def test_initialize_failure_strict(self):
        container = ServiceContainer()
        loader = PluginLoader(container, strict_mode=True)
        bad = BadInitPlugin()
        with pytest.raises(PluginLoadError):
            loader.initialize_all([bad])

    def test_shutdown(self):
        container = ServiceContainer()
        loader = PluginLoader(container)
        plugin = GoodPlugin()
        loader.initialize_all([plugin])
        loader.shutdown_all()
        assert plugin.shut_down
        assert loader.loaded_plugins == []
