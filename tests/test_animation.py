"""Tests for AnimationManager — smooth panel transitions."""
import math
from aether.interaction.animation import AnimationManager, _lerp


def test_lerp_convergence():
    """_lerp approaches target over time."""
    val = 0.0
    for _ in range(100):
        val = _lerp(val, 100.0, 1.0 / 60.0)
    assert abs(val - 100.0) < 1.0


def test_lerp_instant_at_target():
    """_lerp returns target immediately when already close."""
    assert _lerp(100.0, 100.0, 1.0) == 100.0


def test_lerp_jumps_small_distance():
    """_lerp handles tiny gaps."""
    assert _lerp(99.95, 100.0, 1.0) == 100.0


def test_animation_manager_ensure():
    """ensure() creates panel if missing."""
    mgr = AnimationManager()
    anim = mgr.ensure("p1")
    assert anim.panel_id == "p1"
    assert mgr.has("p1")


def test_animation_manager_set_geometry():
    """set_geometry snap targets to current."""
    mgr = AnimationManager()
    mgr.set_geometry("p1", 100, 200, 400, 300)
    anim = mgr.get("p1")
    assert anim.current_x == 100
    assert anim.current_y == 200
    assert anim.current_w == 400
    assert anim.current_h == 300
    assert anim.target_x == 100


def test_animation_manager_move_to():
    """move_to sets target position."""
    mgr = AnimationManager()
    mgr.set_geometry("p1", 100, 200, 400, 300)
    mgr.move_to("p1", 500, 600)
    anim = mgr.get("p1")
    assert anim.target_x == 500
    assert anim.target_y == 600


def test_animation_update_moves_toward_target():
    """update() lerps toward target over time."""
    mgr = AnimationManager()
    mgr.set_geometry("p1", 0, 0, 400, 300)
    mgr.move_to("p1", 100, 100)

    dirty = mgr.update(1.0 / 60.0)
    assert "p1" in dirty
    anim = mgr.get("p1")
    assert anim.current_x > 0
    assert anim.current_y > 0


def test_animation_update_converges():
    """After many updates, position matches target."""
    mgr = AnimationManager()
    mgr.set_geometry("p1", 0, 0, 400, 300)
    mgr.move_to("p1", 100, 100)

    for _ in range(200):
        mgr.update(1.0 / 60.0)

    anim = mgr.get("p1")
    assert abs(anim.current_x - 100.0) < 1.0
    assert abs(anim.current_y - 100.0) < 1.0


def test_animation_show_hide():
    """show/hide controls opacity targets."""
    mgr = AnimationManager()
    mgr.set_geometry("p1", 0, 0, 400, 300)
    mgr.hide("p1")
    anim = mgr.get("p1")
    assert anim.target_opacity == 0.0

    mgr.show("p1")
    assert anim.target_opacity == 1.0


def test_animation_hide_converges():
    """Opacity approaches 0 when hidden."""
    mgr = AnimationManager()
    mgr.set_geometry("p1", 0, 0, 400, 300)
    mgr.hide("p1")

    for _ in range(100):
        mgr.update(1.0 / 60.0)

    anim = mgr.get("p1")
    assert abs(anim.opacity - 0.0) < 0.02


def test_animation_remove():
    """remove() deletes panel."""
    mgr = AnimationManager()
    mgr.set_geometry("p1", 0, 0, 400, 300)
    assert mgr.has("p1")
    mgr.remove("p1")
    assert not mgr.has("p1")


def test_animation_clear():
    """clear() removes all panels."""
    mgr = AnimationManager()
    mgr.set_geometry("p1", 0, 0, 400, 300)
    mgr.set_geometry("p2", 100, 100, 200, 200)
    assert len(mgr.panels) == 2
    mgr.clear()
    assert len(mgr.panels) == 0


def test_no_dirty_when_settled():
    """update() returns empty set when all panels at target."""
    mgr = AnimationManager()
    mgr.set_geometry("p1", 100, 200, 400, 300)

    for _ in range(200):
        mgr.update(1.0 / 60.0)

    dirty = mgr.update(1.0 / 60.0)
    assert "p1" not in dirty
