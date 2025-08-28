"""
WALL-E Control System - Home Screen
Main dashboard with emotion buttons and mode controls
"""

import os
from PyQt6.QtWidgets import (QHBoxLayout, QVBoxLayout, QLabel, QPushButton, 
                            QScrollArea, QWidget, QFrame, QGridLayout)
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtCore import Qt

from widgets.base_screen import BaseScreen
from core.config_manager import config_manager
from core.utils import error_boundary


class HomeScreen(BaseScreen):
    """Main dashboard screen with emotion controls and mode selection"""
    
    def _setup_screen(self):
        """Initialize the home screen interface"""
        layout = QHBoxLayout()
        layout.setContentsMargins(80, 20, 90, 5)

        # WALL-E image on the left
        self._create_image_section(layout)
        
        # Control panels on the right
        self._create_control_section(layout)
        
        self.setLayout(layout)
        self.load_emotion_buttons()

    def _create_image_section(self, parent_layout):
        """Create WALL-E image display section"""
        image_container = QVBoxLayout()
        image_container.addStretch()
        
        self.image_label = QLabel()
        image_path = "resources/images/walle.png"
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path).scaled(
                400, 400, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(pixmap)
        
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignBottom)
        image_container.addWidget(self.image_label)

        image_widget = QWidget()
        image_widget.setLayout(image_container)
        image_widget.setStyleSheet("background-color: rgba(0, 0, 0, 0);")
        parent_layout.addWidget(image_widget)

    def _create_control_section(self, parent_layout):
        """Create control panels section"""
        right_layout = QVBoxLayout()
        
        # Emotion buttons section
        self._create_emotion_buttons_section(right_layout)
        
        right_layout.addSpacing(5)
        
        # Mode control section
        self._create_mode_control_section(right_layout)
        
        parent_layout.addLayout(right_layout)

    def _create_emotion_buttons_section(self, parent_layout):
        """Create scrollable emotion buttons area"""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none; padding: 10px; background: transparent;")

        button_container = QWidget()
        button_container.setStyleSheet("background-color: #222; border-radius: 30px;")
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(10) 
        button_container.setLayout(self.grid_layout)

        # Wrap emotion buttons in a frame
        button_frame = QFrame()
        button_frame.setStyleSheet("QFrame { border: 1px solid #555; border-radius: 12px; background-color: #1e1e1e; }")
        frame_layout = QVBoxLayout(button_frame)
        frame_layout.setContentsMargins(10, 10, 10, 10)
        frame_layout.addWidget(button_container)
        scroll_area.setWidget(button_frame)

        parent_layout.addWidget(scroll_area)

    def _create_mode_control_section(self, parent_layout):
        """Create mode control buttons section"""
        mode_frame = QFrame()
        mode_frame.setStyleSheet("QFrame { border: 0px solid #555; border-radius: 12px; background-color: #1e1e1e; }")
        mode_layout = QHBoxLayout(mode_frame)
        mode_layout.setContentsMargins(10, 10, 10, 10)

        # Create mode buttons
        self.idle_button = QPushButton("Idle Mode")
        self.demo_button = QPushButton("Demo Mode")
        
        self.idle_button.toggled.connect(lambda checked: self.send_mode_state("idle", checked))
        self.demo_button.toggled.connect(lambda checked: self.send_mode_state("demo", checked))

        # Style mode buttons
        button_style = """
            QPushButton {
                background-color: #444;
                color: white;
                border-radius: 12px;
                padding: 10px;
            }
            QPushButton:checked {
                background-color: #888;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """
        
        for btn in [self.idle_button, self.demo_button]:
            btn.setCheckable(True)
            btn.setFont(QFont("Arial", 18))
            btn.setMinimumSize(120, 40)
            btn.setStyleSheet(button_style)
            mode_layout.addWidget(btn)

        # Add mode section to layout
        mode_container = QWidget()
        mode_container_layout = QHBoxLayout()
        mode_container_layout.addSpacing(20)
        mode_container_layout.addWidget(mode_frame)
        mode_container_layout.addSpacing(20)
        mode_container.setLayout(mode_container_layout)
        mode_container.setStyleSheet("background-color: rgba(0, 0, 0, 0);")

        parent_layout.addWidget(mode_container)

    @error_boundary
    def load_emotion_buttons(self):
        """Load emotion buttons from configuration"""
        # Clear existing buttons
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        
        config = config_manager.get_config("resources/configs/emotion_buttons.json")
        emotions = config if isinstance(config, list) else []

        font = QFont("Arial", 18)
        button_style = """
            QPushButton {
                background-color: #444;
                color: white;
                border-radius: 12px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """
        
        for idx, item in enumerate(emotions):
            label = item.get("label", "Unknown")
            emoji = item.get("emoji", "")
            
            btn = QPushButton(f"{emoji} {label}")
            btn.setFont(font)
            btn.setStyleSheet(button_style)
            btn.setMinimumSize(120, 40)
            btn.clicked.connect(lambda _, name=label: self.send_emotion(name))
            
            row = idx // 2
            col = idx % 2
            self.grid_layout.addWidget(btn, row, col)

    @error_boundary
    def send_emotion(self, name: str):
        """Send emotion command to backend"""
        success = self.send_websocket_message("scene", emotion=name)
        if success:
            self.logger.info(f"Sent emotion: {name}")

    @error_boundary
    def send_mode_state(self, mode: str, state: bool):
        """Send mode state change to backend"""
        success = self.send_websocket_message("mode", name=mode, state=state)
        if success:
            self.logger.info(f"Sent mode: {mode} = {state}")

    def reload_emotions(self):
        """Reload emotion buttons from configuration"""
        self.load_emotion_buttons()
        self.logger.info("Emotion buttons reloaded")