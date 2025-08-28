"""
WALL-E Control System - Controller Configuration Screen
Interface for mapping Steam Deck controls to robot movements
"""

from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, 
                            QScrollArea, QWidget, QComboBox, QCheckBox, QMessageBox)
from PyQt6.QtCore import Qt

from widgets.base_screen import BaseScreen
from core.config_manager import config_manager
from core.utils import error_boundary


class ControllerConfigScreen(BaseScreen):
    """Interface for mapping Steam Deck controls to robot movements"""
    
    def _setup_screen(self):
        """Initialize controller configuration screen"""
        self.setFixedWidth(1180)
        self.mapping_rows = []
        self.load_motion_config()
        self.init_ui()
        self.load_config()

    @error_boundary
    def load_motion_config(self):
        """Load motion configuration for dropdowns"""
        config = config_manager.get_config("resources/configs/motion_config.json")
        self.groups = config.get("groups", {})
        self.emotions = config.get("emotions", [])
        self.movements = config.get("movements", {})
        
        # Load steam controls
        steam_controls, _ = config_manager.load_movement_controls()
        self.steam_controls = steam_controls

    @error_boundary
    def get_maestro_channel_by_name(self, name: str) -> str:
        """Get Maestro channel information by servo name"""
        config = config_manager.get_config("resources/configs/servo_config.json")
        for key, value in config.items():
            if value.get("name") == name:
                maestro = "Maestro 1" if key.startswith("m1") else "Maestro 2"
                channel = key.split("_ch")[1]
                return f"{maestro} / Ch {channel}"
        return "Unknown"

    def init_ui(self):
        """Initialize user interface"""
        self.layout = QVBoxLayout()
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.layout.setContentsMargins(100, 20, 15, 5)

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_widget.setLayout(self.grid_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.grid_widget)
        scroll.setStyleSheet("border: 1px solid #555; border-radius: 12px;")
        self.layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Mapping")
        add_btn.clicked.connect(self.add_mapping_row)
        save_btn = QPushButton("Save Config")
        save_btn.clicked.connect(self.save_config)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(save_btn)

        self.layout.addLayout(btn_layout)
        self.setLayout(self.layout)

    def add_mapping_row(self, control=None, control_type=None, movement=None, invert1=False, invert2=False):
        """Add a new control mapping row"""
        row = len(self.mapping_rows)

        control_cb = QComboBox()
        control_cb.addItems(self.steam_controls)
        if control:
            control_cb.setCurrentText(control)

        type_cb = QComboBox()
        type_cb.addItems(["control", "group_control", "track_control", "scene", "toggle"])
        if control_type:
            type_cb.setCurrentText(control_type)

        movement_cb = QComboBox()
        maestro1_label = QLabel("Maestro ? / Ch ?")
        maestro1_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        def update_movement_options():
            selected_type = type_cb.currentText()
            movement_cb.clear()
            if selected_type == "scene":
                movement_cb.addItems(self.emotions)
            elif selected_type == "group_control":
                movement_cb.addItems(list(self.groups.keys()))
            elif selected_type == "track_control":
                movement_cb.addItems([g for g in self.groups if "Track Control" in g])
            elif selected_type == "toggle":
                movement_cb.addItems([m for m in self.movements if "toggle" in m])
            else:
                movement_cb.addItems([m for m in self.movements])

        def update_maestro_label():
            selected_movement = movement_cb.currentText()
            maestro1_label.setText(self.get_maestro_channel_by_name(selected_movement))

        type_cb.currentTextChanged.connect(update_movement_options)
        movement_cb.currentTextChanged.connect(update_maestro_label)

        update_movement_options()
        if movement:
            movement_cb.setCurrentText(movement)
            update_maestro_label()

        invert_cb1 = QCheckBox("Invert")
        invert_cb1.setChecked(invert1)

        maestro2_label = QLabel("Maestro 2 / Ch ?")
        maestro2_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        maestro2_label.setVisible(control_type in ["group_control", "track_control"])

        invert_cb2 = QCheckBox("Invert")
        invert_cb2.setChecked(invert2)
        invert_cb2.setVisible(control_type in ["group_control", "track_control"])

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(lambda: self.remove_mapping_row(row))

        self.grid_layout.addWidget(control_cb, row, 0)
        self.grid_layout.addWidget(type_cb, row, 1)
        self.grid_layout.addWidget(movement_cb, row, 2)
        self.grid_layout.addWidget(maestro1_label, row, 3)
        self.grid_layout.addWidget(invert_cb1, row, 4)
        self.grid_layout.addWidget(maestro2_label, row, 5)
        self.grid_layout.addWidget(invert_cb2, row, 6)
        self.grid_layout.addWidget(remove_btn, row, 7)

        self.mapping_rows.append((control_cb, type_cb, movement_cb, maestro1_label, 
                                  invert_cb1, maestro2_label, invert_cb2, remove_btn))

    def remove_mapping_row(self, index: int):
        """Remove a control mapping row"""
        if index < len(self.mapping_rows) and self.mapping_rows[index]:
            for widget in self.mapping_rows[index]:
                widget.deleteLater()
            self.mapping_rows[index] = None

    @error_boundary
    def save_config(self):
        """Save controller configuration to file"""
        config = {}
        for row in self.mapping_rows:
            if row:
                (control_cb, type_cb, movement_cb, maestro1_label, 
                 invert_cb1, maestro2_label, invert_cb2, _) = row
                
                control = control_cb.currentText()
                control_type = type_cb.currentText()
                movement = movement_cb.currentText()
                invert1 = invert_cb1.isChecked()
                invert2 = invert_cb2.isChecked()

                if control_type == "control":
                    config[control] = {
                        "type": "control",
                        "movement": {
                            "name": movement,
                            "maestro": maestro1_label.text(),
                            "invert": invert1
                        }
                    }
                elif control_type == "group_control":
                    config[control] = {
                        "type": "group_control",
                        "group": movement,
                        "channels": [
                            {"maestro": maestro1_label.text(), "invert": invert1},
                            {"maestro": maestro2_label.text(), "invert": invert2}
                        ]
                    }
                elif control_type == "track_control":
                    config[control] = {
                        "type": "track_control",
                        "group": movement,
                        "tracks": {
                            "left": {"maestro": maestro1_label.text(), "invert": invert1},
                            "right": {"maestro": maestro2_label.text(), "invert": invert2}
                        }
                    }
                elif control_type == "scene":
                    config[control] = {
                        "type": "scene",
                        "emotion": movement
                    }
                elif control_type == "toggle":
                    config[control] = {
                        "type": "toggle",
                        "movement": {
                            "name": movement,
                            "maestro": maestro1_label.text(),
                            "invert": invert1
                        }
                    }

        success = config_manager.save_config("resources/configs/controller_config.json", config)
        if success:
            QMessageBox.information(self, "Saved", "Controller configuration saved successfully.")
            self.logger.info("Controller configuration saved")
        else:
            QMessageBox.critical(self, "Error", "Failed to save configuration.")
            self.logger.error("Failed to save controller configuration")

    @error_boundary
    def load_config(self):
        """Load existing controller configuration"""
        config = config_manager.get_config("resources/configs/controller_config.json")
        for control, settings in config.items():
            control_type = settings.get("type")
            movement = ""
            invert1 = False
            invert2 = False
            
            if control_type == "control":
                movement = settings["movement"]["name"]
                invert1 = settings["movement"]["invert"]
            elif control_type == "group_control":
                movement = settings["group"]
                invert1 = settings["channels"][0]["invert"]
                invert2 = settings["channels"][1]["invert"]
            elif control_type == "track_control":
                movement = settings["group"]
                invert1 = settings["tracks"]["left"]["invert"]
                invert2 = settings["tracks"]["right"]["invert"]
            elif control_type == "scene":
                movement = settings["emotion"]
            elif control_type == "toggle":
                movement = settings["movement"]["name"]
                invert1 = settings["movement"]["invert"]
                
            self.add_mapping_row(control, control_type, movement, invert1, invert2)