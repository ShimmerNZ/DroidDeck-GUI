"""
WALL-E Control System - Updated Base Screen Components with WiFi Monitoring
"""

import random
from abc import ABC, abstractmethod
from PyQt6.QtWidgets import QWidget, QLabel, QFrame, QHBoxLayout
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QTimer

from core.logger import get_logger
from core.utils import error_boundary
from threads.network_monitor import NetworkMonitorThread


# Create a compatible metaclass for PyQt6 + ABC
class WidgetABCMeta(type(QWidget), type(ABC)):
    pass


class BaseScreen(QWidget, ABC, metaclass=WidgetABCMeta):
    """Abstract base class for all application screens"""
    
    def __init__(self, websocket=None):
        super().__init__()
        self.logger = get_logger(self.__class__.__name__.lower())
        self.websocket = websocket
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        self._setup_screen()
    
    @abstractmethod
    def _setup_screen(self):
        """Setup screen-specific UI components"""
        pass
    
    def cleanup(self):
        """Override in subclasses for custom cleanup"""
        pass
    
    @error_boundary
    def send_websocket_message(self, message_type: str, **kwargs) -> bool:
        """Send message via WebSocket if available"""
        if self.websocket and self.websocket.is_connected():
            return self.websocket.send_command(message_type, **kwargs)
        else:
            self.logger.warning(f"Cannot send {message_type}: WebSocket not connected")
            return False

from PyQt6.QtGui import QPainter, QColor, QFont
from PyQt6.QtCore import QRect

class WiFiSignalWidget(QWidget):
    """Custom widget for displaying WiFi signal strength with visual bars"""
    
    def __init__(self):
        super().__init__()
        self.setFixedSize(300, 32)
        self.current_signal = 0
        self.current_ping = None
        self.flash_timer = QTimer()
        self.flash_timer.timeout.connect(self.toggle_flash)
        self.flash_state = True
        self.color = "#44FF44"
        self.update_display(0, None)
    
    def update_display(self, signal_percent: int, ping_ms: float = None):
        """Update WiFi display with signal bars and ping-based coloring"""
        self.current_signal = signal_percent
        self.current_ping = ping_ms
        
        # Determine color based on ping quality
        self.color, should_flash = self.get_color_from_ping(ping_ms)
        
        # Handle flashing for no response
        if should_flash:
            self.start_flashing()
        else:
            self.stop_flashing()
        
        # Trigger repaint
        self.update()
    
    def paintEvent(self, event):
        """Custom paint event to draw signal bars"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Bar dimensions and positions
        bar_width = 4
        bar_spacing = 2
        bar_heights = [10, 15, 20, 25, 30]  # Heights for bars 1-4
        start_x = 190  # Position bars more to the right
        base_y = 30
        
        # Determine how many bars should be active
        if self.current_signal >= 95:
            active_bars = 5 
        elif self.current_signal >= 75:
            active_bars = 4
        elif self.current_signal >= 50:
            active_bars = 3
        elif self.current_signal >= 25:
            active_bars = 2
        elif self.current_signal > 0:
            active_bars = 1
        else:
            active_bars = 0
        
        # Draw bars
        for i in range(5):
            x = start_x + i * (bar_width + bar_spacing)
            y = base_y - bar_heights[i]
            
            if i < active_bars:
                color = QColor(self.color)
                if not self.flash_state and self.current_ping is None:
                    color.setAlpha(80)  # Dim when flashing
            else:
                color = QColor("#333333")  # Inactive bars
            
            painter.fillRect(QRect(x, y, bar_width, bar_heights[i]), color)
        
        # Draw percentage text positioned from right edge
        text_x = self.width() - 80
        text_y = base_y - 5
        
        status_text = f"{self.current_signal}%"
        painter.setPen(QColor(self.color))
        painter.setFont(QFont("Arial", 30))
        painter.drawText(text_x, text_y, status_text)
    
    def get_color_from_ping(self, ping_ms: float = None) -> tuple:
        """Get color and flash state based on ping quality"""
        if ping_ms is None:
            return "#FF4444", True
        elif ping_ms < 20:
            return "#44FF44", False
        elif ping_ms < 50:
            return "#FFAA00", False
        elif ping_ms < 100:
            return "#FF8800", False
        else:
            return "#FF4444", False
    
    def start_flashing(self):
        """Start flashing animation"""
        self.flash_timer.start(500)
    
    def stop_flashing(self):
        """Stop flashing animation"""
        self.flash_timer.stop()
        self.flash_state = True
    
    def toggle_flash(self):
        """Toggle flash state and trigger repaint"""
        self.flash_state = not self.flash_state
        self.update()

class DynamicHeader(QFrame):
    """Dynamic header showing system status at top of application"""
    
    def __init__(self, screen_name: str, pi_ip: str = "10.1.1.230"):
        super().__init__()
        self.logger = get_logger("ui")
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white;")
        self.pi_ip = pi_ip
        self._setup_ui(screen_name)
        self._setup_network_monitoring()
    
    def _setup_ui(self, screen_name: str):
        """Setup header UI components"""
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(0)

        # Status labels
        self.voltage_label = QLabel("🔋 --.-V")
        self.wifi_widget = WiFiSignalWidget()  # Custom WiFi widget
        self.screen_label = QLabel(screen_name)

        # Font styling - all same size
        header_font = QFont("Arial", 30)
        self.voltage_label.setFont(header_font)
        self.screen_label.setFont(header_font)
        
        # Center align the screen label
        self.screen_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Set fixed widths for proper centering and spacing
        self.voltage_label.setFixedWidth(300)     # Increased for left section
        self.screen_label.setFixedWidth(400)      # Center section stays same
        self.wifi_widget.setFixedWidth(310)       # Increased to match left section

        # Layout assembly with fixed positioning (no stretch)
        layout.addWidget(self.voltage_label)
        layout.addWidget(self.screen_label) 
        layout.addWidget(self.wifi_widget)

        self.setLayout(layout)
    
    def _setup_network_monitoring(self):
        """Setup WiFi signal monitoring"""
        self.network_monitor = NetworkMonitorThread(pi_ip=self.pi_ip, update_interval=5.0)
        self.network_monitor.wifi_updated.connect(self.update_wifi_display)
        self.network_monitor.start()
        self.logger.info("Network monitoring started for header")
    
    def update_voltage(self, voltage: float):
        """Update voltage display with color coding based on level"""
        if voltage < 13.2:
            self.voltage_label.setText(f"🔋 {voltage:.2f}V")
            self.voltage_label.setStyleSheet("color: #FF4444; font-weight: bold;")
        elif voltage < 14.0:
            self.voltage_label.setText(f"🔋 {voltage:.2f}V")
            self.voltage_label.setStyleSheet("color: #FFAA00; font-weight: bold;")
        elif voltage > 14.0:
            self.voltage_label.setText(f"🔋 {voltage:.2f}V")
            self.voltage_label.setStyleSheet("color: #44FF44;")
        else:
            self.voltage_label.setText(f"🔋 {voltage:.2f}V")
            self.voltage_label.setStyleSheet("color: white;")

    def update_wifi_display(self, signal_percent: int, status_text: str, ping_ms: float):
        """Update WiFi display with signal bars and ping-based coloring"""
        self.wifi_widget.update_display(signal_percent, ping_ms if ping_ms > 0 else None)

    def update_wifi(self, percentage: int):
        """Legacy method for compatibility - now uses signal bars"""
        # This maintains compatibility with existing code that might call this
        self.wifi_widget.update_display(percentage, None)

    def set_screen_name(self, name: str):
        """Update the current screen name display"""
        self.screen_label.setText(name)

    def cleanup(self):
        """Cleanup header resources"""
        if hasattr(self, 'network_monitor'):
            self.network_monitor.stop()


class StatusMixin:
    """Mixin class providing status update functionality"""
    
    def __init__(self):
        self._status_callbacks = []
    
    def add_status_callback(self, callback):
        """Add callback function for status updates"""
        self._status_callbacks.append(callback)
    
    def update_status(self, message: str, level: str = "info"):
        """Update status with specified message and level"""
        for callback in self._status_callbacks:
            try:
                callback(message, level)
            except Exception as e:
                if hasattr(self, 'logger'):
                    self.logger.error(f"Status callback error: {e}")


class PlaceholderScreen(BaseScreen):
    """Placeholder screen for features under development"""
    
    def __init__(self, title: str, websocket=None):
        self.title = title
        super().__init__(websocket)
    
    def _setup_screen(self):
        """Setup placeholder screen UI"""
        from PyQt6.QtWidgets import QVBoxLayout
        
        self.setFixedSize(1280, 800)
        
        label = QLabel(f"{self.title} Screen Coming Soon")
        label.setFont(QFont("Arial", 24))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout = QVBoxLayout()
        layout.addWidget(label)
        self.setLayout(layout)