"""
WALL-E Control System - Enhanced Controller Configuration Screen
Advanced interface for mapping Steam Deck controls with calibration and differential steering
"""

import json
from typing import Optional
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QComboBox, QCheckBox, QMessageBox,
    QProgressBar, QFrame
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QDateTime

from widgets.base_screen import BaseScreen
from core.config_manager import config_manager
from core.utils import error_boundary


class ControllerConfigScreen(BaseScreen):
    """Enhanced controller configuration with calibration and advanced mapping"""

    # Signals for calibration process
    calibration_update = pyqtSignal(str, float)  # control_name, value

    def _setup_screen(self):
        """Initialize enhanced controller configuration screen"""
        self.setFixedWidth(1180)

        # Controller state
        self.mapping_rows = []
        self.calibration_mode = False
        self.calibration_data = {}
        self.detected_controls = {}

        # Load configurations
        self.load_motion_config()
        self.load_controller_mappings()
        self.init_ui()

        # Connect to WebSocket for controller input
        if self.websocket:
            self.websocket.textMessageReceived.connect(self.handle_controller_input)

    def load_motion_config(self):
        """Load motion configuration for dropdowns"""
        config = config_manager.get_config("resources/configs/motion_config.json")
        self.groups = config.get("groups", {})
        self.emotions = config.get("emotions", [])
        self.movements = config.get("movements", {})

        # Load steam controls
        controls_config = config_manager.get_config("resources/configs/movement_controls.json")
        self.steam_controls = controls_config.get("steam_controls", [])

    def load_controller_mappings(self):
        """Load existing controller mappings"""
        self.controller_config = config_manager.get_config("resources/configs/controller_config.json")

    def init_ui(self):
        """Initialize enhanced user interface with styled panels"""
        # Main horizontal layout
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(90, 15, 15, 10)

        # Left side - mapping grid
        mapping_section = self._create_mapping_section()
        main_layout.addWidget(mapping_section, stretch=4)

        # Right side - styled control panel (reduced width)
        control_panel = self._create_control_panel()
        main_layout.addWidget(control_panel, stretch=1)

        self.setLayout(main_layout)

        # Load existing mappings
        self.populate_existing_mappings()

    def _create_mapping_section(self):
        """Create the controller mapping grid section"""
        mapping_frame = QFrame()
        mapping_frame.setStyleSheet("border: 2px solid #444; border-radius: 10px; background-color: #1e1e1e;")
        mapping_layout = QVBoxLayout(mapping_frame)
        mapping_layout.setContentsMargins(15, 10, 15, 10)

        # Grid header - moved 5px to the right with fixed widths matching grid
        header_layout = QGridLayout()
        header_layout.setContentsMargins(10, 0, 0, 0)  # 5px left margin shift
        headers = ["Control", "Type", "Target", "Min", "Max", "🏠", "↕️", "Pos"]
        header_layout.setHorizontalSpacing(8)
        header_font = QFont("Arial", 16, QFont.Weight.Bold)
        for i, header_text in enumerate(headers):
            header = QLabel(header_text)
            header.setFont(header_font)
            header.setStyleSheet("color: #e1a014; padding: 5px;")
            header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # Fixed widths to exactly match grid below
            if i == 0:  # Control
                header.setFixedWidth(152)
            elif i == 1:  # Type
                header.setFixedWidth(102)    
            elif i == 2:  # Target
                header.setFixedWidth(182)
            elif i == 3:  # Min
                header.setFixedWidth(45)
            elif i == 4:  # Max
                header.setFixedWidth(45)
            elif i == 5:  # Home
                header.setFixedWidth(40)
            elif i == 6:  # Inv
                header.setFixedWidth(25)
            elif i == 7:  # Pos
                header.setFixedWidth(60)
            header_layout.addWidget(header, 0, i)
        
        # Add stretch after Pos to account for delete button column space
        header_layout.setColumnStretch(8, 1)
        mapping_layout.addLayout(header_layout)

        # Scrollable grid area
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_layout.setContentsMargins(5, 5, 5, 5)
        self.grid_layout.setSpacing(5)
        self.grid_widget.setLayout(self.grid_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.grid_widget)
        scroll_area.setStyleSheet("border: 1px solid #555; border-radius: 6px; background-color: #2a2a2a;")

        mapping_layout.addWidget(scroll_area)
        return mapping_frame

    def _create_control_panel(self):
        """Create the styled controller control panel"""
        control_panel = QWidget()
        control_panel.setFixedWidth(240)  # Reduced from 275
        control_panel.setStyleSheet("""
        QWidget {
            background-color: #1e1e1e;
            border: 2px solid #e1a014;
            border-radius: 12px;
            color: white;
        }""")

        panel_layout = QVBoxLayout()
        panel_layout.setContentsMargins(8, 5, 8, 15)
        panel_layout.setSpacing(5)  # Increased spacing between sections

        # Header
        header = QLabel("CONTROLLER CONFIG")
        header.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("""
        QLabel {
            border: none;
            background-color: rgba(0, 0, 0, 0.9);
            color: #e1a014;
            padding: 6px 4px;
            border-radius: 6px;
            margin-bottom: 3px;
        }""")
        panel_layout.addWidget(header)

        # Controller status section
        status_section = self._create_status_section()
        panel_layout.addWidget(status_section)
        panel_layout.addSpacing(15)  # More space after status

        # Calibration section
        calibration_section = self._create_calibration_section()
        panel_layout.addWidget(calibration_section)
        panel_layout.addStretch()

        # Mapping operations section
        operations_section = self._create_operations_section()
        panel_layout.addWidget(operations_section)

        panel_layout.addStretch()
        control_panel.setLayout(panel_layout)
        return control_panel

    def _create_status_section(self):
        """Create controller status display section - just the status field"""
        # Only controller status - standalone with rounded edges
        self.controller_status = QLabel("Controller: Disconnected")
        self.controller_status.setFont(QFont("Arial", 11))
        self.controller_status.setStyleSheet("""
        QLabel {
            color: #FF4444; 
            padding: 8px 12px;
            border: 1px solid #555;
            border-radius: 8px;
            background-color: rgba(0, 0, 0, 0.3);
        }""")
        self.controller_status.setWordWrap(True)
        return self.controller_status

    def _create_calibration_section(self):
        """Create controller calibration section"""
        cal_frame = QWidget()
        cal_frame.setStyleSheet("""
        QWidget {
            border: 1px solid #555;
            border-radius: 8px;
            background-color: rgba(0, 0, 0, 0.3);
        }""")

        cal_layout = QVBoxLayout()
        cal_layout.setContentsMargins(10, 8, 10, 10)  # More padding
        cal_layout.setSpacing(8)  # More spacing between elements

        cal_header = QLabel("CALIBRATION")
        cal_header.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        cal_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cal_header.setStyleSheet("color: #e1a014; border: none; margin-bottom: 3px;")
        cal_layout.addWidget(cal_header)

        # Calibration progress
        self.calibration_progress = QProgressBar()
        self.calibration_progress.setRange(0, 100)
        self.calibration_progress.setValue(0)
        self.calibration_progress.setFixedHeight(20)
        self.calibration_progress.setStyleSheet("""
        QProgressBar {
            border: 1px solid #666;
            border-radius: 4px;
            text-align: center;
            background-color: #333;
            font-size: 11px;
        }
        QProgressBar::chunk {
            background-color: #e1a014;
            border-radius: 3px;
        }""")
        cal_layout.addWidget(self.calibration_progress)

        # Calibration instructions
        self.calibration_instructions = QLabel("Press 'Start Calibration' to begin")
        self.calibration_instructions.setFont(QFont("Arial", 10))
        self.calibration_instructions.setStyleSheet("color: #AAAAAA; padding: 3px;")
        self.calibration_instructions.setWordWrap(True)
        cal_layout.addWidget(self.calibration_instructions)

        # Buttons with more spacing
        button_style = """
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #4a4a4a, stop:1 #2a2a2a);
            color: white;
            border: 1px solid #666;
            border-radius: 6px;
            padding: 8px;
            text-align: center;
            font-weight: bold;
            font-size: 11px;
            margin: 2px 0px;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #5a5a5a, stop:1 #3a3a3a);
            border-color: #888;
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #3a3a3a, stop:1 #1a1a1a);
            border-color: #e1a014;
        }
        QPushButton:disabled {
            background: #333;
            color: #666;
            border-color: #444;
        }"""

        self.start_calibration_btn = QPushButton("🎯 START CAL")
        self.start_calibration_btn.setFont(QFont("Arial", 11))
        self.start_calibration_btn.clicked.connect(self.start_calibration)
        self.start_calibration_btn.setStyleSheet(button_style)
        self.start_calibration_btn.setFixedHeight(32)
        cal_layout.addWidget(self.start_calibration_btn)

        cal_layout.addSpacing(4)  # Space between buttons

        self.save_calibration_btn = QPushButton("💾 SAVE CAL")
        self.save_calibration_btn.setFont(QFont("Arial", 11))
        self.save_calibration_btn.clicked.connect(self.save_calibration)
        self.save_calibration_btn.setStyleSheet(button_style)
        self.save_calibration_btn.setFixedHeight(32)
        self.save_calibration_btn.setEnabled(False)
        cal_layout.addWidget(self.save_calibration_btn)

        cal_frame.setLayout(cal_layout)
        return cal_frame

    def _create_operations_section(self):
        """Create mapping operations section"""
        ops_frame = QWidget()
        ops_frame.setStyleSheet("""
        QWidget {
            border: 1px solid #555;
            border-radius: 8px;
            background-color: rgba(0, 0, 0, 0.3);
        }""")

        ops_layout = QVBoxLayout()
        ops_layout.setContentsMargins(10, 8, 10, 12)  # More padding
        ops_layout.setSpacing(8)  # More spacing between elements

        ops_header = QLabel("OPERATIONS")
        ops_header.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        ops_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ops_header.setStyleSheet("color: #e1a014; border: none; margin-bottom: 3px;")
        ops_layout.addWidget(ops_header)

        button_style = """
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #4a4a4a, stop:1 #2a2a2a);
            color: white;
            border: 1px solid #666;
            border-radius: 6px;
            padding: 8px;
            text-align: center;
            font-weight: bold;
            font-size: 11px;
            margin: 2px 0px;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #5a5a5a, stop:1 #3a3a3a);
            border-color: #888;
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #3a3a3a, stop:1 #1a1a1a);
            border-color: #e1a014;
        }"""

        # Operation buttons with spacing
        operation_buttons = [
            ("➕ ADD MAP", self.add_new_mapping, "Add new controller mapping"),
            ("🔄 REFRESH", self.refresh_mappings, "Refresh controller detection"),
            ("💾 SAVE", self.save_all_mappings, "Save all mappings to file"),
        ]
        for i, (text, callback, tooltip) in enumerate(operation_buttons):
            btn = QPushButton(text)
            btn.setFont(QFont("Arial", 11))
            btn.setToolTip(tooltip)
            btn.clicked.connect(callback)
            btn.setStyleSheet(button_style)
            btn.setFixedHeight(32)
            ops_layout.addWidget(btn)
            
            # Add spacing between buttons (but not after the last one)
            if i < len(operation_buttons) - 1:
                ops_layout.addSpacing(4)

        ops_frame.setLayout(ops_layout)
        return ops_frame

    def add_mapping_row(self, control=None, control_type=None, target=None,
                        min_val=0, max_val=100, center_val=50, invert=False):
        """Add a new controller mapping row with read-only min/max/home values"""
        row = len(self.mapping_rows)

        # Control selection
        combo_style = """
        QComboBox {
            background-color: #333;
            color: #AAAAAA;
            border: 1px solid #555;
            border-radius: 4px;
            padding: 4px;
        }
        """
        control_cb = QComboBox()
        control_cb.addItems(["Select Control..."] + self.steam_controls)
        control_cb.setFont(QFont("Arial", 12))
        control_cb.setFixedWidth(150)
        control_cb.setStyleSheet(combo_style)
        if control:
            control_cb.setCurrentText(control)

        # Input type selection
        type_cb = QComboBox()
        type_cb.addItems([
            "joystick",  # Analog stick (returns to center)
            "button",    # Digital on/off
            "trigger",   # Analog pressure sensitive
            "dpad"       # Digital directional
        ])
        type_cb.setFont(QFont("Arial", 12))
        type_cb.setFixedWidth(100)
        type_cb.setStyleSheet(combo_style)
        if control_type:
            type_cb.setCurrentText(control_type)

        # Target selection
        target_cb = QComboBox()
        target_cb.setFont(QFont("Arial", 12))
        target_cb.setFixedWidth(180)
        target_cb.setStyleSheet(combo_style)

        # Read-only value displays
        def make_value_label(value: float) -> QLabel:
            lbl = QLabel(str(value))
            lbl.setFont(QFont("Arial", 12))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedWidth(40)
            lbl.setStyleSheet(
                "QLabel { background-color: #333; color: #AAAAAA; "
                "border: 1px solid #555; border-radius: 4px; padding: 4px; }"
            )
            return lbl

        min_display = make_value_label(min_val)
        max_display = make_value_label(max_val)
        center_display = make_value_label(center_val)

        # Invert checkbox
        invert_cb = QCheckBox()
        invert_cb.setChecked(invert)
        invert_cb.setFixedWidth(20)
        invert_cb.setStyleSheet("""
        QCheckBox::indicator { width: 16px; height: 16px; }
        QCheckBox::indicator:unchecked { background-color: #333; border: 1px solid #666; border-radius: 2px; }
        QCheckBox::indicator:checked   { background-color: #e1a014; border: 1px solid #e1a014; border-radius: 2px; }
        """)

        # Position (live) display
        position_label = QLabel("0.00")
        position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        position_label.setStyleSheet("color:#AAAAAA; border:1px solid #555; border-radius:4px; padding:4px;")
        position_label.setFixedWidth(60)

        # Remove button - transparent background
        remove_btn = QPushButton("❌")
        remove_btn.setFont(QFont("Arial", 12))
        remove_btn.setMaximumWidth(40)
        remove_btn.clicked.connect(lambda: self.remove_mapping_row(row))
        remove_btn.setStyleSheet("""
        QPushButton { 
            background-color: transparent; 
            color: #FF4444; 
            border: 1px solid #FF4444; 
            border-radius: 4px; 
            padding: 4px; 
        }
        QPushButton:hover { 
            background-color: rgba(255, 68, 68, 0.2); 
            color: #FF6666;
            border-color: #FF6666;
        }
        """)

        # Update target options based on type
        def update_target_options():
            selected_type = type_cb.currentText()
            target_cb.clear()
            if selected_type in ["joystick", "trigger"]:
                # Analog controls can map to servos, tracks, or joystick axes
                target_cb.addItems(["Select Target..."]
                                   + [f"Servo: {name}" for name in self.get_servo_names()]
                                   + ["Track: Differential", "Track: Left", "Track: Right"]
                                   + ["Joystick: Both Axes"])
            elif selected_type == "button":
                # Buttons can trigger scenes, scripts, or sounds
                target_cb.addItems(["Select Target..."]
                                   + [f"Scene: {scene}" for scene in self.emotions]
                                   + ["Script: Custom", "Sound: Beep", "Sound: Alert"])
            elif selected_type == "dpad":
                # D-pad for directional control
                target_cb.addItems(["Select Target..."]
                                   + ["Movement: Forward/Back", "Movement: Left/Right", "Movement: Rotate"])

        type_cb.currentTextChanged.connect(update_target_options)
        update_target_options()
        if target:
            target_cb.setCurrentText(target)

        # Add widgets to grid (Position col=7, Remove col=8)
        self.grid_layout.addWidget(control_cb,    row, 0)
        self.grid_layout.addWidget(type_cb,       row, 1)
        self.grid_layout.addWidget(target_cb,     row, 2)
        self.grid_layout.addWidget(min_display,   row, 3)
        self.grid_layout.addWidget(max_display,   row, 4)
        self.grid_layout.addWidget(center_display,row, 5)
        self.grid_layout.addWidget(invert_cb,     row, 6)
        self.grid_layout.addWidget(position_label,row, 7)
        self.grid_layout.addWidget(remove_btn,    row, 8)

        # Store row data
        row_data = {
            'control_cb': control_cb,
            'type_cb': type_cb,
            'target_cb': target_cb,
            'min_display': min_display,
            'max_display': max_display,
            'center_display': center_display,
            'invert_cb': invert_cb,
            'position_label': position_label,
            'remove_btn': remove_btn
        }
        self.mapping_rows.append(row_data)

    def get_servo_names(self) -> list:
        """Get list of servo names from configuration"""
        try:
            servo_config = config_manager.get_config("resources/configs/servo_config.json")
            return [v.get("name", f"Channel {k}") for k, v in servo_config.items() if v.get("name")]
        except Exception:
            return ["Head Pan", "Head Tilt", "Left Arm", "Right Arm"]  # Fallback

    def remove_mapping_row(self, index: int):
        """Remove a controller mapping row"""
        if 0 <= index < len(self.mapping_rows):
            row_data = self.mapping_rows[index]
            # Remove widgets from grid
            for widget in row_data.values():
                if hasattr(widget, 'deleteLater'):
                    widget.deleteLater()
            # Remove from list
            self.mapping_rows.pop(index)
            # Rebuild grid layout to fix row indices
            self.rebuild_grid()

    def rebuild_grid(self):
        """Rebuild the grid layout after row removal"""
        # Clear the layout
        for i in reversed(range(self.grid_layout.count())):
            w = self.grid_layout.itemAt(i).widget()
            if w:
                self.grid_layout.removeWidget(w)

        # Re-add all widgets with correct row indices
        for row, row_data in enumerate(self.mapping_rows):
            self.grid_layout.addWidget(row_data['control_cb'],     row, 0)
            self.grid_layout.addWidget(row_data['type_cb'],        row, 1)
            self.grid_layout.addWidget(row_data['target_cb'],      row, 2)
            self.grid_layout.addWidget(row_data['min_display'],    row, 3)
            self.grid_layout.addWidget(row_data['max_display'],    row, 4)
            self.grid_layout.addWidget(row_data['center_display'], row, 5)
            self.grid_layout.addWidget(row_data['invert_cb'],      row, 6)
            self.grid_layout.addWidget(row_data['position_label'], row, 7)
            self.grid_layout.addWidget(row_data['remove_btn'],     row, 8)
            # Update remove button callback with the new index
            try:
                row_data['remove_btn'].clicked.disconnect()
            except Exception:
                pass
            row_data['remove_btn'].clicked.connect(lambda checked=False, r=row: self.remove_mapping_row(r))

    def populate_existing_mappings(self):
        """Load and populate existing controller mappings"""
        for control, cfg in self.controller_config.items():
            control_type = cfg.get("type", "button")
            target = "Select Target..."

            # Determine target string and value sources
            min_val = 0
            max_val = 100
            center_val = 50
            invert = False

            # Prefer calibrated values if available
            cal = self.get_calibrated_values(control)
            cal_has_data = cal is not None and isinstance(cal, dict)

            # Convert config to display format & extract defaults
            if control_type in ("control", "servo_control"):
                servo = cfg.get("servo", {}) or cfg.get("movement", {})
                target = f"Servo: {servo.get('name', 'Unknown')}"
                if not cal_has_data:
                    min_val = int(servo.get("min", min_val))
                    max_val = int(servo.get("max", max_val))
                    center_val = int(servo.get("center", center_val))
                invert = bool(servo.get("invert", False))
            elif control_type == "scene" or control_type == "scene_trigger":
                scene = cfg.get("scene", {})
                target = f"Scene: {scene.get('name', cfg.get('emotion', 'Unknown'))}"
            elif control_type == "track_control":
                track = cfg.get("track", {})
                side = track.get("side", "unknown")
                target = f"Track: {side.title()}"
                if not cal_has_data:
                    min_val = int(track.get("min", min_val))
                    max_val = int(track.get("max", max_val))
                    center_val = int(track.get("center", center_val))
                invert = bool(track.get("invert", False))
            elif control_type == "differential_steering":
                target = "Track: Differential"
                tracks = cfg.get("tracks", {})
                # differential uses axis blocks; labels show X axis mins as indicative
                if not cal_has_data:
                    x_axis = tracks.get("x_axis", {})
                    min_val = int(x_axis.get("min", min_val))
                    max_val = int(x_axis.get("max", max_val))
                    center_val = int(x_axis.get("center", center_val))
                invert = bool(tracks.get("invert", False))
            elif control_type == "movement_control":
                target = f"Movement: {cfg.get('movement', {}).get('type', 'Unknown')}"
                mv = cfg.get("movement", {})
                if not cal_has_data:
                    min_val = int(mv.get("min", min_val))
                    max_val = int(mv.get("max", max_val))
                    center_val = int(mv.get("center", center_val))

            # If calibration exists, prefer it for the labels
            if cal_has_data:
                try:
                    min_val = int(cal.get("min", min_val))
                    max_val = int(cal.get("max", max_val))
                    center_val = int(cal.get("center", center_val))
                except Exception:
                    pass

            # Add the mapping row
            self.add_mapping_row(
                control=control,
                control_type=control_type if control_type != "control" else "joystick",
                target=target,
                min_val=min_val,
                max_val=max_val,
                center_val=center_val,
                invert=invert
            )

    @error_boundary
    def start_calibration(self, checked=False):
        """Toggle controller calibration process with backend polling"""
        if not self.calibration_mode:
            # Start calibration mode
            self.calibration_mode = True
            self.calibration_data = {}
            self.calibration_progress.setValue(0)

            # Update button to show "STOP CAL"
            self.start_calibration_btn.setText("🛑 STOP CAL")
            self.start_calibration_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FF6666, stop:1 #CC4444);
                color: white;
                border: 1px solid #FF6666;
                border-radius: 6px;
                padding: 8px;
                text-align: center;
                font-weight: bold;
                font-size: 11px;
                margin: 2px 0px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FF8888, stop:1 #DD5555);
                border-color: #FF8888;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #CC4444, stop:1 #AA2222);
                border-color: #e1a014;
            }""")
            self.save_calibration_btn.setEnabled(False)

            # Update instructions
            self.calibration_instructions.setText(
                "Move all controls to extremes. Backend polling every 100ms... Click STOP when done."
            )
            self.calibration_instructions.setStyleSheet("color: #e1a014; padding: 2px;")

            # Start backend polling timer for calibration
            self.calibration_timer = QTimer()
            self.calibration_timer.timeout.connect(self.request_controller_positions)
            self.calibration_timer.start(100)  # Poll every 100ms

            # Send calibration start command to backend
            self.send_websocket_message("start_controller_calibration")
            self.logger.info("Started controller calibration mode with 100ms backend polling")
        else:
            # Stop calibration mode
            self.stop_calibration()

    def stop_calibration(self):
        """Stop calibration mode and validate data"""
        self.calibration_mode = False

        # Stop polling timer
        if hasattr(self, 'calibration_timer'):
            self.calibration_timer.stop()

        # Reset button to "START CAL"
        self.start_calibration_btn.setText("🎯 START CAL")
        self.start_calibration_btn.setStyleSheet("""
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #4a4a4a, stop:1 #2a2a2a);
            color: white;
            border: 1px solid #666;
            border-radius: 6px;
            padding: 8px;
            text-align: center;
            font-weight: bold;
            font-size: 11px;
            margin: 2px 0px;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #5a5a5a, stop:1 #3a3a3a);
            border-color: #888;
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #3a3a3a, stop:1 #1a1a1a);
            border-color: #e1a014;
        }
        QPushButton:disabled {
            background: #333;
            color: #666;
            border-color: #444;
        }""")

        # Validate calibration data before enabling save
        valid_data = self.validate_calibration_data()
        if valid_data:
            self.save_calibration_btn.setEnabled(True)
            self.calibration_instructions.setText(
                f"Calibration stopped. {len(self.calibration_data)} controls detected. Click SAVE to apply."
            )
            self.calibration_instructions.setStyleSheet("color: #44FF44; padding: 2px;")
            self.logger.info(f"Calibration stopped with valid data for {len(self.calibration_data)} controls")
        else:
            self.save_calibration_btn.setEnabled(False)
            self.calibration_instructions.setText(
                "Calibration stopped. No valid movement detected. Try again and move controls."
            )
            self.calibration_instructions.setStyleSheet("color: #FF6666; padding: 2px;")
            self.logger.warning("Calibration stopped with insufficient/invalid data")

        # Send stop command to backend
        self.send_websocket_message("stop_controller_calibration")

    def validate_calibration_data(self) -> bool:
        """Validate calibration data to ensure meaningful ranges were captured"""
        if not self.calibration_data:
            return False
        valid_controls = 0
        for control_name, cal_data in self.calibration_data.items():
            min_val = cal_data.get("min", 0.0)
            max_val = cal_data.get("max", 0.0)
            center_val = cal_data.get("center", 0.0)
            range_size = abs(max_val - min_val)
            if range_size > 0.1:
                if min_val <= center_val <= max_val or max_val <= center_val <= min_val:
                    valid_controls += 1
                    self.logger.debug(
                        f"Valid calibration for {control_name}: "
                        f"min={min_val:.2f}, max={max_val:.2f}, center={center_val:.2f}, range={range_size:.2f}"
                    )
                else:
                    self.logger.warning(
                        f"Invalid center for {control_name}: center={center_val:.2f} "
                        f"not between min={min_val:.2f} and max={max_val:.2f}"
                    )
            else:
                self.logger.warning(
                    f"Insufficient movement for {control_name}: range={range_size:.2f}"
                )
        return valid_controls > 0

    def request_controller_positions(self):
        """Request current controller positions from backend during calibration"""
        if self.calibration_mode:
            self.send_websocket_message("get_controller_positions")

    @error_boundary
    def save_calibration(self):
        """Save calibration data, update displays, and push to backend"""
        if not self.calibration_data:
            QMessageBox.warning(self, "No Data", "No calibration data collected.")
            return

        # Validate again
        if not self.validate_calibration_data():
            QMessageBox.warning(
                self, "Invalid Data",
                "Calibration data is invalid or insufficient.\n"
                "Ensure controls were moved through their full range."
            )
            return

        # Update labels with calibrated values
        self.update_calibration_displays()

        # Save calibration data to configuration
        calibration_config = {
            "calibration_date": QDateTime.currentDateTime().toString(Qt.ISODate),
            "controls": self.calibration_data
        }
        success = config_manager.save_config("resources/configs/controller_calibration.json", calibration_config)
        if success:
            # Push calibration config to backend
            self.send_websocket_message("controller_calibration_update", calibration=calibration_config)
            QMessageBox.information(
                self, "Calibration Saved",
                f"Calibration data saved for {len(self.calibration_data)} controls.\n"
                f"Min/Max values updated and pushed to backend."
            )
            # Reset UI state
            self.save_calibration_btn.setEnabled(False)
            self.calibration_progress.setValue(100)
            self.calibration_instructions.setText("Calibration completed and pushed to backend.")
            self.logger.info(f"Saved and pushed calibration for {len(self.calibration_data)} controls to backend")
        else:
            QMessageBox.critical(self, "Save Failed", "Failed to save calibration data.")

    def validate_single_control(self, control_name: str, cal_data: dict) -> bool:
        """Validate a single control's calibration data"""
        min_val = cal_data.get("min", 0.0)
        max_val = cal_data.get("max", 0.0)
        center_val = cal_data.get("center", 0.0)
        range_size = abs(max_val - min_val)
        return (range_size > 0.1 and
                (min_val <= center_val <= max_val or max_val <= center_val <= min_val))

    def update_calibration_displays(self):
        """Update the min/max/center display labels with calibrated values"""
        try:
            for row_data in self.mapping_rows:
                control_name = row_data['control_cb'].currentText()
                if control_name in self.calibration_data:
                    cal_data = self.calibration_data[control_name]
                    row_data['min_display'].setText(f"{cal_data['min']:.2f}")
                    row_data['max_display'].setText(f"{cal_data['max']:.2f}")
                    row_data['center_display'].setText(f"{cal_data['center']:.2f}")
                    # Highlight updated values
                    updated_style = (
                        "QLabel { background-color: #2a4a2a; color: #44FF44; "
                        "border: 1px solid #44FF44; border-radius: 4px; padding: 4px; }"
                    )
                    row_data['min_display'].setStyleSheet(updated_style)
                    row_data['max_display'].setStyleSheet(updated_style)
                    row_data['center_display'].setStyleSheet(updated_style)
        except Exception as e:
            self.logger.error(f"Error updating calibration displays: {e}")

    @error_boundary
    def handle_controller_input(self, message: str):
        """Handle incoming controller input data"""
        try:
            data = json.loads(message)
            if data.get("type") == "controller_input":
                control_name = data.get("control")
                value = data.get("value", 0.0)
                axis = data.get("axis", None)  # "x" or "y" for joystick

                # Update controller status
                if not self.controller_status.text().startswith("Controller: Connected"):
                    self.controller_status.setText("Controller: Connected")
                    self.controller_status.setStyleSheet("color: #44FF44; padding: 3px;")

                # Update position display
                self.update_position_display(control_name, value, axis)

                # Handle calibration data collection
                if self.calibration_mode and control_name:
                    if control_name not in self.calibration_data:
                        self.calibration_data[control_name] = {"min": value, "max": value, "center": value}
                    else:
                        cal_data = self.calibration_data[control_name]
                        cal_data["min"] = min(cal_data["min"], value)
                        cal_data["max"] = max(cal_data["max"], value)
                        # Update center if value is closer to zero
                        if abs(value) < abs(cal_data.get("center", 0.0)):
                            cal_data["center"] = value

                    # Update progress (roughly 10% per unique control moved)
                    progress = min(100, (len(self.calibration_data) * 10))
                    self.calibration_progress.setValue(progress)

                    # Enable save button if we have "enough" data
                    if len(self.calibration_data) >= 5:
                        self.save_calibration_btn.setEnabled(True)
        except Exception as e:
            self.logger.error(f"Error handling controller input: {e}")

    def update_position_display(self, control_name: str, value: float, axis: str = None):
        """Update the position display for a specific control"""
        try:
            for row_data in self.mapping_rows:
                current_control = row_data['control_cb'].currentText()
                if current_control == control_name:
                    position_label = row_data['position_label']
                    # Format the display
                    if axis:
                        # Keep both axes if available
                        current_text = position_label.text()
                        if axis == "x":
                            # Preserve any existing Y
                            if "Y:" in current_text:
                                y_part = current_text.split("Y:")[1]
                                position_label.setText(f"X:{value:.2f} Y:{y_part}")
                            else:
                                position_label.setText(f"X:{value:.2f}")
                        elif axis == "y":
                            if "X:" in current_text:
                                x_part = current_text.split(" ")[0]
                                position_label.setText(f"{x_part} Y:{value:.2f}")
                            else:
                                position_label.setText(f"Y:{value:.2f}")
                    else:
                        position_label.setText(f"{value:.2f}")

                    # Color coding
                    if abs(value) > 0.8:
                        color = "#FF6666"  # red extreme
                    elif abs(value) > 0.5:
                        color = "#FFAA00"  # orange medium
                    elif abs(value) > 0.1:
                        color = "#44FF44"  # green active
                    else:
                        color = "#AAAAAA"  # gray center/inactive
                    position_label.setStyleSheet(
                        f"color: {color}; border: 1px solid #555; border-radius: 4px; padding: 4px;"
                    )
        except Exception as e:
            self.logger.error(f"Error updating position display: {e}")

    @error_boundary
    def add_new_mapping(self, checked=False):
        """Add a new empty mapping row"""
        self.add_mapping_row()

    @error_boundary
    def refresh_mappings(self):
        """Refresh controller detection"""
        self.send_websocket_message("refresh_controller")
        self.controller_status.setText("Controller: Refreshing...")
        self.controller_status.setStyleSheet("color: #FFAA00; padding: 3px;")

    @error_boundary
    def toggle_test_mode(self):
        """Toggle controller test mode - intentionally empty"""
        pass

    @error_boundary
    def save_all_mappings(self):
        """Save all controller mappings to configuration file (values from calibration/config only)"""
        config = {}

        for row_data in self.mapping_rows:
            control = row_data['control_cb'].currentText()
            control_type = row_data['type_cb'].currentText()
            target = row_data['target_cb'].currentText()
            invert = row_data['invert_cb'].isChecked()

            if control == "Select Control..." or target == "Select Target...":
                continue

            # Source min/max/center strictly from calibration (or saved calibration file),
            # not from UI labels (UI is read-only and mirrors those sources).
            cal_data = self.get_calibrated_values(control)
            # Provide robust defaults if not calibrated yet
            if not cal_data:
                cal_data = {"min": -100, "max": 100, "center": 0}

            min_val = cal_data.get("min", -100)
            max_val = cal_data.get("max", 100)
            center_val = cal_data.get("center", 0)

            # Build configuration based on type and target
            if target.startswith("Servo:"):
                servo_name = target.replace("Servo: ", "")
                maestro_info = self.get_maestro_info_for_servo(servo_name)
                config[control] = {
                    "type": "servo_control",
                    "input_type": control_type,
                    "servo": {
                        "name": servo_name,
                        "maestro": maestro_info,
                        "min": min_val,
                        "max": max_val,
                        "center": center_val,
                        "invert": invert
                    }
                }
            elif target.startswith("Scene:"):
                scene_name = target.replace("Scene: ", "")
                config[control] = {
                    "type": "scene_trigger",
                    "input_type": control_type,
                    "scene": {
                        "name": scene_name,
                        "trigger_threshold": 0.5  # For button presses
                    }
                }
            elif target.startswith("Track:"):
                track_type = target.replace("Track: ", "")
                if track_type == "Differential":
                    # Differential steering uses both axes
                    config[control] = {
                        "type": "differential_steering",
                        "input_type": control_type,
                        "tracks": {
                            "left_channel": "m2_ch0",
                            "right_channel": "m2_ch1",
                            "invert": invert,
                            "x_axis": {  # turning component
                                "min": min_val, "max": max_val, "center": center_val, "invert": invert
                            },
                            "y_axis": {  # forward/back component
                                "min": min_val, "max": max_val, "center": center_val, "invert": False
                            }
                        }
                    }
                elif track_type == "Left":
                    config[control] = {
                        "type": "track_control",
                        "input_type": control_type,
                        "track": {
                            "channel": "m2_ch0",
                            "side": "left",
                            "min": min_val, "max": max_val, "center": center_val,
                            "invert": invert
                        }
                    }
                elif track_type == "Right":
                    config[control] = {
                        "type": "track_control",
                        "input_type": control_type,
                        "track": {
                            "channel": "m2_ch1",
                            "side": "right",
                            "min": min_val, "max": max_val, "center": center_val,
                            "invert": invert
                        }
                    }
            elif target.startswith("Joystick:"):
                joystick_type = target.replace("Joystick: ", "")
                if joystick_type == "Both Axes":
                    config[control] = {
                        "type": "joystick_dual_axis",
                        "input_type": control_type,
                        "axes": {
                            "x_axis": {
                                "target": "servo",
                                "channel": "m1_ch0",  # default to head pan
                                "min": min_val, "max": max_val, "center": center_val, "invert": invert
                            },
                            "y_axis": {
                                "target": "servo",
                                "channel": "m1_ch1",  # default to head tilt
                                "min": min_val, "max": max_val, "center": center_val, "invert": False
                            }
                        }
                    }
            elif target.startswith("Movement:"):
                movement_type = target.replace("Movement: ", "")
                config[control] = {
                    "type": "movement_control",
                    "input_type": control_type,
                    "movement": {
                        "type": movement_type,
                        "min": min_val, "max": max_val, "center": center_val
                    }
                }
            elif target.startswith("Script:"):
                script_name = target.replace("Script: ", "")
                config[control] = {
                    "type": "maestro_script",
                    "input_type": control_type,
                    "script": {
                        "name": script_name,
                        "trigger_threshold": 0.5
                    }
                }
            elif target.startswith("Sound:"):
                sound_name = target.replace("Sound: ", "")
                config[control] = {
                    "type": "sound_trigger",
                    "input_type": control_type,
                    "sound": {
                        "name": sound_name,
                        "trigger_threshold": 0.5
                    }
                }

        # Save & push
        success = config_manager.save_config("resources/configs/controller_config.json", config)
        if success:
            # Push controller configuration to backend
            self.send_websocket_message("controller_config_update", config=config)
            QMessageBox.information(
                self, "Saved",
                f"Controller configuration saved with {len(config)} mappings and pushed to backend."
            )
            self.logger.info(f"Saved {len(config)} controller mappings and pushed to backend")
        else:
            QMessageBox.critical(self, "Error", "Failed to save controller configuration.")

    def get_maestro_info_for_servo(self, servo_name: str) -> str:
        """Get Maestro channel information for a servo by name"""
        try:
            servo_config = config_manager.get_config("resources/configs/servo_config.json")
            for channel_key, servo_data in servo_config.items():
                if servo_data.get("name") == servo_name:
                    # Parse channel key like "m1_ch0" into "Maestro 1 / Ch 0"
                    parts = channel_key.split("_")
                    if len(parts) == 2:
                        maestro_num = parts[0][1:]  # remove 'm'
                        channel_num = parts[1][2:]  # remove 'ch'
                        return f"Maestro {maestro_num} / Ch {channel_num}"
            return "Unknown"
        except Exception as e:
            self.logger.error(f"Error getting maestro info for {servo_name}: {e}")
            return "Unknown"

    @error_boundary
    def create_differential_steering_logic(self, left_input: float, right_input: float,
                                           forward_input: float) -> tuple:
        """
        Create differential steering logic for track control
        Args:
            left_input: Left turn component (-1.0 to 1.0)
            right_input: Right turn component (-1.0 to 1.0)
            forward_input: Forward/back input (-1.0 to 1.0)
        Returns:
            tuple: (left_track_pulse, right_track_pulse) in 1000-2000 range
        """
        # Convert normalized inputs to servo pulse values (1000-2000)
        center_pulse = 1500
        max_range = 500

        # Basic differential steering algorithm
        if abs(left_input) > 0.1:
            left_speed = -abs(left_input)
            right_speed = abs(left_input)
        elif abs(right_input) > 0.1:
            left_speed = abs(right_input)
            right_speed = -abs(right_input)
        else:
            left_speed = forward_input
            right_speed = forward_input

        left_pulse = center_pulse + int(left_speed * max_range)
        right_pulse = center_pulse + int(right_speed * max_range)
        left_pulse = max(1000, min(2000, left_pulse))
        right_pulse = max(1000, min(2000, right_pulse))
        return left_pulse, right_pulse

    @error_boundary
    def handle_differential_steering(self, control_name: str, x_value: float, y_value: float = 0.0):
        """Handle differential steering input for track control"""
        try:
            # Find the mapping configuration for this control
            mapping = self.controller_config.get(control_name, {})
            if mapping.get("type") != "differential_steering":
                return

            tracks = mapping.get("tracks", {})
            left_channel = tracks.get("left_channel", "m2_ch0")
            right_channel = tracks.get("right_channel", "m2_ch1")
            invert = tracks.get("invert", False)

            # Apply inversion if configured
            if invert:
                x_value = -x_value
                y_value = -y_value

            # Calculate differential steering values
            left_pulse, right_pulse = self.create_differential_steering_logic(
                x_value if x_value < 0 else 0,   # Left turn component
                x_value if x_value > 0 else 0,   # Right turn component
                y_value                           # Forward/backward component
            )

            # Send servo commands to backend
            self.send_websocket_message("servo", channel=left_channel, pos=left_pulse)
            self.send_websocket_message("servo", channel=right_channel, pos=right_pulse)
            self.logger.debug(f"Differential steering: L={left_pulse}, R={right_pulse}")
        except Exception as e:
            self.logger.error(f"Error in differential steering: {e}")

    @error_boundary
    def process_controller_mapping(self, control_name: str, raw_value: float):
        """Process a controller input through its mapping configuration"""
        try:
            mapping = self.controller_config.get(control_name, {})
            if not mapping:
                return

            mapping_type = mapping.get("type")
            # Apply calibration
            calibrated_value = self.apply_calibration(control_name, raw_value)

            # Handle different mapping types
            if mapping_type == "servo_control":
                self.handle_servo_mapping(mapping, calibrated_value)
            elif mapping_type == "scene_trigger":
                self.handle_scene_mapping(mapping, calibrated_value)
            elif mapping_type == "differential_steering":
                # In practice you'd track both axes and call handle_differential_steering with x/y
                self.handle_differential_steering(control_name, calibrated_value)
            elif mapping_type == "track_control":
                self.handle_track_mapping(mapping, calibrated_value)
            elif mapping_type == "maestro_script":
                self.handle_script_mapping(mapping, calibrated_value)
            elif mapping_type == "sound_trigger":
                self.handle_sound_mapping(mapping, calibrated_value)
        except Exception as e:
            self.logger.error(f"Error processing controller mapping for {control_name}: {e}")

    def apply_calibration(self, control_name: str, raw_value: float) -> float:
        """Apply calibration data to raw controller input"""
        try:
            calibration_config = config_manager.get_config("resources/configs/controller_calibration.json")
            control_cal = calibration_config.get("controls", {}).get(control_name, {})
            if control_cal:
                min_val = control_cal.get("min", -1.0)
                max_val = control_cal.get("max", 1.0)
                center_val = control_cal.get("center", 0.0)
                # Deadzone around center
                deadzone = 0.05
                if abs(raw_value - center_val) < deadzone:
                    return 0.0
                # Scale to -1.0 to 1.0
                if raw_value > center_val:
                    return (raw_value - center_val) / (max_val - center_val) if (max_val - center_val) else 0.0
                else:
                    return (raw_value - center_val) / (center_val - min_val) if (center_val - min_val) else 0.0
            return raw_value
        except Exception as e:
            self.logger.debug(f"Calibration not available for {control_name}: {e}")
            return raw_value

    def handle_servo_mapping(self, mapping: dict, value: float):
        """Handle servo control mapping"""
        servo = mapping.get("servo", {})
        servo_name = servo.get("name")
        min_val = servo.get("min", 1000)
        max_val = servo.get("max", 2000)
        center_val = servo.get("center", 1500)
        invert = servo.get("invert", False)
        if invert:
            value = -value

        # Convert normalized value (-1 to 1) to servo pulse
        if value >= 0:
            pulse = center_val + int(value * (max_val - center_val))
        else:
            pulse = center_val + int(value * (center_val - min_val))
        pulse = max(min_val, min(max_val, pulse))

        # Find channel
        channel = self.get_channel_for_servo(servo_name)
        if channel:
            self.send_websocket_message("servo", channel=channel, pos=pulse)

    def handle_scene_mapping(self, mapping: dict, value: float):
        """Handle scene trigger mapping"""
        scene = mapping.get("scene", {})
        scene_name = scene.get("name")
        threshold = scene.get("trigger_threshold", 0.5)
        if abs(value) > threshold:
            self.send_websocket_message("scene", emotion=scene_name)

    def handle_track_mapping(self, mapping: dict, value: float):
        """Handle single track control mapping"""
        track = mapping.get("track", {})
        channel = track.get("channel")
        invert = track.get("invert", False)
        min_val = track.get("min", 1000)
        max_val = track.get("max", 2000)
        center_val = track.get("center", 1500)
        if invert:
            value = -value

        # Convert to servo pulse
        if value >= 0:
            pulse = center_val + int(value * (max_val - center_val))
        else:
            pulse = center_val + int(value * (center_val - min_val))
        pulse = max(min_val, min(max_val, pulse))
        self.send_websocket_message("servo", channel=channel, pos=pulse)

    def handle_script_mapping(self, mapping: dict, value: float):
        """Handle Maestro script trigger mapping"""
        script = mapping.get("script", {})
        script_name = script.get("name")
        threshold = script.get("trigger_threshold", 0.5)
        if abs(value) > threshold:
            self.send_websocket_message("maestro_script", script=script_name)

    def handle_sound_mapping(self, mapping: dict, value: float):
        """Handle sound trigger mapping"""
        sound = mapping.get("sound", {})
        sound_name = sound.get("name")
        threshold = sound.get("trigger_threshold", 0.5)
        if abs(value) > threshold:
            self.send_websocket_message("play_sound", sound=sound_name)

    def get_channel_for_servo(self, servo_name: str) -> Optional[str]:
        """Get the channel key for a servo by name"""
        try:
            servo_config = config_manager.get_config("resources/configs/servo_config.json")
            for channel_key, servo_data in servo_config.items():
                if servo_data.get("name") == servo_name:
                    return channel_key
            return None
        except Exception as e:
            self.logger.error(f"Error getting channel for servo {servo_name}: {e}")
            return None

    def get_calibrated_values(self, control_name: str) -> dict:
        """Get calibrated min/max/center values for a control, or defaults"""
        try:
            # First check current session calibration data
            if control_name in self.calibration_data:
                return self.calibration_data[control_name]

            # Otherwise check saved calibration file
            calibration_config = config_manager.get_config("resources/configs/controller_calibration.json")
            controls = calibration_config.get("controls", {})
            if control_name in controls:
                return controls[control_name]

            # None if no data yet (caller will decide defaults)
            return None
        except Exception as e:
            self.logger.error(f"Error getting calibrated values for {control_name}: {e}")
            return None

    def cleanup(self):
        """Cleanup controller screen resources"""
        # Stop calibration if active
        if self.calibration_mode:
            self.stop_calibration()
        super().cleanup()