"""InteractionPlugin — wires InteractionController to Aether runtime.

Architecture:
    Mouse/Hand → InputRouter → InteractionController → InteractionBridge → OverlayModel → Widgets

This plugin:
1. Creates InteractionController, InputRouter, InteractionBridge
2. Routes mouse events to InputRouter
3. Calls InteractionBridge.update() each frame to sync state to OverlayModel
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from aether.core.plugin import TickablePlugin, PluginMetadata
from aether.core.service_container import ServiceContainer
from aether.interaction.interaction_controller import InteractionController
from aether.interaction.input_router import InputRouter
from aether.ui.interaction_bridge import InteractionBridge

if TYPE_CHECKING:
    pass

logger = logging.getLogger("Aether.InteractionPlugin")


class InteractionPlugin(TickablePlugin):
    """Wires InteractionController to Aether runtime.

    Creates the interaction layer and bridges state to OverlayModel
    for rendering.
    """

    name = "interaction_plugin"

    def __init__(self) -> None:
        self._container: Optional[ServiceContainer] = None
        self._event_bus = None
        self._command_bus = None
        self._overlay_model = None
        self._ic: Optional[InteractionController] = None
        self._router: Optional[InputRouter] = None
        self._bridge: Optional[InteractionBridge] = None
        self._running = False

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="Interaction", version="1.0", category="interaction",
            description="Interaction layer connecting input to panel control"
        )

    def initialize(self, container: ServiceContainer) -> None:
        self._container = container
        self._command_bus = container.resolve("command_bus")
        self._event_bus = container.resolve("event_bus")

        # Get overlay model from GUIPlugin (must be initialized first)
        if container.has("overlay_model"):
            self._overlay_model = container.resolve("overlay_model")

        logger.info("InteractionPlugin initialized")

    def start(self) -> None:
        if not self._overlay_model:
            raise RuntimeError(
                "InteractionPlugin requires OverlayModel — GUIPlugin must start first"
            )

        if not self._container:
            raise RuntimeError("InteractionPlugin requires ServiceContainer")

        panel_registry = None
        if self._container.has("panel_registry"):
            panel_registry = self._container.resolve("panel_registry")

        if not panel_registry:
            raise RuntimeError(
                "InteractionPlugin requires PanelRegistry — GUIPlugin must register it"
            )

        # Create InteractionController
        self._ic = InteractionController(panel_registry, self._event_bus)

        # Create InputRouter
        self._router = InputRouter(self._ic)

        # Create InteractionBridge
        self._bridge = InteractionBridge(
            self._ic,
            self._overlay_model,
            screen_width=1920,
            screen_height=1080,
        )

        # Register with DI container
        self._container.register_instance("interaction_controller", self._ic)
        self._container.register_instance("input_router", self._router)

        self._running = True
        logger.info("InteractionPlugin started")

    def update(self, dt: float) -> None:
        """Called each frame to sync interaction state to OverlayModel."""
        if self._bridge:
            self._bridge.update(dt)

    def stop(self) -> None:
        self._running = False
        logger.info("InteractionPlugin stopped")

    # ── Input routing ───────────────────────────────────────────────

    def on_mouse_move(self, x: float, y: float) -> None:
        """Route mouse move to InputRouter."""
        if self._router:
            self._router.on_mouse_move(x, y)

    def on_mouse_press(self, x: float, y: float) -> None:
        """Route mouse press to InputRouter."""
        if self._router:
            self._router.on_mouse_press(x, y)

    def on_mouse_release(self, x: float, y: float) -> None:
        """Route mouse release to InputRouter."""
        if self._router:
            self._router.on_mouse_release(x, y)

    def on_hand_move(self, x: float, y: float) -> None:
        """Route hand tracking move to InputRouter."""
        if self._router:
            self._router.on_hand_move(x, y)

    def on_hand_pinch_start(self, x: float, y: float) -> None:
        """Route hand pinch start to InputRouter."""
        if self._router:
            self._router.on_hand_pinch_start(x, y)

    def on_hand_pinch_end(self, x: float, y: float) -> None:
        """Route hand pinch end to InputRouter."""
        if self._router:
            self._router.on_hand_pinch_end(x, y)

    def cancel(self) -> None:
        """Cancel current interaction."""
        if self._router:
            self._router.cancel()
