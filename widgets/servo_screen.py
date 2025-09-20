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
from typing import Dict, Any


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
        super().__init__(websocket)
        # NEMA-specific initialization
        self.nema_test_sweeping = False
        self.position_update_timer = QTimer()
        self.position_update_timer.setSingleShot(True)
        self.position_update_timer.timeout.connect(self.send_position_to_backend)
        
        # Add WebSocket message handling
        if websocket:
            websocket.textMessageReceived.connect(self.handle_message)

        # Register for theme change notifications
        theme_manager.register_callback(self._on_theme_changed)
        
        # Add WebSocket connection monitoring
        self.ws_connection_timer = QTimer()
        self.ws_connection_timer.timeout.connect(self.check_websocket_and_detect)
        self.ws_connection_timer.start(2000)  # Check every 2 seconds
        
        # Track if we've done initial detection
        self.initial_detection_done = False
        
        # Call existing init
        
    @error_boundary
    def load_config(self) -> dict:
        """Load servo configuration from file"""
        try:
            config = config_manager.get_config("resources/configs/servo_config.json")
            return config if config else {}
        except Exception as e:
            self.logger.error(f"Failed to load servo config: {e}")
            return {}
        
    
    def __del__(self):
        """Clean up theme manager callback on destruction"""
        try:
            theme_manager.unregister_callback(self._on_theme_changed)
        except Exception:
            pass
    
    def _setup_screen(self):
        """Initialize servo configuration screen"""
        self.logger = get_logger("servo_screen")
        self.setFixedWidth(1180)
        self.servo_config = self.load_config()
        self.active_sweeps = {}
        
        # Maestro state tracking
        self.maestro_channel_counts = {1: 0, 2: 0}
        self.maestro_connected = {1: False, 2: False}
        self.current_maestro = 0  # 0=Maestro1, 1=Maestro2
        self.initialization_complete = False

        # NEMA configuration        
        self.current_controller = 0  # 0=M1, 1=M2, 2=NEMA
        self.nema_config = {
            "lead_screw_pitch": 8.0,
            "lead_screw_length": 20.0,
            "homing_speed": 400,
            "normal_speed": 800,
            "acceleration": 800,
            "min_position": 0.0,
            "max_position": 20.0,
            "current_position": 5.0
        }

        # Load NEMA config from file if it exists
        servo_config = self.load_config()
        if "nema" in servo_config:
            saved_nema = servo_config["nema"]
            for key, value in saved_nema.items():
                if key in self.nema_config:
                    self.nema_config[key] = value

        # Widget tracking for position updates
        self.servo_widgets = {}
        
        # Position update management
        self.position_update_timer_auto = QTimer()
        self.position_update_timer_auto.timeout.connect(self.update_all_positions)
        self.position_update_timer_auto.setInterval(500)
        
        # Position reading state
        self.reading_positions = False
        self.position_read_timeout = QTimer()
        self.position_read_timeout.timeout.connect(self.handle_position_read_timeout)
        self.position_read_timeout.setSingleShot(True)
        
        # Connect Qt signals for thread safety
        self.position_update_signal.connect(self.update_servo_position_display)
        self.status_update_signal.connect(self.update_status_threadsafe)
        
        self.setup_layout()
        
        # Initialize after setup complete
        QTimer.singleShot(200, self.safe_initialization)

# ========================================
    # WEBSOCKET MESSAGE HANDLING
    # ========================================
    
    def handle_message(self, message: str):
        """Enhanced message handler to support NEMA WebSocket messages"""
        try:
            msg = json.loads(message)
            msg_type = msg.get("type")
            
            # Handle existing message types first
            if msg_type == "telemetry":
                self.handle_telemetry(msg)
            elif msg_type == "maestro_info":
                self.handle_maestro_info(msg)
            elif msg_type == "servo_position":
                self.handle_servo_position(msg)
            elif msg_type == "all_servo_positions":
                self.handle_all_servo_positions(msg)
                
            # ========================================
            # NEW NEMA MESSAGE HANDLERS
            # ========================================
            elif msg_type == "nema_position_update":
                self.handle_nema_position_update(msg)
            elif msg_type == "nema_sweep_status":
                self.handle_nema_sweep_status(msg)
            elif msg_type == "nema_homing_complete":
                self.handle_nema_homing_complete(msg)
            elif msg_type == "nema_status":
                self.handle_nema_status_update(msg)
            elif msg_type == "nema_error":
                self.handle_nema_error(msg)
            elif msg_type == "nema_enable_response":
                self.handle_nema_enable_response(msg)
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse WebSocket message: {e}")
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")

    def handle_nema_position_update(self, msg):
        """Handle position updates from NEMA controller"""
        try:
            position_cm = msg.get("position_cm", 0.0)
            
            # Update internal state
            self.nema_config["current_position"] = position_cm
            
            # Update UI if NEMA is currently selected
            if self.current_controller == 2 and hasattr(self, 'position_slider'):
                # Block signals to prevent feedback loop
                self.position_slider.blockSignals(True)
                self.position_slider.setValue(int(position_cm *10))
                self.position_slider.blockSignals(False)
                
                # Update position display
                self.position_display.setText(f"{position_cm:.1f} cm")
                
            self.logger.debug(f"NEMA position updated: {position_cm:.1f} cm")
            
        except Exception as e:
            self.logger.error(f"Error handling NEMA position update: {e}")

    def handle_nema_sweep_status(self, msg):
        """Handle sweep status changes from NEMA controller"""
        try:
            sweeping = msg.get("sweeping", False)
            
            # Update internal state
            self.nema_test_sweeping = sweeping
            
            # Update UI if NEMA is currently selected
            if self.current_controller == 2 and hasattr(self, 'test_sweep_btn'):
                if sweeping:
                    self.test_sweep_btn.setText("⏹️ STOP SWEEP")
                    self.test_sweep_btn.setChecked(True)
                    self.update_status(f"NEMA sweep active: {self.nema_config['min_position']:.1f} ↔ {self.nema_config['max_position']:.1f} cm")
                else:
                    self.test_sweep_btn.setText("▶️ TEST SWEEP")
                    self.test_sweep_btn.setChecked(False)
                    self.update_status("NEMA sweep stopped")
                    
            self.logger.info(f"NEMA sweep status: {'active' if sweeping else 'stopped'}")
            
        except Exception as e:
            self.logger.error(f"Error handling NEMA sweep status: {e}")

    def handle_telemetry(self, msg):
        """Handle telemetry messages - placeholder for now"""
        # You can implement telemetry handling here if needed
        # For now, just log that we received it
        self.logger.debug("Received telemetry message")
        pass

    # You may also need these if they don't exist:
    def handle_servo_position(self, data):
        """Handle servo position messages"""
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


    def handle_nema_homing_complete(self, msg):
        """Handle homing completion notification"""
        try:
            success = msg.get("success", False)
            
            if success:
                self.update_status("NEMA homing completed successfully", color="green")
                # Reset position to 0 after successful homing
                self.nema_config["current_position"] = 0.0
                if self.current_controller == 2 and hasattr(self, 'position_slider'):
                    self.position_slider.blockSignals(True)
                    self.position_slider.setValue(0)
                    self.position_slider.blockSignals(False)
                    self.position_display.setText("0.0 cm")
            else:
                self.update_status("NEMA homing failed", error=True)
                
            self.logger.info(f"NEMA homing completed: {'success' if success else 'failed'}")
            
        except Exception as e:
            self.logger.error(f"Error handling NEMA homing complete: {e}")

    def handle_nema_status_update(self, msg):
        """Handle NEMA status updates with clearer logging"""
        try:
            status = msg.get("status", {})
            state = status.get("state", "unknown")
            homed = status.get("homed", False) 
            hardware_enabled = status.get("enabled", False)  # Hardware enable pin state
            position_cm = status.get("position_cm", 0.0)
            
            # Update internal state
            self.nema_config["current_position"] = position_cm
            
            # Update enable button to match hardware state
            if hasattr(self, 'enable_btn'):
                self.enable_btn.blockSignals(True)
                self.enable_btn.setChecked(hardware_enabled)
                if hardware_enabled:
                    self.enable_btn.setText("🔴 DISABLE")
                else:
                    self.enable_btn.setText("⚡ ENABLE")
                self.enable_btn.blockSignals(False)
            
            # Create clearer status message
            status_parts = []
            status_parts.append(f"State: {state}")
            
            if homed:
                status_parts.append("Homed")
            else:
                status_parts.append("Not Homed")
                
            if hardware_enabled:
                status_parts.append("Motor ON")
            else:
                status_parts.append("Motor OFF")
                
            # Determine overall status color
            if state == "error":
                color = "red"
            elif hardware_enabled and homed and state == "ready":
                color = "green"
            elif hardware_enabled:
                color = "orange"
            else:
                color = "gray"
                
            status_text = f"NEMA: {', '.join(status_parts)}"
            
            # Update status display
            if hasattr(self, 'nema_status_label'):
                self.nema_status_label.setText(status_text)
                self.nema_status_label.setStyleSheet(f"color: {color}; font-weight: bold; background: transparent;")
            
            # Update position if NEMA is active
            if self.current_controller == 2 and hasattr(self, 'position_slider'):
                self.position_slider.blockSignals(True)
                self.position_slider.setValue(int(position_cm * 10))
                self.position_slider.blockSignals(False)
                self.position_display.setText(f"{position_cm:.1f} cm")
                
            # Improved logging - less frequent, more informative
            self.logger.debug(f"NEMA status: {state}, hardware_enabled={hardware_enabled}, homed={homed}, pos={position_cm:.1f}cm")
            
        except Exception as e:
            self.logger.error(f"Error handling NEMA status update: {e}")


    def handle_nema_enable_response(self, msg):
        """Handle enable/disable command responses"""
        try:
            success = msg.get("success", False)
            enabled = msg.get("enabled", False)
            message = msg.get("message", "")
            
            if success:
                action = "enabled" if enabled else "disabled"
                self.update_status(f"NEMA stepper {action} successfully", color="green")
                self.logger.info(f"NEMA stepper {action} successfully")
                
                # Update button state to match response
                if hasattr(self, 'enable_btn'):
                    self.enable_btn.blockSignals(True)
                    self.enable_btn.setChecked(enabled)
                    if enabled:
                        self.enable_btn.setText("🔴 DISABLE")
                    else:
                        self.enable_btn.setText("⚡ ENABLE")
                    self.enable_btn.blockSignals(False)
            else:
                self.update_status(f"Failed to change NEMA state: {message}", error=True)
                self.logger.error(f"NEMA enable command failed: {message}")
                
                # Reset button to previous state on failure
                if hasattr(self, 'enable_btn'):
                    self.enable_btn.blockSignals(True)
                    self.enable_btn.setChecked(not enabled)
                    self.enable_btn.blockSignals(False)
                
        except Exception as e:
            self.logger.error(f"Error handling NEMA enable response: {e}")

    def handle_nema_error(self, msg):
        """Handle NEMA error messages"""
        try:
            error_message = msg.get("error", "Unknown NEMA error")
            error_code = msg.get("error_code", None)
            
            # Display error to user
            full_message = f"NEMA Error: {error_message}"
            if error_code:
                full_message += f" (Code: {error_code})"
                
            self.update_status(full_message, error=True)
            self.logger.error(f"NEMA error received: {error_message} (code: {error_code})")
            
            # Stop any active sweep on error
            if hasattr(self, 'nema_test_sweeping') and self.nema_test_sweeping:
                self.nema_test_sweeping = False
                if hasattr(self, 'test_sweep_btn'):
                    self.test_sweep_btn.setText("▶️ TEST SWEEP")
                    self.test_sweep_btn.setChecked(False)
                    
        except Exception as e:
            self.logger.error(f"Error handling NEMA error message: {e}")

    # Handle existing messages (maestro_info, etc.) - keeping original implementation
    def handle_maestro_info(self, data):
        """Handle maestro info messages"""
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

    def handle_servo_position(self, data):
        """Handle servo position messages"""
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

    def handle_all_servo_positions(self, data):
        """Handle all servo positions messages"""
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

# ========================================
    # NEMA CONTROL METHODS
    # ========================================
    
    def send_position_to_backend(self):
        """Send the current position to backend (called after debounce)"""
        position_cm = self.nema_config["current_position"]
        
        # Validate position is within bounds
        min_pos = self.nema_config["min_position"]
        max_pos = self.nema_config["max_position"]
        
        if not (min_pos <= position_cm <= max_pos):
            self.logger.warning(f"Position {position_cm:.1f} cm outside bounds [{min_pos:.1f}, {max_pos:.1f}]")
            self.update_status(f"Position {position_cm:.1f} cm outside safe bounds", error=True)
            return
        
        # Send WebSocket message to backend
        success = self.send_websocket_message("nema_move_to_position", position_cm=position_cm)
        if success:
            self.logger.debug(f"Sent position to backend: {position_cm:.1f} cm")
        else:
            self.update_status("Failed to send position: WebSocket not connected", error=True)

    def toggle_nema_test_sweep(self):
        """Toggle NEMA test sweep between min and max"""
        if self.nema_test_sweeping:
            # Stop sweep
            success = self.send_websocket_message("nema_stop_sweep")
            if success:
                self.logger.info("Sent stop sweep command")
            else:
                self.update_status("Failed to stop sweep: WebSocket not connected", error=True)
                
        else:
            # Start sweep - validate parameters first
            min_cm = self.nema_config["min_position"]
            max_cm = self.nema_config["max_position"]
            acceleration = self.nema_config["acceleration"]
            normal_speed = self.nema_config["normal_speed"]
            
            if min_cm >= max_cm:
                self.update_status("Invalid sweep range: min >= max", error=True)
                return
                
            success = self.send_websocket_message("nema_start_sweep", 
                                                min_cm=min_cm,
                                                max_cm=max_cm,
                                                acceleration=acceleration,
                                                normal_speed=normal_speed)
            if success:
                self.logger.info(f"Sent start sweep command: {min_cm:.1f} to {max_cm:.1f} cm")
            else:
                self.update_status("Failed to start sweep: WebSocket not connected", error=True)

    def save_nema_config(self):
        """Enhanced save NEMA configuration with backend sync"""
        # Create config without current_position to avoid saving every position change
        config_to_save = {k: v for k, v in self.nema_config.items() if k != "current_position"}
        self.servo_config["nema"] = config_to_save
        
        # Save to file
        success = config_manager.save_config("resources/configs/servo_config.json", self.servo_config)
        if success:
            self.logger.debug("NEMA configuration saved to file")
            
            # Send config update to backend
            ws_success = self.send_websocket_message("nema_config_update", config=config_to_save)
            if ws_success:
                self.logger.debug("NEMA configuration sent to backend")
            else:
                self.logger.warning("Failed to send config to backend: WebSocket not connected")
        else:
            self.logger.error("Failed to save NEMA configuration to file")
            self.update_status("Failed to save NEMA configuration", error=True)

    def home_nema_stepper(self):
        """Send homing command to NEMA controller"""
        success = self.send_websocket_message("nema_home")
        if success:
            self.update_status("NEMA homing started...")
            self.logger.info("Sent NEMA homing command")
        else:
            self.update_status("Failed to start homing: WebSocket not connected", error=True)

    def enable_nema_stepper(self, enabled: bool):
        """Enable/disable NEMA stepper motor with improved logging"""
        success = self.send_websocket_message("nema_enable", enabled=enabled)
        if success:
            action = "enabled" if enabled else "disabled"
            self.update_status(f"NEMA stepper {action}")
            self.logger.info(f"Sent NEMA enable command: {action}")
        else:
            self.update_status("Failed to change NEMA enable state: WebSocket not connected", error=True)
            # Reset button state on failure
            self.enable_btn.blockSignals(True)
            self.enable_btn.setChecked(not enabled)
            self.enable_btn.blockSignals(False)

    def request_nema_status(self):
        """Request current NEMA status from backend"""
        success = self.send_websocket_message("nema_get_status")
        if success:
            self.logger.debug("Requested NEMA status from backend")
        else:
            self.logger.warning("Failed to request NEMA status: WebSocket not connected")

    def validate_nema_position(self, position_cm: float) -> bool:
        """Validate that position is within configured bounds"""
        min_pos = self.nema_config["min_position"]
        max_pos = self.nema_config["max_position"]
        return min_pos <= position_cm <= max_pos

    def clamp_nema_position(self, position_cm: float) -> float:
        """Clamp position to configured bounds"""
        min_pos = self.nema_config["min_position"]
        max_pos = self.nema_config["max_position"]
        return max(min_pos, min(max_pos, position_cm))

    def update_nema_pitch(self, value):
        """Update lead screw pitch"""
        self.nema_config["lead_screw_pitch"] = float(value)
        self.save_nema_config()

    def update_nema_length(self, value):
        """Update lead screw length"""
        self.nema_config["lead_screw_length"] = float(value)
        self.save_nema_config()

    def update_nema_homing_speed(self, value):
        """Update homing speed"""
        self.nema_config["homing_speed"] = value
        self.save_nema_config()

    def update_nema_normal_speed(self, value):
        """Update normal speed"""
        self.nema_config["normal_speed"] = value
        self.save_nema_config()

    def update_nema_acceleration(self, value):
        """Update acceleration slider"""
        self.nema_config["acceleration"] = value
        self.accel_value_label.setText(f"{value} steps/s²")
        self.save_nema_config()

    def init_nema_connection(self):
        """Initialize NEMA controller connection and request status"""
        if self.current_controller == 2:  # NEMA selected
            # Request current status
            self.request_nema_status()
            
            # Start periodic status updates
            if not hasattr(self, 'nema_status_timer'):
                self.nema_status_timer = QTimer()
                self.nema_status_timer.timeout.connect(self.request_nema_status)
            
            self.nema_status_timer.start(5000)  # Request status every 5 seconds
            self.logger.info("NEMA connection initialized")

    def cleanup_nema_connection(self):
        """Clean up NEMA controller connection"""
        if hasattr(self, 'nema_status_timer'):
            self.nema_status_timer.stop()
        
        # Stop any active sweep
        if hasattr(self, 'nema_test_sweeping') and self.nema_test_sweeping:
            self.send_websocket_message("nema_stop_sweep")
            
        self.logger.info("NEMA connection cleaned up")
        """Enhanced position update with validation and improved feedback"""


    def update_nema_position(self, slider_value):
        """Enhanced position update with validation and improved feedback"""
        position_cm = float(slider_value) /10.0

        # Validate position
        if not self.validate_nema_position(position_cm):
            # Clamp to valid range
            position_cm = self.clamp_nema_position(position_cm)
            # Update slider to show clamped value
            self.position_slider.blockSignals(True)
            self.position_slider.setValue(int(position_cm * 10))
            self.position_slider.blockSignals(False)
            
            self.update_status(f"Position clamped to {position_cm:.1f} cm", color="orange")
        
        # Update internal state and display
        self.nema_config["current_position"] = position_cm
        self.position_display.setText(f"{position_cm:.1f} cm")
        
        # Restart the debounce timer
        self.position_update_timer.stop()
        self.position_update_timer.start(300)  # 300ms debounce

    def update_nema_min_pos(self, value):
        """Enhanced min position update with validation"""
        old_min = self.nema_config["min_position"]
        new_min = float(value)
        
        # Validate that min < max
        if new_min >= self.nema_config["max_position"]:
            self.update_status(f"Min position {new_min:.1f} must be less than max {self.nema_config['max_position']:.1f}", error=True)
            # Reset to old value
            if hasattr(self, 'min_pos_spin'):
                self.min_pos_spin.setValue(int(old_min))
            return
        
        self.nema_config["min_position"] = new_min
        
        # Update slider range and clamp current position if needed
        if hasattr(self, 'position_slider'):
            self.position_slider.setMinimum(int(new_min * 10))
            
        if hasattr(self, 'min_label'):
            self.min_label.setText(f"{new_min:.1f}")
        
        # Clamp current position if needed
        if self.nema_config["current_position"] < new_min:
            self.nema_config["current_position"] = new_min
            if hasattr(self, 'position_slider'):
                self.position_slider.setValue(int(new_min * 10))
            if hasattr(self, 'position_display'):
                self.position_display.setText(f"{new_min:.1f} cm")
            self.update_status(f"Current position adjusted to new minimum: {new_min:.1f} cm", color="orange")
        
        self.save_nema_config()

    def update_nema_max_pos(self, value):
        """Enhanced max position update with validation"""
        old_max = self.nema_config["max_position"]
        new_max = float(value)
        
        # Validate that max > min
        if new_max <= self.nema_config["min_position"]:
            self.update_status(f"Max position {new_max:.1f} must be greater than min {self.nema_config['min_position']:.1f}", error=True)
            # Reset to old value
            if hasattr(self, 'max_pos_spin'):
                self.max_pos_spin.setValue(int(old_max))
            return
        
        self.nema_config["max_position"] = new_max
        
        # Update slider range and clamp current position if needed
        if hasattr(self, 'position_slider'):
            self.position_slider.setMaximum(int(new_max * 10))
            
        if hasattr(self, 'max_label'):
            self.max_label.setText(f"{new_max:.1f}")
        
        # Clamp current position if needed
        if self.nema_config["current_position"] > new_max:
            self.nema_config["current_position"] = new_max
            if hasattr(self, 'position_slider'):
                self.position_slider.setValue(int(new_max * 10))
            if hasattr(self, 'position_display'):
                self.position_display.setText(f"{new_max:.1f} cm")
            self.update_status(f"Current position adjusted to new maximum: {new_max:.1f} cm", color="orange")
        
        self.save_nema_config()

# ========================================
    # LAYOUT AND UI SETUP
    # ========================================
    
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
        layout.setContentsMargins(90, 10, 20, 5)
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
                border: none; 
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
        self.maestro_label = QLabel("Controller")
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
        
        button_container.addWidget(self.maestro1_btn)
        button_container.addWidget(self.maestro2_btn)
        maestro_layout.addLayout(button_container)
        
        # Add NEMA button below M1/M2
        self.nema_btn = QPushButton("NEMA")
        self.nema_btn.setCheckable(True)
        self.nema_btn.setChecked(False)
        self.nema_btn.setFixedHeight(40)
        self.nema_btn.setFixedWidth(185)
        self.nema_btn.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self._update_maestro_button_style(self.nema_btn)
        maestro_layout.addWidget(self.nema_btn)
        maestro_layout.setAlignment(self.nema_btn, Qt.AlignmentFlag.AlignCenter)

        # Set up button group
        self.maestro_group = QButtonGroup()
        self.maestro_group.setExclusive(True)
        self.maestro_group.addButton(self.maestro1_btn, 0)
        self.maestro_group.addButton(self.maestro2_btn, 1)
        self.maestro_group.addButton(self.nema_btn, 2)
        self.maestro_group.idClicked.connect(self.on_maestro_changed)
        
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

# ========================================
    # NEMA INTERFACE CREATION
    # ========================================
    
    def create_nema_interface(self):
        """Enhanced NEMA stepper control interface in the grid area"""
        # Clear the grid first
        self.clear_grid()
        
        # Create main container
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(10, 5, 10, 5)
        main_layout.setSpacing(20)
        
        # Left side - Configuration
        self.config_frame = QFrame()
        self.config_frame.setFrameStyle(QFrame.Shape.Box)
        self.config_frame.setStyleSheet(f"""
            QFrame {{
                border: 1px solid {theme_manager.get('primary_color')};
                border-radius: 12px;
                background-color: rgba(0, 0, 0, 0.1);
            }}
        """)
        
        config_layout = QVBoxLayout()
        config_layout.setContentsMargins(20, 15, 20, 15)
        config_layout.setSpacing(15)
        
        # Configuration header
        self.config_header = QLabel("NEMA CONFIGURATION")
        self.config_header.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        self.config_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.config_header.setStyleSheet(f"color: {theme_manager.get('primary_color')}; background: transparent;")
        config_layout.addWidget(self.config_header)
        
        # Configuration form in grid
        form_layout = QGridLayout()
        form_layout.setSpacing(10)
        
        # Lead Screw Pitch
        pitch_label = QLabel("Lead Screw Pitch (mm):")
        pitch_label.setStyleSheet("color: white; background: transparent;")
        form_layout.addWidget(pitch_label, 0, 0)
        
        self.pitch_spin = QSpinBox()
        self.pitch_spin.setRange(1, 20)
        self.pitch_spin.setValue(int(self.nema_config["lead_screw_pitch"]))
        self.pitch_spin.valueChanged.connect(self.update_nema_pitch)
        self._update_spinbox_style(self.pitch_spin)
        form_layout.addWidget(self.pitch_spin, 0, 1)
        
        # Lead Screw Length
        length_label = QLabel("Lead Screw Length (cm):")
        length_label.setStyleSheet("color: white; background: transparent;")
        form_layout.addWidget(length_label, 1, 0)
        
        self.length_spin = QSpinBox()
        self.length_spin.setRange(10, 50)
        self.length_spin.setValue(int(self.nema_config["lead_screw_length"]))
        self.length_spin.valueChanged.connect(self.update_nema_length)
        self._update_spinbox_style(self.length_spin)
        form_layout.addWidget(self.length_spin, 1, 1)
        
        # Homing Speed
        homing_label = QLabel("Homing Speed (steps/s):")
        homing_label.setStyleSheet("color: white; background: transparent;")
        form_layout.addWidget(homing_label, 2, 0)
        
        self.homing_speed_spin = QSpinBox()
        self.homing_speed_spin.setRange(400, 5000)
        self.homing_speed_spin.setSingleStep(100)
        self.homing_speed_spin.setValue(self.nema_config["homing_speed"])
        self.homing_speed_spin.valueChanged.connect(self.update_nema_homing_speed)
        self._update_spinbox_style(self.homing_speed_spin)
        form_layout.addWidget(self.homing_speed_spin, 2, 1)
        
        # Normal Speed
        normal_label = QLabel("Normal Speed (steps/s):")
        normal_label.setStyleSheet("color: white; background: transparent;")
        form_layout.addWidget(normal_label, 3, 0)
        
        self.normal_speed_spin = QSpinBox()
        self.normal_speed_spin.setRange(400, 5000)
        self.normal_speed_spin.setSingleStep(100)
        self.normal_speed_spin.setValue(self.nema_config["normal_speed"])
        self.normal_speed_spin.valueChanged.connect(self.update_nema_normal_speed)
        self._update_spinbox_style(self.normal_speed_spin)
        form_layout.addWidget(self.normal_speed_spin, 3, 1)
        
        # Acceleration slider
        accel_label = QLabel("Acceleration:")
        accel_label.setStyleSheet("color: white; background: transparent;")
        form_layout.addWidget(accel_label, 4, 0)
        
        self.accel_value_label = QLabel(f"{self.nema_config['acceleration']} steps/s²")
        self.accel_value_label.setStyleSheet("color: white; background: transparent;")
        form_layout.addWidget(self.accel_value_label, 4, 1)
        
        self.accel_slider = QSlider(Qt.Orientation.Horizontal)
        self.accel_slider.setRange(200, 12000)
        self.accel_slider.setValue(self.nema_config["acceleration"])
        self.accel_slider.valueChanged.connect(self.update_nema_acceleration)
        form_layout.addWidget(self.accel_slider, 5, 0, 1, 2)
        
        # Position limits
        min_pos_label = QLabel("Min Position (cm):")
        min_pos_label.setStyleSheet("color: white; background: transparent;")
        form_layout.addWidget(min_pos_label, 6, 0)
        
        self.min_pos_spin = QSpinBox()
        self.min_pos_spin.setRange(0, 49)
        self.min_pos_spin.setValue(int(self.nema_config["min_position"]))
        self.min_pos_spin.valueChanged.connect(self.update_nema_min_pos)
        self._update_spinbox_style(self.min_pos_spin)
        form_layout.addWidget(self.min_pos_spin, 6, 1)
        
        max_pos_label = QLabel("Max Position (cm):")
        max_pos_label.setStyleSheet("color: white; background: transparent;")
        form_layout.addWidget(max_pos_label, 7, 0)
        
        self.max_pos_spin = QSpinBox()
        self.max_pos_spin.setRange(1, 50)
        self.max_pos_spin.setValue(int(self.nema_config["max_position"]))
        self.max_pos_spin.valueChanged.connect(self.update_nema_max_pos)
        self._update_spinbox_style(self.max_pos_spin)
        form_layout.addWidget(self.max_pos_spin, 7, 1)
        
        config_layout.addLayout(form_layout)
        
        # Control buttons
        control_buttons_layout = QHBoxLayout()
        
        # Home button
        self.home_btn = QPushButton("🏠 HOME")
        self.home_btn.setFixedHeight(40)
        self.home_btn.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.home_btn.clicked.connect(self.home_nema_stepper)
        self._update_operation_button_style(self.home_btn)
        control_buttons_layout.addWidget(self.home_btn)
        
        # Enable/Disable toggle
        self.enable_btn = QPushButton("⚡ ENABLE")
        self.enable_btn.setFixedHeight(40)
        self.enable_btn.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.enable_btn.setCheckable(True)
        self.enable_btn.toggled.connect(self.on_enable_toggle)
        self._update_operation_button_style(self.enable_btn)
        control_buttons_layout.addWidget(self.enable_btn)
        
        config_layout.addLayout(control_buttons_layout)
        
        # Status indicator
        self.nema_status_label = QLabel("Status: Connecting...")
        self.nema_status_label.setStyleSheet("color: orange; font-weight: bold; background: transparent;")
        self.nema_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        config_layout.addWidget(self.nema_status_label)
        
        config_layout.addStretch()
        self.config_frame.setLayout(config_layout)
        
        # Right side - Position Control
        self.control_frame = QFrame()
        self.control_frame.setFrameStyle(QFrame.Shape.Box)
        self.control_frame.setStyleSheet(f"""
            QFrame {{
                border: 1px solid {theme_manager.get('primary_color')};
                border-radius: 12px;
                background-color: rgba(0, 0, 0, 0.1);
            }}
        """)
        
        control_layout = QVBoxLayout()
        control_layout.setContentsMargins(20, 15, 20, 15)
        control_layout.setSpacing(20)
        
        # Control header
        self.control_header = QLabel("POSITION CONTROL")
        self.control_header.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        self.control_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.control_header.setStyleSheet(f"color: {theme_manager.get('primary_color')}; background: transparent;")
        control_layout.addWidget(self.control_header)
        
        # Current position display
        self.position_display = QLabel(f"{self.nema_config['current_position']:.1f} cm")
        self.position_display.setFont(QFont("Arial", 36, QFont.Weight.Bold))
        self.position_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.position_display.setStyleSheet(f"""
            QLabel {{
                color: {theme_manager.get('primary_color')};
                border: 2px solid {theme_manager.get('primary_color')};
                border-radius: 10px;
                padding: 20px;
                background-color: rgba(0, 0, 0, 0.3);
            }}
        """)
        control_layout.addWidget(self.position_display)
        
        # Position slider
        slider_layout = QVBoxLayout()
        slider_layout.setSpacing(5)
        
        slider_label = QLabel("Target Position")
        slider_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        slider_label.setStyleSheet("color: white; background: transparent;")
        slider_layout.addWidget(slider_label)
        
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(int(self.nema_config["min_position"]*10), 
                                    int(self.nema_config["max_position"]*10))
        self.position_slider.setValue(int(self.nema_config["current_position"]*10))
        self.position_slider.valueChanged.connect(self.update_nema_position)
        self.position_slider.setFixedHeight(30)
        slider_layout.addWidget(self.position_slider)
        
        # Slider range labels
        range_layout = QHBoxLayout()
        self.min_label = QLabel(f"{self.nema_config['min_position']:.1f}")
        self.max_label = QLabel(f"{self.nema_config['max_position']:.1f}")
        self.min_label.setStyleSheet("color: white; background: transparent;")
        self.max_label.setStyleSheet("color: white; background: transparent;")
        range_layout.addWidget(self.min_label)
        range_layout.addStretch()
        range_layout.addWidget(self.max_label)
        slider_layout.addLayout(range_layout)
        
        control_layout.addLayout(slider_layout)

        # Test sweep button
        self.test_sweep_btn = QPushButton("▶️ TEST SWEEP")
        self.test_sweep_btn.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.test_sweep_btn.setCheckable(True)
        self.test_sweep_btn.setFixedHeight(40)
        self.test_sweep_btn.clicked.connect(self.toggle_nema_test_sweep)
        self._update_operation_button_style(self.test_sweep_btn)
        control_layout.addWidget(self.test_sweep_btn)

        # Add some spacing
        control_layout.addSpacing(10)
        self.control_frame.setLayout(control_layout)
        
        # Add both frames to main layout
        main_layout.addWidget(self.config_frame, stretch=1)
        main_layout.addWidget(self.control_frame, stretch=1)
        
        # Create container widget and add to grid
        container_widget = QWidget()
        container_widget.setLayout(main_layout)
        
        # Add to the grid layout at position (0,0) spanning the full width
        self.grid_layout.addWidget(container_widget, 0, 0, 1, 10)

# ========================================
    # CONTROLLER MANAGEMENT
    # ========================================
    
    def on_maestro_changed(self, maestro_index: int):
        
        # Stop current operations
        self.stop_all_sweeps()
        if hasattr(self, 'position_update_timer') and self.position_update_timer.isActive():
            self.position_update_timer.stop()
        
        # Clean up old controller
        old_controller = self.current_controller
        if old_controller == 2:  # Was NEMA
            self.cleanup_nema_connection()
        
        # Update selection
        self.current_controller = maestro_index

        if maestro_index < 2:  # M1 or M2 selected
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
            
            self.logger.info(f"Switched from controller {old_controller} to Maestro {maestro_num}")

        else:  # NEMA selected (index 2)
            self.update_status("NEMA stepper controller selected")
            self.create_nema_interface()
            self.init_nema_connection()  # Initialize NEMA connection
            self.logger.info("Switched to NEMA controller")

    def clear_grid(self):
        """Clear the current grid and widget tracking"""
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        
        self.servo_widgets.clear()

    def on_enable_toggle(self, checked):
        """Handle enable button toggle with proper UI feedback"""
        # Update button appearance immediately
        if checked:
            self.enable_btn.setText("🔴 DISABLE")
            self.enable_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #ff6b6b, stop:1 #ee5a5a);
                    color: white;
                    border: 2px solid #ff4757;
                }
            """)
        else:
            self.enable_btn.setText("⚡ ENABLE")
            self.enable_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #70a1ff, stop:1 #5352ed);
                    color: white;  
                    border: 2px solid #3742fa;
                }
            """)
        
        # Send command to backend
        self.enable_nema_stepper(checked)

    def check_websocket_and_detect(self):
        """Enhanced connection monitoring with NEMA support"""
        if not self.websocket or not self.websocket.is_connected():
            if self.current_controller == 2:  # NEMA selected
                if hasattr(self, 'nema_status_label'):
                    self.nema_status_label.setText("Status: WebSocket Disconnected")
                    self.nema_status_label.setStyleSheet("color: red; font-weight: bold; background: transparent;")
            return
        
        # Original maestro detection logic for M1/M2
        if self.current_controller < 2:
            if not self.initial_detection_done:
                self.logger.info("WebSocket connected - triggering automatic maestro detection")
                self.detect_all_maestros()
                self.initial_detection_done = True
                # Stop the timer once we've done initial detection
                self.ws_connection_timer.stop()
        else:
            # NEMA controller - request status if needed
            if not hasattr(self, 'last_nema_status_request'):
                self.last_nema_status_request = 0
            
            import time
            current_time = time.time()
            if current_time - self.last_nema_status_request > 10:  # Every 10 seconds
                self.request_nema_status()
                self.last_nema_status_request = current_time

    # ========================================
    # THEME HANDLING
    # ========================================
    
    def _on_theme_changed(self):
        """Enhanced theme change handler with NEMA support"""
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
            if hasattr(self, 'nema_btn'):
                self._update_maestro_button_style(self.nema_btn)
            
            # Update operations section
            if hasattr(self, 'ops_header'):
                self._update_ops_header_style()
            if hasattr(self, 'operation_buttons'):
                for btn in self.operation_buttons:
                    self._update_operation_button_style(btn)
            if hasattr(self, 'operations_frame'):
                self._update_operations_frame_style(self.operations_frame)
            
            # Update NEMA-specific elements
            if hasattr(self, 'home_btn'):
                self._update_operation_button_style(self.home_btn)
            if hasattr(self, 'enable_btn'):
                self._update_operation_button_style(self.enable_btn)
            if hasattr(self, 'test_sweep_btn'):
                self._update_operation_button_style(self.test_sweep_btn)
            
            # Update scroll area if it exists
            scroll_areas = self.findChildren(QScrollArea)
            for scroll_area in scroll_areas:
                self._update_scroll_area_style(scroll_area)
            
            # Update all servo widgets in grid
            self._update_servo_widgets_theme()

            # Update NEMA-specific elements 
            if self.current_controller == 2:  # NEMA is active
                # Update NEMA configuration frame borders
                if hasattr(self, 'config_frame'):
                    primary = theme_manager.get("primary_color")
                    self.config_frame.setStyleSheet(f"""
                        QFrame {{
                            border: 1px solid {primary};
                            border-radius: 12px;
                            background-color: rgba(0, 0, 0, 0.1);
                        }}
                    """)
                
                if hasattr(self, 'control_frame'):
                    primary = theme_manager.get("primary_color")
                    self.control_frame.setStyleSheet(f"""
                        QFrame {{
                            border: 1px solid {primary};
                            border-radius: 12px;
                            background-color: rgba(0, 0, 0, 0.1);
                        }}
                    """)
                
                # Update NEMA headers
                if hasattr(self, 'config_header'):
                    primary = theme_manager.get("primary_color")
                    self.config_header.setStyleSheet(f"color: {primary}; background: transparent;")
                
                if hasattr(self, 'control_header'):
                    primary = theme_manager.get("primary_color")
                    self.control_header.setStyleSheet(f"color: {primary}; background: transparent;")
                
                # Update all NEMA spinboxes
                nema_spinboxes = ['pitch_spin', 'length_spin', 'homing_speed_spin', 'normal_speed_spin', 'min_pos_spin', 'max_pos_spin']
                for spinbox_name in nema_spinboxes:
                    if hasattr(self, spinbox_name):
                        spinbox = getattr(self, spinbox_name)
                        self._update_spinbox_style(spinbox)
                
                # Update NEMA slider
                if hasattr(self, 'accel_slider'):
                    self._update_slider_style(self.accel_slider)
                if hasattr(self, 'position_slider'):
                    self._update_slider_style(self.position_slider)
                
                # Update NEMA labels
                nema_labels = ['accel_value_label', 'position_display']
                for label_name in nema_labels:
                    if hasattr(self, label_name):
                        label = getattr(self, label_name)
                        label.setStyleSheet("color: white; background: transparent;")
            
            
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

# ========================================
    # MAESTRO GRID AND CONTROL METHODS
    # ========================================
    
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
        """Handle incoming WebSocket messages - calls the enhanced handler"""
        self.handle_message(message)

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
    
    def update_status(self, message: str, error: bool = False, warning: bool = False, color: str = None):
        """Update status using Qt signal for thread safety"""
        if color:
            # Handle color-specific updates
            self.status_label.setText(message)
            self.status_label.setStyleSheet(f"color: {color}; padding: 3px;")
            self.logger.info(f"Status: {message}")
        else:
            self.status_update_signal.emit(message, error, warning)

    def update_grid(self):
        """Build servo control grid for currently selected Maestro only"""
        maestro_num = self.current_maestro + 1
        channel_count = self.maestro_channel_counts.get(maestro_num, 0)
        
        if channel_count == 0:
            self.update_status(f"Maestro {maestro_num} not available", error=True)
            return
        
        self.logger.info(f"Building grid for Maestro {maestro_num} with {channel_count} channels")
        
        # Stop any active updates while rebuilding
        if hasattr(self, 'position_update_timer_auto') and self.position_update_timer_auto.isActive():
            self.position_update_timer_auto.stop()
        
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
            speed_spin.valueChanged.connect(lambda val, k=channel_key: self.update_servo_speed_config(k, val))
            self._update_spinbox_style(speed_spin)
            self.grid_layout.addWidget(speed_spin, row, 5)
            
            accel_spin = QSpinBox()
            accel_spin.setFont(QFont("Arial", 16))
            accel_spin.setRange(0, 100)
            accel_spin.setValue(config.get("accel", 0))
            accel_spin.setFixedWidth(60)
            accel_spin.valueChanged.connect(lambda val, k=channel_key: self.update_servo_accel_config(k, val))
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

    def update_servo_speed_config(self, channel_key: str, speed: int):
        """Update servo speed configuration"""
        if channel_key not in self.servo_config:
            self.servo_config[channel_key] = {}
        self.servo_config[channel_key]["speed"] = speed
        self.save_config()
        
        # Send to backend immediately
        self.send_websocket_message("servo_speed", channel=channel_key, speed=speed)

    def update_servo_accel_config(self, channel_key: str, accel: int):
        """Update servo acceleration configuration"""
        if channel_key not in self.servo_config:
            self.servo_config[channel_key] = {}
        self.servo_config[channel_key]["accel"] = accel
        self.save_config()
        
        # Send to backend immediately
        self.send_websocket_message("servo_acceleration", channel=channel_key, acceleration=accel)

# ========================================
    # POSITION UPDATES AND SERVO CONTROL
    # ========================================
    
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
                
                # Update visual indicator
                slider.set_home_position(current_pos)
                if channel_key not in self.servo_config:
                    self.servo_config[channel_key] = {}
                self.servo_config[channel_key]["home"] = current_pos
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
        button.setText("⸏")
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
        if hasattr(self, 'position_update_timer_auto') and self.position_update_timer_auto.isActive():
            self.position_update_timer_auto.stop()

# ========================================
    # CONFIGURATION MANAGEMENT
    # ========================================
        

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

    def update_config(self, config_dict: Dict[str, Any]) -> bool:
        try:
            # Don't allow updates while moving
            if self.state == MotorState.MOVING:
                logger.warning("Cannot update config while motor is moving")
                return False
            
            old_config = dict(self.config.__dict__)  # Save old config
            self.config.update_from_dict(config_dict)
            
            # Log what actually changed
            for key, value in config_dict.items():
                if hasattr(self.config, key):
                    logger.info(f"NEMA config updated: {key} = {value}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update NEMA config: {e}")
            return False

    # ========================================
    # CLEANUP METHODS
    # ========================================
        
    def cleanup(self):
        """Enhanced cleanup with NEMA support"""
        # Stop any NEMA operations
        if hasattr(self, 'nema_test_sweeping') and self.nema_test_sweeping:
            self.send_websocket_message("nema_stop_sweep")
        
        # Stop timers
        if hasattr(self, 'position_update_timer'):
            self.position_update_timer.stop()
        
        if hasattr(self, 'nema_status_timer'):
            self.nema_status_timer.stop()
        
        # Clean up NEMA connection
        if self.current_controller == 2:
            self.cleanup_nema_connection()
        
        # Stop all operations
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

