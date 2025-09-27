"""
WALL-E Control System - Complete Controller Configuration Screen
Fixed maestro detection and servo channel loading issue + Bluetooth controller support
"""

import json
from typing import Optional, Dict, Any, List
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QStackedWidget, QProgressBar, QFrame, QGridLayout, QComboBox,
    QSlider, QSpinBox, QGroupBox, QTextEdit, QCheckBox, QLineEdit, 
    QMessageBox, QScrollArea, QApplication
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from widgets.base_screen import BaseScreen
from core.config_manager import config_manager
from core.theme_manager import theme_manager
from core.utils import error_boundary
from widgets.controller_status_splash import show_controller_status_splash


# ========================================
# BEHAVIOR HANDLER CLASSES
# ========================================

class BehaviorHandler:
    """Base class for all behavior handlers"""
    
    def __init__(self, websocket_sender=None, logger=None):
        self.websocket_sender = websocket_sender
        self.logger = logger
    
    def process(self, control_name: str, raw_value: float, config: Dict[str, Any]) -> bool:
        """Process controller input with behavior-specific logic"""
        raise NotImplementedError
    
    def send_websocket_message(self, message_type: str, **kwargs):
        """Helper to send websocket messages"""
        if self.websocket_sender:
            self.websocket_sender(message_type, **kwargs)


class DirectServoHandler(BehaviorHandler):
    """Handle direct servo control - single axis to single servo"""
    
    def process(self, control_name: str, raw_value: float, config: Dict[str, Any]) -> bool:
        try:
            servo_channel = config.get('target')
            invert = config.get('invert', False)
            
            if not servo_channel:
                return False
            
            value = -raw_value if invert else raw_value
            pulse = 1500 + int(value * 500)
            pulse = max(1000, min(2000, pulse))
            
            self.send_websocket_message("servo", channel=servo_channel, pos=pulse)
            
            if self.logger:
                self.logger.debug(f"Direct servo {servo_channel}: {pulse} (raw: {raw_value})")
            
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error in direct servo handler: {e}")
            return False


class NemaStepperHandler(BehaviorHandler):
    """Handle NEMA stepper control - move between min/max positions or direct control"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_position = 0.0  # Track current position for toggle
        self.is_at_min = True  # Track which end we're at for toggle
        
    def process(self, control_name: str, raw_value: float, config: Dict[str, Any]) -> bool:
        try:
            behavior_type = config.get('nema_behavior', 'toggle_positions')
            trigger_timing = config.get('trigger_timing', 'on_press')
            threshold = 0.5
            
            if behavior_type == "toggle_positions":
                return self._handle_toggle_positions(control_name, raw_value, config, trigger_timing, threshold)
            elif behavior_type == "sweep_continuous":
                return self._handle_sweep_continuous(control_name, raw_value, config, trigger_timing, threshold)
            elif behavior_type == "direct_control":
                return self._handle_direct_control(control_name, raw_value, config)
            
            return False
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error in NEMA stepper handler: {e}")
            return False
    
    def _handle_toggle_positions(self, control_name: str, raw_value: float, config: Dict[str, Any], 
                                trigger_timing: str, threshold: float) -> bool:
        """Toggle between min and max positions on button press"""
        if trigger_timing == 'on_press' and raw_value > threshold:
            # Get NEMA config from controller config
            min_pos = config.get('min_position', 0.0)
            max_pos = config.get('max_position', 20.0)
            speed = config.get('normal_speed', 800)
            acceleration = config.get('acceleration', 800)
            
            # Determine target position
            target_position = max_pos if self.is_at_min else min_pos
            self.is_at_min = not self.is_at_min  # Toggle for next press
            
            # Send move command
            self.send_websocket_message("nema_move_to", 
                                      position_cm=target_position,
                                      speed=speed,
                                      acceleration=acceleration)
            
            if self.logger:
                self.logger.debug(f"NEMA toggle: Moving to {target_position:.1f} cm")
            
            return True
        
        return False
    
    def _handle_sweep_continuous(self, control_name: str, raw_value: float, config: Dict[str, Any], 
                                trigger_timing: str, threshold: float) -> bool:
        """Start/stop continuous sweeping between min and max"""
        if trigger_timing == 'on_press' and raw_value > threshold:
            min_pos = config.get('min_position', 0.0)
            max_pos = config.get('max_position', 20.0)
            speed = config.get('normal_speed', 800)
            acceleration = config.get('acceleration', 800)
            
            # Start sweep
            self.send_websocket_message("nema_sweep",
                                      min_position_cm=min_pos,
                                      max_position_cm=max_pos,
                                      speed=speed,
                                      acceleration=acceleration)
            
            if self.logger:
                self.logger.debug(f"NEMA sweep: {min_pos:.1f} to {max_pos:.1f} cm")
            
            return True
        
        return False
    
    def _handle_direct_control(self, control_name: str, raw_value: float, config: Dict[str, Any]) -> bool:
        """Direct position control using analog input"""
        min_pos = config.get('min_position', 0.0)
        max_pos = config.get('max_position', 20.0)
        speed = config.get('normal_speed', 800)
        acceleration = config.get('acceleration', 800)
        invert = config.get('invert', False)
        
        # Convert raw value (-1 to 1) to position
        value = -raw_value if invert else raw_value
        # Map from -1,1 to min,max position
        position_range = max_pos - min_pos
        target_position = min_pos + ((value + 1) / 2.0) * position_range
        
        # Clamp to valid range
        target_position = max(min_pos, min(max_pos, target_position))
        
        # Only send if position changed significantly (reduce spam)
        if abs(target_position - self.current_position) > 0.1:
            self.current_position = target_position
            
            self.send_websocket_message("nema_move_to",
                                      position_cm=target_position,
                                      speed=speed,
                                      acceleration=acceleration)
            
            if self.logger:
                self.logger.debug(f"NEMA direct: {target_position:.1f} cm (raw: {raw_value})")
        
        return True


class JoystickPairHandler(BehaviorHandler):
    """Handle joystick pair control - both X and Y axes"""
    
    def process(self, control_name: str, raw_value: float, config: Dict[str, Any]) -> bool:
        try:
            x_servo = config.get('x_servo')
            y_servo = config.get('y_servo')
            
            if not x_servo or not y_servo:
                return False
            
            if control_name.endswith('_x'):
                pulse = 1500 + int(raw_value * 500)
                pulse = max(1000, min(2000, pulse))
                self.send_websocket_message("servo", channel=x_servo, pos=pulse)
                return True
                
            elif control_name.endswith('_y'):
                pulse = 1500 + int(raw_value * 500) 
                pulse = max(1000, min(2000, pulse))
                self.send_websocket_message("servo", channel=y_servo, pos=pulse)
                return True
                
            return False
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error in joystick pair handler: {e}")
            return False


class DifferentialTracksHandler(BehaviorHandler):
    """Handle differential tracks control - tank steering"""
    
    def process(self, control_name: str, raw_value: float, config: Dict[str, Any]) -> bool:
        try:
            left_servo = config.get('left_servo')
            right_servo = config.get('right_servo')
            sensitivity = config.get('turn_sensitivity', 1.0)
            
            if not left_servo or not right_servo:
                return False
            
            if control_name.endswith('_x'):
                turn_input = raw_value * sensitivity
                left_speed, right_speed = self._calculate_differential_steering(turn_input, 0.0)
            elif control_name.endswith('_y'):
                forward_input = raw_value
                left_speed, right_speed = self._calculate_differential_steering(0.0, forward_input)
            else:
                return False
            
            left_pulse = 1500 + int(left_speed * 500)
            right_pulse = 1500 + int(right_speed * 500)
            
            left_pulse = max(1000, min(2000, left_pulse))
            right_pulse = max(1000, min(2000, right_pulse))
            
            self.send_websocket_message("servo", channel=left_servo, pos=left_pulse)
            self.send_websocket_message("servo", channel=right_servo, pos=right_pulse)
            
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error in differential tracks handler: {e}")
            return False
    
    def _calculate_differential_steering(self, turn_input: float, forward_input: float) -> tuple:
        """Calculate left and right track speeds"""
        if abs(turn_input) > 0.1:
            if turn_input > 0:  # Turn right
                left_speed = abs(turn_input)
                right_speed = -abs(turn_input)
            else:  # Turn left  
                left_speed = -abs(turn_input)
                right_speed = abs(turn_input)
        else:
            left_speed = forward_input
            right_speed = forward_input
        
        return max(-1.0, min(1.0, left_speed)), max(-1.0, min(1.0, right_speed))


class SceneTriggerHandler(BehaviorHandler):
    """Handle scene trigger behavior"""
    
    def process(self, control_name: str, raw_value: float, config: Dict[str, Any]) -> bool:
        try:
            scene_name = config.get('scene')
            trigger_timing = config.get('trigger_timing', 'on_press')
            threshold = 0.5
            
            if not scene_name:
                return False
            
            if trigger_timing == 'on_press' and raw_value > threshold:
                self.send_websocket_message("scene", emotion=scene_name)
                if self.logger:
                    self.logger.debug(f"Scene triggered: {scene_name}")
                return True
                
            return False
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error in scene trigger handler: {e}")
            return False


class ToggleScenesHandler(BehaviorHandler):
    """Handle toggling between two scenes"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_scene = 0
    
    def process(self, control_name: str, raw_value: float, config: Dict[str, Any]) -> bool:
        try:
            scene_1 = config.get('scene_1')
            scene_2 = config.get('scene_2')
            trigger_timing = config.get('trigger_timing', 'on_press')
            threshold = 0.5
            
            if not scene_1 or not scene_2:
                return False
            
            if trigger_timing == 'on_press' and raw_value > threshold:
                scene_to_trigger = scene_1 if self.current_scene == 0 else scene_2
                self.current_scene = 1 - self.current_scene
                
                self.send_websocket_message("scene", emotion=scene_to_trigger)
                if self.logger:
                    self.logger.debug(f"Toggle scene triggered: {scene_to_trigger}")
                return True
                
            return False
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error in toggle scenes handler: {e}")
            return False

class SystemControlHandler(BehaviorHandler):
    """Handle system control commands - exit app, restart, shutdown"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app_instance = None

    def set_app_instance(self, app_instance):
        """Set reference to the main application for direct exit handling"""
        self.app_instance = app_instance

    def process(self, control_name: str, raw_value: float, config: Dict[str, Any]) -> bool:
        try:
            action = config.get('system_action')
            trigger_timing = config.get('trigger_timing', 'on_press')
            threshold = 0.5
            
            if not action:
                return False
            
            if trigger_timing == 'on_press' and raw_value > threshold:
                if action == "exit_app":
                    self._handle_exit_app()
                    if self.logger:
                        self.logger.info("Exit app command triggered")
                elif action == "restart_app":
                    self._handle_restart_app()
                    if self.logger:
                        self.logger.info("Restart app command triggered")
                elif action == "restart_pi":
                    self.send_websocket_message("pi_control", action="restart")
                    if self.logger:
                        self.logger.info("Restart Pi command sent to backend")
                elif action == "shutdown_pi":
                    self.send_websocket_message("pi_control", action="shutdown")
                    if self.logger:
                        self.logger.info("Shutdown Pi command sent to backend")
                
                return True
                
            return False
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error in system control handler: {e}")
            return False

    def _handle_exit_app(self):
        """Handle exit app directly in frontend"""
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            from PyQt6.QtCore import QTimer
            from PyQt6.QtGui import QIcon, QPixmap
            
            # Get the main application window to use as parent for the dialog
            app = QApplication.instance()
            main_window = None
            for widget in app.topLevelWidgets():
                if hasattr(widget, 'close_application'):  # Look for the main DroidDeckApplication
                    main_window = widget
                    break
            
            # Create custom message box
            msg_box = QMessageBox(main_window)
            msg_box.setWindowTitle('Exit Application')
            msg_box.setText('Are you sure you want to exit the WALL-E control application?')
            msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg_box.setDefaultButton(QMessageBox.StandardButton.No)
            
            # Try to set a custom WALL-E icon
            try:
                # Option 1: Use a WALL-E icon from your resources
                # Replace "wall-e-icon.png" with your actual icon file path
                icon_path = "resources/icons/exit.png"  # or wherever your WALL-E icon is
                if os.path.exists(icon_path):
                    custom_icon = QIcon(icon_path)
                    msg_box.setIconPixmap(custom_icon.pixmap(64, 64))  # 64x64 pixel icon
                else:
                    # Option 2: Use a different built-in icon (no spaceship)
                    msg_box.setIcon(QMessageBox.Icon.Warning)  # Orange warning triangle
                    # Or try: QMessageBox.Icon.Information (blue 'i')
                    # Or: QMessageBox.Icon.Critical (red X)
            except Exception as e:
                # Fallback to warning icon if custom icon fails
                msg_box.setIcon(QMessageBox.Icon.Warning)
                if self.logger:
                    self.logger.debug(f"Could not load custom icon: {e}")
            
            # Style the message box to match your theme
            msg_box.setStyleSheet("""
                QMessageBox {
                    background-color: #2d2d2d;
                    color: white;
                    font-size: 14px;
                }
                QMessageBox QPushButton {
                    background-color: #1e90ff;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-size: 12px;
                    min-width: 60px;
                }
                QMessageBox QPushButton:hover {
                    background-color: #4dabf7;
                }
                QMessageBox QPushButton:pressed {
                    background-color: #0d7ae4;
                }
            """)
            
            # Show the dialog and get result
            reply = msg_box.exec()
            
            if reply == QMessageBox.StandardButton.Yes:
                if self.logger:
                    self.logger.info("User confirmed app exit via controller")
                
                # Try multiple exit methods
                if main_window and hasattr(main_window, 'close_application'):
                    # Use the main window's close method if available
                    QTimer.singleShot(100, main_window.close_application)
                else:
                    # Fallback to direct quit
                    QTimer.singleShot(100, app.quit)
            else:
                if self.logger:
                    self.logger.info("User cancelled app exit")
                    
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error handling exit app: {e}")
            # Emergency fallback - force quit
            try:
                QApplication.instance().quit()
            except:
                import sys
                sys.exit(0)

    def _handle_restart_app(self):
        """Handle restart app directly in frontend"""
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            from PyQt6.QtCore import QTimer
            import sys
            import os
            
            reply = QMessageBox.question(
                None, 
                'Restart Application', 
                'Are you sure you want to restart the WALL-E control application?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                if self.logger:
                    self.logger.info("User confirmed app restart via controller")
                
                def restart_app():
                    python = sys.executable
                    os.execl(python, python, *sys.argv)
                
                QTimer.singleShot(100, restart_app)
            else:
                if self.logger:
                    self.logger.info("User cancelled app restart")
                    
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error handling restart app: {e}")

# ========================================
# BEHAVIOR REGISTRY
# ========================================

class BehaviorHandlerRegistry:
    """Registry to manage different behavior handlers"""
    
    def __init__(self, websocket_sender=None, logger=None, app_instance=None):
        system_handler = SystemControlHandler(websocket_sender, logger)
        if app_instance:
            system_handler.set_app_instance(app_instance)
        
        self.handlers = {
            "direct_servo": DirectServoHandler(websocket_sender, logger),
            "joystick_pair": JoystickPairHandler(websocket_sender, logger),
            "differential_tracks": DifferentialTracksHandler(websocket_sender, logger),
            "scene_trigger": SceneTriggerHandler(websocket_sender, logger),
            "toggle_scenes": ToggleScenesHandler(websocket_sender, logger),
            "nema_stepper": NemaStepperHandler(websocket_sender, logger),
            "system_control": system_handler
        }
        self.active_mappings = {}
        self.logger = logger
    
    def register_mapping(self, control_name: str, behavior: str, config: Dict[str, Any]):
        """Register a new mapping"""
        self.active_mappings[control_name] = {
            'behavior': behavior,
            'config': config
        }
    
    def unregister_mapping(self, control_name: str):
        """Remove a mapping"""
        if control_name in self.active_mappings:
            del self.active_mappings[control_name]
    
    def process_input(self, control_name: str, raw_value: float, mapping_config: Dict[str, Any]) -> bool:
        """Process controller input through appropriate handler"""
        behavior = mapping_config.get('behavior')
        if behavior not in self.handlers:
            return False
        
        handler = self.handlers[behavior]
        return handler.process(control_name, raw_value, mapping_config)
    
    def get_joystick_conflict_info(self, control_name: str, behavior: str) -> Optional[str]:
        """Check for joystick behavior conflicts"""
        joystick_behaviors = ["joystick_pair", "differential_tracks"]
        
        if behavior not in joystick_behaviors:
            return None
        
        base_name = control_name.replace('_x', '').replace('_y', '')
        
        for existing_control, mapping in self.active_mappings.items():
            existing_base = existing_control.replace('_x', '').replace('_y', '')
            existing_behavior = mapping['behavior']
            
            if (existing_base == base_name and 
                existing_behavior in joystick_behaviors and 
                existing_behavior != behavior and
                existing_control != control_name):
                
                return f"Cannot mix different behaviors on the same joystick."
        
        return None


    # ========================================
# MAIN CONTROLLER CONFIGURATION CLASS
# ========================================

class ControllerConfigScreen(BaseScreen):
    """Controller configuration with all fixes applied including maestro detection and bluetooth controller support"""

    calibration_update = pyqtSignal(str, float)

    def __init__(self, websocket=None):
        self.behavior_registry = None
        self.mapping_rows = []
        self.selected_row_index = None
        self.parameters_panel = None
        self.config_frame = None
        self.controller_status_label = None
        
        # Add maestro tracking (like servo screen)
        self.maestro_channel_counts = {1: 0, 2: 0}
        self.maestro_connected = {1: False, 2: False}
        self._config_loaded = False

        super().__init__(websocket)
        theme_manager.register_callback(self.update_theme)

    def _init_ui(self):
        """Initialize the UI layout with proper padding"""
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(100, 25, 40, 15)

        # Main content - no more separate status frame
        config_section = self._create_config_section()
        main_layout.addWidget(config_section, stretch=3)
        
        params_section = self._create_parameters_section()  
        main_layout.addWidget(params_section, stretch=1)
        
        # Create overall layout - just the main layout, no status bar
        self.setLayout(main_layout)
        QTimer.singleShot(1000, self.request_controller_info)

    def _setup_screen(self):
        """Initialize controller configuration screen with maestro detection"""
        self.setFixedWidth(1200)
        
        # Get app instance for system control
        from PyQt6.QtWidgets import QApplication
        app_instance = QApplication.instance()
        
        self.behavior_registry = BehaviorHandlerRegistry(
            websocket_sender=self.send_websocket_message,
            logger=self.logger,
            app_instance=app_instance  # Pass app instance
        )
        
        self._load_predefined_options()
        self._init_ui()
        
        # Request maestro detection before loading config
        QTimer.singleShot(1000, self._detect_maestros)
        
        if self.websocket:
            self.websocket.textMessageReceived.connect(self.handle_controller_input)
            self.websocket.textMessageReceived.connect(self.handle_websocket_message)

    def _detect_maestros(self):
        """Request maestro detection to get available channels"""
        if self.websocket and self.websocket.is_connected():
            self.send_websocket_message("get_maestro_info", maestro=1)
            self.send_websocket_message("get_maestro_info", maestro=2)
            self.request_controller_info()
            self.logger.info("Requesting maestro detection for controller config")
        else:
            self.logger.warning("WebSocket not connected - using fallback channel list")
            # Use fallback then load existing config
            QTimer.singleShot(2000, self._load_existing_configuration)

    # Add this to your controller_screen.py handle_websocket_message method

    def handle_websocket_message(self, message):
        """Handle WebSocket messages including maestro detection and system control commands"""
        try:
            self.handle_controller_input_for_status(message)
            msg = json.loads(message)
            msg_type = msg.get("type")
            
            if msg_type == "maestro_info":
                self._handle_maestro_info(msg)
            elif msg_type == "controller_info":
                self.handle_controller_info_response(msg)
            elif msg_type == "controller_input":
                # This is already handled by handle_controller_input
                pass
            elif msg_type == "system_control_command":  # ADD THIS
                self._handle_system_control_command(msg)
                
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error handling WebSocket message: {e}")

    def _handle_system_control_command(self, msg):
        """Handle system control commands routed from backend"""
        try:
            action = msg.get("action")
            control_name = msg.get("control_name")
            config = msg.get("config", {})
            
            if not action:
                self.logger.warning("System control command missing action")
                return
            
            self.logger.info(f"Received system control command from backend: {action}")
            
            # Create a mock mapping config and process through behavior registry
            mapping_config = {
                'behavior': 'system_control',
                'system_action': action,
                **config
            }
            
            # Process through the frontend system control handler
            success = self.behavior_registry.process_input(
                control_name, 1.0, mapping_config  # Use 1.0 as "button pressed"
            )
            
            if success:
                self.logger.info(f"System control '{action}' executed successfully")
            else:
                self.logger.warning(f"System control '{action}' failed to execute")
                
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error handling system control command: {e}")

    def open_controller_status(self):
        """Open controller status display splash"""
        try:
            from PyQt6.QtWidgets import QApplication
            
            self.controller_status_splash = show_controller_status_splash(self)
            
            # Get the main application instance to access the controller thread
            app = QApplication.instance()
            main_window = None
            for widget in app.topLevelWidgets():
                if hasattr(widget, 'controller_thread'):
                    main_window = widget
                    break
            
            if main_window and hasattr(main_window, 'controller_thread'):
                controller_thread = main_window.controller_thread
                
                # Connect signals for live updates - but don't duplicate existing connections
                try:
                    controller_thread.controller_input.disconnect(self.controller_status_splash.update_controller_input)
                except:
                    pass  # Connection didn't exist
                
                try:
                    controller_thread.controller_connected.disconnect()
                except:
                    pass
                    
                try:
                    controller_thread.controller_disconnected.disconnect()
                except:
                    pass
                
                # Now connect the signals
                controller_thread.controller_input.connect(
                    self.controller_status_splash.update_controller_input
                )
                controller_thread.controller_connected.connect(
                    lambda name, id: self.controller_status_splash.set_controller_info(name, True)
                )
                controller_thread.controller_disconnected.connect(
                    lambda reason: self.controller_status_splash.set_controller_info(f"Disconnected: {reason}", False)
                )
                
                # Set initial controller info
                controller_info = controller_thread.get_controller_info()
                self.controller_status_splash.set_controller_info(
                    controller_info.get("controller_name", "Steam Deck Controller"),
                    controller_info.get("connected", False)
                )
                
                self.logger.info("Controller status splash connected to controller thread")
            else:
                self.logger.warning("No controller thread available for status display")
                self.controller_status_splash.set_controller_info("No Controller Thread", False)
                    
        except Exception as e:
            self.logger.error(f"Failed to open controller status splash: {e}")

    def handle_controller_input_signal(self, input_data):
        """Handle controller input from the Qt signal (thread-safe)"""
        try:
            # Update controller status to show it's connected and active
            if hasattr(self, 'controller_status_label'):
                self.controller_status_label.setText("Connected & Active")
                self.controller_status_label.setStyleSheet("color: #51cf66; margin-left: 10px; border: none; background: transparent;")
            
            # Process the input data through your existing behavior registry
            if self.behavior_registry:
                # Convert ControllerInputData to the format expected by behavior registry
                for axis_name, value in input_data.axes.items():
                    if abs(value) > 0.1:  # Only process significant movements
                        self.behavior_registry.process_input(axis_name, value, {})
                
                for button_name, pressed in input_data.buttons.items():
                    if pressed:  # Only process button presses
                        self.behavior_registry.process_input(button_name, 1.0, {})
            
            # Forward to controller status splash if open
            if hasattr(self, 'controller_status_splash') and self.controller_status_splash and self.controller_status_splash.isVisible():
                self.controller_status_splash.update_controller_input(input_data)
                
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"Error handling controller input signal: {e}")

    def update_controller_status(self, status_text: str, connected: bool):
        """Update controller status display (thread-safe)"""
        try:
            if hasattr(self, 'controller_status_label'):
                self.controller_status_label.setText(status_text)
                if connected:
                    self.controller_status_label.setStyleSheet("color: #51cf66; margin-left: 10px; border: none; background: transparent;")
                else:
                    self.controller_status_label.setStyleSheet("color: #ff6b6b; margin-left: 10px; border: none; background: transparent;")
                    
            # Also update the splash if it's open
            if hasattr(self, 'controller_status_splash') and self.controller_status_splash and self.controller_status_splash.isVisible():
                controller_name = status_text.replace("Connected: ", "").replace("Disconnected: ", "")
                self.controller_status_splash.set_controller_info(controller_name, connected)
                
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"Error updating controller status: {e}")


    def handle_controller_input_for_status(self, message: str):
        """Handle WebSocket controller input for status display"""
        try:
            if hasattr(self, 'controller_status_splash') and self.controller_status_splash.isVisible():
                msg = json.loads(message)
                
                if msg.get("type") == "steamdeck_controller":
                    # Create ControllerInputData from WebSocket message
                    from threads.steamdeck_controller import ControllerInputData
                    
                    input_data = ControllerInputData(
                        axes=msg.get("axes", {}),
                        buttons=msg.get("buttons", {}),
                        timestamp=msg.get("timestamp", time.time()),
                        sequence=msg.get("sequence", 0)
                    )
                    
                    self.controller_status_splash.update_controller_input(input_data)
                    
        except Exception as e:
            self.logger.error(f"Error handling controller input for status: {e}")
        

    def _handle_maestro_info(self, data):
        """Handle maestro detection results"""
        maestro_num = data.get("maestro")
        channels = data.get("channels", 0)
        connected = data.get("connected", False)
        
        if maestro_num in [1, 2]:
            self.maestro_channel_counts[maestro_num] = channels
            self.maestro_connected[maestro_num] = connected
            
            if self.logger:
                self.logger.info(f"Controller config - Maestro {maestro_num}: {channels} channels, connected: {connected}")
            
            # Update servo channels list
            self._update_servo_channels()
            
            # Load existing configuration after we have maestro info
            if not self._config_loaded:
                self._config_loaded = True
                QTimer.singleShot(500, self._load_existing_configuration)

    def _update_servo_channels(self):
        """Update servo channels based on detected maestros"""
        self.servo_channels = []
        
        for maestro_num in [1, 2]:
            if self.maestro_connected.get(maestro_num, False):
                channel_count = self.maestro_channel_counts.get(maestro_num, 0)
                for ch in range(channel_count):
                    self.servo_channels.append(f"m{maestro_num}_ch{ch}")
        
        if not self.servo_channels:
            # Fallback if no maestros detected
            self.servo_channels = [f"m{m}_ch{c}" for m in [1, 2] for c in range(24)]
        
        if self.logger:
            self.logger.info(f"Updated servo channels: {len(self.servo_channels)} channels available")

    def _load_predefined_options(self):
        """Load predefined dropdown options from configs - now supports multiple controller types"""
        # Steam Deck inputs (default)
        self.steam_inputs = [
            # Axes
            "left_stick_x", "left_stick_y", 
            "left_trigger",
            "right_stick_x", "right_stick_y",
            "right_trigger",
            # Buttons
            "button_a", "button_b", "button_x", "button_y",
            "shoulder_left", "shoulder_right",
            "button_menu",
            "trigger_left_click", "trigger_right_click",
            "stick_left_click", "stick_right_click",
            "dpad_up", "dpad_down", "dpad_left", "dpad_right"
        ]
        
        # Start with Steam Deck as default - will be updated when controller connects
        self.current_inputs = self.steam_inputs.copy()
        
        self.input_types = ["joystick", "trigger", "button", "dpad"]
        
        self.behaviors = [
            "direct_servo", "joystick_pair", "differential_tracks", 
            "scene_trigger", "toggle_scenes", "nema_stepper", "system_control"
        ]
        
        # Don't load servo channels here - wait for maestro detection
        self.servo_channels = []  # Will be populated by maestro detection
        
        # Load scene names properly
        self.scene_names = []
        try:
            scenes_config = config_manager.get_config("resources/configs/scenes_config.json")
            if isinstance(scenes_config, list) and scenes_config:
                self.scene_names = [scene.get("label", "Unknown") for scene in scenes_config if scene.get("label")]
        except Exception:
            pass
        
        if not self.scene_names:
            try:
                motion_config = config_manager.get_config("resources/configs/motion_config.json")
                self.scene_names = motion_config.get("emotions", [])
            except Exception:
                self.scene_names = ["Happy", "Sad", "Curious", "Excited", "Alert"]

# Update the ControllerConfigScreen._setup_screen method to pass app instance:

    def _setup_screen(self):
        """Initialize controller configuration screen with maestro detection"""
        self.setFixedWidth(1200)
        
        # Get app instance for system control
        from PyQt6.QtWidgets import QApplication
        app_instance = QApplication.instance()
        
        self.behavior_registry = BehaviorHandlerRegistry(
            websocket_sender=self.send_websocket_message,
            logger=self.logger,
            app_instance=app_instance  # Pass app instance
        )
        
        self._load_predefined_options()
        self._init_ui()
        
        # Request maestro detection before loading config
        QTimer.singleShot(1000, self._detect_maestros)
        
        if self.websocket:
            self.websocket.textMessageReceived.connect(self.handle_controller_input)
            self.websocket.textMessageReceived.connect(self.handle_websocket_message)


    # Update the parameter creation to show which actions are handled where:

    def _create_system_control_params(self, row_data: Dict):
        """Create parameters for system control behavior"""
        # Header without border - direct styling
        header = QLabel("System Control Configuration")
        header.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        primary_color = theme_manager.get("primary_color")
        header.setStyleSheet(f"color: {primary_color}; padding: 6px 0px; margin-bottom: 10px; border: none; background: transparent;")
        self.params_layout.addWidget(header)
        
        control_name = row_data['input_combo'].currentText()
        if control_name != "Select Input...":
            axis_info = QLabel(f"Controls system using {control_name}")
            grey = theme_manager.get("grey")
            axis_info.setStyleSheet(f"color: {grey}; font-style: italic; padding: 3px 0px; font-size: 10px; border: none; background: transparent;")
            self.params_layout.addWidget(axis_info)
        
        # System Action combo with clean label
        action_combo = QComboBox()
        system_actions = ["up", "down", "left", "right", "select", "exit", "exit_app", "restart_app", "restart_pi", "shutdown_pi"]
        action_combo.addItems(["Select Action..."] + system_actions)
        if 'system_action' in row_data['config']:
            action_combo.setCurrentText(row_data['config']['system_action'])
        action_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'system_action', text)
        )
        action_combo.setStyleSheet(self._get_combo_style())
        
        # Add label and combo manually with clean label styling
        label1 = QLabel("System Action:")
        label1.setStyleSheet("color: white; padding: 3px 0px; font-size: 10px; border: none; background: transparent;")
        self.params_layout.addWidget(label1)
        self.params_layout.addWidget(action_combo)
        self.params_layout.addSpacing(6)
        
        # Trigger Timing combo with clean label
        timing_combo = QComboBox()
        timing_combo.addItems(["on_press", "on_release"])
        timing_combo.setCurrentText(row_data['config'].get('trigger_timing', 'on_press'))
        timing_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'trigger_timing', text)
        )
        timing_combo.setStyleSheet(self._get_combo_style())
        
        # Add label and combo manually with clean label styling
        label2 = QLabel("Trigger Timing:")
        label2.setStyleSheet("color: white; padding: 3px 0px; font-size: 10px; border: none; background: transparent;")
        self.params_layout.addWidget(label2)
        self.params_layout.addWidget(timing_combo)
        self.params_layout.addSpacing(6)
        
        # Action descriptions with location info
        descriptions = {
            "up": "Navigate up in menus",
            "down": "Navigate down in menus",
            "left": "Navigate left in menus",
            "right": "Navigate right in menus",
            "select": "Select/confirm in menus",
            "exit_app": "Close app", 
            "restart_pi": "Reboot the Raspberry Pi",
            "shutdown_pi": "Shutdown the Raspberry Pi"
        }
        
        current_action = row_data['config'].get('system_action', 'Not configured')
        if current_action in descriptions:
            desc_label = QLabel(f"📝 {descriptions[current_action]}")
            desc_label.setStyleSheet(f"color: #4CAF50; padding: 8px; background-color: rgba(76, 175, 80, 0.1); border-radius: 4px; font-size: 10px; font-style: italic; border: none;")
            desc_label.setWordWrap(True)
            self.params_layout.addWidget(desc_label)
        
        # Warning for destructive actions
        if current_action in ["restart_pi", "shutdown_pi"]:
            warning_label = QLabel("⚠️ WARNING: This will affect the entire Raspberry Pi system!")
            warning_label.setStyleSheet(f"color: #F44336; padding: 6px; background-color: rgba(244, 67, 54, 0.1); border-radius: 4px; font-size: 10px; font-weight: bold; border: none;")
            warning_label.setWordWrap(True)
            self.params_layout.addWidget(warning_label)
        elif current_action in ["exit_app", "restart_app"]:
            info_label = QLabel("ℹ️ This action includes a confirmation dialog for safety")
            info_label.setStyleSheet(f"color: #2196F3; padding: 6px; background-color: rgba(33, 150, 243, 0.1); border-radius: 4px; font-size: 10px; border: none;")
            info_label.setWordWrap(True)
            self.params_layout.addWidget(info_label)
        
        action = row_data['config'].get('system_action', 'Not configured')
        row_data['target_label'].setText(f"→ {action}")

    def _load_existing_configuration(self):
        """Load existing controller configuration on startup"""
        try:
            config = config_manager.get_config("resources/configs/controller_config.json")
            if config and isinstance(config, dict):
                for control_name, control_config in config.items():
                    self._add_mapping_row_from_config(control_name, control_config)
                
                if self.logger:
                    self.logger.info(f"Loaded {len(config)} existing controller mappings")
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Could not load controller config: {e}")

    def update_available_inputs(self, controller_type: str, available_inputs: list):
        """Update available inputs based on connected controller type"""
        if controller_type.lower() in ['wii', 'wiimote', 'nintendo']:
            self.current_inputs = available_inputs if available_inputs else self.wii_inputs
            controller_name = "Wii Remote"
        else:
            self.current_inputs = available_inputs if available_inputs else self.steam_inputs  
            controller_name = "Steam Deck"
        
        # Update all input combo boxes
        for row_data in self.mapping_rows:
            current_selection = row_data['input_combo'].currentText()
            row_data['input_combo'].clear()
            row_data['input_combo'].addItems(["Select Input..."] + self.current_inputs)
            
            # Restore selection if still valid
            if current_selection in self.current_inputs:
                row_data['input_combo'].setCurrentText(current_selection)
        
        if self.logger:
            self.logger.info(f"Updated input options for {controller_name}: {len(self.current_inputs)} inputs available")

    def _add_mapping_row_from_config(self, control_name: str, control_config: Dict):
        """Add a mapping row from saved configuration - updated to use current_inputs"""
        try:
            row = len(self.mapping_rows)
            
            input_combo = QComboBox()
            input_combo.addItems(["Select Input..."] + self.current_inputs)  # Use current_inputs
            input_combo.setCurrentText(control_name)
            input_combo.setStyleSheet(self._get_combo_style())
            
            behavior = control_config.get('behavior', 'direct_servo')
            type_combo = QComboBox()
            type_combo.addItems(["Select Type..."] + self.input_types)
            type_combo.setStyleSheet(self._get_combo_style())
            
            behavior_combo = QComboBox()
            behavior_combo.addItems(["Select Behavior..."] + self.behaviors)
            behavior_combo.setCurrentText(behavior)
            behavior_combo.setStyleSheet(self._get_combo_style())
            
            target_text = self._get_target_display_text(behavior, control_config)
            target_label = QLabel(target_text)
            target_label.setStyleSheet(self._get_target_label_style())
            
            actions_layout = QHBoxLayout()
            select_btn = QPushButton("Configure")
            select_btn.clicked.connect(lambda: self._select_row_for_config(row))
            select_btn.setStyleSheet(self._get_small_button_style())
            
            remove_btn = QPushButton("×")
            remove_btn.clicked.connect(lambda: self._remove_mapping_row(row))
            remove_btn.setStyleSheet(self._get_remove_button_style())
            
            actions_layout.addWidget(select_btn)
            actions_layout.addWidget(remove_btn)
            actions_widget = QWidget()
            actions_widget.setLayout(actions_layout)
            actions_widget.setStyleSheet("border:none; padding:0px;")
            
            self.grid_layout.addWidget(input_combo, row, 0)
            self.grid_layout.addWidget(type_combo, row, 1) 
            self.grid_layout.addWidget(behavior_combo, row, 2)
            self.grid_layout.addWidget(target_label, row, 3)
            self.grid_layout.addWidget(actions_widget, row, 4)
            
            row_data = {
                'input_combo': input_combo,
                'type_combo': type_combo,
                'behavior_combo': behavior_combo,
                'target_label': target_label,
                'select_btn': select_btn,
                'remove_btn': remove_btn,
                'config': control_config.copy(),
                'conflict_detected': False
            }
            
            input_combo.currentTextChanged.connect(lambda: self._check_for_conflicts())
            behavior_combo.currentTextChanged.connect(lambda text: self._on_behavior_changed(row, text))
            
            self.mapping_rows.append(row_data)
            
            # Register with behavior registry
            self.behavior_registry.register_mapping(control_name, behavior, control_config)
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error adding mapping row from config: {e}")

    def request_controller_info(self):
        """Request controller information from backend"""
        if self.websocket and self.websocket.is_connected():
            self.send_websocket_message("get_controller_info")
            if self.logger:
                self.logger.info("Requested controller info from backend")

    def handle_controller_info_response(self, data: Dict):
        """Handle controller info response from backend"""
        try:

            if not hasattr(self, 'controller_status_label') or self.controller_status_label is None:
                if self.logger:
                    self.logger.warning("Controller status label not yet initialized")
                return
        
            try:
                # This will raise RuntimeError if C++ object has been deleted
                self.controller_status_label.text()
            except RuntimeError:
                if self.logger:
                    self.logger.warning("Controller status label has been deleted")
                return

            controller_info = data.get("controller_info", {})
            connected = controller_info.get("connected", False)
            controller_type = controller_info.get("controller_type", "unknown")
            controller_name = controller_info.get("controller_name", "Unknown")
            available_inputs = controller_info.get("available_inputs", [])
            
            if connected:
                # Update UI to show controller is connected
                if hasattr(self, 'controller_status_label'):
                    self.controller_status_label.setText(f"Connected: {controller_name}")
                    self.controller_status_label.setStyleSheet("color: #4CAF50;border: none; background: transparent; padding: 0px;")  # Green
                
                # Update available inputs
                if available_inputs:
                    self.update_available_inputs(controller_type, available_inputs)
            else:
                # Show disconnected status
                if hasattr(self, 'controller_status_label'):
                    self.controller_status_label.setText("No controller connected")
                    self.controller_status_label.setStyleSheet("color: #F44336;border: none; background: transparent; padding: 0px;")  # Red
            
            if self.logger:
                self.logger.info(f"Controller info updated: {controller_name} ({controller_type})")
                
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error handling controller info response: {e}")

    def __del__(self):
        """Clean up theme manager callback on destruction"""
        try:
            theme_manager.unregister_callback(self.update_theme)
        except Exception:
            pass  # Ignore errors during cleanup

    def _get_target_display_text(self, behavior: str, config: Dict[str, Any]) -> str:
        """Get display text for target column based on behavior and config"""
        if behavior == "direct_servo":
            target = config.get('target', 'Not configured')
            return f"→ {target}"
        elif behavior == "joystick_pair":
            x_servo = config.get('x_servo', '?')
            y_servo = config.get('y_servo', '?')
            return f"→ X:{x_servo}, Y:{y_servo}"
        elif behavior == "differential_tracks":
            left = config.get('left_servo', '?')
            right = config.get('right_servo', '?')
            return f"→ L:{left}, R:{right}"
        elif behavior == "scene_trigger":
            scene = config.get('scene', 'Not configured')
            return f"→ {scene}"
        elif behavior == "toggle_scenes":
            scene1 = config.get('scene_1', '?')
            scene2 = config.get('scene_2', '?')
            return f"→ {scene1} ⟷ {scene2}"
        elif behavior == "nema_stepper":
            mode = config.get('nema_behavior', 'Not configured')
            min_pos = config.get('min_position', '?')
            max_pos = config.get('max_position', '?')
            return f"→ NEMA {mode}: {min_pos}-{max_pos}cm"
        elif behavior == "system_control":  # ADD THIS
            action = config.get('system_action', 'Not configured')
            return f"→ {action}"
        else:
            return "Configure targets →"

    def _init_ui(self):
        """Initialize the UI layout with proper padding"""
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(100, 25, 40, 15)

        # Main content - no more separate status frame
        config_section = self._create_config_section()
        main_layout.addWidget(config_section, stretch=3)
        
        params_section = self._create_parameters_section()  
        main_layout.addWidget(params_section, stretch=1)
        
        # Create overall layout - just the main layout, no status bar
        self.setLayout(main_layout)
        QTimer.singleShot(1000, self.request_controller_info)

    def _create_config_section(self):
        """Create the main configuration grid section"""
        self.config_frame = QFrame()
        self.update_config_frame_style()
        layout = QVBoxLayout(self.config_frame)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Status and controls header (replaces the title)
        status_header_layout = QHBoxLayout()
        status_header_layout.setContentsMargins(0, 0, 0, 10)
        
        # Controller status on the left
        status_label = QLabel("Controller Status:")
        status_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.controller_status_label = QLabel("Checking...")
        
        # Apply status styling
        status_label.setStyleSheet("color: #cccccc; border: none; background: transparent;")
        self.controller_status_label.setStyleSheet("color: #ff6b6b; margin-left: 10px; border: none; background: transparent;")
        
        status_header_layout.addWidget(status_label)
        status_header_layout.addWidget(self.controller_status_label)
        status_header_layout.addStretch()  # Push buttons to the right
        
        # Control buttons on the right
        self.calibration_button = QPushButton("Controller Calibration")
        self.calibration_button.setStyleSheet("""
            QPushButton {
                background-color: #1e90ff;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #4dabf7; }
            QPushButton:disabled { background-color: #555555; }
        """)
        self.calibration_button.clicked.connect(self.open_calibration_dialog)
                
        # Add the Controller Status button
        self.status_button = QPushButton("Controller Status")
        self.status_button.setStyleSheet("""
            QPushButton {
                background-color: #51cf66;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                font-size: 12px;
                font-weight: bold;
                margin-left: 10px;
            }
            QPushButton:hover { background-color: #69db7c; }
            QPushButton:disabled { background-color: #555555; }
        """)
        self.status_button.clicked.connect(self.open_controller_status)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #666666;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                font-size: 12px;
                margin-left: 10px;
            }
            QPushButton:hover { background-color: #777777; }
        """)
        self.refresh_btn.clicked.connect(self.request_controller_info)
        
        status_header_layout.addWidget(self.calibration_button)
        status_header_layout.addWidget(self.status_button)  
        status_header_layout.addWidget(self.refresh_btn)
        
        layout.addLayout(status_header_layout)
        
        # Conflict warning
        self.conflict_warning = QLabel("")
        self.conflict_warning.setWordWrap(True)
        self.update_conflict_warning_style()
        self.conflict_warning.hide()
        layout.addWidget(self.conflict_warning)
        
        # Headers with proper alignment
        headers_layout = QGridLayout()
        headers_layout.setHorizontalSpacing(10)
        headers_layout.setVerticalSpacing(10)
        headers_layout.setContentsMargins(0, 0, 0, 0)
        
        headers = ["Input", "Type", "Behavior", "Target(s)", "Actions"]
        
        self.header_labels = []
        for i, header_text in enumerate(headers):
            header_label = QLabel(header_text)
            header_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            self.update_column_header_style(header_label)
            header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            headers_layout.addWidget(header_label, 0, i)
            self.header_labels.append(header_label)
        
        # Set column stretch factors
        headers_layout.setColumnStretch(0, 2)
        headers_layout.setColumnStretch(1, 1)
        headers_layout.setColumnStretch(2, 2)
        headers_layout.setColumnStretch(3, 3)
        headers_layout.setColumnStretch(4, 1)
        
        layout.addLayout(headers_layout)
        
        # Scroll area for the grid
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.update_scroll_area_style()
        
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        
        self.grid_layout.setHorizontalSpacing(10)
        self.grid_layout.setVerticalSpacing(10)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        
        # Apply same column stretch factors
        self.grid_layout.setColumnStretch(0, 2)
        self.grid_layout.setColumnStretch(1, 1)
        self.grid_layout.setColumnStretch(2, 2)
        self.grid_layout.setColumnStretch(3, 3)
        self.grid_layout.setColumnStretch(4, 1)
        
        self.scroll_area.setWidget(self.grid_widget)
        layout.addWidget(self.scroll_area)
        
        # Control buttons at bottom
        buttons_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add Mapping")
        self.add_btn.clicked.connect(self._add_mapping_row)
        self.update_button_style(self.add_btn)
        buttons_layout.addWidget(self.add_btn)
        
        self.save_btn = QPushButton("Save All")
        self.save_btn.clicked.connect(self._save_all_mappings)
        self.update_button_style(self.save_btn)
        buttons_layout.addWidget(self.save_btn)
        
        layout.addLayout(buttons_layout)
        
        return self.config_frame

    def _create_header_with_calibration_button(self):
        """Create header layout with calibration button if one doesn't exist"""
        # Create header layout
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 10)
        
        # Main title
        title_label = QLabel("Controller Configuration")
        title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #1e90ff; margin: 10px 0;")
        header_layout.addWidget(title_label)
        
        # Stretch to push button right
        header_layout.addStretch()
        
        # Calibration button
        self.calibration_button = QPushButton("🎮 Controller Calibration")
        self.calibration_button.setStyleSheet("""
            QPushButton {
                background-color: #1e90ff;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #4dabf7; }
            QPushButton:disabled { background-color: #555555; }
        """)
        self.calibration_button.clicked.connect(self.open_calibration_dialog)
        header_layout.addWidget(self.calibration_button)
        
        # Insert at top of main layout
        if hasattr(self, 'layout'):
            self.layout().insertWidget(0, header_widget)
    
    def open_calibration_dialog(self):
        """Open the controller calibration dialog"""
        try:
            # Import here to avoid circular imports
            from widgets.controller_calibration_screen import ControllerCalibrationDialog
            
            dialog = ControllerCalibrationDialog(
                websocket=self.websocket,
                parent=self
            )
            
            # Connect completion signal
            dialog.calibration_completed.connect(self.on_calibration_completed)
            
            # Show dialog
            result = dialog.exec()
            
            if result == QDialog.DialogCode.Accepted:
                self.logger.info("Controller calibration completed successfully")
            else:
                self.logger.info("Controller calibration cancelled")
                
        except ImportError as e:
            self.logger.error(f"Failed to import calibration dialog: {e}")
            self.show_error_message("Calibration Error", 
                                  "Failed to load calibration interface. Please check the installation.")
        except Exception as e:
            self.logger.error(f"Failed to open calibration dialog: {e}")
            self.show_error_message("Calibration Error", 
                                  f"Failed to open calibration dialog: {str(e)}")
    
    def on_calibration_completed(self, calibration_data: dict):
        """Handle completion of controller calibration"""
        self.logger.info("Controller calibration data received")
        
        # Optionally refresh the controller configuration
        # to reflect any changes made during calibration
        self._refresh_controller_mappings()
        
        # Show success message
        self.show_info_message("Calibration Complete", 
                              "Controller calibration completed successfully!\n"
                              "New settings have been applied.")
    
    def show_error_message(self, title: str, message: str):
        """Show error message dialog"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #2d2d2d;
                color: white;
            }
            QMessageBox QPushButton {
                background-color: #1e90ff;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 3px;
            }
            QMessageBox QPushButton:hover {
                background-color: #4dabf7;
            }
        """)
        msg_box.exec()
    
    def show_info_message(self, title: str, message: str):
        """Show info message dialog"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #2d2d2d;
                color: white;
            }
            QMessageBox QPushButton {
                background-color: #1e90ff;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 3px;
            }
            QMessageBox QPushButton:hover {
                background-color: #4dabf7;
            }
        """)
        msg_box.exec()
    
    def _refresh_controller_mappings(self):
        """Refresh controller mappings after calibration"""
        # This method can be used to reload mappings or update displays
        # based on the new calibration data
        if hasattr(self, 'mapping_rows') and self.mapping_rows:
            self.logger.info("Refreshing controller mappings with new calibration")
            # Add any specific refresh logic here if needed




    def _create_parameters_section(self):
        """Create the parameters panel section"""
        self.parameters_panel = QFrame()
        self.parameters_panel.setFixedWidth(280)
        self.update_parameters_panel_style()
        
        layout = QVBoxLayout(self.parameters_panel)
        layout.setContentsMargins(6, 12, 6, 12)
        
        self.params_header = QLabel("BEHAVIOR PARAMETERS")
        self.params_header.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        self.params_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_params_header_style()
        layout.addWidget(self.params_header)
        
        self.params_container = QWidget()
        self.params_layout = QVBoxLayout(self.params_container)
        layout.addWidget(self.params_container)
        
        self._show_no_selection_message()
        
        layout.addStretch()
        return self.parameters_panel
    
    def _show_no_selection_message(self):
        """Show message when no row is selected"""
        self._clear_parameters_layout()
        
        self.no_selection_label = QLabel("Select a mapping row to configure behavior-specific parameters.\n\nNote: Combined joystick behaviors use both X and Y axes.")
        self.no_selection_label.setWordWrap(True)
        self.update_no_selection_style()
        self.no_selection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.params_layout.addWidget(self.no_selection_label)

    def _add_mapping_row(self):
        """Add a new mapping configuration row - updated to use current_inputs"""
        row = len(self.mapping_rows)
        
        input_combo = QComboBox()
        input_combo.addItems(["Select Input..."] + self.current_inputs)
        input_combo.setStyleSheet(self._get_combo_style())
        
        type_combo = QComboBox()
        type_combo.addItems(["Select Type..."] + self.input_types)
        type_combo.setStyleSheet(self._get_combo_style())
        
        behavior_combo = QComboBox()
        behavior_combo.addItems(["Select Behavior..."] + self.behaviors)
        behavior_combo.setStyleSheet(self._get_combo_style())
        
        target_label = QLabel("Configure targets →")
        target_label.setStyleSheet(self._get_target_label_style())
        
        actions_layout = QHBoxLayout()
        select_btn = QPushButton("Configure")
        select_btn.clicked.connect(lambda: self._select_row_for_config(row))
        select_btn.setStyleSheet(self._get_small_button_style())
        
        remove_btn = QPushButton("×")
        remove_btn.clicked.connect(lambda: self._remove_mapping_row(row))
        remove_btn.setStyleSheet(self._get_remove_button_style())
        
        actions_layout.addWidget(select_btn)
        actions_layout.addWidget(remove_btn)
        actions_widget = QWidget()
        actions_widget.setLayout(actions_layout)
        
        self.grid_layout.addWidget(input_combo, row, 0)
        self.grid_layout.addWidget(type_combo, row, 1) 
        self.grid_layout.addWidget(behavior_combo, row, 2)
        self.grid_layout.addWidget(target_label, row, 3)
        self.grid_layout.addWidget(actions_widget, row, 4)
        
        row_data = {
            'input_combo': input_combo,
            'type_combo': type_combo,
            'behavior_combo': behavior_combo,
            'target_label': target_label,
            'select_btn': select_btn,
            'remove_btn': remove_btn,
            'config': {},
            'conflict_detected': False
        }
        
        input_combo.currentTextChanged.connect(lambda: self._check_for_conflicts())
        behavior_combo.currentTextChanged.connect(lambda text: self._on_behavior_changed(row, text))
        
        self.mapping_rows.append(row_data)
    
    def _check_for_conflicts(self):
        """Check for joystick axis conflicts and update UI"""
        conflicts_found = []
        
        for i, row_data in enumerate(self.mapping_rows):
            control_name = row_data['input_combo'].currentText()
            behavior = row_data['behavior_combo'].currentText()
            
            if control_name != "Select Input..." and behavior != "Select Behavior...":
                conflict_info = self.behavior_registry.get_joystick_conflict_info(control_name, behavior)
                if conflict_info:
                    conflicts_found.append(f"Row {i+1}: {conflict_info}")
                    row_data['conflict_detected'] = True
                    row_data['input_combo'].setStyleSheet(self._get_combo_style(error=True))
                else:
                    row_data['conflict_detected'] = False
                    row_data['input_combo'].setStyleSheet(self._get_combo_style())
        
        if conflicts_found:
            self.conflict_warning.setText("\n".join(conflicts_found))
            self.conflict_warning.show()
        else:
            self.conflict_warning.hide()

    def _on_behavior_changed(self, row_index: int, behavior: str):
        """Handle behavior selection change"""
        if behavior == "Select Behavior...":
            return
            
        if row_index < len(self.mapping_rows):
            row_data = self.mapping_rows[row_index]
            row_data['config'] = {}
            row_data['target_label'].setText("Configure targets →")
            
            if self.selected_row_index == row_index:
                self._create_behavior_parameters(row_data)

    def _select_row_for_config(self, row_index: int):
        """Select a row for configuration"""
        if row_index >= len(self.mapping_rows):
            return
            
        self.selected_row_index = row_index
        row_data = self.mapping_rows[row_index]
        
        # Update button states
        for i, rd in enumerate(self.mapping_rows):
            if i == row_index:
                rd['select_btn'].setText("Selected")
                rd['select_btn'].setStyleSheet(self._get_small_button_style(selected=True))
            else:
                rd['select_btn'].setText("Configure")
                rd['select_btn'].setStyleSheet(self._get_small_button_style())
        
        self._create_behavior_parameters(row_data)

    def _create_behavior_parameters(self, row_data: Dict):
        """Create behavior-specific parameter controls"""
        self._clear_parameters_layout()
        
        behavior = row_data['behavior_combo'].currentText()
        if behavior == "Select Behavior...":
            self._show_no_selection_message()
            return
        
        # Show warning if conflicts exist
        if row_data.get('conflict_detected', False):
            warning = QLabel("⚠️ Configuration conflict detected. Please resolve before saving.")
            self.update_warning_style(warning)
            warning.setWordWrap(True)
            self.params_layout.addWidget(warning)
        
        if behavior == "direct_servo":
            self._create_direct_servo_params(row_data)
        elif behavior == "joystick_pair":
            self._create_joystick_pair_params(row_data)
        elif behavior == "differential_tracks":
            self._create_differential_tracks_params(row_data)
        elif behavior == "scene_trigger":
            self._create_scene_trigger_params(row_data)
        elif behavior == "toggle_scenes":
            self._create_toggle_scenes_params(row_data)
        elif behavior == "nema_stepper":
            self._create_nema_stepper_params(row_data)
        elif behavior == "system_control":  
            self._create_system_control_params(row_data)

    def _create_direct_servo_params(self, row_data: Dict):
        """Create parameters for direct servo behavior"""
        # Replace _add_param_header with direct styling
        header = QLabel("Direct Servo Configuration")
        header.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        primary_color = theme_manager.get("primary_color")
        header.setStyleSheet(f"color: {primary_color}; padding: 6px 0px; margin-bottom: 10px; border: none; background: transparent;")
        self.params_layout.addWidget(header)
        
        control_name = row_data['input_combo'].currentText()
        if control_name != "Select Input...":
            axis_info = QLabel(f"Maps {control_name} to one servo")
            # Replace update_axis_info_style with direct styling
            grey = theme_manager.get("grey")
            axis_info.setStyleSheet(f"color: {grey}; font-style: italic; padding: 3px 0px; font-size: 10px; border: none; background: transparent;")
            self.params_layout.addWidget(axis_info)
        
        servo_combo = QComboBox()
        servo_combo.addItems(["Select Servo..."] + self.servo_channels)
        if 'target' in row_data['config']:
            servo_combo.setCurrentText(row_data['config']['target'])
        servo_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'target', text)
        )
        # Use clean param row instead of regular _add_param_row
        servo_combo.setStyleSheet(self._get_combo_style())
        label = QLabel("Target Servo:")
        label.setStyleSheet("color: white; padding: 3px 0px; font-size: 10px; border: none; background: transparent;")
        self.params_layout.addWidget(label)
        self.params_layout.addWidget(servo_combo)
        self.params_layout.addSpacing(6)
        
        invert_checkbox = QCheckBox("Invert Direction")
        invert_checkbox.setChecked(row_data['config'].get('invert', False))
        invert_checkbox.toggled.connect(
            lambda checked: self._update_row_config(row_data, 'invert', checked)
        )
        # Use clean param row for checkbox too
        self._add_clean_param_row("", invert_checkbox)
        
        target = row_data['config'].get('target', 'Not configured')
        row_data['target_label'].setText(f"→ {target}")

    def _create_joystick_pair_params(self, row_data: Dict):
        """Create parameters for joystick pair behavior"""
        self._add_param_header("Joystick Pair Configuration")
        
        control_name = row_data['input_combo'].currentText()
        if control_name != "Select Input...":
            axis_info = QLabel(f"Uses both X and Y axes of {control_name}")
            self.update_axis_info_style(axis_info)
            self.params_layout.addWidget(axis_info)
        
        x_servo_combo = QComboBox()
        x_servo_combo.addItems(["Select X Servo..."] + self.servo_channels)
        if 'x_servo' in row_data['config']:
            x_servo_combo.setCurrentText(row_data['config']['x_servo'])
        x_servo_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'x_servo', text)
        )
        self._add_param_row("X-Axis Servo:", x_servo_combo)
        
        y_servo_combo = QComboBox()
        y_servo_combo.addItems(["Select Y Servo..."] + self.servo_channels)
        if 'y_servo' in row_data['config']:
            y_servo_combo.setCurrentText(row_data['config']['y_servo'])
        y_servo_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'y_servo', text)
        )
        self._add_param_row("Y-Axis Servo:", y_servo_combo)
        
        x_servo = row_data['config'].get('x_servo', '?')
        y_servo = row_data['config'].get('y_servo', '?')
        row_data['target_label'].setText(f"→ X:{x_servo}, Y:{y_servo}")

    def _create_differential_tracks_params(self, row_data: Dict):
        """Create parameters for differential tracks behavior"""
        self._add_param_header("Differential Tracks Configuration")
        
        control_name = row_data['input_combo'].currentText()
        if control_name != "Select Input...":
            axis_info = QLabel(f"Uses both X and Y axes of {control_name} for tank steering")
            self.update_tank_steering_info_style(axis_info)
            self.params_layout.addWidget(axis_info)
        
        left_servo_combo = QComboBox()
        left_servo_combo.addItems(["Select Left Servo..."] + self.servo_channels)
        if 'left_servo' in row_data['config']:
            left_servo_combo.setCurrentText(row_data['config']['left_servo'])
        left_servo_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'left_servo', text)
        )
        self._add_param_row("Left Track:", left_servo_combo)
        
        right_servo_combo = QComboBox()
        right_servo_combo.addItems(["Select Right Servo..."] + self.servo_channels)
        if 'right_servo' in row_data['config']:
            right_servo_combo.setCurrentText(row_data['config']['right_servo'])
        right_servo_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'right_servo', text)
        )
        self._add_param_row("Right Track:", right_servo_combo)
        
        sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
        sensitivity_slider.setMinimum(1)
        sensitivity_slider.setMaximum(200) 
        sensitivity_slider.setValue(int(row_data['config'].get('turn_sensitivity', 1.0) * 100))
        sensitivity_slider.valueChanged.connect(
            lambda value: self._update_row_config(row_data, 'turn_sensitivity', value / 100.0)
        )
        
        sensitivity_label = QLabel(f"{row_data['config'].get('turn_sensitivity', 1.0):.2f}")
        sensitivity_slider.valueChanged.connect(
            lambda value: sensitivity_label.setText(f"{value / 100.0:.2f}")
        )
        
        sensitivity_layout = QHBoxLayout()
        sensitivity_layout.addWidget(sensitivity_slider)
        sensitivity_layout.addWidget(sensitivity_label)
        sensitivity_widget = QWidget()
        sensitivity_widget.setLayout(sensitivity_layout)
        
        self._add_param_row("Turn Sensitivity:", sensitivity_widget)
        
        left = row_data['config'].get('left_servo', '?')
        right = row_data['config'].get('right_servo', '?')
        row_data['target_label'].setText(f"→ L:{left}, R:{right}")

    def _create_scene_trigger_params(self, row_data: Dict):
        """Create parameters for scene trigger behavior"""
        # Header without border - direct styling
        header = QLabel("Scene Trigger Configuration")
        header.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        primary_color = theme_manager.get("primary_color")
        header.setStyleSheet(f"color: {primary_color}; padding: 6px 0px; margin-bottom: 10px; border: none; background: transparent;")
        self.params_layout.addWidget(header)
        
        # Target Scene combo with clean label
        scene_combo = QComboBox()
        scene_combo.addItems(["Select Scene..."] + self.scene_names)
        if 'scene' in row_data['config']:
            scene_combo.setCurrentText(row_data['config']['scene'])
        scene_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'scene', text)
        )
        scene_combo.setStyleSheet(self._get_combo_style())
        
        # Add label and combo manually with clean label styling
        label1 = QLabel("Target Scene:")
        label1.setStyleSheet("color: white; padding: 3px 0px; font-size: 10px; border: none; background: transparent;")
        self.params_layout.addWidget(label1)
        self.params_layout.addWidget(scene_combo)
        self.params_layout.addSpacing(6)
        
        # Trigger Timing combo with clean label
        timing_combo = QComboBox()
        timing_combo.addItems(["on_press", "on_release", "continuous"])
        timing_combo.setCurrentText(row_data['config'].get('trigger_timing', 'on_press'))
        timing_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'trigger_timing', text)
        )
        timing_combo.setStyleSheet(self._get_combo_style())
        
        # Add label and combo manually with clean label styling
        label2 = QLabel("Trigger Timing:")
        label2.setStyleSheet("color: white; padding: 3px 0px; font-size: 10px; border: none; background: transparent;")
        self.params_layout.addWidget(label2)
        self.params_layout.addWidget(timing_combo)
        self.params_layout.addSpacing(6)
        
        scene = row_data['config'].get('scene', 'Not configured')
        row_data['target_label'].setText(f"→ {scene}")

    def _create_toggle_scenes_params(self, row_data: Dict):
        """Create parameters for toggle scenes behavior"""
        # Header without border - direct styling
        header = QLabel("Toggle Scenes Configuration")
        header.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        primary_color = theme_manager.get("primary_color")
        header.setStyleSheet(f"color: {primary_color}; padding: 6px 0px; margin-bottom: 10px; border: none; background: transparent;")
        self.params_layout.addWidget(header)
        
        # Scene 1 combo with clean label
        scene1_combo = QComboBox()
        scene1_combo.addItems(["Select Scene 1..."] + self.scene_names)
        if 'scene_1' in row_data['config']:
            scene1_combo.setCurrentText(row_data['config']['scene_1'])
        scene1_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'scene_1', text)
        )
        scene1_combo.setStyleSheet(self._get_combo_style())
        
        # Add label and combo manually with clean label styling
        label1 = QLabel("Scene 1:")
        label1.setStyleSheet("color: white; padding: 3px 0px; font-size: 10px; border: none; background: transparent;")
        self.params_layout.addWidget(label1)
        self.params_layout.addWidget(scene1_combo)
        self.params_layout.addSpacing(6)
        
        # Scene 2 combo with clean label
        scene2_combo = QComboBox()
        scene2_combo.addItems(["Select Scene 2..."] + self.scene_names)
        if 'scene_2' in row_data['config']:
            scene2_combo.setCurrentText(row_data['config']['scene_2'])
        scene2_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'scene_2', text)
        )
        scene2_combo.setStyleSheet(self._get_combo_style())
        
        # Add label and combo manually with clean label styling
        label2 = QLabel("Scene 2:")
        label2.setStyleSheet("color: white; padding: 3px 0px; font-size: 10px; border: none; background: transparent;")
        self.params_layout.addWidget(label2)
        self.params_layout.addWidget(scene2_combo)
        self.params_layout.addSpacing(6)
        
        # Trigger Timing combo with clean label
        timing_combo = QComboBox()
        timing_combo.addItems(["on_press", "on_release"])
        timing_combo.setCurrentText(row_data['config'].get('trigger_timing', 'on_press'))
        timing_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'trigger_timing', text)
        )
        timing_combo.setStyleSheet(self._get_combo_style())
        
        # Add label and combo manually with clean label styling
        label3 = QLabel("Trigger Timing:")
        label3.setStyleSheet("color: white; padding: 3px 0px; font-size: 10px; border: none; background: transparent;")
        self.params_layout.addWidget(label3)
        self.params_layout.addWidget(timing_combo)
        self.params_layout.addSpacing(6)
        
        scene1 = row_data['config'].get('scene_1', '?')
        scene2 = row_data['config'].get('scene_2', '?')
        row_data['target_label'].setText(f"→ {scene1} ⟷ {scene2}")

    def _create_nema_stepper_params(self, row_data: Dict):
        """Create streamlined parameters for NEMA stepper behavior"""
        header = QLabel("NEMA Stepper Configuration")
        header.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        primary_color = theme_manager.get("primary_color")
        header.setStyleSheet(f"color: {primary_color}; padding: 6px 0px; margin-bottom: 10px; border: none; background: transparent;")
        self.params_layout.addWidget(header)
        
        control_name = row_data['input_combo'].currentText()
        if control_name != "Select Input...":
            axis_info = QLabel(f"Controls NEMA stepper using {control_name}")
            # Direct styling without borders - replace update_axis_info_style call
            grey = theme_manager.get("grey")
            axis_info.setStyleSheet(f"color: {grey}; font-style: italic; padding: 3px 0px; font-size: 10px; border: none; background: transparent;")
            self.params_layout.addWidget(axis_info)

        
        # Behavior type selection
        behavior_combo = QComboBox()
        behavior_options = ["toggle_positions", "sweep_continuous", "direct_control"]
        behavior_combo.addItems(["Select Mode..."] + behavior_options)
        if 'nema_behavior' in row_data['config']:
            behavior_combo.setCurrentText(row_data['config']['nema_behavior'])
        behavior_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'nema_behavior', text)
        )
        behavior_combo.setStyleSheet(self._get_clean_combo_style())

        # Load NEMA config from servo config to initialize row values
        nema_config = self._get_nema_config()
        row_data['config']['min_position'] = float(nema_config.get('min_position', 0.0))
        row_data['config']['max_position'] = float(nema_config.get('max_position', 20.0))  
        row_data['config']['normal_speed'] = int(nema_config.get('normal_speed', 800))
        row_data['config']['acceleration'] = int(nema_config.get('acceleration', 800))

        # Update the target display with the actual values
        self._update_nema_target_display(row_data)

        self._add_clean_param_row("Behavior Mode:", behavior_combo)
        
        # Current NEMA Configuration Display (read-only)
        self._add_nema_config_display()
        
        # Trigger timing section
        self._add_trigger_timing_section(row_data)
        
        # Update target display with current servo config values
        self._update_nema_target_display(row_data)

    def _add_clean_param_row(self, label_text: str, widget: QWidget):
        """Add a parameter row with label and control without borders"""
        if label_text:
            label = QLabel(label_text)
            label.setStyleSheet("color: white; padding: 3px 0px; font-size: 10px; border: none; background: transparent;")
            self.params_layout.addWidget(label)
        
        widget.setStyleSheet(widget.styleSheet() + "; border: none; background: transparent;")
        self.params_layout.addWidget(widget)
        self.params_layout.addSpacing(6)

    def _add_nema_config_display(self):
        """Add read-only display of current NEMA configuration from servo config"""
        # Load current NEMA config from servo config
        nema_config = self._get_nema_config()
        
        # Create config display frame
        config_frame = QFrame()
        config_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(42, 42, 58, 0.8);
                border: 1px solid #555;
                border-radius: 4px;
                margin: 5px 0px;
            }
        """)
        
        config_layout = QVBoxLayout(config_frame)
        config_layout.setContentsMargins(8, 8, 8, 8)
        config_layout.setSpacing(3)
        
        # Header
        primary_color = theme_manager.get("primary_color")
        header = QLabel("Current NEMA Configuration:")
        header.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        header.setStyleSheet(f"color: {primary_color}; margin-bottom: 5px; border: none; background: transparent;")
        config_layout.addWidget(header)
        
        # Configuration rows
        config_items = [
            ("Min Position:", f"{nema_config.get('min_position', 0.0):.1f} cm"),
            ("Max Position:", f"{nema_config.get('max_position', 20.0):.1f} cm"),
            ("Movement Speed:", f"{nema_config.get('normal_speed', 800)} steps/s"),
            ("Acceleration:", f"{nema_config.get('acceleration', 800)} steps/s²")
        ]
        
        for label_text, value_text in config_items:
            row_widget = QWidget()
            row_widget.setStyleSheet("border: none; background: transparent;")
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 2, 0, 2)
            
            label = QLabel(label_text)
            label.setStyleSheet("color: #aaa; font-size: 11px; border: none; background: transparent;")
            
            value = QLabel(value_text)
            value.setStyleSheet("color: #4CAF50; font-size: 11px; border: none; background: transparent;")
            
            row_layout.addWidget(label)
            row_layout.addStretch()
            row_layout.addWidget(value)
            
            config_layout.addWidget(row_widget)
        
        self.params_layout.addWidget(config_frame)

    def _add_trigger_timing_section(self, row_data: Dict):
        """Add trigger timing section with visual separation"""
        # Add visual separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("color: #444; margin: 8px 0px; border: none; background: transparent;")
        self.params_layout.addWidget(separator)
        
        # Trigger timing (for toggle/sweep modes)
        current_behavior = row_data['config'].get('nema_behavior', 'toggle_positions')
        if current_behavior in ['toggle_positions', 'sweep_continuous']:
            timing_combo = QComboBox()
            timing_combo.addItems(["on_press", "on_release"])
            timing_combo.setCurrentText(row_data['config'].get('trigger_timing', 'on_press'))
            timing_combo.currentTextChanged.connect(
                lambda text: self._update_row_config(row_data, 'trigger_timing', text)
            )
            timing_combo.setStyleSheet(self._get_clean_combo_style())
            self._add_clean_param_row("Trigger Timing:", timing_combo)
        
        # Invert direction (for direct control)
        if current_behavior == 'direct_control':
            invert_checkbox = QCheckBox("Invert Direction")
            invert_checkbox.setChecked(row_data['config'].get('invert', False))
            invert_checkbox.toggled.connect(
                lambda checked: self._update_row_config(row_data, 'invert', checked)
            )
            invert_checkbox.setStyleSheet("border: none; background: transparent; color: white;")
            self._add_clean_param_row("", invert_checkbox)

    def _update_nema_target_display(self, row_data: Dict):
        """Update target display using current servo config values"""
        nema_config = self._get_nema_config()
        mode = row_data['config'].get('nema_behavior', 'Not configured')
        min_pos = nema_config.get('min_position', 0.0)
        max_pos = nema_config.get('max_position', 20.0)
        row_data['target_label'].setText(f"→ NEMA {mode}: {min_pos:.1f}-{max_pos:.1f}cm")

    def _get_clean_combo_style(self):
        """Get clean combobox styling without borders"""
        primary = theme_manager.get("primary_color")
        panel_bg = theme_manager.get("panel_bg")
        
        return f"""
            QComboBox {{
                background-color: {panel_bg};
                color: {primary};
                border: none;
                border-radius: 3px;
                padding: 4px;
                font-size: 10px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid {primary};
                margin-right: 3px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {panel_bg};
                color: {primary};
                border: 1px solid {primary};
                selection-background-color: {primary};
                selection-color: black;
            }}
        """

    def _get_nema_config(self):
        """Get NEMA configuration from servo config"""
        try:
            servo_config = config_manager.get_config("resources/configs/servo_config.json")
            return servo_config.get("nema", {
                "min_position": 0.0,
                "max_position": 20.0,
                "normal_speed": 800,
                "acceleration": 800
            })
        except Exception:
            return {
                "min_position": 0.0,
                "max_position": 20.0,
                "normal_speed": 800,
                "acceleration": 800
            }

    def _add_param_header(self, text: str):
        """Add a parameter section header"""
        header = QLabel(text)
        header.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.update_param_header_style(header)
        self.params_layout.addWidget(header)

    def _add_param_row(self, label_text: str, widget: QWidget):
        """Add a parameter row with label and control"""
        if label_text:
            label = QLabel(label_text)
            self.update_param_label_style(label)
            self.params_layout.addWidget(label)
        
        widget.setStyleSheet(self._get_param_widget_style())
        self.params_layout.addWidget(widget)
        self.params_layout.addSpacing(6)

    def _update_row_config(self, row_data: Dict, key: str, value):
        """Update row configuration and refresh target display"""
        row_data['config'][key] = value
        
        behavior = row_data['behavior_combo'].currentText()
        if behavior == "direct_servo":
            target = row_data['config'].get('target', 'Not configured')
            row_data['target_label'].setText(f"→ {target}")
        elif behavior == "joystick_pair":
            x_servo = row_data['config'].get('x_servo', '?')
            y_servo = row_data['config'].get('y_servo', '?') 
            row_data['target_label'].setText(f"→ X:{x_servo}, Y:{y_servo}")
        elif behavior == "differential_tracks":
            left = row_data['config'].get('left_servo', '?')
            right = row_data['config'].get('right_servo', '?')
            row_data['target_label'].setText(f"→ L:{left}, R:{right}")
        elif behavior == "scene_trigger":
            scene = row_data['config'].get('scene', 'Not configured')
            row_data['target_label'].setText(f"→ {scene}")
        elif behavior == "toggle_scenes":
            scene1 = row_data['config'].get('scene_1', '?')
            scene2 = row_data['config'].get('scene_2', '?')
            row_data['target_label'].setText(f"→ {scene1} ⟷ {scene2}")
        elif behavior == "nema_stepper":
            mode = row_data['config'].get('nema_behavior', 'Not configured')
            min_pos = row_data['config'].get('min_position', '?')
            max_pos = row_data['config'].get('max_position', '?')
            row_data['target_label'].setText(f"→ NEMA {mode}: {min_pos}-{max_pos}cm")
        elif behavior == "system_control":  # ADD THIS
            action = row_data['config'].get('system_action', 'Not configured')
            row_data['target_label'].setText(f"→ {action}")

            if hasattr(self, 'selected_row_index') and self.selected_row_index is not None:
                if 0 <= self.selected_row_index < len(self.mapping_rows):
                    selected_row = self.mapping_rows[self.selected_row_index]
                    if selected_row == row_data:
                        self._create_behavior_parameters(row_data)


    def _clear_parameters_layout(self):
        """Clear all widgets from parameters layout"""
        while self.params_layout.count():
            child = self.params_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _remove_mapping_row(self, row_index: int):
        """Remove a mapping row"""
        if 0 <= row_index < len(self.mapping_rows):
            row_data = self.mapping_rows[row_index]
            control_name = row_data['input_combo'].currentText()
            if control_name != "Select Input...":
                self.behavior_registry.unregister_mapping(control_name)
            
            for key in ['input_combo', 'type_combo', 'behavior_combo', 'target_label']:
                widget = row_data[key]
                self.grid_layout.removeWidget(widget)
                widget.deleteLater()
            
            actions_widget = row_data['select_btn'].parent()
            self.grid_layout.removeWidget(actions_widget)
            actions_widget.deleteLater()
            
            self.mapping_rows.pop(row_index)
            
            if self.selected_row_index == row_index:
                self.selected_row_index = None
                self._show_no_selection_message()
            
            self._rebuild_grid_layout()
            self._check_for_conflicts()

    def _rebuild_grid_layout(self):
        """Rebuild grid layout with correct row indices after removal"""
        while self.grid_layout.count():
            self.grid_layout.takeAt(0)
            
        # Reapply all layout settings to match headers exactly
        self.grid_layout.setHorizontalSpacing(10)
        self.grid_layout.setVerticalSpacing(10)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        
        # Reapply column stretch factors
        self.grid_layout.setColumnStretch(0, 2)
        self.grid_layout.setColumnStretch(1, 1)
        self.grid_layout.setColumnStretch(2, 2)
        self.grid_layout.setColumnStretch(3, 3)
        self.grid_layout.setColumnStretch(4, 1)
            
        for row, row_data in enumerate(self.mapping_rows):
            self.grid_layout.addWidget(row_data['input_combo'], row, 0)
            self.grid_layout.addWidget(row_data['type_combo'], row, 1)
            self.grid_layout.addWidget(row_data['behavior_combo'], row, 2)
            self.grid_layout.addWidget(row_data['target_label'], row, 3)
            
            # Create actions widget for this row
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            actions_layout.setSpacing(5)
            
            actions_layout.addWidget(row_data['select_btn'])
            actions_layout.addWidget(row_data['remove_btn'])
            
            self.grid_layout.addWidget(actions_widget, row, 4)

    def _save_all_mappings(self):
        """Save all controller mappings to configuration"""
        conflicts_exist = any(row['conflict_detected'] for row in self.mapping_rows)
        if conflicts_exist:
            QMessageBox.warning(self, "Conflicts Detected", 
                              "Please resolve all joystick conflicts before saving.")
            return
        
        controller_config = {}
        
        for row_data in self.mapping_rows:
            control_name = row_data['input_combo'].currentText()
            behavior = row_data['behavior_combo'].currentText()
            
            if control_name != "Select Input..." and behavior != "Select Behavior...":
                controller_config[control_name] = {
                    'behavior': behavior,
                    **row_data['config']
                }
        
        try:
            config_manager.save_config("resources/configs/controller_config.json", controller_config)
            if self.websocket and self.websocket.is_connected():
                success = self.send_websocket_message("save_controller_config", config=controller_config)
                if success:
                    self.logger.info("Controller config sent to backend")
                else:
                    self.logger.warning("Failed to send controller config to backend")
            else:
                self.logger.warning("WebSocket not connected - controller config not synced to backend")

            QMessageBox.information(self, "Saved", f"Saved {len(controller_config)} controller mappings.")
            
            # Update behavior registry
            for control_name, config in controller_config.items():
                self.behavior_registry.register_mapping(control_name, config['behavior'], config)
            
            if self.logger:
                self.logger.info(f"Saved {len(controller_config)} controller mappings")
                
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save controller mappings: {e}")
            if self.logger:
                self.logger.error(f"Failed to save controller mappings: {e}")

    @error_boundary
    def handle_controller_input(self, message):
        """Handle incoming controller input messages"""
        try:
            msg = json.loads(message)
            if msg.get("type") != "controller_input":
                return
            
            control_name = msg.get("control")
            raw_value = msg.get("value", 0.0)
            
            if not control_name:
                return
            
            # Process through behavior registry
            for row_data in self.mapping_rows:
                if row_data['input_combo'].currentText() == control_name:
                    behavior = row_data['behavior_combo'].currentText()
                    
                    if behavior != "Select Behavior..." and not row_data.get('conflict_detected', False):
                        mapping_config = {
                            'behavior': behavior,
                            **row_data['config']
                        }
                        
                        success = self.behavior_registry.process_input(
                            control_name, raw_value, mapping_config
                        )
                        
                        if not success and self.logger:
                            self.logger.warning(f"Failed to process input {control_name}: {raw_value}")
                    break
                    
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error handling controller input: {e}")

    # ========================================
    # THEME UPDATE METHODS
    # ========================================
 
# Replace the update_theme method in controller_screen.py (around line 1190)

    def update_theme(self):
        """Update all UI elements when theme changes - FIXED"""
        try:
            # First, get fresh theme colors
            primary = theme_manager.get("primary_color")
            panel_bg = theme_manager.get("panel_bg")
            
            # Log the theme change for debugging
            self.logger.info(f"Controller screen updating theme to: {theme_manager.get_theme_name()}")
            
            # Update frame and panel styles
            self.update_config_frame_style()
            self.update_parameters_panel_style()
            self.update_conflict_warning_style()
            self.update_scroll_area_style()
            self.update_params_header_style()
            
            # Update column headers
            if hasattr(self, 'header_labels'):
                for header_label in self.header_labels:
                    self.update_column_header_style(header_label)
            
            # Update buttons - FIX: Correct attribute names
            if hasattr(self, 'add_btn'):
                self.update_button_style(self.add_btn)
            if hasattr(self, 'save_btn'):
                self.update_button_style(self.save_btn)
            if hasattr(self, 'calibration_button'):  # FIXED: correct attribute name
                self.calibration_button.setStyleSheet(f"""
                    QPushButton {{
                        background-color: #1e90ff;
                        color: white;
                        border: none;
                        padding: 8px 16px;
                        border-radius: 5px;
                        font-size: 12px;
                        font-weight: bold;
                    }}
                    QPushButton:hover {{ background-color: #4dabf7; }}
                    QPushButton:disabled {{ background-color: #555555; }}
                """)
            if hasattr(self, 'refresh_btn'):  # FIXED: removed extra 'self.'
                self.refresh_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #666666;
                        color: white;
                        border: none;
                        padding: 8px 16px;
                        border-radius: 5px;
                        font-size: 12px;
                        margin-left: 10px;
                    }
                    QPushButton:hover { background-color: #777777; }
                """)
            
            # FIX: Update controller status label styling
            if hasattr(self, 'controller_status_label') and self.controller_status_label:
                try:
                    # Check if widget still exists
                    self.controller_status_label.text()
                    current_text = self.controller_status_label.text()
                    if "Connected" in current_text:
                        self.controller_status_label.setStyleSheet("color: #4CAF50;border: none; background: transparent; padding: 0px;")
                    else:
                        self.controller_status_label.setStyleSheet("color: #F44336;border: none; background: transparent; padding: 0px;")
                except RuntimeError:
                    pass  # Widget has been deleted
                    
            # CRITICAL: Update all existing row widgets with fresh styles
            for row_data in self.mapping_rows:
                # Force refresh of combo box styles
                row_data['input_combo'].setStyleSheet(self._get_combo_style())
                row_data['type_combo'].setStyleSheet(self._get_combo_style())
                row_data['behavior_combo'].setStyleSheet(self._get_combo_style())
                row_data['target_label'].setStyleSheet(self._get_target_label_style())
                row_data['select_btn'].setStyleSheet(self._get_small_button_style())
                row_data['remove_btn'].setStyleSheet(self._get_remove_button_style())
            
            # Update no selection message if visible
            if hasattr(self, 'no_selection_label') and self.no_selection_label:
                self.update_no_selection_style()
                
            # CRITICAL: Force update of the parameters panel content if a row is selected
            if hasattr(self, 'selected_row_index') and self.selected_row_index is not None:
                if 0 <= self.selected_row_index < len(self.mapping_rows):
                    selected_row = self.mapping_rows[self.selected_row_index]
                    self._create_behavior_parameters(selected_row) 
            
            self.logger.info("Controller screen theme update completed")
            
        except Exception as e:
            self.logger.error(f"Failed to update controller screen theme: {e}")

    # Also add this method after the update_theme method:

    def _refresh_parameter_widgets(self):
        """Force refresh all parameter widgets with current theme"""
        try:
            # Clear and rebuild parameters panel if needed
            if hasattr(self, 'params_layout'):
                # Get all combo boxes in the parameters panel and refresh their styles
                for i in range(self.params_layout.count()):
                    widget = self.params_layout.itemAt(i).widget()
                    if widget:
                        if isinstance(widget, QComboBox):
                            widget.setStyleSheet(self._get_combo_style())
                        elif isinstance(widget, QLabel):
                            # Check if it's a header or regular label and style accordingly
                            font = widget.font()
                            if font.weight() == QFont.Weight.Bold:
                                primary = theme_manager.get("primary_color")
                                widget.setStyleSheet(f"color: {primary}; padding: 6px 0px; margin-bottom: 10px; border: none; background: transparent;")
                            else:
                                widget.setStyleSheet("color: white; padding: 3px 0px; font-size: 10px; border: none; background: transparent;")
        except Exception as e:
            self.logger.warning(f"Failed to refresh parameter widgets: {e}")

    def update_config_frame_style(self):
        """Update main config frame styling"""
        primary = theme_manager.get("primary_color")
        panel_bg = theme_manager.get("panel_bg")
        self.config_frame.setStyleSheet(f"border: 2px solid {primary}; border-radius: 10px; background-color: {panel_bg};")

    def update_parameters_panel_style(self):
        """Update parameters panel styling"""
        primary = theme_manager.get("primary_color")
        panel_bg = theme_manager.get("panel_bg")
        self.parameters_panel.setStyleSheet(f"""
            QFrame {{
                background-color: {panel_bg};
                border: 2px solid {primary};
                border-radius: 10px;
                color: white;
            }}
        """)

    def update_header_style(self):
        """Update main header styling"""
        primary = theme_manager.get("primary_color")
        self.header.setStyleSheet(f"color: {primary}; padding: 10px; border: none;")

    def update_column_header_style(self, header_label):
        """Update column header styling"""
        primary = theme_manager.get("primary_color")
        header_label.setStyleSheet(f"color: {primary}; padding: 8px;")

    def update_conflict_warning_style(self):
        """Update conflict warning styling"""
        red = theme_manager.get("red")
        self.conflict_warning.setStyleSheet(f"color: {red}; background-color: rgba(204, 68, 68, 0.1); padding: 8px; border-radius: 4px; margin: 5px 0px;")

    def update_scroll_area_style(self):
        """Update scroll area styling"""
        expanded_bg = theme_manager.get("expanded_bg")
        self.scroll_area.setStyleSheet(f"border: 1px solid #555; background-color: {expanded_bg};")

    def update_params_header_style(self):
        """Update parameters header styling"""
        primary = theme_manager.get("primary_color")
        self.params_header.setStyleSheet(f"color: {primary}; padding: 6px; border: none;")

    def update_param_header_style(self, header):
        """Update parameter section header styling"""
        primary = theme_manager.get("primary_color")
        header.setStyleSheet(f"color: {primary}; padding: 6px 0px; margin-bottom: 10px;")

    def update_param_label_style(self, label):
        """Update parameter label styling"""
        label.setStyleSheet("color: white; padding: 3px 0px; font-size: 10px;")

    def update_axis_info_style(self, label):
        """Update axis info label styling"""
        grey = theme_manager.get("grey")
        label.setStyleSheet(f"color: {grey}; font-style: italic; padding: 3px 0px; font-size: 10px;")

    def update_tank_steering_info_style(self, label):
        """Update tank steering info label styling"""
        primary_light = theme_manager.get("primary_light")
        label.setStyleSheet(f"color: {primary_light}; font-weight: bold; padding: 3px 0px; font-size: 10px;")

    def update_warning_style(self, warning):
        """Update warning label styling"""
        red = theme_manager.get("red")
        warning.setStyleSheet(f"color: {red}; background-color: rgba(204, 68, 68, 0.1); padding: 6px; border-radius: 4px; margin-bottom: 8px; font-size: 10px;")

    def update_no_selection_style(self):
        """Update no selection message styling"""
        grey = theme_manager.get("grey")
        self.no_selection_label.setStyleSheet(f"color: {grey}; padding: 15px; text-align: center; font-size: 11px;")

    def update_button_style(self, button):
        """Update button styling"""
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        button.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {primary_light}, stop:1 {primary});
                border: 2px solid {primary};
                border-radius: 8px;
                color: black;
                font-weight: bold;
                padding: 10px 20px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {primary_light};
            }}
        """)

    # ========================================
    # STYLING METHODS
    # ========================================
    
    def _get_small_button_style(self, selected=False):
        """Get small button styling"""
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        
        if selected:
            return f"""
                QPushButton {{
                    background-color: {primary};
                    color: black;
                    border: 2px solid {primary};
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 10px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {primary_light};
                }}
            """
        else:
            return f"""
                QPushButton {{
                    background-color: transparent;
                    color: {primary};
                    border: 1px solid {primary};
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 10px;
                }}
                QPushButton:hover {{
                    background-color: {primary};
                    color: black;
                }}
            """
    
    def _get_remove_button_style(self):
        """Get remove button styling"""
        red = theme_manager.get("red")
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {red};
                border: 1px solid {red};
                border-radius: 4px;
                padding: 4px 6px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {red};
                color: white;
            }}
        """
    
    def _get_combo_style(self, error=False):
        """Get combobox styling"""
        primary = theme_manager.get("primary_color")
        red = theme_manager.get("red") 
        panel_bg = theme_manager.get("panel_bg")
        border_color = red if error else primary
        
        return f"""
            QComboBox {{
                background-color: {panel_bg};
                color: {primary};
                border: 1px solid {border_color};
                border-radius: 3px;
                padding: 4px;
                font-size: 10px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid {primary};
                margin-right: 3px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {panel_bg};
                color: {primary};
                border: 1px solid {primary};
                selection-background-color: {primary};
                selection-color: black;
            }}
        """

    def _get_target_label_style(self):
        """Get target label styling"""
        grey = theme_manager.get("grey")
        return f"color: {grey}; padding: 0px; border: 1px solid #555; border-radius: 4px;"
    
    def _get_param_widget_style(self):
        """Get parameter widget styling"""
        primary = theme_manager.get("primary_color")
        panel_bg = theme_manager.get("panel_bg")
        
        return f"""
            QWidget {{
                background-color: {panel_bg};
                color: {primary};
                border: 1px solid #555;
                border-radius: 3px;
                padding: 2px;
                font-size: 10px;
            }}
            QComboBox {{
                border: 1px solid {primary};
            }}
            QSlider::groove:horizontal {{
                height: 6px;
                background: #555;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {primary};
                width: 14px;
                height: 14px;
                border-radius: 7px;
                margin: -4px 0;
            }}
            QCheckBox {{
                color: {primary};
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border-radius: 2px;
            }}
            QCheckBox::indicator:unchecked {{
                background: #555;
                border: 1px solid {primary};
            }}
            QCheckBox::indicator:checked {{
                background: {primary};
                border: 1px solid {primary};
            }}
        """

    # ========================================
    # COMPATIBILITY & CLEANUP METHODS
    # ========================================
    
    def cleanup(self):
        """Cleanup resources"""
        try:
            if hasattr(theme_manager, 'unregister_callback'):
                theme_manager.unregister_callback(self.update_theme)
        except Exception:
            pass