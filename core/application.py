"""
WALL-E Control System - Main Application Class (Updated)
"""

import os
from PyQt6.QtWidgets import QMainWindow, QStackedWidget, QVBoxLayout, QHBoxLayout, QFrame, QWidget, QPushButton
from PyQt6.QtGui import QPixmap, QPalette, QBrush, QIcon, QFont
from PyQt6.QtCore import Qt, QTimer, QSize

from .config_manager import config_manager
from .logger import get_logger, logger_manager
from .websocket_manager import WebSocketManager
from .utils import MemoryManager, error_boundary
from widgets.base_screen import DynamicHeader
from widgets.home_screen import HomeScreen
from widgets.camera_screen import CameraFeedScreen  
from widgets.health_screen import HealthScreen
from widgets.servo_screen import ServoConfigScreen
from widgets.controller_screen import ControllerConfigScreen
from widgets.settings_screen import SettingsScreen
from widgets.scene_screen import SceneScreen


class WalleApplication(QMainWindow):
    """Main WALL-E application window managing all screens and navigation"""
    
    def __init__(self):
        super().__init__()
        self.logger = get_logger("main")
        
        # Initialize logging system
        self._setup_logging()
        
        # Setup main window
        self.setWindowTitle("WALL-E Control System")
        self.setFixedSize(1280, 800)
        self._setup_background()
        
        # Initialize WebSocket connection
        self.websocket = self._setup_websocket()
        
        # Get Pi IP from config for network monitoring
        wave_config = config_manager.get_wave_config()
        proxy_url = wave_config.get("camera_proxy_url", "http://10.1.1.230:8081")
        # Extract IP from proxy URL
        import re
        ip_match = re.search(r'http://([^:]+)', proxy_url)
        self.pi_ip = ip_match.group(1) if ip_match else "10.1.1.230"
        
        # Initialize UI components with Pi IP
        self.header = DynamicHeader("Home", pi_ip=self.pi_ip)
        self.header.setMaximumWidth(1000)
        self.stack = QStackedWidget()
        self.nav_buttons = {}
        
        # Initialize screens
        self._setup_screens()
        
        # Setup memory management
        self._setup_memory_management()
        
        # Setup UI layout
        self._setup_navigation()
        self._setup_layout()
        
        # Connect telemetry updates to header (voltage only, WiFi handled by network monitor)
        self.websocket.textMessageReceived.connect(self._update_header_from_telemetry)
        
        self.logger.info(f"WALL-E Control System initialized with Pi IP: {self.pi_ip}")
    
    def _setup_logging(self):
        """Initialize the logging system with configuration"""
        logging_config = config_manager.get_logging_config()
        logger_manager.configure(
            debug_level=logging_config["debug_level"],
            module_debug=logging_config["module_debug"]
        )
    
    def _setup_background(self):
        """Set application background if available"""
        if os.path.exists("resources/images/background.png"):
            background = QPixmap("resources/images/background.png")
            palette = QPalette()
            palette.setBrush(QPalette.ColorRole.Window, QBrush(background))
            self.setPalette(palette)
    
    def _setup_websocket(self) -> WebSocketManager:
        """Setup WebSocket connection"""
        ws_url = config_manager.get_websocket_url()
        if not ws_url.startswith("ws://"):
            ws_url = f"ws://{ws_url}"
        return WebSocketManager(ws_url)
    
    def _setup_screens(self):
        """Initialize all application screens"""
        # Create screens with shared WebSocket
        self.home_screen = HomeScreen(self.websocket)
        self.camera_screen = CameraFeedScreen(self.websocket)
        self.health_screen = HealthScreen(self.websocket)
        self.servo_screen = ServoConfigScreen(self.websocket)
        self.controller_screen = ControllerConfigScreen(self.websocket)
        self.settings_screen = SettingsScreen()
        self.scene_screen = SceneScreen(self.websocket)
        
        # Add screens to stack
        self.stack.addWidget(self.home_screen)
        self.stack.addWidget(self.camera_screen)
        self.stack.addWidget(self.health_screen)
        self.stack.addWidget(self.servo_screen)
        self.stack.addWidget(self.controller_screen)
        self.stack.addWidget(self.settings_screen)
        self.stack.addWidget(self.scene_screen)
    
    def _setup_memory_management(self):
        """Setup periodic memory cleanup"""
        self.memory_timer = QTimer()
        self.memory_timer.timeout.connect(MemoryManager.periodic_cleanup)
        self.memory_timer.start(30000)  # 30 seconds
    
    def _setup_navigation(self):
        """Setup navigation bar with screen buttons"""
        self.nav_bar = QHBoxLayout()
        self.nav_bar.addSpacing(100)
        
        # Define navigation buttons
        navigation_items = [
            ("Home", self.home_screen),
            ("Camera", self.camera_screen),
            ("Health", self.health_screen),
            ("ServoConfig", self.servo_screen),
            ("Controller", self.controller_screen),
            ("Settings", self.settings_screen),
            ("Scene", self.scene_screen)
        ]
        
        # Create navigation buttons
        for name, screen in navigation_items:
            btn = QPushButton()
            icon_path = f"resources/icons/{name}.png"
            if os.path.exists(icon_path):
                btn.setIcon(QIcon(icon_path))
                btn.setIconSize(QSize(64, 64))
            btn.clicked.connect(lambda _, s=screen, n=name: self.switch_screen(s, n))
            self.nav_bar.addWidget(btn)
            self.nav_buttons[name] = btn
        
        # Failsafe button
        self.failsafe_button = QPushButton()
        self.failsafe_button.setCheckable(True)
        failsafe_icon = "resources/icons/failsafe.png"
        if os.path.exists(failsafe_icon):
            self.failsafe_button.setIcon(QIcon(failsafe_icon))
            self.failsafe_button.setIconSize(QSize(300, 70))
        self.failsafe_button.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white;")
        self.failsafe_button.clicked.connect(self._toggle_failsafe)
        
        self.nav_bar.addSpacing(20)
        self.nav_bar.addWidget(self.failsafe_button)
        self.nav_bar.addSpacing(100)
    
    def _setup_layout(self):
        """Setup main window layout"""
        # Navigation frame
        nav_frame = QFrame()
        nav_frame.setLayout(self.nav_bar)
        nav_frame.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white;")
        
        # Main layout
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.addSpacing(60)
        
        # Header container
        header_container = QWidget()
        header_layout = QHBoxLayout()
        header_layout.addWidget(self.header)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_container.setLayout(header_layout)
        
        layout.addWidget(header_container)
        layout.addSpacing(2)
        layout.addWidget(self.stack)
        layout.addWidget(nav_frame)
        layout.addSpacing(35)
        
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        
        # Set initial screen
        self.switch_screen(self.home_screen, "Home")
    
    @error_boundary
    def switch_screen(self, screen, name: str):
        """Switch to specified screen and update navigation"""
        self.stack.setCurrentWidget(screen)
        self.header.set_screen_name(name)
        
        # Update navigation icons
        for btn_name, btn in self.nav_buttons.items():
            pressed_icon = f"resources/icons/{btn_name}_pressed.png"
            normal_icon = f"resources/icons/{btn_name}.png"
            
            if btn_name == name and os.path.exists(pressed_icon):
                btn.setIcon(QIcon(pressed_icon))
            elif os.path.exists(normal_icon):
                btn.setIcon(QIcon(normal_icon))
        
        self.logger.debug(f"Switched to {name} screen")
    
    @error_boundary
    def _toggle_failsafe(self, checked):
        """Toggle failsafe state and send to backend"""
        # Update button icon
        if checked:
            pressed_icon = "resources/icons/failsafe_pressed.png"
            if os.path.exists(pressed_icon):
                self.failsafe_button.setIcon(QIcon(pressed_icon))
        else:
            normal_icon = "resources/icons/failsafe.png"
            if os.path.exists(normal_icon):
                self.failsafe_button.setIcon(QIcon(normal_icon))
        
        # Send command to backend
        self.websocket.send_command("failsafe", state=checked)
        self.logger.info(f"Failsafe toggled: {checked}")
    
    def _update_header_from_telemetry(self, message: str):
        """Update header voltage from telemetry data"""
        try:
            import json
            data = json.loads(message)
            if data.get("type") == "telemetry":
                voltage = data.get("battery_voltage", 0.0)
                if voltage > 0:
                    self.header.update_voltage(voltage)
                
        except Exception as e:
            self.logger.error(f"Header update error: {e}")
    
    def closeEvent(self, event):
        """Handle application shutdown with proper cleanup"""
        self.logger.info("Application closing - cleaning up resources")
        
        # Stop network monitoring in header
        if hasattr(self.header, 'cleanup'):
            self.header.cleanup()
        
        # Stop camera thread if active
        if hasattr(self.camera_screen, 'image_thread'):
            self.camera_screen.stop_camera_thread()
        
        # Stop servo operations
        if hasattr(self.servo_screen, 'stop_all_operations'):
            self.servo_screen.stop_all_operations()
        
        # Stop health screen network monitoring
        if hasattr(self.health_screen, 'cleanup'):
            self.health_screen.cleanup()
        
        # Close WebSocket connection
        if hasattr(self, 'websocket'):
            self.websocket.close()
        
        # Stop timers
        if hasattr(self, 'memory_timer'):
            self.memory_timer.stop()
        
        # Final cleanup
        MemoryManager.cleanup_widgets(self)
        event.accept()