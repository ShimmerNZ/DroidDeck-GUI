"""
WALL-E Control System - Camera Feed Screen (Refined)
- Wider right panel (380px) to prevent button crowding
- Scoped yellow border only to the outer control panel (no yellow XCLK border)
- Mirror H/V buttons use yellow gradient when toggled (checked)
- Full yellow border wraps the entire right-side (header/settings/actions/status)
"""
import os
import time
import requests
from collections import deque

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QSlider, QSpinBox,
    QCheckBox, QWidget, QSizePolicy
)
from PyQt6.QtGui import QFont, QImage, QPixmap
from PyQt6.QtCore import Qt, QSize

from widgets.base_screen import BaseScreen
from threads.image_processor import ImageProcessingThread
from core.config_manager import config_manager
from core.utils import error_boundary
from core.logger import get_logger


# ---------- Shared theme helpers (greyscale base + variants) ----------

def _greyscale_button_css() -> str:
    """Base greyscale gradient button styling."""
    return """
    QPushButton {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #4a4a4a, stop:1 #2a2a2a);
        color: white;
        border: 1px solid #666;
        border-radius: 6px;
        padding: 6px;
        text-align: center;
        font-weight: bold;
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
    }
    """


def _checked_yellow_css() -> str:
    """Yellow gradient for checked (Start Stream ON / toggled buttons that should be yellow)."""
    return """
    QPushButton:checked {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #FFD700, stop:1 #e1a014);
        border: 2px solid #FFD700;
        color: black;
        font-weight: bold;
    }
    QPushButton:checked:hover {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #FFEA00, stop:1 #f1b024);
        border: 2px solid #FFEA00;
    }
    """


def _checked_green_css() -> str:
    """Green gradient for checked (Track Person ON)."""
    return """
    QPushButton:checked {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #44FF44, stop:1 #228B22);
        border: 2px solid #44FF44;
        color: black;
        font-weight: bold;
    }
    QPushButton:checked:hover {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #66FF66, stop:1 #2FAE2F);
        border: 2px solid #66FF66;
    }
    """


class CameraControlsWidget(QWidget):
    """
    Camera controls panel (unified side panel)
    - Yellow bordered outer wrapper (header/settings/actions/status)
    - ESP32 SETTINGS contains all camera/image controls
    - ACTIONS contains Reset + Start Stream (yellow on) + Track Person (green on)
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

        self.init_ui()
        self.load_current_settings()

    def init_ui(self):
        """Initialize the camera controls UI with consistent styling."""
        # Scope the outer panel styles using objectName, so children don't inherit the yellow border
        self.setObjectName("cameraPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(380)  # wider to prevent button crowding
        self.setStyleSheet("""
            #cameraPanel {
                background-color: #1e1e1e;
                border: 2px solid #e1a014;
                border-radius: 12px;
                color: white;
            }
        """)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 10, 15, 15)
        main_layout.setSpacing(12)

        # Header - "CAMERA SETTINGS"
        header = QLabel("CAMERA SETTINGS")
        header.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("""
            QLabel {
                border: none;
                background-color: rgba(0, 0, 0, 0.9);
                color: #e1a014;
                padding: 8px;
                border-radius: 6px;
                margin-bottom: 5px;
            }
        """)
        main_layout.addWidget(header)

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
        self.status_label.setStyleSheet("color: #AAAAAA; border: none; padding: 3px; text-align: center;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_label)

        main_layout.addStretch()
        self.setLayout(main_layout)

    def _create_esp32_section(self):
        """Create ESP32 camera settings section holding all camera settings."""
        esp32_frame = QWidget()
        esp32_frame.setObjectName("esp32Frame")
        esp32_frame.setStyleSheet("""
            #esp32Frame {
                border: 1px solid #555;
                border-radius: 8px;
                background-color: rgba(0, 0, 0, 0.3);
            }
        """)
        esp32_layout = QVBoxLayout()
        esp32_layout.setContentsMargins(12, 8, 12, 12)
        esp32_layout.setSpacing(8)

        # Section header
        esp32_header = QLabel("ESP32 SETTINGS")
        esp32_header.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        esp32_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        esp32_header.setStyleSheet("color: #e1a014; border: none; margin-bottom: 5px;")
        esp32_layout.addWidget(esp32_header)

        # XCLK Frequency
        xclk_layout = QHBoxLayout()
        xclk_label = QLabel("XCLK MHz:")
        xclk_label.setFont(QFont("Arial", 12))
        xclk_label.setStyleSheet("border: none; color: white;")
        xclk_label.setFixedWidth(80)

        self.xclk_spin = QSpinBox()
        self.xclk_spin.setRange(8, 20)
        self.xclk_spin.setValue(10)
        self.xclk_spin.setFont(QFont("Arial", 12))
        self.xclk_spin.setFixedWidth(60)
        self.xclk_spin.setStyleSheet("""
            QSpinBox {
                background-color: #2a2a2a;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
                color: white;
            }
            /* keep focus border neutral (no yellow) */
            QSpinBox:focus { border-color: #555; }
        """)

        xclk_btn = QPushButton("SET")
        xclk_btn.setFont(QFont("Arial", 11))
        xclk_btn.setFixedSize(45, 28)
        xclk_btn.clicked.connect(lambda: self.update_setting("xclk_freq", self.xclk_spin.value()))
        xclk_btn.setStyleSheet(_greyscale_button_css())

        xclk_layout.addWidget(xclk_label)
        xclk_layout.addWidget(self.xclk_spin)
        xclk_layout.addWidget(xclk_btn)
        xclk_layout.addStretch()
        esp32_layout.addLayout(xclk_layout)

        # Resolution
        res_layout = QHBoxLayout()
        res_label = QLabel("Resolution:")
        res_label.setFont(QFont("Arial", 12))
        res_label.setStyleSheet("border: none; color: white;")
        res_label.setFixedWidth(80)

        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems([
            "QQVGA(160x120)", "QCIF(176x144)", "HQVGA(240x176)", "QVGA(320x240)",
            "CIF(400x296)", "VGA(640x480)", "SVGA(800x600)", "XGA(1024x768)",
            "SXGA(1280x1024)", "UXGA(1600x1200)"
        ])
        self.resolution_combo.setCurrentIndex(5)  # VGA
        self.resolution_combo.setFont(QFont("Arial", 11))
        self.resolution_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
                color: white;
            }
            QComboBox:focus { border-color: #555; }  /* no yellow highlight */
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow { image: none; border: none; }
        """)
        self.resolution_combo.currentIndexChanged.connect(
            lambda idx: self.update_setting("resolution", idx)
        )

        res_layout.addWidget(res_label)
        res_layout.addWidget(self.resolution_combo)
        esp32_layout.addLayout(res_layout)

        # ---- Image Controls (sliders) ----
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

        # Mirror controls (H, V) with yellow when toggled
        mirror_layout = QHBoxLayout()
        mirror_label = QLabel("Mirror:")
        mirror_label.setFont(QFont("Arial", 12))
        mirror_label.setStyleSheet("border: none; color: white;")
        mirror_label.setFixedWidth(80)

        self.h_mirror_btn = QPushButton("Horizontal")
        self.h_mirror_btn.setCheckable(True)
        self.h_mirror_btn.setFixedSize(100, 30)
        self.h_mirror_btn.setFont(QFont("Arial", 11))
        self.h_mirror_btn.setToolTip("Horizontal Mirror")
        self.h_mirror_btn.clicked.connect(
            lambda checked: self.update_setting("h_mirror", checked)
        )
        self.h_mirror_btn.setStyleSheet(_greyscale_button_css() + _checked_yellow_css())

        self.v_flip_btn = QPushButton("Vertical")
        self.v_flip_btn.setCheckable(True)
        self.v_flip_btn.setFixedSize(100, 30)
        self.v_flip_btn.setFont(QFont("Arial", 11))
        self.v_flip_btn.setToolTip("Vertical Flip")
        self.v_flip_btn.clicked.connect(
            lambda checked: self.update_setting("v_flip", checked)
        )
        self.v_flip_btn.setStyleSheet(_greyscale_button_css() + _checked_yellow_css())

        mirror_layout.addWidget(mirror_label)
        mirror_layout.addWidget(self.h_mirror_btn)
        mirror_layout.addWidget(self.v_flip_btn)
        mirror_layout.addStretch()
        esp32_layout.addLayout(mirror_layout)

        esp32_frame.setLayout(esp32_layout)
        return esp32_frame

    def _create_actions_section(self):
        """Create camera actions section: Reset + Start Stream + Track Person (toggles)"""
        actions_frame = QWidget()
        actions_frame.setObjectName("actionsFrame")
        actions_frame.setStyleSheet("""
            #actionsFrame {
                border: 1px solid #555;
                border-radius: 8px;
                background-color: rgba(0, 0, 0, 0.3);
            }
        """)
        actions_layout = QVBoxLayout()
        actions_layout.setContentsMargins(12, 8, 12, 12)
        actions_layout.setSpacing(8)

        actions_header = QLabel("ACTIONS")
        actions_header.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        actions_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        actions_header.setStyleSheet("color: #e1a014; border: none; margin-bottom: 5px;")
        actions_layout.addWidget(actions_header)

        # Reset button
        reset_btn = QPushButton("🔄 RESET TO DEFAULTS")
        reset_btn.setFont(QFont("Arial", 12))
        reset_btn.clicked.connect(self.reset_to_defaults)
        reset_btn.setStyleSheet(_greyscale_button_css())
        actions_layout.addWidget(reset_btn)

        # Row for toggle buttons (now has more width; use Expanding policies to avoid crowding)
        toggles_row = QHBoxLayout()
        toggles_row.setSpacing(10)

        # Stream button (yellow when checked)
        self.stream_button.setText("Start Stream")
        self.stream_button.setCheckable(True)
        self.stream_button.setChecked(False)
        self.stream_button.setMinimumHeight(40)
        self.stream_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.stream_button.setStyleSheet(_greyscale_button_css() + _checked_yellow_css())
        toggles_row.addWidget(self.stream_button, stretch=1)

        # Track button (green when checked, disabled until streaming)
        self.track_button.setText("Track Person")
        self.track_button.setCheckable(True)
        self.track_button.setChecked(False)
        self.track_button.setEnabled(False)
        self.track_button.setMinimumHeight(40)
        self.track_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.track_button.setStyleSheet(_greyscale_button_css() + _checked_green_css())
        toggles_row.addWidget(self.track_button, stretch=1)

        actions_layout.addLayout(toggles_row)
        actions_frame.setLayout(actions_layout)
        return actions_frame

    def create_slider_control(self, label_text, min_val, max_val, default_val, setting_name):
        """Create a slider control with consistent styling."""
        layout = QHBoxLayout()
        layout.setSpacing(8)

        label = QLabel(label_text)
        label.setFont(QFont("Arial", 12))
        label.setStyleSheet("border: none; color: white;")
        label.setFixedWidth(80)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(default_val)
        slider.setFixedWidth(160)  # a bit wider with the new panel width
        slider.setStyleSheet("""
            QSlider { border: none; background: transparent; }
            QSlider::groove:horizontal {
                border: 1px solid #555;
                height: 6px;
                background: #333;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #e1a014;
                border: 1px solid #e1a014;
                width: 16px; height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #f1b024;
                border-color: #f1b024;
            }
        """)

        value_label = QLabel(str(default_val))
        value_label.setFont(QFont("Arial", 12))
        value_label.setStyleSheet("border: none; color: #e1a014;")
        value_label.setFixedWidth(30)
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        slider.valueChanged.connect(lambda val: value_label.setText(str(val)))
        slider.sliderReleased.connect(lambda: self.update_setting(setting_name, slider.value()))

        layout.addWidget(label)
        layout.addWidget(slider)
        layout.addWidget(value_label)
        layout.addStretch()
        return slider, layout

    @error_boundary
    def load_current_settings(self):
        """Load current settings from camera proxy."""
        try:
            response = requests.get(f"{self.proxy_base_url}/camera/settings", timeout=3)
            if response.status_code == 200:
                settings = response.json()
                self.current_settings = settings

                # Update UI
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

                self.status_label.setText("Settings loaded")
                self.status_label.setStyleSheet("color: #44FF44; border: none; padding: 3px; text-align: center;")
                self.logger.info("Loaded camera settings")
        except Exception as e:
            self.status_label.setText("Failed to load settings")
            self.status_label.setStyleSheet("color: #FF4444; border: none; padding: 3px; text-align: center;")
            self.logger.error(f"Failed to load camera settings: {e}")

    @error_boundary
    def update_setting(self, setting_name, value):
        """Update a camera setting via the proxy."""
        try:
            if isinstance(value, bool):
                value = "true" if value else "false"
            response = requests.post(
                f"{self.proxy_base_url}/camera/setting/{setting_name}",
                params={"value": value},
                timeout=3
            )
            if response.status_code == 200:
                self.status_label.setText(f"Updated {setting_name}")
                self.status_label.setStyleSheet("color: #44FF44; border: none; padding: 3px; text-align: center;")
                self.current_settings[setting_name] = value
                self.logger.info(f"Updated {setting_name} = {value}")
            else:
                self.status_label.setText(f"Failed to update {setting_name}")
                self.status_label.setStyleSheet("color: #FF4444; border: none; padding: 3px; text-align: center;")
        except Exception as e:
            self.status_label.setText(f"Error: {str(e)[:30]}")
            self.status_label.setStyleSheet("color: #FF4444; border: none; padding: 3px; text-align: center;")
            self.logger.error(f"Failed to update {setting_name}: {e}")

    @error_boundary
    def reset_to_defaults(self):
        """Reset all settings to default values."""
        defaults = {
            "xclk_freq": 10, "resolution": 5, "quality": 12,
            "brightness": 0, "contrast": 0, "saturation": 0,
            "h_mirror": False, "v_flip": False
        }

        # Update UI
        self.xclk_spin.setValue(defaults["xclk_freq"])
        self.resolution_combo.setCurrentIndex(defaults["resolution"])
        self.quality_slider.setValue(defaults["quality"])
        self.brightness_slider.setValue(defaults["brightness"])
        self.contrast_slider.setValue(defaults["contrast"])
        self.saturation_slider.setValue(defaults["saturation"])
        self.h_mirror_btn.setChecked(defaults["h_mirror"])
        self.v_flip_btn.setChecked(defaults["v_flip"])

        # Send to camera
        try:
            response = requests.post(f"{self.proxy_base_url}/camera/settings", json=defaults, timeout=3)
            if response.status_code == 200:
                self.status_label.setText("Reset to defaults")
                self.status_label.setStyleSheet("color: #44FF44; border: none; padding: 3px; text-align: center;")
                self.current_settings = defaults
            else:
                self.status_label.setText("Failed to reset")
                self.status_label.setStyleSheet("color: #FF4444; border: none; padding: 3px; text-align: center;")
        except Exception as e:
            self.status_label.setText(f"Error: {str(e)[:30]}")
            self.status_label.setStyleSheet("color: #FF4444; border: none; padding: 3px; text-align: center;")
            self.logger.error(f"Failed to reset to defaults: {e}")


class CameraFeedScreen(BaseScreen):
    """Live camera stream display with tracking and unified controls."""

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
        self.video_label.setStyleSheet("""
            border: 2px solid #555;
            padding: 2px;
            background-color: black;
        """)

        # Stats display
        self.stats_label = QLabel("Stream Stats: Initializing...")
        self.stats_label.setStyleSheet("""
            border: 1px solid #555;
            border-radius: 4px;
            padding: 1px;
            background-color: black;
            color: #aaa;
        """)
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

    def setup_control_buttons(self):
        """Create stream and tracking buttons with consistent styling (no icons)."""
        # Stream toggle
        self.stream_button = QPushButton("Start Stream")
        self.stream_button.setCheckable(True)
        self.stream_button.setChecked(False)
        self.stream_button.setMinimumSize(150, 40)
        self.stream_button.setStyleSheet(_greyscale_button_css() + _checked_yellow_css())
        self.stream_button.toggled.connect(self.toggle_stream)

        # Tracking toggle (disabled until stream is active)
        self.tracking_button = QPushButton("Track Person")
        self.tracking_button.setCheckable(True)
        self.tracking_button.setChecked(False)
        self.tracking_button.setMinimumSize(150, 40)
        self.tracking_button.setToolTip("Toggle Wave Detection / Person Tracking")
        self.tracking_button.setEnabled(False)
        self.tracking_button.setStyleSheet(_greyscale_button_css() + _checked_green_css())
        self.tracking_button.toggled.connect(self.toggle_tracking)

        self.logger.info("Camera control buttons initialized (styled, no icons)")

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
            frame_rgb = processed_data['frame']
            wave_detected = processed_data['wave_detected']

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
        self.stop_camera_thread()
