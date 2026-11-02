#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - Camera Feed Screen
Video display, ESP32 camera settings, stream control, and gesture detection.
All HTTP requests to the camera proxy run asynchronously so an unreachable
proxy can never freeze the GUI.
"""
import os
import time
from collections import deque
from typing import Dict, Any, Callable, List, Optional, Tuple

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QSlider, QSpinBox,
    QCheckBox, QWidget, QSizePolicy, QFrame
)
from PyQt6.QtGui import QFont, QImage, QPixmap, QColor
from PyQt6.QtCore import Qt, QSize, QTimer, QPoint, pyqtSignal

from widgets.base_screen import BaseScreen
from threads.image_processor import ImageProcessingThread
from core.config_manager import config_manager
from core.theme_manager import theme_manager
from core.http_client import get_http_client
from core.utils import error_boundary
from core.logger import get_logger
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

# Minimum seconds between people updates sent to the backend (10 Hz)
PEOPLE_SEND_INTERVAL = 0.1

# Card layout - matches the Health screen card style
CARD_OBJECT_NAME = "camera_card"
CARD_GAP = 12
VIDEO_WIDTH = 640
VIDEO_HEIGHT = 480
VIDEO_CARD_PADDING = 6
VIDEO_HEADER_HEIGHT = 18
CONTROLS_COLUMN_WIDTH = 397
STREAM_CARD_HEIGHT = 90
ESP32_CARD_HEIGHT = 414
SLIDER_ROW_HEIGHT = 36

# Fixed colours shared by every theme
LABEL_GREY = "#9e9e9e"
TEXT_SOFT = "#bdbdbd"
TILE_BG = "#202020"
MONO_FAMILY = "Consolas"


def px_font(pixel_size: int, bold: bool = False, spacing: float = 0.0,
            family: str = "Arial") -> QFont:
    """Font sized in pixels so the layout matches the mockup"""
    font = QFont(family)
    if family == MONO_FAMILY:
        font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPixelSize(pixel_size)
    font.setBold(bold)
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return font


def card_style() -> str:
    """Card frame: panel background with the theme colour as a soft border"""
    primary = QColor(theme_manager.get("primary_color"))
    panel_bg = theme_manager.get("panel_bg")
    border = f"rgba({primary.red()}, {primary.green()}, {primary.blue()}, 0.45)"
    return f"""
        QFrame#{CARD_OBJECT_NAME} {{
            background-color: {panel_bg};
            border: 1px solid {border};
            border-radius: 10px;
        }}
        QLabel {{
            border: none;
            background: transparent;
        }}
    """


def button_style(checked_fill: Optional[str] = None) -> str:
    """Button matching the Health screen buttons; checkable ones fill when on"""
    primary = theme_manager.get("primary_color")
    style = f"""
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #4a4a4a, stop:1 #2a2a2a);
            color: white;
            border: 1px solid #666;
            border-radius: 8px;
            padding: 4px;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #5a5a5a, stop:1 #3a3a3a);
            border-color: {primary};
        }}
        QPushButton:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #3a3a3a, stop:1 #1a1a1a);
            border-color: {primary};
        }}
        QPushButton:disabled {{
            background: #333;
            color: #666;
            border-color: #444;
        }}
    """
    if checked_fill:
        style += f"""
        QPushButton:checked {{
            background: {checked_fill};
            border: 1px solid {checked_fill};
            color: #111111;
        }}
        """
    return style

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
        """Send all pending settings as a batch request (asynchronous)"""
        if not self.pending_settings:
            return
        
        settings_to_send = self.pending_settings.copy()
        self.pending_settings.clear()
        
        self.logger.info(f"Sending batched settings: {list(settings_to_send.keys())}")
        
        if self.status_callback:
            self.status_callback("Updating settings...", "#0088FF")  # Blue

        url = f"{self.proxy_base_url}/camera/settings"
        get_http_client().post_json(url, settings_to_send,
                                    self._on_settings_response, timeout_ms=10000)

    def _on_settings_response(self, response):
        """Handle the batched settings response on the GUI thread"""
        if response.ok and response.json:
            message = response.json.get("message", "Settings updated successfully")
            if self.status_callback:
                self.status_callback(message, "#00AA00")  # Green
            self.logger.info(f"✅ {message}")
        else:
            if response.json and "message" in response.json:
                error_message = response.json["message"]
            elif response.error:
                error_message = response.error
            else:
                error_message = f"HTTP {response.status}"

            if self.status_callback:
                self.status_callback(f"Update failed: {error_message}", "#FF0000")
            self.logger.error(f"❌ Settings update failed: {error_message}")
    
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


class ClickableVideoLabel(QLabel):
    """QLabel that reports where it was clicked, in its own local pixel
    coordinates. Used to let the person tap a tracked person's box in the
    camera view to manually select who the robot should focus on."""

    clicked = pyqtSignal(QPoint)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(event.position().toPoint())
        super().mousePressEvent(event)


class CameraControlsWidget(QWidget):
    """Camera controls panel with ESP32 settings and actions"""

    def __init__(self, stream_button: QPushButton, track_button: QPushButton, parent=None):
        super().__init__(parent)
        self.logger = get_logger("camera")
        self.initializing = True
        wave_config = config_manager.get_wave_config()
        raw_url = wave_config.get("camera_proxy_url", "http://10.1.1.230:8081")
        self.proxy_base_url = raw_url.replace("/stream", "")
        self.current_settings = {}

        # External buttons (wired by parent)
        self.stream_button = stream_button
        self.track_button = track_button

        # Setting name labels, kept for theme updates
        self._control_labels = []

        # Initialize debouncer
        self.settings_debouncer = CameraSettingsDebouncer(
            proxy_base_url=self.proxy_base_url,
            delay_ms=500
        )
        self.settings_debouncer.set_status_callback(self._update_status_display)

        # Register for theme change notifications
        theme_manager.register_callback(self._on_theme_changed)

        self.init_ui()
        self.initializing = False
        # Load settings asynchronously; the ESP32 sync is chained from the
        # load callback so it always runs against the values just loaded
        self.load_current_settings()

    def _update_status_display(self, message: str, color: str):
        """Update status display with color"""
        if hasattr(self, 'status_label'):
            self.status_label.setText(message)
            self.status_label.setStyleSheet(
                f"color: {color}; border: none; background: transparent;"
            )

    def init_ui(self):
        """Initialize the camera controls UI: stream card and ESP32 settings card"""
        self.setFixedWidth(CONTROLS_COLUMN_WIDTH)
        self.setStyleSheet("background: transparent;")

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(CARD_GAP)

        main_layout.addWidget(self._create_actions_section())
        main_layout.addWidget(self._create_esp32_section())
        main_layout.addStretch()
        self.setLayout(main_layout)

        self._update_panel_style()

    def _update_panel_style(self):
        """Update card style based on current theme"""
        for card in (getattr(self, 'stream_card', None), getattr(self, 'esp32_card', None)):
            if card is not None:
                card.setStyleSheet(card_style())

    def _make_card(self, title: str, height: int):
        """Titled card; returns (card, layout, header_row, title_label)"""
        card = QFrame()
        card.setObjectName(CARD_OBJECT_NAME)
        card.setFixedHeight(height)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)
        title_label = QLabel(title)
        title_label.setFont(px_font(14, bold=True, spacing=1.5))
        self._update_section_header_style(title_label)
        header_row.addWidget(title_label)
        layout.addLayout(header_row)
        return card, layout, header_row, title_label

    def _create_esp32_section(self):
        """Create ESP32 camera settings card"""
        card, esp32_layout, _, self.esp32_header = self._make_card("ESP32 CAMERA", ESP32_CARD_HEIGHT)
        self.esp32_card = card

        # Resolution control
        res_layout = QHBoxLayout()
        res_layout.setSpacing(10)
        res_label = self._make_control_label("Resolution")

        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems([
            "QQVGA(160x120)", "QCIF(176x144)", "HQVGA(240x176)", "QVGA(320x240)",
            "CIF(400x296)", "VGA(640x480)", "SVGA(800x600)", "XGA(1024x768)",
            "SXGA(1280x1024)", "UXGA(1600x1200)"
        ])
        self.resolution_combo.setCurrentIndex(5)  # VGA
        self.resolution_combo.setFont(px_font(14))
        self.resolution_combo.setFixedHeight(36)
        self._update_combobox_style(self.resolution_combo)
        self.resolution_combo.currentIndexChanged.connect(self._on_resolution_changed)

        res_layout.addWidget(res_label)
        res_layout.addWidget(self.resolution_combo, 1)
        res_row = QWidget()
        res_row.setFixedHeight(40)
        res_row.setLayout(res_layout)
        res_layout.setContentsMargins(0, 0, 0, 0)
        esp32_layout.addWidget(res_row)

        # X CLK slider keeps its own attribute names for existing callers
        self.xclk_slider, xclk_layout = self.create_slider_control("X CLK", 10, 20, 16, "xclk_freq")
        self.xclk_value_label = getattr(self, 'xclk_freq_value_label')
        esp32_layout.addWidget(self._wrap_row(xclk_layout, SLIDER_ROW_HEIGHT))

        # Slider controls
        slider_controls = [
            ("Quality", 4, 63, 12, "quality"),
            ("Brightness", -2, 2, 0, "brightness"),
            ("Contrast", -2, 2, 0, "contrast"),
            ("Saturation", -2, 2, 0, "saturation")
        ]

        self.sliders = {}
        for label_text, min_val, max_val, default_val, setting_name in slider_controls:
            slider, layout = self.create_slider_control(label_text, min_val, max_val, default_val, setting_name)
            self.sliders[setting_name] = slider
            esp32_layout.addWidget(self._wrap_row(layout, SLIDER_ROW_HEIGHT))

        # Mirror controls
        mirror_layout = QHBoxLayout()
        mirror_layout.setSpacing(10)
        mirror_label = self._make_control_label("Mirror")

        self.h_mirror_btn = QPushButton("Horizontal")
        self.h_mirror_btn.setCheckable(True)
        self.h_mirror_btn.setFixedHeight(36)
        self.h_mirror_btn.setFont(px_font(14, bold=True))
        self.h_mirror_btn.clicked.connect(
            lambda checked: self.settings_debouncer.update_setting("h_mirror", checked)
        )
        self.h_mirror_btn.setStyleSheet(button_style(theme_manager.get("primary_color")))

        self.v_flip_btn = QPushButton("Vertical")
        self.v_flip_btn.setCheckable(True)
        self.v_flip_btn.setFixedHeight(36)
        self.v_flip_btn.setFont(px_font(14, bold=True))
        self.v_flip_btn.clicked.connect(
            lambda checked: self.settings_debouncer.update_setting("v_flip", checked)
        )
        self.v_flip_btn.setStyleSheet(button_style(theme_manager.get("primary_color")))

        mirror_layout.addWidget(mirror_label)
        mirror_layout.addWidget(self.h_mirror_btn, 1)
        mirror_layout.addWidget(self.v_flip_btn, 1)
        esp32_layout.addWidget(self._wrap_row(mirror_layout, 40))

        esp32_layout.addStretch(1)

        # Reset button
        self.reset_btn = QPushButton("RESET TO DEFAULTS")
        self.reset_btn.setFont(px_font(14, bold=True))
        self.reset_btn.setFixedHeight(44)
        self.reset_btn.clicked.connect(self.reset_to_defaults)
        self.reset_btn.setStyleSheet(button_style())
        esp32_layout.addWidget(self.reset_btn)

        return card

    def _wrap_row(self, layout, height: int) -> QWidget:
        """Put a row layout in a fixed-height transparent widget"""
        layout.setContentsMargins(0, 0, 0, 0)
        row = QWidget()
        row.setFixedHeight(height)
        row.setStyleSheet("background: transparent;")
        row.setLayout(layout)
        return row

    def _make_control_label(self, text: str) -> QLabel:
        """Fixed-width setting name label"""
        label = QLabel(text)
        label.setFont(px_font(14))
        label.setFixedWidth(96)
        self._update_control_label_style(label)
        self._control_labels.append(label)
        return label

    def _handle_setting_change(self, setting_name, value):
        """Handle setting changes, but only if not initializing"""
        if not self.initializing:
            self.settings_debouncer.update_setting(setting_name, value)

    def _on_resolution_changed(self, index: int):
        """Handle resolution change - send immediately"""
        if not self.initializing: 
            self.settings_debouncer.update_setting("resolution", index)
            self.settings_debouncer.force_send_now()

    def _create_actions_section(self):
        """Create the stream card: status message plus stream and tracking toggles"""
        card, actions_layout, header_row, self.actions_header = self._make_card("STREAM", STREAM_CARD_HEIGHT)
        self.stream_card = card

        # Status message sits in the card header
        self.status_label = QLabel("Ready")
        self.status_label.setFont(px_font(13))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._update_status_label_style()
        header_row.addWidget(self.status_label, 1)

        # Toggle buttons row
        toggles_row = QHBoxLayout()
        toggles_row.setSpacing(10)

        # Stream button
        self.stream_button.setText("Start Stream")
        self.stream_button.setCheckable(True)
        self.stream_button.setChecked(False)
        self.stream_button.setFixedHeight(44)
        self.stream_button.setFont(px_font(16, bold=True))
        self.stream_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.stream_button.setStyleSheet(button_style(theme_manager.get("primary_color")))
        toggles_row.addWidget(self.stream_button, stretch=1)

        # Track button
        self.track_button.setText("Track Person")
        self.track_button.setCheckable(True)
        self.track_button.setChecked(False)
        self.track_button.setEnabled(False)
        self.track_button.setFixedHeight(44)
        self.track_button.setFont(px_font(16, bold=True))
        self.track_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.track_button.setStyleSheet(button_style(theme_manager.get("green")))
        toggles_row.addWidget(self.track_button, stretch=1)

        actions_layout.addLayout(toggles_row)
        return card

    def create_slider_control(self, label_text, min_val, max_val, default_val, setting_name):
        """Create a slider control with debounced updates"""
        layout = QHBoxLayout()
        layout.setSpacing(10)

        label = self._make_control_label(label_text)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(default_val)
        slider.setFixedHeight(24)
        self._update_slider_style(slider)

        value_label = QLabel(str(default_val))
        value_label.setFont(px_font(14, family=MONO_FAMILY))
        self._update_value_label_style(value_label)
        value_label.setFixedSize(40, 28)
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        setattr(self, f'{setting_name}_value_label', value_label)

        # Connect slider to update value label and debounced setting
        slider.valueChanged.connect(lambda val: value_label.setText(str(val)))
        slider.valueChanged.connect(lambda val: self._handle_setting_change(setting_name, val)) 
        
        layout.addWidget(label)
        layout.addWidget(slider, 1)
        layout.addWidget(value_label)
        return slider, layout

    def _update_section_header_style(self, label):
        primary_color = theme_manager.get("primary_color")
        label.setStyleSheet(f"color: {primary_color}; border: none; background: transparent;")

    def _update_status_label_style(self):
        """Update status label style based on current theme"""
        self.status_label.setStyleSheet(f"color: {LABEL_GREY}; border: none; background: transparent;")

    def _update_control_label_style(self, label):
        label.setStyleSheet(f"border: none; background: transparent; color: {TEXT_SOFT};")

    def _update_combobox_style(self, combobox):
        primary_color = theme_manager.get("primary_color")
        combobox.setStyleSheet(f"""
            QComboBox {{
                background-color: {TILE_BG};
                border: 1px solid #555;
                border-radius: 6px;
                padding: 0px 8px;
                color: white;
            }}
            QComboBox:focus {{
                border-color: {primary_color};
            }}
            QComboBox QAbstractItemView {{
                background-color: {TILE_BG};
                color: white;
                selection-background-color: {primary_color};
                selection-color: black;
                border: 1px solid #555;
            }}
        """)

    def _update_slider_style(self, slider):
        primary_color = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        panel_bg = theme_manager.get("panel_bg")
        slider.setStyleSheet(f"""
            QSlider {{
                background: transparent;
            }}
            QSlider::groove:horizontal {{
                border: none;
                height: 6px;
                background: #2c2c2c;
                border-radius: 3px;
            }}
            QSlider::sub-page:horizontal {{
                background: {primary_color};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {primary_light};
                border: 2px solid {panel_bg};
                width: 14px; height: 14px;
                margin: -6px 0;
                border-radius: 9px;
            }}
        """)

    def _update_value_label_style(self, label):
        label.setStyleSheet(
            f"border: none; border-radius: 6px; background-color: {TILE_BG}; color: white;"
        )

    def _on_theme_changed(self):
        """Handle theme changes"""
        try:
            self._update_panel_style()
            self._update_status_label_style()

            # Update card titles
            if hasattr(self, 'esp32_header'):
                self._update_section_header_style(self.esp32_header)
            if hasattr(self, 'actions_header'):
                self._update_section_header_style(self.actions_header)

            # Update value labels
            if hasattr(self, 'xclk_value_label'):
                self._update_value_label_style(self.xclk_value_label)
            for setting_name in getattr(self, 'sliders', {}):
                if hasattr(self, f'{setting_name}_value_label'):
                    self._update_value_label_style(getattr(self, f'{setting_name}_value_label'))

            # Update buttons
            primary_color = theme_manager.get("primary_color")
            if hasattr(self, 'h_mirror_btn'):
                self.h_mirror_btn.setStyleSheet(button_style(primary_color))
            if hasattr(self, 'v_flip_btn'):
                self.v_flip_btn.setStyleSheet(button_style(primary_color))
            if hasattr(self, 'reset_btn'):
                self.reset_btn.setStyleSheet(button_style())

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
        """Load current settings from camera proxy (asynchronous)"""
        get_http_client().get(f"{self.proxy_base_url}/camera/settings",
                              self._on_settings_loaded, timeout_ms=3000, owner=self)

    def _on_settings_loaded(self, response):
        """Apply loaded settings to the UI, then sync them back to the ESP32"""
        if not response.ok or response.json is None:
            self._update_status_display("Failed to load settings", "#FF4444")
            self.logger.error(f"Failed to load camera settings: {response.error or response.status}")
            return

        settings = response.json
        self.current_settings = settings

        # Guard so applying loaded values doesn't bounce back through the
        # debouncer as user changes
        self.initializing = True
        try:
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
        finally:
            self.initializing = False

        self._update_status_display("Settings loaded", "#44FF44")
        self.logger.info("Loaded camera settings")

        self._sync_loaded_settings_to_esp32()

    def _sync_loaded_settings_to_esp32(self):
        """
        After loading settings from the proxy, send them back to the ESP32 so
        both ends hold the same values (asynchronous).
        """
        if not self.current_settings:
            self.logger.warning("No current settings to sync to ESP32")
            return

        self._update_status_display("Syncing settings to ESP32...", "#0088FF")  # Blue

        url = f"{self.proxy_base_url}/camera/settings"
        get_http_client().post_json(url, self.current_settings,
                                    self._on_sync_response, timeout_ms=5000, owner=self)

    def _on_sync_response(self, response):
        """Handle the ESP32 sync response"""
        if response.ok and response.json:
            message = response.json.get("message", "Settings synchronized")
            self._update_status_display(message, "#00AA00")  # Green
            self.logger.info(f"Settings synchronized with ESP32: {list(self.current_settings.keys())}")
        else:
            if response.json and "message" in response.json:
                error_message = response.json["message"]
            elif response.error:
                error_message = response.error
            else:
                error_message = f"HTTP {response.status}"

            self._update_status_display(f"Sync failed: {error_message[:30]}", "#FF0000")
            self.logger.error(f"Settings sync failed: {error_message}")

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

        # Send defaults immediately (asynchronous)
        self._update_status_display("Resetting to defaults...", "#FFAA00")

        def _on_reset_response(response):
            if response.ok:
                self._update_status_display("Reset to defaults", "#44FF44")
                self.current_settings = defaults
                self.settings_debouncer.clear_pending()
                self.logger.info("Reset camera settings to defaults")
            else:
                self._update_status_display("Reset failed", "#FF4444")
                self.logger.error(f"Reset failed: {response.error or f'HTTP {response.status}'}")

        get_http_client().post_json(f"{self.proxy_base_url}/camera/settings", defaults,
                                    _on_reset_response, timeout_ms=3000, owner=self)

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
    """Camera screen with live video display, proxy control, and gesture detection"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        theme_manager.register_callback(self._on_theme_changed)

    def _setup_screen(self):
        wave_config = config_manager.get_wave_config()

        # Wave detection state
        self.sample_buffers = {
            'left_wave': deque(maxlen=wave_config["sample_duration"] * wave_config["sample_rate"]),
            'right_wave': deque(maxlen=wave_config["sample_duration"] * wave_config["sample_rate"]),
            'hands_up': deque(maxlen=wave_config["sample_duration"] * wave_config["sample_rate"])
        }
        self.last_gesture_time = 0
        self.last_sample_time = 0
        self.last_people_send_time = 0.0

        self.tracking_enabled = False
        self.streaming_enabled = False

        # Most recent tracked-people list and the frame size it was measured
        # against, kept so a click on the video can be mapped back to a
        # person's box and sent to the backend as a manual selection
        self._last_people: List[Dict[str, float]] = []
        self._last_frame_size: Optional[Tuple[int, int]] = None

        # Camera URLs
        camera_proxy_url = wave_config.get("camera_proxy_url", "")
        self.camera_proxy_base_url = camera_proxy_url.replace("/stream", "") if camera_proxy_url else ""

        self.logger.info(f"Camera proxy URL: {camera_proxy_url}")

        # Image processing runs in its own thread; frames arrive via signal
        self.image_thread = ImageProcessingThread(camera_proxy_url)
        self.image_thread.frame_processed.connect(self.update_display)
        self.image_thread.stats_updated.connect(self.update_stats)

        # The backend reports which person it is focused on so the overlay can highlight them
        register_handler = getattr(self.websocket, "register_handler", None)
        if register_handler:
            register_handler("attention_state", self._on_attention_state)

        # Build UI
        self.init_ui()

        # Start processing and check initial status
        self.image_thread.start_processing()
        self.check_stream_status()

        # Re-check whenever the backend connection is (re)established - a
        # backend restart resets the camera proxy's own state (stream
        # stopped, fresh process), so the cached button state here would
        # otherwise go stale until manually toggled.
        if self.websocket is not None:
            self.websocket.connected.connect(self.check_stream_status)

    def init_ui(self):
        # Video display
        self.video_label = ClickableVideoLabel()
        self.video_label.setFixedSize(VIDEO_WIDTH, VIDEO_HEIGHT)
        self.video_label.setFont(px_font(16))
        self._update_video_label_style()
        self.video_label.setText("Connecting to camera...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.clicked.connect(self._on_video_clicked)

        # Stats display, shown in the live view card header
        self.stats_label = QLabel("Initializing...")
        self.stats_label.setFont(px_font(13))
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._stats_active = False
        self._update_stats_label_style()

        # Create control buttons
        self.setup_control_buttons()

        # Controls widget
        self.controls_widget = CameraControlsWidget(
            stream_button=self.stream_button,
            track_button=self.tracking_button
        )

        # Layout
        self.setup_layout()

    def _update_video_label_style(self):
        self.video_label.setStyleSheet("""
            border: none;
            border-radius: 4px;
            background-color: black;
            color: #6f6f6f;
        """)

    def _update_stats_label_style(self):
        color = theme_manager.get("green") if self._stats_active else LABEL_GREY
        self.stats_label.setStyleSheet(f"color: {color}; border: none; background: transparent;")

    def _set_stats_text(self, text: str, active: bool = False):
        """Set the stream stats text; active stats show in green"""
        self.stats_label.setText(text)
        if active != self._stats_active:
            self._stats_active = active
            self._update_stats_label_style()

    def setup_control_buttons(self):
        """Create stream and tracking buttons"""
        self.stream_button = QPushButton("Start Stream")
        self.stream_button.setCheckable(True)
        self.stream_button.setChecked(False)
        self._update_stream_button_style()
        self.stream_button.toggled.connect(self.toggle_stream)

        self.tracking_button = QPushButton("Track Person")
        self.tracking_button.setCheckable(True)
        self.tracking_button.setChecked(False)
        self.tracking_button.setEnabled(False)
        self._update_tracking_button_style()
        self.tracking_button.toggled.connect(self.toggle_tracking)

    def _update_stream_button_style(self):
        self.stream_button.setStyleSheet(button_style(theme_manager.get("primary_color")))

    def _update_tracking_button_style(self):
        self.tracking_button.setStyleSheet(button_style(theme_manager.get("green")))

    def get_gesture_detection_status(self):
        """Get current status of gesture detection buffers (for debugging)"""
        if not hasattr(self, 'sample_buffers'):
            return "Gesture detection not initialized"
        
        status = {}
        wave_config = config_manager.get_wave_config()
        current_time = time.time()
        
        # Shared stand-down status
        time_since_last = current_time - self.last_gesture_time
        in_standdown = time_since_last < wave_config['stand_down_time']
        standdown_remaining = max(0, wave_config['stand_down_time'] - time_since_last)
        
        status['shared_standdown'] = {
            'active': in_standdown,
            'time_since_last_gesture': f"{time_since_last:.1f}s",
            'remaining_time': f"{standdown_remaining:.1f}s" if in_standdown else "Ready",
            'standdown_period': f"{wave_config['stand_down_time']}s"
        }
        
        # Individual gesture buffer status
        status['gestures'] = {}
        for gesture_type, buffer in self.sample_buffers.items():
            if len(buffer) > 0:
                confidence = sum(buffer) / len(buffer)
                status['gestures'][gesture_type] = {
                    'buffer_length': len(buffer),
                    'confidence': f"{confidence:.2%}",
                    'threshold': f"{wave_config['confidence_threshold']:.2%}",
                    'ready_to_trigger': confidence >= wave_config['confidence_threshold'] and not in_standdown
                }
            else:
                status['gestures'][gesture_type] = {
                    'buffer_length': 0, 
                    'confidence': '0%',
                    'ready_to_trigger': False
                }
        
        return status

    def setup_layout(self):
        """Live view card on the left, stream and settings cards on the right"""
        self.video_card = QFrame()
        self.video_card.setObjectName(CARD_OBJECT_NAME)
        self.video_card.setFixedSize(VIDEO_WIDTH + 2 * VIDEO_CARD_PADDING,
                                     VIDEO_HEIGHT + VIDEO_HEADER_HEIGHT + 3 * VIDEO_CARD_PADDING)
        self.video_card.setStyleSheet(card_style())

        video_layout = QVBoxLayout(self.video_card)
        video_layout.setContentsMargins(VIDEO_CARD_PADDING, VIDEO_CARD_PADDING,
                                        VIDEO_CARD_PADDING, VIDEO_CARD_PADDING)
        video_layout.setSpacing(VIDEO_CARD_PADDING)

        header = QHBoxLayout()
        header.setContentsMargins(6, 0, 6, 0)
        self.video_title = QLabel("LIVE VIEW")
        self.video_title.setFont(px_font(14, bold=True, spacing=1.5))
        self._update_video_title_style()
        header.addWidget(self.video_title)
        header.addStretch(1)
        header.addWidget(self.stats_label)
        header_widget = QWidget()
        header_widget.setFixedHeight(VIDEO_HEADER_HEIGHT)
        header_widget.setStyleSheet("background: transparent;")
        header_widget.setLayout(header)

        video_layout.addWidget(header_widget)
        video_layout.addWidget(self.video_label)

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(105, 31, 12, 6)
        main_layout.setSpacing(CARD_GAP)
        main_layout.addWidget(self.video_card, 0, Qt.AlignmentFlag.AlignTop)
        main_layout.addWidget(self.controls_widget, 0, Qt.AlignmentFlag.AlignTop)
        main_layout.addStretch()
        self.setLayout(main_layout)

    def _update_video_title_style(self):
        primary_color = theme_manager.get("primary_color")
        self.video_title.setStyleSheet(f"color: {primary_color}; border: none; background: transparent;")

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
            if hasattr(self, 'video_card'):
                self.video_card.setStyleSheet(card_style())
                self._update_video_title_style()
            self._update_stream_button_style()
            self._update_tracking_button_style()
            self.logger.info(f"Camera screen updated for theme: {theme_manager.get_display_name()}")
        except Exception as e:
            self.logger.error(f"Error updating camera screen theme: {e}")

    @error_boundary
    def toggle_stream(self, checked):
        """Toggle camera stream and notify the proxy (asynchronous)"""
        self.streaming_enabled = checked
        
        if self.streaming_enabled:
            self.logger.info("Starting camera stream")
            self._set_stats_text("Starting stream...")
            
            # Tell image processor to start connecting
            if hasattr(self, 'image_thread'):
                self.image_thread.start_connecting()
            
            # Send start command to proxy
            if self.camera_proxy_base_url:
                def _on_start_response(response):
                    if response.ok:
                        self.logger.info("Stream start command sent to proxy")
                        self.tracking_button.setEnabled(True)
                    else:
                        self.logger.warning(f"Stream start failed: {response.error or f'HTTP {response.status}'}")
                        self._set_stats_text("Stream error: proxy unreachable")

                get_http_client().post(f"{self.camera_proxy_base_url}/stream/start",
                                       _on_start_response, timeout_ms=3000, owner=self)
        else:
            self.logger.info("Stopping camera stream")
            self._set_stats_text("Stopping stream...")

            # Disable tracking when stream stops
            if self.tracking_enabled:
                self.tracking_button.setChecked(False)
                self.toggle_tracking(False)
            self.tracking_button.setEnabled(False)

            # Tell image processor to stop connecting
            if hasattr(self, 'image_thread'):
                self.image_thread.stop_connecting()

            # Send stop command to proxy
            if self.camera_proxy_base_url:
                def _on_stop_response(response):
                    if response.ok:
                        self.logger.info("Stream stop command sent to proxy")
                    else:
                        self.logger.warning(f"Stream stop failed: {response.error or f'HTTP {response.status}'}")

                get_http_client().post(f"{self.camera_proxy_base_url}/stream/stop",
                                       _on_stop_response, timeout_ms=3000, owner=self)

        self.update_stream_button_appearance()

    @error_boundary
    def check_stream_status(self):
        """Check camera proxy stream status and sync UI (asynchronous)"""
        if not self.camera_proxy_base_url:
            return

        get_http_client().get(f"{self.camera_proxy_base_url}/stream/status",
                              self._on_stream_status, timeout_ms=2000, owner=self)

    def _on_stream_status(self, response):
        """Apply stream status response to the UI"""
        if not response.ok or response.json is None:
            self.logger.warning(f"Stream status check failed: {response.error or f'HTTP {response.status}'}")
            return

        status = response.json
        is_streaming = status.get("streaming_enabled", False)
        is_active = status.get("stream_active", False)

        self.logger.info(f"Stream status: enabled={is_streaming}, active={is_active}")

        if is_streaming != self.streaming_enabled:
            self.streaming_enabled = is_streaming
            self.stream_button.setChecked(is_streaming)
            self.update_stream_button_appearance()
            self.tracking_button.setEnabled(is_streaming)

        if is_streaming and is_active:
            self._set_stats_text("Stream active", active=True)
            # Tell image processor to start if proxy is active
            if hasattr(self, 'image_thread'):
                self.image_thread.start_connecting()
        else:
            self._set_stats_text("Stream inactive")

    @error_boundary
    def update_display(self, processed_data):
        """Update display with processed frame data supporting multiple gestures"""
        try:
            if processed_data is None:
                self.video_label.setText("No frame data")
                return

            frame_rgb = processed_data.frame
            gesture_detected = processed_data.gesture_detected

            if frame_rgb is None:
                self.video_label.setText("Camera not available")
                return

            # Handle gesture detection if tracking enabled
            if self.tracking_enabled and gesture_detected:
                self._handle_gesture_detection(gesture_detected)

            # Report who is in view to the backend for attention behaviour,
            # and cache the list so a click on the video can be matched
            # against it
            if self.tracking_enabled and processed_data.people is not None:
                self._last_people = processed_data.people
                self._send_people(processed_data.people)

            # Convert frame to Qt pixmap and display
            height, width, channel = frame_rgb.shape
            self._last_frame_size = (width, height)
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

    def _on_video_clicked(self, click_pos: QPoint):
        """Map a click on the video to a tracked person's box, and tell the
        backend to lock attention onto them. Clicking outside every box
        clears the manual selection and returns to automatic picking."""
        if not self.tracking_enabled or not self._last_people or not self._last_frame_size:
            return

        frame_w, frame_h = self._last_frame_size
        if frame_w <= 0 or frame_h <= 0:
            return

        label_w = self.video_label.width()
        label_h = self.video_label.height()

        # Match the Qt.AspectRatioMode.KeepAspectRatio scaling used to build
        # the displayed pixmap, so the click can be mapped back through the
        # same letterboxing (the label centres a smaller pixmap within it)
        scale = min(label_w / frame_w, label_h / frame_h)
        disp_w = frame_w * scale
        disp_h = frame_h * scale
        offset_x = (label_w - disp_w) / 2.0
        offset_y = (label_h - disp_h) / 2.0

        x = click_pos.x() - offset_x
        y = click_pos.y() - offset_y
        if x < 0 or y < 0 or x > disp_w or y > disp_h:
            return  # clicked in the letterbox padding, not on the frame itself

        norm_x = x / disp_w
        norm_y = y / disp_h

        selected_id = None
        for person in self._last_people:
            half_w = max(person.get("w", 0.1), 0.02) / 2.0
            half_h = max(person.get("h", 0.1), 0.02) / 2.0
            if (person["cx"] - half_w <= norm_x <= person["cx"] + half_w and
                    person["cy"] - half_h <= norm_y <= person["cy"] + half_h):
                selected_id = person["id"]
                break

        self.send_websocket_message("select_person", id=selected_id)
        if selected_id is not None:
            self.logger.info(f"Manually selected person {selected_id}")
        else:
            self.logger.info("Cleared manual person selection")

    def _on_attention_state(self, message):
        """Pass the backend attention state to the image processor for the overlay"""
        if hasattr(self, 'image_thread'):
            self.image_thread.set_attention_state(message.get("state"), message.get("focus_id"))

    def _send_people(self, people):
        """Send the tracked people to the backend at a limited rate.
        An empty list is sent too, so the backend can tell 'nobody in view'
        apart from 'no updates'."""
        now = time.monotonic()
        if now - self.last_people_send_time < PEOPLE_SEND_INTERVAL:
            return
        self.last_people_send_time = now
        self.send_websocket_message("people", people=people)

    def update_stats(self, stats_dict):
        """Update statistics display"""
        try:
            if isinstance(stats_dict, dict):
                fps = stats_dict.get('fps', 0)
                frame_count = stats_dict.get('frame_count', 0)
                running = stats_dict.get('running', False)
                
                if running:
                    self._set_stats_text(f"{fps:.1f} FPS · {int(frame_count):,} frames", active=True)
                else:
                    self._set_stats_text("Not running")
            else:
                self._set_stats_text(f"{stats_dict}")
        except Exception as e:
            self.logger.error(f"Stats update error: {e}")
            self._set_stats_text("Stats error")

    def _handle_gesture_detection(self, gesture_type):
        """
        Handle multiple gesture types with confidence buffering
        Uses SHARED stand-down timer for all gestures to prevent being too busy
        gesture_type: "left_wave", "right_wave", or "hands_up"
        """
        wave_config = config_manager.get_wave_config()
        current_time = time.time()
        
        # Sample rate limiting
        if current_time - self.last_sample_time < 1.0 / wave_config["sample_rate"]:
            return  # Don't process if we're sampling too fast
        
        self.last_sample_time = current_time
        
        # Add detection to the appropriate buffer
        self.sample_buffers[gesture_type].append(True)
        
        # Check confidence for the detected gesture ONLY if buffer is full
        buffer = self.sample_buffers[gesture_type]
        if len(buffer) == buffer.maxlen:  # Wait for FULL buffer (3 seconds)
            confidence = sum(buffer) / len(buffer)
            
            self.logger.debug(f"{gesture_type} buffer full: {confidence:.2%} confidence (need {wave_config['confidence_threshold']:.2%})")
            
            if confidence >= wave_config["confidence_threshold"]:
                # Check SHARED stand-down time for ALL gestures
                if current_time - self.last_gesture_time >= wave_config["stand_down_time"]:
                    # Send the appropriate gesture message
                    self.send_websocket_message("gesture", name=gesture_type)
                    
                    # Update the SHARED gesture timer (prevents any gesture for stand-down period)
                    self.last_gesture_time = current_time
                    
                    # Clear ALL buffers to prevent other gestures from triggering immediately
                    for gesture in self.sample_buffers:
                        self.sample_buffers[gesture].clear()
                    
                    # Log the detection
                    gesture_name = gesture_type.replace("_", " ").title()
                    self.logger.info(f"{gesture_name} gesture detected and sent! (Confidence: {confidence:.2%})")
                else:
                    # Still in stand-down period
                    remaining_time = wave_config["stand_down_time"] - (current_time - self.last_gesture_time)
                    self.logger.debug(f"{gesture_type} detected but in stand-down period ({remaining_time:.1f}s remaining)")

    @error_boundary
    def toggle_tracking(self, checked=None):
        """Toggle gesture tracking and inform the image processor"""
        if checked is not None:
            self.tracking_enabled = checked
        else:
            self.tracking_enabled = self.tracking_button.isChecked()

        # Tell image processor about tracking state
        if hasattr(self, 'image_thread'):
            self.image_thread.set_tracking_enabled(self.tracking_enabled)

        if not self.tracking_enabled:
            # Stop reporting stale boxes to clicks once tracking is off
            self._last_people = []

        if self.tracking_enabled:
            self.tracking_button.setToolTip("Gesture Detection: ENABLED\n(Left Wave, Right Wave, Hands Up)\nClick to disable")
            self.logger.info("Multi-gesture detection ENABLED (left wave, right wave, hands up)")
        else:
            self.tracking_button.setToolTip("Gesture Detection: DISABLED (Click to enable)")
            self.logger.info("Multi-gesture detection DISABLED")

        self.send_websocket_message("tracking", state=self.tracking_enabled)

    def cleanup(self):
        """Cleanup camera screen resources"""
        unregister_handler = getattr(self.websocket, "unregister_handler", None)
        if unregister_handler:
            unregister_handler("attention_state", self._on_attention_state)

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