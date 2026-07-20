import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import psutil
import platform
from datetime import datetime


@dataclass
class ContextSnapshot:
    """A snapshot of the current context."""
    active_app: str = "unknown"
    active_window: str = "unknown"
    mode: str = "normal"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    project_context: Dict[str, Any] = field(default_factory=dict)


class ContextManager:
    """Understands the current situation - what's happening right now."""
    
    def __init__(self):
        self.logger = logging.getLogger("Aether.Context")
        self._current_context = ContextSnapshot()
        self._context_history = []
        self._max_history = 20
    
    def update(self, **kwargs) -> ContextSnapshot:
        """Update context with new information."""
        for key, value in kwargs.items():
            if hasattr(self._current_context, key):
                setattr(self._current_context, key, value)
        
        # Update system metrics
        self._current_context.cpu_percent = psutil.cpu_percent(interval=0.1)
        self._current_context.memory_percent = psutil.virtual_memory().percent
        self._current_context.timestamp = datetime.now().isoformat()
        
        # Add to history
        self._context_history.append(self._current_context)
        if len(self._context_history) > self._max_history:
            self._context_history.pop(0)
        
        return self._current_context
    
    def get_context(self) -> ContextSnapshot:
        """Get current context snapshot."""
        return self._current_context
    
    def get_mode(self) -> str:
        """Get current mode - can be overridden by activity detection."""
        return self._current_context.mode
    
    def set_mode(self, mode: str):
        """Set the current mode."""
        self._current_context.mode = mode
        self.logger.info(f"Mode changed to: {mode}")
    
    def detect_context(self) -> str:
        """Auto-detect context from system state."""
        try:
            # Get active window info (Windows-specific)
            import win32gui
            import win32process
            
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                try:
                    proc = psutil.Process(pid)
                    app_name = proc.name()
                    window_title = win32gui.GetWindowText(hwnd)
                    
                    self.update(active_app=app_name, active_window=window_title)
                    
                    # Detect developer mode
                    if self._is_developer_context(app_name, window_title):
                        return "developer"
                    
                    # Detect presentation mode
                    if self._is_presentation_context(app_name, window_title):
                        return "presentation"
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except ImportError:
            pass  # win32gui not available
        
        return self._current_context.mode
    
    def _is_developer_context(self, app: str, window: str) -> bool:
        """Detect if user is in developer context."""
        dev_apps = ["code", "vscode", "pycharm", "intellij", "vim", "emacs", 
                    "terminal", "cmd", "powershell", "git", "docker"]
        dev_keywords = ["git", "debug", "terminal", "console", "build", "compile"]
        
        app_lower = app.lower()
        window_lower = window.lower()
        
        if any(dev in app_lower for dev in dev_apps):
            return True
        if any(keyword in window_lower for keyword in dev_keywords):
            return True
        
        return False
    
    def _is_presentation_context(self, app: str, window: str) -> bool:
        """Detect if user is presenting."""
        present_apps = ["powerpoint", "ppt", "keynote", "slides"]
        app_lower = app.lower()
        return any(p in app_lower for p in present_apps)
    
    def get_history(self, limit: int = 10) -> list:
        return self._context_history[-limit:]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a human-readable context summary."""
        ctx = self._current_context
        return {
            "mode": ctx.mode,
            "active_app": ctx.active_app,
            "active_window": ctx.active_window[:50] if ctx.active_window else "none",
            "cpu": f"{ctx.cpu_percent:.1f}%",
            "memory": f"{ctx.memory_percent:.1f}%",
            "timestamp": ctx.timestamp
        }