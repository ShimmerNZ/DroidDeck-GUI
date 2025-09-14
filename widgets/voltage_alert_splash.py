# widgets/voltage_alert_splash.py

import os
import pygame
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QColor
from core.theme_manager import theme_manager
from core.logger import get_logger

class VoltageAlertSplash(QWidget):
    """Non-blocking splash screen for voltage alerts with themed audio"""
    
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
        """Setup the splash screen UI"""
        # Remove window decorations and make frameless
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        
        # Set window properties
        self.setFixedSize(500, 200)

        
        # Center on screen
        self._center_on_screen()
        
        # Create layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Create content layout with icon and text
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)
        
        # Alert icon
        icon_label = QLabel()
        icon_label.setFixedSize(80, 80)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet(self._get_icon_style())
        icon_label.setText("⚠️" if self.alert_type == "LOW" else "🛑")
        content_layout.addWidget(icon_label)
        
        # Text content
        text_layout = QVBoxLayout()
        text_layout.setSpacing(8)
        
        # Title
        title_label = QLabel()
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        title_label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        title_label.setStyleSheet(self._get_title_style())
        
        if self.alert_type == "CRITICAL":
            title_label.setText("CRITICAL: Battery voltage is critical!")
        else:
            title_label.setText("WARNING: Battery voltage is low")
        
        # Voltage display
        voltage_label = QLabel(f"Current voltage: {self.voltage:.2f}V")
        voltage_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        voltage_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        voltage_label.setStyleSheet(self._get_voltage_style())
        
        # Action message
        action_label = QLabel()
        action_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        action_label.setFont(QFont("Arial", 12))
        action_label.setStyleSheet(self._get_action_style())
        
        if self.alert_type == "CRITICAL":
            action_label.setText("Land immediately to prevent damage!")
        else:
            action_label.setText("Consider landing soon.")
        
        text_layout.addWidget(title_label)
        text_layout.addWidget(voltage_label)
        text_layout.addWidget(action_label)
        text_layout.addStretch()
        
        content_layout.addLayout(text_layout)
        content_layout.addStretch()
        
        main_layout.addLayout(content_layout)
        
        # Auto-close indicator
        self.countdown_label = QLabel("Auto-close in 5 seconds...")
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.setFont(QFont("Arial", 10))
        self.countdown_label.setStyleSheet(self._get_countdown_style())
        main_layout.addWidget(self.countdown_label)
        
        self.setLayout(main_layout)
        
        # Apply main window styling
        self.setStyleSheet(self._get_main_style())
        
    def _center_on_screen(self):
        """Center the splash screen on the display with better positioning"""
        # Always show first, then position
        self.show()
        
        try:
            # Get the primary screen geometry
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen().availableGeometry()
            
            # Calculate center position
            x = (screen.width() - self.width()) // 2
            y = (screen.height() - self.height()) // 2
            
            self.move(x, y)
               
        except Exception as e:
            self.logger.warning(f"Could not center splash screen: {e}")
            # Fallback positioning - center of a typical screen
            self.move(400, 300)
        
        # Force to front after positioning
        self.raise_()
        self.activateWindow()
    
    def _setup_auto_close(self):
        """Setup timer for auto-close functionality"""
        self.countdown = 5
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self._update_countdown)
        self.countdown_timer.start(1000)  # Update every second
        
        # Auto-close timer
        self.close_timer = QTimer()
        self.close_timer.timeout.connect(self.close_splash)
        self.close_timer.setSingleShot(True)
        self.close_timer.start(5000)  # Close after 3 seconds
    
    def _update_countdown(self):
        """Update countdown display"""
        self.countdown -= 1
        if self.countdown > 0:
            self.countdown_label.setText(f"Auto-close in {self.countdown} second{'s' if self.countdown != 1 else ''}...")
        else:
            self.countdown_label.setText("Closing...")
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
                
    def _get_main_style(self):
        """Get main window styling with solid background and visible borders"""
        if self.alert_type == "CRITICAL":
            return """
                VoltageAlertSplash {
                    background-color: rgb(50, 15, 15);
                    border: 4px solid #ff4444;
                    border-radius: 30px;
                }
            """
        else:
            return """
                VoltageAlertSplash {
                    background-color: rgb(35, 35, 35);
                    border: 4px solid #e1a014;
                    border-radius: 30px;
                }
            """
    
    def _get_icon_style(self):
        """Get icon styling with better contrast"""
        if self.alert_type == "CRITICAL":
            return """
                QLabel {
                    font-size: 48px;
                    background: rgba(255, 100, 100, 150);
                    border-radius: 40px;
                    border: 3px solid #ff6666;
                    color: white;
                }
            """
        else:
            primary = theme_manager.get("primary_color")
            return f"""
                QLabel {{
                    font-size: 48px;
                    background: rgba(225, 160, 20, 150);
                    border-radius: 40px;
                    border: 3px solid {primary};
                    color: white;
                }}
            """
    
    def _get_title_style(self):
        """Get title styling"""
        if self.alert_type == "CRITICAL":
            return """
                QLabel {
                    color: #ff6666;
                    background: transparent;
                    border: none;
                }
            """
        else:
            primary = theme_manager.get("primary_color")
            return f"""
                QLabel {{
                    color: {primary};
                    background: transparent;
                    border: none;
                }}
            """
    
    def _get_voltage_style(self):
        """Get voltage display styling"""
        return """
            QLabel {
                color: white;
                background: transparent;
                border: none;
            }
        """
    
    def _get_action_style(self):
        """Get action message styling"""
        if self.alert_type == "CRITICAL":
            return """
                QLabel {
                    color: #ffaaaa;
                    background: transparent;
                    border: none;
                    font-style: italic;
                }
            """
        else:
            return """
                QLabel {
                    color: #cccccc;
                    background: transparent;
                    border: none;
                    font-style: italic;
                }
            """
    
    def _get_countdown_style(self):
        """Get countdown styling"""
        return """
            QLabel {
                color: #888888;
                background: transparent;
                border: none;
                font-style: italic;
            }
        """
    
    def close_splash(self):
        """Close the splash screen and emit signal"""
        self.close_timer.stop()
        self.countdown_timer.stop()
        
        # Stop any playing audio gracefully
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