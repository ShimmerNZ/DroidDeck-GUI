"""
WALL-E Control System - Camera Feed Screen (Cleaned & Fixed)
- Integrated with fixed image_processor.py
- Removed code duplication and unnecessary complexity
- Proper integration with updated ImageProcessingThread
- Fixed settings debouncer with better error handling
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
    FIXED: Debounces camera settings changes to prevent excessive HTTP requests.
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
        """Queue a setting change for debounced sending."""
        self.logger.debug(f"Queuing setting update: {key} = {value}")
        
        # Add to pending settings
        self.pending_settings[key] = value
        
        # Reset the debounce timer
        self.debounce_timer.stop()
        self.debounce_timer.start(self.delay_ms)
        
        # Update status to show pending
        if self.status_callback:
            self.status_callback("Settings pending...", "#FFA500")  # Orange
    
    def _send_batched_settings(self):
        """Send all pending settings as a batch request"""
        if not self.pending_settings:
            return
        
        settings_to_send = self.pending_settings.copy()
        self.pending_settings.clear()
        
        self.logger.info(f"Sending batched settings: {list(settings_to_send.keys())}")
        
        try:
            if self.status_callback:
                self.status_callback("Updating settings...", "#0088FF")  # Blue
            
            url = f"{self.proxy_base_url}/camera/settings"
            response = requests.post(
                url,
                json=settings_to_send,
                timeout=10,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                result = response.json()
                message = result.get("message", "Settings updated successfully")
                if self.status_callback:
                    self.status_callback(message, "#00AA00")  # Green
                self.logger.info(f"✅ {message}")
                
            else:
                try:
                    error_data = response.json()
                    error_message = error_data.get("message", f"HTTP {response.status_code}")
                except:
                    error_message = f"HTTP {response.status_code}"
                
                if self.status_callback:
                    self.status_callback(f"Update failed: {error_message}", "#FF0000")
                self.logger.error(f"❌ Settings update failed: {error_message}")
        
        except requests.exceptions.Timeout:
            if self.status_callback:
                self.status_callback("Update failed: Timeout", "#FF0000")
            self.logger.error("❌ Settings update timeout")
            
        except requests.exceptions.ConnectionError:
            if self.status_callback:
                self.status_callback("Update failed: Connection error", "#FF0000")
            self.logger.error("❌ Settings update connection error")
            
        except Exception as e:
            if self.status_callback:
                self.status_callback(f"Update failed: {str(e)}", "#FF0000")
            self.logger.error(f"❌ Settings update error: {e}")
    
    def force_send_now(self):
        """Force immediate sending of pending settings"""
        self.debounce_timer.stop()
        self._send_batched_settings()
    
    def clear_pending(self):
        """Clear all pending settings without sending"""
        self.pending_settings.clear()
        self.debounce_timer.stop()
        if self.status_callback:
            self.status_callback("Ready", "#888888")
    
    def has_pending_changes(self):
        """Check if there are pending changes"""
        return len(self.pending_settings) > 0
    
    def cleanup(self):
        """Cleanup debouncer resources"""
        self.debounce_timer.stop()
        self.pending_settings.clear()


class CameraControlsWidget(QWidget):
    """Camera controls panel with ESP32 settings and actions"""

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
            delay_ms=500
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
        """Initialize the camera controls UI"""
        self.setObjectName("cameraPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(380)
        self._update_panel_style()

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 10, 15, 15)
        main_layout.setSpacing(12)

        # Header
        self.header = QLabel("CAMERA SETTINGS")
        self.header.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_header_style()
        main_layout.addWidget(self.header)

        # ESP32 settings section
        esp32_section = self._create_esp32_section()
        main_layout.addWidget(esp32_section)
        main_layout.addSpacing(10)

        # Actions section
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

    def _create_esp32_section(self):
        """Create ESP32 camera settings section"""
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

        # Add this after your other controls in _create_esp32_section
        xclk_layout = QHBoxLayout()
        xclk_label = QLabel("X CLK:")
        xclk_label.setFont(QFont("Arial", 12))
        self._update_control_label_style(xclk_label)
        xclk_label.setFixedWidth(80)

        self.xclk_slider = QSlider(Qt.Orientation.Horizontal)
        self.xclk_slider.setRange(1, 40)  # Adjust min/max as needed for your hardware
        self.xclk_slider.setValue(16)     # Default value
        self.xclk_slider.setFixedWidth(160)
        self._update_slider_style(self.xclk_slider)

        self.xclk_value_label = QLabel(str(16))
        self.xclk_value_label.setFont(QFont("Arial", 12))
        self._update_value_label_style(self.xclk_value_label)
        self.xclk_value_label.setFixedWidth(30)
        self.xclk_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Connect slider to update value label and send debounced setting
        self.xclk_slider.valueChanged.connect(lambda val: self.xclk_value_label.setText(str(val)))
        self.xclk_slider.valueChanged.connect(lambda val: self.settings_debouncer.update_setting("xclk_freq", val))

        xclk_layout = QHBoxLayout()
        xclk_layout.setSpacing(8)
        xclk_layout.addWidget(xclk_label)
        xclk_layout.addWidget(self.xclk_slider)
        xclk_layout.addWidget(self.xclk_value_label)
        xclk_layout.addStretch()
        esp32_layout.addLayout(xclk_layout)



        # Resolution control
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

        # Slider controls
        slider_controls = [
            ("Quality:", 4, 63, 12, "quality"),
            ("Brightness:", -2, 2, 0, "brightness"),
            ("Contrast:", -2, 2, 0, "contrast"),
            ("Saturation:", -2, 2, 0, "saturation")
        ]

        self.sliders = {}
        for label_text, min_val, max_val, default_val, setting_name in slider_controls:
            slider, layout = self.create_slider_control(label_text, min_val, max_val, default_val, setting_name)
            self.sliders[setting_name] = slider
            esp32_layout.addLayout(layout)

        # Mirror controls
        mirror_layout = QHBoxLayout()
        mirror_label = QLabel("Mirror:")
        mirror_label.setFont(QFont("Arial", 12))
        self._update_control_label_style(mirror_label)
        mirror_label.setFixedWidth(80)

        self.h_mirror_btn = QPushButton("Horizontal")
        self.h_mirror_btn.setCheckable(True)
        self.h_mirror_btn.setFixedSize(100, 30)
        self.h_mirror_btn.setFont(QFont("Arial", 11))
        self.h_mirror_btn.clicked.connect(
            lambda checked: self.settings_debouncer.update_setting("h_mirror", checked)
        )
        self.h_mirror_btn.setStyleSheet(self._get_base_button_style() + self._get_yellow_checked_style())

        self.v_flip_btn = QPushButton("Vertical")
        self.v_flip_btn.setCheckable(True)
        self.v_flip_btn.setFixedSize(100, 30)
        self.v_flip_btn.setFont(QFont("Arial", 11))
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

    def _on_resolution_changed(self, index: int):
        """Handle resolution change - send immediately"""
        self.settings_debouncer.update_setting("resolution", index)
        self.settings_debouncer.force_send_now()

    def _create_actions_section(self):
        """Create camera actions section"""
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
        self.reset_btn = QPushButton("RESET TO DEFAULTS")
        self.reset_btn.setFont(QFont("Arial", 12))
        self.reset_btn.clicked.connect(self.reset_to_defaults)
        self.reset_btn.setStyleSheet(self._get_base_button_style())
        actions_layout.addWidget(self.reset_btn)

        # Toggle buttons row
        toggles_row = QHBoxLayout()
        toggles_row.setSpacing(10)

        # Stream button
        self.stream_button.setText("Start Stream")
        self.stream_button.setCheckable(True)
        self.stream_button.setChecked(False)
        self.stream_button.setMinimumHeight(40)
        self.stream_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.stream_button.setStyleSheet(self._get_base_button_style() + self._get_yellow_checked_style())
        toggles_row.addWidget(self.stream_button, stretch=1)

        # Track button
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

    def create_slider_control(self, label_text, min_val, max_val, default_val, setting_name):
        """Create a slider control with debounced updates"""
        layout = QHBoxLayout()
        layout.setSpacing(8)

        label = QLabel(label_text)
        label.setFont(QFont("Arial", 12))
        self._update_control_label_style(label)
        label.setFixedWidth(80)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(default_val)
        slider.setFixedWidth(160)
        self._update_slider_style(slider)

        value_label = QLabel(str(default_val))
        value_label.setFont(QFont("Arial", 12))
        self._update_value_label_style(value_label)
        value_label.setFixedWidth(30)
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        setattr(self, f'{setting_name}_value_label', value_label)

        # Connect slider to update value label and debounced setting
        slider.valueChanged.connect(lambda val: value_label.setText(str(val)))
        slider.valueChanged.connect(lambda val: self.settings_debouncer.update_setting(setting_name, val))

        layout.addWidget(label)
        layout.addWidget(slider)
        layout.addWidget(value_label)
        layout.addStretch()
        return slider, layout

    # Style update methods (keeping these for theme support)
    def _get_base_button_style(self) -> str:
        return theme_manager.get_button_style("default")

    def _get_yellow_checked_style(self) -> str:
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
        """

    def _get_green_checked_style(self) -> str:
        green = theme_manager.get("green")
        green_gradient = theme_manager.get("green_gradient")
        return f"""
        QPushButton:checked {{
            background: {green_gradient};
            border: 2px solid {green};
            color: black;
            font-weight: bold;
        }}
        """

    def _update_section_frame_style(self, frame):
        frame.setStyleSheet("""
            QWidget {
                border: 1px solid #555;
                border-radius: 8px;
                background-color: rgba(0, 0, 0, 0.3);
            }
        """)

    def _update_section_header_style(self, label):
        primary_color = theme_manager.get("primary_color")
        label.setStyleSheet(f"color: {primary_color}; border: none; margin-bottom: 5px;")

    def _update_control_label_style(self, label):
        label.setStyleSheet("border: none; color: white;")

    def _update_combobox_style(self, combobox):
        combobox.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
                color: white;
            }
        """)

    def _update_slider_style(self, slider):
        primary_color = theme_manager.get("primary_color")
        slider.setStyleSheet(f"""
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
        """)

    def _update_value_label_style(self, label):
        primary_color = theme_manager.get("primary_color")
        label.setStyleSheet(f"border: none; color: {primary_color};")

    def _on_theme_changed(self):
        """Handle theme changes"""
        try:
            # Update main panel styling
            self._update_panel_style()
            self._update_header_style()
            self._update_status_label_style()
            
            # Update section headers
            if hasattr(self, 'esp32_header'):
                self._update_section_header_style(self.esp32_header)
            if hasattr(self, 'actions_header'):
                self._update_section_header_style(self.actions_header)
                
            # Update all value labels (this is what's missing!)
            if hasattr(self, 'xclk_value_label'):
                self._update_value_label_style(self.xclk_value_label)
            
            # Update all slider value labels
            for setting_name, slider in getattr(self, 'sliders', {}).items():
                # Find the associated value label - they should be stored during creation
                if hasattr(self, f'{setting_name}_value_label'):
                    value_label = getattr(self, f'{setting_name}_value_label')
                    self._update_value_label_style(value_label)
            
            # Update mirror buttons to use current theme colors instead of hardcoded yellow
            if hasattr(self, 'h_mirror_btn'):
                self.h_mirror_btn.setStyleSheet(self._get_base_button_style() + self._get_yellow_checked_style())
            if hasattr(self, 'v_flip_btn'):
                self.v_flip_btn.setStyleSheet(self._get_base_button_style() + self._get_yellow_checked_style())
                
            # Update combobox styling
            if hasattr(self, 'resolution_combo'):
                self._update_combobox_style(self.resolution_combo)
                
            # Update all sliders
            if hasattr(self, 'xclk_slider'):
                self._update_slider_style(self.xclk_slider)
            for slider in getattr(self, 'sliders', {}).values():
                self._update_slider_style(slider)
                
        except Exception as e:
            self.logger.error(f"Error updating camera controls theme: {e}")

    @error_boundary
    def load_current_settings(self):
        """Load current settings from camera proxy"""
        try:
            response = requests.get(f"{self.proxy_base_url}/camera/settings", timeout=3)
            if response.status_code == 200:
                settings = response.json()
                self.current_settings = settings

                # Update UI controls
                if "resolution" in settings:
                    self.resolution_combo.setCurrentIndex(settings["resolution"])
                if "quality" in settings and "quality" in self.sliders:
                    self.sliders["quality"].setValue(settings["quality"])
                if "brightness" in settings and "brightness" in self.sliders:
                    self.sliders["brightness"].setValue(settings["brightness"])
                if "contrast" in settings and "contrast" in self.sliders:
                    self.sliders["contrast"].setValue(settings["contrast"])
                if "saturation" in settings and "saturation" in self.sliders:
                    self.sliders["saturation"].setValue(settings["saturation"])
                if "h_mirror" in settings:
                    self.h_mirror_btn.setChecked(settings["h_mirror"])
                if "xclk_freq" in settings:
                    self.xclk_slider.setValue(settings["xclk_freq"])
                if "v_flip" in settings:
                    self.v_flip_btn.setChecked(settings["v_flip"])

                self._update_status_display("Settings loaded", "#44FF44")
                self.logger.info("Loaded camera settings")
        except Exception as e:
            self._update_status_display("Failed to load settings", "#FF4444")
            self.logger.error(f"Failed to load camera settings: {e}")

    @error_boundary
    def reset_to_defaults(self):
        """Reset all settings to default values"""
        self.settings_debouncer.clear_pending()
        
        defaults = {
            "xclk_freq": 16, "resolution": 5, "quality": 12,
            "brightness": 0, "contrast": 0, "saturation": 0,
            "h_mirror": False, "v_flip": False
        }

        # Update UI controls
        self.xclk_slider.setValue(defaults["xclk_freq"])
        self.resolution_combo.setCurrentIndex(defaults["resolution"])
        self.sliders["quality"].setValue(defaults["quality"])
        self.sliders["brightness"].setValue(defaults["brightness"])
        self.sliders["contrast"].setValue(defaults["contrast"])
        self.sliders["saturation"].setValue(defaults["saturation"])
        self.h_mirror_btn.setChecked(defaults["h_mirror"])
        self.v_flip_btn.setChecked(defaults["v_flip"])

        # Send defaults immediately
        try:
            self._update_status_display("Resetting to defaults...", "#FFAA00")
            response = requests.post(f"{self.proxy_base_url}/camera/settings", json=defaults, timeout=3)
            if response.status_code == 200:
                self._update_status_display("Reset to defaults", "#44FF44")
                self.current_settings = defaults
                self.settings_debouncer.clear_pending()
                self.logger.info("Reset camera settings to defaults")
            else:
                self._update_status_display("Reset failed", "#FF4444")
                self.logger.error(f"Reset failed: HTTP {response.status_code}")
        except Exception as e:
            self._update_status_display(f"Error: {str(e)[:20]}", "#FF4444")
            self.logger.error(f"Failed to reset to defaults: {e}")

    def cleanup(self):
        """Clean up debouncer on widget destruction"""
        if hasattr(self, 'settings_debouncer'):
            if self.settings_debouncer.has_pending_changes():
                self.settings_debouncer.force_send_now()
            self.settings_debouncer.cleanup()

    def __del__(self):
        """Clean up theme manager callback and debouncer on destruction"""
        try:
            theme_manager.unregister_callback(self._on_theme_changed)
        except:
            pass
        self.cleanup()


class CameraFeedScreen(BaseScreen):
    """FIXED: Camera screen with proper image processor integration"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        theme_manager.register_callback(self._on_theme_changed)

    def _setup_screen(self):
        wave_config = config_manager.get_wave_config()

        # Wave detection state
        self.sample_buffer = deque(maxlen=wave_config["sample_duration"] * wave_config["sample_rate"])
        self.last_wave_time = 0
        self.last_sample_time = 0

        self.tracking_enabled = False
        self.streaming_enabled = False

        # Camera URLs
        camera_proxy_url = wave_config.get("camera_proxy_url", "")
        self.camera_proxy_base_url = camera_proxy_url.replace("/stream", "") if camera_proxy_url else ""

        self.logger.info(f"Camera proxy URL: {camera_proxy_url}")

        # FIXED: Use updated ImageProcessingThread with proper integration
        self.image_thread = ImageProcessingThread(camera_proxy_url)
        self.image_thread.frame_processed.connect(self.update_display)
        self.image_thread.stats_updated.connect(self.update_stats)

        # Build UI
        self.init_ui()

        # FIXED: Start processing and check initial status
        self.image_thread.start_processing()
        self.check_stream_status()

    def init_ui(self):
        # Video display
        self.video_label = QLabel()
        self.video_label.setFixedSize(640, 480)
        self._update_video_label_style()
        self.video_label.setText("Connecting to camera...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Stats display
        self.stats_label = QLabel("Stream Stats: Initializing...")
        self._update_stats_label_style()
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.stats_label.setFixedWidth(640)

        # Create control buttons
        self.setup_control_buttons()

        # Controls widget
        self.controls_widget = CameraControlsWidget(
            stream_button=self.stream_button,
            track_button=self.tracking_button
        )
        self.controls_widget.setMaximumHeight(700)

        # Layout
        self.setup_layout()

    def _update_video_label_style(self):
        grey = theme_manager.get("grey")
        self.video_label.setStyleSheet(f"""
            border: 2px solid {grey};
            padding: 2px;
            background-color: black;
            color: white;
        """)

    def _update_stats_label_style(self):
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
        """Create stream and tracking buttons"""
        self.stream_button = QPushButton("Start Stream")
        self.stream_button.setCheckable(True)
        self.stream_button.setChecked(False)
        self.stream_button.setMinimumSize(150, 40)
        self._update_stream_button_style()
        self.stream_button.toggled.connect(self.toggle_stream)

        self.tracking_button = QPushButton("Track Person")
        self.tracking_button.setCheckable(True)
        self.tracking_button.setChecked(False)
        self.tracking_button.setMinimumSize(150, 40)
        self.tracking_button.setEnabled(False)
        self._update_tracking_button_style()
        self.tracking_button.toggled.connect(self.toggle_tracking)

    def _update_stream_button_style(self):
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
        """
        self.stream_button.setStyleSheet(base_style + checked_style)

    def _update_tracking_button_style(self):
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
        """
        self.tracking_button.setStyleSheet(base_style + checked_style)

    def setup_layout(self):
        """Layout with video display left and controls right"""
        video_layout = QVBoxLayout()
        video_layout.setContentsMargins(0, 15, 0, 0)
        video_layout.addWidget(self.video_label)
        video_layout.addWidget(self.stats_label)

        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(20, 15, 0, 0)
        right_layout.setSpacing(20)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        right_layout.addWidget(self.controls_widget)
        right_layout.addStretch()

        main_layout = QHBoxLayout()
        main_layout.addSpacing(95)
        main_layout.addLayout(video_layout)
        main_layout.addLayout(right_layout)
        main_layout.addStretch()
        self.setLayout(main_layout)

    def update_stream_button_appearance(self):
        """Update stream button appearance based on state"""
        if self.streaming_enabled:
            self.stream_button.setText("Stop Stream")
            self.stream_button.setToolTip("Click to stop camera stream")
            self.stream_button.setChecked(True)
        else:
            self.stream_button.setText("Start Stream")
            self.stream_button.setToolTip("Click to start camera stream")
            self.stream_button.setChecked(False)

    def _on_theme_changed(self):
        """Handle theme changes"""
        try:
            self._update_video_label_style()
            self._update_stats_label_style()
            self._update_stream_button_style()
            self._update_tracking_button_style()
            self.logger.info(f"Camera screen updated for theme: {theme_manager.get_display_name()}")
        except Exception as e:
            self.logger.error(f"Error updating camera screen theme: {e}")

    @error_boundary
    def toggle_stream(self, checked):
        """FIXED: Toggle camera stream with proper image processor integration"""
        self.streaming_enabled = checked
        
        if self.streaming_enabled:
            self.logger.info("Starting camera stream")
            self.stats_label.setText("Stream Stats: Starting stream...")
            
            # FIXED: Tell image processor to start connecting
            if hasattr(self, 'image_thread'):
                self.image_thread.start_connecting()
            
            # Send start command to proxy
            try:
                if self.camera_proxy_base_url:
                    response = requests.post(f"{self.camera_proxy_base_url}/stream/start", timeout=3)
                    if response.status_code == 200:
                        self.logger.info("Stream start command sent to proxy")
                        self.tracking_button.setEnabled(True)
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

            # FIXED: Tell image processor to stop connecting
            if hasattr(self, 'image_thread'):
                self.image_thread.stop_connecting()

            # Send stop command to proxy
            try:
                if self.camera_proxy_base_url:
                    response = requests.post(f"{self.camera_proxy_base_url}/stream/stop", timeout=3)
                    if response.status_code == 200:
                        self.logger.info("Stream stop command sent to proxy")
                    else:
                        self.logger.warning(f"Stream stop failed: HTTP {response.status_code}")
            except Exception as e:
                self.logger.error(f"Failed to stop stream: {e}")

        self.update_stream_button_appearance()

    @error_boundary
    def check_stream_status(self):
        """Check camera proxy stream status and sync UI"""
        try:
            if not self.camera_proxy_base_url:
                return
                
            response = requests.get(f"{self.camera_proxy_base_url}/stream/status", timeout=2)
            if response.status_code == 200:
                status = response.json()
                is_streaming = status.get("streaming_enabled", False)
                is_active = status.get("stream_active", False)

                self.logger.info(f"Stream status: enabled={is_streaming}, active={is_active}")

                if is_streaming != self.streaming_enabled:
                    self.streaming_enabled = is_streaming
                    self.stream_button.setChecked(is_streaming)
                    self.update_stream_button_appearance()
                    self.tracking_button.setEnabled(is_streaming)

                if is_streaming and is_active:
                    self.stats_label.setText("Stream Stats: Stream active")
                    # FIXED: Tell image processor to start if proxy is active
                    if hasattr(self, 'image_thread'):
                        self.image_thread.start_connecting()
                else:
                    self.stats_label.setText("Stream Stats: Stream inactive")
                    
            else:
                self.logger.warning(f"Stream status check failed: HTTP {response.status_code}")
        except Exception as e:
            self.logger.error(f"Stream status check error: {e}")

    @error_boundary
    def update_display(self, processed_data):
        """FIXED: Update display with processed frame data from image processor"""
        try:
            if processed_data is None:
                self.video_label.setText("No frame data")
                return

            frame_rgb = processed_data.frame
            wave_detected = processed_data.wave_detected

            if frame_rgb is None:
                self.video_label.setText("Camera not available")
                return

            # Handle wave detection if tracking enabled
            if self.tracking_enabled and wave_detected:
                self._handle_wave_detection()

            # Convert frame to Qt pixmap and display
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

    def update_stats(self, stats_dict):
        """FIXED: Update statistics display with better formatting"""
        try:
            if isinstance(stats_dict, dict):
                fps = stats_dict.get('fps', 0)
                frame_count = stats_dict.get('frame_count', 0)
                running = stats_dict.get('running', False)
                
                if running:
                    self.stats_label.setText(f"Stream Stats: {fps:.1f} FPS, {frame_count} frames")
                else:
                    self.stats_label.setText("Stream Stats: Not running")
            else:
                self.stats_label.setText(f"Stream Stats: {stats_dict}")
        except Exception as e:
            self.logger.error(f"Stats update error: {e}")
            self.stats_label.setText("Stream Stats: Error")

    def _handle_wave_detection(self):
        """Handle wave detection with confidence buffering"""
        wave_config = config_manager.get_wave_config()
        current_time = time.time()
        
        if current_time - self.last_sample_time >= 1.0 / wave_config["sample_rate"]:
            self.sample_buffer.append(True)  # Wave detected
            self.last_sample_time = current_time

        if len(self.sample_buffer) == self.sample_buffer.maxlen:
            confidence = sum(self.sample_buffer) / len(self.sample_buffer)
            if confidence >= wave_config["confidence_threshold"]:
                if current_time - self.last_wave_time >= wave_config["stand_down_time"]:
                    self.send_websocket_message("gesture", name="wave")
                    self.last_wave_time = current_time
                    self.sample_buffer.clear()
                    self.logger.info("Wave gesture detected and sent!")

    @error_boundary
    def toggle_tracking(self, checked=None):
        """FIXED: Toggle tracking with proper image processor integration"""
        if checked is not None:
            self.tracking_enabled = checked
        else:
            self.tracking_enabled = self.tracking_button.isChecked()

        # FIXED: Tell image processor about tracking state
        if hasattr(self, 'image_thread'):
            self.image_thread.set_tracking_enabled(self.tracking_enabled)

        if self.tracking_enabled:
            self.tracking_button.setToolTip("Wave Detection: ENABLED (Click to disable)")
            self.logger.info("Wave detection ENABLED")
        else:
            self.tracking_button.setToolTip("Wave Detection: DISABLED (Click to enable)")
            self.logger.info("Wave detection DISABLED")

        self.send_websocket_message("tracking", state=self.tracking_enabled)

    def cleanup(self):
        """Cleanup camera screen resources"""
        if hasattr(self, 'image_thread'):
            self.image_thread.stop_processing()
        
        if hasattr(self, 'controls_widget'):
            self.controls_widget.cleanup()

    def __del__(self):
        """Clean up theme manager callback on destruction"""
        try:
            theme_manager.unregister_callback(self._on_theme_changed)
        except:
            pass