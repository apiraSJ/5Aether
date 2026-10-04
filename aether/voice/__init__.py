"""M2 Voice/Input Pipeline — STT adapters + rule-based voice intent parser."""

from aether.voice.audio import SoundDeviceCapturer, audio_to_pcm16
from aether.voice.intent_parser import VoiceIntentParser
from aether.voice.recognizers import VoskRecognizer
from aether.voice.stt import (
    DeterministicSTTProvider,
    MicSTTProvider,
    STTResult,
)

__all__ = [
    "STTResult",
    "DeterministicSTTProvider",
    "MicSTTProvider",
    "SoundDeviceCapturer",
    "VoskRecognizer",
    "VoiceIntentParser",
    "audio_to_pcm16",
]