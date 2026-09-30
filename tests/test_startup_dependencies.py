"""Startup dependency validation tests.

Covers:
    - StartupDependencyValidator unit tests
    - Happy path: InteractionPlugin → InputRouter → GesturePlugin
    - Missing dependency: GesturePlugin without InputRouter
    - Wrong order: GesturePlugin starts before InteractionPlugin
"""

import pytest
from aether.core.service_container import ServiceContainer
from aether.core.startup_validator import (
    StartupDependencyValidator,
    PluginDependency,
    DependencyError,
)
from aether.core.plugin import PluginBase, TickablePlugin
from aether.interaction.input_router import InputRouter
from aether.interaction.interaction_controller import InteractionController
from aether.ui.panel.panel_registry import PanelRegistry
from aether.ui.panel.panel_info import PanelInfo


# ── Unit tests: StartupDependencyValidator ──────────────────────────


def test_validator_passes_with_registered_services():
    container = ServiceContainer()
    container.register_instance("input_router", object())
    container.register_instance("interaction_controller", object())

    validator = StartupDependencyValidator(container)
    validator.register("gesture_plugin",
        PluginDependency("input_router", "InputRouter"),
        PluginDependency("interaction_controller", "InteractionController"),
    )
    report = validator.validate()
    assert report.passed
    assert report.failed == 0


def test_validator_fails_on_missing_service():
    container = ServiceContainer()
    container.register_instance("something_else", object())

    validator = StartupDependencyValidator(container)
    validator.register("gesture_plugin",
        PluginDependency("input_router", "InputRouter"),
    )
    with pytest.raises(DependencyError) as exc:
        validator.validate()
    assert "input_router" in str(exc.value)


def test_validator_fails_on_multiple_missing():
    container = ServiceContainer()

    validator = StartupDependencyValidator(container)
    validator.register("gesture_plugin",
        PluginDependency("input_router", "InputRouter"),
        PluginDependency("cursor_mapper", "CursorMapper"),
    )
    with pytest.raises(DependencyError) as exc:
        validator.validate()
    error_msg = str(exc.value)
    assert "input_router" in error_msg
    assert "cursor_mapper" in error_msg


def test_validator_clear():
    container = ServiceContainer()
    container.register_instance("input_router", object())

    validator = StartupDependencyValidator(container)
    validator.register("gesture_plugin",
        PluginDependency("input_router", "InputRouter"),
    )
    validator.validate()  # passes

    validator.clear()
    validator.register("gesture_plugin",
        PluginDependency("missing_svc", "DoesNotExist"),
    )
    with pytest.raises(DependencyError):
        validator.validate()


def test_validator_multiple_plugins():
    container = ServiceContainer()
    container.register_instance("event_bus", object())
    container.register_instance("input_router", object())

    validator = StartupDependencyValidator(container)
    validator.register("interaction_plugin",
        PluginDependency("event_bus", "EventBus"),
    )
    validator.register("gesture_plugin",
        PluginDependency("input_router", "InputRouter"),
        PluginDependency("event_bus", "EventBus"),
    )
    report = validator.validate()
    assert report.passed
    assert report.total == 3


def test_validator_partial_failure():
    container = ServiceContainer()
    container.register_instance("event_bus", object())
    # input_router missing

    validator = StartupDependencyValidator(container)
    validator.register("gesture_plugin",
        PluginDependency("event_bus", "EventBus"),
        PluginDependency("input_router", "InputRouter"),
    )
    with pytest.raises(DependencyError):
        validator.validate()


# ── Case A: Happy Path ──────────────────────────────────────────────


def test_happy_path_interaction_then_gesture():
    """InteractionPlugin creates InputRouter, registers it, GesturePlugin resolves it."""
    container = ServiceContainer()
    container.register_instance("event_bus", object())

    # Simulate InteractionPlugin.start()
    panel_registry = PanelRegistry()
    panel_registry.register(PanelInfo(id="test", type="test", x=0, y=0, w=400, h=300, visible=True))
    ic = InteractionController(panel_registry)
    router = InputRouter(ic)
    container.register_instance("interaction_controller", ic)
    container.register_instance("input_router", router)

    # Validate before GesturePlugin.start()
    validator = StartupDependencyValidator(container)
    validator.register("gesture_plugin",
        PluginDependency("input_router", "InputRouter"),
        PluginDependency("interaction_controller", "InteractionController"),
    )
    report = validator.validate()
    assert report.passed

    # GesturePlugin resolves successfully
    resolved_router = container.resolve("input_router")
    assert resolved_router is router


# ── Case B: Missing InteractionPlugin ──────────────────────────────


def test_missing_interaction_plugin_fails_fast():
    """GesturePlugin without InteractionPlugin → explicit error, not silent warning."""
    container = ServiceContainer()
    container.register_instance("event_bus", object())

    # input_router was never registered (InteractionPlugin didn't start)

    validator = StartupDependencyValidator(container)
    validator.register("gesture_plugin",
        PluginDependency("input_router", "InputRouter"),
        PluginDependency("interaction_controller", "InteractionController"),
    )

    with pytest.raises(DependencyError) as exc:
        validator.validate()
    assert "input_router" in str(exc.value)
    assert "interaction_controller" in str(exc.value)


# ── Case C: Wrong Startup Order ────────────────────────────────────


def test_wrong_startup_order_fails():
    """GesturePlugin starts before InteractionPlugin → resolve fails."""
    container = ServiceContainer()

    # Neither service registered yet (simulating wrong order)
    with pytest.raises(Exception):
        container.resolve("input_router")


def test_gesture_plugin_requires_registered_router():
    """GesturePlugin constructor must receive a valid InputRouter — not None."""
    container = ServiceContainer()
    container.register_instance("event_bus", object())

    # Simulate starting GesturePlugin before InteractionPlugin
    assert not container.has("input_router")

    validator = StartupDependencyValidator(container)
    validator.register("gesture_plugin",
        PluginDependency("input_router", "InputRouter"),
    )

    with pytest.raises(DependencyError):
        validator.validate()


def test_interaction_plugin_requires_panel_registry():
    """InteractionPlugin fails fast if PanelRegistry is missing."""
    container = ServiceContainer()
    container.register_instance("event_bus", object())
    container.register_instance("command_bus", object())

    assert not container.has("panel_registry")

    validator = StartupDependencyValidator(container)
    validator.register("interaction_plugin",
        PluginDependency("panel_registry", "PanelRegistry"),
    )

    with pytest.raises(DependencyError):
        validator.validate()


def test_full_boot_validation_simulated():
    """Simulate full boot with all required services present."""
    container = ServiceContainer()
    container.register_instance("event_bus", object())
    container.register_instance("command_bus", object())
    container.register_instance("config", object())
    container.register_instance("panel_registry", PanelRegistry())
    container.register_instance("interaction_controller", object())
    container.register_instance("input_router", object())
    container.register_instance("cursor_mapper", object())
    container.register_instance("memory_manager", object())

    validator = StartupDependencyValidator(container)
    validator.register("interaction_plugin",
        PluginDependency("panel_registry", "PanelRegistry"),
        PluginDependency("event_bus", "EventBus"),
        PluginDependency("command_bus", "CommandBus"),
    )
    validator.register("gesture_plugin",
        PluginDependency("input_router", "InputRouter"),
        PluginDependency("cursor_mapper", "CursorMapper"),
    )
    validator.register("memory_plugin",
        PluginDependency("memory_manager", "MemoryManager"),
    )

    report = validator.validate()
    assert report.passed
    assert report.total == 6