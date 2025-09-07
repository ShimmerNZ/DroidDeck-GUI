"""
WALL-E Control System - Servo Configuration Screen (Themed)
Real-time servo control and configuration interface with theme support
"""

import json
import os
from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, 
                            QScrollArea, QWidget, QFrame, QLineEdit, QSpinBox, QSlider,
                            QCheckBox, QButtonGroup)
from PyQt6.QtGui import QFont, QIcon, QPainter, QPolygon, QColor
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal, QPoint

from widgets.base_screen import BaseScreen
from core.config_manager import config_manager
from core.theme_manager import theme_manager
from core.utils import error_boundary
from core.logger import get_logger


class HomePositionSlider(QSlider):
    """Custom slider with diamond home position indicator"""
    
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.home_position = None
        self._update_slider_style()
        # Register for theme changes
        theme_manager.register_callback(self._update_slider_style)
    
    def _update_slider_style(self):
        """Apply themed styling to slider"""
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        self.setStyleSheet(f"""
            QSlider {{
                border: none;
                background: transparent;
            }}
            QSlider::groove:horizontal {{
                border: none;
                height: 6px;
                background: #333;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {primary};
                border: none;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {primary_light};
            }}
        """)
    
    def set_home_position(self, position):
        """Set the home position for visual indication"""
        self.home_position = position
        self.update()
    
    def paintEvent(self, event):
        """Custom paint event to draw home position diamond"""
        super().paintEvent(event)
        
        if self.home_position is None:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calculate home position on slider
        slider_range = self.maximum() - self.minimum()
        if slider_range <= 0:
            return
            
        home_ratio = (self.home_position - self.minimum()) / slider_range
        
        # Get slider groove rectangle
        groove_rect = self.rect()
        groove_rect.setY(groove_rect.center().y() - 3)
        groove_rect.setHeight(6)
        groove_rect.setX(groove_rect.x() + 8)  # Account for handle width
        groove_rect.setWidth(groove_rect.width() - 16)
        
        # Calculate diamond position
        diamond_x = groove_rect.x() + int(home_ratio * groove_rect.width())
        diamond_y = groove_rect.center().y()
        
        # Draw diamond with theme color
        diamond_size = 4
        diamond = QPolygon([
            QPoint(diamond_x, diamond_y - diamond_size),      # Top
            QPoint(diamond_x + diamond_size, diamond_y),      # Right
            QPoint(diamond_x, diamond_y + diamond_size),      # Bottom
            QPoint(diamond_x - diamond_size, diamond_y)       # Left
        ])
        
        # Use theme primary color for home indicator
        home_color = theme_manager.get("primary_color", "#FFD700")
        painter.setBrush(QColor(home_color))
        painter.setPen(QColor(home_color))
        painter.drawPolygon(diamond)


class ServoConfigScreen(BaseScreen):
    """Real-time servo control and configuration interface"""
    
    # Qt signals for thread-safe communication
    position_update_signal = pyqtSignal(str, int)
    status_update_signal = pyqtSignal(str, bool, bool)
    
    def __init__(self, websocket=None):

        # Register for theme change notifications
        theme_manager.register_callback(self._on_theme_changed)
        
        # Add WebSocket connection monitoring
        self.ws_connection_timer = QTimer()
        self.ws_connection_timer.timeout.connect(self.check_websocket_and_detect)
        self.ws_connection_timer.start(2000)  # Check every 2 seconds
        
        # Track if we've done initial detection
        self.initial_detection_done = False
        
        # Call existing init
        super().__init__(websocket)

    
    def __del__(self):
        """Clean up theme manager callback on destruction"""
        try:
            theme_manager.unregister_callback(self._on_theme_changed)
        except Exception:
            pass
    
    def _setup_screen(self):
        """Initialize servo configuration screen"""
        self.setFixedWidth(1180)
        self.servo_config = self.load_config()
        self.active_sweeps = {}
        
        # Maestro state tracking
        self.maestro_channel_counts = {1: 0, 2: 0}
        self.maestro_connected = {1: False, 2: False}
        self.current_maestro = 0  # 0=Maestro1, 1=Maestro2
        self.initialization_complete = False
        
        # Widget tracking for position updates
        self.servo_widgets = {}
        
        # Position update management
        self.position_update_timer = QTimer()
        self.position_update_timer.timeout.connect(self.update_all_positions)
        self.position_update_timer.setInterval(500)
        
        # Position reading state
        self.reading_positions = False
        self.position_read_timeout = QTimer()
        self.position_read_timeout.timeout.connect(self.handle_position_read_timeout)
        self.position_read_timeout.setSingleShot(True)
        
        # Connect Qt signals for thread safety
        self.position_update_signal.connect(self.update_servo_position_display)
        self.status_update_signal.connect(self.update_status_threadsafe)
        
        self.setup_layout()
        
        # Connect to WebSocket for responses
        if self.websocket:
            self.websocket.textMessageReceived.connect(self.handle_websocket_message)
        
        # Initialize after setup complete
        QTimer.singleShot(200, self.safe_initialization)
        
    def setup_layout(self):
        """Setup the complete layout with themed control panel"""
        # Scrollable grid area
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_layout.setContentsMargins(2, 5, 2, 5)
        self.grid_layout.setVerticalSpacing(6)
        self.grid_widget.setLayout(self.grid_layout)
        self._update_grid_widget_style()
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setWidget(self.grid_widget)
        self._update_scroll_area_style(scroll_area)
        
        # Create themed control panel
        control_panel = self._create_control_panel()
        
        # Status label
        self.status_label = QLabel("Initializing...")
        self.status_label.setFont(QFont("Arial", 12))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFixedWidth(1050)
        self._update_status_label_style()
        
        # Main layout assembly
        grid_and_selector_layout = QHBoxLayout()
        grid_and_selector_layout.addSpacing(5)
        grid_and_selector_layout.addWidget(scroll_area, stretch=5)
        grid_and_selector_layout.addWidget(control_panel)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(90, 10, 10, 5)
        status_container = QHBoxLayout()
        status_container.addStretch()
        status_container.addWidget(self.status_label)
        status_container.addStretch()
        layout.addLayout(status_container)
        layout.addLayout(grid_and_selector_layout)
        self.setLayout(layout)

    def _update_grid_widget_style(self):
        """Apply themed styling to grid widget"""
        primary = theme_manager.get("primary_color")
        self.grid_widget.setStyleSheet(f"""
            QWidget {{ 
                border: 1px solid {primary}; 
                border-radius: 12px; 
                background: transparent;
            }}
        """)

    def _update_scroll_area_style(self, scroll_area):
        """Apply themed styling to scroll area"""
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        scroll_area.setStyleSheet(f"""
        QScrollArea {{
            border: none;
            background-color: transparent;
        }}
        QScrollBar:vertical {{
            background: #2d2d2d;
            width: 12px;
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical {{
            background: {primary};
            border-radius: 6px;
            min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {primary_light};
        }}
        """)

    def _update_status_label_style(self):
        """Update status label with theme colors"""
        primary = theme_manager.get("primary_color")
        self.status_label.setStyleSheet(f"color: {primary}; padding: 3px;")

    def _create_control_panel(self):
        """Create the themed servo control panel"""
        # Main panel with theme styling
        control_panel = QWidget()
        control_panel.setFixedWidth(240)
        self._update_control_panel_style(control_panel)
        
        panel_layout = QVBoxLayout()
        panel_layout.setContentsMargins(15, 5, 15, 15)
        panel_layout.setSpacing(15)
        
        # Header with theme styling
        self.header = QLabel("SERVO CONTROL")
        self.header.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_header_style()
        panel_layout.addWidget(self.header)
        
        # Maestro selection with theme buttons
        maestro_layout = self._create_maestro_section()
        panel_layout.addLayout(maestro_layout)
        panel_layout.addSpacing(20)
        
        # Operations section
        operations_section = self._create_operations_section()
        panel_layout.addWidget(operations_section)
        
        panel_layout.addStretch()
        control_panel.setLayout(panel_layout)
        self.control_panel = control_panel
        return control_panel

    def _update_control_panel_style(self, panel):
        """Apply themed styling to control panel"""
        primary = theme_manager.get("primary_color")
        panel_bg = theme_manager.get("panel_bg")
        panel.setStyleSheet(f"""
            QWidget {{
                background-color: {panel_bg};
                border: 2px solid {primary};
                border-radius: 12px;
                color: white;
            }}
        """)

    def _update_header_style(self):
        """Apply themed styling to header"""
        primary = theme_manager.get("primary_color")
        panel_bg = theme_manager.get("panel_bg")
        self.header.setStyleSheet(f"""
            QLabel {{
                border: none;
                background-color: rgba(0, 0, 0, 0.9);
                color: {primary};
                padding: 8px;
                border-radius: 6px;
                margin-bottom: 5px;
            }}
        """)

    def _create_maestro_section(self):
        """Create themed Maestro selection buttons"""
        maestro_layout = QVBoxLayout()
        maestro_layout.setSpacing(10)
        
        # Maestro label
        self.maestro_label = QLabel("MAESTRO")
        self.maestro_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self.maestro_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_maestro_label_style()
        maestro_layout.addWidget(self.maestro_label)
        
        # Button container
        button_container = QHBoxLayout()
        button_container.setSpacing(10)
        
        # Create themed M1 and M2 buttons
        self.maestro1_btn = self._create_maestro_button("1", True)
        self.maestro2_btn = self._create_maestro_button("2", False)
        
        # Set up button group
        self.maestro_group = QButtonGroup()
        self.maestro_group.setExclusive(True)
        self.maestro_group.addButton(self.maestro1_btn, 0)
        self.maestro_group.addButton(self.maestro2_btn, 1)
        self.maestro_group.idClicked.connect(self.on_maestro_changed)
        
        button_container.addWidget(self.maestro1_btn)
        button_container.addWidget(self.maestro2_btn)
        maestro_layout.addLayout(button_container)
        return maestro_layout

    def _update_maestro_label_style(self):
        """Apply themed styling to maestro label"""
        primary = theme_manager.get("primary_color")
        self.maestro_label.setStyleSheet(f"color: {primary}; border: none; background: transparent;")

    def _create_maestro_button(self, number: str, is_selected: bool):
        """Create a themed Maestro selection button"""
        btn = QPushButton(f"M{number}")
        btn.setCheckable(True)
        btn.setChecked(is_selected)
        btn.setFixedSize(80, 60)
        btn.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        self._update_maestro_button_style(btn)
        return btn

    def _update_maestro_button_style(self, btn):
        """Apply themed styling to maestro button"""
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        primary_gradient = theme_manager.get("primary_gradient")
        
        btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4a4a4a, stop:1 #2a2a2a);
                border: 2px solid #666;
                border-radius: 8px;
                color: #ccc;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5a5a5a, stop:1 #3a3a3a);
                border: 2px solid {primary};
                color: {primary};
            }}
            QPushButton:checked {{
                background: {primary_gradient};
                border: 2px solid {primary};
                color: black;
                font-weight: bold;
            }}
            QPushButton:checked:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {primary_light}, stop:1 {primary});
                border: 2px solid {primary_light};
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3a3a3a, stop:1 #1a1a1a);
            }}
        """)

    def _create_operations_section(self):
        """Create the operations section with themed styling"""
        self.operations_frame = QWidget()
        self._update_operations_frame_style(self.operations_frame)

        ops_layout = QVBoxLayout()
        ops_layout.setContentsMargins(15, 10, 15, 15)
        ops_layout.setSpacing(8)
        
        # Operations header
        self.ops_header = QLabel("OPERATIONS")
        self.ops_header.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self.ops_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_ops_header_style()
        ops_layout.addWidget(self.ops_header)
        
        # Create operation buttons
        button_configs = [
            ("🔄 REFRESH", self.refresh_current_maestro, "Refresh Maestro connection"),
            ("🏠 SET HOME", self.set_home_positions, "Set current positions as home"),
            ("↩️ GO HOME", self.go_home_positions, "Move all servos to home positions"),
            ("📖 READ POS", self.read_all_positions_now, "Read current servo positions"),
            ("⚡ TOGGLE LIVE", self.toggle_all_live_checkboxes, "Toggle all live updates")
        ]
        
        self.operation_buttons = []
        for text, callback, tooltip in button_configs:
            btn = QPushButton(text)
            btn.setFont(QFont("Arial", 14))  
            btn.setToolTip(tooltip)
            btn.clicked.connect(callback)
            self._update_operation_button_style(btn)
            ops_layout.addWidget(btn)
            self.operation_buttons.append(btn)
        
        self.operations_frame.setLayout(ops_layout)
        return self.operations_frame

    def _update_operations_frame_style(self, frame):
        """Apply themed styling to operations frame"""
        primary = theme_manager.get("primary_color")
        frame.setStyleSheet(f"""
            QWidget {{
                border: 1px solid {primary};
                border-radius: 8px;
                background-color: rgba(0, 0, 0, 0.3);
            }}
        """)

    def _update_ops_header_style(self):
        """Apply themed styling to operations header"""
        primary = theme_manager.get("primary_color")
        self.ops_header.setStyleSheet(f"color: {primary}; border: none; margin-bottom: 5px; background: transparent;")

    def _update_operation_button_style(self, btn):
        """Apply themed styling to operation button"""
        primary = theme_manager.get("primary_color")
        btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4a4a4a, stop:1 #2a2a2a);
                color: white;
                border: 1px solid #666;
                border-radius: 6px;
                padding: 6px;
                text-align: center;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5a5a5a, stop:1 #3a3a3a);
                border-color: {primary};
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3a3a3a, stop:1 #1a1a1a);
                border-color: {primary};
            }}
        """)

    def _on_theme_changed(self):
        """Handle theme change by updating all styled components"""
        try:
            # Update main panel styling
            if hasattr(self, 'main_frame'):
                self._update_control_panel_style(self.main_frame)

            if hasattr(self, 'control_panel'):
                self._update_control_panel_style(self.control_panel)

            # Update grid widget
            self._update_grid_widget_style()
            
            # Update status label
            self._update_status_label_style()
            
            # Update header
            if hasattr(self, 'header'):
                self._update_header_style()
            
            # Update maestro section
            if hasattr(self, 'maestro_label'):
                self._update_maestro_label_style()
            if hasattr(self, 'maestro1_btn'):
                self._update_maestro_button_style(self.maestro1_btn)
            if hasattr(self, 'maestro2_btn'):
                self._update_maestro_button_style(self.maestro2_btn)
            
            # Update operations section
            if hasattr(self, 'ops_header'):
                self._update_ops_header_style()
            if hasattr(self, 'operation_buttons'):
                for btn in self.operation_buttons:
                    self._update_operation_button_style(btn)
            if hasattr(self, 'operations_frame'):
                self._update_operations_frame_style(self.operations_frame)
       
            
            # Update scroll area if it exists
            scroll_areas = self.findChildren(QScrollArea)
            for scroll_area in scroll_areas:
                self._update_scroll_area_style(scroll_area)
            
            # Update all servo widgets in grid
            self._update_servo_widgets_theme()
            
            self.logger.info(f"Servo screen updated for theme: {theme_manager.get_theme_name()}")
        except Exception as e:
            self.logger.warning(f"Failed to apply theme changes: {e}")

    def _update_servo_widgets_theme(self):
        """Update theme for all servo control widgets"""
        primary = theme_manager.get("primary_color")
        
        # Update all input widgets
        for edit in self.findChildren(QLineEdit):
            self._update_input_style(edit)
        for spin in self.findChildren(QSpinBox):
            self._update_spinbox_style(spin)
        for checkbox in self.findChildren(QCheckBox):
            self._update_checkbox_style(checkbox)
        for label in self.findChildren(QLabel):
            if label not in [self.status_label, self.header, self.maestro_label, self.ops_header]:
                label.setStyleSheet("color: white; background: transparent;")
        
        # Update play buttons
        play_buttons = [widgets[2] for widgets in self.servo_widgets.values() if len(widgets) > 2]
        for btn in play_buttons:
            self._update_play_button_style(btn)

    def _update_input_style(self, input_field):
        """Apply themed styling to input field"""
        primary = theme_manager.get("primary_color")
        input_field.setStyleSheet(f"""
        QLineEdit {{
            background-color: #2d2d2d;
            border: 1px solid #555;
            border-radius: 4px;
            padding: 6px;
            color: white;
        }}
        QLineEdit:focus {{ 
            border-color: {primary}; 
            background-color: #333333;
        }}
        """)

    def _update_spinbox_style(self, spinbox):
        """Apply themed styling to spinbox"""
        primary = theme_manager.get("primary_color")
        spinbox.setStyleSheet(f"""
        QSpinBox {{
            background-color: #2d2d2d;
            border: 1px solid #555;
            border-radius: 4px;
            padding: 6px;
            color: white;
        }}
        QSpinBox:focus {{ 
            border-color: {primary}; 
            background-color: #333333;
        }}
        """)

    def _update_checkbox_style(self, checkbox):
        """Apply themed styling to checkbox"""
        green = theme_manager.get("green")
        checkbox.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
            }}
            QCheckBox::indicator:unchecked {{
                background-color: #333;
                border: 1px solid #666;
                border-radius: 2px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {green};
                border: 1px solid {green};
                border-radius: 2px;
            }}
        """)

    def _update_play_button_style(self, btn):
        """Apply themed styling to play button"""
        red = theme_manager.get("red")
        btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background-color: #444;
                color: white;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: #555;
            }}
            QPushButton:pressed {{
                background-color: #333;
            }}
            QPushButton:checked {{
                background-color: {red};
                color: white;
            }}
        """)

    def check_websocket_and_detect(self):
        """Check if WebSocket is connected and trigger detection if needed"""
        if self.websocket and self.websocket.is_connected():
            if not self.initial_detection_done:
                self.logger.info("WebSocket connected - triggering automatic maestro detection")
                self.detect_all_maestros()
                self.initial_detection_done = True
                # Stop the timer once we've done initial detection
                self.ws_connection_timer.stop()
        else:
            # Reset detection flag if WebSocket disconnects
            self.initial_detection_done = False

    def detect_all_maestros(self):
        """Detect both Maestro 1 and 2 automatically"""
        if not self.websocket or not self.websocket.is_connected():
            self.update_status("Cannot detect maestros: WebSocket not connected", error=True)
            return
        
        self.update_status("Auto-detecting maestro controllers...")
        
        # Request info for both maestros
        for maestro_num in [1, 2]:
            success = self.send_websocket_message("get_maestro_info", maestro=maestro_num)
            if success:
                self.logger.info(f"Requested auto-detection for Maestro {maestro_num}")
            else:
                self.logger.warning(f"Failed to request info for Maestro {maestro_num}")

    def showEvent(self, event):
        """Override showEvent to trigger detection when screen becomes visible"""
        super().showEvent(event)
        
        # If WebSocket is connected but we haven't detected, do it now
        if (self.websocket and 
            self.websocket.is_connected() and 
            not self.initial_detection_done):
            
            self.logger.info("Servo screen shown - triggering maestro detection")
            QTimer.singleShot(500, self.detect_all_maestros)

    def safe_initialization(self):
        """Safe initialization that queries the selected Maestro"""
        try:
            self.update_status("Initializing servo configuration...")
            
            # Check if we already have info for current Maestro
            maestro_num = self.current_maestro + 1
            if (self.maestro_connected.get(maestro_num, False) and 
                self.maestro_channel_counts.get(maestro_num, 0) > 0):
                self.update_status(f"Using cached info for Maestro {maestro_num}")
                self.update_grid()
                QTimer.singleShot(300, self.read_all_positions_now)
            else:
                self.request_current_maestro_info()
            
        except Exception as e:
            self.logger.error(f"Initialization error: {e}")
            self.update_status(f"Initialization failed: {str(e)}", error=True)
    
    def request_current_maestro_info(self):
        """Enhanced maestro info request with retry logic"""
        maestro_num = self.current_maestro + 1
        self.update_status(f"Detecting Maestro {maestro_num} controller...")
        
        if not self.websocket or not self.websocket.is_connected():
            self.update_status("Cannot detect maestro: WebSocket not connected", error=True)
            # Restart the connection monitoring timer
            if not self.ws_connection_timer.isActive():
                self.ws_connection_timer.start(2000)
            return
        
        success = self.send_websocket_message("get_maestro_info", maestro=maestro_num)
        if success:
            self.logger.info(f"Requested info for Maestro {maestro_num}")
            # Set a timeout to retry if no response
            QTimer.singleShot(5000, self.check_detection_timeout)
        else:
            self.update_status("Failed to request Maestro info: WebSocket error", error=True)

        
    # Enhanced refresh method
    def refresh_current_maestro(self):
        """Enhanced refresh with better status feedback"""
        # Stop any active operations
        self.stop_all_sweeps()
        if hasattr(self, 'position_update_timer') and self.position_update_timer.isActive():
            self.position_update_timer.stop()
        
        # Clear current state
        maestro_num = self.current_maestro + 1
        self.maestro_connected[maestro_num] = False
        self.maestro_channel_counts[maestro_num] = 0
        
        # Clear the grid immediately
        self.clear_grid()
        
        # Request fresh info with better feedback
        self.update_status(f"Refreshing Maestro {maestro_num}...")
        self.request_current_maestro_info()
        self.reload_servo_config()

    def update_maestro_selector_status(self):
        """Update the maestro selector to show which ones are detected"""
        pass

        
    @error_boundary
    def handle_websocket_message(self, message: str):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "maestro_info":
                maestro_num = data.get("maestro")
                channels = data.get("channels", 0)
                connected = data.get("connected", False)
                
                if maestro_num in [1, 2]:
                    old_count = self.maestro_channel_counts.get(maestro_num, 0)
                    self.maestro_channel_counts[maestro_num] = channels
                    self.maestro_connected[maestro_num] = connected
                    self.logger.info(f"Maestro {maestro_num}: {channels} channels, connected: {connected}")
                    
                    if connected:
                        self.update_status(f"Maestro {maestro_num}: {channels} channels detected")
                        # Only update grid if this is the currently selected Maestro
                        if (maestro_num == self.current_maestro + 1 and 
                            channels != old_count and channels > 0):
                            self.logger.info(f"Channel count changed for current maestro: {old_count} -> {channels}")
                            self.update_grid()
                            QTimer.singleShot(500, self.read_all_positions_now)
                        # Only update grid if this is the currently selected Maestro (existing logic)
                        elif maestro_num == self.current_maestro + 1:
                            self.update_grid()
                            QTimer.singleShot(500, self.read_all_positions_now)

                        self.update_maestro_selector_status()
                    else:
                        self.update_status(f"Maestro {maestro_num}: Not connected", error=True)
            
            elif msg_type == "servo_position":
                channel_key = data.get("channel")
                position = data.get("position")
                
                if channel_key and position is not None:
                    self.position_update_signal.emit(channel_key, position)
                    
                    # Notify active sweeps
                    if channel_key in self.active_sweeps:
                        try:
                            self.active_sweeps[channel_key].position_reached(position)
                        except Exception as e:
                            self.logger.error(f"Error updating sweep position for {channel_key}: {e}")
                            if channel_key in self.active_sweeps:
                                self.active_sweeps[channel_key].stop()
                                del self.active_sweeps[channel_key]
            
            elif msg_type == "all_servo_positions":
                maestro_num = data.get("maestro")
                positions = data.get("positions", {})
                
                # Only process if this is for the currently selected Maestro
                if maestro_num == self.current_maestro + 1:
                    self.logger.info(f"Received {len(positions)} positions for Maestro {maestro_num}")
                    
                    self.reading_positions = False
                    self.position_read_timeout.stop()
                    
                    # Update all positions using Qt signals
                    for channel, position in positions.items():
                        channel_key = f"m{maestro_num}_ch{channel}"
                        if position is not None:
                            self.position_update_signal.emit(channel_key, position)
                    
                    if len(positions) > 0:
                        self.update_status(f"Read {len(positions)} positions from Maestro {maestro_num}")
                    else:
                        self.update_status(f"No positions received from Maestro {maestro_num}", warning=True)
                        
        except Exception as e:
            self.logger.error(f"Error handling WebSocket message: {e}")
    
    def update_servo_position_display(self, channel_key: str, position: int):
        """Thread-safe method to update servo position display"""
        if channel_key in self.servo_widgets:
            widgets = self.servo_widgets[channel_key]
            slider = widgets[0]
            pos_label = widgets[1]
            
            # Update slider position without triggering servo movement
            slider.blockSignals(True)
            slider.setValue(position)
            slider.blockSignals(False)
            
            # Update position label with theme color
            green = theme_manager.get("green")
            pos_label.setText(f"V: {position}")
            pos_label.setStyleSheet(f"color: {green}; background: transparent;")
            
            self.logger.debug(f"Updated display: {channel_key} = {position}")

    def check_detection_timeout(self):
        """Check if detection timed out and retry if needed"""
        maestro_num = self.current_maestro + 1
        
        if not self.maestro_connected.get(maestro_num, False):
            self.logger.warning(f"Maestro {maestro_num} detection timed out, retrying...")
            self.request_current_maestro_info()
    
    def update_status_threadsafe(self, message: str, error: bool = False, warning: bool = False):
        """Thread-safe status update"""
        self.status_label.setText(message)
        
        if error:
            red = theme_manager.get("red")
            self.status_label.setStyleSheet(f"color: {red}; padding: 3px;")
        elif warning:
            primary = theme_manager.get("primary_color")
            self.status_label.setStyleSheet(f"color: {primary}; padding: 3px;")
        else:
            green = theme_manager.get("green")
            self.status_label.setStyleSheet(f"color: {green}; padding: 3px;")
        
        self.logger.info(f"Status: {message}")
    
    def update_status(self, message: str, error: bool = False, warning: bool = False):
        """Update status using Qt signal for thread safety"""
        self.status_update_signal.emit(message, error, warning)
    
    def on_maestro_changed(self, maestro_index: int):
        """Handle maestro selection change with proper cleanup"""
        if maestro_index == self.current_maestro:
            return
        
        # Stop current operations
        self.stop_all_sweeps()
        if hasattr(self, 'position_update_timer') and self.position_update_timer.isActive():
            self.position_update_timer.stop()
        
        # Update selection
        old_maestro = self.current_maestro
        self.current_maestro = maestro_index
        
        # Clear old grid
        self.clear_grid()
        
        maestro_num = maestro_index + 1
        
        # Check if we already have info for this Maestro
        if self.maestro_connected.get(maestro_num, False):
            channels = self.maestro_channel_counts.get(maestro_num, 0)
            self.update_status(f"Switched to Maestro {maestro_num}: {channels} channels")
            self.update_grid()
            QTimer.singleShot(200, self.read_all_positions_now)
        else:
            self.update_status(f"Loading Maestro {maestro_num}...")
            self.request_current_maestro_info()
        
        self.logger.info(f"Switched from Maestro {old_maestro + 1} to Maestro {maestro_num}")
    
    def clear_grid(self):
        """Clear the current grid and widget tracking"""
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        
        self.servo_widgets.clear()
    
    def update_grid(self):
        """Build servo control grid for currently selected Maestro only"""
        maestro_num = self.current_maestro + 1
        channel_count = self.maestro_channel_counts.get(maestro_num, 0)
        
        if channel_count == 0:
            self.update_status(f"Maestro {maestro_num} not available", error=True)
            return
        
        self.logger.info(f"Building grid for Maestro {maestro_num} with {channel_count} channels")
        
        # Stop any active updates while rebuilding
        if hasattr(self, 'position_update_timer') and self.position_update_timer.isActive():
            self.position_update_timer.stop()
        
        self.clear_grid()
        
        font = QFont("Arial", 14)
        
        # Create grid for detected channels
        for i in range(channel_count):
            channel_key = f"m{maestro_num}_ch{i}"
            config = self.servo_config.get(channel_key, {})
            row = i
            
            # Channel number
            label = QLabel(f"Ch{i}")
            label.setFont(font)
            label.setFixedWidth(35)
            label.setStyleSheet("color: white; background: transparent;")
            self.grid_layout.addWidget(label, row, 0)
            
            # Name edit
            name_edit = QLineEdit(config.get("name", ""))
            name_edit.setFont(QFont("Arial", 16))
            name_edit.setMaxLength(25)
            name_edit.setFixedWidth(140)
            name_edit.setPlaceholderText("Servo Name")
            name_edit.textChanged.connect(lambda text, k=channel_key: self.update_config(k, "name", text))
            self._update_input_style(name_edit)
            self.grid_layout.addWidget(name_edit, row, 1)
            
            # Slider for position control with custom styling and home indicator
            slider = HomePositionSlider(Qt.Orientation.Horizontal)
            min_val = config.get("min", 992)
            max_val = config.get("max", 2000)
            home_pos = config.get("home")
            slider.setMinimum(min_val)
            slider.setMaximum(max_val)
            slider.setValue((min_val + max_val) // 2)
            slider.setFixedWidth(140)
            slider.setMinimumHeight(24)
            
            # Set home position indicator if available
            if home_pos is not None:
                slider.set_home_position(home_pos)
            self.grid_layout.addWidget(slider, row, 2)
            
            # Min/Max value controls
            min_spin = QSpinBox()
            min_spin.setFont(QFont("Arial", 16))
            min_spin.setRange(0, 2500)
            min_spin.setValue(min_val)
            min_spin.setFixedWidth(75)
            min_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "min", val))
            min_spin.valueChanged.connect(lambda val, s=slider: s.setMinimum(val))
            self._update_spinbox_style(min_spin)
            self.grid_layout.addWidget(min_spin, row, 3)
            
            max_spin = QSpinBox()
            max_spin.setFont(QFont("Arial", 16))
            max_spin.setRange(0, 2500)
            max_spin.setValue(max_val)
            max_spin.setFixedWidth(75)
            max_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "max", val))
            max_spin.valueChanged.connect(lambda val, s=slider: s.setMaximum(val))
            self._update_spinbox_style(max_spin)
            self.grid_layout.addWidget(max_spin, row, 4)
            
            # Speed/Acceleration controls
            speed_spin = QSpinBox()
            speed_spin.setFont(QFont("Arial", 16))
            speed_spin.setRange(0, 100)
            speed_spin.setValue(config.get("speed", 0))
            speed_spin.setFixedWidth(60)
            speed_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "speed", val))
            self._update_spinbox_style(speed_spin)
            self.grid_layout.addWidget(speed_spin, row, 5)
            
            accel_spin = QSpinBox()
            accel_spin.setFont(QFont("Arial", 16))
            accel_spin.setRange(0, 100)
            accel_spin.setValue(config.get("accel", 0))
            accel_spin.setFixedWidth(60)
            accel_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "accel", val))
            self._update_spinbox_style(accel_spin)
            self.grid_layout.addWidget(accel_spin, row, 6)
            
            # Position label
            pos_label = QLabel("---")
            pos_label.setFont(QFont("Arial", 16))
            pos_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pos_label.setFixedWidth(60)
            primary = theme_manager.get("primary_color")
            pos_label.setStyleSheet(f"color: {primary}; background: transparent;")
            self.grid_layout.addWidget(pos_label, row, 7)
            
            # Live update checkbox
            live_checkbox = QCheckBox()
            live_checkbox.setChecked(False)
            live_checkbox.setToolTip("Enable live servo updates")
            live_checkbox.setFixedSize(20, 20)
            self._update_checkbox_style(live_checkbox)
            self.grid_layout.addWidget(live_checkbox, row, 8)
            
            # Play/sweep button with themed styling
            play_btn = QPushButton("▶️")
            play_btn.setFont(QFont("Arial", 12))
            play_btn.setCheckable(True)
            play_btn.setFixedSize(30, 30)
            self._update_play_button_style(play_btn)
            play_btn.clicked.connect(
                lambda checked, k=channel_key, p=pos_label, b=play_btn,
                min_spin=min_spin, max_spin=max_spin, speed_spin=speed_spin:
                self.toggle_sweep_minmax(k, p, b, min_spin.value(), max_spin.value(), speed_spin.value())
            )
            self.grid_layout.addWidget(play_btn, row, 9)
            
            # Connect slider to servo movement
            slider.valueChanged.connect(
                lambda val, k=channel_key, p=pos_label, cb=live_checkbox:
                self.update_servo_position_conditionally(k, p, val, cb)
            )
            
            # Track widgets for position updates
            self.servo_widgets[channel_key] = (slider, pos_label, play_btn, live_checkbox, name_edit)
        
        self.update_status(f"Maestro {maestro_num}: {channel_count} channels loaded")
    
    def update_all_positions(self):
        """Update all servo positions for current Maestro"""
        maestro_num = self.current_maestro + 1
        
        if not self.maestro_connected.get(maestro_num, False) or not self.servo_widgets:
            return
        
        success = self.send_websocket_message("get_all_servo_positions", maestro=maestro_num)
        if success:
            self.logger.debug(f"Auto-updating positions for Maestro {maestro_num}")
    
    def read_all_positions_now(self):
        """Manually read all servo positions for current Maestro"""
        if self.reading_positions:
            self.logger.debug("Already reading positions, skipping...")
            return
        
        maestro_num = self.current_maestro + 1
        
        if not self.maestro_connected.get(maestro_num, False):
            self.update_status(f"Maestro {maestro_num} not connected", error=True)
            return
        
        self.reading_positions = True
        self.position_read_timeout.start(3000)
        
        success = self.send_websocket_message("get_all_servo_positions", maestro=maestro_num)
        if success:
            self.update_status(f"Reading positions from Maestro {maestro_num}...")
            self.logger.info(f"Requested all positions from Maestro {maestro_num}")
        else:
            self.reading_positions = False
            self.position_read_timeout.stop()
            self.update_status("Failed to send position request: WebSocket not connected", error=True)
    
    def handle_position_read_timeout(self):
        """Handle timeout when reading positions"""
        self.reading_positions = False
        maestro_num = self.current_maestro + 1
        
        self.logger.warning(f"Timeout reading positions from Maestro {maestro_num}")
        self.update_status(f"Maestro {maestro_num} not responding - check connection", error=True)
        
        # Set all sliders to center position as fallback
        primary = theme_manager.get("primary_color")
        for channel_key, widgets in self.servo_widgets.items():
            if channel_key.startswith(f"m{maestro_num}_"):
                slider = widgets[0]
                pos_label = widgets[1]
                
                center = (slider.minimum() + slider.maximum()) // 2
                slider.blockSignals(True)
                slider.setValue(center)
                slider.blockSignals(False)
                
                pos_label.setText(f"V: {center}")
                pos_label.setStyleSheet(f"color: {primary}; background: transparent;")
    
    def update_servo_position_conditionally(self, channel_key: str, pos_label: QLabel, 
                                           value: int, live_checkbox: QCheckBox):
        """Update servo position only if live checkbox is checked"""
        pos_label.setText(f"V: {value}")
        
        if live_checkbox.isChecked():
            self.update_servo_position(channel_key, pos_label, value)
            red = theme_manager.get("red")
            pos_label.setStyleSheet(f"color: {red}; background: transparent;")
        else:
            pos_label.setStyleSheet("color: #AAAAAA; background: transparent;")
    
    def update_servo_position(self, channel_key: str, pos_label: QLabel, value: int):
        """Send servo position command with configuration"""
        config = self.servo_config.get(channel_key, {})
        speed = config.get("speed", 0)
        accel = config.get("accel", 0)
        
        # Apply speed and acceleration settings
        self.send_websocket_message("servo_speed", channel=channel_key, speed=speed)
        self.send_websocket_message("servo_acceleration", channel=channel_key, acceleration=accel)
        
        # Send position command
        self.send_websocket_message("servo", channel=channel_key, pos=value)
        
        self.logger.debug(f"Servo command: {channel_key} -> {value} (speed: {speed}, accel: {accel})")
        
    def set_home_positions(self):
        """Set current slider positions as home positions for all servos"""
        maestro_num = self.current_maestro + 1
        
        if not self.maestro_connected.get(maestro_num, False):
            self.update_status(f"Maestro {maestro_num} not connected", error=True)
            return
        
        # Use current slider positions instead of reading from servos
        home_count = 0
        home_positions = {}
        
        for channel_key, widgets in self.servo_widgets.items():
            if channel_key.startswith(f"m{maestro_num}_"):
                slider = widgets[0]  # Get slider widget
                current_pos = slider.value()  # Get current slider position
                
                # Save to config
                if channel_key not in self.servo_config:
                    self.servo_config[channel_key] = {}
                self.servo_config[channel_key]["home"] = current_pos
                
                # Update visual indicator
                slider.set_home_position(current_pos)
                
                # Prepare for backend
                channel_num = int(channel_key.split("_ch")[1])
                home_positions[channel_num] = current_pos
                
                home_count += 1
        
        # Save and notify
        success = config_manager.save_config("resources/configs/servo_config.json", self.servo_config)
        if success:
            self.update_status(f"Set {home_count} home positions")
            self.send_websocket_message("servo_home_positions", 
                                    maestro=maestro_num, 
                                    home_positions=home_positions)
    
    def go_home_positions(self):
        """Move all servos to their home positions"""
        maestro_num = self.current_maestro + 1
        
        if not self.maestro_connected.get(maestro_num, False):
            self.update_status(f"Maestro {maestro_num} not connected", error=True)
            return
        
        home_count = 0
        for channel_key in self.servo_widgets.keys():
            if channel_key.startswith(f"m{maestro_num}_"):
                config = self.servo_config.get(channel_key, {})
                home_pos = config.get("home")
                
                if home_pos is not None:
                    # Apply configured speed and acceleration first
                    speed = config.get("speed", 0)
                    accel = config.get("accel", 0)

                    self.send_websocket_message("servo_speed", channel=channel_key, speed=speed)
                    self.send_websocket_message("servo_acceleration", channel=channel_key, acceleration=accel)
                    self.send_websocket_message("servo", channel=channel_key, pos=home_pos)
                    
                    # Update slider to home position
                    widgets = self.servo_widgets[channel_key]
                    slider = widgets[0]
                    pos_label = widgets[1]
                    
                    slider.blockSignals(True)
                    slider.setValue(home_pos)
                    slider.blockSignals(False)
                    
                    pos_label.setText(f"H: {home_pos}")
                    primary = theme_manager.get("primary_color")  # Gold equivalent for home
                    pos_label.setStyleSheet(f"color: {primary}; background: transparent;")
                    
                    home_count += 1
        
        if home_count > 0:
            self.update_status(f"Moving {home_count} servos to home positions")
            self.logger.info(f"Sent {home_count} servos to home positions")
            
            # Send home positions to backend
            self.send_websocket_message("servo_home_positions", 
                                       maestro=maestro_num, 
                                       home_positions=self.get_maestro_home_positions(maestro_num))
        else:
            self.update_status("No home positions set", warning=True)
    
    def get_maestro_home_positions(self, maestro_num: int) -> dict:
        """Get home positions for specific maestro"""
        home_positions = {}
        for channel_key, config in self.servo_config.items():
            if channel_key.startswith(f"m{maestro_num}_") and "home" in config:
                channel = int(channel_key.split("_ch")[1])
                home_positions[channel] = config["home"]
        return home_positions
    
    def toggle_sweep_minmax(self, channel_key: str, pos_label: QLabel, button: QPushButton, 
                           min_val: int, max_val: int, speed: int):
        """Toggle min/max sweep for a servo channel"""
        if channel_key in self.active_sweeps:
            # Stop existing sweep
            self.active_sweeps[channel_key].stop()
            del self.active_sweeps[channel_key]
            button.setText("▶️")
            button.setChecked(False)
            self.logger.info(f"Stopped sweep for {channel_key}")
            return
        
        # Get configured values
        config = self.servo_config.get(channel_key, {})
        actual_min = config.get("min", 992)
        actual_max = config.get("max", 2000) 
        actual_speed = config.get("speed", speed)
        
        self.logger.info(f"Starting sweep for {channel_key}: min={actual_min}, max={actual_max}, speed={actual_speed}")
        
        # Create new sweep
        sweep = MinMaxSweep(self, channel_key, pos_label, button, actual_min, actual_max, actual_speed)
        self.active_sweeps[channel_key] = sweep
        button.setText("⏸️")
        self.logger.info(f"Started sweep for {channel_key}")
    
    def toggle_all_live_checkboxes(self):
        """Toggle all live update checkboxes"""
        any_checked = any(widgets[3].isChecked() for widgets in self.servo_widgets.values() if len(widgets) > 3)
        
        new_state = not any_checked
        for widgets in self.servo_widgets.values():
            if len(widgets) > 3:
                widgets[3].setChecked(new_state)
        
        status = "enabled" if new_state else "disabled"
        self.update_status(f"All live updates {status}")
        self.logger.info(f"Toggled all live checkboxes to: {new_state}")
    
    def stop_all_sweeps(self):
        """Stop any active sweeps"""
        for channel_key, sweep in list(self.active_sweeps.items()):
            sweep.stop()
        self.active_sweeps.clear()
        self.logger.info("All sweeps stopped")
    
    def stop_all_operations(self):
        """Stop all servo operations for cleanup"""
        self.stop_all_sweeps()
        if hasattr(self, 'position_update_timer') and self.position_update_timer.isActive():
            self.position_update_timer.stop()
    
    @error_boundary
    def load_config(self) -> dict:
        """Load servo configuration from file"""
        return config_manager.get_config("resources/configs/servo_config.json")
    
    @error_boundary
    def save_config(self):
        """Save servo configuration to file"""
        success = config_manager.save_config("resources/configs/servo_config.json", self.servo_config)
        if success:
            self.logger.info("Servo configuration saved")
            
            # Send updated config to backend
            self.send_websocket_message("servo_config_update", config=self.servo_config)
        else:
            self.logger.error("Failed to save servo configuration")
    
    @error_boundary
    def reload_servo_config(self):
        """Reload servo configuration and update grid"""
        config_manager.clear_cache()
        self.servo_config = config_manager.get_config("resources/configs/servo_config.json")
        if hasattr(self, 'grid_layout'):
            self.update_grid()
        self.logger.info("Servo config reloaded")
    
    def update_config(self, key: str, field: str, value):
        """Update configuration for a specific servo channel"""
        if key not in self.servo_config:
            self.servo_config[key] = {}
        self.servo_config[key][field] = value
        
        # Send specific websocket messages for speed and acceleration
        if field == "speed":
            self.send_websocket_message("servo_speed", channel=key, speed=value)
            self.logger.debug(f"Sent servo_speed: {key} = {value}")
        elif field == "accel":
            self.send_websocket_message("servo_acceleration", channel=key, acceleration=value)
            self.logger.debug(f"Sent servo_acceleration: {key} = {value}")
        
        self.save_config()
    
    def cleanup(self):
        """Enhanced cleanup to stop timers"""
        self.stop_all_operations()
        
        # Stop the WebSocket monitoring timer
        if hasattr(self, 'ws_connection_timer'):
            self.ws_connection_timer.stop()
        
        self.logger.info("Servo screen cleanup completed")


class MinMaxSweep:
    """Min/Max sweep controller for automated servo testing"""
    
    def __init__(self, parent_screen, channel_key: str, label: QLabel, btn: QPushButton, 
                 minv: int, maxv: int, speedv: int):
        self.logger = parent_screen.logger
        self.parent_screen = parent_screen
        self.channel_key = channel_key
        self.label = label
        self.btn = btn
        self.min_val = minv
        self.max_val = maxv
        self.speed = speedv
        
        # State tracking
        self.current_target = None
        self.going_to_max = True
        self.position_tolerance = 1
        self.check_interval = 100
        self.hold_delay = 1000
        
        # Timers
        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.check_position)
        
        self.hold_timer = QTimer()
        self.hold_timer.setSingleShot(True)
        self.hold_timer.timeout.connect(self.continue_after_hold)
        
        self.start_sweep()
        self.logger.info(f"Starting min/max sweep on {channel_key}: {minv}->{maxv}, speed={speedv}")
    
    def start_sweep(self):
        """Start the sweep by configuring servo and moving to first target"""
        # Apply speed setting
        if self.speed >= 0:
            self.parent_screen.send_websocket_message("servo_speed", channel=self.channel_key, speed=self.speed)
        
        # Apply acceleration from config
        config = self.parent_screen.servo_config.get(self.channel_key, {})
        accel = config.get("accel", 0)
        if accel >= 0:
            self.parent_screen.send_websocket_message("servo_acceleration", channel=self.channel_key, acceleration=accel)
        
        # Move to first target (max)
        self.move_to_next_target()
        
        # Start position checking
        self.check_timer.start(self.check_interval)
    
    def move_to_next_target(self):
        """Move to the next target position"""
        if self.going_to_max:
            self.current_target = self.max_val
            self.logger.debug(f"{self.channel_key} -> MAX ({self.max_val})")
        else:
            self.current_target = self.min_val
            self.logger.debug(f"{self.channel_key} -> MIN ({self.min_val})")
        
        # Send move command
        self.parent_screen.send_websocket_message("servo", channel=self.channel_key, pos=self.current_target)
        
        # Update UI with theme color
        self.label.setText(f"->{self.current_target}")
        primary = theme_manager.get("primary_color")
        self.label.setStyleSheet(f"color: {primary}; background: transparent;")
    
    def check_position(self):
        """Request current position for sweep validation"""
        self.parent_screen.send_websocket_message("get_servo_position", channel=self.channel_key)
    
    def position_reached(self, actual_position: int):
        """Called when position update received"""
        if self.current_target is None:
            return
        
        if actual_position == self.current_target:
            self.logger.debug(f"{self.channel_key} reached {self.current_target} precisely")
            
            # Update UI to show reached
            self.label.setText(f"@{actual_position}")
            green = theme_manager.get("green")
            self.label.setStyleSheet(f"color: {green}; background: transparent;")
            
            # Stop position checking during hold delay
            self.check_timer.stop()
            
            # Start hold timer before switching direction
            self.hold_timer.start(self.hold_delay)
            
        else:
            # Still moving, update display
            self.label.setText(f"V:{actual_position}")
            primary_light = theme_manager.get("primary_light")
            self.label.setStyleSheet(f"color: {primary_light}; background: transparent;")
            self.logger.debug(f"{self.channel_key}: {actual_position}/{self.current_target}")
    
    def continue_after_hold(self):
        """Continue sweep after hold delay"""
        # Switch direction
        self.going_to_max = not self.going_to_max
        
        # Move to next target
        self.move_to_next_target()
        
        # Resume position checking
        self.check_timer.start(self.check_interval)
    
    def stop(self):
        """Stop the sweep and return to center"""
        self.check_timer.stop()
        self.hold_timer.stop()
        
        # Return to center position
        center_pos = (self.min_val + self.max_val) // 2
        self.parent_screen.send_websocket_message("servo", channel=self.channel_key, pos=center_pos)
        
        # Update UI
        self.label.setText(f"C:{center_pos}")
        self.label.setStyleSheet("color: #AAAAAA; background: transparent;")
        self.btn.setText("▶️")
        self.btn.setChecked(False)
        
        self.logger.info(f"Min/Max sweep stopped: {self.channel_key} returned to center ({center_pos})")