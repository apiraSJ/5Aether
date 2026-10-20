"""Tests for event-driven workspace auto-save (Sprint 2.1A).

Covers:
    - WorkspaceManager session save/load roundtrip (pure Python)
    - WorkspaceScene debounced auto-save on geometry change
    - Window ops (pin/close) persist to the layout file
    - apply_sessions() restores geometry without re-saving
"""

from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from aether.ui.panel.panel_info import PanelInfo
from aether.ui.panel.panel_registry import PanelRegistry
from aether.ui.panel.panel_widget import PanelWidget
from aether.ui.panel.workspace_scene import WorkspaceScene
from aether.workspace.workspace_manager import WorkspaceManager


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def make_manager(tmp_path, registry=None):
    registry = registry or PanelRegistry()
    return WorkspaceManager(registry, workspaces_dir=tmp_path, layouts_dir=tmp_path)


def make_scene(manager):
    scene = WorkspaceScene()
    scene.bind_workspace_manager(manager)
    return scene


# ── WorkspaceManager session persistence (no Qt widgets) ────────────


class TestSessionLayoutPersistence:
    def test_save_load_roundtrip(self, tmp_path):
        manager = make_manager(tmp_path)
        sessions = [
            {
                "panel_id": "mem", "panel_type": "memory",
                "x": 120, "y": 80, "w": 640, "h": 480,
                "visible": True, "pinned": False,
            },
            {
                "panel_id": "chat", "panel_type": "ai_chat",
                "x": 800, "y": 100, "w": 480, "h": 360,
                "visible": False, "pinned": True,
            },
        ]
        manager.save_layout_sessions("last", sessions)
        loaded = manager.load_layout_sessions("last")
        assert loaded == sessions
        assert (tmp_path / "last.json").exists()

    def test_last_layout_sessions(self, tmp_path):
        import os
        manager = make_manager(tmp_path)
        assert manager.last_layout_sessions() is None
        manager.save_layout_sessions("first", [{"panel_id": "a", "x": 0}])
        # Force distinct mtimes (Windows mtime granularity can collide)
        first = tmp_path / "first.json"
        os.utime(first, (1_600_000_000, 1_600_000_000))
        manager.save_layout_sessions("second", [{"panel_id": "b", "x": 50}])
        loaded = manager.last_layout_sessions()
        assert loaded[0]["panel_id"] == "b"

    def test_load_missing_returns_none(self, tmp_path):
        manager = make_manager(tmp_path)
        assert manager.load_layout_sessions("nope") is None

    def test_load_corrupt_returns_none(self, tmp_path, caplog):
        manager = make_manager(tmp_path)
        (tmp_path / "bad.json").write_text("{ broken", encoding="utf-8")
        assert manager.load_layout_sessions("bad") is None

    def test_load_no_sessions_key_returns_none(self, tmp_path):
        manager = make_manager(tmp_path)
        (tmp_path / "nosess.json").write_text(json.dumps({"name": "x"}), encoding="utf-8")
        assert manager.load_layout_sessions("nosess") is None


# ── WorkspaceScene event-driven auto-save ───────────────────────────


class TestWorkspaceAutoSave:
    def test_geometry_change_arms_debounce(self, qapp, tmp_path):
        scene = make_scene(make_manager(tmp_path))
        widget = PanelWidget("mem", "memory", "Memory")
        scene.add_panel(widget)
        scene.show()  # Qt delivers move/resize events only when shown
        widget.move(120, 80)
        assert scene._save_timer.isActive()

    def test_autosave_persists_after_debounce(self, qapp, tmp_path):
        manager = make_manager(tmp_path)
        scene = make_scene(manager)
        widget = PanelWidget("mem", "memory", "Memory")
        scene.add_panel(widget)
        scene.show()
        widget.move(120, 80)
        QTest.qWait(600)
        sessions = manager.last_layout_sessions()
        assert sessions is not None
        mem = sessions[0]
        assert (mem["x"], mem["y"]) == (120, 80)

    def test_pin_op_persists(self, qapp, tmp_path):
        manager = make_manager(tmp_path)
        scene = make_scene(manager)
        widget = PanelWidget("mem", "memory", "Memory")
        scene.add_panel(widget)
        scene.pin_panel("mem")
        QTest.qWait(600)
        sessions = manager.last_layout_sessions()
        assert sessions[0]["pinned"] is True
        assert widget.is_pinned() is True

    def test_close_persists_visibility(self, qapp, tmp_path):
        manager = make_manager(tmp_path)
        scene = make_scene(manager)
        widget = PanelWidget("mem", "memory", "Memory")
        scene.add_panel(widget)
        scene.close_panel("mem")
        QTest.qWait(600)
        sessions = manager.last_layout_sessions()
        assert sessions[0]["visible"] is False

    def test_window_op_signal_routes_to_scene(self, qapp, tmp_path):
        manager = make_manager(tmp_path)
        scene = make_scene(manager)
        widget = PanelWidget("mem", "memory", "Memory")
        scene.add_panel(widget)
        widget._on_close()  # TitleBar close button path
        assert not widget.isVisible()

    def test_apply_sessions_restores_geometry(self, qapp, tmp_path):
        manager = make_manager(tmp_path)
        sessions = [{
            "panel_id": "mem", "panel_type": "memory",
            "x": 300, "y": 200, "w": 500, "h": 400,
            "visible": True, "pinned": True,
        }]
        manager.save_layout_sessions("last", sessions)

        scene = make_scene(manager)
        widget = PanelWidget("mem", "memory", "Memory")
        scene.add_panel(widget)
        applied = scene.apply_sessions(manager.last_layout_sessions())
        assert applied == 1
        assert (widget.x(), widget.y()) == (300, 200)
        assert (widget.width(), widget.height()) == (500, 400)
        assert widget.is_pinned() is True

    def test_apply_sessions_does_not_resave(self, qapp, tmp_path):
        manager = make_manager(tmp_path)
        scene = make_scene(manager)
        widget = PanelWidget("mem", "memory", "Memory")
        scene.add_panel(widget)
        scene.apply_sessions([])  # no data → no-op
        assert not scene._save_timer.isActive()
        scene.apply_sessions([{
            "panel_id": "mem", "panel_type": "memory",
            "x": 10, "y": 10, "w": 400, "h": 300, "visible": True, "pinned": False,
        }])
        assert not scene._save_timer.isActive()

    def test_request_layout_save_writes_and_emits(self, qapp, tmp_path):
        manager = make_manager(tmp_path)
        scene = make_scene(manager)
        emitted = []
        scene.layout_changed.connect(lambda: emitted.append(True))
        widget = PanelWidget("mem", "memory", "Memory")
        scene.add_panel(widget)
        scene.request_layout_save()
        assert emitted
        assert manager.last_layout_sessions() is not None

    def test_no_manager_falls_back_to_signal(self, qapp, tmp_path):
        scene = WorkspaceScene()
        emitted = []
        scene.layout_changed.connect(lambda: emitted.append(True))
        widget = PanelWidget("mem", "memory", "Memory")
        scene.add_panel(widget)
        scene._request_save()  # no manager bound → emit immediately
        assert emitted
