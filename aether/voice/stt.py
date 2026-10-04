"""STT abstraction — M2 deterministic-by-default voice-to-text.

Design:
    STTProvider         : protocol — pull one transcript per transcribe() call
    DeterministicSTTProv: default provider; yields canned scripts (tests, demo)
    MicSTTProvider      : optional real-mic path = capturer + recognizer

The deterministic provider is the default so the whole pipeline runs and is
testable without a microphone, audio drivers, or external services. The mic
path is opt-in via config (``voice.provider: mic``) and degrades to None
(→ ``voice.error``) when its optional deps (sounddevice / vosk) are missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol


@dataclass(frozen=True)
class STTResult:
    """A single transcribed utterance."""

    text: str
    confidence: float = 1.0
    source: str = "deterministic"


class STTProvider(Protocol):
    """Pull-based speech-to-text provider."""

    @property
    def name(self) -> str:
        ...

    @property
    def available(self) -> bool:
        ...

    def transcribe(self) -> Optional["STTResult"]:
        """Return the next transcript, or None (silence / unavailable)."""
        ...


class DeterministicSTTProvider:
    """Returns canned transcripts in order (deterministic, no hardware).

    The default M2 provider: config `voice.scripts` drives the demo/tests so
    the full Text → Intent → Command chain is exercised without a mic.
    """

    name = "deterministic"

    def __init__(self, scripts: Optional[list[str]] = None, loop: bool = True) -> None:
        self._scripts = list(scripts or [])
        self._loop = loop
        self._index = 0

    @property
    def available(self) -> bool:
        return bool(self._scripts)

    def transcribe(self) -> Optional[STTResult]:
        if not self._scripts:
            return None
        if self._index >= len(self._scripts):
            if not self._loop:
                return None
            self._index = 0
        text = self._scripts[self._index]
        self._index += 1
        return STTResult(text=text, confidence=1.0, source=self.name)

    def reset(self) -> None:
        self._index = 0

    def remaining(self) -> int:
        return max(0, len(self._scripts) - self._index)


class MicSTTProvider:
    """Real-microphone path: AudioCapturer → STTRecognizer (both injected).

    `available` is False when the capturer or recognizer is unavailable, so
    `voice.listen` degrades to a `voice.error` event instead of raising.
    """

    name = "mic"

    def __init__(
        self,
        capturer: Any,
        recognizer: Any,
        sample_rate: int = 16000,
        duration_sec: float = 3.0,
    ) -> None:
        self._capturer = capturer
        self._recognizer = recognizer
        self._sample_rate = sample_rate
        self._duration_sec = duration_sec

    @property
    def capturer(self) -> Any:
        return self._capturer

    @property
    def recognizer(self) -> Any:
        return self._recognizer

    @property
    def available(self) -> bool:
        return bool(
            getattr(self._capturer, "available", False)
            and getattr(self._recognizer, "available", False)
        )

    def transcribe(self) -> Optional[STTResult]:
        if not self.available:
            return None
        try:
            audio = self._capturer.capture(self._duration_sec, self._sample_rate)
        except Exception:
            return None
        if audio is None:
            return None
        try:
            result = self._recognizer.recognize(audio)
        except Exception:
            return None
        if result is None:
            return None
        return STTResult(text=result.text, confidence=result.confidence, source=self.name)