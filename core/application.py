"""
Droid Deck Control System - Main Application Class with Front Splash & Shutdown
"""

import os
import time
from PyQt6.QtWidgets import QMainWindow, QStackedWidget, QVBoxLayout, QHBoxLayout, QFrame, QWidget, QPushButton, QApplication
from PyQt6.QtGui import QPixmap, QPalette, QBrush, QIcon, QFont
from PyQt6.QtCore import Qt, QTimer, QSize

from .config_manager import config_manager
from .logger import get_logger, logger_manager
from .websocket_manager import WebSocketManager
from .theme_manager import theme_manager
from .utils import MemoryManager, error_boundary
from widgets.base_screen import DynamicHeader
from widgets.home_screen import HomeScreen
from widgets.camera_screen import CameraFeedScreen  
from widgets.health_screen import HealthScreen
from widgets.servo_screen import ServoConfigScreen
from widgets.controller_screen import ControllerConfigScreen
from widgets.settings_screen import SettingsScreen
from widgets.scene_screen import SceneScreen
from widgets.splash_screen import DroidDeckSplashScreen, show_shutdown_splash


class DroidDeckApplication(QMainWindow):
    """Main DroidDeck application window with enhanced splash screens"""
    
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
    
        # Show splash screen first - it will come to front
        self.splash = DroidDeckSplashScreen()
        self.splash.show()
        self.splash.raise_()
        self.splash.activateWindow()
        QApplication.processEvents()
        
        # Define initialization steps with messages and methods
        self.init_steps = [
            ("Initializing DroidDeck core...", self._setup_logging),
            ("Loading configuration files...", self._setup_theme),
            ("Establishing connections...", self._setup_websocket_step),
            ("Loading interface modules...", self._setup_screens),
            ("Configuring navigation...", self._setup_navigation_step),
            ("Finalizing DroidDeck...", self._finalize_setup)
        ]
        
        # Run initialization with progress tracking
        self._run_initialization()
    
    def _run_initialization(self):
        """Run initialization steps with realistic timing"""
        try:
            for i, (message, method) in enumerate(self.init_steps):
                # Update splash screen with current step
                self.splash.update_progress(i, message)
                
                # Vary delay based on step complexity
                if i in [2, 3]:  # Connection and screens steps
                    time.sleep(1.2)
                elif i in [1, 4]:  # Config and navigation steps
                    time.sleep(0.8)
                else:
                    time.sleep(0.6)
                
                # Execute the initialization step
                method()
                
                # Process events to update splash
                QApplication.processEvents()
                
                # Extra delay after heavy steps
                if i in [2, 3]:  # After connections and screens
                    time.sleep(0.4)
            
            # Mark initialization complete
            self.splash.finish_loading()
            
            # Show main window after splash closes
            QTimer.singleShot(2200, self._show_main_window)
            
        except Exception as e:
            # Show error on splash
            error_msg = f"Initialization failed: {str(e)}"
            self.splash.set_message(error_msg)
            if hasattr(self, 'logger'):
                self.logger.error(f"DroidDeck initialization error: {e}")
            
            # Handle error after delay
            captured_error = e
            QTimer.singleShot(3000, lambda: self._handle_init_error(captured_error))
    
    def _show_main_window(self):
        """Show main window and complete initialization"""
        self.show()
        self.raise_()
        self.activateWindow()
        if hasattr(self, 'logger'):
            self.logger.info(f"DroidDeck Control System initialized - Pi IP: {self.pi_ip}, Theme: {theme_manager.get_display_name()}")
    
    def _handle_init_error(self, error):
        """Handle initialization errors"""
        # Could show error dialog or attempt recovery
        # For now, just close the application
        QApplication.quit()
    
    def _setup_logging(self):
        """Initialize the logging system"""
        self.logger = get_logger("main")
        time.sleep(0.3)
        
        logging_config = config_manager.get_logging_config()
        logger_manager.configure(
            debug_level=logging_config["debug_level"],
            module_debug=logging_config["module_debug"]
        )
        time.sleep(0.2)
    def _center_main_window(self):
        """Center the main application window on screen"""
        try:
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen().availableGeometry()
            
            # Calculate center position
            x = (screen.width() - self.width()) // 2
            y = (screen.height() - self.height()) // 2
            
            self.move(x, y)
            
            if hasattr(self, 'logger'):
                self.logger.debug(f"Centered main window at ({x}, {y}) on screen {screen.width()}x{screen.height()}")
                
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.warning(f"Could not center main window: {e}")
            # Fallback positioning
            self.move(100, 100)
            
    def _setup_theme(self):
        """Initialize theme manager and window setup"""
        time.sleep(0.4)
        
        # Initialize theme manager
        theme_manager.initialize()
        theme_manager.register_callback(self._apply_theme)
        
        # Setup main window with DroidDeck branding
        self.setWindowTitle("DroidDeck - Professional Droid Control System")
        self.setFixedSize(1280, 800)
        self._setup_background()
        time.sleep(0.3)
    
    def _setup_websocket_step(self):
        """Setup WebSocket connection"""
        time.sleep(0.5)
        
        self.websocket = self._setup_websocket()
        
        # Get Pi IP from config for network monitoring
        wave_config = config_manager.get_wave_config()
        proxy_url = wave_config.get("camera_proxy_url", "http://10.1.1.230:8081")
        # Extract IP from proxy URL
        import re
        ip_match = re.search(r'http://([^:]+)', proxy_url)
        self.pi_ip = ip_match.group(1) if ip_match else "10.1.1.230"
        time.sleep(0.3)
    
    def _setup_screens(self):
        """Initialize all application screens"""
        time.sleep(0.4)
        
        # Initialize UI components with Pi IP
        self.header = DynamicHeader("Home", pi_ip=self.pi_ip)
        self.header.setMaximumWidth(1000)
        self.stack = QStackedWidget()
        
        time.sleep(0.3)
        
        # Create screens with shared WebSocket
        self.home_screen = HomeScreen(self.websocket)
        time.sleep(0.1)
        self.camera_screen = CameraFeedScreen(self.websocket)
        time.sleep(0.1)
        self.health_screen = HealthScreen(self.websocket)
        time.sleep(0.1)
        self.servo_screen = ServoConfigScreen(self.websocket)
        time.sleep(0.1)
        self.controller_screen = ControllerConfigScreen(self.websocket)
        time.sleep(0.1)
        self.settings_screen = SettingsScreen()
        time.sleep(0.1)
        self.scene_screen = SceneScreen(self.websocket)
        
        # Add screens to stack
        self.stack.addWidget(self.home_screen)
        self.stack.addWidget(self.camera_screen)
        self.stack.addWidget(self.health_screen)
        self.stack.addWidget(self.servo_screen)
        self.stack.addWidget(self.controller_screen)
        self.stack.addWidget(self.settings_screen)
        self.stack.addWidget(self.scene_screen)
        
        # Connect scene screen signals to home screen for updates
        if hasattr(self.scene_screen, 'scenes_updated') and hasattr(self.home_screen, 'connect_scene_screen_signals'):
            self.home_screen.connect_scene_screen_signals(self.scene_screen)
        
        time.sleep(0.2)
    
    def _setup_navigation_step(self):
        """Setup navigation and memory management"""
        time.sleep(0.3)
        
        self.nav_buttons = {}
        
        # Setup memory management
        self._setup_memory_management()
        
        # Setup UI layout
        self._setup_navigation()
        time.sleep(0.2)

        self.menuBar().hide()
        self._setup_hidden_exit()


    def _setup_hidden_exit(self):
        """Setup hidden exit functionality"""
        # Option 1: Keyboard shortcut (Ctrl+Q or Cmd+Q)
        from PyQt6.QtGui import QShortcut, QKeySequence
        exit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        exit_shortcut.activated.connect(self.close_application)
        

    def close_application(self):
        """Safely close the application"""
        self.logger.info("Application exit requested")
        
        # Cleanup health screen resources
        if hasattr(self, 'health_screen'):
            self.health_screen.cleanup()
        
        # Close websocket connections
        if hasattr(self, 'websocket'):
            self.websocket.close()
        
        # Exit application
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()

    
    def _finalize_setup(self):
        """Finalize setup and apply theme"""
        time.sleep(0.3)
        
        self._setup_layout()
        
        # Apply initial theme
        self._apply_theme()
        self._center_main_window()
        
        # Connect telemetry updates to header
        self.websocket.textMessageReceived.connect(self._update_header_from_telemetry)
        time.sleep(0.2)
    
    def _setup_background(self):
        """Set application background using theme manager"""
        background_path = theme_manager.get_image_path("background")
        if os.path.exists(background_path):
            background = QPixmap(background_path)
            palette = QPalette()
            palette.setBrush(QPalette.ColorRole.Window, QBrush(background))
            self.setPalette(palette)
            if hasattr(self, 'logger'):
                self.logger.debug(f"Applied background: {background_path}")
        else:
            if hasattr(self, 'logger'):
                self.logger.warning(f"Background image not found: {background_path}")
    
    def _setup_websocket(self) -> WebSocketManager:
        """Setup WebSocket connection"""
        ws_url = config_manager.get_websocket_url()
        if not ws_url.startswith("ws://"):
            ws_url = f"ws://{ws_url}"
        return WebSocketManager(ws_url)
    
    def _setup_memory_management(self):
        """Setup periodic memory cleanup"""
        self.memory_timer = QTimer()
        self.memory_timer.timeout.connect(MemoryManager.periodic_cleanup)
        self.memory_timer.start(30000)  # 30 seconds
    
    def _setup_navigation(self):
        """Setup navigation bar with screen buttons using themed icons"""
        self.nav_bar = QHBoxLayout()
        self.nav_bar.addSpacing(100)
        
        # Define navigation buttons
        navigation_items = [
            ("Home", self.home_screen, "home"),
            ("Camera", self.camera_screen, "camera"),
            ("Health", self.health_screen, "health"),
            ("ServoConfig", self.servo_screen, "servo"),
            ("Controller", self.controller_screen, "controller"),
            ("Settings", self.settings_screen, "settings"),
            ("Scene", self.scene_screen, "scene")
        ]
        
        # Create navigation buttons with themed icons
        for name, screen, icon_key in navigation_items:
            btn = QPushButton()
            btn.clicked.connect(lambda _, s=screen, n=name: self.switch_screen(s, n))
            self.nav_bar.addWidget(btn)
            self.nav_buttons[name] = {"button": btn, "icon_key": icon_key}
        
        # Failsafe button with themed icon
        self.failsafe_button = QPushButton()
        self.failsafe_button.setCheckable(True)
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
    
    def _apply_theme(self):
        """Apply current theme to all UI elements"""
        # Update background
        self._setup_background()
        
        # Update navigation icons
        for name, nav_info in self.nav_buttons.items():
            button = nav_info["button"]
            icon_key = nav_info["icon_key"]
            
            # Set normal icon
            normal_icon_path = theme_manager.get_icon_path(icon_key, pressed=False)
            if os.path.exists(normal_icon_path):
                button.setIcon(QIcon(normal_icon_path))
                button.setIconSize(QSize(64, 64))
            else:
                if hasattr(self, 'logger'):
                    self.logger.warning(f"Icon not found: {normal_icon_path}")
        
        # Update failsafe button icon
        failsafe_icon_path = theme_manager.get_icon_path("failsafe", pressed=False)
        if os.path.exists(failsafe_icon_path):
            self.failsafe_button.setIcon(QIcon(failsafe_icon_path))
            self.failsafe_button.setIconSize(QSize(300, 70))
        else:
            if hasattr(self, 'logger'):
                self.logger.warning(f"Failsafe icon not found: {failsafe_icon_path}")
        
        # Update window title with DroidDeck branding and theme
        self.setWindowTitle(f"Droid Deck - {theme_manager.get_display_name()} Theme")
        
        if hasattr(self, 'logger'):
            self.logger.info(f"Applied {theme_manager.get_display_name()} theme to DroidDeck")
    
    @error_boundary
    def switch_screen(self, screen, name: str):
        """Switch to specified screen and update navigation with themed icons"""
        self.stack.setCurrentWidget(screen)
        self.header.set_screen_name(name)
        
        # Update navigation icons with theme support
        for btn_name, nav_info in self.nav_buttons.items():
            button = nav_info["button"]
            icon_key = nav_info["icon_key"]
            
            if btn_name == name:
                # Use pressed/active icon
                pressed_icon_path = theme_manager.get_icon_path(icon_key, pressed=True)
                if os.path.exists(pressed_icon_path):
                    button.setIcon(QIcon(pressed_icon_path))
                else:
                    # Fallback to normal icon
                    normal_icon_path = theme_manager.get_icon_path(icon_key, pressed=False)
                    if os.path.exists(normal_icon_path):
                        button.setIcon(QIcon(normal_icon_path))
            else:
                # Use normal icon
                normal_icon_path = theme_manager.get_icon_path(icon_key, pressed=False)
                if os.path.exists(normal_icon_path):
                    button.setIcon(QIcon(normal_icon_path))
        
        if hasattr(self, 'logger'):
            self.logger.debug(f"Switched to {name} screen")
    
    @error_boundary
    def _toggle_failsafe(self, checked):
        """Toggle failsafe state and send to backend with themed icons"""
        # Update button icon based on state
        if checked:
            pressed_icon_path = theme_manager.get_icon_path("failsafe", pressed=True)
            if os.path.exists(pressed_icon_path):
                self.failsafe_button.setIcon(QIcon(pressed_icon_path))
        else:
            normal_icon_path = theme_manager.get_icon_path("failsafe", pressed=False)
            if os.path.exists(normal_icon_path):
                self.failsafe_button.setIcon(QIcon(normal_icon_path))
        
        # Send command to backend
        self.websocket.send_command("failsafe", state=checked)
        if hasattr(self, 'logger'):
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
            if hasattr(self, 'logger'):
                self.logger.error(f"Header update error: {e}")
    
    def closeEvent(self, event):
        """Handle application shutdown with shutdown splash"""
        # Show shutdown splash
        self.shutdown_splash = show_shutdown_splash()
        QApplication.processEvents()
        
        if hasattr(self, 'logger'):
            self.logger.info("DroidDeck closing - cleaning up resources")
        
        shutdown_steps = [
            ("Saving configurations...", self._save_configs_on_exit),
            ("Closing connections...", self._close_connections),
            ("Stopping processes...", self._stop_background_processes),
            ("Cleaning resources...", self._cleanup_resources),
            ("Shutdown complete", lambda: None)
        ]
        
        # Run shutdown steps with progress
        for i, (message, method) in enumerate(shutdown_steps):
            self.shutdown_splash.update_shutdown_progress(i)
            time.sleep(0.4)  # Show progress
            try:
                method()
            except Exception as e:
                if hasattr(self, 'logger'):
                    self.logger.error(f"Shutdown error in {message}: {e}")
            QApplication.processEvents()
        
        # Final step
        self.shutdown_splash.update_shutdown_progress(len(shutdown_steps))
        time.sleep(0.8)
        
        self.shutdown_splash.close()
        event.accept()
    
    def _save_configs_on_exit(self):
        """Save any pending configurations"""
        # Add any config saving logic here if needed
        pass
    
    def _close_connections(self):
        """Close WebSocket and network connections"""
        if hasattr(self, 'websocket'):
            self.websocket.close()
    
    def _stop_background_processes(self):
        """Stop background processes"""
        # Stop network monitoring in header
        if hasattr(self.header, 'cleanup'):
            self.header.cleanup()
        
        # Stop camera thread
        if hasattr(self.camera_screen, 'cleanup'):
            self.camera_screen.cleanup()
        
        # Stop servo operations
        if hasattr(self.servo_screen, 'stop_all_operations'):
            self.servo_screen.stop_all_operations()
        
        # Stop health screen network monitoring
        if hasattr(self.health_screen, 'cleanup'):
            self.health_screen.cleanup()
        
        # Cleanup settings screen
        if hasattr(self.settings_screen, 'cleanup'):
            self.settings_screen.cleanup()
    
    def _cleanup_resources(self):
        """Final resource cleanup"""
        # Unregister theme manager
        theme_manager.unregister_callback(self._apply_theme)
        
        # Stop timers
        if hasattr(self, 'memory_timer'):
            self.memory_timer.stop()
        
        # Final cleanup
        MemoryManager.cleanup_widgets(self)