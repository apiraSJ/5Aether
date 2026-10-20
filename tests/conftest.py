"""Shared fixtures for Aether API tests (Track B).

``wired`` boots the full API stack against a temp SQLite database with the
real ScheduleService — no service layer is faked, matching the Contract's
"API is a thin adapter" rule.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from aether.api.main import create_app
from aether.core.service_container import ServiceContainer


def _build_wired(tmp_path) -> SimpleNamespace:
    from aether.task.repository import SqliteScheduleRepository
    from aether.task.service import ScheduleService

    repo = SqliteScheduleRepository(str(tmp_path / "tasks.db"))
    repo.open()
    container = ServiceContainer()
    service = ScheduleService(repo)
    container.register_instance("schedule_service", service)
    app = create_app(container=container)
    client = TestClient(app, base_url="http://localhost")
    return SimpleNamespace(
        client=client, service=service, container=container, repo=repo
    )


@pytest.fixture
def wired(tmp_path):
    """API client + real ScheduleService on a temp database (closed after)."""
    ctx = _build_wired(tmp_path)
    yield ctx
    ctx.repo.close()


@pytest.fixture
def wired_client(wired):
    """Just the TestClient from the ``wired`` stack."""
    return wired.client
