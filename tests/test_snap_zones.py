"""Tests for SnapZoneManager — edge/center/dock snap behavior."""
import pytest
from aether.interaction.snap_zones import SnapZoneManager, SnapType
from aether.ui.panel.panel_registry import PanelRegistry
from aether.ui.panel.panel_info import PanelInfo


@pytest.fixture
def registry():
    r = PanelRegistry()
    r.register(PanelInfo(id="p1", type="test", x=100, y=100, w=400, h=300))
    r.register(PanelInfo(id="p2", type="test", x=500, y=100, w=400, h=300))
    return r


def test_default_threshold(registry):
    snap = SnapZoneManager(registry)
    assert snap.threshold == 30


def test_threshold_setter(registry):
    snap = SnapZoneManager(registry)
    snap.threshold = 50
    assert snap.threshold == 50
    snap.threshold = 200  # clamped to 100
    assert snap.threshold == 100
    snap.threshold = 5  # clamped to 10
    assert snap.threshold == 10


def test_snap_edge_left(registry):
    snap = SnapZoneManager(registry, screen_width=1920, screen_height=1080, snap_threshold=50)
    result = snap.find_snap(10, 100, 400, 300)
    assert result.active
    assert result.snap_type == SnapType.EDGE_LEFT
    assert result.target_x == 0


def test_snap_edge_right(registry):
    snap = SnapZoneManager(registry, screen_width=1920, screen_height=1080, snap_threshold=50)
    # Panel right edge (x + w) near screen right edge: 1520 + 400 = 1920
    result = snap.find_snap(1520, 100, 400, 300)
    assert result.active
    assert result.snap_type == SnapType.EDGE_RIGHT
    assert result.target_x == 1520  # 1920 - 400

def test_snap_edge_right_almost(registry):
    snap = SnapZoneManager(registry, screen_width=1920, screen_height=1080, snap_threshold=50)
    # Panel right edge near screen edge: 1540 + 400 = 1940, dist = 20
    result = snap.find_snap(1540, 100, 400, 300)
    assert result.active
    assert result.snap_type == SnapType.EDGE_RIGHT


def test_snap_edge_top(registry):
    snap = SnapZoneManager(registry, screen_width=1920, screen_height=1080, snap_threshold=50)
    result = snap.find_snap(100, 10, 400, 300)
    assert result.active
    assert result.snap_type == SnapType.EDGE_TOP
    assert result.target_y == 0


def test_snap_edge_bottom(registry):
    snap = SnapZoneManager(registry, screen_width=1920, screen_height=1080, snap_threshold=50)
    result = snap.find_snap(100, 750, 400, 300)
    assert result.active
    assert result.snap_type == SnapType.EDGE_BOTTOM
    assert result.target_y == 780  # 1080 - 300


def test_no_snap_when_far(registry):
    snap = SnapZoneManager(registry, screen_width=1920, screen_height=1080, snap_threshold=30)
    result = snap.find_snap(500, 500, 400, 300)
    assert not result.active


def test_snap_dock_left(registry):
    snap = SnapZoneManager(registry, screen_width=1920, screen_height=1080, snap_threshold=100)
    result = snap.find_snap(5, 0, 400, 300)
    # Should snap to edge (closer) not dock
    assert result.active


def test_snap_dock_right(registry):
    snap = SnapZoneManager(registry, screen_width=1920, screen_height=1080, snap_threshold=100)
    dw = int(1920 * 0.5)
    result = snap.find_snap(1920 - dw - 5, 0, 400, 300)
    # Near dock_right zone
    assert result.active


def test_active_zones_cleared(registry):
    snap = SnapZoneManager(registry, screen_width=1920, screen_height=1080)
    snap.find_snap(10, 10, 400, 300)
    assert len(snap.active_zones) > 0
    snap.clear_active_zones()
    assert len(snap.active_zones) == 0


def test_set_screen_size(registry):
    snap = SnapZoneManager(registry, screen_width=1920, screen_height=1080)
    snap.set_screen_size(2560, 1440)
    result = snap.find_snap(10, 10, 400, 300)
    assert result.active  # Still snaps to left edge
    assert result.target_x == 0


def test_is_snapped(registry):
    snap = SnapZoneManager(registry, screen_width=1920, screen_height=1080, snap_threshold=50)
    assert snap.is_snapped(10, 100, 400, 300)  # close to left edge
    assert not snap.is_snapped(500, 500, 400, 300)  # far from all edges
