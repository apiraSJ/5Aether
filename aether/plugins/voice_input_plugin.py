"""VoiceInputPlugin — M2 Voice/Input Pipeline adapter.

Solves Mic → STT → Text → Intent → Command (rule-based, no LLM):

    STT provider (deterministic | mic)
        → voice.text.ready event
        → VoiceIntentParser (Thai/EN rules)
        → voice.intent.resolved event + Command(source="voice") → CommandBus
             → baseline.select / baseline.capture / baseline.info / baseline.status

Commands:
    voice.listen   — pull one utterance from the configured STT provider
    voice.text     — inject raw text as transcribed speech (deterministic path)
    voice.status   — show provider / enabled / last result

The deterministic provider is the default so the whole pipeline runs and is
testable without a microphone. The real-mic provider (``voice.provider: mic``)
is config-gated and degrades to a voice.error event when sounddevice/vosk are
missing. Intents without an explicit component (ถ่ายภาพ / แสดงข้อมูล / บันทึก)
fall back to the last BASELINE_SELECTED component.

M2 emits events only — no UI/TTS (those are M4), no LLM/semantic (M3).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from aether.core.command import Command
from aether.core.command_registry import CommandInfo, CommandRegistry
from aether.core.event_bus_v2 import Event
from aether.core.event_type import EventType
from aether.core.intent_resolver import IntentResult
from aether.core.plugin import PluginBase, PluginMetadata
from aether.core.service_container import ServiceContainer
from aether.voice.audio import SoundDeviceCapturer
from aether.voice.intent_parser import VoiceIntentParser
from aether.voice.recognizers import VoskRecognizer
from aether.voice.stt import DeterministicSTTProvider, MicSTTProvider

logger = logging.getLogger("Aether.VoicePlugin")

_VOICE_COMMANDS = [
    CommandInfo(
        name="voice.listen",
        description="Pull one utterance from the STT provider and run the voice pipeline",
        category="voice",
    ),
    CommandInfo(
        name="voice.text",
        description="Inject raw text as transcribed speech (deterministic demo/test path)",
        category="voice",
        params_help="<text>",
        examples=("voice.text เลือก component 2",),
    ),
    CommandInfo(
        name="voice.status",
        description="Show STT provider, enabled state, and last voice result",
        category="voice",
    ),
]

# Commands that may omit an explicit component id and fall back to the
# last user selection.
_ID_FALLBACK_COMMANDS = ("baseline.capture", "baseline.info")


class VoiceInputPlugin(PluginBase):
    """Owns the M2 voice pipeline: STT → text → rule intent → command."""

    name = "voice_input_plugin"

    def __init__(self) -> None:
        self._event_bus = None
        self._command_bus = None
        self._container: Optional[ServiceContainer] = None
        self._enabled = True
        self._provider: Any = None
        self._parser: Optional[VoiceIntentParser] = None
        self._selected_component: Optional[str] = None
        self._last: Optional[dict] = None

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="Voice Input",
            version="1.0",
            category="voice",
            commands=[c.name for c in _VOICE_COMMANDS],
            description="M2 voice pipeline: STT → text → rule intent → baseline commands",
        )

    def initialize(self, container: ServiceContainer) -> None:
        self._container = container
        self._event_bus = container.resolve("event_bus")
        self._command_bus = container.resolve("command_bus")

        config = container.resolve("config") if container.has("config") else None
        self._enabled = bool(config.get("voice.enabled", True)) if config else True

        provider_name = config.get("voice.provider", "deterministic") if config else "deterministic"
        self._provider = self._build_provider(provider_name, config)

        self._parser = VoiceIntentParser()
        container.register_instance("voice_intent_parser", self._parser)
        container.register_instance("voice_stt_provider", self._provider)

        self._register_commands()
        self._event_bus.subscribe(EventType.BASELINE_SELECTED, self._on_baseline_selected)
        logger.info(
            "VoiceInputPlugin initialized (enabled=%s, provider=%s)",
            self._enabled,
            provider_name,
        )

    def start(self) -> None:
        logger.info(
            "VoiceInputPlugin started (provider=%s available=%s)",
            getattr(self._provider, "name", "?"),
            bool(getattr(self._provider, "available", False)),
        )

    def stop(self) -> None:
        logger.info("VoiceInputPlugin stopped")

    # ── Provider builder ─────────────────────────────────────────────

    def _build_provider(self, provider_name: str, config: Any) -> Any:
        if not self._enabled:
            return None
        if provider_name == "mic":
            model_path = (
                config.get("voice.model_path", "models/vosk-model-small-th")
                if config
                else "models/vosk-model-small-th"
            )
            duration_sec = float(config.get("voice.duration_sec", 3.0)) if config else 3.0
            return MicSTTProvider(
                capturer=SoundDeviceCapturer(),
                recognizer=VoskRecognizer(model_path),
                duration_sec=duration_sec,
            )
        scripts = list(config.get("voice.scripts", [])) if config else []
        return DeterministicSTTProvider(scripts=scripts, loop=True)

    # ── Command registration ─────────────────────────────────────────

    def _register_commands(self) -> None:
        if not self._container:
            return
        registry = (
            self._container.resolve("command_registry")
            if self._container.has("command_registry")
            else None
        )
        if registry is None:
            registry = CommandRegistry()
            registry.initialize(self._container)
        for cmd_info in _VOICE_COMMANDS:
            registry.register(cmd_info)
        if self._command_bus:
            self._command_bus.register_handler("voice.listen", self._handle_listen)
            self._command_bus.register_handler("voice.text", self._handle_text)
            self._command_bus.register_handler("voice.status", self._handle_status)

    # ── Command handlers ─────────────────────────────────────────────

    def _handle_listen(self, command: Command) -> dict:
        if not self._enabled or self._provider is None:
            return self._error_result("Voice input disabled (voice.enabled=false)", command)
        if not getattr(self._provider, "available", False):
            return self._error_result(
                "STT provider not available "
                "(install sounddevice+vosk for 'mic', or set voice.scripts for 'deterministic')",
                command,
            )
        stt = self._provider.transcribe()
        if stt is None or not stt.text:
            self._publish_error("No speech recognized (silence or unsupported audio)")
            return {"message": "Voice: no speech recognized"}
        return self.process_text(stt.text, source=stt.source, command=command)

    def _handle_text(self, command: Command) -> dict:
        text = str(command.params.get("text", "") or "")
        return self.process_text(text, source="inject", command=command)

    def _handle_status(self, command: Command) -> dict:
        provider_name = getattr(self._provider, "name", "none")
        return {
            "message": (
                f"Voice: enabled={self._enabled}, provider={provider_name}, "
                f"available={bool(getattr(self._provider, 'available', False))}"
            ),
            "enabled": self._enabled,
            "provider": provider_name,
            "available": bool(getattr(self._provider, "available", False)),
            "selected_component": self._selected_component,
            "last_result": self._last,
        }

    # ── Pipeline: text → intent → command ─────────────────────────────

    def process_text(self, text: str, source: str = "voice", command: Optional[Command] = None) -> dict:
        """Run the M2 chain for one text transcript. Returns a result dict."""
        text = (text or "").strip()
        if not text:
            self._publish_error("No speech text to parse")
            return {"message": "Voice: no text to parse"}

        self._publish(
            EventType.VOICE_TEXT_READY,
            {"text": text, "confidence": 1.0, "source": source},
        )

        assert self._parser is not None
        result = self._parser.resolve(text)
        if result is None:
            self._publish_error(
                f"ไม่เข้าใจคำสั่ง: '{text}'",
                hint="ลอง: เลือก component 1-5 | ถ่ายภาพ | แสดงข้อมูล | สถานะ | บันทึก",
            )
            return {"message": f"Voice: ไม่เข้าใจคำสั่ง '{text}'"}

        # Bare capture/info phrases fall back to the last selected component.
        if (
            "component_id" not in result.params
            and result.command_name in _ID_FALLBACK_COMMANDS
        ):
            result.params["component_id"] = self._selected_component or ""
        params = dict(result.params)

        self._publish(
            EventType.VOICE_INTENT_RESOLVED,
            {
                "intent": result.intent,
                "command": result.command_name,
                "params": params,
                "confidence": result.confidence,
                "raw_input": result.raw_input,
            },
        )

        cmd = Command(name=result.command_name, source="voice", params=params)
        if self._command_bus:
            self._command_bus.dispatch(cmd)

        self._last = {
            "intent": result.intent,
            "command": result.command_name,
            "params": params,
            "raw_input": result.raw_input,
        }
        logger.debug("Voice dispatched: %s %s", result.command_name, params)
        return {
            "message": f"Voice → {result.command_name} ({result.intent})",
            "command_name": result.command_name,
            "intent": result.intent,
            "params": params,
        }

    # ── Event helpers ────────────────────────────────────────────────

    def _publish(self, event_type: Any, payload: dict) -> None:
        if self._event_bus:
            self._event_bus.publish(Event(type=event_type, payload=payload, source=self.name))

    def _publish_error(self, message: str, hint: str = "") -> None:
        payload = {"message": message}
        if hint:
            payload["hint"] = hint
        self._publish(EventType.VOICE_ERROR, payload)
        logger.info("Voice error: %s", message)

    def _error_result(self, message: str, command: Command) -> dict:
        self._publish_error(message)
        return {"message": message}

    def _on_baseline_selected(self, event: Event) -> None:
        cid = event.payload.get("component_id")
        if cid:
            self._selected_component = str(cid)