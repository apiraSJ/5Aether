"""Tests for ServiceContainer — IService ABC, thread safety, factory lifecycle."""
import threading
import time

from aether.core.service_container import (
    IService,
    ServiceBuildError,
    ServiceContainer,
    ServiceNames,
    ServiceNotFoundError,
)


class TestIServiceABC:
    def test_service_container_is_iservice(self):
        assert issubclass(ServiceContainer, IService)

    def test_iservice_has_required_methods(self):
        for method in ("register_instance", "register_factory", "resolve", "has", "unregister", "registered_names"):
            assert hasattr(IService, method)


class TestServiceNames:
    def test_constants_exist(self):
        assert ServiceNames.CONFIG == "config"
        assert ServiceNames.EVENT_BUS == "event_bus"
        assert ServiceNames.COMMAND_BUS == "command_bus"
        assert ServiceNames.RESULT_PIPELINE == "result_pipeline"
        assert ServiceNames.PLUGIN_LOADER == "plugin_loader"


class TestServiceContainer:
    def test_register_and_resolve_instance(self):
        c = ServiceContainer()
        c.register_instance("svc", "hello")
        assert c.resolve("svc") == "hello"

    def test_resolve_not_found(self):
        c = ServiceContainer()
        try:
            c.resolve("nope")
            assert False, "Should have raised"
        except ServiceNotFoundError as e:
            assert "nope" in str(e)

    def test_factory_singleton(self):
        c = ServiceContainer()
        call_count = 0

        def build():
            nonlocal call_count
            call_count += 1
            return f"built_{call_count}"

        c.register_factory("svc", build, singleton=True)
        r1 = c.resolve("svc")
        r2 = c.resolve("svc")
        assert r1 == r2 == "built_1"
        assert call_count == 1

    def test_factory_non_singleton(self):
        c = ServiceContainer()
        call_count = 0

        def build():
            nonlocal call_count
            call_count += 1
            return f"built_{call_count}"

        c.register_factory("svc", build, singleton=False)
        r1 = c.resolve("svc")
        r2 = c.resolve("svc")
        assert r1 != r2
        assert call_count == 2

    def test_factory_build_error(self):
        c = ServiceContainer()
        c.register_factory("svc", (_ for _ in ()).throw if False else lambda: (_ for _ in ()).__next__())
        # Simpler: use a function that raises
        def bad_factory():
            raise RuntimeError("boom")

        c.register_factory("svc", bad_factory)
        try:
            c.resolve("svc")
            assert False, "Should have raised"
        except ServiceBuildError as e:
            assert "boom" in str(e)

    def test_has(self):
        c = ServiceContainer()
        assert not c.has("x")
        c.register_instance("x", 1)
        assert c.has("x")

    def test_unregister(self):
        c = ServiceContainer()
        c.register_instance("x", 1)
        c.unregister("x")
        assert not c.has("x")

    def test_registered_names(self):
        c = ServiceContainer()
        c.register_instance("a", 1)
        c.register_instance("b", 2)
        names = c.registered_names()
        assert "a" in names
        assert "b" in names

    def test_factory_overrides_instance(self):
        c = ServiceContainer()
        c.register_instance("x", "old")
        c.register_factory("x", lambda: "new")
        assert c.resolve("x") == "new"

    def test_instance_overrides_factory(self):
        c = ServiceContainer()
        c.register_factory("x", lambda: "factory")
        c.register_instance("x", "instance")
        assert c.resolve("x") == "instance"

    def test_thread_safety(self):
        c = ServiceContainer()
        errors = []

        def writer(n):
            try:
                for i in range(100):
                    c.register_instance(f"svc_{n}_{i}", i)
            except Exception as e:
                errors.append(e)

        def reader(n):
            try:
                for i in range(100):
                    c.has(f"svc_{n}_{i}")
            except Exception as e:
                errors.append(e)

        threads = []
        for n in range(5):
            threads.append(threading.Thread(target=writer, args=(n,)))
            threads.append(threading.Thread(target=reader, args=(n,)))
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert errors == []
