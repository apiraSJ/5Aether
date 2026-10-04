"""BaselinePlugin — M1 Deterministic Baseline lifecycle and commands.

M1 flow:
    Camera frame → user picks Component 1..5 → baseline.capture → snapshot file
    + SQLite record → baseline.captured → UI.

The plugin reuses existing infrastructure only:
    - MemoryManager (registered by MemoryPlugin) for `component:<id>` records
    - FrameBroker.get_frame() for the raw camera frame (frames never on EventBus)
    - CommandBus + EventBus for "baseline.*" commands/events

Commands registered:
    baseline.select   — pick the target component (publishes baseline.selected)
    baseline.capture  — snapshot the current frame for the component
    baseline.status   — seeded / captured summary
    baseline.list     — render the baseline table
    baseline.info     — show the full catalog entry for a component (M2 voice target)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from aether.core.command import Command
from aether.core.command_registry import CommandRegistry, CommandInfo
from aether.core.event_bus_v2 import Event
from aether.core.event_type import EventType
from aether.core.plugin import PluginBase, PluginMetadata
from aether.core.service_container import ServiceContainer
from aether.baseline.baseline_service import BaselineService
from aether.sandbox.catalog import get_component

logger = logging.getLogger("Aether.BaselinePlugin")

_BASELINE_COMMANDS = [
    CommandInfo(
        name="baseline.select",
        description="Select a maintenance component as the capture target",
        category="baseline",
        params_help="<component_id 1-5>",
        examples=("baseline.select 1",),
    ),
    CommandInfo(
        name="baseline.capture",
        description="Snapshot the current camera frame for the selected component",
        category="baseline",
        params_help="<component_id 1-5>",
        examples=("baseline.capture 2",),
    ),
    CommandInfo(
        name="baseline.status",
        description="Show seeded / captured baseline summary",
        category="baseline",
    ),
    CommandInfo(
        name="baseline.list",
        description="List all baseline components and their snapshots",
        category="baseline",
        aliases=("baseline",),
    ),
    CommandInfo(
        name="baseline.info",
        description="Show the full catalog entry (specs / inspection / troubleshooting) for a component",
        category="baseline",
        params_help="<component_id 1-5>",
        examples=("baseline.info 2",),
    ),
]


class BaselinePlugin(PluginBase):
    """Owns the BaselineService and exposes the deterministic baseline flow."""

    name = "baseline_plugin"

    def __init__(self) -> None:
        self._container: Optional[ServiceContainer] = None
        self._event_bus = None
        self._command_bus = None
        self._frame_broker = None
        self._service: Optional[BaselineService] = None
        self._snapshots_dir: str = "data"

    @property
    def service(self) -> Optional[BaselineService]:
        return self._service

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="Baseline",
            version="1.0",
            category="baseline",
            commands=[c.name for c in _BASELINE_COMMANDS],
            description="M1 deterministic baseline: component capture to SQLite",
        )

    def initialize(self, container: ServiceContainer) -> None:
        self._container = container
        self._event_bus = container.resolve("event_bus")
        self._command_bus = container.resolve("command_bus")

        if container.has("config"):
            config = container.resolve("config")
            self._snapshots_dir = config.get("baseline.snapshots_dir", "data")

        if container.has("frame_broker"):
            self._frame_broker = container.resolve("frame_broker")

        memory = container.resolve("memory_manager")
        self._service = BaselineService(memory, snapshots_dir=self._snapshots_dir)
        container.register_instance("baseline_service", self._service)

        self._register_commands()
        logger.info("BaselinePlugin initialized (snapshots_dir=%s)", self._snapshots_dir)

    def start(self) -> None:
        if self._service is not None:
            seeded = self._service.seed_catalog()
            logger.info("BaselinePlugin seeded %d component(s)", seeded)
        logger.info("BaselinePlugin started")

    def is_ready(self) -> bool:
        return self._service is not None

    def stop(self) -> None:
        logger.info("BaselinePlugin stopped (memory owned by MemoryPlugin)")

    # ── Command registration ──────────────────────────────────────

    def _register_commands(self) -> None:
        if not self._container:
            return

        registry = None
        if self._container.has("command_registry"):
            registry = self._container.resolve("command_registry")
        else:
            registry = CommandRegistry()
            registry.initialize(self._container)

        for cmd_info in _BASELINE_COMMANDS:
            registry.register(cmd_info)

        if self._command_bus:
            self._command_bus.register_handler("baseline.select", self._handle_select)
            self._command_bus.register_handler("baseline.capture", self._handle_capture)
            self._command_bus.register_handler("baseline.status", self._handle_status)
            self._command_bus.register_handler("baseline.list", self._handle_list)
            self._command_bus.register_handler("baseline.info", self._handle_info)

    # ── Command handlers ──────────────────────────────────────────

    def _handle_select(self, command: Command) -> dict:
        component_id = str(command.params.get("component_id", "")).strip()
        comp = get_component(component_id)
        if comp is None:
            return {"message": "Unknown component. Pick id 1-5 (baseline.select <id>)."}
        if self._event_bus:
            self._event_bus.publish(Event(
                type=EventType.BASELINE_SELECTED,
                payload={"component_id": component_id, "name": comp["name"]},
                source=self.name,
            ))
        return {
            "message": f"Selected component {component_id}: {comp['name']}",
            "entry": {"component_id": component_id, "name": comp["name"]},
        }

    def _handle_capture(self, command: Command) -> dict:
        component_id = str(command.params.get("component_id", "")).strip()
        comp = get_component(component_id)
        if comp is None:
            return {"message": "Unknown component. Pick id 1-5 (baseline.capture <id>)."}
        if self._frame_broker is None:
            return {"message": "No camera available (FrameBroker not bound)."}
        frame = self._frame_broker.get_frame()
        if frame is None:
            return {"message": "No frame yet — wait for the camera stream."}
        if self._service is None:
            return {"message": "BaselineService not initialized."}
        value = self._service.capture(component_id, frame)
        if value is None:
            return {"message": "Capture failed (frame short-circuit)."}
        if self._event_bus:
            self._event_bus.publish(Event(
                type=EventType.BASELINE_CAPTURED,
                payload={
                    "component_id": component_id,
                    "name": comp["name"],
                    "snapshot_path": value.get("snapshot_path"),
                    "captured_at": value.get("captured_at"),
                },
                source=self.name,
            ))
        return {
            "message": (
                f"Captured {comp['name']} → {value.get('snapshot_path')}"
            ),
            "entry": value,
        }

    def _handle_status(self, command: Command) -> dict:
        if self._service is None:
            return {"message": "BaselineService not initialized."}
        status = self._service.baseline_status()
        return {
            "message": (
                f"Baseline: {status['captured']}/{status['seeded']} components captured"
            ),
            "status": status,
        }

    def _handle_list(self, command: Command) -> dict:
        if self._service is None:
            return {"message": "BaselineService not initialized."}
        entries = self._service.list_baselines()
        lines = [
            (
                f"  #{e['component_id']} {e['name']} — "
                f"{'captured' if e['captured'] else 'pending'}"
            )
            for e in entries
        ]
        if not lines:
            lines = ["  (catalog empty)"]
        return {
            "message": "Baseline catalog:\n" + "\n".join(lines),
            "baselines": entries,
        }

    def _handle_info(self, command: Command) -> dict:
        component_id = str(command.params.get("component_id", "")).strip()
        comp = get_component(component_id)
        if comp is None:
            return {"message": "Unknown component. Pick id 1-5 (baseline.info <id>)."}
        lines = [
            f"#{comp['id']} {comp['name']}",
            f"  specifications: {comp['specifications']}",
            f"  inspection: {comp['inspection_procedure']}",
            f"  troubleshooting: {comp['troubleshooting']}",
            f"  source: {comp['source_manual']}",
        ]
        return {
            "message": "\n".join(lines),
            "component": comp,
        }
