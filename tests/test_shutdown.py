"""Test clean shutdown — verifies no threads hang after boot+shutdown cycle."""

import threading
import time

from aether.core.service_container import ServiceContainer
from aether.core.event_bus_v2 import EventBus
from aether.core.command_bus import CommandBus
from aether.core.result_pipeline import ResultPipeline
from aether.core.plugin_loader import PluginLoader


def test_clean_shutdown():
    """Boot the app, then shut it down. Verify no threads remain."""
    container = ServiceContainer()
    container.register_instance("event_bus", EventBus(queued=True))
    container.register_instance("command_bus", CommandBus())
    container.register_instance("result_pipeline", ResultPipeline())

    threads_before = set(threading.enumerate())

    loader = PluginLoader(container)

    # Minimal plugin list — just SystemPlugin (no GUI, no vision)
    plugin_specs = [
        {"module": "aether.plugins.system_plugin", "class": "SystemPlugin", "enabled": True},
    ]
    plugins = loader.load_from_config(plugin_specs)
    loader.initialize_all(plugins)
    time.sleep(0.5)

    # Shutdown
    loader.shutdown_all()

    threads_after = set(threading.enumerate())
    new_threads = threads_after - threads_before

    # Filter out daemon threads (pytest, etc.)
    non_daemon = [t for t in new_threads if not t.daemon]

    print(f"Threads before: {len(threads_before)}")
    print(f"Threads after:  {len(threads_after)}")
    print(f"New threads:    {len(new_threads)}")
    print(f"Non-daemon new: {len(non_daemon)}")

    if non_daemon:
        for t in non_daemon:
            print(f"  WARNING: {t.name} (alive={t.is_alive()})")

    assert len(non_daemon) == 0, f"Non-daemon threads left alive: {[t.name for t in non_daemon]}"
    print("\nClean shutdown verified!")


if __name__ == "__main__":
    test_clean_shutdown()
