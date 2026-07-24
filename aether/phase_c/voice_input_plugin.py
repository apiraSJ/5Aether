"""
Voice input plugin for Phase C - converts speech recognition to Commands.
Placeholder implementation - requires speech recognition library.
"""

from aether.core.plugin import PluginBase
from aether.core.command import Command


class VoiceInputPlugin(PluginBase):
    """Converts speech recognition results to Commands.
    
    Requires: pip install speechrecognition pyaudio
    """
    
    name = "voice_input"
    
    def __init__(self):
        self.event_bus = None
        self.command_bus = None
        self._running = False
        self._recognizer = None
        self._microphone = None
        self._listen_thread = None
        
        # Voice command mappings (keyword -> command)
        self.COMMAND_MAP = {
            "open": "ui_toggle",
            "close": "ui_close",
            "show": "panel_system",
            "hide": "ui_close",
            "system": "panel_system",
            "developer": "panel_developer",
            "settings": "panel_settings",
            "normal": "mode_normal",
            "develop": "mode_developer",
            "presentation": "mode_presentation",
            "click": "cursor_click",
            "stop": "ui_close",
        }
    
    def initialize(self, container):
        self.event_bus = container.resolve("event_bus")
        self.command_bus = container.resolve("command_bus")
        
        # Try to import speech_recognition
        try:
            import speech_recognition as sr
            self._sr = sr
            self._recognizer = sr.Recognizer()
            self._microphone = sr.Microphone()
            
            # Adjust for ambient noise
            with self._microphone as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=1)
            
            self._running = True
            self._start_listening()
            
        except ImportError:
            # speech_recognition not available - plugin loads but does nothing
            pass
    
    def shutdown(self):
        self._running = False
        if self._listen_thread:
            self._listen_thread.join(timeout=2.0)
    
    def _start_listening(self):
        """Start background listening thread."""
        import threading
        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listen_thread.start()
    
    def _listen_loop(self):
        """Continuous speech recognition loop."""
        while self._running:
            try:
                with self._microphone as source:
                    audio = self._recognizer.listen(source, timeout=1, phrase_time_limit=3)
                
                # Recognize speech
                text = self._recognizer.recognize_google(audio).lower()
                self._process_speech(text)
                
            except Exception:
                # Timeout or recognition error - continue loop
                pass
    
    def _process_speech(self, text):
        """Process recognized speech text and dispatch commands."""
        words = text.split()
        
        for word in words:
            if word in self.COMMAND_MAP:
                cmd_name = self.COMMAND_MAP[word]
                self._dispatch(cmd_name, {"voice_text": text})
                break  # Only first matching command
    
    def _dispatch(self, cmd_name, params):
        if self.command_bus:
            cmd = Command(name=cmd_name, source="voice", params=params)
            self.command_bus.dispatch(cmd)


class VoiceCommandPlugin(PluginBase):
    """Simple voice command plugin using event bus for external ASR integration."""
    
    name = "voice_command"
    
    def __init__(self):
        self.event_bus = None
        self.command_bus = None
        self._running = False
        
        # Voice command -> Command mapping
        self.VOICE_COMMANDS = {
            "aether": "ui_toggle",
            "system": "panel_system",
            "dev": "panel_developer",
            "settings": "panel_settings",
            "normal": "mode_normal",
            "developer": "mode_developer",
            "present": "mode_presentation",
        }
    
    def initialize(self, container):
        self.event_bus = container.resolve("event_bus")
        self.command_bus = container.resolve("command_bus")
        
        # Subscribe to voice recognition events from external ASR
        self.event_bus.subscribe("voice_recognized", self._on_voice_recognized)
        self._running = True
    
    def shutdown(self):
        self._running = False
        if self.event_bus:
            self.event_bus.unsubscribe("voice_recognized", self._on_voice_recognized)
    
    def _on_voice_recognized(self, event):
        """Handle voice recognition event from external ASR service."""
        if not self._running:
            return
        
        text = event.data.get("text", "").lower()
        confidence = event.data.get("confidence", 1.0)
        
        # Minimum confidence threshold
        if confidence < 0.7:
            return
        
        words = text.split()
        for word in words:
            if word in self.VOICE_COMMANDS:
                cmd_name = self.VOICE_COMMANDS[word]
                self._dispatch(cmd_name, {
                    "voice_text": text,
                    "confidence": confidence
                })
                break
    
    def _dispatch(self, cmd_name, params):
        if self.command_bus:
            cmd = Command(name=cmd_name, source="voice", params=params)
            self.command_bus.dispatch(cmd)