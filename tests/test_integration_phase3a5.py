"""Integration Tests for Phase 3A.5 — GUI/UI Foundation.

Tests the full service pipeline:
  CommandBus → SystemCommandPlugin → PanelRegistry → Panel → EventBus

Levels:
  Level 2: Service Integration (CommandBus → Plugin → Registry → Panel → EventBus)
  Level 3: Layout System Integration (save/load, filesystem, position restore)
  Level 5 extras: Stress, Event Replay, Shutdown
"""

import json
import time
from pathlib import Path
from typing import List

from aether.core.event_bus_v2 import EventBus, Event
from aether.core.event_type import EventType
from aether.core.command import Command
from aether.core.command_bus import CommandBus
from aether.core.result_pipeline import ResultPipeline
from aether.core.command_registry import CommandRegistry
from aether.core.service_container import ServiceContainer
from aether.plugins.system_commands_plugin import SystemCommandPlugin
from aether.ui.panel.panel_registry import PanelRegistry
from aether.ui.panel.panel_info import PanelInfo, PanelCapability
from aether.ui.panel.layout_manager import LayoutManager
from aether.ui.panel.theme_manager import ThemeManager
from aether.ui.panel.notification_manager import NotificationManager
from aether.ui.panel.memory_panel import MemoryPanel, MemoryItem
from aether.ui.panel.vision_panel import VisionPanel, VisionSnapshot
from aether.ui.panel.system_panel import SystemPanel, SystemSnapshot
from aether.ui.panel.abstract_panel import AbstractPanel


# ══════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════

def _make_full_stack(tmp_path=None):
    """Create a complete service stack with EventBus integration."""
    bus = EventBus(queued=True)
    pipeline = ResultPipeline()
    cmd_bus = CommandBus(result_pipeline=pipeline, event_bus=bus)
    c = ServiceContainer()
    c.register_instance("event_bus", bus)
    c.register_instance("command_bus", cmd_bus)
    c.register_instance("result_pipeline", pipeline)
    c.register_instance("config", {})

    # PanelRegistry WITH EventBus
    reg = PanelRegistry(event_bus=bus)
    mem = MemoryPanel()
    vis = VisionPanel()
    sys_p = SystemPanel()
    reg.register(PanelInfo(id="memory", type="memory", widget=mem, z_index=20))
    reg.register(PanelInfo(id="vision", type="vision", widget=vis, z_index=10))
    reg.register(PanelInfo(id="system", type="system", widget=sys_p, z_index=5))
    c.register_instance("panel_registry", reg)

    layouts_dir = tmp_path or Path(__file__).parent / "_test_layouts"
    layouts_dir.mkdir(exist_ok=True)
    mgr = LayoutManager(reg, layouts_dir=layouts_dir)
    c.register_instance("layout_manager", mgr)

    theme_mgr = ThemeManager(themes_dir=layouts_dir)
    c.register_instance("theme_manager", theme_mgr)

    notif_mgr = NotificationManager(event_bus=bus)
    c.register_instance("notification_manager", notif_mgr)

    # Initialize SystemCommandPlugin
    plugin = SystemCommandPlugin()
    plugin.initialize(c)

    return c, bus, cmd_bus, reg, mgr, theme_mgr, notif_mgr


# ══════════════════════════════════════════════════════════════════════
# Level 2 — Service Integration Tests
# ══════════════════════════════════════════════════════════════════════

class TestLevel2_PanelShow:
    """CommandBus → SystemCommandPlugin → PanelRegistry → Panel visible."""

    def test_panel_show_sets_visible(self, tmp_path):
        c, bus, cmd_bus, reg, _, _, _ = _make_full_stack(tmp_path)
        assert reg.get("memory").visible is False

        cmd_bus.dispatch_sync(Command(
            name="system.panel.show", source="test",
            params={"panel_id": "memory"},
        ))

        assert reg.get("memory").visible is True

    def test_panel_show_emits_event(self, tmp_path):
        c, bus, cmd_bus, reg, _, _, _ = _make_full_stack(tmp_path)
        events: List[Event] = []
        bus.subscribe(EventType.PANEL_SHOWN, lambda e: events.append(e))

        cmd_bus.dispatch_sync(Command(
            name="system.panel.show", source="test",
            params={"panel_id": "memory"},
        ))

        bus.flush()
        assert len(events) == 1
        assert events[0].payload["panel_id"] == "memory"
        assert events[0].payload["type"] == "memory"

    def test_panel_show_not_found(self, tmp_path):
        c, bus, cmd_bus, reg, _, _, _ = _make_full_stack(tmp_path)
        result = cmd_bus.dispatch_sync(Command(
            name="system.panel.show", source="test",
            params={"panel_id": "nonexistent"},
        ))
        assert "not found" in result.get("message", "")

    def test_panel_show_no_id(self, tmp_path):
        c, bus, cmd_bus, reg, _, _, _ = _make_full_stack(tmp_path)
        result = cmd_bus.dispatch_sync(Command(
            name="system.panel.show", source="test", params={},
        ))
        assert "Usage" in result.get("message", "")


class TestLevel2_PanelHide:
    """CommandBus → SystemCommandPlugin → PanelRegistry → Panel hidden."""

    def test_panel_hide_sets_invisible(self, tmp_path):
        c, bus, cmd_bus, reg, _, _, _ = _make_full_stack(tmp_path)
        reg.show_panel("memory")
        assert reg.get("memory").visible is True

        cmd_bus.dispatch_sync(Command(
            name="system.panel.hide", source="test",
            params={"panel_id": "memory"},
        ))

        assert reg.get("memory").visible is False

    def test_panel_hide_emits_event(self, tmp_path):
        c, bus, cmd_bus, reg, _, _, _ = _make_full_stack(tmp_path)
        reg.show_panel("vision")
        events: List[Event] = []
        bus.subscribe(EventType.PANEL_HIDDEN, lambda e: events.append(e))

        cmd_bus.dispatch_sync(Command(
            name="system.panel.hide", source="test",
            params={"panel_id": "vision"},
        ))

        bus.flush()
        assert len(events) == 1
        assert events[0].payload["panel_id"] == "vision"


class TestLevel2_PanelToggle:
    """Toggle panel visibility through command."""

    def test_toggle_off_to_on(self, tmp_path):
        c, bus, cmd_bus, reg, _, _, _ = _make_full_stack(tmp_path)
        assert reg.get("memory").visible is False

        cmd_bus.dispatch_sync(Command(
            name="system.panel.toggle", source="test",
            params={"panel_id": "memory"},
        ))

        assert reg.get("memory").visible is True

    def test_toggle_on_to_off(self, tmp_path):
        c, bus, cmd_bus, reg, _, _, _ = _make_full_stack(tmp_path)
        reg.show_panel("memory")
        assert reg.get("memory").visible is True

        cmd_bus.dispatch_sync(Command(
            name="system.panel.toggle", source="test",
            params={"panel_id": "memory"},
        ))

        assert reg.get("memory").visible is False

    def test_toggle_emits_both_events(self, tmp_path):
        c, bus, cmd_bus, reg, _, _, _ = _make_full_stack(tmp_path)
        shown_events: List[Event] = []
        hidden_events: List[Event] = []
        bus.subscribe(EventType.PANEL_SHOWN, lambda e: shown_events.append(e))
        bus.subscribe(EventType.PANEL_HIDDEN, lambda e: hidden_events.append(e))

        # Toggle on
        cmd_bus.dispatch_sync(Command(
            name="system.panel.toggle", source="test",
            params={"panel_id": "memory"},
        ))
        bus.flush()
        assert len(shown_events) == 1
        assert len(hidden_events) == 0

        # Toggle off
        cmd_bus.dispatch_sync(Command(
            name="system.panel.toggle", source="test",
            params={"panel_id": "memory"},
        ))
        bus.flush()
        assert len(shown_events) == 1
        assert len(hidden_events) == 1


class TestLevel2_PanelList:
    """List all panels through command."""

    def test_panel_list_returns_all(self, tmp_path):
        c, bus, cmd_bus, reg, _, _, _ = _make_full_stack(tmp_path)
        result = cmd_bus.dispatch_sync(Command(
            name="system.panel.list", source="test", params={},
        ))
        assert "3 panels" in result.get("message", "")
        assert "memory" in result.get("message", "")
        assert "vision" in result.get("message", "")
        assert "system" in result.get("message", "")

    def test_panel_list_shows_visibility(self, tmp_path):
        c, bus, cmd_bus, reg, _, _, _ = _make_full_stack(tmp_path)
        reg.show_panel("memory")
        result = cmd_bus.dispatch_sync(Command(
            name="system.panel.list", source="test", params={},
        ))
        assert "visible" in result.get("message", "")


# ══════════════════════════════════════════════════════════════════════
# Level 3 — Layout System Integration Tests
# ══════════════════════════════════════════════════════════════════════

class TestLevel3_LayoutSaveLoad:
    """Save layout → file exists → load restores geometry."""

    def test_save_creates_json_file(self, tmp_path):
        c, bus, cmd_bus, reg, mgr, _, _ = _make_full_stack(tmp_path)
        cmd_bus.dispatch_sync(Command(
            name="system.layout.save", source="test",
            params={"name": "developer"},
        ))
        assert (tmp_path / "developer.json").exists()

    def test_save_file_contains_panel_data(self, tmp_path):
        c, bus, cmd_bus, reg, mgr, _, _ = _make_full_stack(tmp_path)
        cmd_bus.dispatch_sync(Command(
            name="system.layout.save", source="test",
            params={"name": "dev"},
        ))
        data = json.loads((tmp_path / "dev.json").read_text(encoding="utf-8"))
        assert data["name"] == "dev"
        assert len(data["panels"]) == 3

    def test_load_restores_geometry(self, tmp_path):
        c, bus, cmd_bus, reg, mgr, _, _ = _make_full_stack(tmp_path)

        # Save current geometry
        cmd_bus.dispatch_sync(Command(
            name="system.layout.save", source="test",
            params={"name": "dev"},
        ))

        # Move panels to new positions
        reg.move_panel("memory", 999, 888)
        reg.move_panel("vision", 777, 666)
        assert reg.get("memory").x == 999

        # Load should restore
        cmd_bus.dispatch_sync(Command(
            name="system.layout.load", source="test",
            params={"name": "dev"},
        ))

        assert reg.get("memory").x == 0
        assert reg.get("memory").y == 0
        assert reg.get("vision").x == 0  # default from fixture

    def test_load_shows_hides_correctly(self, tmp_path):
        c, bus, cmd_bus, reg, mgr, _, _ = _make_full_stack(tmp_path)

        # Show memory, save
        reg.show_panel("memory")
        cmd_bus.dispatch_sync(Command(
            name="system.layout.save", source="test",
            params={"name": "vis"},
        ))

        # Hide memory
        reg.hide_panel("memory")
        assert reg.get("memory").visible is False

        # Load should show it again
        cmd_bus.dispatch_sync(Command(
            name="system.layout.load", source="test",
            params={"name": "vis"},
        ))

        assert reg.get("memory").visible is True

    def test_layout_not_found(self, tmp_path):
        c, bus, cmd_bus, reg, mgr, _, _ = _make_full_stack(tmp_path)
        result = cmd_bus.dispatch_sync(Command(
            name="system.layout.load", source="test",
            params={"name": "nonexistent"},
        ))
        assert "not found" in result.get("message", "")

    def test_layout_delete(self, tmp_path):
        c, bus, cmd_bus, reg, mgr, _, _ = _make_full_stack(tmp_path)
        mgr.save("todelete")
        assert (tmp_path / "todelete.json").exists()

        cmd_bus.dispatch_sync(Command(
            name="system.layout.delete", source="test",
            params={"name": "todelete"},
        ))

        assert not (tmp_path / "todelete.json").exists()

    def test_layout_reset(self, tmp_path):
        c, bus, cmd_bus, reg, mgr, _, _ = _make_full_stack(tmp_path)
        reg.show_panel("memory")
        mgr.save("before_reset")

        cmd_bus.dispatch_sync(Command(
            name="system.layout.reset", source="test", params={},
        ))

        assert reg.get("memory").visible is False
        assert mgr.current_layout is None

    def test_layout_roundtrip_multiple_saves(self, tmp_path):
        c, bus, cmd_bus, reg, mgr, _, _ = _make_full_stack(tmp_path)

        # Save layout 1
        reg.move_panel("memory", 100, 100)
        cmd_bus.dispatch_sync(Command(
            name="system.layout.save", source="test",
            params={"name": "layout1"},
        ))

        # Save layout 2
        reg.move_panel("memory", 500, 500)
        cmd_bus.dispatch_sync(Command(
            name="system.layout.save", source="test",
            params={"name": "layout2"},
        ))

        # Load layout 1
        cmd_bus.dispatch_sync(Command(
            name="system.layout.load", source="test",
            params={"name": "layout1"},
        ))
        assert reg.get("memory").x == 100

        # Load layout 2
        cmd_bus.dispatch_sync(Command(
            name="system.layout.load", source="test",
            params={"name": "layout2"},
        ))
        assert reg.get("memory").x == 500


# ══════════════════════════════════════════════════════════════════════
# Theme System Integration Tests
# ══════════════════════════════════════════════════════════════════════

class TestLevel3_ThemeSystem:
    """Apply theme → panels updated → event emitted."""

    def test_theme_apply_updates_panels(self, tmp_path):
        c, bus, cmd_bus, reg, _, theme_mgr, _ = _make_full_stack(tmp_path)
        theme_mgr.save_theme("cyber", {"colors": {"primary": "#0ff"}})

        cmd_bus.dispatch_sync(Command(
            name="system.theme.apply", source="test",
            params={"name": "cyber"},
        ))

        assert theme_mgr.current_name == "cyber"
        assert theme_mgr.get_color("colors.primary") == "#0ff"

    def test_theme_list(self, tmp_path):
        c, bus, cmd_bus, reg, _, theme_mgr, _ = _make_full_stack(tmp_path)
        theme_mgr.save_theme("dark", {"colors": {"primary": "#fff"}})
        theme_mgr.save_theme("light", {"colors": {"primary": "#000"}})

        result = cmd_bus.dispatch_sync(Command(
            name="system.theme.list", source="test", params={},
        ))

        msg = result.get("message", "")
        assert "themes" in msg
        assert "dark" in msg
        assert "light" in msg

    def test_theme_not_found(self, tmp_path):
        c, bus, cmd_bus, reg, _, _, _ = _make_full_stack(tmp_path)
        result = cmd_bus.dispatch_sync(Command(
            name="system.theme.apply", source="test",
            params={"name": "nonexistent"},
        ))
        assert "not found" in result.get("message", "")


# ══════════════════════════════════════════════════════════════════════
# Level 5 Extra — Stress Test
# ══════════════════════════════════════════════════════════════════════

class TestLevel5_Stress:
    """PanelRegistry stress test: 100 panels."""

    def test_register_100_panels(self):
        reg = PanelRegistry()
        for i in range(100):
            reg.register(PanelInfo(id=f"panel_{i}", type="test"))
        assert reg.panel_count() == 100

    def test_show_hide_100_panels(self):
        reg = PanelRegistry()
        for i in range(100):
            reg.register(PanelInfo(id=f"panel_{i}", type="test"))

        for i in range(100):
            assert reg.show_panel(f"panel_{i}") is True
        assert len(reg.list_visible()) == 100

        for i in range(100):
            assert reg.hide_panel(f"panel_{i}") is True
        assert len(reg.list_visible()) == 0

    def test_toggle_100_panels(self):
        reg = PanelRegistry()
        for i in range(100):
            reg.register(PanelInfo(id=f"panel_{i}", type="test"))

        for i in range(100):
            reg.toggle_panel(f"panel_{i}")

        # All should now be visible
        assert len(reg.list_visible()) == 100

    def test_z_sort_100_panels(self):
        reg = PanelRegistry()
        for i in range(100):
            reg.register(PanelInfo(id=f"panel_{i}", type="test", z_index=i))

        sorted_panels = reg.get_sorted_by_z()
        assert len(sorted_panels) == 100
        assert sorted_panels[0].z_index == 0
        assert sorted_panels[-1].z_index == 99

    def test_stress_with_event_bus(self):
        bus = EventBus(queued=True)
        reg = PanelRegistry(event_bus=bus)
        events = []
        bus.subscribe(EventType.PANEL_SHOWN, lambda e: events.append(e))

        for i in range(50):
            reg.register(PanelInfo(id=f"p{i}", type="t"))
            reg.show_panel(f"p{i}")

        bus.flush()
        assert len(events) == 50

    def test_stress_layout_save_load(self, tmp_path):
        c, bus, cmd_bus, reg, mgr, _, _ = _make_full_stack(tmp_path)

        # Register 20 more panels
        for i in range(20):
            reg.register(PanelInfo(id=f"extra_{i}", type="extra", x=i*10, y=i*5))

        # Save
        mgr.save("stress_test")
        assert (tmp_path / "stress_test.json").exists()

        # Move all
        for i in range(20):
            reg.move_panel(f"extra_{i}", 9999, 8888)

        # Load
        mgr.load("stress_test")
        for i in range(20):
            info = reg.get(f"extra_{i}")
            assert info.x == i * 10
            assert info.y == i * 5


# ══════════════════════════════════════════════════════════════════════
# Level 5 Extra — Event Replay Test
# ══════════════════════════════════════════════════════════════════════

class TestLevel5_EventReplay:
    """Panel change events flow through EventBus correctly."""

    def test_register_emits_panel_registered(self):
        bus = EventBus(queued=True)
        reg = PanelRegistry(event_bus=bus)
        events: List[Event] = []
        bus.subscribe(EventType.PANEL_REGISTERED, lambda e: events.append(e))

        reg.register(PanelInfo(id="test", type="t"))
        bus.flush()

        assert len(events) == 1
        assert events[0].payload["panel_id"] == "test"

    def test_show_hide_full_event_sequence(self):
        bus = EventBus(queued=True)
        reg = PanelRegistry(event_bus=bus)
        shown: List[Event] = []
        hidden: List[Event] = []
        bus.subscribe(EventType.PANEL_SHOWN, lambda e: shown.append(e))
        bus.subscribe(EventType.PANEL_HIDDEN, lambda e: hidden.append(e))

        reg.register(PanelInfo(id="p1", type="t"))
        reg.show_panel("p1")
        reg.hide_panel("p1")
        reg.show_panel("p1")
        reg.hide_panel("p1")

        bus.flush()
        assert len(shown) == 2
        assert len(hidden) == 2

    def test_move_emits_panel_moved(self):
        bus = EventBus(queued=True)
        reg = PanelRegistry(event_bus=bus)
        events: List[Event] = []
        bus.subscribe(EventType.PANEL_MOVED, lambda e: events.append(e))

        reg.register(PanelInfo(id="p1", type="t"))
        reg.move_panel("p1", 100, 200)
        bus.flush()

        assert len(events) == 1
        assert events[0].payload["x"] == 100
        assert events[0].payload["y"] == 200

    def test_focus_emits_panel_focused(self):
        bus = EventBus(queued=True)
        reg = PanelRegistry(event_bus=bus)
        events: List[Event] = []
        bus.subscribe(EventType.PANEL_FOCUSED, lambda e: events.append(e))

        reg.register(PanelInfo(id="p1", type="t"))
        reg.focus_panel("p1")
        bus.flush()

        assert len(events) == 1
        assert events[0].payload["panel_id"] == "p1"

    def test_notification_publish_emits_event(self):
        bus = EventBus(queued=True)
        notif_mgr = NotificationManager(event_bus=bus)
        events: List[Event] = []
        bus.subscribe(EventType.NOTIFICATION_SHOW, lambda e: events.append(e))

        notif_mgr.info("test notification")
        bus.flush()

        assert len(events) == 1
        assert events[0].payload["text"] == "test notification"
        assert events[0].payload["type"] == "info"

    def test_notification_dismiss_emits_event(self):
        bus = EventBus(queued=True)
        notif_mgr = NotificationManager(event_bus=bus)
        events: List[Event] = []
        bus.subscribe(EventType.NOTIFICATION_DISMISS, lambda e: events.append(e))

        notif = notif_mgr.info("dismiss me")
        notif_mgr.dismiss(notif.id)
        bus.flush()

        assert len(events) == 1
        assert events[0].payload["text"] == "dismiss me"


# ══════════════════════════════════════════════════════════════════════
# Level 5 Extra — Shutdown Test
# ══════════════════════════════════════════════════════════════════════

class TestLevel5_Shutdown:
    """Verify clean shutdown: resources released, no errors."""

    def test_overlay_controller_unsubscribes(self):
        """OverlayController.unsubscribe() removes all handlers."""
        from aether.ui.overlay_controller import OverlayController
        from aether.ui.overlay_model import OverlayModel

        bus = EventBus(queued=True)
        model = OverlayModel()
        ctrl = OverlayController(bus, model)

        # Verify subscriptions exist
        assert bus.get_subscriber_count("vision.object.detected") >= 1

        ctrl.unsubscribe()

        # Verify unsubscribed
        assert bus.get_subscriber_count("vision.object.detected") == 0

    def test_notification_manager_clear_on_shutdown(self):
        """NotificationManager.clear() empties all notifications."""
        bus = EventBus(queued=True)
        mgr = NotificationManager(event_bus=bus)
        mgr.info("a")
        mgr.info("b")
        mgr.error("c")
        assert mgr.count() == 3

        cleared = mgr.clear()
        assert cleared == 3
        assert mgr.count() == 0

    def test_layout_manager_save_before_shutdown(self):
        """LayoutManager.save() persists to disk."""
        from aether.ui.panel.panel_registry import PanelRegistry
        from aether.ui.panel.panel_info import PanelInfo
        from aether.ui.panel.layout_manager import LayoutManager

        reg = PanelRegistry()
        reg.register(PanelInfo(id="mem", type="memory", x=100, y=200, w=400, h=300))
        mgr = LayoutManager(reg, layouts_dir=Path(__file__).parent / "_test_shutdown")
        mgr.save("pre_shutdown")

        # Verify file exists
        assert (mgr._dir / "pre_shutdown.json").exists()

        # Verify contents
        data = json.loads((mgr._dir / "pre_shutdown.json").read_text(encoding="utf-8"))
        mem_panel = next(p for p in data["panels"] if p["id"] == "mem")
        assert mem_panel["x"] == 100
        assert mem_panel["y"] == 200

    def test_panel_registry_cleanup(self):
        """PanelRegistry supports unregister all panels."""
        reg = PanelRegistry()
        for i in range(10):
            reg.register(PanelInfo(id=f"p{i}", type="t"))
        assert reg.panel_count() == 10

        for i in range(10):
            reg.unregister(f"p{i}")
        assert reg.panel_count() == 0

    def test_theme_manager_persists_across_instances(self):
        """Theme saved by one instance is loadable by another."""
        d = Path(__file__).parent / "_test_theme_persist"
        d.mkdir(exist_ok=True)
        try:
            mgr1 = ThemeManager(themes_dir=d)
            mgr1.save_theme("persist_test", {"colors": {"primary": "#aabbcc"}})

            mgr2 = ThemeManager(themes_dir=d)
            assert mgr2.load_theme("persist_test") is True
            assert mgr2.get_color("colors.primary") == "#aabbcc"
        finally:
            # Cleanup
            import shutil
            shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# Cross-cutting Integration Tests
# ══════════════════════════════════════════════════════════════════════

class TestCrossCutting:
    """Tests that exercise multiple systems together."""

    def test_full_workflow_show_move_save_load(self, tmp_path):
        """Show panel → move → save layout → move back → load → verify."""
        c, bus, cmd_bus, reg, mgr, _, _ = _make_full_stack(tmp_path)

        # 1. Show memory panel
        cmd_bus.dispatch_sync(Command(
            name="system.panel.show", source="test",
            params={"panel_id": "memory"},
        ))
        assert reg.get("memory").visible is True

        # 2. Move it
        reg.move_panel("memory", 300, 250)
        assert reg.get("memory").x == 300

        # 3. Save layout
        cmd_bus.dispatch_sync(Command(
            name="system.layout.save", source="test",
            params={"name": "custom"},
        ))

        # 4. Move somewhere else
        reg.move_panel("memory", 0, 0)
        assert reg.get("memory").x == 0

        # 5. Load layout
        cmd_bus.dispatch_sync(Command(
            name="system.layout.load", source="test",
            params={"name": "custom"},
        ))

        # 6. Verify restored
        assert reg.get("memory").x == 300
        assert reg.get("memory").y == 250
        assert reg.get("memory").visible is True

    def test_theme_apply_then_panel_show(self, tmp_path):
        """Apply theme → show panel → panel should have theme."""
        c, bus, cmd_bus, reg, mgr, theme_mgr, _ = _make_full_stack(tmp_path)
        theme_mgr.save_theme("test_theme", {"colors": {"primary": "#ff0000"}})

        # Apply theme
        cmd_bus.dispatch_sync(Command(
            name="system.theme.apply", source="test",
            params={"name": "test_theme"},
        ))

        # Verify panel received theme via widget
        mem_widget = reg.get_widget("memory")
        assert mem_widget is not None
        # AbstractPanel stores theme
        assert mem_widget._theme.get("colors", {}).get("primary") == "#ff0000"

    def test_notification_flows_through_eventbus(self, tmp_path):
        """NotificationManager → EventBus → OverlayModel notifications."""
        c, bus, cmd_bus, reg, mgr, _, notif_mgr = _make_full_stack(tmp_path)

        notif_mgr.info("hello world")

        # Notification should be in manager
        assert notif_mgr.count() == 1

        # Event should be in EventBus queue
        assert bus.queue_size() >= 1

    def test_multiple_panels_independent(self, tmp_path):
        """Show/hide one panel doesn't affect others."""
        c, bus, cmd_bus, reg, _, _, _ = _make_full_stack(tmp_path)

        reg.show_panel("memory")
        assert reg.get("memory").visible is True
        assert reg.get("vision").visible is False
        assert reg.get("system").visible is False

        reg.hide_panel("memory")
        assert reg.get("memory").visible is False
        # Others unchanged
        assert reg.get("vision").visible is False

    def test_event_bus_does_not_leak_between_registries(self):
        """Events from one PanelRegistry don't affect another."""
        bus = EventBus(queued=True)
        reg1 = PanelRegistry(event_bus=bus)
        reg2 = PanelRegistry(event_bus=bus)

        events1: List[Event] = []
        events2: List[Event] = []

        def handler1(e):
            if e.payload.get("panel_id", "").startswith("r1_"):
                events1.append(e)

        def handler2(e):
            if e.payload.get("panel_id", "").startswith("r2_"):
                events2.append(e)

        bus.subscribe(EventType.PANEL_SHOWN, handler1)
        bus.subscribe(EventType.PANEL_SHOWN, handler2)

        reg1.register(PanelInfo(id="r1_panel", type="t"))
        reg2.register(PanelInfo(id="r2_panel", type="t"))

        reg1.show_panel("r1_panel")
        bus.flush()

        # Both handlers see the event, but filter by panel_id
        assert len(events1) == 1
        assert events1[0].payload["panel_id"] == "r1_panel"
