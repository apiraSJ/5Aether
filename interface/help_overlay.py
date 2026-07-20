import sys
import logging
from typing import Dict, Any, List
from dataclasses import dataclass
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QScrollArea, QTableWidget, QTableWidgetItem
)
from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import QFont, QColor, QPainter, QBrush, QPen


@dataclass
class CommandInfo:
    """Represents a command with metadata for display."""
    name: str
    description: str
    hotkey: str = ""
    gesture: str = ""


@dataclass
class GestureInfo:
    """Represents a gesture with action info."""
    gesture_name: str
    action_name: str
    description: str
    position: tuple = (0, 0)


class HelpOverlay(QWidget):
    """Floating help overlay widget showing keyboard shortcuts and gesture controls."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("Aether.HelpOverlay")
        
        # Configuration
        self.width = 600
        self.height = 500
        self.fade_timer = None
        self.auto_hide_after = 10000  # 10 seconds
        
        self._setup_ui()
        self._setup_timer()
    
    def _setup_ui(self):
        """Setup the help overlay UI."""
        # Main container
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint | 
            Qt.Tool |
            Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        
        self.resize(self.width, self.height)
        
        # Create main container with rounded corners
        self.container = QFrame()
        self.container.setObjectName("help_container")
        self.container.setFrameStyle(QFrame.Plain)
        
        container_style = """
            QFrame#help_container {
                background: rgba(20, 22, 28, 0.97);
                border-radius: 20px;
                border: 2px solid rgba(30, 140, 255, 0.5);
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
            }
        """
        self.container.setStyleSheet(container_style)
        
        main_layout = QVBoxLayout(self.container)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # Title bar
        title_bar = self._create_title_bar()
        main_layout.addWidget(title_bar)
        
        # Content - two column layout
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)
        
        # Keyboard shortcuts column
        keyboard_section = self._create_keyboard_section()
        content_layout.addWidget(keyboard_section)
        
        # Gesture controls column  
        gesture_section = self._create_gesture_section()
        content_layout.addWidget(gesture_section)
        
        main_layout.addLayout(content_layout)
        
        # Footer with mode and system info
        footer = self._create_footer()
        main_layout.addWidget(footer)
        
        # Set the container as the main widget layout
        final_layout = QVBoxLayout(self)
        final_layout.setContentsMargins(15, 15, 15, 15)
        final_layout.addWidget(self.container)
    
    def _create_title_bar(self) -> QFrame:
        """Create the title bar with close button."""
        title_bar = QFrame()
        title_bar.setFixedHeight(50)
        title_bar.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(30, 140, 255, 0.4), stop:1 rgba(100, 100, 255, 0.3));
                border-radius: 15px;
                border-bottom-left-radius: 0;
                border-bottom-right-radius: 0;
            }
        """)
        
        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(20, 0, 20, 0)
        
        # Title
        title = QLabel("AETHER HELP")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setStyleSheet("color: white; letter-spacing: 2px;")
        layout.addWidget(title)
        
        layout.addStretch()
        
        # Close button
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border-radius: 15px;
                font-size: 16px;
                font-weight: bold;
                border: 1px solid rgba(255, 255, 255, 0.3);
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
                border-color: rgba(255, 255, 255, 0.5);
            }
        """)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        return title_bar
    
    def _create_keyboard_section(self) -> QFrame:
        """Create the keyboard shortcuts section."""
        section = QFrame()
        section.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(15)
        
        # Section title
        title = QLabel("⌨️ KEYBOARD SHORTCUTS")
        title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        title.setStyleSheet("color: #4ade80; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # Keyboard shortcuts table
        self.keyboard_table = QTableWidget()
        self.keyboard_table.setColumnCount(2)
        self.keyboard_table.setHorizontalHeaderLabels(["Hotkey", "Action"])
        self.keyboard_table.setRowCount(0)
        self.keyboard_table.setFixedHeight(320)
        self.keyboard_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.keyboard_table.setSelectionMode(QTableWidget.NoSelection)
        self.keyboard_table.setStyleSheet("""
            QTableWidget {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                color: white;
                font-size: 12px;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            QTableWidget::horizontalHeader {
                background: rgba(30, 140, 255, 0.2);
                border-bottom: 1px solid rgba(30, 140, 255, 0.5);
                color: white;
                font-weight: bold;
            }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.05);
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(30, 140, 255, 0.5);
                border-radius: 4px;
            }
        """)
        
        layout.addWidget(self.keyboard_table)
        
        # Help text
        help_text = QLabel("\n💡 Use gestures or hotkeys to control Aether without keyboard.\n")
        help_text.setFont(QFont("Segoe UI", 9))
        help_text.setStyleSheet("color: #aaa; font-style: italic;")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        
        return section
    
    def _create_gesture_section(self) -> QFrame:
        """Create the gesture controls section."""
        section = QFrame()
        section.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setSpacing(15)
        
        # Section title
        title = QLabel("🤚 GESTURE CONTROL")
        title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        title.setStyleSheet("color: #60a5fa; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # Gesture table
        self.gesture_table = QTableWidget()
        self.gesture_table.setColumnCount(2)
        self.gesture_table.setHorizontalHeaderLabels(["Gesture", "Action"])
        self.gesture_table.setRowCount(0)
        self.gesture_table.setFixedHeight(320)
        self.gesture_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.gesture_table.setSelectionMode(QTableWidget.NoSelection)
        self.gesture_table.setStyleSheet("""
            QTableWidget {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                color: white;
                font-size: 12px;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            QTableWidget::horizontalHeader {
                background: rgba(96, 165, 250, 0.2);
                border-bottom: 1px solid rgba(96, 165, 250, 0.5);
                color: white;
                font-weight: bold;
            }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.05);
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(96, 165, 250, 0.5);
                border-radius: 4px;
            }
        """)
        
        layout.addWidget(self.gesture_table)
        
        # Tip
        tip = QLabel("\n🤖	Hold press to activate modes\n📍 Point and click\n")
        tip.setFont(QFont("Segoe UI", 10))
        tip.setStyleSheet("color: #fbbf24;")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        
        return section
    
    def _create_footer(self) -> QFrame:
        """Create the footer with mode and system info."""
        footer = QFrame()
        footer.setFixedHeight(60)
        footer.setStyleSheet("""
            QFrame {
                background: rgba(0, 0, 0, 0.3);
                border-radius: 10px;
                border-top: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)
        
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(20, 10, 20, 10)
        
        # Mode indicator
        self.mode_label = QLabel("MODE: NORMAL")
        self.mode_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.mode_label.setStyleSheet("color: #4ade80;")
        layout.addWidget(self.mode_label)
        
        layout.addStretch()
        
        # System info
        self.system_label = QLabel("CPU: --%  MEM: --%")
        self.system_label.setFont(QFont("Segoe UI", 9))
        self.system_label.setStyleSheet("color: #aaa;")
        layout.addWidget(self.system_label)
        
        # Auto-hide indicator
        self.auto_hide_label = QLabel("Auto-hide: 10s")
        self.auto_hide_label.setFont(QFont("Segoe UI", 8))
        self.auto_hide_label.setStyleSheet("color: #666;")
        layout.addWidget(self.auto_hide_label)
        
        # Toggle auto-hide button
        self.auto_hide_btn = QPushButton("🔄")
        self.auto_hide_btn.setFixedSize(24, 24)
        self.auto_hide_btn.setCursor(Qt.PointingHandCursor)
        self.auto_hide_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #666;
                border: none;
                font-size: 14px;
            }
            QPushButton:hover {
                color: #aaa;
            }
        """)
        self.auto_hide_btn.clicked.connect(self._toggle_auto_hide)
        layout.addWidget(self.auto_hide_btn)
        
        return footer
    
    def _setup_timer(self):
        """Setup auto-hide timer."""
        self.fade_timer = QTimer()
        self.fade_timer.timeout.connect(self.close)
        self.fade_timer.start(self.auto_hide_after)
    
    def set_commands(self, commands: List[CommandInfo]):
        """Set keyboard command list for display."""
        self.keyboard_table.setRowCount(len(commands))
        for row, cmd in enumerate(commands):
            hotkey_item = QTableWidgetItem(cmd.hotkey)
            action_item = QTableWidgetItem(cmd.description)
            
            hotkey_item.setTextAlignment(Qt.AlignCenter)
            action_item.setTextAlignment(Qt.AlignLeft)
            
            # Style based on hotkey pattern
            if "+" in cmd.hotkey:
                hotkey_item.setBackground(QColor(30, 140, 255, 50))
            
            self.keyboard_table.setItem(row, 0, hotkey_item)
            self.keyboard_table.setItem(row, 1, action_item)
    
    def set_gestures(self, gestures: List[GestureInfo]):
        """Set gesture list for display."""
        self.gesture_table.setRowCount(len(gestures))
        for row, gest in enumerate(gestures):
            gesture_item = QTableWidgetItem(gest.gesture_name.replace('_', ' ').title())
            action_item = QTableWidgetItem(gest.action_name.replace('_', ' ').title())
            
            gesture_item.setTextAlignment(Qt.AlignCenter)
            action_item.setTextAlignment(Qt.AlignLeft)
            
            # Highlight CALL gesture (helps users find it)
            if gest.gesture_name == "call":
                gesture_item.setBackground(QColor(251, 191, 36, 50))
                gesture_item.setForeground(QColor(251, 191, 36))
            
            self.gesture_table.setItem(row, 0, gesture_item)
            self.gesture_table.setItem(row, 1, action_item)
    
    def set_mode(self, mode: str):
        """Update the mode indicator."""
        mode_styles = {
            "normal": "#4ade80",
            "developer": "#fbbf24", 
            "presentation": "#f87171",
            "ai": "#a78bfa"
        }
        color = mode_styles.get(mode, "#4ade80")
        self.mode_label.setText(f"MODE: {mode.upper()}")
        self.mode_label.setStyleSheet(f"color: {color};")
    
    def set_system_info(self, cpu: float, memory: float):
        """Update CPU and memory usage display."""
        self.system_label.setText(f"CPU: {cpu:.0f}%  MEM: {memory:.0f}%")
    
    def _toggle_auto_hide(self):
        """Toggle auto-hide on/off."""
        if self.fade_timer.isActive():
            self.fade_timer.stop()
            self.auto_hide_label.setText("Auto-hide: OFF")
        else:
            self.fade_timer.start(self.auto_hide_after)
            self.auto_hide_label.setText("Auto-hide: 10s")
    
    def mousePressEvent(self, event):
        """Enable window dragging."""
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """Handle window dragging."""
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag_pos'):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
    
    def closeEvent(self, event):
        """Clean up on close."""
        if self.fade_timer:
            self.fade_timer.stop()
        super().closeEvent(event)
