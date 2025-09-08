"""
WALL-E Control System - Camera Feed Screen (Themed)
- Integrated with theme manager for dynamic theming
- Wider right panel (380px) to prevent button crowding
- Theme-aware color styling throughout
- Full theme support for all UI elements
- Added debouncing for camera settings to prevent excessive HTTP requests
"""
import os
import time
import requests
from collections import deque
from typing import Dict, Any, Callable

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QSlider, QSpinBox,
    QCheckBox, QWidget, QSizePolicy
)
from PyQt6.QtGui import QFont, QImage, QPixmap
from PyQt6.QtCore import Qt, QSize, QTimer

from widgets.base_screen import BaseScreen
from threads.image_processor import ImageProcessingThread
from core.config_manager import config_manager
from core.theme_manager import theme_manager
from core.utils import error_boundary
from core.logger import get_logger


class CameraSettingsDebouncer:
    """
    Debounces camera settings changes to prevent excessive HTTP requests.
    Collects multiple rapid changes and sends them as a single batch request.
    """
    
    def __init__(self, proxy_base_url: str, delay_ms: int = 500):
        self.proxy_base_url = proxy_base_url
        self.delay_ms = delay_ms
        self.logger = get_logger("camera")
        
        # Timer for debouncing
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self._send_batched_settings)
        
        # Pending settings to send
        self.pending_settings: Dict[str, Any] = {}
        
        # Status callback for UI updates
        self.status_callback: Callable[[str, str], None] = None
    
    def set_status_callback(self, callback: Callable[[str, str], None]):
        """Set callback for status updates (message, color)"""
        self.status_callback = callback
    
    def update_setting(self, key: str, value: Any):
        """
        Queue a setting change for debounced sending.
        
        Args:
            key: Setting name (e.g., 'brightness', 'contrast', 'resolution')
            value: Setting value
        """
        self.pending_settings[key] = value
        
        # Restart the timer - this cancels any previous timer
        self.debounce_timer.stop()
        self.debounce_timer.start(self.delay_ms)
        
        # Update UI to show pending state
        if self.status_callback:
            pending_count = len(self.pending_settings)
            self.status_callback(
                f"Pending: {pending_count} setting{'s' if pending_count != 1 else ''}...", 
                "#FFAA00"  # Orange for pending
            )
        
        self.logger.debug(f"Queued setting: {key}={value}, pending: {list(self.pending_settings.keys())}")
    
    def _send_batched_settings(self):
        """Send all pending settings in a single HTTP request"""
        if not self.pending_settings:
            return
        
        settings_to_send = self.pending_settings.copy()
        self.pending_settings.clear()
        
        try:
            self.logger.info(f"Sending batched settings: {settings_to_send}")
            
            if self.status_callback:
                self.status_callback("Updating camera...", "#FFAA00")
            
            response = requests.post(
                f"{self.proxy_base_url}/camera/settings", 
                json=settings_to_send, 
                timeout=3
            )
            
            if response.status_code == 200:
                success_msg = f"Updated {len(settings_to_send)} setting{'s' if len(settings_to_send) != 1 else ''}"
                if self.status_callback:
                    self.status_callback(success_msg, "#44FF44")  # Green for success
                self.logger.info(f"Successfully updated settings: {list(settings_to_send.keys())}")
            else:
                error_msg = f"Update failed: HTTP {response.status_code}"
                if self.status_callback:
                    self.status_callback(error_msg, "#FF4444")  # Red for error
                self.logger.error(f"Settings update failed: HTTP {response.status_code}")
                
        except requests.exceptions.Timeout:
            error_msg = "Update timeout"
            if self.status_callback:
                self.status_callback(error_msg, "#FF4444")
            self.logger.error("Settings update timeout")
            
        except Exception as e:
            error_msg = f"Update error: {str(e)[:30]}"
            if self.status_callback:
                self.status_callback(error_msg, "#FF4444")
            self.logger.error(f"Settings update error: {e}")
    
    def force_send_now(self):
        """Immediately send any pending settings (for critical changes)"""
        if self.debounce_timer.isActive():
            self.debounce_timer.stop()
            self._send_batched_settings()
    
    def has_pending_changes(self) -> bool:
        """Check if there are pending changes"""
        return bool(self.pending_settings) or self.debounce_timer.isActive()
    
    def clear_pending(self):
        """Clear all pending changes without sending"""
        self.debounce_timer.stop()
        self.pending_settings.clear()
        if self.status_callback:
            self.status_callback("Ready", "#44FF44")


class CameraControlsWidget(QWidget):
    """
    Camera controls panel (unified side panel) with theme manager integration and debouncing
    - Theme-aware bordered outer wrapper (header/settings/actions/status)
    - ESP32 SETTINGS contains all camera/image controls
    - ACTIONS contains Reset + Start Stream + Track Person toggle buttons
    - Debounced settings to prevent excessive HTTP requests
    """

    def __init__(self, stream_button: QPushButton, track_button: QPushButton, parent=None):
        super().__init__(parent)
        self.logger = get_logger("camera")
        wave_config = config_manager.get_wave_config()
        raw_url = wave_config.get("camera_proxy_url", "http://10.1.1.230:8081")
        self.proxy_base_url = raw_url.replace("/stream", "")
        self.current_settings = {}

        # External buttons (wired by parent)
        self.stream_button = stream_button
        self.track_button = track_button

        # Initialize debouncer
        self.settings_debouncer = CameraSettingsDebouncer(
            proxy_base_url=self.proxy_base_url,
            delay_ms=500  # 500ms delay
        )
        self.settings_debouncer.set_status_callback(self._update_status_display)

        # Register for theme change notifications
        theme_manager.register_callback(self._on_theme_changed)

        self.init_ui()
        self.load_current_settings()

    def _update_status_display(self, message: str, color: str):
        """Update status display with color"""
        if hasattr(self, 'status_label'):
            self.status_label.setText(message)
            self.status_label.setStyleSheet(
                f"color: {color}; border: none; padding: 3px; text-align: center;"
            )

    def init_ui(self):
        """Initialize the camera controls UI with theme-aware styling."""
        # Scope the outer panel styles using objectName, so children don't inherit the border
        self.setObjectName("cameraPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(380)  # wider to prevent button crowding
        self._update_panel_style()

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 10, 15, 15)
        main_layout.setSpacing(12)

        # Header - "CAMERA SETTINGS"
        self.header = QLabel("CAMERA SETTINGS")
        self.header.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_header_style()
        main_layout.addWidget(self.header)

        # Combined settings section (ESP32 SETTINGS + Image controls)
        esp32_section = self._create_esp32_section()
        main_layout.addWidget(esp32_section)
        main_layout.addSpacing(10)

        # Actions Section (Reset + Start/Track toggle buttons)
        actions_section = self._create_actions_section()
        main_layout.addWidget(actions_section)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setFont(QFont("Arial", 12))
        self._update_status_label_style()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_label)

        main_layout.addStretch()
        self.setLayout(main_layout)

    def _update_panel_style(self):
        """Update panel style based on current theme"""
        primary_color = theme_manager.get("primary_color")
        panel_dark = theme_manager.get("panel_dark")
        self.setStyleSheet(f"""
            #cameraPanel {{
                background-color: {panel_dark};
                border: 2px solid {primary_color};
                border-radius: 12px;
                color: white;
            }}
        """)

    def _update_header_style(self):
        """Update header style based on current theme"""
        primary_color = theme_manager.get("primary_color")
        self.header.setStyleSheet(f"""
            QLabel {{
                border: none;
                background-color: rgba(0, 0, 0, 0.9);
                color: {primary_color};
                padding: 8px;
                border-radius: 6px;
                margin-bottom: 5px;
            }}
        """)

    def _update_status_label_style(self):
        """Update status label style based on current theme"""
        grey_light = theme_manager.get("grey_light")
        self.status_label.setStyleSheet(f"color: {grey_light}; border: none; padding: 3px; text-align: center;")

    def _get_base_button_style(self) -> str:
        """Get base button style using theme manager"""
        return theme_manager.get_button_style("default")

    def _get_yellow_checked_style(self) -> str:
        """Get yellow checked button style using theme colors"""
        primary_color = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        return f"""
        QPushButton:checked {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {primary_light}, stop:1 {primary_color});
            border: 2px solid {primary_light};
            color: black;
            font-weight: bold;
        }}
        QPushButton:checked:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFEA00, stop:1 {primary_light});
            border: 2px solid #FFEA00;
        }}
        """

    def _get_green_checked_style(self) -> str:
        """Get green checked button style using theme colors"""
        green = theme_manager.get("green")
        green_gradient = theme_manager.get("green_gradient")
        return f"""
        QPushButton:checked {{
            background: {green_gradient};
            border: 2px solid {green};
            color: black;
            font-weight: bold;
        }}
        QPushButton:checked:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #66FF66, stop:1 #2FAE2F);
            border: 2px solid #66FF66;
        }}
        """

    def _create_esp32_section(self):
        """Create ESP32 camera settings section holding all camera settings."""
        esp32_frame = QWidget()
        esp32_frame.setObjectName("esp32Frame")
        self._update_section_frame_style(esp32_frame)
        esp32_layout = QVBoxLayout()
        esp32_layout.setContentsMargins(12, 8, 12, 12)
        esp32_layout.setSpacing(8)

        # Section header
        self.esp32_header = QLabel("ESP32 SETTINGS")
        self.esp32_header.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.esp32_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_section_header_style(self.esp32_header)
        esp32_layout.addWidget(self.esp32_header)

        # XCLK Frequency - immediate update (affects stream)
        xclk_layout = QHBoxLayout()
        xclk_label = QLabel("XCLK MHz:")
        xclk_label.setFont(QFont("Arial", 12))
        self._update_control_label_style(xclk_label)
        xclk_label.setFixedWidth(80)

        self.xclk_spin = QSpinBox()
        self.xclk_spin.setRange(8, 20)
        self.xclk_spin.setValue(10)
        self.xclk_spin.setFont(QFont("Arial", 12))
        self.xclk_spin.setFixedWidth(60)
        self._update_spinbox_style(self.xclk_spin)

        xclk_btn = QPushButton("SET")
        xclk_btn.setFont(QFont("Arial", 11))
        xclk_btn.setFixedSize(45, 28)
        xclk_btn.clicked.connect(lambda: self.settings_debouncer.force_send_now() if self._update_xclk() else None)
        xclk_btn.setStyleSheet(self._get_base_button_style())

        xclk_layout.addWidget(xclk_label)
        xclk_layout.addWidget(self.xclk_spin)
        xclk_layout.addWidget(xclk_btn)
        xclk_layout.addStretch()
        esp32_layout.addLayout(xclk_layout)

        # Resolution - immediate update (affects stream significantly)
        res_layout = QHBoxLayout()
        res_label = QLabel("Resolution:")
        res_label.setFont(QFont("Arial", 12))
        self._update_control_label_style(res_label)
        res_label.setFixedWidth(80)

        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems([
            "QQVGA(160x120)", "QCIF(176x144)", "HQVGA(240x176)", "QVGA(320x240)",
            "CIF(400x296)", "VGA(640x480)", "SVGA(800x600)", "XGA(1024x768)",
            "SXGA(1280x1024)", "UXGA(1600x1200)"
        ])
        self.resolution_combo.setCurrentIndex(5)  # VGA
        self.resolution_combo.setFont(QFont("Arial", 11))
        self._update_combobox_style(self.resolution_combo)
        self.resolution_combo.currentIndexChanged.connect(self._on_resolution_changed)

        res_layout.addWidget(res_label)
        res_layout.addWidget(self.resolution_combo)
        esp32_layout.addLayout(res_layout)

        # ---- Image Controls (sliders) - all debounced ----
        self.quality_slider, quality_layout = self.create_slider_control(
            "Quality:", 4, 63, 12, "quality"
        )
        esp32_layout.addLayout(quality_layout)

        self.brightness_slider, brightness_layout = self.create_slider_control(
            "Brightness:", -2, 2, 0, "brightness"
        )
        esp32_layout.addLayout(brightness_layout)

        self.contrast_slider, contrast_layout = self.create_slider_control(
            "Contrast:", -2, 2, 0, "contrast"
        )
        esp32_layout.addLayout(contrast_layout)

        self.saturation_slider, saturation_layout = self.create_slider_control(
            "Saturation:", -2, 2, 0, "saturation"
        )
        esp32_layout.addLayout(saturation_layout)

        # Mirror controls (H, V) with debounced updates
        mirror_layout = QHBoxLayout()
        mirror_label = QLabel("Mirror:")
        mirror_label.setFont(QFont("Arial", 12))
        self._update_control_label_style(mirror_label)
        mirror_label.setFixedWidth(80)

        self.h_mirror_btn = QPushButton("Horizontal")
        self.h_mirror_btn.setCheckable(True)
        self.h_mirror_btn.setFixedSize(100, 30)
        self.h_mirror_btn.setFont(QFont("Arial", 11))
        self.h_mirror_btn.setToolTip("Horizontal Mirror")
        self.h_mirror_btn.clicked.connect(
            lambda checked: self.settings_debouncer.update_setting("h_mirror", checked)
        )
        self.h_mirror_btn.setStyleSheet(self._get_base_button_style() + self._get_yellow_checked_style())

        self.v_flip_btn = QPushButton("Vertical")
        self.v_flip_btn.setCheckable(True)
        self.v_flip_btn.setFixedSize(100, 30)
        self.v_flip_btn.setFont(QFont("Arial", 11))
        self.v_flip_btn.setToolTip("Vertical Flip")
        self.v_flip_btn.clicked.connect(
            lambda checked: self.settings_debouncer.update_setting("v_flip", checked)
        )
        self.v_flip_btn.setStyleSheet(self._get_base_button_style() + self._get_yellow_checked_style())

        mirror_layout.addWidget(mirror_label)
        mirror_layout.addWidget(self.h_mirror_btn)
        mirror_layout.addWidget(self.v_flip_btn)
        mirror_layout.addStretch()
        esp32_layout.addLayout(mirror_layout)

        esp32_frame.setLayout(esp32_layout)
        return esp32_frame

    def _update_xclk(self) -> bool:
        """Update XCLK frequency immediately and return True"""
        self.settings_debouncer.update_setting("xclk_freq", self.xclk_spin.value())
        return True

    def _on_resolution_changed(self, index: int):
        """Handle resolution change - send immediately due to stream impact"""
        self.settings_debouncer.update_setting("resolution", index)
        self.settings_debouncer.force_send_now()  # Immediate send for resolution

    def _create_actions_section(self):
        """Create camera actions section: Reset + Start Stream + Track Person (toggles)"""
        actions_frame = QWidget()
        actions_frame.setObjectName("actionsFrame")
        self._update_section_frame_style(actions_frame)
        actions_layout = QVBoxLayout()
        actions_layout.setContentsMargins(12, 8, 12, 12)
        actions_layout.setSpacing(8)

        self.actions_header = QLabel("ACTIONS")
        self.actions_header.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.actions_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_section_header_style(self.actions_header)
        actions_layout.addWidget(self.actions_header)

        # Reset button
        self.reset_btn = QPushButton("🔄 RESET TO DEFAULTS")
        self.reset_btn.setFont(QFont("Arial", 12))
        self.reset_btn.clicked.connect(lambda: self.reset_to_defaults)
        self.reset_btn.setStyleSheet(self._get_base_button_style())
        actions_layout.addWidget(self.reset_btn)

        # Row for toggle buttons (now has more width; use Expanding policies to avoid crowding)
        toggles_row = QHBoxLayout()
        toggles_row.setSpacing(10)

        # Stream button (primary color when checked)
        self.stream_button.setText("Start Stream")
        self.stream_button.setCheckable(True)
        self.stream_button.setChecked(False)
        self.stream_button.setMinimumHeight(40)
        self.stream_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.stream_button.setStyleSheet(self._get_base_button_style() + self._get_yellow_checked_style())
        toggles_row.addWidget(self.stream_button, stretch=1)

        # Track button (green when checked, disabled until streaming)
        self.track_button.setText("Track Person")
        self.track_button.setCheckable(True)
        self.track_button.setChecked(False)
        self.track_button.setEnabled(False)
        self.track_button.setMinimumHeight(40)
        self.track_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.track_button.setStyleSheet(self._get_base_button_style() + self._get_green_checked_style())
        toggles_row.addWidget(self.track_button, stretch=1)

        actions_layout.addLayout(toggles_row)
        actions_frame.setLayout(actions_layout)
        return actions_frame

    def _update_section_frame_style(self, frame):
        """Update section frame style based on current theme"""
        frame.setStyleSheet("""
            QWidget {
                border: 1px solid #555;
                border-radius: 8px;
                background-color: rgba(0, 0, 0, 0.3);
            }
        """)

    def _update_section_header_style(self, label):
        """Update section header style based on current theme"""
        primary_color = theme_manager.get("primary_color")
        label.setStyleSheet(f"color: {primary_color}; border: none; margin-bottom: 5px;")

    def _update_control_label_style(self, label):
        """Update control label style based on current theme"""
        label.setStyleSheet("border: none; color: white;")

    def _update_spinbox_style(self, spinbox):
        """Update spinbox style based on current theme"""
        spinbox.setStyleSheet("""
            QSpinBox {
                background-color: #2a2a2a;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
                color: white;
            }
            QSpinBox:focus { border-color: #555; }
        """)

    def _update_combobox_style(self, combobox):
        """Update combobox style based on current theme"""
        combobox.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
                color: white;
            }
            QComboBox:focus { border-color: #555; }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow { image: none; border: none; }
        """)

    def create_slider_control(self, label_text, min_val, max_val, default_val, setting_name):
        """Create a slider control with debounced updates and theme-aware styling."""
        layout = QHBoxLayout()
        layout.setSpacing(8)

        label = QLabel(label_text)
        label.setFont(QFont("Arial", 12))
        self._update_control_label_style(label)
        label.setFixedWidth(80)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(default_val)
        slider.setFixedWidth(160)  # a bit wider with the new panel width
        self._update_slider_style(slider)

        value_label = QLabel(str(default_val))
        value_label.setFont(QFont("Arial", 12))
        self._update_value_label_style(value_label)
        value_label.setFixedWidth(30)
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Connect slider to update value label and debounced setting
        slider.valueChanged.connect(lambda val: value_label.setText(str(val)))
        slider.valueChanged.connect(lambda val: self.settings_debouncer.update_setting(setting_name, val))

        layout.addWidget(label)
        layout.addWidget(slider)
        layout.addWidget(value_label)
        layout.addStretch()
        return slider, layout

    def _update_slider_style(self, slider):
        """Update slider style based on current theme"""
        primary_color = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        slider.setStyleSheet(f"""
            QSlider {{ border: none; background: transparent; }}
            QSlider::groove:horizontal {{
                border: 1px solid #555;
                height: 6px;
                background: #333;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {primary_color};
                border: 1px solid {primary_color};
                width: 16px; height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {primary_light};
                border-color: {primary_light};
            }}
        """)

    def _update_value_label_style(self, label):
        """Update value label style based on current theme"""
        primary_color = theme_manager.get("primary_color")
        label.setStyleSheet(f"border: none; color: {primary_color};")

    def _on_theme_changed(self):
        """Handle theme change by updating all styled components"""
        try:
            # Update main panel
            self._update_panel_style()
            self._update_header_style()
            self._update_status_label_style()
            
            # Update section headers
            self._update_section_header_style(self.esp32_header)
            self._update_section_header_style(self.actions_header)
            
            # Update all sliders
            for slider_name in ['quality_slider', 'brightness_slider', 'contrast_slider', 'saturation_slider']:
                if hasattr(self, slider_name):
                    self._update_slider_style(getattr(self, slider_name))
            
            # Update all value labels (find them in the layout)
            for i in range(self.layout().count()):
                item = self.layout().itemAt(i)
                if item and item.widget():
                    self._update_widget_themes_recursive(item.widget())
            
            # Update buttons with new theme colors
            button_style = self._get_base_button_style()
            yellow_checked = self._get_yellow_checked_style()
            green_checked = self._get_green_checked_style()
            
            if hasattr(self, 'reset_btn'):
                self.reset_btn.setStyleSheet(button_style)
            
            if hasattr(self, 'h_mirror_btn'):
                self.h_mirror_btn.setStyleSheet(button_style + yellow_checked)
            
            if hasattr(self, 'v_flip_btn'):
                self.v_flip_btn.setStyleSheet(button_style + yellow_checked)
            
            # Update external buttons
            self.stream_button.setStyleSheet(button_style + yellow_checked)
            self.track_button.setStyleSheet(button_style + green_checked)
            
            self.logger.info(f"Camera controls updated for theme: {theme_manager.get_display_name()}")
        except Exception as e:
            self.logger.error(f"Error updating camera controls theme: {e}")

    def _update_widget_themes_recursive(self, widget):
        """Recursively update widget themes"""
        # Update specific widget types
        if isinstance(widget, QLabel) and widget.text().isdigit():
            # Value labels for sliders
            self._update_value_label_style(widget)
        elif isinstance(widget, QLabel) and any(text in widget.text().lower() for text in ['xclk', 'resolution', 'quality', 'brightness', 'contrast', 'saturation', 'mirror']):
            # Control labels
            self._update_control_label_style(widget)
        
        # Recursively check children
        for child in widget.findChildren(QWidget):
            if child.parent() == widget:  # Only immediate children
                self._update_widget_themes_recursive(child)

    @error_boundary
    def load_current_settings(self):
        """Load current settings from camera proxy."""
        try:
            response = requests.get(f"{self.proxy_base_url}/camera/settings", timeout=3)
            if response.status_code == 200:
                settings = response.json()
                self.current_settings = settings

                # Update UI (without triggering debounced updates)
                if "xclk_freq" in settings:
                    self.xclk_spin.setValue(settings["xclk_freq"])
                if "resolution" in settings:
                    self.resolution_combo.setCurrentIndex(settings["resolution"])
                if "quality" in settings:
                    self.quality_slider.setValue(settings["quality"])
                if "brightness" in settings:
                    self.brightness_slider.setValue(settings["brightness"])
                if "contrast" in settings:
                    self.contrast_slider.setValue(settings["contrast"])
                if "saturation" in settings:
                    self.saturation_slider.setValue(settings["saturation"])
                if "h_mirror" in settings:
                    self.h_mirror_btn.setChecked(settings["h_mirror"])
                if "v_flip" in settings:
                    self.v_flip_btn.setChecked(settings["v_flip"])

                self._update_status_display("Settings loaded", "#44FF44")
                self.logger.info("Loaded camera settings")
        except Exception as e:
            self._update_status_display("Failed to load settings", "#FF4444")
            self.logger.error(f"Failed to load camera settings: {e}")

    @error_boundary
    def update_setting(self, setting_name, value):
        """Update a camera setting via the proxy (legacy method - now uses debouncer)."""
        # This method is kept for backward compatibility but now uses the debouncer
        self.settings_debouncer.update_setting(setting_name, value)

    @error_boundary
    def reset_to_defaults(self):
        """Reset all settings to default values with debouncer clear."""
        # Clear any pending changes first
        self.settings_debouncer.clear_pending()
        
        defaults = {
            "xclk_freq": 10, "resolution": 5, "quality": 12,
            "brightness": 0, "contrast": 0, "saturation": 0,
            "h_mirror": False, "v_flip": False
        }

        # Update UI controls (this will trigger debounced updates, but we'll override)
        self.xclk_spin.setValue(defaults["xclk_freq"])
        self.resolution_combo.setCurrentIndex(defaults["resolution"])
        self.quality_slider.setValue(defaults["quality"])
        self.brightness_slider.setValue(defaults["brightness"])
        self.contrast_slider.setValue(defaults["contrast"])
        self.saturation_slider.setValue(defaults["saturation"])
        self.h_mirror_btn.setChecked(defaults["h_mirror"])
        self.v_flip_btn.setChecked(defaults["v_flip"])

        # Send defaults immediately (this is a user action, bypass debouncer)
        try:
            self._update_status_display("Resetting to defaults...", "#FFAA00")
            response = requests.post(f"{self.proxy_base_url}/camera/settings", json=defaults, timeout=3)
            if response.status_code == 200:
                self._update_status_display("Reset to defaults", "#44FF44")
                self.current_settings = defaults
                # Clear any pending changes that might have been queued by UI updates
                self.settings_debouncer.clear_pending()
                self.logger.info("Reset camera settings to defaults")
            else:
                self._update_status_display("Reset failed", "#FF4444")
                self.logger.error(f"Reset failed: HTTP {response.status_code}")
        except Exception as e:
            error_msg = f"Error: {str(e)[:20]}"
            self._update_status_display(error_msg, "#FF4444")
            self.logger.error(f"Failed to reset to defaults: {e}")

    def cleanup(self):
        """Clean up debouncer on widget destruction"""
        if hasattr(self, 'settings_debouncer'):
            # Send any final pending changes
            if self.settings_debouncer.has_pending_changes():
                self.settings_debouncer.force_send_now()

    def __del__(self):
        """Clean up theme manager callback and debouncer on destruction"""
        try:
            theme_manager.unregister_callback(self._on_theme_changed)
        except:
            pass  # Ignore errors during cleanup
        
        # Cleanup debouncer
        self.cleanup()


class CameraFeedScreen(BaseScreen):
    """Live camera stream display with tracking and unified controls."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Register for theme change notifications
        theme_manager.register_callback(self._on_theme_changed)

    def _setup_screen(self):
        wave_config = config_manager.get_wave_config()

        # Wave detection sampling state
        self.sample_buffer = deque(maxlen=wave_config["sample_duration"] * wave_config["sample_rate"])
        self.last_wave_time = 0
        self.last_sample_time = 0

        self.tracking_enabled = False
        self.streaming_enabled = False
        self.stream_can_change_settings = True

        # Camera URLs
        camera_proxy_url = wave_config.get("camera_proxy_url", "")
        self.camera_proxy_base_url = camera_proxy_url.replace("/stream", "") if camera_proxy_url else ""

        # Image processing thread
        self.image_thread = ImageProcessingThread(camera_proxy_url)
        self.image_thread.frame_processed.connect(self.update_display)
        self.image_thread.stats_updated.connect(self.update_stats)

        # Build UI and wire controls
        self.init_ui()

        # Start image thread
        self.image_thread.start()
        self.check_stream_status()

    def init_ui(self):
        # Video display
        self.video_label = QLabel()
        self.video_label.setFixedSize(640, 480)
        self._update_video_label_style()

        # Stats display
        self.stats_label = QLabel("Stream Stats: Initializing...")
        self._update_stats_label_style()
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.stats_label.setFixedWidth(640)

        # Create control buttons first (to pass into widget)
        self.setup_control_buttons()

        # Controls widget (contains Actions with our toggle buttons)
        self.controls_widget = CameraControlsWidget(
            stream_button=self.stream_button,
            track_button=self.tracking_button
        )
        self.controls_widget.setMaximumHeight(700)

        # Layouts
        self.setup_layout()

    def _update_video_label_style(self):
        """Update video label style based on current theme"""
        grey = theme_manager.get("grey")
        self.video_label.setStyleSheet(f"""
            border: 2px solid {grey};
            padding: 2px;
            background-color: black;
        """)

    def _update_stats_label_style(self):
        """Update stats label style based on current theme"""
        grey = theme_manager.get("grey")
        grey_light = theme_manager.get("grey_light")
        self.stats_label.setStyleSheet(f"""
            border: 1px solid {grey};
            border-radius: 4px;
            padding: 1px;
            background-color: black;
            color: {grey_light};
        """)

    def setup_control_buttons(self):
        """Create stream and tracking buttons with theme-aware styling."""
        # Stream toggle
        self.stream_button = QPushButton("Start Stream")
        self.stream_button.setCheckable(True)
        self.stream_button.setChecked(False)
        self.stream_button.setMinimumSize(150, 40)
        self._update_stream_button_style()
        self.stream_button.toggled.connect(self.toggle_stream)

        # Tracking toggle (disabled until stream is active)
        self.tracking_button = QPushButton("Track Person")
        self.tracking_button.setCheckable(True)
        self.tracking_button.setChecked(False)
        self.tracking_button.setMinimumSize(150, 40)
        self.tracking_button.setToolTip("Toggle Wave Detection / Person Tracking")
        self.tracking_button.setEnabled(False)
        self._update_tracking_button_style()
        self.tracking_button.toggled.connect(self.toggle_tracking)

        self.logger.info("Camera control buttons initialized (themed, no icons)")

    def _update_stream_button_style(self):
        """Update stream button style based on current theme"""
        base_style = theme_manager.get_button_style("default")
        primary_color = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        checked_style = f"""
        QPushButton:checked {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {primary_light}, stop:1 {primary_color});
            border: 2px solid {primary_light};
            color: black;
            font-weight: bold;
        }}
        QPushButton:checked:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFEA00, stop:1 {primary_light});
            border: 2px solid #FFEA00;
        }}
        """
        self.stream_button.setStyleSheet(base_style + checked_style)

    def _update_tracking_button_style(self):
        """Update tracking button style based on current theme"""
        base_style = theme_manager.get_button_style("default")
        green = theme_manager.get("green")
        green_gradient = theme_manager.get("green_gradient")
        checked_style = f"""
        QPushButton:checked {{
            background: {green_gradient};
            border: 2px solid {green};
            color: black;
            font-weight: bold;
        }}
        QPushButton:checked:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #66FF66, stop:1 #2FAE2F);
            border: 2px solid #66FF66;
        }}
        """
        self.tracking_button.setStyleSheet(base_style + checked_style)

    def setup_layout(self):
        """Layout with video display left and unified controls right."""
        video_layout = QVBoxLayout()
        video_layout.setContentsMargins(0, 10, 0, 0)
        video_layout.addWidget(self.video_label)
        video_layout.addWidget(self.stats_label)

        # Right column contains the unified control panel
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(20, 5, 0, 0)  # left=20px, top=5px, right=0px, bottom=0px
        right_layout.setSpacing(20)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        right_layout.addWidget(self.controls_widget)
        right_layout.addStretch()

        main_layout = QHBoxLayout()
        main_layout.addSpacing(90)
        main_layout.addLayout(video_layout)
        main_layout.addLayout(right_layout)
        main_layout.addStretch()
        self.setLayout(main_layout)

    def update_stream_button_appearance(self):
        """Update the stream button appearance based on current state (text + checked)."""
        if self.streaming_enabled:
            self.stream_button.setText("Stop Stream")
            self.stream_button.setToolTip("Click to stop camera stream")
            self.stream_button.setChecked(True)
        else:
            self.stream_button.setText("Start Stream")
            self.stream_button.setToolTip("Click to start camera stream")
            self.stream_button.setChecked(False)

    def _on_theme_changed(self):
        """Handle theme change by updating all styled components"""
        try:
            # Update video and stats labels
            self._update_video_label_style()
            self._update_stats_label_style()
            
            # Update control buttons
            self._update_stream_button_style()
            self._update_tracking_button_style()
            
            self.logger.info(f"Camera screen updated for theme: {theme_manager.get_display_name()}")
        except Exception as e:
            self.logger.error(f"Error updating camera screen theme: {e}")

    @error_boundary
    def toggle_stream(self, checked):
        """Toggle camera stream on/off."""
        self.streaming_enabled = checked
        if self.streaming_enabled:
            self.logger.info("Starting camera stream")
            self.stats_label.setText("Stream Stats: Starting stream...")
            try:
                if self.camera_proxy_base_url:
                    response = requests.post(f"{self.camera_proxy_base_url}/stream/start", timeout=3)
                    if response.status_code == 200:
                        self.logger.info("Stream start command sent to proxy")
                        self.tracking_button.setEnabled(True)
                        self.stream_can_change_settings = False
                    else:
                        self.logger.warning(f"Stream start failed: HTTP {response.status_code}")
            except Exception as e:
                self.logger.error(f"Failed to start stream: {e}")
                self.stats_label.setText(f"Stream Error: {str(e)[:50]}")
        else:
            self.logger.info("Stopping camera stream")
            self.stats_label.setText("Stream Stats: Stopping stream...")

            # Disable tracking when stream stops
            if self.tracking_enabled:
                self.tracking_button.setChecked(False)
                self.toggle_tracking(False)
            self.tracking_button.setEnabled(False)

            try:
                if self.camera_proxy_base_url:
                    response = requests.post(f"{self.camera_proxy_base_url}/stream/stop", timeout=3)
                    if response.status_code == 200:
                        self.logger.info("Stream stop command sent to proxy")
                        self.stream_can_change_settings = True
                    else:
                        self.logger.warning(f"Stream stop failed: HTTP {response.status_code}")
            except Exception as e:
                self.logger.error(f"Failed to stop stream: {e}")

        self.update_stream_button_appearance()

    @error_boundary
    def check_stream_status(self):
        """Check if camera proxy stream is currently active and sync UI."""
        try:
            if not self.camera_proxy_base_url:
                return
            response = requests.get(f"{self.camera_proxy_base_url}/stream/status", timeout=2)
            if response.status_code == 200:
                status = response.json()
                is_streaming = status.get("streaming", False)

                if is_streaming != self.streaming_enabled:
                    self.streaming_enabled = is_streaming
                    self.stream_button.setChecked(is_streaming)
                    self.update_stream_button_appearance()
                    self.tracking_button.setEnabled(is_streaming)

                if is_streaming:
                    self.logger.info("Stream detected as active")
                    self.stats_label.setText("Stream Stats: Stream active")
                else:
                    self.logger.info("Stream detected as inactive")
                    self.stats_label.setText("Stream Stats: Stream inactive")
            else:
                self.logger.warning(f"Stream status check failed: HTTP {response.status_code}")
        except Exception as e:
            self.logger.error(f"Stream status check error: {e}")
            if self.streaming_enabled:
                self.streaming_enabled = False
                self.stream_button.setChecked(False)
                self.tracking_button.setEnabled(False)
                self.update_stream_button_appearance()

    @error_boundary
    def update_display(self, processed_data):
        """Update display with processed frame data."""
        try:
            frame_rgb = processed_data.frame
            wave_detected = processed_data.wave_detected

            if frame_rgb is None:
                self.video_label.setText("Camera not available\n(OpenCV not installed)")
                return

            # Wave detection aggregation logic
            if self.tracking_enabled and wave_detected:
                wave_config = config_manager.get_wave_config()
                current_time = time.time()
                if current_time - self.last_sample_time >= 1.0 / wave_config["sample_rate"]:
                    self.sample_buffer.append(wave_detected)
                    self.last_sample_time = current_time

                if len(self.sample_buffer) == self.sample_buffer.maxlen:
                    confidence = sum(self.sample_buffer) / len(self.sample_buffer)
                    if confidence >= wave_config["confidence_threshold"]:
                        if current_time - self.last_wave_time >= wave_config["stand_down_time"]:
                            self.send_websocket_message("gesture", name="wave")
                            self.last_wave_time = current_time
                            self.sample_buffer.clear()
                            self.logger.info("Wave gesture detected and sent!")

            # Convert to QPixmap and display
            height, width, channel = frame_rgb.shape
            bytes_per_line = 3 * width
            q_img = QImage(frame_rgb.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img).scaled(
                self.video_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )
            self.video_label.setPixmap(pixmap)

        except Exception as e:
            self.logger.error(f"Display update error: {e}")
            self.video_label.setText(f"Display Error:\n{str(e)}")

    def update_stats(self, stats_text):
        """Update statistics display."""
        self.stats_label.setText(f"Stream Stats: {stats_text}")

    @error_boundary
    def toggle_tracking(self, checked=None):
        """Toggle tracking with backend updates."""
        if checked is not None:
            self.tracking_enabled = checked
        else:
            self.tracking_enabled = self.tracking_button.isChecked()

        self.image_thread.set_tracking_enabled(self.tracking_enabled)

        if self.tracking_enabled:
            self.tracking_button.setToolTip("Wave Detection: ENABLED (Click to disable)")
            self.logger.info("Wave detection ENABLED")
        else:
            self.tracking_button.setToolTip("Wave Detection: DISABLED (Click to enable)")
            self.logger.info("Wave detection DISABLED")

        self.send_websocket_message("tracking", state=self.tracking_enabled)

        status = "ENABLED" if self.tracking_enabled else "DISABLED"
        current_stats = self.stats_label.text()
        if "Wave Detection:" in current_stats:
            parts = current_stats.split(" \n Wave Detection:")
            self.stats_label.setText(f"{parts[0]} \n Wave Detection: {status}")
        else:
            self.stats_label.setText(f"{current_stats} \n Wave Detection: {status}")

    def stop_camera_thread(self):
        if hasattr(self, 'image_thread'):
            self.image_thread.stop()

    def cleanup(self):
        """Cleanup camera screen resources"""
        self.stop_camera_thread()
        
        # Cleanup controls widget debouncer
        if hasattr(self, 'controls_widget'):
            self.controls_widget.cleanup()

    def __del__(self):
        """Clean up theme manager callback on destruction"""
        try:
            theme_manager.unregister_callback(self._on_theme_changed)
        except:
            pass  # Ignore errors during cleanup