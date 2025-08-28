"""
WALL-E Control System - Camera Feed Screen
Live camera stream display with pose tracking and controls
"""

import os
import time
import requests
from collections import deque
from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                            QComboBox, QSlider, QSpinBox, QCheckBox, QWidget)
from PyQt6.QtGui import QFont, QIcon, QImage, QPixmap
from PyQt6.QtCore import Qt, QSize

from widgets.base_screen import BaseScreen
from threads.image_processor import ImageProcessingThread
from core.config_manager import config_manager
from core.utils import error_boundary
from core.logger import get_logger


class CameraControlsWidget(QWidget):
    """Camera controls panel for adjusting ESP32 camera settings"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_logger("camera")
        wave_config = config_manager.get_wave_config()
        raw_url = wave_config.get("camera_proxy_url", "http://10.1.1.230:8081")
        self.proxy_base_url = raw_url.replace("/stream", "")
        self.current_settings = {}
        self.init_ui()
        self.load_current_settings()
        
    def init_ui(self):
        """Initialize the camera controls UI"""
        self.setStyleSheet("""
            QWidget {
                background-color: #2a2a2a;
                color: white;
                border-radius: 10px;
            }
            QLabel {
                color: white;
                font-size: 14px;
            } 
            QLabel#title {
                font-size: 32px;
                font-weight: bold;
                text-align: center;
            }
            QSlider {
                min-height: 20px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #555;
                height: 8px;
                background: #333;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #FF4444;
                border: 1px solid #FF4444;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #FF6666;
            }
            QPushButton {
                background-color: #444;
                color: white;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #555;
            }
            QPushButton:pressed {
                background-color: #333;
            }
            QPushButton:checked {
                background-color: #44FF44;
                color: black;
            }
            QComboBox {
                background-color: #444;
                color: white;
                border-radius: 6px;
                padding: 6px;
                font-size: 14px;
            }
            QSpinBox {
                background-color: #444;
                color: white;
                border-radius: 6px;
                padding: 6px;
                font-size: 14px;
            }
        """)
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        # Title
        title = QLabel("📷 Camera Controls")
        title.setObjectName("title")  
        title.setFont(QFont("Arial", 32, QFont.Weight.Bold))
        main_layout.addWidget(title)
        
        # XCLK Frequency control
        xclk_layout = QHBoxLayout()
        xclk_label = QLabel("XCLK MHz:")
        xclk_label.setFixedWidth(100)
        self.xclk_spin = QSpinBox()
        self.xclk_spin.setRange(8, 20)
        self.xclk_spin.setValue(10)
        self.xclk_spin.setFixedWidth(80)
        self.xclk_btn = QPushButton("Set")
        self.xclk_btn.setFixedWidth(60)
        self.xclk_btn.clicked.connect(lambda: self.update_setting("xclk_freq", self.xclk_spin.value()))
        xclk_layout.addWidget(xclk_label)
        xclk_layout.addWidget(self.xclk_spin)
        xclk_layout.addWidget(self.xclk_btn)
        xclk_layout.addStretch()
        main_layout.addLayout(xclk_layout)
        
        # Resolution dropdown
        res_layout = QHBoxLayout()
        res_label = QLabel("Resolution:")
        res_label.setFixedWidth(100)
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems([
            "QQVGA(160x120)", "QCIF(176x144)", "HQVGA(240x176)", "QVGA(320x240)",
            "CIF(400x296)", "VGA(640x480)", "SVGA(800x600)", "XGA(1024x768)",
            "SXGA(1280x1024)", "UXGA(1600x1200)"
        ])
        self.resolution_combo.setCurrentIndex(5)  # Default to VGA
        self.resolution_combo.currentIndexChanged.connect(
            lambda idx: self.update_setting("resolution", idx)
        )
        res_layout.addWidget(res_label)
        res_layout.addWidget(self.resolution_combo)
        main_layout.addLayout(res_layout)
        
        # Quality slider
        self.quality_slider, quality_layout = self.create_slider_control(
            "Quality:", 4, 63, 12, "quality"
        )
        main_layout.addLayout(quality_layout)
        
        # Brightness slider
        self.brightness_slider, brightness_layout = self.create_slider_control(
            "Brightness:", -2, 2, 0, "brightness"
        )
        main_layout.addLayout(brightness_layout)
        
        # Contrast slider
        self.contrast_slider, contrast_layout = self.create_slider_control(
            "Contrast:", -2, 2, 0, "contrast"
        )
        main_layout.addLayout(contrast_layout)
        
        # Saturation slider
        self.saturation_slider, saturation_layout = self.create_slider_control(
            "Saturation:", -2, 2, 0, "saturation"
        )
        main_layout.addLayout(saturation_layout)
        
        # Mirror controls
        mirror_layout = QHBoxLayout()
        mirror_label = QLabel("Mirror:")
        mirror_label.setFixedWidth(100)
        
        self.h_mirror_btn = QPushButton("Horizontal")
        self.h_mirror_btn.setCheckable(True)
        self.h_mirror_btn.setFixedWidth(125)
        self.h_mirror_btn.clicked.connect(
            lambda checked: self.update_setting("h_mirror", checked)
        )
        
        self.v_flip_btn = QPushButton("Vertical")
        self.v_flip_btn.setCheckable(True)
        self.v_flip_btn.setFixedWidth(125)
        self.v_flip_btn.clicked.connect(
            lambda checked: self.update_setting("v_flip", checked)
        )
        
        mirror_layout.addWidget(mirror_label)
        mirror_layout.addWidget(self.h_mirror_btn)
        mirror_layout.addWidget(self.v_flip_btn)
        mirror_layout.addStretch()
        main_layout.addLayout(mirror_layout)
        
        # Reset button
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self.reset_to_defaults)
        main_layout.addWidget(reset_btn)
        
        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #888; font-size: 12px;")
        main_layout.addWidget(self.status_label)
        
        main_layout.addStretch()
        self.setLayout(main_layout)
        
    def create_slider_control(self, label_text, min_val, max_val, default_val, setting_name):
        """Create a slider control with label and value display"""
        layout = QHBoxLayout()
        
        label = QLabel(label_text)
        label.setFixedWidth(100)
        
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(default_val)
        slider.setFixedWidth(170)
        
        value_label = QLabel(str(default_val))
        value_label.setFixedWidth(40)
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Update value label when slider changes
        slider.valueChanged.connect(lambda val: value_label.setText(str(val)))
        
        # Update camera setting when slider is released
        slider.sliderReleased.connect(
            lambda: self.update_setting(setting_name, slider.value())
        )
        
        # Add min/max labels
        min_label = QLabel(str(min_val))
        min_label.setStyleSheet("color: #666; font-size: 12px;")
        max_label = QLabel(str(max_val))
        max_label.setStyleSheet("color: #666; font-size: 12px;")
        
        layout.addWidget(label)
        layout.addWidget(min_label)
        layout.addWidget(slider)
        layout.addWidget(max_label)
        layout.addWidget(value_label)
        layout.addStretch()
        
        return slider, layout
    
    @error_boundary
    def load_current_settings(self):
        """Load current settings from camera proxy"""
        try:
            response = requests.get(f"{self.proxy_base_url}/camera/settings", timeout=3)
            if response.status_code == 200:
                settings = response.json()
                self.current_settings = settings
                
                # Update UI with current settings
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
                self.logger.info(f"Loaded camera settings")
                
        except Exception as e:
            self.status_label.setText("Failed to load settings")
            self.logger.error(f"Failed to load camera settings: {e}")
    
    @error_boundary
    def update_setting(self, setting_name, value):
        """Update a camera setting via the proxy"""
        try:
            # Convert boolean to string for POST request
            if isinstance(value, bool):
                value = "true" if value else "false"
            
            response = requests.post(
                f"{self.proxy_base_url}/camera/setting/{setting_name}",
                params={"value": value},
                timeout=3
            )
            
            if response.status_code == 200:
                self.status_label.setText(f"Updated {setting_name}")
                self.current_settings[setting_name] = value
                self.logger.info(f"Updated {setting_name} = {value}")
            else:
                self.status_label.setText(f"Failed to update {setting_name}")
                
        except Exception as e:
            self.status_label.setText(f"Error: {str(e)[:50]}")
            self.logger.error(f"Failed to update {setting_name}: {e}")
    
    @error_boundary
    def reset_to_defaults(self):
        """Reset all settings to default values"""
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
        
        # Send all defaults to camera
        try:
            response = requests.post(f"{self.proxy_base_url}/camera/settings", json=defaults, timeout=3)
            if response.status_code == 200:
                self.status_label.setText("Reset to defaults")
                self.current_settings = defaults
            else:
                self.status_label.setText("Failed to reset")
        except Exception as e:
            self.status_label.setText(f"Error: {str(e)[:50]}")
            self.logger.error(f"Failed to reset to defaults: {e}")


class CameraFeedScreen(BaseScreen):
    """Live camera stream display with pose tracking and controls"""
    
    def _setup_screen(self):
        """Initialize camera feed screen"""
        wave_config = config_manager.get_wave_config()
        
        # Initialize state
        self.sample_buffer = deque(maxlen=wave_config["sample_duration"] * wave_config["sample_rate"])
        self.last_wave_time = 0
        self.last_sample_time = 0
        self.tracking_enabled = False
        self.streaming_enabled = False
        self.stream_can_change_settings = True
        
        # Get camera URLs
        camera_proxy_url = wave_config.get("camera_proxy_url", "")
        self.camera_proxy_base_url = camera_proxy_url.replace("/stream", "") if camera_proxy_url else ""
        
        # Initialize image processing thread
        self.image_thread = ImageProcessingThread(camera_proxy_url)
        self.image_thread.frame_processed.connect(self.update_display)
        self.image_thread.stats_updated.connect(self.update_stats)
        
        self.init_ui()
        
        # Start image processing thread
        self.image_thread.start()
        self.check_stream_status()
        
    def init_ui(self):
        """Initialize user interface"""
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
        
        # Setup controls
        self.setup_control_buttons()
        self.controls_widget = CameraControlsWidget()
        self.controls_widget.setFixedWidth(400)
        self.controls_widget.setMaximumHeight(600)
        
        self.setup_layout()
        
    def setup_control_buttons(self):        
        """Setup stream and tracking control buttons"""
        # Stream Control Button
        self.stream_button = QPushButton()
        self.stream_button.setCheckable(True)
        self.stream_button.setChecked(False)
        
        # Load icons for stream control
        self.stream_start_icon = None
        self.stream_stop_icon = None
        if os.path.exists("resources/icons/StreamStart.png"):
            self.stream_start_icon = QIcon("resources/icons/StreamStart.png")
        if os.path.exists("resources/icons/StreamStop.png"):
            self.stream_stop_icon = QIcon("resources/icons/StreamStop.png")
        
        self.update_stream_button_appearance()
        self.stream_button.toggled.connect(self.toggle_stream)
        self.stream_button.setFixedSize(150, 50)
        self.stream_button.setStyleSheet("""
            QPushButton {
                background-color: #333;
                border: 2px solid #555;
                border-radius: 12px;
                color: white;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #444;
                border-color: #777;
            }
            QPushButton:checked {
                background-color: #4a9;
                border-color: #5ba;
                color: black;
            }
            QPushButton:disabled {
                background-color: #222;
                border-color: #333;
                color: #666;
            }
        """)
        
        # Tracking Button
        self.tracking_button = QPushButton()
        self.tracking_button.setCheckable(True)
        if os.path.exists("resources/icons/Tracking.png"):
            self.tracking_button.setIcon(QIcon("resources/icons/Tracking.png"))
            self.tracking_button.setIconSize(QSize(200, 80))
        
        self.tracking_button.toggled.connect(self.toggle_tracking)
        self.tracking_button.setFixedSize(220, 100)
        self.tracking_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
            }
        """)
        self.tracking_button.setToolTip("Toggle Wave Detection")
        self.tracking_button.setEnabled(False) 
        
        self.logger.info("Camera control buttons initialized")

    def setup_layout(self):
        """Setup layout with video display and controls"""
        video_layout = QVBoxLayout()
        video_layout.setContentsMargins(0, 10, 0, 0)
        video_layout.addWidget(self.video_label)
        video_layout.addWidget(self.stats_label)
        
        button_layout = QVBoxLayout()
        button_layout.setSpacing(20)
        button_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        button_layout.addWidget(self.controls_widget)
            
        control_buttons_layout = QHBoxLayout()
        control_buttons_layout.setSpacing(15)
        control_buttons_layout.addStretch()
        control_buttons_layout.addWidget(self.stream_button)
        control_buttons_layout.addWidget(self.tracking_button)
        control_buttons_layout.addStretch()

        button_layout.addLayout(control_buttons_layout)
        button_layout.addStretch()
        
        main_layout = QHBoxLayout()
        main_layout.addSpacing(90)
        main_layout.addLayout(video_layout)
        main_layout.addLayout(button_layout)
        main_layout.addStretch()
        
        self.setLayout(main_layout)

    def update_stream_button_appearance(self):
        """Update the stream button appearance based on current state"""
        if self.streaming_enabled:
            if self.stream_stop_icon:
                self.stream_button.setIcon(self.stream_stop_icon)
                self.stream_button.setIconSize(QSize(32, 32)) 
            self.stream_button.setText("Stop Stream")
            self.stream_button.setToolTip("Click to stop camera stream")
            self.stream_button.setChecked(True)
        else:
            if self.stream_start_icon:
                self.stream_button.setIcon(self.stream_start_icon)
                self.stream_button.setIconSize(QSize(32, 32)) 
            self.stream_button.setText("Start Stream")
            self.stream_button.setToolTip("Click to start camera stream")
            self.stream_button.setChecked(False)

    @error_boundary
    def toggle_stream(self, checked):
        """Toggle camera stream on/off"""
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
        """Check if camera proxy stream is currently active"""
        try:
            if not self.camera_proxy_base_url:
                return
                
            response = requests.get(f"{self.camera_proxy_base_url}/stream/status", timeout=2)
            
            if response.status_code == 200:
                status = response.json()
                is_streaming = status.get("streaming", False)
                
                # Update UI to match actual stream state
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
        """Update display with processed frame data"""
        try:
            frame_rgb = processed_data['frame']
            wave_detected = processed_data['wave_detected']
            
            if frame_rgb is None:
                self.video_label.setText("Camera not available\n(OpenCV not installed)")
                return
            
            # Handle wave detection logic
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
                            # Send wave gesture detected
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
        """Update statistics display"""
        self.stats_label.setText(f"Stream Stats: {stats_text}")
    
    @error_boundary    
    def toggle_tracking(self, checked=None):
        """Toggle wave detection tracking with visual feedback"""
        if checked is not None:
            self.tracking_enabled = checked
        else:
            self.tracking_enabled = self.tracking_button.isChecked()
        
        # Update the image thread with tracking state
        self.image_thread.set_tracking_enabled(self.tracking_enabled)
        
        # Update button icon based on state
        if self.tracking_enabled:
            pressed_icon = "resources/icons/Tracking_pressed.png"
            if os.path.exists(pressed_icon):
                self.tracking_button.setIcon(QIcon(pressed_icon))
                self.logger.debug("Changed to Tracking_pressed.png icon")
            self.tracking_button.setToolTip("Wave Detection: ENABLED (Click to disable)")
            self.logger.info("Wave detection ENABLED")
        else:
            normal_icon = "resources/icons/Tracking.png"
            if os.path.exists(normal_icon):
                self.tracking_button.setIcon(QIcon(normal_icon))
                self.logger.debug("Changed to Tracking.png icon")
            self.tracking_button.setToolTip("Wave Detection: DISABLED (Click to enable)")
            self.logger.info("Wave detection DISABLED")
        
        # Send tracking state to backend
        self.send_websocket_message("tracking", state=self.tracking_enabled)
        
        # Update stats to show tracking status
        status = "ENABLED" if self.tracking_enabled else "DISABLED"
        current_stats = self.stats_label.text()
        if "Wave Detection:" in current_stats:
            parts = current_stats.split(" | Wave Detection:")
            self.stats_label.setText(f"{parts[0]} | Wave Detection: {status}")
        else:
            self.stats_label.setText(f"{current_stats} | Wave Detection: {status}")
    
    def stop_camera_thread(self):
        """Stop the camera processing thread"""
        if hasattr(self, 'image_thread'):
            self.image_thread.stop()
    
    def cleanup(self):
        """Cleanup camera resources"""
        self.stop_camera_thread()