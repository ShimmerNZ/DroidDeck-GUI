"""
Settings Screen (Themed) - Part 1
- Class definition, initialization, and UI setup methods
- Theme integration and styling methods
"""

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QLineEdit, QSpinBox, QSlider, QPushButton,
    QComboBox, QMessageBox, QGroupBox, QFrame, QScrollArea, QWidget
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

from widgets.base_screen import BaseScreen
from core.config_manager import config_manager
from core.theme_manager import theme_manager
from core.utils import error_boundary


class SettingsScreen(BaseScreen):
    """Configuration interface for system settings with theme manager integration"""

    # ---------- Lifecycle ----------

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Register for theme change notifications
        theme_manager.register_callback(self._on_theme_changed)

    def __del__(self):
        """Clean up theme manager callback on destruction"""
        try:
            theme_manager.unregister_callback(self._on_theme_changed)
        except Exception:
            pass  # Ignore errors during cleanup

    # ---------- UI Build ----------

    def _setup_screen(self):
        """Initialize settings interface"""
        self.config_path = "resources/configs/steamdeck_config.json"

        # Root layout (similar outer margins to Home screen)
        root = QVBoxLayout()
        root.setContentsMargins(100, 20, 90, 10)
        root.setSpacing(8)

        # Main themed frame (like Home right panel)
        self.main_frame = QFrame()
        self._update_main_frame_style()

        main = QVBoxLayout(self.main_frame)
        main.setContentsMargins(0, 10, 0, 10)
        main.setSpacing(10)

        # Add header
        self.header = QLabel("Settings Configuration")
        self.header.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_header_style()
        main.addWidget(self.header)

        # Theme selector (top row)
        self._create_theme_selector(main)

        # Scrollable content area (to fit lots of options neatly)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._update_scroll_area_style()

        content_widget = QWidget()
        content_layout = QGridLayout(content_widget)
        content_layout.setContentsMargins(8, 0, 8, 0)
        content_layout.setHorizontalSpacing(12)
        content_layout.setVerticalSpacing(10)

        # Sections
        self.network_group = self._create_section("Network Configuration")
        self._build_network(self.network_group)

        self.logging_group = self._create_section("Logging Configuration")
        self._build_logging(self.logging_group)

        self.wave_group = self._create_section("Wave Detection")
        self._build_wave(self.wave_group)

        # Two-column placement to use width
        content_layout.addWidget(self.network_group, 0, 0, 2, 1)  # row, col, rowspan, colspan
        content_layout.addWidget(self.logging_group, 0, 1)
        content_layout.addWidget(self.wave_group,    1, 1)
        # Buttons row (full width)
        content_layout.setRowStretch(1, 1)
        self.buttons_row = self._create_control_buttons()
        content_layout.addLayout(self.buttons_row, 2, 0, 1, 2)

        self.scroll_area.setWidget(content_widget)
        main.addWidget(self.scroll_area)

        # Assemble
        root.addWidget(self.main_frame)
        self.setLayout(root)

        # Load config on open
        self.load_config()

    # ---------- Themed header & frame ----------

    def _update_main_frame_style(self):
        """Apply themed frame style (similar to Home right frame)"""
        primary_color = theme_manager.get("primary_color")
        panel_bg = theme_manager.get("panel_bg")
        self.main_frame.setStyleSheet(f"""
        QFrame {{
            background-color: {panel_bg};
            border: 2px solid {primary_color};
            border-radius: 12px;
            padding: 6px 12px 12px 12px;
        }}
        """)

    def _update_header_style(self):
        """Apply themed header style"""
        primary = theme_manager.get("primary_color")
        self.header.setStyleSheet(f"""
            QLabel {{
                color: {primary};
                padding-bottom: 8px;
                font-weight: bold;
                border: none;
                background: transparent;
            }}
        """)

    def _update_scroll_area_style(self):
        """Themed scroll bars"""
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        self.scroll_area.setStyleSheet(f"""
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

    # ---------- Theme selector ----------

    def _create_theme_selector(self, parent_layout: QVBoxLayout):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(20, 0, 10, 0)

        label = QLabel("Theme:")
        label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        self._update_label_style(label)
        row.addWidget(label)

        self.theme_buttons = {}  # Use dict for easier lookup
        
        # Use available themes reported by ThemeManager
        theme_names = theme_manager.available_themes()
        current_theme = theme_manager.get_theme_name()

        for name in theme_names:
            display_name = "WALL-E" if name == "Wall-e" else name
            btn = QPushButton(display_name)
            btn.setCheckable(True)
            btn.setFont(QFont("Arial", 16, QFont.Weight.Bold))
            btn.setMinimumSize(120, 36)
            
            # Set initial state based on current theme
            is_current = (name == current_theme)
            btn.setChecked(is_current)
            
            # Connect with theme name, not display name
            btn.clicked.connect(lambda checked, theme_name=name: self._on_theme_selected(theme_name))
            
            self.theme_buttons[name] = btn
            row.addWidget(btn)

        # Apply initial styling
        self._update_theme_button_styles()

        row.addStretch()
        parent_layout.addLayout(row)

    def _update_theme_button_styles(self):
        """Update all theme button styles based on current selection"""
        current_theme = theme_manager.get_theme_name()
        for theme_name, btn in self.theme_buttons.items():
            is_selected = (theme_name == current_theme)
            btn.setChecked(is_selected)
            btn.setStyleSheet(theme_manager.get_button_style("primary", checked=is_selected))

    def _on_theme_selected(self, theme_name: str):
        """Handle theme selection"""
        # Only proceed if this is actually a different theme
        if theme_name == theme_manager.get_theme_name():
            return
            
        # Update the theme
        success = theme_manager.set_theme(theme_name)
        if success:
            # Update button states - this will be handled by the theme change callback
            self.logger.info(f"Theme changed to: {theme_name}")
        else:
            # Revert button state if theme change failed
            self._update_theme_button_styles()
            self.logger.error(f"Failed to change theme to: {theme_name}")

    # ---------- Sections ----------

    def _create_section(self, title: str) -> QGroupBox:
        group = QGroupBox(title)
        group.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self._update_section_style(group)
        return group

    def _update_section_style(self, group: QGroupBox):
        primary = theme_manager.get("primary_color")
        panel_bg = theme_manager.get("panel_bg")
        group.setStyleSheet(f"""
        QGroupBox {{
            font-weight: bold;
            border: 2px solid {primary};
            border-radius: 6px;
            margin-top: 18px;
            padding-top: 12px;
            color: {primary};
            background-color: rgba(0, 0, 0, 0.3);
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 15px;
            padding: 0 8px 0 8px;
            top: 5px;
            border-radius: 6px;
            background-color: {panel_bg};
            color: {primary};
        }}
        """)

    def _build_network(self, group: QGroupBox):
        layout = QGridLayout()
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(6)

        font = QFont("Arial", 16)
        labels = [
            ("ESP32 Camera:", "esp32_url", "http://192.168.1.100:81/stream"),
            ("Camera Proxy:", "proxy_url", "http://10.1.1.230:8081/stream"),
            ("Control WebSocket:", "control_ws", "ws://10.1.1.230:8766"),
        ]
        self.network_inputs = {}

        for i, (text, key, placeholder) in enumerate(labels):
            lab = QLabel(text)
            lab.setFont(font)
            lab.setMinimumWidth(140)
            self._update_label_style(lab)

            edit = QLineEdit()
            edit.setFont(font)
            edit.setFixedHeight(30)
            edit.setMinimumWidth(230)
            edit.setPlaceholderText(placeholder)
            self._update_input_style(edit)

            self.network_inputs[key] = edit
            layout.addWidget(lab, i, 0)
            layout.addWidget(edit, i, 1, 1, 3)

        group.setLayout(layout)

    def _build_logging(self, group: QGroupBox):
        layout = QGridLayout()
        layout.setContentsMargins(10, 0, 10, 10)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        font = QFont("Arial", 16)

        items = [
            ("Global Debug:", "debug_combo"),
            ("Camera Debug:", "camera_debug_combo"),
            ("Servo Debug:", "servo_debug_combo"),
            ("Network Debug:", "network_debug_combo"),
        ]
        self.debug_combos = {}

        for i, (label_text, key) in enumerate(items):
            row = i // 2
            col = (i % 2) * 2
            lab = QLabel(label_text)
            lab.setFont(font)
            self._update_label_style(lab)

            combo = QComboBox()
            combo.setFont(font)
            combo.addItems(["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"])
            combo.setFixedHeight(30)
            combo.setFixedWidth(120)
            self._update_combo_style(combo)

            self.debug_combos[key] = combo
            layout.addWidget(lab, row, col)
            layout.addWidget(combo, row, col + 1)

        group.setLayout(layout)

    def _build_wave(self, group: QGroupBox):
        layout = QGridLayout()
        layout.setContentsMargins(10, 0, 10, 10)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        font = QFont("Arial", 16)

        # Row 0: Sample Duration / Sample Rate
        dur_lab = QLabel("Sample Duration:")
        self._update_label_style(dur_lab)
        layout.addWidget(dur_lab, 0, 0)

        self.sample_duration_spin = QSpinBox()
        self.sample_duration_spin.setFont(font)
        self.sample_duration_spin.setRange(1, 10)
        self.sample_duration_spin.setValue(3)
        self.sample_duration_spin.setFixedHeight(30)
        self.sample_duration_spin.setMaximumWidth(70)
        self._update_spinbox_style(self.sample_duration_spin)
        layout.addWidget(self.sample_duration_spin, 0, 1)

        rate_lab = QLabel("Sample Rate:")
        self._update_label_style(rate_lab)
        layout.addWidget(rate_lab, 0, 2)

        self.sample_rate_spin = QSpinBox()
        self.sample_rate_spin.setFont(font)
        self.sample_rate_spin.setRange(1, 60)
        self.sample_rate_spin.setValue(5)
        self.sample_rate_spin.setFixedHeight(30)
        self.sample_rate_spin.setMaximumWidth(70)
        self._update_spinbox_style(self.sample_rate_spin)
        layout.addWidget(self.sample_rate_spin, 0, 3)

        # Row 1: Confidence / Stand down
        conf_lab = QLabel("Confidence:")
        self._update_label_style(conf_lab)
        layout.addWidget(conf_lab, 1, 0)

        conf_row = QHBoxLayout()
        self.confidence_slider = QSlider(Qt.Orientation.Horizontal)
        self.confidence_slider.setRange(0, 100)
        self.confidence_slider.setValue(70)
        self.confidence_slider.setMaximumWidth(140)
        self.confidence_slider.setFixedHeight(30)
        self._update_slider_style(self.confidence_slider)

        self.confidence_value = QLabel("70%")
        self.confidence_value.setFont(font)
        self.confidence_value.setMinimumWidth(48)
        self._update_value_label_style(self.confidence_value)

        self.confidence_slider.valueChanged.connect(
            lambda v: self.confidence_value.setText(f"{v}%")
        )

        conf_row.addWidget(self.confidence_slider)
        conf_row.addWidget(self.confidence_value)
        layout.addLayout(conf_row, 1, 1)

        sd_lab = QLabel("Stand Down:")
        self._update_label_style(sd_lab)
        layout.addWidget(sd_lab, 1, 2)

        self.stand_down_spin = QSpinBox()
        self.stand_down_spin.setFont(font)
        self.stand_down_spin.setRange(0, 300)
        self.stand_down_spin.setValue(30)
        self.stand_down_spin.setFixedHeight(30)
        self.stand_down_spin.setMaximumWidth(90)
        self._update_spinbox_style(self.stand_down_spin)
        layout.addWidget(self.stand_down_spin, 1, 3)

        group.setLayout(layout)

    # ---------- Buttons row ----------

    def _create_control_buttons(self) -> QHBoxLayout:
        font = QFont("Arial", 20, QFont.Weight.Bold)
        row = QHBoxLayout()
        row.setSpacing(12)

        self.save_btn = QPushButton("💾 Save Settings")
        self.save_btn.setFont(font)
        self.save_btn.clicked.connect(self.save_config)
        self.save_btn.setFixedHeight(45)
        self.save_btn.setMinimumWidth(160)
        self._update_save_button_style()

        self.reset_btn = QPushButton("🔄 Reset")
        self.reset_btn.setFont(font)
        self.reset_btn.clicked.connect(self.reset_to_defaults)
        self.reset_btn.setFixedHeight(45)
        self.reset_btn.setMinimumWidth(120)
        self._update_reset_button_style()

        self.test_connection_btn = QPushButton("🔗 Test")
        self.test_connection_btn.setFont(font)
        self.test_connection_btn.clicked.connect(self.test_websocket_connection)
        self.test_connection_btn.setFixedHeight(45)
        self.test_connection_btn.setMinimumWidth(110)
        self._update_test_button_style()

        row.addWidget(self.save_btn)
        row.addWidget(self.reset_btn)
        row.addWidget(self.test_connection_btn)
        row.addStretch()
        return row

    def _update_save_button_style(self):
        green = theme_manager.get("green")
        green_gradient = theme_manager.get("green_gradient")
        self.save_btn.setStyleSheet(f"""
        QPushButton {{
            background: {green_gradient};
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: bold;
        }}
        QPushButton:hover {{ 
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #55cc55, stop:1 #339933);
        }}
        QPushButton:pressed {{ 
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #339933, stop:1 #226622);
        }}
        """)

    def _update_reset_button_style(self):
        red = theme_manager.get("red")
        self.reset_btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {red};
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: #da190b; }}
        QPushButton:pressed {{ background-color: #c41e3a; }}
        """)

    def _update_test_button_style(self):
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        self.test_connection_btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {primary};
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: {primary_light}; }}
        QPushButton:pressed {{ 
            background-color: {primary};
        }}
        """)

    # ---------- Widget styling helpers ----------

    def _update_label_style(self, label: QLabel):
        label.setStyleSheet("color: white; background: transparent;")

    def _update_input_style(self, input_field: QLineEdit):
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

    def _update_combo_style(self, combo: QComboBox):
        primary = theme_manager.get("primary_color")
        combo.setStyleSheet(f"""
        QComboBox {{
            background-color: #2d2d2d;
            border: 1px solid #555;
            border-radius: 4px;
            padding: 6px;
            color: white;
        }}
        QComboBox:focus {{ 
            border-color: {primary}; 
            background-color: #333333;
        }}
        QComboBox::drop-down {{ border: none; }}
        QComboBox::down-arrow {{ image: none; border: none; }}
        QComboBox QAbstractItemView {{
            background-color: #2d2d2d;
            color: white;
            selection-background-color: {primary};
        }}
        """)

    def _update_spinbox_style(self, spinbox: QSpinBox):
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

    def _update_slider_style(self, slider: QSlider):
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        slider.setStyleSheet(f"""
        QSlider::groove:horizontal {{
            border: 1px solid #555;
            height: 6px;
            background: #2d2d2d;
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: {primary};
            border: 1px solid {primary};
            width: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{
            background: {primary_light};
            border-color: {primary_light};
        }}
        """)

    def _update_value_label_style(self, label: QLabel):
        primary = theme_manager.get("primary_color")
        label.setStyleSheet(f"color: {primary}; padding-left: 4px; background: transparent;")

    # ---------- Theme change hook ----------

    def _on_theme_changed(self):
        """Handle theme change by updating all styled components"""
        try:
            # Frame + header
            self._update_main_frame_style()
            if hasattr(self, 'header'):
                self._update_header_style()
            self._update_scroll_area_style()

            # Theme buttons - update all button styles
            self._update_theme_button_styles()

            # Sections
            for group in self.findChildren(QGroupBox):
                self._update_section_style(group)

            # Labels
            for label in self.findChildren(QLabel):
                if label is getattr(self, "header", None):
                    self._update_header_style()
                elif label is getattr(self, "confidence_value", None):
                    self._update_value_label_style(label)
                else:
                    self._update_label_style(label)

            # Inputs
            for edit in self.findChildren(QLineEdit):
                self._update_input_style(edit)
            for combo in self.findChildren(QComboBox):
                self._update_combo_style(combo)
            for spin in self.findChildren(QSpinBox):
                self._update_spinbox_style(spin)
            for slider in self.findChildren(QSlider):
                self._update_slider_style(slider)

            # Buttons
            self._update_save_button_style()
            self._update_reset_button_style()
            self._update_test_button_style()

            self.logger.info(f"Settings screen updated for theme: {theme_manager.get_theme_name()}")
        except Exception as e:
            self.logger.warning(f"Failed to apply theme changes: {e}")

    # ---------- Config I/O ----------

    @error_boundary
    def load_config(self):
        """Load current configuration settings"""
        cfg = config_manager.get_config(self.config_path)
        current = cfg.get("current", {})
        wave = current.get("wave_detection", {})
        module_debug = current.get("module_debug", {})

        # Network
        self.network_inputs["esp32_url"].setText(current.get("esp32_cam_url", ""))
        self.network_inputs["proxy_url"].setText(current.get("camera_proxy_url", ""))
        self.network_inputs["control_ws"].setText(current.get("control_websocket_url", "localhost:8766"))

        # Logging
        self.debug_combos["debug_combo"].setCurrentText(current.get("debug_level", "INFO"))
        self.debug_combos["camera_debug_combo"].setCurrentText(module_debug.get("camera", "INFO"))
        self.debug_combos["servo_debug_combo"].setCurrentText(module_debug.get("servo", "INFO"))
        self.debug_combos["network_debug_combo"].setCurrentText(module_debug.get("network", "INFO"))

        # Wave
        self.sample_duration_spin.setValue(wave.get("sample_duration", 3))
        self.sample_rate_spin.setValue(wave.get("sample_rate", 5))
        conf_pct = int(wave.get("confidence_threshold", 0.7) * 100)
        self.confidence_slider.setValue(conf_pct)
        self.confidence_value.setText(f"{conf_pct}%")
        self.stand_down_spin.setValue(wave.get("stand_down_time", 30))

        # Theme selector state - ensure buttons reflect current theme
        self._update_theme_button_styles()

    
    def save_config(self):
        """Validate and save settings to file"""
        if not self._validate_inputs():
            return
        
        try:
            existing = config_manager.get_config(self.config_path)
        except Exception:
            existing = {}

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
                    **{
                        k: v for k, v in existing.get("current", {}).get("module_debug", {}).items()
                        if k not in {"camera", "servo", "network"}
                    }
                },
                "wave_detection": {
                    "sample_duration": self.sample_duration_spin.value(),
                    "sample_rate": self.sample_rate_spin.value(),
                    "confidence_threshold": self.confidence_slider.value() / 100.0,
                    "stand_down_time": self.stand_down_spin.value(),
                }
            },
            "defaults": existing.get("defaults", {})
        }
        try:
            success = config_manager.save_config(self.config_path, new_config)
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")
            success = False

        if success:
            if self.websocket:
                self.send_websocket_message(
                    "update_camera_config",
                    esp32_url=self.network_inputs["esp32_url"].text().strip()
                )

            QMessageBox.information(
                self,
                "Settings Saved",
                "Configuration updated successfully.\n\n"
                "Note: Some changes (e.g., global log level) may require app restart."
            )
            self.logger.info("Configuration updated successfully")
            self._notify_config_changes()
        else:
            QMessageBox.critical(
                self,
                "Save Failed",
                "Failed to save configuration.\n\nPlease check file permissions and try again."
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
        if reply != QMessageBox.StandardButton.Yes:
            return

        cfg = config_manager.get_config(self.config_path)
        defaults = cfg.get("defaults", {})
        if defaults:
            cfg["current"] = defaults.copy()
            if config_manager.save_config(self.config_path, cfg):
                self.load_config()
                QMessageBox.information(self, "Reset Complete", "Configuration has been reset to defaults.")
                self.logger.info("Configuration reset to defaults")
            else:
                QMessageBox.critical(self, "Reset Failed", "Failed to reset configuration.")
        else:
            self._create_default_config()
            QMessageBox.information(self, "Defaults Created", "Default configuration has been created and applied.")

    @error_boundary
    def test_websocket_connection(self):
        """Basic format validation of WebSocket URL (non-blocking)"""
        url = self.network_inputs["control_ws"].text().strip()
        if not url:
            QMessageBox.warning(self, "Invalid URL", "Please enter a WebSocket URL before testing.")
            return

        try:
            if not (url.startswith("ws://") or url.startswith("wss://")):
                test_url = f"ws://{url}"
            else:
                test_url = url

            from urllib.parse import urlparse
            parsed = urlparse(test_url)

            if parsed.scheme in ['ws', 'wss'] and parsed.netloc:
                QMessageBox.information(
                    self,
                    "Connection Test",
                    f"WebSocket URL format is valid: {test_url}\n\n"
                    "Note: Actual connectivity will be tested when you save settings."
                )
            else:
                QMessageBox.warning(self, "Invalid URL", f"WebSocket URL format is invalid: {test_url}")
        except Exception as e:
            QMessageBox.critical(self, "Test Failed", f"Connection test failed: {str(e)}")
            self.logger.error(f"WebSocket connection test failed: {e}")

    # ---------- Validation / Notifications ----------

    def _validate_inputs(self) -> bool:
        errors = []

        esp32_url = self.network_inputs["esp32_url"].text().strip()
        proxy_url = self.network_inputs["proxy_url"].text().strip()
        ws_url = self.network_inputs["control_ws"].text().strip()

        if esp32_url and not (esp32_url.startswith("http://") or esp32_url.startswith("https://")):
            errors.append("ESP32 URL must start with http:// or https://")
        if proxy_url and not (proxy_url.startswith("http://") or proxy_url.startswith("https://")):
            errors.append("Camera Proxy URL must start with http:// or https://")
        if not ws_url:
            errors.append("WebSocket URL is required")

        if self.sample_duration_spin.value() < 1:
            errors.append("Sample duration must be at least 1 second")
        if self.sample_rate_spin.value() < 1:
            errors.append("Sample rate must be at least 1 Hz")

        if errors:
            QMessageBox.warning(
                self,
                "Invalid Settings",
                "Please correct the following errors:\n\n" + "\n".join(f"• {e}" for e in errors)
            )
            return False
        return True

    def _create_default_config(self):
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
                    "error": "ERROR",
                },
                "network_monitoring": {"update_interval": 5.0, "ping_samples": 3},
                "wave_detection": {
                    "sample_duration": 3,
                    "sample_rate": 5,
                    "confidence_threshold": 0.7,
                    "stand_down_time": 30,
                },
            }
        }
        default_config["defaults"] = default_config["current"].copy()
        config_manager.save_config(self.config_path, default_config)
        self.load_config()

    def _notify_config_changes(self):
        """Notify other components about configuration changes"""
        try:
            from PyQt6.QtWidgets import QApplication

            app = QApplication.instance()
            if not app:
                return

            for widget in app.allWidgets():
                if hasattr(widget, "reload_wave_settings"):
                    widget.reload_wave_settings()
                elif hasattr(widget, "reload_camera_settings"):
                    widget.reload_camera_settings()
                elif hasattr(widget, "reload_network_settings"):
                    widget.reload_network_settings()

        except Exception as e:
            self.logger.warning(f"Failed to notify components of config changes: {e}")

