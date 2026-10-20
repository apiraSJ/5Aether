"""Tests for the --mode web launch path (Aether Mark-1 Track B).

Covers: CLI arg, web config minimality, and the server lifecycle —
boot (existing sequence) → plugin start (repo opens) → uvicorn serve →
plugin stop + app shutdown. Uvicorn is stubbed so no socket is bound.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

from aether.__main__ import WEB_CONFIG, _parse_args


# ── CLI ────────────────────────────────────────────────────────────


class TestWebModeArgs:
    def test_web_mode_accepted(self):
        assert _parse_args(["--mode", "web"]).mode == "web"

    def test_default_mode_unchanged(self):
        """Adding web mode must not change the default run mode."""
        assert _parse_args([]).mode == "headless"

    def test_web_config_constant_exists(self):
        assert WEB_CONFIG.exists()
        assert WEB_CONFIG.name == "web.yaml"


# ── config/web.yaml ────────────────────────────────────────────────


class TestWebConfigMinimal:
    def test_only_task_plugin_declared(self):
        """Web mode loads no GUI, vision, AI, or Memory plugins."""
        from aether.config.loader import ConfigLoader

        config = ConfigLoader(str(WEB_CONFIG))
        config.load()
        classes = [p["class"] for p in config.get("plugins", [])]
        assert classes == ["TaskPlugin"]

    def test_task_db_path_configured(self):
        from aether.config.loader import ConfigLoader

        config = ConfigLoader(str(WEB_CONFIG))
        config.load()
        assert config.get("task.db_path") == "data/tasks.db"


# ── Server lifecycle ───────────────────────────────────────────────


def _boot_web_app(tmp_path: Path):
    """Boot AetherApp from a web.yaml copy pointing at a temp database."""
    from aether.app import AetherApp

    db_path = str(tmp_path / "tasks.db").replace("\\", "/")
    text = WEB_CONFIG.read_text(encoding="utf-8")
    text = text.replace('db_path: "data/tasks.db"', f'db_path: "{db_path}"')
    cfg_path = tmp_path / "web.yaml"
    cfg_path.write_text(text, encoding="utf-8")

    app = AetherApp(config_path=str(cfg_path))
    app.boot()
    return app


class TestWebServerLifecycle:
    @pytest.fixture
    def booted_app(self, tmp_path):
        app = _boot_web_app(tmp_path)
        yield app
        if app.is_booted:
            app.shutdown()

    def test_boot_registers_schedule_service(self, booted_app):
        """Existing boot sequence wires the shared ScheduleService."""
        assert booted_app.container is not None
        assert booted_app.container.has("schedule_service")
        plugins = booted_app.plugin_loader.loaded_plugins
        assert [p.name for p in plugins] == ["task_plugin"]

    def test_run_serves_api_then_stops_everything(self, tmp_path, monkeypatch):
        """run(): plugin start → uvicorn (host/port/API) → stop + shutdown."""
        app = _boot_web_app(tmp_path)
        plugin = app.plugin_loader.loaded_plugins[0]
        captured: dict = {}

        def fake_uvicorn_run(api_app, *, host, port, log_level):
            captured["host"] = host
            captured["port"] = port
            captured["log_level"] = log_level
            # While "serving", the repo must be open and the API answerable.
            client = TestClient(api_app, base_url="http://localhost")
            response = client.get("/api/v1/tasks")
            captured["status"] = response.status_code

        monkeypatch.setattr(uvicorn, "run", fake_uvicorn_run)

        from aether.api.server import run

        exit_code = run(app)

        assert exit_code == 0
        # Local-only binding per API Contract v1.1
        assert captured["host"] == "127.0.0.1"
        assert captured["port"] == 8765
        assert captured["status"] == 200
        # After run(): plugin stopped (repo closed) and app shut down.
        assert plugin.is_ready() is False
        assert app.is_booted is False
        assert app.plugin_loader.loaded_plugins == []

    def test_run_refuses_without_container(self):
        """boot() must succeed before run() — no silent half-started server."""
        from aether.app import AetherApp
        from aether.api.server import run

        unbooted = AetherApp(config_path=str(WEB_CONFIG))
        assert unbooted.container is None
        assert run(unbooted) == 1
