"""Test plugin loading and instantiation.

These tests verify that all plugins can be constructed and that
TickablePlugin subclasses implement the required update(dt) method.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from aether.core.plugin import PluginBase, TickablePlugin, PluginMetadata
from aether.core.service_container import ServiceContainer


class TestPluginBase:
    """Tests for PluginBase abstract class."""

    def test_plugin_requires_name(self):
        """Plugin subclass must define a name class attribute."""
        with pytest.raises(TypeError, match="must define a 'name'"):
            class BadPlugin(PluginBase):
                pass

    def test_plugin_with_name(self):
        """Plugin subclass with name attribute works."""
        class GoodPlugin(PluginBase):
            name = "good_plugin"
            def initialize(self, container):
                pass

        p = GoodPlugin()
        assert p.name == "good_plugin"

    def test_plugin_metadata_default(self):
        """Plugin gets default metadata from name."""
        class TestPlugin(PluginBase):
            name = "test_plugin"
            def initialize(self, container):
                pass

        p = TestPlugin()
        assert p.metadata.label == "test_plugin"
        assert p.metadata.version == "1.0"

    def test_plugin_metadata_custom(self):
        """Plugin can override metadata."""
        class CustomPlugin(PluginBase):
            name = "custom_plugin"
            def initialize(self, container):
                pass

            @property
            def metadata(self):
                return PluginMetadata(label="Custom", version="2.0")

        p = CustomPlugin()
        assert p.metadata.label == "Custom"
        assert p.metadata.version == "2.0"


class TestTickablePlugin:
    """Tests for TickablePlugin abstract class."""

    def test_tickable_plugin_requires_update(self):
        """TickablePlugin subclass must implement update(dt)."""
        with pytest.raises(TypeError, match="abstract method"):
            class BadTickable(TickablePlugin):
                name = "bad_tickable"
                def initialize(self, container):
                    pass
                # Missing update(dt)

            BadTickable()

    def test_tickable_plugin_with_update(self):
        """TickablePlugin subclass with update(dt) works."""
        class GoodTickable(TickablePlugin):
            name = "good_tickable"
            def initialize(self, container):
                pass
            def update(self, dt):
                pass

        p = GoodTickable()
        assert p.name == "good_tickable"
        assert callable(p.update)

    def test_tickable_plugin_start_stop(self):
        """TickablePlugin has default start() and stop() methods."""
        class TestTickable(TickablePlugin):
            name = "test_tickable"
            def initialize(self, container):
                pass
            def update(self, dt):
                pass

        p = TestTickable()
        # Should not raise
        p.start()
        p.stop()


class TestConcretePlugins:
    """Tests that concrete plugins can be imported and instantiated."""

    def test_interaction_plugin_importable(self):
        """InteractionPlugin can be imported."""
        from aether.plugins.interaction_plugin import InteractionPlugin
        assert InteractionPlugin.name == "interaction_plugin"

    def test_interaction_plugin_instantiable(self):
        """InteractionPlugin can be instantiated (not abstract)."""
        from aether.plugins.interaction_plugin import InteractionPlugin
        p = InteractionPlugin()
        assert p is not None
        assert hasattr(p, "update")
        assert callable(p.update)

    def test_gesture_plugin_importable(self):
        """GesturePlugin can be imported."""
        from aether.plugins.gesture_plugin import GesturePlugin
        assert GesturePlugin.name == "gesture_plugin"

    def test_gesture_plugin_instantiable(self):
        """GesturePlugin can be instantiated (not abstract)."""
        from aether.plugins.gesture_plugin import GesturePlugin
        p = GesturePlugin()
        assert p is not None
        assert hasattr(p, "update")
        assert callable(p.update)

    def test_system_commands_plugin_importable(self):
        """SystemCommandPlugin can be imported."""
        from aether.plugins.system_commands_plugin import SystemCommandPlugin
        assert SystemCommandPlugin.name == "system_commands_plugin"

    def test_system_commands_plugin_instantiable(self):
        """SystemCommandPlugin can be instantiated."""
        from aether.plugins.system_commands_plugin import SystemCommandPlugin
        p = SystemCommandPlugin()
        assert p is not None

    def test_all_plugins_have_name(self):
        """All plugin classes have a non-empty name attribute."""
        from aether.plugins.interaction_plugin import InteractionPlugin
        from aether.plugins.gesture_plugin import GesturePlugin
        from aether.plugins.system_commands_plugin import SystemCommandPlugin

        plugins = [InteractionPlugin, GesturePlugin, SystemCommandPlugin]
        for plugin_cls in plugins:
            assert plugin_cls.name, f"{plugin_cls.__name__} missing name"


class TestPluginInitialization:
    """Tests for plugin initialization flow."""

    def test_interaction_plugin_initialize(self):
        """InteractionPlugin.initialize() can be called."""
        from aether.plugins.interaction_plugin import InteractionPlugin

        container = ServiceContainer()
        container.register_instance("event_bus", MagicMock())
        container.register_instance("command_bus", MagicMock())

        p = InteractionPlugin()
        p.initialize(container)

        assert p._container is container
        assert p._event_bus is not None

    def test_gesture_plugin_initialize(self):
        """GesturePlugin.initialize() can be called."""
        from aether.plugins.gesture_plugin import GesturePlugin

        container = ServiceContainer()
        container.register_instance("event_bus", MagicMock())

        p = GesturePlugin()
        p.initialize(container)

        assert p._container is container
        assert p._hand_controller is not None

    def test_interaction_plugin_update_callable(self):
        """InteractionPlugin.update(dt) can be called."""
        from aether.plugins.interaction_plugin import InteractionPlugin

        p = InteractionPlugin()
        # Should not raise (bridge is None, so it's a no-op)
        p.update(0.016)

    def test_gesture_plugin_update_callable(self):
        """GesturePlugin.update(dt) can be called."""
        from aether.plugins.gesture_plugin import GesturePlugin

        p = GesturePlugin()
        # Should not raise
        p.update(0.016)


class TestGestureEnum:
    """Tests for the new Gesture enum."""

    def test_gesture_from_mediapipe_open_palm(self):
        """MediaPipe 'Open_Palm' normalizes to Gesture.OPEN_PALM."""
        from aether.interaction.gestures import Gesture

        assert Gesture.from_mediapipe("Open_Palm") == Gesture.OPEN_PALM

    def test_gesture_from_mediapipe_lowercase(self):
        """MediaPipe 'open_palm' normalizes to Gesture.OPEN_PALM."""
        from aether.interaction.gestures import Gesture

        assert Gesture.from_mediapipe("open_palm") == Gesture.OPEN_PALM

    def test_gesture_from_mediapipe_pinch(self):
        """MediaPipe 'Pinch' normalizes to Gesture.PINCH."""
        from aether.interaction.gestures import Gesture

        assert Gesture.from_mediapipe("Pinch") == Gesture.PINCH

    def test_gesture_from_mediapipe_closed_fist(self):
        """MediaPipe 'Closed_Fist' normalizes to Gesture.CLOSED_FIST."""
        from aether.interaction.gestures import Gesture

        assert Gesture.from_mediapipe("Closed_Fist") == Gesture.CLOSED_FIST

    def test_gesture_from_mediapipe_unknown(self):
        """Unknown gesture normalizes to Gesture.NONE."""
        from aether.interaction.gestures import Gesture

        assert Gesture.from_mediapipe("UnknownGesture") == Gesture.NONE

    def test_gesture_from_mediapipe_empty(self):
        """Empty string normalizes to Gesture.NONE."""
        from aether.interaction.gestures import Gesture

        assert Gesture.from_mediapipe("") == Gesture.NONE

    def test_gesture_from_mediapipe_none(self):
        """None normalizes to Gesture.NONE."""
        from aether.interaction.gestures import Gesture

        assert Gesture.from_mediapipe(None) == Gesture.NONE

    def test_gesture_value_is_lowercase(self):
        """Gesture enum values are lowercase strings for config lookup."""
        from aether.interaction.gestures import Gesture

        assert Gesture.PINCH.value == "pinch"
        assert Gesture.OPEN_PALM.value == "open_palm"
        assert Gesture.CLOSED_FIST.value == "closed_fist"

    def test_gesture_config_lookup(self):
        """Gesture.from_config() works with config values."""
        from aether.interaction.gestures import Gesture

        assert Gesture.from_config("pinch") == Gesture.PINCH
        assert Gesture.from_config("open_palm") == Gesture.OPEN_PALM

    def test_hand_input_event_gesture_enum(self):
        """HandInputEvent.gesture_enum returns canonical Gesture."""
        from aether.interaction.hand_controller import HandInputEvent, HandGesture
        from aether.interaction.gestures import Gesture

        event = HandInputEvent(gesture=HandGesture.PINCH)
        assert event.gesture_enum == Gesture.PINCH

        event2 = HandInputEvent(gesture=HandGesture.OPEN_PALM)
        assert event2.gesture_enum == Gesture.OPEN_PALM
