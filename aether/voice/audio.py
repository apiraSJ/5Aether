"""Audio capture helpers for the M2 mic STT path.

The real-microphone path is optional: `SoundDeviceCapturer` imports
`sounddevice` lazily inside its constructor/methods, so importing this module
never touches optional dependencies and the test suite / deterministic
fallback stay hardware-free.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

__all__ = ["SoundDeviceCapturer", "audio_to_pcm16"]


class SoundDeviceCapturer:
    """Records a short mono audio window via sounddevice (lazy import).

    Only used when ``voice.provider: mic``. If `sounddevice` is not installed
    or no input device is available, `available` is False and capture returns
    None — the pipeline degrades gracefully without raising.
    """

    name = "sounddevice"

    def __init__(self) -> None:
        self._sd: Optional[Any] = None
        self._error: Optional[Exception] = None
        try:
            import sounddevice  # noqa: PLC0415  (optional, lazy)

            self._sd = sounddevice
        except Exception as exc:  # ImportError or device issues
            self._error = exc
            self._sd = None

    @property
    def available(self) -> bool:
        return self._sd is not None

    def capture(self, duration_sec: float, sample_rate: int = 16000) -> Optional[np.ndarray]:
        """Record `duration_sec` seconds of mono float32 audio (None when unavailable)."""
        if self._sd is None:
            return None
        try:
            frames = int(duration_sec * sample_rate)
            audio = self._sd.rec(frames, samplerate=sample_rate, channels=1, dtype="float32")
            self._sd.wait()
            if audio is None:
                return None
            data = np.asarray(audio, dtype=np.float32).reshape(-1)
            if data.size == 0:
                return None
            return data
        except Exception:
            return None


def audio_to_pcm16(audio: Any) -> Optional[bytes]:
    """Convert float32 mono samples in [-1, 1] to 16-bit PCM bytes for vosk.

    Returns None when `audio` is missing or cannot be converted.
    """
    if audio is None:
        return None
    try:
        data = np.asarray(audio, dtype=np.float32).reshape(-1)
        pcm = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)
        return pcm.tobytes()
    except Exception:
        return None