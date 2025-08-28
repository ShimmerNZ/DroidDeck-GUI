"""
WALL-E Control System - Servo Configuration Screen
Real-time servo control and configuration interface
"""

import json
import os
from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, 
                            QScrollArea, QWidget, QFrame, QLineEdit, QSpinBox, QSlider,
                            QCheckBox, QButtonGroup)
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal

from widgets.base_screen import BaseScreen
from core.config_manager import config_manager
from core.utils import error_boundary


class ServoConfigScreen(BaseScreen):
    """Real-time servo control and configuration interface"""
    
    # Qt signals for thread-safe communication
    position_update_signal = pyqtSignal(str, int)
    status_update_signal = pyqtSignal(str, bool, bool)
    
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
        self.auto_update_positions = False
        
        # Position reading state
        self.reading_positions = False
        self.position_read_timeout = QTimer()
        self.position_read_timeout.timeout.connect(self.handle_position_read_timeout)
        self.position_read_timeout.setSingleShot(True)
        
        # Setup UI components
        self.setup_maestro_selectors()
        self.setup_control_buttons()
        self.setup_position_controls()
        
        # Connect Qt signals for thread safety
        self.position_update_signal.connect(self.update_servo_position_display)
        self.status_update_signal.connect(self.update_status_threadsafe)
        
        self.setup_layout()
        
        # Connect to WebSocket for responses
        if self.websocket:
            self.websocket.textMessageReceived.connect(self.handle_websocket_message)
        
        # Initialize after setup complete
        QTimer.singleShot(200, self.safe_initialization)
        
    def setup_maestro_selectors(self):
        """Setup maestro selection buttons"""
        self.maestro1_btn = QPushButton()
        self.maestro2_btn = QPushButton()
        self.maestro1_btn.setCheckable(True)
        self.maestro2_btn.setCheckable(True)
        
        # Load icons if available
        if os.path.exists("resources/icons/M1.png"):
            self.maestro1_btn.setIcon(QIcon("resources/icons/M1.png"))
            self.maestro1_btn.setIconSize(QSize(112, 118))
        if os.path.exists("resources/icons/M2.png"):
            self.maestro2_btn.setIcon(QIcon("resources/icons/M2.png"))
            self.maestro2_btn.setIconSize(QSize(112, 118))
        
        self.maestro_group = QButtonGroup()
        self.maestro_group.setExclusive(True)
        self.maestro_group.addButton(self.maestro1_btn, 0)
        self.maestro_group.addButton(self.maestro2_btn, 1)
        self.maestro_group.idClicked.connect(self.on_maestro_changed)
        
        # Default to Maestro 1
        self.maestro1_btn.setChecked(True)
        self.update_maestro_icons(0)
        
    def setup_control_buttons(self):
        """Setup control buttons"""
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Refresh Maestro connection and reload servo config")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #444;
                color: white;
                border-radius: 12px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        self.refresh_btn.setMinimumSize(100, 40)
        self.refresh_btn.clicked.connect(self.refresh_current_maestro)
        
    def setup_position_controls(self):
        """Setup controls for position reading"""
        # Auto-update checkbox
        self.auto_update_checkbox = QCheckBox("Auto-refresh")
        self.auto_update_checkbox.setChecked(False)
        self.auto_update_checkbox.setFont(QFont("Arial", 14))
        self.auto_update_checkbox.setStyleSheet("color: white;")
        self.auto_update_checkbox.setToolTip("Automatically read positions every 500ms")
        self.auto_update_checkbox.toggled.connect(self.toggle_auto_update)
        
        # Manual refresh button
        self.read_positions_btn = QPushButton("Read Positions")
        self.read_positions_btn.setFont(QFont("Arial", 14))
        self.read_positions_btn.setToolTip("Read current servo positions from selected Maestro")
        self.read_positions_btn.clicked.connect(self.read_all_positions_now)
        self.read_positions_btn.setStyleSheet("""
            QPushButton {
                background-color: #444;
                color: white;
                border-radius: 8px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        
        # Toggle all live checkboxes
        self.toggle_all_live_btn = QPushButton("Toggle Live")
        self.toggle_all_live_btn.setFont(QFont("Arial", 14))
        self.toggle_all_live_btn.clicked.connect(self.toggle_all_live_checkboxes)
        self.toggle_all_live_btn.setStyleSheet("""
            QPushButton {
                background-color: #444;
                color: white;
                border-radius: 8px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        
        # Status label
        self.status_label = QLabel("Initializing...")
        self.status_label.setFont(QFont("Arial", 12))
        self.status_label.setStyleSheet("color: #FFAA00; padding: 3px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFixedWidth(1050) 
        
    def setup_layout(self):
        """Setup the complete layout"""
        # Scrollable grid area
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_layout.setContentsMargins(2, 5, 2, 5)
        self.grid_layout.setVerticalSpacing(6)
        self.grid_widget.setLayout(self.grid_layout)
        self.grid_widget.setStyleSheet("QWidget { border: 1px solid #555; border-radius: 12px; }")
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setWidget(self.grid_widget)
        
        # Maestro selector container
        selector_container = QVBoxLayout()
        selector_container.addStretch()
        selector_container.addWidget(self.maestro1_btn)
        selector_container.addWidget(self.maestro2_btn)
        selector_container.addSpacing(20)
        selector_container.addWidget(self.refresh_btn)
        selector_container.addSpacing(10)
        selector_container.addWidget(self.auto_update_checkbox)
        selector_container.addWidget(self.read_positions_btn)
        selector_container.addWidget(self.toggle_all_live_btn)
        selector_container.addStretch()
        
        selector_widget = QWidget()
        selector_widget.setLayout(selector_container)
        selector_widget.setStyleSheet("background-color: rgba(0, 0, 0, 0);")
        
        # Main layout
        grid_and_selector_layout = QHBoxLayout()
        grid_and_selector_layout.addSpacing(5)
        grid_and_selector_layout.addWidget(scroll_area, stretch=5)
        grid_and_selector_layout.addWidget(selector_widget)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(90, 10, 10, 5)
        status_container = QHBoxLayout()
        status_container.addStretch()
        status_container.addWidget(self.status_label)
        status_container.addStretch()
        layout.addLayout(status_container)
        layout.addLayout(grid_and_selector_layout)
        self.setLayout(layout)
        
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
        """Request information for the currently selected Maestro"""
        maestro_num = self.current_maestro + 1
        self.update_status(f"Detecting Maestro {maestro_num} controller...")
        
        success = self.send_websocket_message("get_maestro_info", maestro=maestro_num)
        if success:
            self.logger.info(f"Requested info for Maestro {maestro_num}")
        else:
            self.update_status("Failed to request Maestro info: WebSocket not connected", error=True)
    
    def refresh_current_maestro(self):
        """Refresh only the currently selected Maestro"""
        # Stop any active operations
        self.stop_all_sweeps()
        if self.auto_update_positions:
            self.position_update_timer.stop()
        
        # Clear current state
        self.maestro_connected[self.current_maestro + 1] = False
        self.maestro_channel_counts[self.current_maestro + 1] = 0
        
        # Request fresh info
        self.request_current_maestro_info()
        self.reload_servo_config()
        
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
                    self.maestro_channel_counts[maestro_num] = channels
                    self.maestro_connected[maestro_num] = connected
                    self.logger.info(f"Maestro {maestro_num}: {channels} channels, connected: {connected}")
                    
                    if connected:
                        self.update_status(f"Maestro {maestro_num}: {channels} channels detected")
                        # Only update grid if this is the currently selected Maestro
                        if maestro_num == self.current_maestro + 1:
                            self.update_grid()
                            QTimer.singleShot(500, self.read_all_positions_now)
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
            
            # Update position label
            pos_label.setText(f"V: {position}")
            pos_label.setStyleSheet("color: #44FF44;")
            
            self.logger.debug(f"Updated display: {channel_key} = {position}")
    
    def update_status_threadsafe(self, message: str, error: bool = False, warning: bool = False):
        """Thread-safe status update"""
        self.status_label.setText(message)
        
        if error:
            self.status_label.setStyleSheet("color: #FF4444; padding: 3px;")
        elif warning:
            self.status_label.setStyleSheet("color: #FFAA00; padding: 3px;")
        else:
            self.status_label.setStyleSheet("color: #44FF44; padding: 3px;")
        
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
        if self.auto_update_positions:
            self.position_update_timer.stop()
        
        # Update selection
        old_maestro = self.current_maestro
        self.current_maestro = maestro_index
        self.update_maestro_icons(maestro_index)
        
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
        if self.auto_update_positions:
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
            self.grid_layout.addWidget(label, row, 0)
            
            # Name edit
            name_edit = QLineEdit(config.get("name", ""))
            name_edit.setFont(QFont("Arial", 16))
            name_edit.setMaxLength(25)
            name_edit.setFixedWidth(180)
            name_edit.setPlaceholderText("Servo Name")
            name_edit.textChanged.connect(lambda text, k=channel_key: self.update_config(k, "name", text))
            self.grid_layout.addWidget(name_edit, row, 1)
            
            # Slider for position control
            slider = QSlider(Qt.Orientation.Horizontal)
            min_val = config.get("min", 992)
            max_val = config.get("max", 2000)
            slider.setMinimum(min_val)
            slider.setMaximum(max_val)
            slider.setValue((min_val + max_val) // 2)
            slider.setFixedWidth(150)
            slider.setMinimumHeight(24)
            self.grid_layout.addWidget(slider, row, 2)
            
            # Min/Max value controls
            min_spin = QSpinBox()
            min_spin.setFont(QFont("Arial", 16))
            min_spin.setRange(0, 2500)
            min_spin.setValue(min_val)
            min_spin.setFixedWidth(60)
            min_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "min", val))
            min_spin.valueChanged.connect(lambda val, s=slider: s.setMinimum(val))
            self.grid_layout.addWidget(min_spin, row, 3)
            
            max_spin = QSpinBox()
            max_spin.setFont(QFont("Arial", 16))
            max_spin.setRange(0, 2500)
            max_spin.setValue(max_val)
            max_spin.setFixedWidth(60)
            max_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "max", val))
            max_spin.valueChanged.connect(lambda val, s=slider: s.setMaximum(val))
            self.grid_layout.addWidget(max_spin, row, 4)
            
            # Speed/Acceleration controls
            speed_spin = QSpinBox()
            speed_spin.setFont(QFont("Arial", 16))
            speed_spin.setRange(0, 100)
            speed_spin.setValue(config.get("speed", 0))
            speed_spin.setFixedWidth(50)
            speed_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "speed", val))
            self.grid_layout.addWidget(speed_spin, row, 5)
            
            accel_spin = QSpinBox()
            accel_spin.setFont(QFont("Arial", 16))
            accel_spin.setRange(0, 100)
            accel_spin.setValue(config.get("accel", 0))
            accel_spin.setFixedWidth(50)
            accel_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "accel", val))
            self.grid_layout.addWidget(accel_spin, row, 6)
            
            # Position label
            pos_label = QLabel("---")
            pos_label.setFont(QFont("Arial", 16))
            pos_label.setStyleSheet("color: #FFAA00;")
            pos_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pos_label.setFixedWidth(60)
            self.grid_layout.addWidget(pos_label, row, 7)
            
            # Live update checkbox
            live_checkbox = QCheckBox()
            live_checkbox.setChecked(False)
            live_checkbox.setToolTip("Enable live servo updates")
            live_checkbox.setFixedSize(20, 20)
            live_checkbox.setStyleSheet("""
                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                }
                QCheckBox::indicator:unchecked {
                    background-color: #333;
                    border: 1px solid #666;
                    border-radius: 2px;
                }
                QCheckBox::indicator:checked {
                    background-color: #44FF44;
                    border: 1px solid #44FF44;
                    border-radius: 2px;
                }
            """)
            self.grid_layout.addWidget(live_checkbox, row, 8)
            
            # Play/sweep button
            play_btn = QPushButton("▶️")
            play_btn.setFont(QFont("Arial", 12))
            play_btn.setCheckable(True)
            play_btn.setFixedSize(30, 30)
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
        
        # Restart auto-updates if enabled
        if self.auto_update_positions:
            self.position_update_timer.start()
    
    def toggle_auto_update(self, enabled: bool):
        """Toggle automatic position updates for current Maestro"""
        self.auto_update_positions = enabled
        
        if enabled:
            maestro_num = self.current_maestro + 1
            if self.maestro_connected.get(maestro_num, False):
                self.position_update_timer.start()
                self.update_status("Auto-refresh positions: ON")
                self.logger.info("Auto position updates enabled")
            else:
                self.auto_update_checkbox.setChecked(False)
                self.auto_update_positions = False
                self.update_status("No valid Maestro for auto-refresh", warning=True)
        else:
            self.position_update_timer.stop()
            self.update_status("Auto-refresh positions: OFF")
            self.logger.info("Auto position updates disabled")
    
    def update_all_positions(self):
        """Update all servo positions for current Maestro"""
        if not self.auto_update_positions or self.reading_positions:
            return
        
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
        for channel_key, widgets in self.servo_widgets.items():
            if channel_key.startswith(f"m{maestro_num}_"):
                slider = widgets[0]
                pos_label = widgets[1]
                
                center = (slider.minimum() + slider.maximum()) // 2
                slider.blockSignals(True)
                slider.setValue(center)
                slider.blockSignals(False)
                
                pos_label.setText(f"V: {center}")
                pos_label.setStyleSheet("color: #FFAA00;")
    
    def update_servo_position_conditionally(self, channel_key: str, pos_label: QLabel, 
                                           value: int, live_checkbox: QCheckBox):
        """Update servo position only if live checkbox is checked"""
        pos_label.setText(f"V: {value}")
        
        if live_checkbox.isChecked():
            self.update_servo_position(channel_key, pos_label, value)
            pos_label.setStyleSheet("color: #FF4444;")
        else:
            pos_label.setStyleSheet("color: #AAAAAA;")
    
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
        button.setText("⏹️")
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
        if self.auto_update_positions:
            self.position_update_timer.stop()
    
    @error_boundary
    def update_maestro_icons(self, checked_id: int):
        """Update button icons based on selection"""
        if self.maestro_group.checkedId() == 0:
            if os.path.exists("resources/icons/M1_pressed.png"):
                self.maestro1_btn.setIcon(QIcon("resources/icons/M1_pressed.png"))
            if os.path.exists("resources/icons/M2.png"):
                self.maestro2_btn.setIcon(QIcon("resources/icons/M2.png"))
        else:
            if os.path.exists("resources/icons/M1.png"):
                self.maestro1_btn.setIcon(QIcon("resources/icons/M1.png"))
            if os.path.exists("resources/icons/M2_pressed.png"):
                self.maestro2_btn.setIcon(QIcon("resources/icons/M2_pressed.png"))
    
    @error_boundary
    def load_config(self) -> dict:
        """Load servo configuration from file"""
        return config_manager.get_config("resources/configs/servo_config.json")
    
    @error_boundary
    def save_config(self):
        """Save servo configuration to file"""
        success = config_manager.save_config("configs/servo_config.json", self.servo_config)
        if success:
            self.logger.info("Servo configuration saved")
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
        self.save_config()
    
    def cleanup(self):
        """Cleanup servo screen resources"""
        self.stop_all_operations()


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
        
        # Update UI
        self.label.setText(f"->{self.current_target}")
        self.label.setStyleSheet("color: #FFFF44;")
    
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
            self.label.setStyleSheet("color: #44FF44;")
            
            # Stop position checking during hold delay
            self.check_timer.stop()
            
            # Start hold timer before switching direction
            self.hold_timer.start(self.hold_delay)
            
        else:
            # Still moving, update display
            self.label.setText(f"V:{actual_position}")
            self.label.setStyleSheet("color: #FFAA44;")
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
        self.label.setStyleSheet("color: #AAAAAA;")
        self.btn.setText("▶️")
        self.btn.setChecked(False)
        
        self.logger.info(f"Min/Max sweep stopped: {self.channel_key} returned to center ({center_pos})")