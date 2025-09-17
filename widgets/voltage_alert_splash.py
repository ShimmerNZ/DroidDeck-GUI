# widgets/voltage_alert_splash.py

import os
import pygame
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QColor
from core.theme_manager import theme_manager
from core.logger import get_logger

class VoltageAlertSplash(QWidget):
    """Clean, modern voltage alert splash screen"""
    
    # Signal to indicate the splash has closed
    splash_closed = pyqtSignal()
    
    def __init__(self, alert_type="LOW", voltage=0.0, parent=None):
        super().__init__(parent)
        print(f"🚨 VoltageAlertSplash.__init__ called: {alert_type}, {voltage}V")
 
        self.alert_type = alert_type  # "LOW" or "CRITICAL"
        self.voltage = voltage
        self.logger = get_logger("voltage_alert")
        
        # Initialize pygame mixer for audio playback
        self._init_audio()
        
        # Setup the splash screen
        self._setup_ui()
        self._setup_auto_close()
        
        # Play themed audio
        self._play_alert_audio()
    
    def _init_audio(self):
        """Initialize pygame mixer for audio playback"""
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
            self.audio_available = True
            self.logger.debug("Audio system initialized successfully")
        except Exception as e:
            self.logger.warning(f"Failed to initialize audio: {e}")
            self.audio_available = False
    
    def _setup_ui(self):
        """Setup the modern splash screen UI"""
        # Remove window decorations and make frameless
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        
        # Set window properties - wider aspect ratio for modern look
        self.setFixedSize(550, 140)
        
        # Center on screen
        self._center_on_screen()
        
        # Create layout with modern spacing
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(25, 20, 25, 20)
        main_layout.setSpacing(10)
        
        # Create horizontal content layout
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)
        
        # Modern icon
        self._create_icon(content_layout)
        
        # Text content with better typography
        self._create_text_content(content_layout)
        
        # Add close indicator
        self._create_close_indicator(main_layout)
        
        main_layout.addLayout(content_layout)
        self.setLayout(main_layout)
        
        # Don't apply main styling here since we're using custom painting
    
    def _create_icon(self, layout):
        """Create a clean, modern icon"""
        icon_label = QLabel()
        icon_label.setFixedSize(60, 60)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        if self.alert_type == "CRITICAL":
            icon_text = "⚠"
            icon_style = """
                QLabel {
                    font-size: 30px;
                    color: #ff4757;
                    background: rgba(255, 71, 87, 25);
                    border: 1px solid rgba(255, 71, 87, 60);
                    border-radius: 30px;
                    font-weight: bold;
                }
            """
        else:
            icon_text = "⚡"
            icon_style = """
                QLabel {
                    font-size: 30px;
                    color: #ffa502;
                    background: rgba(255, 165, 2, 25);
                    border: 1px solid rgba(255, 165, 2, 60);
                    border-radius: 30px;
                    font-weight: bold;
                }
            """
        
        icon_label.setText(icon_text)
        icon_label.setStyleSheet(icon_style)
        layout.addWidget(icon_label)
    
    def _create_text_content(self, layout):
        """Create modern text content"""
        text_layout = QVBoxLayout()
        text_layout.setSpacing(5)
        
        # Title
        title_label = QLabel()
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        
        if self.alert_type == "CRITICAL":
            title_text = "Critical Battery Alert"
            title_style = """
                QLabel {
                    color: #ff4757;
                    background: transparent;
                    border: none;
                }
            """
        else:
            title_text = "Low Battery Warning"
            title_style = """
                QLabel {
                    color: #ffa502;
                    background: transparent;
                    border: none;
                }
            """
        
        title_label.setText(title_text)
        title_label.setStyleSheet(title_style)
        
        # Voltage display
        voltage_label = QLabel(f"{self.voltage:.2f}V")
        voltage_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        voltage_label.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        voltage_label.setStyleSheet("""
            QLabel {
                color: white;
                background: transparent;
                border: none;
            }
        """)
        
        # Action message
        action_label = QLabel()
        action_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        action_label.setFont(QFont("Arial", 10))
        
        if self.alert_type == "CRITICAL":
            action_text = "Land immediately"
            action_style = """
                QLabel {
                    color: #ff6b6b;
                    background: transparent;
                    border: none;
                    font-style: italic;
                }
            """
        else:
            action_text = "Consider landing soon"
            action_style = """
                QLabel {
                    color: #ddd;
                    background: transparent;
                    border: none;
                    font-style: italic;
                }
            """
        
        action_label.setText(action_text)
        action_label.setStyleSheet(action_style)
        
        text_layout.addWidget(title_label)
        text_layout.addWidget(voltage_label)
        text_layout.addWidget(action_label)
        text_layout.addStretch()
        
        layout.addLayout(text_layout)
        layout.addStretch()
    
    def _create_close_indicator(self, layout):
        """Create a subtle close indicator"""
        self.countdown_label = QLabel("Click to dismiss • Auto-close in 5s")
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.setFont(QFont("Arial", 9))
        self.countdown_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 150);
                background: transparent;
                border: none;
            }
        """)
        layout.addWidget(self.countdown_label)
    
    def _get_main_style(self):
        """Get clean main window styling"""
        if self.alert_type == "CRITICAL":
            return """
                VoltageAlertSplash {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #2d1b1b, stop:1 #1a0f0f);
                    border: 2px solid #ff4757;
                    border-radius: 12px;
                }
            """
        else:
            return """
                VoltageAlertSplash {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #2d2d2d, stop:1 #1a1a1a);
                    border: 2px solid #ffa502;
                    border-radius: 12px;
                }
            """
    
    def _center_on_screen(self):
        """Center the splash screen on the display"""
        self.show()
        
        try:
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen().availableGeometry()
            
            x = (screen.width() - self.width()) // 2
            y = (screen.height() - self.height()) // 2
            
            self.move(x, y)
               
        except Exception as e:
            self.logger.warning(f"Could not center splash screen: {e}")
            self.move(400, 300)
        
        self.raise_()
        self.activateWindow()
    
    def _setup_auto_close(self):
        """Setup timer for auto-close functionality"""
        self.countdown = 5
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self._update_countdown)
        self.countdown_timer.start(1000)
        
        self.close_timer = QTimer()
        self.close_timer.setSingleShot(True)
        self.close_timer.timeout.connect(self.close_splash)
        self.close_timer.start(5000)
    
    def _update_countdown(self):
        """Update countdown display"""
        self.countdown -= 1
        if self.countdown > 0:
            self.countdown_label.setText(f"Click to dismiss • Auto-close in {self.countdown}s")
        else:
            self.countdown_timer.stop()
    
    def _play_alert_audio(self):
        """Play themed audio file for the alert"""
        if not self.audio_available:
            self.logger.debug("Audio not available, skipping sound playback")
            return
        
        try:
            # Get current theme name
            theme_name = theme_manager.get_theme_name()
            
            # Determine audio filename based on alert type
            if self.alert_type == "CRITICAL":
                audio_filename = "battery_critical.mp3"
            else:
                audio_filename = "battery_low.mp3"
            
            # Build path to themed audio file
            audio_path = os.path.join(
                "resources", "theme", theme_name, "audio", audio_filename
            )
            
            # Fallback to other theme if file doesn't exist
            if not os.path.exists(audio_path):
                # Try the other theme
                fallback_theme = "Wall-e" if theme_name == "Star Wars" else "Star Wars"
                audio_path = os.path.join(
                    "resources", "theme", fallback_theme, "audio", audio_filename
                )
            
            # Play audio if file exists
            if os.path.exists(audio_path):
                pygame.mixer.music.load(audio_path)
                pygame.mixer.music.play()
                self.logger.debug(f"Playing alert audio: {audio_path}")
            else:
                self.logger.warning(f"Alert audio file not found: {audio_filename}")
                
        except Exception as e:
            self.logger.error(f"Failed to play alert audio: {e}")
    
    def close_splash(self):
        """Close the splash screen"""
        if hasattr(self, 'close_timer'):
            self.close_timer.stop()
        if hasattr(self, 'countdown_timer'):
            self.countdown_timer.stop()
        
        try:
            if self.audio_available and pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception as e:
            self.logger.debug(f"Minor issue stopping audio: {e}")
        
        self.splash_closed.emit()
        self.close()
        self.deleteLater()
    
    def mousePressEvent(self, event):
        """Allow manual close by clicking"""
        self.close_splash()
    
    def keyPressEvent(self, event):
        """Allow manual close with Escape key"""
        if event.key() == Qt.Key.Key_Escape:
            self.close_splash()
        super().keyPressEvent(event)