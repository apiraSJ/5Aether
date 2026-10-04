"""M2 integration — deterministic Voice → Text → Intent → Command, end-to-end.

No microphone, no vosk, no sounddevice, no external services. The default
deterministic provider drives the locked 6-intent script straight into the
real BaselinePlugin flow (select → capture → info → status → save alias).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from aether.core.command import Command
from aether.core.command_bus import CommandBus
from aether.core.command_registry import CommandRegistry
from aether.core.event_bus_v2 import Event, EventBus
from aether.core.event_type import EventType
from aether.core.frame_broker import FrameBroker
from aether.core.service_container import ServiceContainer
from aether.memory.memory_manager import MemoryManager
from aether.plugins.baseline_plugin import BaselinePlugin
from aether.plugins.voice_input_plugin import VoiceInputPlugin

SCRIPT = ["เลือก component 2", "ถ่ายภาพ", "แสดงข้อมูล", "สถานะ", "บันทึก"]


class _FakeConfig:
    def __init__(self, data):
        self._data = data

    def get(self, key_path, default=None):
        value = self._data
        for part in key_path.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "baseline.db")


@pytest.fixture
def snapshots_dir(tmp_path):
    return str(tmp_path)


@pytest.fixture
def container(db_path, snapshots_dir):
    c = ServiceContainer()
    event_bus = EventBus(queued=False)
    command_bus = CommandBus()
    c.register_instance("event_bus", event_bus)
    c.register_instance("command_bus", command_bus)
    c.register_instance("config", _FakeConfig({
        "baseline": {"snapshots_dir": snapshots_dir},
        "voice": {"enabled": True, "provider": "deterministic", "scripts": SCRIPT},
    }))
    registry = CommandRegistry()
    registry.initialize(c)

    memory = MemoryManager(db_path=db_path)
    memory.open()
    c.register_instance("memory_manager", memory)

    broker = FrameBroker(event_bus=event_bus)
    broker.update_frame(np.zeros((48, 64, 3), dtype=np.uint8))
    c.register_instance("frame_broker", broker)
    yield c
    memory.close()


@pytest.fixture
def plugins(container):
    baseline = BaselinePlugin()
    baseline.initialize(container)
    baseline.start()
    voice = VoiceInputPlugin()
    voice.initialize(container)
    voice.start()
    yield baseline, voice
    for p in (voice, baseline):
        try:
            p.stop()
        except Exception:
            pass


class TestDeterministicVoicePipeline:
    def test_full_script_runs_to_baseline(self, container, plugins, snapshots_dir):
        event_bus = container.resolve("event_bus")
        command_bus = container.resolve("command_bus")

        selected, captured, resolved = [], [], []
        event_bus.subscribe(EventType.BASELINE_SELECTED, lambda e: selected.append(e.payload))
        event_bus.subscribe(EventType.BASELINE_CAPTURED, lambda e: captured.append(e.payload))
        event_bus.subscribe(EventType.VOICE_INTENT_RESOLVED, lambda e: resolved.append(e.payload))

        for _ in range(len(SCRIPT)):
            command_bus.dispatch_sync(Command(name="voice.listen", source="test", params={}))
            command_bus.update()

        # Intent chain is deterministic and in order.
        assert [r["command"] for r in resolved] == [
            "baseline.select",
            "baseline.capture",
            "baseline.info",
            "baseline.status",
            "baseline.capture",  # บันทึก = save alias of capture
        ]

        # The bare "ถ่ายภาพ"/"บันทึก" intents fell back to the selected component 2.
        assert selected and selected[0]["component_id"] == "2"
        assert captured and all(c["component_id"] == "2" for c in captured)
        assert len(captured) == 2

        # Snapshot persisted where M1 defined it.
        snapshot = Path(snapshots_dir) / "baseline_snapshots" / "2.png"
        assert snapshot.exists()

        # Memory holds the component record.
        memory = container.resolve("memory_manager")
        assert memory.recall("component:2", "working").found

    def test_voice_text_injection_end_to_end(self, container, plugins):
        event_bus = container.resolve("event_bus")
        command_bus = container.resolve("command_bus")
        resolved = []
        event_bus.subscribe(EventType.VOICE_INTENT_RESOLVED, lambda e: resolved.append(e.payload))

        event_bus.publish(Event(
            type=EventType.BASELINE_SELECTED,
            payload={"component_id": "4"},
            source="test",
        ))
        result = command_bus.dispatch_sync(
            Command(name="voice.text", source="test", params={"text": "แสดงข้อมูล"})
        )
        assert result["command_name"] == "baseline.info"
        assert result["params"]["component_id"] == "4"
        command_bus.update()
        assert resolved[-1]["command"] == "baseline.info"

    def test_unknown_phrase_dispatches_nothing(self, container, plugins):
        event_bus = container.resolve("event_bus")
        command_bus = container.resolve("command_bus")
        errors = []
        event_bus.subscribe(EventType.VOICE_ERROR, lambda e: errors.append(e.payload))

        command_bus.dispatch_sync(
            Command(name="voice.text", source="test", params={"text": "ขออะไรก็ได้"})
        )
        command_bus.update()

        assert errors
        recent = command_bus.get_recent(50)
        assert all("baseline." not in c.name for c in recent)