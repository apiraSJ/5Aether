import sys
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QFrame, QScrollArea, QSizePolicy, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QRect
from PySide6.QtGui import QFont, QColor, QPalette, QPainter, QBrush, QPen


@dataclass
class UIPanel:
    """Represents a UI panel."""
    name: str
    title: str
    content_widget: QWidget
    visible: bool = False


class AetherUI(QWidget):
    """Aether's Smart UI - floating, adaptive, always-on-top."""
    
    def __init__(self, context_manager=None, memory_storage=None):
        super().__init__()
        self.logger = logging.getLogger("Aether.UI")
        self.context_manager = context_manager
        self.memory_storage = memory_storage
        
        self._panels: Dict[str, UIPanel] = {}
        self._current_mode = "normal"
        self._animating = False
        
        self._setup_window()
        self._setup_ui()
        self._load_saved_state()
        
        # Update timer for live metrics
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._update_metrics)
        self._update_timer.start(2000)  # Update every 2 seconds
    
    def _setup_window(self):
        """Configure window properties for floating overlay."""
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint | 
            Qt.Tool |
            Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        
        # Load saved position or default
        pos = self.memory_storage.get("ui_position", {"x": 50, "y": 50}) if self.memory_storage else {"x": 50, "y": 50}
        self.move(pos["x"], pos["y"])
        
        self.resize(340, 480)
    
    def _setup_ui(self):
        """Build the UI layout."""
        # Main container with rounded corners and shadow
        self.container = QFrame()
        self.container.setObjectName("container")
        self.container.setStyleSheet("""
            QFrame#container {
                background: rgba(20, 22, 28, 0.95);
                border-radius: 16px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)
        
        # Add drop shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 4)
        self.container.setGraphicsEffect(shadow)
        
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        self.header = self._create_header()
        layout.addWidget(self.header)
        
        # Content area (scrollable)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: rgba(255,255,255,0.05);
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.2);
                border-radius: 3px;
                min-height: 30px;
            }
        """)
        
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(16, 8, 16, 16)
        self.content_layout.setSpacing(12)
        self.content_layout.addStretch()
        
        self.scroll.setWidget(self.content_widget)
        layout.addWidget(self.scroll)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.addWidget(self.container)
    
    def _create_header(self) -> QFrame:
        """Create the header with title, mode, and controls."""
        header = QFrame()
        header.setFixedHeight(60)
        header.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(30, 140, 255, 0.3), stop:1 rgba(100, 100, 255, 0.2));
                border-top-left-radius: 16px;
                border-top-right-radius: 16px;
                border-bottom: 1px solid rgba(255,255,255,0.08);
            }
        """)
        
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 0, 16, 0)
        
        # Logo/Title
        title = QLabel("AETHER")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setStyleSheet("color: #ffffff;")
        layout.addWidget(title)
        
        layout.addStretch()
        
        # Mode indicator
        self.mode_label = QLabel("NORMAL")
        self.mode_label.setFont(QFont("Segoe UI", 9, QFont.Medium))
        self.mode_label.setStyleSheet("""
            color: #4ade80;
            background: rgba(74, 222, 128, 0.15);
            padding: 4px 10px;
            border-radius: 12px;
        """)
        layout.addWidget(self.mode_label)
        
        # Minimize/Close buttons
        btn_minimize = self._create_icon_btn("—", self.showMinimized)
        btn_close = self._create_icon_btn("×", self.hide)
        
        layout.addWidget(btn_minimize)
        layout.addWidget(btn_close)
        
        return header
    
    def _create_icon_btn(self, text: str, callback) -> QPushButton:
        """Create a small icon button."""
        btn = QPushButton(text)
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(callback)
        btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(255,255,255,0.7);
                border: none;
                border-radius: 14px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.1);
                color: white;
            }
        """)
        return btn
    
    def _load_saved_state(self):
        """Load saved UI state from memory."""
        if not self.memory_storage:
            return
        
        mode = self.memory_storage.get("mode", "normal")
        self.set_mode(mode)
        
        last_panel = self.memory_storage.get("last_panel", "system")
        if last_panel in self._panels:
            self._panels[last_panel].visible = True
    
    def _save_state(self):
        """Save UI state to memory."""
        if not self.memory_storage:
            return
        
        self.memory_storage.set("mode", self._current_mode)
        self.memory_storage.set("ui_position", {"x": self.x(), "y": self.y()})
        
        # Save last visible panel
        for name, panel in self._panels.items():
            if panel.visible:
                self.memory_storage.set("last_panel", name)
                break
    
    def register_panel(self, name: str, title: str, widget: QWidget):
        """Register a content panel."""
        panel = UIPanel(name=name, title=title, content_widget=widget)
        self._panels[name] = panel
        self.content_layout.insertWidget(self.content_layout.count() - 1, widget)
        widget.hide()
        self.logger.debug(f"Registered panel: {name}")
    
    def show_panel(self, name: str):
        """Show a specific panel."""
        if name in self._panels:
            self._panels[name].content_widget.show()
            self._panels[name].visible = True
            self._save_state()
    
    def hide_panel(self, name: str):
        """Hide a specific panel."""
        if name in self._panels:
            self._panels[name].content_widget.hide()
            self._panels[name].visible = False
            self._save_state()
    
    def set_mode(self, mode: str):
        """Set the UI mode."""
        self._current_mode = mode
        self.mode_label.setText(mode.upper())
        
        # Color coding for modes
        mode_colors = {
            "normal": "#4ade80",       # green
            "developer": "#fbbf24",    # amber
            "presentation": "#f87171", # red
            "ai": "#a78bfa"            # purple
        }
        color = mode_colors.get(mode, "#4ade80")
        self.mode_label.setStyleSheet(f"""
            color: {color};
            background: {color}20;
            padding: 4px 10px;
            border-radius: 12px;
        """)
        
        self._save_state()
        
        # Emit mode change for panels to react
        if hasattr(self, 'mode_changed'):
            self.mode_changed.emit(mode)
    
    def _update_metrics(self):
        """Update live metrics display."""
        if self.context_manager:
            ctx = self.context_manager.get_context()
            self._update_system_metrics(ctx.cpu_percent, ctx.memory_percent)
    
    def _update_system_metrics(self, cpu: float, memory: float):
        """Update system metrics in the UI."""
        # Find and update metrics labels if they exist
        for name, panel in self._panels.items():
            if hasattr(panel.content_widget, 'update_metrics'):
                panel.content_widget.update_metrics(cpu, memory)
    
    def mousePressEvent(self, event):
        """Enable dragging the window."""
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """Handle window dragging."""
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag_pos'):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
    
    def closeEvent(self, event):
        """Save state on close."""
        self._save_state()
        event.accept()


def create_system_panel(context_manager=None) -> QWidget:
    """Create the System panel widget."""
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    
    # Title
    title = QLabel("SYSTEM STATUS")
    title.setFont(QFont("Segoe UI", 11, QFont.Bold))
    title.setStyleSheet("color: #888888;")
    layout.addWidget(title)
    
    # Metrics cards
    metrics_frame = QFrame()
    metrics_frame.setStyleSheet("""
        QFrame {
            background: rgba(255,255,255,0.03);
            border-radius: 10px;
            border: 1px solid rgba(255,255,255,0.05);
        }
    """)
    metrics_layout = QVBoxLayout(metrics_frame)
    metrics_layout.setContentsMargins(16, 16, 16, 16)
    metrics_layout.setSpacing(12)
    
    # CPU
    cpu_row = QHBoxLayout()
    cpu_label = QLabel("CPU")
    cpu_label.setStyleSheet("color: #aaa; font-size: 12px;")
    cpu_value = QLabel("0%")
    cpu_value.setFont(QFont("Segoe UI", 14, QFont.Bold))
    cpu_value.setStyleSheet("color: #4ade80;")
    cpu_value.setObjectName("cpu_value")
    cpu_row.addWidget(cpu_label)
    cpu_row.addStretch()
    cpu_row.addWidget(cpu_value)
    metrics_layout.addLayout(cpu_row)
    
    # RAM
    ram_row = QHBoxLayout()
    ram_label = QLabel("MEMORY")
    ram_label.setStyleSheet("color: #aaa; font-size: 12px;")
    ram_value = QLabel("0%")
    ram_value.setFont(QFont("Segoe UI", 14, QFont.Bold))
    ram_value.setStyleSheet("color: #60a5fa;")
    ram_value.setObjectName("ram_value")
    ram_row.addWidget(ram_label)
    ram_row.addStretch()
    ram_row.addWidget(ram_value)
    metrics_layout.addLayout(ram_row)
    
    layout.addWidget(metrics_frame)
    layout.addStretch()
    
    # Add update method
    def update_metrics(cpu: float, mem: float):
        cpu_value.setText(f"{cpu:.0f}%")
        ram_value.setText(f"{mem:.0f}%")
        # Color based on usage
        cpu_value.setStyleSheet(f"color: {'#f87171' if cpu > 80 else '#4ade80'};")
        ram_value.setStyleSheet(f"color: {'#f87171' if mem > 80 else '#60a5fa'};")
    
    panel.update_metrics = update_metrics
    return panel


def create_developer_panel() -> QWidget:
    """Create the Developer panel widget."""
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    
    title = QLabel("DEVELOPER TOOLS")
    title.setFont(QFont("Segoe UI", 11, QFont.Bold))
    title.setStyleSheet("color: #888888;")
    layout.addWidget(title)
    
    # Tool buttons
    tools = [
        ("Terminal", "Open terminal"),
        ("Git Status", "Check repository status"),
        ("Debug", "Attach debugger"),
        ("Logs", "View application logs"),
        ("Build", "Run build"),
        ("Test", "Run tests"),
    ]
    
    for tool_name, tooltip in tools:
        btn = QPushButton(tool_name)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 8px;
                padding: 12px 16px;
                text-align: left;
                color: #e0e0e0;
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(251, 191, 36, 0.15);
                border-color: #fbbf24;
                color: #fbbf24;
            }
        """)
        layout.addWidget(btn)
    
    layout.addStretch()
    return panel


def create_settings_panel(memory_storage=None) -> QWidget:
    """Create the Settings panel widget."""
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    
    title = QLabel("SETTINGS")
    title.setFont(QFont("Segoe UI", 11, QFont.Bold))
    title.setStyleSheet("color: #888888;")
    layout.addWidget(title)
    
    # Theme toggle
    theme_frame = QFrame()
    theme_frame.setStyleSheet("""
        QFrame {
            background: rgba(255,255,255,0.03);
            border-radius: 10px;
            border: 1px solid rgba(255,255,255,0.05);
        }
    """)
    theme_layout = QHBoxLayout(theme_frame)
    theme_layout.setContentsMargins(16, 12, 16, 12)
    
    theme_label = QLabel("Dark Theme")
    theme_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
    
    from PySide6.QtWidgets import QCheckBox
    theme_check = QCheckBox()
    theme_check.setChecked(True)
    theme_check.setStyleSheet("""
        QCheckBox::indicator {
            width: 20px;
            height: 20px;
            border-radius: 10px;
            border: 2px solid rgba(255,255,255,0.2);
        }
        QCheckBox::indicator:checked {
            background: #4ade80;
            border-color: #4ade80;
        }
    """)
    
    theme_layout.addWidget(theme_label)
    theme_layout.addStretch()
    theme_layout.addWidget(theme_check)
    layout.addWidget(theme_frame)
    
    # Auto-start
    autostart_frame = QFrame()
    autostart_frame.setStyleSheet("""
        QFrame {
            background: rgba(255,255,255,0.03);
            border-radius: 10px;
            border: 1px solid rgba(255,255,255,0.05);
        }
    """)
    autostart_layout = QHBoxLayout(autostart_frame)
    autostart_layout.setContentsMargins(16, 12, 16, 12)
    
    autostart_label = QLabel("Auto-start with system")
    autostart_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
    
    autostart_check = QCheckBox()
    autostart_check.setStyleSheet("""
        QCheckBox::indicator {
            width: 20px;
            height: 20px;
            border-radius: 10px;
            border: 2px solid rgba(255,255,255,0.2);
        }
        QCheckBox::indicator:checked {
            background: #4ade80;
            border-color: #4ade80;
        }
    """)
    
    autostart_layout.addWidget(autostart_label)
    autostart_layout.addStretch()
    autostart_layout.addWidget(autostart_check)
    layout.addWidget(autostart_frame)
    
    layout.addStretch()
    return panel


def run_aether_ui(context_manager=None, memory_storage=None):
    """Run the Aether UI application."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Dark palette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(20, 22, 28))
    palette.setColor(QPalette.WindowText, QColor(224, 224, 224))
    palette.setColor(QPalette.Base, QColor(25, 28, 35))
    palette.setColor(QPalette.AlternateBase, QColor(30, 33, 40))
    palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
    palette.setColor(QPalette.Text, QColor(224, 224, 224))
    palette.setColor(QPalette.Button, QColor(30, 33, 40))
    palette.setColor(QPalette.ButtonText, QColor(224, 224, 224))
    palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.Highlight, QColor(30, 140, 255))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)
    
    # Font
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    window = AetherUI(context_manager, memory_storage)
    
    # Register panels
    window.register_panel("system", "System", create_system_panel(context_manager))
    window.register_panel("developer", "Developer", create_developer_panel())
    window.register_panel("settings", "Settings", create_settings_panel(memory_storage))
    
    # Show default panel
    window.show_panel("system")
    
    window.show()
    
    return app.exec()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_aether_ui()