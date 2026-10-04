"""Tests for M2 STT abstractions — deterministic default + mic composition.

These tests never touch a real microphone or any optional ASR dependency
(sounddevice / vosk are lazy-imported inside the classes, never here).
"""

from __future__ import annotations

import numpy as np
import pytest

from aether.voice.audio import audio_to_pcm16
from aether.voice.recognizers import VoskRecognizer
from aether.voice.stt import DeterministicSTTProvider, MicSTTProvider, STTResult


def test_optional_deps_are_not_imported_at_module_load():
    import sys

    assert "sounddevice" not in sys.modules
    assert "vosk" not in sys.modules


class TestDeterministicSTTProvider:
    def test_yields_scripts_in_order(self):
        provider = DeterministicSTTProvider(["a", "b"], loop=False)
        assert provider.transcribe().text == "a"
        assert provider.transcribe().text == "b"

    def test_exhausted_without_loop_returns_none(self):
        provider = DeterministicSTTProvider(["a"], loop=False)
        provider.transcribe()
        assert provider.transcribe() is None

    def test_loop_cycles_when_requested(self):
        provider = DeterministicSTTProvider(["a", "b"], loop=True)
        assert [provider.transcribe().text for _ in range(4)] == ["a", "b", "a", "b"]

    def test_reset_and_remaining(self):
        provider = DeterministicSTTProvider(["a", "b", "c"], loop=False)
        assert provider.remaining() == 3
        provider.transcribe()
        assert provider.remaining() == 2
        provider.reset()
        assert provider.remaining() == 3

    def test_available_is_false_with_empty_scripts(self):
        provider = DeterministicSTTProvider([])
        assert not provider.available
        assert provider.transcribe() is None


class TestMicSTTProvider:
    def test_transcribes_through_capturer_and_recognizer(self):
        capturer = _FakeCapturer(audio=np.zeros(1600, dtype=np.float32))
        recognizer = _FakeRecognizer(STTResult("สวัสดี", 0.8, "fake"))
        provider = MicSTTProvider(capturer=capturer, recognizer=recognizer)

        assert provider.available
        result = provider.transcribe()
        assert result is not None
        assert result.text == "สวัสดี"
        assert result.source == "mic"

    def test_unavailable_when_capturer_missing(self):
        provider = MicSTTProvider(capturer=_FakeCapturer(available=False), recognizer=_FakeRecognizer())
        assert not provider.available
        assert provider.transcribe() is None

    def test_unavailable_when_recognizer_missing(self):
        provider = MicSTTProvider(capturer=_FakeCapturer(), recognizer=_FakeRecognizer(available=False))
        assert not provider.available
        assert provider.transcribe() is None

    def test_capture_silence_returns_none(self):
        provider = MicSTTProvider(capturer=_FakeCapturer(audio=None), recognizer=_FakeRecognizer())
        assert provider.transcribe() is None

    def test_recognizer_empty_result_returns_none(self):
        capturer = _FakeCapturer(audio=np.zeros(1600, dtype=np.float32))
        provider = MicSTTProvider(capturer=capturer, recognizer=_FakeRecognizer())
        assert provider.transcribe() is None


class TestAudioConversion:
    def test_float32_to_pcm16(self):
        audio = np.array([0.0, 1.0, -1.0, 0.5], dtype=np.float32)
        pcm = audio_to_pcm16(audio)
        assert isinstance(pcm, bytes)
        import struct

        samples = struct.unpack("<4h", pcm)
        assert samples[0] == 0
        assert samples[1] == 32767
        assert samples[2] == -32767

    def test_none_input_returns_none(self):
        assert audio_to_pcm16(None) is None

    def test_empty_audio_returns_empty_bytes(self):
        assert audio_to_pcm16(np.zeros(0, dtype=np.float32)) == b""


class TestVoskRecognizer:
    def test_unavailable_when_model_missing(self):
        # Deliberately points at a model dir that does not exist.
        recognizer = VoskRecognizer("__definitely_missing_vosk_model__")
        assert not recognizer.available

    def test_recognize_returns_none_when_unavailable(self):
        recognizer = VoskRecognizer("__definitely_missing_vosk_model__")
        assert recognizer.recognize(np.zeros(1600, dtype=np.float32)) is None


class _FakeCapturer:
    name = "fake_capturer"

    def __init__(self, available=True, audio=None):
        self._available = available
        self._audio = audio

    @property
    def available(self):
        return self._available

    def capture(self, duration_sec, sample_rate=16000):
        return self._audio


class _FakeRecognizer:
    name = "fake_recognizer"

    def __init__(self, result=None, available=True):
        self._result = result
        self._available = available

    @property
    def available(self):
        return self._available

    def recognize(self, audio):
        return self._result