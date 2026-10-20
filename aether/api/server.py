"""Aether web server entry point (--mode web).

Serves the Track B API from an already-booted AetherApp:

    app = AetherApp(config_path="config/web.yaml")
    app.boot()          # existing boot sequence — no duplicate DI
    run(app)            # this module: uvicorn + clean shutdown

Local-only by contract: binds 127.0.0.1 (never 0.0.0.0). Uvicorn owns the
signal handling while serving; AetherApp.shutdown() runs once the server
stops, releasing plugin resources (including the schedule repository).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("Aether.Web")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def run(app, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> int:
    """Serve the Aether API until the server stops, then shut the app down.

    AetherApp.boot() only initializes plugins; the plugin start()/stop()
    lifecycle (which opens/closes the schedule repository) is owned here —
    mirroring what AetherApplication does for tick/vision modes, without
    changing the shared boot sequence.

    Args:
        app: A booted AetherApp whose container holds the shared
            ScheduleService (registered by TaskPlugin during boot).
        host: Bind address — defaults to the local-only loopback address.
        port: TCP port for the web server.

    Returns:
        Process exit code (0 on clean shutdown).
    """
    import uvicorn

    from aether.api.main import create_app

    if app.container is None:
        logger.error("AetherApp has no container — boot() must succeed first.")
        return 1

    plugins = list(app.plugin_loader.loaded_plugins) if app.plugin_loader else []
    for plugin in plugins:
        plugin.start()
        logger.info("Started plugin '%s'", plugin.name)

    api_app = create_app(container=app.container)
    logger.info("Serving Aether Mark-1 API on http://%s:%d/ (local-only)", host, port)
    try:
        uvicorn.run(api_app, host=host, port=port, log_level="info")
    finally:
        for plugin in reversed(plugins):
            try:
                plugin.stop()
            except Exception:
                logger.exception("Plugin '%s' raised while stopping.", plugin.name)
        app.shutdown()
    return 0
