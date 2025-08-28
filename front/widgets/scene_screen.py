"""
WALL-E Control System - Scene Editor Screen
Interface for managing emotion scenes and audio mappings
"""

import json
from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, 
                            QScrollArea, QWidget, QCheckBox, QComboBox, QMessageBox)
from PyQt6.QtCore import Qt

from widgets.base_screen import BaseScreen
from core.config_manager import config_manager
from core.utils import error_boundary


class SceneScreen(BaseScreen):
    """Interface for managing emotion scenes and audio mappings"""
    
    def _setup_screen(self):
        """Initialize scene editor screen"""
        self.setFixedWidth(1180)
        self.scene_widgets = {}
        self.selected_labels = []
        self.categories = [
            "Happy", "Sad", "Curious", "Angry", "Surprise",
            "Love", "Calm", "Sound Effect", "Misc"
        ]
        
        self.init_ui()
        self.load_config()
        
        if self.websocket:
            self.websocket.textMessageReceived.connect(self.handle_message)
        
        self.request_scenes()

    def init_ui(self):
        """Initialize user interface"""
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(100, 20, 15, 5)

        # Scrollable grid for scenes
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_widget.setLayout(self.grid_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.grid_widget)
        scroll.setStyleSheet("border: 1px solid #555; border-radius: 12px;")
        self.layout.addWidget(scroll)

        # Control buttons
        btn_layout = QHBoxLayout()
        self.import_btn = QPushButton("Import Scenes")
        self.import_btn.clicked.connect(lambda: self.request_scenes())
        self.save_btn = QPushButton("Save Config")
        self.save_btn.clicked.connect(lambda: self.save_config())
        btn_layout.addWidget(self.import_btn)
        btn_layout.addWidget(self.save_btn)
        self.layout.addLayout(btn_layout)

        self.setLayout(self.layout)

    @error_boundary
    def request_scenes(self):
        """Request available scenes from backend"""
        success = self.send_websocket_message("get_scenes")
        if success:
            self.logger.info("Requested scenes from backend")
        else:
            self.logger.warning("Failed to request scenes - WebSocket not connected")

    @error_boundary
    def handle_message(self, message: str):
        """Handle incoming WebSocket messages"""
        try:
            msg = json.loads(message)
            if msg.get("type") == "scene_list":
                self.update_grid(msg.get("scenes", []))
        except Exception as e:
            self.logger.error(f"Failed to handle message: {e}")

    @error_boundary
    def update_grid(self, scenes: list):
        """Update the scene grid with available scenes"""
        # Clear existing widgets
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        self.scene_widgets.clear()

        for idx, scene in enumerate(scenes):
            label = scene.get("label", "")
            emoji = scene.get("emoji", "")
            
            # Checkbox for selection
            checkbox = QCheckBox()
            checkbox.setChecked(label in self.selected_labels)

            # Scene name display
            name_label = QLabel(f"{emoji} {label}")
            name_label.setStyleSheet("font-size: 20px;")

            # Category selection
            category_cb = QComboBox()
            category_cb.addItems(self.categories)
            category_cb.setStyleSheet("font-size: 16px;")
            category_cb.setFixedWidth(150)

            # Test button
            test_btn = QPushButton("Test")
            test_btn.setStyleSheet("font-size: 16px;")
            test_btn.clicked.connect(lambda _, name=label: self.test_scene(name))

            # Layout in grid (2 columns)
            row = idx // 2
            col = (idx % 2) * 4
            self.grid_layout.addWidget(checkbox, row, col)
            self.grid_layout.addWidget(name_label, row, col + 1)
            self.grid_layout.addWidget(category_cb, row, col + 2)
            self.grid_layout.addWidget(test_btn, row, col + 3)

            # Store widget references
            self.scene_widgets[label] = (checkbox, emoji, category_cb)

    @error_boundary
    def test_scene(self, name: str):
        """Test a scene by sending it to the backend"""
        success = self.send_websocket_message("scene", emotion=name)
        if success:
            self.logger.info(f"Testing scene: {name}")
        else:
            self.logger.warning(f"Failed to test scene: {name}")

    @error_boundary
    def save_config(self):
        """Save selected scenes configuration"""
        selected = [
            {"label": label, "emoji": emoji, "category": cb.currentText()}
            for label, (cbx, emoji, cb) in self.scene_widgets.items()
            if cbx.isChecked()
        ]
        
        success = config_manager.save_config("resources/configs/emotion_buttons.json", selected)
        
        if success:
            QMessageBox.information(self, "Saved", "Emotion buttons saved successfully.")
            self.load_config()
            self.logger.info("Scene configuration saved")

            # Reload HomeScreen emotion buttons
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                for widget in app.allWidgets():
                    # Import here to avoid circular imports
                    from widgets.home_screen import HomeScreen
                    if isinstance(widget, HomeScreen):
                        widget.reload_emotions()
        else:
            QMessageBox.critical(self, "Error", "Failed to save configuration.")
            self.logger.error("Failed to save scene configuration")

    @error_boundary
    def load_config(self):
        """Load existing scene configuration"""
        config = config_manager.get_config("resources/configs/emotion_buttons.json")
        emotions = config if isinstance(config, list) else []
        self.selected_labels = [item.get("label", "") for item in emotions]
        self.logger.debug(f"Loaded {len(self.selected_labels)} selected scenes")