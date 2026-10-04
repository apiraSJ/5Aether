"""STT recognizers — interface + optional vosk backend (lazy import).

The vosk backend is optional: it is never imported at module load. `available`
is only True when vosk is installed AND the model directory exists, so the
mic path stays opt-in and the test suite never depends on it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional, Protocol

from aether.voice.audio import audio_to_pcm16
from aether.voice.stt import STTResult

logger = logging.getLogger("Aether.Voice.Recognizer")


class STTRecognizer(Protocol):
    """Converts raw mono audio samples into an STTResult."""

    @property
    def name(self) -> str:
        ...

    @property
    def available(self) -> bool:
        ...

    def recognize(self, audio: Any) -> Optional[STTResult]:
        ...


class VoskRecognizer:
    """Offline vosk recognizer. Lazy — vosk is only imported when used.

    Expects 16 kHz mono audio (numpy float32 from the capturer). Confidence is
    reported as 1.0 because Kaldi results do not expose a single utterance-level
    score; text-vs-empty is the deterministic signal for M2.
    """

    name = "vosk"

    def __init__(self, model_path: str = "models/vosk-model-small-th") -> None:
        self._model_path = str(model_path)
        self._vosk: Optional[Any] = None
        self._model: Optional[Any] = None
        self._error: Optional[Exception] = None

    @property
    def model_path(self) -> str:
        return self._model_path

    def _ensure_loaded(self) -> bool:
        if self._model is not None:
            return True
        if self._error is not None:
            return False
        try:
            import vosk  # noqa: PLC0415  (optional, lazy)

            self._vosk = vosk
        except Exception as exc:
            self._error = exc
            logger.info("vosk not available: %s", exc)
            return False

        model_dir = Path(self._model_path)
        if not model_dir.exists():
            self._error = FileNotFoundError(f"vosk model not found: {self._model_path}")
            logger.info("vosk model not found: %s", self._model_path)
            return False

        try:
            self._model = self._vosk.Model(str(model_dir))
        except Exception as exc:
            self._error = exc
            logger.error("vosk model failed to load: %s", exc)
            return False
        return True

    @property
    def available(self) -> bool:
        return self._ensure_loaded()

    def recognize(self, audio: Any) -> Optional[STTResult]:
        if not self._ensure_loaded():
            return None
        try:
            frames = audio_to_pcm16(audio)
            if not frames:
                return None
            rec = self._vosk.KaldiRecognizer(self._model, 16000)
            rec.AcceptWaveform(frames)
            result = json.loads(rec.FinalResult())
            text = str(result.get("text", "")).strip()
            if not text:
                return None
            return STTResult(text=text, confidence=1.0, source=self.name)
        except Exception:
            logger.exception("vosk recognize failed")
            return None