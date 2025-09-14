"""
WALL-E Control System - Complete Controller Configuration Screen
Fixed maestro detection and servo channel loading issue + Bluetooth controller support
"""

import json
from typing import Optional, Dict, Any, List
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QComboBox, QCheckBox, QMessageBox,
    QProgressBar, QFrame, QSlider, QSpinBox, QGroupBox
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from widgets.base_screen import BaseScreen
from core.config_manager import config_manager
from core.theme_manager import theme_manager
from core.utils import error_boundary


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


# ========================================
# BEHAVIOR REGISTRY
# ========================================

class BehaviorHandlerRegistry:
    """Registry to manage different behavior handlers"""
    
    def __init__(self, websocket_sender=None, logger=None):
        self.handlers = {
            "direct_servo": DirectServoHandler(websocket_sender, logger),
            "joystick_pair": JoystickPairHandler(websocket_sender, logger),
            "differential_tracks": DifferentialTracksHandler(websocket_sender, logger),
            "scene_trigger": SceneTriggerHandler(websocket_sender, logger),
            "toggle_scenes": ToggleScenesHandler(websocket_sender, logger),
            "nema_stepper": NemaStepperHandler(websocket_sender, logger)
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

    def _setup_screen(self):
        """Initialize controller configuration screen with maestro detection"""
        self.setFixedWidth(1200)
        
        self.behavior_registry = BehaviorHandlerRegistry(
            websocket_sender=self.send_websocket_message,
            logger=self.logger
        )
        
        self._load_predefined_options()
        self._init_ui()
        
        # Request maestro detection before loading config
        QTimer.singleShot(1000, self._detect_maestros)
        
        if self.websocket:
            self.websocket.textMessageReceived.connect(self.handle_controller_input)
            self.websocket.textMessageReceived.connect(self.handle_websocket_message)
        
        theme_manager.register_callback(self.update_theme)

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

    def handle_websocket_message(self, message):
        """Handle WebSocket messages including maestro detection"""
        try:
            msg = json.loads(message)
            msg_type = msg.get("type")
            
            if msg_type == "maestro_info":
                self._handle_maestro_info(msg)
            elif msg_type == "controller_info":
                self.handle_controller_info_response(msg)
            elif msg_type == "controller_input":
                # This is already handled by handle_controller_input
                pass
                
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error handling WebSocket message: {e}")

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
            "left_stick", "right_stick",
            "left_stick_x", "left_stick_y", "right_stick_x", "right_stick_y",
            "left_trigger", "right_trigger", "button_a", "button_b", "button_x", "button_y",
            "shoulder_left", "shoulder_right", "dpad_up", "dpad_down", "dpad_left", "dpad_right"
        ]
        
        # Wii Remote + Nunchuk inputs
        self.wii_inputs = [
            "button_a", "button_b", "button_1", "button_2", "button_plus", "button_minus", "button_home",
            "nunchuk_c", "nunchuk_z", "wiimote_tilt_x", "wiimote_tilt_y", 
            "nunchuk_stick_x", "nunchuk_stick_y", "dpad_up", "dpad_down", "dpad_left", "dpad_right"
        ]
        
        # Start with Steam Deck as default - will be updated when controller connects
        self.current_inputs = self.steam_inputs.copy()
        
        self.input_types = ["joystick", "trigger", "button", "dpad"]
        
        self.behaviors = [
            "direct_servo", "joystick_pair", "differential_tracks", 
            "scene_trigger", "toggle_scenes", "nema_stepper"
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
                    self.controller_status_label.setStyleSheet("color: #4CAF50;")  # Green
                
                # Update available inputs
                if available_inputs:
                    self.update_available_inputs(controller_type, available_inputs)
            else:
                # Show disconnected status
                if hasattr(self, 'controller_status_label'):
                    self.controller_status_label.setText("No controller connected")
                    self.controller_status_label.setStyleSheet("color: #F44336;")  # Red
            
            if self.logger:
                self.logger.info(f"Controller info updated: {controller_name} ({controller_type})")
                
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error handling controller info response: {e}")

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
        else:
            return "Configure targets →"

    def _init_ui(self):
        """Initialize the UI layout with proper padding"""
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(100, 25, 40, 15)

        # Status frame at top
        status_frame = QFrame()
        status_layout = QHBoxLayout(status_frame)
        
        status_label = QLabel("Controller Status:")
        self.controller_status_label = QLabel("Checking...")
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.request_controller_info)
        
        status_layout.addWidget(status_label)
        status_layout.addWidget(self.controller_status_label)
        status_layout.addStretch()
        status_layout.addWidget(refresh_btn)

        # Main layout
        config_section = self._create_config_section()
        main_layout.addWidget(config_section, stretch=3)
        
        params_section = self._create_parameters_section()  
        main_layout.addWidget(params_section, stretch=1)
        
        self.setLayout(main_layout)
        QTimer.singleShot(1000, self.request_controller_info)

    def _create_config_section(self):
        """Create the main configuration grid section"""
        self.config_frame = QFrame()
        self.update_config_frame_style()
        layout = QVBoxLayout(self.config_frame)
        layout.setContentsMargins(15, 15, 15, 15)
        
        self.header = QLabel("CONTROLLER CONFIGURATION")
        self.header.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_header_style()
        layout.addWidget(self.header)
        
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

    def _create_parameters_section(self):
        """Create the parameters panel section"""
        self.parameters_panel = QFrame()
        self.parameters_panel.setFixedWidth(280)
        self.update_parameters_panel_style()
        
        layout = QVBoxLayout(self.parameters_panel)
        layout.setContentsMargins(12, 12, 12, 12)
        
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

    def _create_direct_servo_params(self, row_data: Dict):
        """Create parameters for direct servo behavior"""
        self._add_param_header("Direct Servo Configuration")
        
        control_name = row_data['input_combo'].currentText()
        if control_name != "Select Input...":
            axis_info = QLabel(f"Maps {control_name} to one servo")
            self.update_axis_info_style(axis_info)
            self.params_layout.addWidget(axis_info)
        
        servo_combo = QComboBox()
        servo_combo.addItems(["Select Servo..."] + self.servo_channels)
        if 'target' in row_data['config']:
            servo_combo.setCurrentText(row_data['config']['target'])
        servo_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'target', text)
        )
        self._add_param_row("Target Servo:", servo_combo)
        
        invert_checkbox = QCheckBox("Invert Direction")
        invert_checkbox.setChecked(row_data['config'].get('invert', False))
        invert_checkbox.toggled.connect(
            lambda checked: self._update_row_config(row_data, 'invert', checked)
        )
        self._add_param_row("", invert_checkbox)
        
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
        self._add_param_header("Scene Trigger Configuration")
        
        scene_combo = QComboBox()
        scene_combo.addItems(["Select Scene..."] + self.scene_names)
        if 'scene' in row_data['config']:
            scene_combo.setCurrentText(row_data['config']['scene'])
        scene_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'scene', text)
        )
        self._add_param_row("Target Scene:", scene_combo)
        
        timing_combo = QComboBox()
        timing_combo.addItems(["on_press", "on_release", "continuous"])
        timing_combo.setCurrentText(row_data['config'].get('trigger_timing', 'on_press'))
        timing_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'trigger_timing', text)
        )
        self._add_param_row("Trigger Timing:", timing_combo)
        
        scene = row_data['config'].get('scene', 'Not configured')
        row_data['target_label'].setText(f"→ {scene}")

    def _create_toggle_scenes_params(self, row_data: Dict):
        """Create parameters for toggle scenes behavior"""
        self._add_param_header("Toggle Scenes Configuration")
        
        scene1_combo = QComboBox()
        scene1_combo.addItems(["Select Scene 1..."] + self.scene_names)
        if 'scene_1' in row_data['config']:
            scene1_combo.setCurrentText(row_data['config']['scene_1'])
        scene1_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'scene_1', text)
        )
        self._add_param_row("Scene 1:", scene1_combo)
        
        scene2_combo = QComboBox()
        scene2_combo.addItems(["Select Scene 2..."] + self.scene_names)
        if 'scene_2' in row_data['config']:
            scene2_combo.setCurrentText(row_data['config']['scene_2'])
        scene2_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'scene_2', text)
        )
        self._add_param_row("Scene 2:", scene2_combo)
        
        timing_combo = QComboBox()
        timing_combo.addItems(["on_press", "on_release"])
        timing_combo.setCurrentText(row_data['config'].get('trigger_timing', 'on_press'))
        timing_combo.currentTextChanged.connect(
            lambda text: self._update_row_config(row_data, 'trigger_timing', text)
        )
        self._add_param_row("Trigger Timing:", timing_combo)
        
        scene1 = row_data['config'].get('scene_1', '?')
        scene2 = row_data['config'].get('scene_2', '?')
        row_data['target_label'].setText(f"→ {scene1} ⟷ {scene2}")

    def _create_nema_stepper_params(self, row_data: Dict):
        """Create parameters for NEMA stepper behavior"""
        self._add_param_header("NEMA Stepper Configuration")
        
        control_name = row_data['input_combo'].currentText()
        if control_name != "Select Input...":
            axis_info = QLabel(f"Controls NEMA stepper using {control_name}")
            self.update_axis_info_style(axis_info)
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
        self._add_param_row("Behavior Mode:", behavior_combo)
        
        # Load NEMA config from servo config
        nema_config = self._get_nema_config()
        
        # Position limits
        min_pos_spin = QSpinBox()
        min_pos_spin.setRange(0, 100)
        min_pos_spin.setSuffix(" cm")
        min_pos_spin.setValue(int(row_data['config'].get('min_position', nema_config.get('min_position', 0))))
        min_pos_spin.valueChanged.connect(
            lambda value: self._update_row_config(row_data, 'min_position', float(value))
        )
        self._add_param_row("Min Position:", min_pos_spin)
        
        max_pos_spin = QSpinBox()
        max_pos_spin.setRange(1, 100)
        max_pos_spin.setSuffix(" cm")
        max_pos_spin.setValue(int(row_data['config'].get('max_position', nema_config.get('max_position', 20))))
        max_pos_spin.valueChanged.connect(
            lambda value: self._update_row_config(row_data, 'max_position', float(value))
        )
        self._add_param_row("Max Position:", max_pos_spin)
        
        # Speed setting
        speed_spin = QSpinBox()
        speed_spin.setRange(100, 2000)
        speed_spin.setSuffix(" steps/s")
        speed_spin.setValue(int(row_data['config'].get('normal_speed', nema_config.get('normal_speed', 800))))
        speed_spin.valueChanged.connect(
            lambda value: self._update_row_config(row_data, 'normal_speed', value)
        )
        self._add_param_row("Movement Speed:", speed_spin)
        
        # Acceleration setting
        accel_spin = QSpinBox()
        accel_spin.setRange(100, 2000)
        accel_spin.setSuffix(" steps/s²")
        accel_spin.setValue(int(row_data['config'].get('acceleration', nema_config.get('acceleration', 800))))
        accel_spin.valueChanged.connect(
            lambda value: self._update_row_config(row_data, 'acceleration', value)
        )
        self._add_param_row("Acceleration:", accel_spin)
        
        # Trigger timing (for toggle/sweep modes)
        current_behavior = row_data['config'].get('nema_behavior', 'toggle_positions')
        if current_behavior in ['toggle_positions', 'sweep_continuous']:
            timing_combo = QComboBox()
            timing_combo.addItems(["on_press", "on_release"])
            timing_combo.setCurrentText(row_data['config'].get('trigger_timing', 'on_press'))
            timing_combo.currentTextChanged.connect(
                lambda text: self._update_row_config(row_data, 'trigger_timing', text)
            )
            self._add_param_row("Trigger Timing:", timing_combo)
        
        # Invert direction (for direct control)
        if current_behavior == 'direct_control':
            invert_checkbox = QCheckBox("Invert Direction")
            invert_checkbox.setChecked(row_data['config'].get('invert', False))
            invert_checkbox.toggled.connect(
                lambda checked: self._update_row_config(row_data, 'invert', checked)
            )
            self._add_param_row("", invert_checkbox)
        
        # Update target display
        mode = row_data['config'].get('nema_behavior', 'Not configured')
        min_pos = row_data['config'].get('min_position', '?')
        max_pos = row_data['config'].get('max_position', '?')
        row_data['target_label'].setText(f"→ NEMA {mode}: {min_pos}-{max_pos}cm")

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
    
    def update_theme(self):
        """Update all UI elements when theme changes"""
        self.update_config_frame_style()
        self.update_parameters_panel_style()
        self.update_header_style()
        self.update_conflict_warning_style()
        self.update_scroll_area_style()
        self.update_params_header_style()
        
        # Update column headers
        if hasattr(self, 'header_labels'):
            for header_label in self.header_labels:
                self.update_column_header_style(header_label)
        
        # Update buttons
        if hasattr(self, 'add_btn'):
            self.update_button_style(self.add_btn)
        if hasattr(self, 'save_btn'):
            self.update_button_style(self.save_btn)
            
        # Update all existing row widgets
        for row_data in self.mapping_rows:
            row_data['input_combo'].setStyleSheet(self._get_combo_style())
            row_data['type_combo'].setStyleSheet(self._get_combo_style())
            row_data['behavior_combo'].setStyleSheet(self._get_combo_style())
            row_data['target_label'].setStyleSheet(self._get_target_label_style())
            row_data['select_btn'].setStyleSheet(self._get_small_button_style())
            row_data['remove_btn'].setStyleSheet(self._get_remove_button_style())
        
        # Update no selection message if visible
        if hasattr(self, 'no_selection_label'):
            self.update_no_selection_style()

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
        return f"color: {grey}; padding: 8px; border: 1px solid #555; border-radius: 4px;"
    
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
                padding: 3px;
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