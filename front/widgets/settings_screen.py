"""
WALL-E Control System - Settings Screen (Compact Scrollable Layout)
Configuration interface for system settings with better space utilization
"""

from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
                            QLineEdit, QSpinBox, QSlider, QPushButton, 
                            QComboBox, QMessageBox, QDoubleSpinBox, QSizePolicy,
                            QGroupBox, QFrame, QScrollArea, QTabWidget, QWidget)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

from widgets.base_screen import BaseScreen
from core.config_manager import config_manager
from core.utils import error_boundary


class SettingsScreen(BaseScreen):
    """Configuration interface for system settings"""
    
    def _setup_screen(self):
        """Initialize settings interface"""
        self.setFixedWidth(1180)
        self.config_path = "resources/configs/steamdeck_config.json"
        
        # Create main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(90, 10, 20, 10)
        main_layout.setSpacing(10)
        
        # Create scroll area for content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background: #2d2d2d;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #FFB000;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #FFC000;
            }
        """)
        
        # Create content widget
        content_widget = QWidget()
        self.layout = QVBoxLayout(content_widget)
        self.layout.setContentsMargins(20, 10, 20, 10)
        self.layout.setSpacing(10)
        
        self._create_compact_settings()
        self._create_control_buttons()
        
        # Set up scroll area
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)
        
        self.setLayout(main_layout)
        self.load_config()

    def _create_compact_settings(self):
        """Create compact settings layout"""
        
        # Network Configuration Section
        network_group = self._create_section("Network Configuration")
        network_layout = QGridLayout()
        network_layout.setSpacing(0)
        network_layout.setContentsMargins(15, 0, 15, 10)
        
        font = QFont("Arial", 16)
        
        # Network settings in compact grid
        labels_texts = [
            ("ESP32 Camera:", "esp32_url", "http://192.168.1.100:81/stream"),
            ("Camera Proxy:", "proxy_url", "http://10.1.1.230:8081/stream"),
            ("Control WebSocket:", "control_ws", "ws://10.1.1.230:8766")
        ]
        
        self.network_inputs = {}
        for i, (label_text, key, placeholder) in enumerate(labels_texts):
            label = QLabel(label_text)
            label.setFont(font)
            label.setMinimumWidth(120)
            
            input_field = QLineEdit()
            input_field.setFont(font)
            input_field.setFixedHeight(30)
            input_field.setPlaceholderText(placeholder)
            self.network_inputs[key] = input_field
            
            network_layout.addWidget(label, i, 0)
            network_layout.addWidget(input_field, i, 1, 1, 3)
        
        network_group.setLayout(network_layout)
        self.layout.addWidget(network_group)
        
        # Logging Section (simplified)
        logging_group = self._create_section("Logging Configuration")
        logging_layout = QGridLayout()
        logging_layout.setSpacing(10)
        logging_layout.setContentsMargins(15, 0, 15, 10)
        
        # Debug levels in 2x2 grid
        debug_configs = [
            ("Global Debug:", "debug_combo"),
            ("Camera Debug:", "camera_debug_combo"),
            ("Servo Debug:", "servo_debug_combo"),
            ("Network Debug:", "network_debug_combo")
        ]
        
        self.debug_combos = {}
        for i, (label_text, key) in enumerate(debug_configs):
            row = i // 2
            col_offset = (i % 2) * 2
            
            label = QLabel(label_text)
            label.setFont(font)
            combo = QComboBox()
            combo.setFont(font)
            combo.addItems(["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"])
            combo.setFixedHeight(30)
            combo.setMaximumWidth(100)
            self.debug_combos[key] = combo
            
            logging_layout.addWidget(label, row, col_offset)
            logging_layout.addWidget(combo, row, col_offset + 1)
        
        logging_group.setLayout(logging_layout)
        self.layout.addWidget(logging_group)
        
        # Wave Detection Section
        wave_group = self._create_section("Wave Detection")
        wave_layout = QGridLayout()
        wave_layout.setSpacing(10)
        wave_layout.setContentsMargins(15, 0, 15, 10)
        
        # Row 0: Sample Duration and Rate
        wave_layout.addWidget(QLabel("Sample Duration:"), 0, 0)
        self.sample_duration_spin = QSpinBox()
        self.sample_duration_spin.setFont(font)
        self.sample_duration_spin.setRange(1, 10)
        self.sample_duration_spin.setValue(3)
        self.sample_duration_spin.setFixedHeight(30)
        self.sample_duration_spin.setMaximumWidth(60)
        wave_layout.addWidget(self.sample_duration_spin, 0, 1)
        
        wave_layout.addWidget(QLabel("Sample Rate:"), 0, 2)
        self.sample_rate_spin = QSpinBox()
        self.sample_rate_spin.setFont(font)
        self.sample_rate_spin.setRange(1, 60)
        self.sample_rate_spin.setValue(5)
        self.sample_rate_spin.setFixedHeight(30)
        self.sample_rate_spin.setMaximumWidth(60)
        wave_layout.addWidget(self.sample_rate_spin, 0, 3)
        
        # Row 1: Confidence and Stand Down
        wave_layout.addWidget(QLabel("Confidence:"), 1, 0)
        
        confidence_layout = QHBoxLayout()
        self.confidence_slider = QSlider(Qt.Orientation.Horizontal)
        self.confidence_slider.setRange(0, 100)
        self.confidence_slider.setValue(70)
        self.confidence_slider.setMaximumWidth(120)
        self.confidence_slider.setFixedHeight(30)
        
        self.confidence_value = QLabel("70%")
        self.confidence_value.setFont(font)
        self.confidence_value.setMinimumWidth(40)
        
        self.confidence_slider.valueChanged.connect(
            lambda val: self.confidence_value.setText(f"{val}%")
        )
        
        confidence_layout.addWidget(self.confidence_slider)
        confidence_layout.addWidget(self.confidence_value)
        wave_layout.addLayout(confidence_layout, 1, 1)
        
        wave_layout.addWidget(QLabel("Stand Down:"), 1, 2)
        self.stand_down_spin = QSpinBox()
        self.stand_down_spin.setFont(font)
        self.stand_down_spin.setRange(0, 300)
        self.stand_down_spin.setValue(30)
        self.stand_down_spin.setFixedHeight(30)
        self.stand_down_spin.setMaximumWidth(80)
        wave_layout.addWidget(self.stand_down_spin, 1, 3)
        
        wave_group.setLayout(wave_layout)
        self.layout.addWidget(wave_group)

    def _create_section(self, title: str) -> QGroupBox:
        """Create a compact section group box"""
        group = QGroupBox(title)
        group.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #e1a014;
                border-radius: 6px;
                margin-top: 18px;
                padding-top: 12px;
                color: #e1a014;
                background-color: rgba(0, 0, 0, 0.3);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
                top: 5px;
                border-radius: 6px;
                background-color: rgba(0, 0, 0, 0.9);
            }
        """)
        return group

    def _create_control_buttons(self):
        """Create save and reset buttons"""
        font = QFont("Arial", 20, QFont.Weight.Bold)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        
        self.save_btn = QPushButton("💾 Save Settings")
        self.save_btn.setFont(font)
        self.save_btn.clicked.connect(lambda: self.save_config())
        self.save_btn.setFixedHeight(45)
        self.save_btn.setMinimumWidth(140)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        
        self.reset_btn = QPushButton("🔄 Reset")
        self.reset_btn.setFont(font)
        self.reset_btn.clicked.connect(lambda: self.reset_to_defaults())
        self.reset_btn.setFixedHeight(45)
        self.reset_btn.setMinimumWidth(120)
        self.reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:pressed {
                background-color: #c41e3a;
            }
        """)
        
        self.test_connection_btn = QPushButton("🔗 Test")
        self.test_connection_btn.setFont(font)
        self.test_connection_btn.clicked.connect(lambda: self.test_websocket_connection())
        self.test_connection_btn.setFixedHeight(45)
        self.test_connection_btn.setMinimumWidth(100)
        self.test_connection_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #1565C0;
            }
        """)
        
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.reset_btn)
        btn_layout.addWidget(self.test_connection_btn)
        btn_layout.addStretch()
        
        self.layout.addSpacing(15)
        self.layout.addLayout(btn_layout)

    @error_boundary
    def load_config(self):
        """Load current configuration settings"""
        config = config_manager.get_config(self.config_path)
        current = config.get("current", {})
        wave = current.get("wave_detection", {})
        module_debug = current.get("module_debug", {})
        
        # Network settings
        self.network_inputs["esp32_url"].setText(current.get("esp32_cam_url", ""))
        self.network_inputs["proxy_url"].setText(current.get("camera_proxy_url", ""))
        self.network_inputs["control_ws"].setText(current.get("control_websocket_url", "localhost:8766"))
        
        # Logging settings
        self.debug_combos["debug_combo"].setCurrentText(current.get("debug_level", "INFO"))
        self.debug_combos["camera_debug_combo"].setCurrentText(module_debug.get("camera", "INFO"))
        self.debug_combos["servo_debug_combo"].setCurrentText(module_debug.get("servo", "INFO"))
        self.debug_combos["network_debug_combo"].setCurrentText(module_debug.get("network", "INFO"))
        
        # Wave detection settings
        self.sample_duration_spin.setValue(wave.get("sample_duration", 3))
        self.sample_rate_spin.setValue(wave.get("sample_rate", 5))
        confidence_percent = int(wave.get("confidence_threshold", 0.7) * 100)
        self.confidence_slider.setValue(confidence_percent)
        self.confidence_value.setText(f"{confidence_percent}%")
        self.stand_down_spin.setValue(wave.get("stand_down_time", 30))

    @error_boundary
    def save_config(self):
        """Save configuration changes"""
        # Validate inputs
        if not self._validate_inputs():
            return
        
        # Get current config structure
        try:
            current_config = config_manager.get_config(self.config_path)
        except:
            current_config = {}
        
        # Build new configuration
        new_config = {
            "current": {
                "esp32_cam_url": self.network_inputs["esp32_url"].text().strip(),
                "camera_proxy_url": self.network_inputs["proxy_url"].text().strip(),
                "control_websocket_url": self.network_inputs["control_ws"].text().strip(),
                "debug_level": self.debug_combos["debug_combo"].currentText(),
                "module_debug": {
                    "camera": self.debug_combos["camera_debug_combo"].currentText(),
                    "servo": self.debug_combos["servo_debug_combo"].currentText(),
                    "network": self.debug_combos["network_debug_combo"].currentText(),
                    "websocket": "WARNING",
                    "telemetry": "INFO",
                    "ui": "INFO", 
                    "config": "WARNING",
                    "main": "INFO",
                    "controller": "INFO",
                    "error": "ERROR"
                },
                "wave_detection": {
                    "sample_duration": self.sample_duration_spin.value(),
                    "sample_rate": self.sample_rate_spin.value(),
                    "confidence_threshold": self.confidence_slider.value() / 100.0,
                    "stand_down_time": self.stand_down_spin.value()
                }
            },
            "defaults": current_config.get("defaults", {})
        }

        # Save configuration
        success = config_manager.save_config(self.config_path, new_config)
        
        if success:
            # Send camera URL update to backend if WebSocket is available
            if self.websocket:
                self.send_websocket_message(
                    "update_camera_config",
                    esp32_url=self.network_inputs["esp32_url"].text().strip()
                )
            
            QMessageBox.information(
                self, 
                "Settings Saved", 
                "Configuration updated successfully.\n\n"
                "Note: Network monitoring and debug level changes require application restart to take full effect."
            )
            self.logger.info("Configuration updated successfully")
            
            # Notify other components about config changes
            self._notify_config_changes()
            
        else:
            QMessageBox.critical(
                self, 
                "Save Failed", 
                "Failed to save configuration.\n\n"
                "Please check file permissions and try again."
            )
            self.logger.error("Failed to save configuration")

    @error_boundary
    def reset_to_defaults(self):
        """Reset configuration to default values"""
        reply = QMessageBox.question(
            self, 
            "Reset to Defaults", 
            "Are you sure you want to reset all settings to default values?\n\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            config = config_manager.get_config(self.config_path)
            defaults = config.get("defaults", {})
            
            if defaults:
                # Update current config with defaults
                config["current"] = defaults.copy()
                success = config_manager.save_config(self.config_path, config)
                
                if success:
                    self.load_config()  # Reload UI with default values
                    QMessageBox.information(
                        self, 
                        "Reset Complete", 
                        "Configuration has been reset to defaults."
                    )
                    self.logger.info("Configuration reset to defaults")
                else:
                    QMessageBox.critical(
                        self, 
                        "Reset Failed", 
                        "Failed to reset configuration."
                    )
            else:
                # Create sensible defaults if none exist
                self._create_default_config()
                QMessageBox.information(
                    self, 
                    "Defaults Created", 
                    "Default configuration has been created and applied."
                )

    @error_boundary
    def test_websocket_connection(self):
        """Test WebSocket connection with current settings"""
        url = self.network_inputs["control_ws"].text().strip()
        if not url:
            QMessageBox.warning(
                self,
                "Invalid URL",
                "Please enter a WebSocket URL before testing."
            )
            return
        
        # Temporarily create WebSocket to test connection
        try:
            from core.websocket_manager import WebSocketManager
            
            # Show progress
            test_msg = QMessageBox(self)
            test_msg.setWindowTitle("Testing Connection")
            test_msg.setText("Testing WebSocket connection...")
            test_msg.setStandardButtons(QMessageBox.StandardButton.NoButton)
            test_msg.show()
            
            # Test connection (simplified)
            if url.startswith("ws://") or url.startswith("wss://"):
                test_url = url
            else:
                test_url = f"ws://{url}"
            
            # For now, just validate URL format
            from urllib.parse import urlparse
            parsed = urlparse(test_url)
            
            test_msg.close()
            
            if parsed.scheme in ['ws', 'wss'] and parsed.netloc:
                QMessageBox.information(
                    self,
                    "Connection Test",
                    f"WebSocket URL format is valid: {test_url}\n\n"
                    "Note: Actual connectivity will be tested when you save settings."
                )
            else:
                QMessageBox.warning(
                    self,
                    "Invalid URL",
                    f"WebSocket URL format is invalid: {test_url}"
                )
                
        except Exception as e:
            QMessageBox.critical(
                self,
                "Test Failed",
                f"Connection test failed: {str(e)}"
            )
            self.logger.error(f"WebSocket connection test failed: {e}")

    def _validate_inputs(self) -> bool:
        """Validate all input fields"""
        errors = []
        
        # Validate URLs
        esp32_url = self.network_inputs["esp32_url"].text().strip()
        proxy_url = self.network_inputs["proxy_url"].text().strip()
        ws_url = self.network_inputs["control_ws"].text().strip()
        
        if esp32_url and not (esp32_url.startswith("http://") or esp32_url.startswith("https://")):
            errors.append("ESP32 URL must start with http:// or https://")
        
        if proxy_url and not (proxy_url.startswith("http://") or proxy_url.startswith("https://")):
            errors.append("Camera Proxy URL must start with http:// or https://")
        
        if not ws_url:
            errors.append("WebSocket URL is required")
        
        # Validate wave detection settings
        if self.sample_duration_spin.value() < 1:
            errors.append("Sample duration must be at least 1 second")
        
        if self.sample_rate_spin.value() < 1:
            errors.append("Sample rate must be at least 1 Hz")
        
        if errors:
            QMessageBox.warning(
                self,
                "Invalid Settings",
                "Please correct the following errors:\n\n" + "\n".join(f"• {error}" for error in errors)
            )
            return False
        
        return True

    def _create_default_config(self):
        """Create default configuration if none exists"""
        default_config = {
            "current": {
                "esp32_cam_url": "http://esp32.local:81/stream",
                "camera_proxy_url": "http://10.1.1.230:8081/stream",
                "control_websocket_url": "localhost:8766",
                "debug_level": "INFO",
                "module_debug": {
                    "camera": "INFO",
                    "servo": "INFO",
                    "network": "INFO",
                    "websocket": "WARNING",
                    "telemetry": "INFO",
                    "ui": "INFO",
                    "config": "WARNING",
                    "main": "INFO",
                    "controller": "INFO",
                    "error": "ERROR"
                },
                "network_monitoring": {
                    "update_interval": 5.0,
                    "ping_samples": 3
                },
                "wave_detection": {
                    "sample_duration": 3,
                    "sample_rate": 5,
                    "confidence_threshold": 0.7,
                    "stand_down_time": 30
                }
            }
        }
        
        # Copy current as defaults
        default_config["defaults"] = default_config["current"].copy()
        
        # Save and reload
        config_manager.save_config(self.config_path, default_config)
        self.load_config()

    def _notify_config_changes(self):
        """Notify other components about configuration changes"""
        # Find other components that need to reload settings
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                for widget in app.allWidgets():
                    # Notify camera screen about wave detection changes
                    if hasattr(widget, "reload_wave_settings"):
                        widget.reload_wave_settings()
                    # Notify camera screen about URL changes
                    elif hasattr(widget, "reload_camera_settings"):
                        widget.reload_camera_settings()
                    # Notify network monitors about config changes
                    elif hasattr(widget, "reload_network_settings"):
                        widget.reload_network_settings()
        except Exception as e:
            self.logger.warning(f"Failed to notify components of config changes: {e}")

    def get_current_config(self) -> dict:
        """Get current configuration values from UI"""
        return {
            "esp32_cam_url": self.network_inputs["esp32_url"].text().strip(),
            "camera_proxy_url": self.network_inputs["proxy_url"].text().strip(),
            "control_websocket_url": self.network_inputs["control_ws"].text().strip(),
            "debug_level": self.debug_combos["debug_combo"].currentText(),
            "module_debug": {
                "camera": self.debug_combos["camera_debug_combo"].currentText(),
                "servo": self.debug_combos["servo_debug_combo"].currentText(),
                "network": self.debug_combos["network_debug_combo"].currentText(),
            },
            "wave_detection": {
                "sample_duration": self.sample_duration_spin.value(),
                "sample_rate": self.sample_rate_spin.value(),
                "confidence_threshold": self.confidence_slider.value() / 100.0,
                "stand_down_time": self.stand_down_spin.value()
            }
        }

    def apply_theme(self, theme_name: str):
        """Apply visual theme to settings screen"""
        if theme_name == "dark":
            self.setStyleSheet("""
                QWidget {
                    background-color: #1e1e1e;
                    color: white;
                }
                QLabel {
                    color: white;
                }
                QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                    background-color: #2d2d2d;
                    border: 1px solid #555;
                    border-radius: 4px;
                    padding: 6px;
                    color: white;
                }
                QSlider::groove:horizontal {
                    border: 1px solid #555;
                    height: 6px;
                    background: #2d2d2d;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background: #FFB000;
                    border: 1px solid #FFB000;
                    width: 16px;
                    margin: -5px 0;
                    border-radius: 8px;
                }
            """)
        # Additional themes can be added here