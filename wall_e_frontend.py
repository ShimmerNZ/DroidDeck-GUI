# WALL-E Optimized Frontend - Complete Implementation with Performance and Reliability Improvements
import sys
import json
import time
import random
import requests
import numpy as np
from tkinter import font
import psutil
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QMainWindow, QStackedWidget, QFrame, QScrollArea, QComboBox, QGridLayout,
    QLineEdit, QSpinBox, QCheckBox, QMenuBar, QMenu, QButtonGroup, QSlider, QMessageBox
)
from PyQt6.QtGui import QFont, QImage, QPixmap, QPainter, QPen, QColor, QPalette, QBrush, QIcon
from PyQt6.QtCore import Qt, QTimer, QUrl, QRect, QSize, QThread, pyqtSignal
from PyQt6.QtWebSockets import QWebSocket
from PyQt6.QtNetwork import QAbstractSocket
import pyqtgraph as pg

# Optional imports for camera functionality
try:
    import cv2
    import mediapipe as mp
    CV2_AVAILABLE = True
except ImportError:
    print("Warning: OpenCV and/or MediaPipe not available. Camera functionality will be disabled.")
    CV2_AVAILABLE = False
    cv2 = None
    mp = None

from collections import deque
import weakref
import gc
from functools import lru_cache
import os

# PERFORMANCE IMPROVEMENT 1: Lazy initialization of MediaPipe
mp_pose = None
pose = None

def init_mediapipe():
    """Lazy initialization of MediaPipe to reduce startup time"""
    global mp_pose, pose
    if not CV2_AVAILABLE:
        print("MediaPipe not available - camera tracking disabled")
        return False
    
    if mp_pose is None:
        mp_pose = mp.solutions.pose
        pose = mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=0.75,
            min_tracking_confidence=0.9
        )
    return True

# PERFORMANCE IMPROVEMENT 2: Configuration caching and singleton pattern
class ConfigManager:
    _instance = None
    _configs = {}
    _last_modified = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @lru_cache(maxsize=32)
    def get_config(self, config_path):
        """Cached config loading with file modification time checking"""
        try:
            if not os.path.exists(config_path):
                return {}
            current_mtime = os.path.getmtime(config_path)
            if (config_path not in self._last_modified or 
                self._last_modified[config_path] < current_mtime):
                with open(config_path, "r") as f:
                    self._configs[config_path] = json.load(f)
                self._last_modified[config_path] = current_mtime
            return self._configs[config_path]
        except Exception as e:
            print(f"Failed to load config {config_path}: {e}")
            return {}
    
    def clear_cache(self):
        """Clear configuration cache"""
        self.get_config.cache_clear()
        self._configs.clear()
        self._last_modified.clear()

config_manager = ConfigManager()

# MEMORY MANAGEMENT: Add cleanup utilities
class MemoryManager:
    @staticmethod
    def cleanup_widgets(widget):
        """Recursively cleanup widget resources"""
        if hasattr(widget, 'children'):
            for child in widget.children():
                if hasattr(child, 'deleteLater'):
                    child.deleteLater()
        gc.collect()
    
    @staticmethod
    def periodic_cleanup():
        """Periodic memory cleanup"""
        gc.collect()

# RELIABILITY IMPROVEMENT 2: Error boundary decorator
def error_boundary(func):
    """Decorator to catch and log errors without crashing"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"Error in {func.__name__}: {e}")
            return None
    return wrapper


class ImageProcessingThread(QThread):
    frame_processed = pyqtSignal(object)
    stats_updated = pyqtSignal(str)

    def __init__(self, camera_proxy_url):
        super().__init__()
        self.camera_proxy_url = camera_proxy_url
        self.stats_url = "http://10.1.1.230:8081/stats"
        self.running = False
        self.tracking_enabled = False
        self.frame_skip_count = 0
        self.target_fps = 15
        self.last_stats_update = 0
        self.stats_fetch_interval = 2.0
        self.hog = None
        print(f"📷 Camera thread initialized with URL: {camera_proxy_url}")

    def set_tracking_enabled(self, enabled):
        self.tracking_enabled = enabled
        print(f"👀 Tracking enabled: {enabled}")

    def fetch_camera_stats(self):
        try:
            response = requests.get(self.stats_url, timeout=2)
            if response.status_code == 200:
                stats_data = response.json()
                fps = stats_data.get("fps", 0)
                frame_count = stats_data.get("frame_count", 0)
                latency = stats_data.get("latency", 0)
                status = stats_data.get("status", "unknown")
                return f"FPS: {fps}, Frames: {frame_count}, Latency: {latency}ms, Status: {status}"
            else:
                return f"Stats Error: HTTP {response.status_code}"
        except Exception as e:
            return f"Stats Error: {str(e)[:50]}"

    def run(self):
        if not CV2_AVAILABLE:
            print("❌ Camera processing disabled - OpenCV not available")
            self.stats_updated.emit("OpenCV not available")
            return

        self.running = True
        frame_time = 1.0 / self.target_fps
        last_process_time = time.time()
        reconnect_attempts = 0
        max_retries = 5
        reconnect_delay = 3  # seconds

        while self.running and reconnect_attempts < max_retries:
            try:
                self.stats_updated.emit(f"Connecting to stream... (Attempt {reconnect_attempts + 1})")
                stream = requests.get(self.camera_proxy_url, stream=True, timeout=5)
                stream.raise_for_status()
                print("✅ Connected to MJPEG stream")
                self.stats_updated.emit("Stream connected")
                reconnect_attempts = 0  # reset on success

                bytes_data = b""
                for chunk in stream.iter_content(chunk_size=1024):
                    if not self.running:
                        break

                    bytes_data += chunk
                    a = bytes_data.find(b'\xff\xd8')
                    b = bytes_data.find(b'\xff\xd9')

                    if a != -1 and b != -1:
                        jpg = bytes_data[a:b+2]
                        bytes_data = bytes_data[b+2:]

                        img_array = np.frombuffer(jpg, dtype=np.uint8)
                        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

                        if frame is not None:
                            current_time = time.time()
                            if current_time - last_process_time >= frame_time:
                                processed_frame = self.process_frame(frame)
                                self.frame_processed.emit(processed_frame)
                                last_process_time = current_time

                            if current_time - self.last_stats_update >= self.stats_fetch_interval:
                                stats_text = self.fetch_camera_stats()
                                self.stats_updated.emit(stats_text)
                                self.last_stats_update = current_time
            except Exception as e:
                reconnect_attempts += 1
                print(f"❌ MJPEG stream error: {e}")
                self.stats_updated.emit(f"Stream error: {str(e)} - retrying in {reconnect_delay}s")
                time.sleep(reconnect_delay)

        if reconnect_attempts >= max_retries:
            self.stats_updated.emit("❌ Failed to connect after multiple attempts")
            print("❌ Max reconnect attempts reached")


    def process_frame(self, frame):
        try:
            height, width = frame.shape[:2]
            if width > 640:
                scale = 640 / width
                frame = cv2.resize(frame, (int(width * scale), int(height * scale)))

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            wave_detected = False

            if self.tracking_enabled:
                if init_mediapipe() and pose is not None:
                    results = pose.process(frame_rgb)
                    if results.pose_landmarks:
                        lm = results.pose_landmarks.landmark
                        rw = lm[mp_pose.PoseLandmark.RIGHT_WRIST]
                        rs = lm[mp_pose.PoseLandmark.RIGHT_SHOULDER]
                        if rw.y < rs.y:
                            wave_detected = True
                            cv2.putText(frame_rgb, 'Wave Detected', (50, 50),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            return {
                'frame': frame_rgb,
                'wave_detected': wave_detected,
                'stats': f"Processing: {frame_rgb.shape[1]}x{frame_rgb.shape[0]}"
            }
        except Exception as e:
            print(f"❌ Frame processing error: {e}")
            black_frame = np.zeros((240, 320, 3), dtype=np.uint8)
            cv2.putText(black_frame, f"Error: {str(e)[:30]}", (10, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            return {'frame': black_frame, 'wave_detected': False, 'stats': f"Error: {e}"}

    def stop(self):
        print("🛑 Stopping camera thread...")
        self.running = False
        self.quit()
        self.wait(3000)



# RELIABILITY IMPROVEMENT 1: WebSocket connection management
class WebSocketManager(QWebSocket):
    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url
        self.reconnect_timer = QTimer()
        self.reconnect_timer.timeout.connect(self.attempt_reconnect)
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        
        # Connection state management
        self.connected.connect(self.on_connected)
        self.disconnected.connect(self.on_disconnected)
        self.error.connect(self.on_error)
        
        self.connect_to_server()
    
    def connect_to_server(self):
        """Attempt to connect to WebSocket server"""
        try:
            if not self.url.startswith("ws://") and not self.url.startswith("wss://"):
                self.url = f"ws://{self.url}"
            self.open(QUrl(self.url))
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            self.start_reconnect_timer()
    
    def on_connected(self):
        print(f"WebSocket connected to {self.url}")
        self.reconnect_attempts = 0
        self.reconnect_timer.stop()
    
    def on_disconnected(self):
        print(f"WebSocket disconnected from {self.url}")
        self.start_reconnect_timer()
    
    def on_error(self, error):
        print(f"WebSocket error: {error}")
        self.start_reconnect_timer()
    
    def start_reconnect_timer(self):
        if self.reconnect_attempts < self.max_reconnect_attempts:
            delay = min(1000 * (2 ** self.reconnect_attempts), 30000)  # Exponential backoff
            self.reconnect_timer.start(delay)
        else:
            print("Max reconnection attempts reached")
    
    def attempt_reconnect(self):
        self.reconnect_attempts += 1
        print(f"Attempting to reconnect ({self.reconnect_attempts}/{self.max_reconnect_attempts})")
        self.connect_to_server()
    
    def send_safe(self, message):
        """Safe message sending with connection check"""
        
        if self.state() == QAbstractSocket.SocketState.ConnectedState:  # FIXED
            self.sendTextMessage(message)
            return True
        else:
            print("WebSocket not connected, message not sent")
            return False

# Load configuration with improvements
try:
    config = config_manager.get_config("configs/steamdeck_config.json")
    wave_config = config.get("current", {})
    wave_settings = wave_config.get("wave_detection", {})
    ESP32_CAM_URL = wave_config.get("esp32_cam_url", "")
    SAMPLE_DURATION = wave_settings.get("sample_duration", 3)
    SAMPLE_RATE = wave_settings.get("sample_rate", 5)
    CONFIDENCE_THRESHOLD = wave_settings.get("confidence_threshold", 0.7)
    STAND_DOWN_TIME = wave_settings.get("stand_down_time", 30)
except Exception as e:
    print(f"Failed to load wave detection config: {e}")
    ESP32_CAM_URL = ""
    SAMPLE_DURATION = 3
    SAMPLE_RATE = 5
    CONFIDENCE_THRESHOLD = 0.7
    STAND_DOWN_TIME = 30

# Load servo friendly names from config
@error_boundary
def load_servo_names():
    config = config_manager.get_config("configs/servo_config.json")
    return [v["name"] for v in config.values() if "name" in v and v["name"]]

@error_boundary
def load_movement_controls():
    config = config_manager.get_config("configs/movement_controls.json")
    return config.get("steam_controls", []), config.get("nema_movements", [])

STEAM_CONTROLS, NEMA_MOVEMENTS = load_movement_controls() or ([], [])


class ControllerConfigScreen(QWidget):
    def __init__(self, websocket):
        super().__init__()
        self.websocket = websocket
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        self.setFixedWidth(1180)
        self.mapping_rows = []
        self.load_motion_config()
        self.init_ui()
        self.load_config()

    @error_boundary
    def load_motion_config(self):
        config = config_manager.get_config("configs/motion_config.json")
        self.groups = config.get("groups", {})
        self.emotions = config.get("emotions", [])
        self.movements = config.get("movements", {})

    @error_boundary
    def get_maestro_channel_by_name(self, name):
        config = config_manager.get_config("configs/servo_config.json")
        for key, value in config.items():
            if value.get("name") == name:
                maestro = "Maestro 1" if key.startswith("m1") else "Maestro 2"
                channel = key.split("_ch")[1]
                return f"{maestro} / Ch {channel}"
        return "Unknown"

    def init_ui(self):
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
        add_btn = QPushButton("➕ Add Mapping")
        add_btn.clicked.connect(self.add_mapping_row)
        save_btn = QPushButton("💾 Save Config")
        save_btn.clicked.connect(self.save_config)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(save_btn)

        self.layout.addLayout(btn_layout)
        self.setLayout(self.layout)

    def add_mapping_row(self, control=None, control_type=None, movement=None, invert1=False, invert2=False):
        row = len(self.mapping_rows)

        control_cb = QComboBox()
        control_cb.addItems(STEAM_CONTROLS)
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

        remove_btn = QPushButton("❌")
        remove_btn.clicked.connect(lambda: self.remove_mapping_row(row))

        self.grid_layout.addWidget(control_cb, row, 0)
        self.grid_layout.addWidget(type_cb, row, 1)
        self.grid_layout.addWidget(movement_cb, row, 2)
        self.grid_layout.addWidget(maestro1_label, row, 3)
        self.grid_layout.addWidget(invert_cb1, row, 4)
        self.grid_layout.addWidget(maestro2_label, row, 5)
        self.grid_layout.addWidget(invert_cb2, row, 6)
        self.grid_layout.addWidget(remove_btn, row, 7)

        self.mapping_rows.append((control_cb, type_cb, movement_cb, maestro1_label, invert_cb1, maestro2_label, invert_cb2, remove_btn))

    def remove_mapping_row(self, index):
        if index < len(self.mapping_rows) and self.mapping_rows[index]:
            for widget in self.mapping_rows[index]:
                widget.deleteLater()
            self.mapping_rows[index] = None

    @error_boundary
    def save_config(self):
        config = {}
        for row in self.mapping_rows:
            if row:
                control_cb, type_cb, movement_cb, maestro1_label, invert_cb1, maestro2_label, invert_cb2, _ = row
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

        try:
            with open("configs/controller_config.json", "w") as f:
                json.dump(config, f, indent=2)
            QMessageBox.information(self, "Saved", "Controller configuration saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save config: {e}")

    @error_boundary
    def load_config(self):
        config = config_manager.get_config("configs/controller_config.json")
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


class BackgroundWidget(QWidget):
    def __init__(self, background_path):
        super().__init__()
        self.setFixedSize(1280, 800)

        # Background image
        self.background_label = QLabel(self)
        if os.path.exists(background_path):
            self.background_label.setPixmap(QPixmap(background_path).scaled(self.size()))
        self.background_label.setGeometry(0, 0, 1280, 800)

        # Overlay layout
        self.overlay_layout = QVBoxLayout(self)
        self.overlay_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.overlay_layout)


class DynamicHeader(QFrame):
    def __init__(self, screen_name):
        super().__init__()
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white;")
        
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.voltage_label = QLabel("🔋 --.-V")
        self.wifi_label = QLabel("📶 0%")
        self.screen_label = QLabel(screen_name)

        for label in [self.voltage_label, self.wifi_label, self.screen_label]:
            label.setFont(QFont("Arial", 30))
        self.screen_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.voltage_label)
        layout.addStretch()
        layout.addWidget(self.screen_label)
        layout.addStretch()
        layout.addWidget(self.wifi_label)

        self.setLayout(layout)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_values)
        self.timer.start(5000)

    def update_voltage(self, voltage):
        """Update voltage from telemetry data"""
        if voltage < 13.2:
            self.voltage_label.setText(f"🔋 {voltage:.2f}V")
            self.voltage_label.setStyleSheet("color: #FF4444; font-weight: bold;")
        elif voltage < 14.0:
            self.voltage_label.setText(f"🔋 {voltage:.2f}V")
            self.voltage_label.setStyleSheet("color: #FFAA00; font-weight: bold;")
        elif voltage > 14.0:
            self.voltage_label.setText(f"🔋 {voltage:.2f}V")
            self.voltage_label.setStyleSheet("color: #44FF44;")
        else:
            self.voltage_label.setText(f"🔋 {voltage:.2f}V")
            self.voltage_label.setStyleSheet("color: white;")

    def update_wifi(self, percentage):
        """Update WiFi percentage"""
        self.wifi_label.setText(f"📶 {percentage}%")

    def set_screen_name(self, name):
        self.screen_label.setText(name)

    @error_boundary
    def update_values(self):
        wifi = random.randint(70, 100)
        self.wifi_label.setText(f"📶 {wifi}%")


class HealthScreen(QWidget):
    """FIXED: Single HealthScreen with comprehensive debugging and proper voltage display"""
    
    def __init__(self, websocket):
        super().__init__()
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        self.setFixedWidth(1180)
        
        self.websocket = websocket
        self.websocket.textMessageReceived.connect(self.handle_telemetry)
        
        # Rate limiting for telemetry updates
        self.last_telemetry_update = 0
        self.telemetry_update_interval = 0.25  # 500ms minimum between updates
        
        # Voltage alarm state tracking
        self.last_voltage_alarm = None
        
        # Track start time for relative time calculation
        self.start_time = time.time()
        
        # Initialize UI
        self.init_ui_optimized()
    
    def init_ui_optimized(self):
        """FIXED: Optimized UI with better graph positioning and voltage display"""
        # Enhanced graph widget for battery voltage + dual current
        self.graph_widget = pg.PlotWidget()
        self.graph_widget.setBackground('#1e1e1e')
        self.graph_widget.showGrid(x=True, y=True, alpha=0.3)
        self.graph_widget.setTitle("Battery Voltage & Current Draw", color='white', size='14pt')
        self.graph_widget.setLabel('left', 'Battery Voltage (V)', color='white')
        self.graph_widget.setLabel('bottom', 'Time (s)', color='white')
        
        # FIXED: Better voltage range for 4S LiPo batteries
        self.graph_widget.setYRange(0, 20)  # Focus on normal operating range
        self.graph_widget.setLimits(yMin=0, yMax=20)
        self.graph_widget.setMouseEnabled(x=False, y=False)
        
        # Add legend
        self.graph_widget.addLegend(offset=(10, 150))
        self.graph_widget.getPlotItem().setContentsMargins(5, 5, 5, 5)  # left, top, right, bottom
        
        # Limit data points for better performance
        self.max_data_points = 100
        self.battery_voltage_data = deque(maxlen=self.max_data_points)
        self.current_a0_data = deque(maxlen=self.max_data_points)
        self.current_a1_data = deque(maxlen=self.max_data_points)
        self.time_data = deque(maxlen=self.max_data_points)
        
        # FIXED: Create voltage curve with better visibility
        self.voltage_curve = self.graph_widget.plot(
            pen=pg.mkPen(color='#00FF00', width=4),  # Thicker line for better visibility
            name="Battery Voltage",
            antialias=True
        )
        
        
        # FIXED: Current curves setup (right Y-axis) with proper scaling
        self.current_view = pg.ViewBox()
        self.graph_widget.scene().addItem(self.current_view)
        self.graph_widget.getPlotItem().showAxis('right')
        self.graph_widget.getPlotItem().getAxis('right').setLabel('Current (A)', color='white')
        self.graph_widget.getPlotItem().getAxis('right').linkToView(self.current_view)

        # FIXED: Better current range (0-70A is more realistic)
        self.current_view.setYRange(0, 70)  
        self.current_view.setLimits(yMin=-5, yMax=100)
        
        # Link the views properly
        self.graph_widget.getPlotItem().getViewBox().sigResized.connect(self.update_views)
        
        # Current A0 plot (cyan)
        self.current_a0_plot = pg.PlotCurveItem(
            pen=pg.mkPen(color='#00FFFF', width=3), 
            name="Current Battery 1",
            antialias=True
        )
        self.current_view.addItem(self.current_a0_plot)
        
        # Current A1 plot (magenta)
        self.current_a1_plot = pg.PlotCurveItem(
            pen=pg.mkPen(color='#FF00FF', width=3), 
            name="Current Battery 2",
            antialias=True
        )
        self.current_view.addItem(self.current_a1_plot)
        
        legend = self.graph_widget.addLegend(offset=(30, 30))
        legend.addItem(self.current_a0_plot, "Current A0")
        legend.addItem(self.current_a1_plot, "Current A1")

        # Enhanced status labels with battery monitoring
        self.status_labels = {}
        label_configs = [
            ("cpu", "CPU: 0%", 400),
            ("mem", "Memory: 0%", 400),
            ("temp", "Temp: 0°C", 400),
            ("battery", "Battery: 0.0V ⚡", 400),
            ("stream", "Stream: 0 FPS, 0x0, 0ms", 400),
            ("dfplayer", "Audio: Disconnected, 0 files", 400),
            ("maestro1", "Maestro 1: Disconnected", 500),
            ("maestro2", "Maestro 2: Disconnected", 500)
        ]
        
        for key, text, width in label_configs:
            label = QLabel(text)
            label.setFont(QFont("Arial", 18))
            label.setStyleSheet("color: lime; padding: 2px;")
            label.setFixedWidth(width)
            self.status_labels[key] = label
        
        # Layout setup
        self.setup_layout()
    
    def update_views(self):
        """Update the current view geometry to match the main plot"""
        self.current_view.setGeometry(self.graph_widget.getPlotItem().getViewBox().sceneBoundingRect())
    

    def setup_layout(self):
        """FIXED: Enhanced layout with better graph positioning"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(100, 15, 15, 10)
        
        # FIXED: Graph container with better positioning
        graph_frame = QFrame()
        graph_frame.setStyleSheet("border: 2px solid #444; border-radius: 10px; background-color: #1e1e1e;")
        graph_layout = QHBoxLayout(graph_frame)
        graph_layout.setContentsMargins(15, 10, 15, 10)
        
        # FIXED: Better graph sizing and positioning
        self.graph_widget.setFixedWidth(1000)
        self.graph_widget.setFixedHeight(315)
        
        # Center the graph horizontally
        graph_layout.addStretch(1)
        graph_layout.addWidget(self.graph_widget, 4)
        graph_layout.addStretch(1)
        
        # FIXED: Stats layout with better organization
        stats_layout = QGridLayout()
        stats_layout.setVerticalSpacing(8)
        stats_layout.setHorizontalSpacing(15)
        stats_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Add labels to grid (2 columns) with better alignment
        labels_list = list(self.status_labels.values())
        for i, label in enumerate(labels_list[:4]):  # First column
            stats_layout.addWidget(label, i, 0, Qt.AlignmentFlag.AlignLeft)
        for i, label in enumerate(labels_list[4:]):  # Second column
            stats_layout.addWidget(label, i, 1, Qt.AlignmentFlag.AlignLeft)
        
        # FIXED: Container widgets with better spacing
        graph_container = QWidget()
        graph_container_layout = QVBoxLayout(graph_container)
        graph_container_layout.setContentsMargins(5, 0, 5, 0)
        graph_container_layout.addWidget(graph_frame)
        
        stats_container = QWidget()
        stats_container_layout = QHBoxLayout(stats_container)
        stats_container_layout.setContentsMargins(50, 10, 50, 10)
        stats_container_layout.addStretch()
        stats_container_layout.addLayout(stats_layout)
        stats_container_layout.addStretch()
        
        # FIXED: Main layout assembly
        main_layout.addWidget(graph_container, 3)
        main_layout.addWidget(stats_container, 1)
        main_layout.addStretch(0)
        
        self.setLayout(main_layout)

    def get_voltage_status_text(self, voltage):
        """Get voltage status with color coding"""
        if voltage < 13.2:
            return f"Battery: {voltage:.2f}V 🔴 CRITICAL", "color: #FF4444; font-weight: bold;"
        elif voltage < 14.0:
            return f"Battery: {voltage:.2f}V ⚠️ LOW", "color: #FFAA00; font-weight: bold;"
        elif voltage > 14.0:
            return f"Battery: {voltage:.2f}V ✅ GOOD", "color: #44FF44;"
        else:
            return f"Battery: {voltage:.2f}V ⚡ OK", "color: #AAAAFF;"

    def get_maestro_status_text(self, maestro_data, maestro_name):
        """Format detailed Maestro status"""
        if not maestro_data or not maestro_data.get('connected', False):
            return f"{maestro_name}: ❌ Disconnected", "color: #FF4444;"
        
        # Extract detailed status
        channels = maestro_data.get('channel_count', 0)
        error_flags = maestro_data.get('error_flags', {})
        script_status = maestro_data.get('script_status', {}).get('status', 'unknown')
        moving = maestro_data.get('moving', False)
        
        # Check for errors
        has_errors = error_flags.get('has_errors', False)
        if has_errors:
            error_details = error_flags.get('details', {})
            error_list = [k.replace('_error', '') for k, v in error_details.items() if v]
            error_text = ', '.join(error_list[:2])
            status = f"{maestro_name}: ⚠️ {channels}ch, Errors: {error_text}"
            color = "color: #FFAA00; font-weight: bold;"
        else:
            move_text = "Moving" if moving else "Idle"
            status = f"{maestro_name}: ✅ {channels}ch, {script_status.title()}, {move_text}"
            color = "color: #44FF44;"
        
        return status, color

    def handle_telemetry(self, message):
        """FIXED: Enhanced telemetry handler with comprehensive debugging"""
        current_time = time.time()
        
        # Rate limiting to prevent UI overload
        if current_time - self.last_telemetry_update < self.telemetry_update_interval:
            return
        
        try:
            data = json.loads(message)
            if data.get("type") != "telemetry":
                return
            
            print(f"TELEMETRY DEBUG: Processing telemetry data")
            print(f"TELEMETRY DEBUG: Received data keys: {list(data.keys())}")
            
            # Basic system stats
            updates = {}
            
            cpu = data.get("cpu", "--")
            mem = data.get("memory", "--")
            temp = data.get("temperature", "--")
            
            updates["cpu"] = f"CPU: {cpu}%"
            updates["mem"] = f"Memory: {mem}%"
            updates["temp"] = f"Temperature: {temp}°C"
            
            # FIXED: Enhanced battery voltage handling - check multiple possible field names
            battery_voltage = data.get("battery_voltage", None)
            if battery_voltage is None:
                battery_voltage = data.get("voltage", None)
            if battery_voltage is None:
                battery_voltage = data.get("battery", None)

            # FIXED: Enhanced graph data processing with relative time
            current_a0 = data.get("current", 0.0)
            current_a1 = data.get("current_a1", 0.0)
            
            # Ensure we have a valid voltage reading
            if battery_voltage is None or battery_voltage <= 0:
                battery_voltage = 12.6  # Default fallback for display
                print(f"TELEMETRY DEBUG: No valid voltage found, using fallback = {battery_voltage}")
            else:
                print(f"TELEMETRY DEBUG: Found battery voltage = {battery_voltage}")
            
            battery_text, battery_style = self.get_voltage_status_text(battery_voltage)
            updates["battery"] = battery_text
            self.status_labels["battery"].setStyleSheet(battery_style)
            
            # Check for voltage alarms
            self.check_voltage_alarms(battery_voltage)
            
            # Stream info
            stream = data.get("stream", {})
            updates["stream"] = f"Stream: {stream.get('fps', 0)} FPS, {stream.get('resolution', '0x0')}, {stream.get('latency', 0)}ms"
            
            # Audio system
            audio = data.get("audio_system", {})
            updates["dfplayer"] = f"Audio: {'Connected' if audio.get('connected') else 'Disconnected'}, {audio.get('file_count', 0)} files"
            
            # Enhanced Maestro status handling
            m1 = data.get("maestro1", {})
            m2 = data.get("maestro2", {})
            
            m1_text, m1_style = self.get_maestro_status_text(m1, "Maestro 1")
            m2_text, m2_style = self.get_maestro_status_text(m2, "Maestro 2")
            
            updates["maestro1"] = m1_text
            updates["maestro2"] = m2_text
            
            self.status_labels["maestro1"].setStyleSheet(m1_style)
            self.status_labels["maestro2"].setStyleSheet(m2_style)
            
            # Update all text labels
            for key, text in updates.items():
                if key in self.status_labels:
                    self.status_labels[key].setText(text)
            
         
            
            # FIXED: Calculate relative time in seconds from start
            relative_time = current_time - self.start_time
            
            print(f"TELEMETRY DEBUG: Graph data - Time: {relative_time:.1f}s, Battery: {battery_voltage:.2f}V, Current A0: {current_a0:.2f}A, Current A1: {current_a1:.2f}A")
            
            # Always update graph data with relative time
            self.battery_voltage_data.append(float(battery_voltage))
            self.current_a0_data.append(float(current_a0))
            self.current_a1_data.append(float(current_a1))
            self.time_data.append(relative_time)  # Use relative time instead of absolute
            
            # FIXED: Robust graph update with better time scaling
            try:
                # Convert deques to lists for plotting
                time_list = list(self.time_data)
                voltage_list = list(self.battery_voltage_data)
                current_a0_list = list(self.current_a0_data)
                current_a1_list = list(self.current_a1_data)
                
                print(f"GRAPH DEBUG: Data lengths - Time: {len(time_list)}, Voltage: {len(voltage_list)}")
                if len(time_list) > 1:
                    print(f"GRAPH DEBUG: Time range: {min(time_list):.1f}s - {max(time_list):.1f}s")
                    print(f"GRAPH DEBUG: Voltage range: {min(voltage_list):.2f}V - {max(voltage_list):.2f}V")
                
                if len(time_list) > 1 and len(voltage_list) > 1:  # Need at least 2 points
                    # FIXED: Update voltage curve with proper data
                    
                    self.voltage_curve.setData(time_list, voltage_list)
                    print(f"VOLTAGE UPDATE: Updated voltage curve, range: {min(voltage_list):.2f}V - {max(voltage_list):.2f}V")
                    
                    # Update current curves
                    self.current_a0_plot.setData(time_list, current_a0_list)
                    self.current_a1_plot.setData(time_list, current_a1_list)
                    
                    # FIXED: Auto-scale the X-axis to show recent data with proper time scaling
                    time_span = max(time_list) - min(time_list)
                    if time_span > 120:  # If more than 2 minutes of data, show last 2 minutes
                        x_min = max(time_list) - 120
                        x_max = max(time_list)
                        self.graph_widget.setXRange(x_min, x_max)
                        print(f"X-AXIS: Showing last 2 minutes ({x_min:.1f}s - {x_max:.1f}s)")
                    elif time_span > 1:  # Show all data if less than 2 minutes
                        x_min = min(time_list)
                        x_max = max(time_list) + 5  # Add 5s padding
                        self.graph_widget.setXRange(x_min, x_max)
                        print(f"X-AXIS: Showing all data ({x_min:.1f}s - {x_max:.1f}s)")
                    
                    # Force graph update
                    self.graph_widget.update()
                
                else:
                    print(f"GRAPH DEBUG: Not enough data points yet (need 2+)")
                
            except Exception as graph_error:
                print(f"GRAPH ERROR: Failed to update graph: {graph_error}")
                import traceback
                traceback.print_exc()
            
            self.last_telemetry_update = current_time
            
        except json.JSONDecodeError as e:
            print(f"TELEMETRY ERROR: JSON decode failed: {e}")
        except Exception as e:
            print(f"TELEMETRY ERROR: Processing failed: {e}")
            import traceback
            traceback.print_exc()

    def check_voltage_alarms(self, voltage):
        """Check and display voltage alarms"""
        current_alarm = None
        
        if voltage < 11.0:
            current_alarm = "CRITICAL"
        elif voltage < 12.0:
            current_alarm = "LOW"
        
        # Only show popup if alarm state changed
        if current_alarm != self.last_voltage_alarm and current_alarm is not None:
            if current_alarm == "CRITICAL":
                QMessageBox.critical(self, "Battery Critical", 
                                   f"⚠️ CRITICAL: Battery voltage is {voltage:.2f}V!\nLand immediately to prevent damage!")
            elif current_alarm == "LOW":
                QMessageBox.warning(self, "Battery Low", 
                                  f"⚠️ WARNING: Battery voltage is {voltage:.2f}V\nConsider landing soon.")
        
        self.last_voltage_alarm = current_alarm

    def send_failsafe(self):
        """Send failsafe command to backend"""
        if hasattr(self.websocket, 'send_safe'):
            self.websocket.send_safe(json.dumps({"type": "failsafe"}))
        else:
            try:
                self.websocket.sendTextMessage(json.dumps({"type": "failsafe"}))
            except Exception as e:
                print(f"Failed to send failsafe command: {e}")

    def reload_settings(self):
        """Reload settings if needed"""
        print("HealthScreen: Settings reloaded")
    
    def reset_graph_time(self):
        """Reset the graph time scale to start from 0"""
        self.start_time = time.time()
        self.time_data.clear()
        self.battery_voltage_data.clear()
        self.current_a0_data.clear()
        self.current_a1_data.clear()
        
        # Clear the graph plots
        self.voltage_curve.clear()
        self.current_a0_plot.clear()
        self.current_a1_plot.clear()
        
        print("Graph time scale reset")

    def get_battery_health_summary(self):
        """Get battery health summary for display"""
        if not self.battery_voltage_data:
            return "No battery data"
        
        current_voltage = self.battery_voltage_data[-1]
        if len(self.battery_voltage_data) > 10:
            avg_voltage = sum(list(self.battery_voltage_data)[-10:]) / 10
            voltage_trend = "↗️" if current_voltage > avg_voltage else "↘️" if current_voltage < avg_voltage else "➡️"
        else:
            voltage_trend = "➡️"
        
        # Estimate remaining capacity (rough approximation for 4S LiPo)
        if current_voltage > 15.0:
            capacity = "90-100%"
        elif current_voltage > 14.4:
            capacity = "75-90%"
        elif current_voltage > 13.8:
            capacity = "50-75%"
        elif current_voltage > 13.2:
            capacity = "25-50%"
        elif current_voltage > 12.6:
            capacity = "10-25%"
        else:
            capacity = "<10%"
        
        return f"{voltage_trend} Est. Capacity: {capacity}"

class ServoConfigScreen(QWidget):
    """Fixed Servo Configuration Screen with proper thread safety and initialization"""
    
    # Qt signals for thread-safe communication
    position_update_signal = pyqtSignal(str, int)  # channel_key, position
    status_update_signal = pyqtSignal(str, bool, bool)  # message, error, warning
    
    def __init__(self, websocket):
        super().__init__()
        self.websocket = websocket
        self.setFixedWidth(1180)
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        self.servo_config = self.load_config()
        self.active_sweeps = {}  # Track multiple active sweeps by channel
        
        # Track channel counts for each Maestro with defensive defaults
        self.maestro_channel_counts = {1: 0, 2: 0}  # Start with 0, detect later
        self.maestro_connected = {1: False, 2: False}  # Track connection status
        self.current_maestro = 0  # 0=Maestro1, 1=Maestro2
        self.initialization_complete = False
        
        # Track servo widgets for position updates
        self.servo_widgets = {}
        
        # Timer for batch position updates
        self.position_update_timer = QTimer()
        self.position_update_timer.timeout.connect(self.update_all_positions)
        self.position_update_timer.setInterval(500)
        self.auto_update_positions = False
        
        # Position reading state
        self.reading_positions = False
        self.position_read_timeout = QTimer()
        self.position_read_timeout.timeout.connect(self.handle_position_read_timeout)
        self.position_read_timeout.setSingleShot(True)
        
        # Maestro selector setup
        self.setup_maestro_selectors()
        self.setup_control_buttons()
        self.setup_position_controls()
        
        # Connect Qt signals for thread safety
        self.position_update_signal.connect(self.update_servo_position_display)
        self.status_update_signal.connect(self.update_status_threadsafe)
        
        # Layout setup
        self.setup_layout()
        
        # Connect to WebSocket for responses
        self.websocket.textMessageReceived.connect(self.handle_websocket_message)
        
        # Initialize only after everything is set up
        QTimer.singleShot(200, self.safe_initialization)
        
    def setup_maestro_selectors(self):
        """Setup maestro selection buttons"""
        self.maestro1_btn = QPushButton()
        self.maestro2_btn = QPushButton()
        self.maestro1_btn.setCheckable(True)
        self.maestro2_btn.setCheckable(True)
        
        # Load icons if they exist
        if os.path.exists("icons/M1.png"):
            self.maestro1_btn.setIcon(QIcon("icons/M1.png"))
            self.maestro1_btn.setIconSize(QSize(112, 118))
        if os.path.exists("icons/M2.png"):
            self.maestro2_btn.setIcon(QIcon("icons/M2.png"))
            self.maestro2_btn.setIconSize(QSize(112, 118))
        
        self.maestro_group = QButtonGroup()
        self.maestro_group.setExclusive(True)
        self.maestro_group.addButton(self.maestro1_btn, 0)
        self.maestro_group.addButton(self.maestro2_btn, 1)
        self.maestro_group.idClicked.connect(self.on_maestro_changed)
        
        # Default to Maestro 1
        self.maestro1_btn.setChecked(True)
        self.update_maestro_icons(0)
        
    def setup_control_buttons(self):
        """Setup control buttons with clearer labels"""
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Refresh Maestro connection and reload servo config")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #444;
                color: white;
                border-radius: 12px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        self.refresh_btn.setMinimumSize(100, 40)
        self.refresh_btn.clicked.connect(self.refresh_current_maestro)
        
    def setup_position_controls(self):
        """Setup controls for position reading"""
        # Auto-update checkbox
        self.auto_update_checkbox = QCheckBox("Auto-refresh")
        self.auto_update_checkbox.setChecked(False)
        self.auto_update_checkbox.setFont(QFont("Arial", 14))
        self.auto_update_checkbox.setStyleSheet("color: white;")
        self.auto_update_checkbox.setToolTip("Automatically read positions every 500ms")
        self.auto_update_checkbox.toggled.connect(self.toggle_auto_update)
        
        # Manual refresh button
        self.read_positions_btn = QPushButton("Read Positions")
        self.read_positions_btn.setFont(QFont("Arial", 14))
        self.read_positions_btn.setToolTip("Read current servo positions from selected Maestro")
        self.read_positions_btn.clicked.connect(self.read_all_positions_now)
        self.read_positions_btn.setStyleSheet("""
            QPushButton {
                background-color: #444;
                color: white;
                border-radius: 8px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        
        # Enable/Disable all live checkboxes
        self.toggle_all_live_btn = QPushButton("Toggle Live")
        self.toggle_all_live_btn.setFont(QFont("Arial", 14))
        self.toggle_all_live_btn.clicked.connect(self.toggle_all_live_checkboxes)
        self.toggle_all_live_btn.setStyleSheet("""
            QPushButton {
                background-color: #444;
                color: white;
                border-radius: 8px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        
        # Status label
        self.status_label = QLabel("Initializing...")
        self.status_label.setFont(QFont("Arial", 12))
        self.status_label.setStyleSheet("color: #FFAA00; padding: 3px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFixedWidth(1050) 
        
    def setup_layout(self):
        """Setup the complete layout"""
        # Scrollable grid area
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_layout.setContentsMargins(2, 5, 2, 5)
        self.grid_layout.setVerticalSpacing(6)
        self.grid_widget.setLayout(self.grid_layout)
        self.grid_widget.setStyleSheet("QWidget { border: 1px solid #555; border-radius: 12px; }")
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setWidget(self.grid_widget)
        
        # Create a vertical layout to center the maestro selector
        selector_container = QVBoxLayout()
        selector_container.addStretch()
        selector_container.addWidget(self.maestro1_btn)
        selector_container.addWidget(self.maestro2_btn)
        selector_container.addSpacing(20)
        selector_container.addWidget(self.refresh_btn)
        selector_container.addSpacing(10)
        selector_container.addWidget(self.auto_update_checkbox)
        selector_container.addWidget(self.read_positions_btn)
        selector_container.addWidget(self.toggle_all_live_btn)
        selector_container.addStretch()
        
        selector_widget = QWidget()
        selector_widget.setLayout(selector_container)
        selector_widget.setStyleSheet("background-color: rgba(0, 0, 0, 0);")
        
        # Main layout
        grid_and_selector_layout = QHBoxLayout()
        grid_and_selector_layout.addSpacing(5)
        grid_and_selector_layout.addWidget(scroll_area, stretch=5)
        grid_and_selector_layout.addWidget(selector_widget)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(90, 10, 10, 5)
        status_container = QHBoxLayout()
        status_container.addStretch()
        status_container.addWidget(self.status_label)
        status_container.addStretch()
        layout.addLayout(status_container)
        layout.addLayout(grid_and_selector_layout)
        self.setLayout(layout)
        
    def safe_initialization(self):
        """Safe initialization that only queries the selected Maestro"""
        try:
            self.update_status("Initializing servo configuration...")
            
            # Check if we already have info for current Maestro
            maestro_num = self.current_maestro + 1
            if self.maestro_connected.get(maestro_num, False) and self.maestro_channel_counts.get(maestro_num, 0) > 0:
                # Already have info, build grid immediately
                self.update_status(f"Using cached info for Maestro {maestro_num}")
                self.update_grid()
                QTimer.singleShot(300, self.read_all_positions_now)
            else:
                # Request fresh info
                self.request_current_maestro_info()
            
        except Exception as e:
            print(f"Initialization error: {e}")
            self.update_status(f"Initialization failed: {str(e)}", error=True)
    
    def request_current_maestro_info(self):
        """Request information only for the currently selected Maestro"""
        maestro_num = self.current_maestro + 1
        self.update_status(f"Detecting Maestro {maestro_num} controller...")
        
        # Send request only for selected Maestro
        message = json.dumps({
            "type": "get_maestro_info",
            "maestro": maestro_num
        })
        
        if hasattr(self.websocket, 'send_safe'):
            self.websocket.send_safe(message)
        else:
            try:
                self.websocket.sendTextMessage(message)
            except Exception as e:
                self.update_status(f"Failed to request Maestro info: {e}", error=True)
        
        print(f"Requested info for Maestro {maestro_num} only")
    
    def refresh_current_maestro(self):
        """Refresh only the currently selected Maestro"""
        # Stop any active operations
        self.stop_all_sweeps()
        if self.auto_update_positions:
            self.position_update_timer.stop()
        
        # Clear current state
        self.maestro_connected[self.current_maestro + 1] = False
        self.maestro_channel_counts[self.current_maestro + 1] = 0
        
        # Request fresh info
        self.request_current_maestro_info()
        self.reload_servo_config()
        
    @error_boundary
    def handle_websocket_message(self, message):
        """Handle incoming WebSocket messages with proper routing"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "maestro_info":
                maestro_num = data.get("maestro")
                channels = data.get("channels", 0)
                connected = data.get("connected", False)
                
                if maestro_num in [1, 2]:
                    self.maestro_channel_counts[maestro_num] = channels
                    self.maestro_connected[maestro_num] = connected
                    print(f"Maestro {maestro_num}: {channels} channels, connected: {connected}")
                    
                    if connected:
                        self.update_status(f"Maestro {maestro_num}: {channels} channels detected")
                        # Only update grid if this is the currently selected Maestro
                        if maestro_num == self.current_maestro + 1:
                            self.update_grid()
                            # Read initial positions after short delay
                            QTimer.singleShot(500, self.read_all_positions_now)
                    else:
                        self.update_status(f"Maestro {maestro_num}: Not connected", error=True)
            
            elif msg_type == "servo_position":
                channel_key = data.get("channel")
                position = data.get("position")
                
                if channel_key and position is not None:
                    # Use Qt signal for thread-safe update
                    self.position_update_signal.emit(channel_key, position)
                    
                    # Notify active sweeps
                    if channel_key in self.active_sweeps:
                        try:
                            self.active_sweeps[channel_key].position_reached(position)
                        except Exception as e:
                            print(f"Error updating sweep position for {channel_key}: {e}")
                            if channel_key in self.active_sweeps:
                                self.active_sweeps[channel_key].stop()
                                del self.active_sweeps[channel_key]
            
            elif msg_type == "all_servo_positions":
                maestro_num = data.get("maestro")
                positions = data.get("positions", {})
                
                # Only process if this is for the currently selected Maestro
                if maestro_num == self.current_maestro + 1:
                    print(f"Received {len(positions)} positions for Maestro {maestro_num}")
                    
                    self.reading_positions = False
                    self.position_read_timeout.stop()
                    
                    # Update all positions using Qt signals
                    for channel, position in positions.items():
                        channel_key = f"m{maestro_num}_ch{channel}"
                        if position is not None:
                            self.position_update_signal.emit(channel_key, position)
                    
                    if len(positions) > 0:
                        self.update_status(f"Read {len(positions)} positions from Maestro {maestro_num}")
                    else:
                        self.update_status(f"No positions received from Maestro {maestro_num}", warning=True)
                        
        except Exception as e:
            print(f"Error handling WebSocket message: {e}")
    
    def update_servo_position_display(self, channel_key, position):
        """Thread-safe method to update servo position display"""
        if channel_key in self.servo_widgets:
            widgets = self.servo_widgets[channel_key]
            slider = widgets[0]
            pos_label = widgets[1]
            
            # Update slider position without triggering servo movement
            slider.blockSignals(True)
            slider.setValue(position)
            slider.blockSignals(False)
            
            # Update position label
            pos_label.setText(f"V: {position}")
            pos_label.setStyleSheet("color: #44FF44;")
            
            print(f"Updated display: {channel_key} = {position}")
    
    def update_status_threadsafe(self, message, error=False, warning=False):
        """Thread-safe status update"""
        self.status_label.setText(message)
        
        if error:
            self.status_label.setStyleSheet("color: #FF4444; padding: 3px;")
        elif warning:
            self.status_label.setStyleSheet("color: #FFAA00; padding: 3px;")
        else:
            self.status_label.setStyleSheet("color: #44FF44; padding: 3px;")
        
        print(f"Status: {message}")
    
    def update_status(self, message, error=False, warning=False):
        """Update status using Qt signal for thread safety"""
        self.status_update_signal.emit(message, error, warning)
    
    def on_maestro_changed(self, maestro_index):
        """Handle maestro selection change with proper cleanup"""
        if maestro_index == self.current_maestro:
            return  # No change needed
        
        # Stop current operations
        self.stop_all_sweeps()
        if self.auto_update_positions:
            self.position_update_timer.stop()
        
        # Update selection
        old_maestro = self.current_maestro
        self.current_maestro = maestro_index
        self.update_maestro_icons(maestro_index)
        
        # Clear old grid
        self.clear_grid()
        
        maestro_num = maestro_index + 1
        
        # Check if we already have info for this Maestro
        if self.maestro_connected.get(maestro_num, False):
            channels = self.maestro_channel_counts.get(maestro_num, 0)
            self.update_status(f"Switched to Maestro {maestro_num}: {channels} channels")
            self.update_grid()
            QTimer.singleShot(200, self.read_all_positions_now)
        else:
            # Request info for newly selected Maestro
            self.update_status(f"Loading Maestro {maestro_num}...")
            self.request_current_maestro_info()
        
        print(f"Switched from Maestro {old_maestro + 1} to Maestro {maestro_num}")
    
    def clear_grid(self):
        """Clear the current grid and widget tracking"""
        # Clear existing widgets
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        
        self.servo_widgets.clear()
    
    def update_grid(self):
        """Build servo control grid for currently selected Maestro only"""
        maestro_num = self.current_maestro + 1
        channel_count = self.maestro_channel_counts.get(maestro_num, 0)
        
        if channel_count == 0:
            self.update_status(f"Maestro {maestro_num} not available", error=True)
            return
        
        print(f"Building grid for Maestro {maestro_num} with {channel_count} channels")
        
        # Stop any active updates while rebuilding
        if self.auto_update_positions:
            self.position_update_timer.stop()
        
        # Clear existing content
        self.clear_grid()
        
        font = QFont("Arial", 14)
        
        # Create grid for detected channels
        for i in range(channel_count):
            channel_key = f"m{maestro_num}_ch{i}"
            config = self.servo_config.get(channel_key, {})
            row = i
            
            # Channel number
            label = QLabel(f"Ch{i}")
            label.setFont(font)
            label.setFixedWidth(35)
            self.grid_layout.addWidget(label, row, 0)
            
            # Name edit
            name_edit = QLineEdit(config.get("name", ""))
            name_edit.setFont(QFont("Arial", 16))
            name_edit.setMaxLength(25)
            name_edit.setFixedWidth(180)
            name_edit.setPlaceholderText("Servo Name")
            name_edit.textChanged.connect(lambda text, k=channel_key: self.update_config(k, "name", text))
            self.grid_layout.addWidget(name_edit, row, 1)
            
            # Slider for position control
            slider = QSlider(Qt.Orientation.Horizontal)
            min_val = config.get("min", 992)
            max_val = config.get("max", 2000)
            slider.setMinimum(min_val)
            slider.setMaximum(max_val)
            slider.setValue((min_val + max_val) // 2)
            slider.setFixedWidth(150)
            slider.setMinimumHeight(24)
            self.grid_layout.addWidget(slider, row, 2)
            
            # Min value controls
            min_spin = QSpinBox()
            min_spin.setFont(QFont("Arial", 16))
            min_spin.setRange(0, 2500)
            min_spin.setValue(min_val)
            min_spin.setFixedWidth(60)
            min_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "min", val))
            min_spin.valueChanged.connect(lambda val, s=slider: s.setMinimum(val))
            self.grid_layout.addWidget(min_spin, row, 3)
            
            # Max value controls
            max_spin = QSpinBox()
            max_spin.setFont(QFont("Arial", 16))
            max_spin.setRange(0, 2500)
            max_spin.setValue(max_val)
            max_spin.setFixedWidth(60)
            max_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "max", val))
            max_spin.valueChanged.connect(lambda val, s=slider: s.setMaximum(val))
            self.grid_layout.addWidget(max_spin, row, 4)
            
            # Speed control
            speed_spin = QSpinBox()
            speed_spin.setFont(QFont("Arial", 16))
            speed_spin.setRange(0, 100)
            speed_spin.setValue(config.get("speed", 0))
            speed_spin.setFixedWidth(50)
            speed_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "speed", val))
            self.grid_layout.addWidget(speed_spin, row, 5)
            
            # Acceleration control
            accel_spin = QSpinBox()
            accel_spin.setFont(QFont("Arial", 16))
            accel_spin.setRange(0, 100)
            accel_spin.setValue(config.get("accel", 0))
            accel_spin.setFixedWidth(50)
            accel_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "accel", val))
            self.grid_layout.addWidget(accel_spin, row, 6)
            
            # Position label
            pos_label = QLabel("---")
            pos_label.setFont(QFont("Arial", 16))
            pos_label.setStyleSheet("color: #FFAA00;")
            pos_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pos_label.setFixedWidth(60)
            self.grid_layout.addWidget(pos_label, row, 7)
            
            # Live update checkbox
            live_checkbox = QCheckBox()
            live_checkbox.setChecked(False)
            live_checkbox.setToolTip("Enable live servo updates")
            live_checkbox.setFixedSize(20, 20)
            live_checkbox.setStyleSheet("""
                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                }
                QCheckBox::indicator:unchecked {
                    background-color: #333;
                    border: 1px solid #666;
                    border-radius: 2px;
                }
                QCheckBox::indicator:checked {
                    background-color: #44FF44;
                    border: 1px solid #44FF44;
                    border-radius: 2px;
                }
            """)
            self.grid_layout.addWidget(live_checkbox, row, 8)
            
            # Play/sweep button
            play_btn = QPushButton("▶")
            play_btn.setFont(QFont("Arial", 12))
            play_btn.setCheckable(True)
            play_btn.setFixedSize(30, 30)
            play_btn.clicked.connect(
                lambda checked, k=channel_key, p=pos_label, b=play_btn,
                min_spin=min_spin, max_spin=max_spin, speed_spin=speed_spin:
                self.toggle_sweep_minmax(k, p, b, min_spin.value(), max_spin.value(), speed_spin.value())
            )
            self.grid_layout.addWidget(play_btn, row, 9)
            
            # Connect slider to servo movement
            slider.valueChanged.connect(
                lambda val, k=channel_key, p=pos_label, cb=live_checkbox:
                self.update_servo_position_conditionally(k, p, val, cb)
            )
            
            # Track widgets for position updates
            self.servo_widgets[channel_key] = (slider, pos_label, play_btn, live_checkbox, name_edit)
        
        # Update status
        self.update_status(f"Maestro {maestro_num}: {channel_count} channels loaded")
        
        # Restart auto-updates if enabled
        if self.auto_update_positions:
            self.position_update_timer.start()
    
    def toggle_auto_update(self, enabled):
        """Toggle automatic position updates for current Maestro only"""
        self.auto_update_positions = enabled
        
        if enabled:
            # Only start if we have a valid current Maestro
            maestro_num = self.current_maestro + 1
            if self.maestro_connected.get(maestro_num, False):
                self.position_update_timer.start()
                self.update_status("Auto-refresh positions: ON")
                print("Auto position updates enabled")
            else:
                self.auto_update_checkbox.setChecked(False)
                self.auto_update_positions = False
                self.update_status("No valid Maestro for auto-refresh", warning=True)
        else:
            self.position_update_timer.stop()
            self.update_status("Auto-refresh positions: OFF")
            print("Auto position updates disabled")
    
    def update_all_positions(self):
        """Update all servo positions for current Maestro only"""
        if not self.auto_update_positions or self.reading_positions:
            return
        
        maestro_num = self.current_maestro + 1
        
        # Only update if current Maestro is connected and we have servo widgets
        if not self.maestro_connected.get(maestro_num, False) or not self.servo_widgets:
            return
        
        message = json.dumps({
            "type": "get_all_servo_positions",
            "maestro": maestro_num
        })
        
        if hasattr(self.websocket, 'send_safe'):
            self.websocket.send_safe(message)
        else:
            try:
                self.websocket.sendTextMessage(message)
            except Exception as e:
                print(f"Failed to send auto position request: {e}")
                return
        
        print(f"Auto-updating positions for Maestro {maestro_num}")
    
    def read_all_positions_now(self):
        """Manually read all servo positions for current Maestro"""
        if self.reading_positions:
            print("Already reading positions, skipping...")
            return
        
        maestro_num = self.current_maestro + 1
        
        if not self.maestro_connected.get(maestro_num, False):
            self.update_status(f"Maestro {maestro_num} not connected", error=True)
            return
        
        self.reading_positions = True
        self.position_read_timeout.start(3000)
        
        message = json.dumps({
            "type": "get_all_servo_positions",
            "maestro": maestro_num
        })
        
        if hasattr(self.websocket, 'send_safe'):
            self.websocket.send_safe(message)
        else:
            try:
                self.websocket.sendTextMessage(message)
            except Exception as e:
                print(f"Failed to send position request: {e}")
                self.reading_positions = False
                self.position_read_timeout.stop()
                return
        
        self.update_status(f"Reading positions from Maestro {maestro_num}...")
        print(f"Requested all positions from Maestro {maestro_num}")
    
    def handle_position_read_timeout(self):
        """Handle timeout when reading positions"""
        self.reading_positions = False
        maestro_num = self.current_maestro + 1
        
        print(f"Timeout reading positions from Maestro {maestro_num}")
        self.update_status(f"Maestro {maestro_num} not responding - check connection", error=True)
        
        # Set all sliders to center position as fallback
        for channel_key, widgets in self.servo_widgets.items():
            if channel_key.startswith(f"m{maestro_num}_"):
                slider = widgets[0]
                pos_label = widgets[1]
                
                center = (slider.minimum() + slider.maximum()) // 2
                slider.blockSignals(True)
                slider.setValue(center)
                slider.blockSignals(False)
                
                pos_label.setText(f"V: {center}")
                pos_label.setStyleSheet("color: #FFAA00;")
    
    def update_servo_position_conditionally(self, channel_key, pos_label, value, live_checkbox):
        """Update servo position only if live checkbox is checked"""
        pos_label.setText(f"V: {value}")
        
        if live_checkbox.isChecked():
            self.update_servo_position(channel_key, pos_label, value)
            pos_label.setStyleSheet("color: #FF4444;")
        else:
            pos_label.setStyleSheet("color: #AAAAAA;")
    
    def update_servo_position(self, channel_key, pos_label, value):
        """Send servo position command with configuration"""
        config = self.servo_config.get(channel_key, {})
        speed = config.get("speed", 0)
        accel = config.get("accel", 0)
        
        # Always apply speed setting (including 0 to disable speed limit)
        speed_message = json.dumps({
            "type": "servo_speed",
            "channel": channel_key,
            "speed": speed
        })
        self.websocket.send_safe(speed_message)
        
        # Always apply acceleration setting (including 0 to disable acceleration limit)  
        accel_message = json.dumps({
            "type": "servo_acceleration",
            "channel": channel_key,
            "acceleration": accel
        })
        self.websocket.send_safe(accel_message)
        
        # Send position command
        self.websocket.send_safe(json.dumps({
            "type": "servo",
            "channel": channel_key,
            "pos": value
        }))
        
        print(f"Servo command: {channel_key} → {value} (speed: {speed}, accel: {accel})")
    
    def toggle_sweep_minmax(self, channel_key, pos_label, button, min_val, max_val, speed):
        """Toggle min/max sweep for a servo channel using configured values"""
        if channel_key in self.active_sweeps:
            # Stop existing sweep
            self.active_sweeps[channel_key].stop()
            del self.active_sweeps[channel_key]
            button.setText("▶")
            button.setChecked(False)
            print(f"Stopped sweep for {channel_key}")
            return
        
        # Get actual configured min/max values from servo config (not spin boxes)
        config = self.servo_config.get(channel_key, {})
        actual_min = config.get("min", 992)
        actual_max = config.get("max", 2000) 
        actual_speed = config.get("speed", speed)  # Use config speed if available
        
        print(f"Starting sweep for {channel_key}: min={actual_min}, max={actual_max}, speed={actual_speed}")
        
        # Create new sweep with actual configured values
        sweep = MinMaxSweep(self, channel_key, pos_label, button, actual_min, actual_max, actual_speed)
        self.active_sweeps[channel_key] = sweep
        button.setText("⏸")
        print(f"Started sweep for {channel_key}")
    
    def toggle_all_live_checkboxes(self):
        """Toggle all live update checkboxes"""
        any_checked = False
        for widgets in self.servo_widgets.values():
            if len(widgets) > 3 and widgets[3].isChecked():
                any_checked = True
                break
        
        new_state = not any_checked
        for widgets in self.servo_widgets.values():
            if len(widgets) > 3:
                widgets[3].setChecked(new_state)
        
        status = "enabled" if new_state else "disabled"
        self.update_status(f"All live updates {status}")
        print(f"Toggled all live checkboxes to: {new_state}")
    
    def stop_all_sweeps(self):
        """Stop any active sweeps"""
        for channel_key, sweep in list(self.active_sweeps.items()):
            sweep.stop()
        self.active_sweeps.clear()
        print("All sweeps stopped")
    
    @error_boundary
    def update_maestro_icons(self, checked_id):
        """Update button icons based on selection"""
        if self.maestro_group.checkedId() == 0:
            if os.path.exists("icons/M1_pressed.png"):
                self.maestro1_btn.setIcon(QIcon("icons/M1_pressed.png"))
            if os.path.exists("icons/M2.png"):
                self.maestro2_btn.setIcon(QIcon("icons/M2.png"))
        else:
            if os.path.exists("icons/M1.png"):
                self.maestro1_btn.setIcon(QIcon("icons/M1.png"))
            if os.path.exists("icons/M2_pressed.png"):
                self.maestro2_btn.setIcon(QIcon("icons/M2_pressed.png"))
    
    @error_boundary
    def load_config(self):
        """Load servo configuration from file"""
        return config_manager.get_config("configs/servo_config.json")
    
    @error_boundary
    def save_config(self):
        """Save servo configuration to file"""
        with open("configs/servo_config.json", "w") as f:
            json.dump(self.servo_config, f, indent=2)
        config_manager.clear_cache()
    
    @error_boundary
    def reload_servo_config(self):
        """Reload servo configuration and update grid"""
        config_manager.clear_cache()
        self.servo_config = config_manager.get_config("configs/servo_config.json")
        if hasattr(self, 'grid_layout'):
            self.update_grid()
        print("Servo config reloaded successfully.")
    
    def update_config(self, key, field, value):
        """Update configuration for a specific servo channel"""
        if key not in self.servo_config:
            self.servo_config[key] = {}
        self.servo_config[key][field] = value
        self.save_config()


class MinMaxSweep:
    """Fixed Min/Max sweep class with thread-safe callbacks and proper timing"""
    
    def __init__(self, parent_screen, channel_key, label, btn, minv, maxv, speedv):
        self.parent_screen = parent_screen
        self.channel_key = channel_key
        self.label = label
        self.btn = btn
        self.min_val = minv
        self.max_val = maxv
        self.speed = speedv
        
        # State tracking
        self.current_target = None
        self.going_to_max = True
        self.position_tolerance = 1
        self.check_interval = 100
        self.hold_delay = 1000  # 500ms delay at each end
        
        # Timers
        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.check_position)
        
        self.hold_timer = QTimer()
        self.hold_timer.setSingleShot(True)
        self.hold_timer.timeout.connect(self.continue_after_hold)
        
        self.start_sweep()
        print(f"Starting min/max sweep on {channel_key}: {minv}↔{maxv}, speed={speedv}")
    
    def start_sweep(self):
        """Start the sweep by configuring servo and moving to first target"""
        # Apply speed setting if specified
        if self.speed >= 0:
            speed_message = json.dumps({
                "type": "servo_speed",
                "channel": self.channel_key,
                "speed": self.speed
            })
            if hasattr(self.parent_screen.websocket, 'send_safe'):
                self.parent_screen.websocket.send_safe(speed_message)
        
        # Apply acceleration from config
        config = self.parent_screen.servo_config.get(self.channel_key, {})
        accel = config.get("accel", 0)
        if accel >= 0:  # Send even if 0
            accel_message = json.dumps({
                "type": "servo_acceleration",
                "channel": self.channel_key,
                "acceleration": accel
            })
            if hasattr(self.parent_screen.websocket, 'send_safe'):
                self.parent_screen.websocket.send_safe(accel_message)
        
        # Move to first target (max)
        self.move_to_next_target()
        
        # Start position checking
        self.check_timer.start(self.check_interval)
    
    def move_to_next_target(self):
        """Move to the next target position"""
        if self.going_to_max:
            self.current_target = self.max_val
            print(f"{self.channel_key} → MAX ({self.max_val})")
        else:
            self.current_target = self.min_val
            print(f"{self.channel_key} → MIN ({self.min_val})")
        
        # Send move command
        move_message = json.dumps({
            "type": "servo",
            "channel": self.channel_key,
            "pos": self.current_target
        })
        if hasattr(self.parent_screen.websocket, 'send_safe'):
            self.parent_screen.websocket.send_safe(move_message)
        
        # Update UI
        self.label.setText(f"→{self.current_target}")
        self.label.setStyleSheet("color: #FFFF44;")
    
    def check_position(self):
        """Request current position for sweep validation"""
        message = json.dumps({
            "type": "get_servo_position",
            "channel": self.channel_key
        })
        
        if hasattr(self.parent_screen.websocket, 'send_safe'):
            self.parent_screen.websocket.send_safe(message)
        else:
            try:
                self.parent_screen.websocket.sendTextMessage(message)
            except Exception as e:
                print(f"Failed to request position for sweep {self.channel_key}: {e}")
    
    def position_reached(self, actual_position):
        """Called when position update received - thread-safe"""
        if self.current_target is None:
            return
        
        # Check if we've reached the target
        if actual_position == self.current_target:
            print(f"✅ {self.channel_key} reached {self.current_target} precisely")
            
            # Update UI to show reached
            self.label.setText(f"@{actual_position}")
            self.label.setStyleSheet("color: #44FF44;")
            
            # Stop position checking during hold delay
            self.check_timer.stop()
            
            # Start 500ms hold timer before switching direction
            self.hold_timer.start(self.hold_delay)
            
        else:
            # Still moving, update display
            self.label.setText(f"V:{actual_position}")
            self.label.setStyleSheet("color: #FFAA44;")
            print(f"{self.channel_key}: {actual_position}/{self.current_target}")
    
    def continue_after_hold(self):
        """Continue sweep after 500ms hold delay"""
        # Switch direction
        self.going_to_max = not self.going_to_max
        
        # Move to next target
        self.move_to_next_target()
        
        # Resume position checking
        self.check_timer.start(self.check_interval)
    
    def stop(self):
        """Stop the sweep and return to center"""
        self.check_timer.stop()
        self.hold_timer.stop()
        
        # Return to center position
        center_pos = (self.min_val + self.max_val) // 2
        stop_message = json.dumps({
            "type": "servo",
            "channel": self.channel_key,
            "pos": center_pos
        })
        if hasattr(self.parent_screen.websocket, 'send_safe'):
            self.parent_screen.websocket.send_safe(stop_message)
        
        # Update UI
        self.label.setText(f"C:{center_pos}")
        self.label.setStyleSheet("color: #AAAAAA;")
        self.btn.setText("▶")
        self.btn.setChecked(False)
        
        print(f"Min/Max sweep stopped: {self.channel_key} returned to center ({center_pos})")


class PlaceholderScreen(QWidget):
    def __init__(self, title):
        super().__init__()
        self.setFixedSize(1280, 800)
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        label = QLabel(f"{title} Screen Coming Soon")
        label.setFont(QFont("Arial", 24))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout()
        layout.addWidget(label)
        self.setLayout(layout)


class HomeScreen(QWidget):
    def __init__(self, websocket):
        super().__init__()
        self.websocket = websocket
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(80, 20, 90, 5)

        # WALL-E image on the left
        image_container = QVBoxLayout()
        image_container.addStretch()
        self.image_label = QLabel()
        if os.path.exists("walle.png"):
            self.image_label.setPixmap(QPixmap("walle.png").scaled(400, 400, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignBottom)
        image_container.addWidget(self.image_label)

        image_widget = QWidget()
        image_widget.setLayout(image_container)
        image_widget.setStyleSheet("background-color: rgba(0, 0, 0, 0);")
        layout.addWidget(image_widget)

        # Scrollable area for emotion buttons
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

        # Create Idle and Demo Mode buttons
        mode_frame = QFrame()
        mode_frame.setStyleSheet("QFrame { border: 0px solid #555; border-radius: 12px; background-color: #1e1e1e; }")
        mode_layout = QHBoxLayout(mode_frame)
        mode_layout.setContentsMargins(10, 10, 10, 10)

        self.idle_button = QPushButton("🛋️ Idle Mode")
        self.demo_button = QPushButton("🎬 Demo Mode")
        self.idle_button.toggled.connect(lambda checked: self.send_mode_state("idle", checked))
        self.demo_button.toggled.connect(lambda checked: self.send_mode_state("demo", checked))

        for btn in [self.idle_button, self.demo_button]:
            btn.setCheckable(True)
            btn.setFont(QFont("Arial", 18))
            btn.setMinimumSize(120, 40)
            btn.setStyleSheet("""
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
            """)
            mode_layout.addWidget(btn)

        # Add both sections to the right layout
        right_layout = QVBoxLayout()
        right_layout.addWidget(scroll_area)
        right_layout.addSpacing(5)

        mode_container = QWidget()
        mode_container_layout = QHBoxLayout()
        mode_container_layout.addSpacing(20)
        mode_container_layout.addWidget(mode_frame)
        mode_container_layout.addSpacing(20)
        mode_container.setLayout(mode_container_layout)
        mode_container.setStyleSheet("background-color: rgba(0, 0, 0, 0);")

        right_layout.addWidget(mode_container)
        layout.addLayout(right_layout)
        self.setLayout(layout)
        self.load_emotion_buttons()

    @error_boundary
    def load_emotion_buttons(self):
        # Clear existing buttons
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        
        config = config_manager.get_config("configs/emotion_buttons.json")
        emotions = config if isinstance(config, list) else []

        font = QFont("Arial", 18)
        for idx, item in enumerate(emotions):
            label = item.get("label", "Unknown")
            emoji = item.get("emoji", "")
            btn = QPushButton(f"{emoji} {label}")
            btn.setFont(font)
            btn.setStyleSheet("""
            QPushButton {
                background-color: #444;
                color: white;
                border-radius: 12px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #666;
            }
            """)
            btn.setMinimumSize(120, 40)
            btn.clicked.connect(lambda _, name=label: self.send_emotion(name))
            row = idx // 2
            col = idx % 2
            self.grid_layout.addWidget(btn, row, col)

    @error_boundary
    def send_emotion(self, name):
        self.websocket.send_safe(json.dumps({"type": "scene", "emotion": name}))

    @error_boundary
    def send_mode_state(self, mode, state):
        self.websocket.send_safe(json.dumps({
            "type": "mode",
            "name": mode,
            "state": state
        }))

class CameraControlsWidget(QWidget):
    """Camera controls panel for adjusting ESP32 camera settings"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        config = config_manager.get_config("configs/steamdeck_config.json")
        raw_url = config.get("current", {}).get("camera_proxy_url", "http://10.1.1.230:8081")
        self.proxy_base_url = raw_url.replace("/stream", "")  # Remove trailing /stream if present
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
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid white;
                margin-right: 5px;
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
            "QQVGA(160x120)",   # 0
            "QCIF(176x144)",    # 1
            "HQVGA(240x176)",   # 2
            "QVGA(320x240)",    # 3
            "CIF(400x296)",     # 4
            "VGA(640x480)",     # 5
            "SVGA(800x600)",    # 6
            "XGA(1024x768)",    # 7
            "SXGA(1280x1024)",  # 8
            "UXGA(1600x1200)"   # 9
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
            "Quality:", 4, 63, 12, "quality",
            inverted=True  # Lower value = better quality
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
        
        self.h_mirror_btn = QPushButton("↔ Horizontal")
        self.h_mirror_btn.setCheckable(True)
        self.h_mirror_btn.setFixedWidth(125)
        self.h_mirror_btn.clicked.connect(
            lambda checked: self.update_setting("h_mirror", checked)
        )
        
        self.v_flip_btn = QPushButton("↕ Vertical")
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
        reset_btn = QPushButton("🔄 Reset to Defaults")
        reset_btn.clicked.connect(self.reset_to_defaults)
        main_layout.addWidget(reset_btn)
        
        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #888; font-size: 12px;")
        main_layout.addWidget(self.status_label)
        
        main_layout.addStretch()
        self.setLayout(main_layout)
        
    def create_slider_control(self, label_text, min_val, max_val, default_val, setting_name, inverted=False):
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
            response = requests.get(
                f"{self.proxy_base_url}/camera/settings",
                timeout=3
            )
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
                
                self.status_label.setText("✅ Settings loaded")
                print(f"📷 Loaded camera settings: {settings}")
                
        except Exception as e:
            self.status_label.setText(f"⚠️ Failed to load settings")
            print(f"Failed to load camera settings: {e}")
    
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
                self.status_label.setText(f"✅ Updated {setting_name}")
                self.current_settings[setting_name] = value
                print(f"📷 Updated {setting_name} = {value}")
            else:
                self.status_label.setText(f"❌ Failed to update {setting_name}")
                
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)[:50]}")
            print(f"Failed to update {setting_name}: {e}")
    
    @error_boundary
    def reset_to_defaults(self):
        """Reset all settings to default values"""
        defaults = {
            "xclk_freq": 10,
            "resolution": 5,  # VGA
            "quality": 12,
            "brightness": 0,
            "contrast": 0,
            "saturation": 0,
            "h_mirror": False,
            "v_flip": False
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
            response = requests.post(
                f"{self.proxy_base_url}/camera/settings",
                json=defaults,
                timeout=3
            )
            if response.status_code == 200:
                self.status_label.setText("✅ Reset to defaults")
                self.current_settings = defaults
            else:
                self.status_label.setText("❌ Failed to reset")
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)[:50]}")
            print(f"Failed to reset to defaults: {e}")

class CameraFeedScreen(QWidget):
    def __init__(self, websocket):
        super().__init__()
        self.websocket = websocket
        self.sample_buffer = deque(maxlen=SAMPLE_DURATION * SAMPLE_RATE)
        self.last_wave_time = 0
        self.last_sample_time = 0
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        self.tracking_enabled = False

        # Stream control state
        self.streaming_enabled = False
        self.stream_can_change_settings = True
        
        # Use camera proxy URL instead of direct ESP32 URL
        config = config_manager.get_config("configs/steamdeck_config.json")
        camera_proxy_url = config.get("current", {}).get("camera_proxy_url", "")

        # Extract base URL for API calls
        self.camera_proxy_base_url = camera_proxy_url.replace("/stream", "") if camera_proxy_url else ""

        self.image_thread = ImageProcessingThread(camera_proxy_url)
        self.image_thread.frame_processed.connect(self.update_display)
        self.image_thread.stats_updated.connect(self.update_stats)
        
        self.init_ui()

        # Start image processing thread but don't auto-start streaming
        self.image_thread.start()
        
        # Check initial stream status
        self.check_stream_status()
        
    def init_ui(self):
        """Optimized UI setup"""
        self.video_label = QLabel()
        self.video_label.setFixedSize(640, 480)
        self.video_label.setStyleSheet("""
            border: 2px solid #555;
            padding: 2px;
            background-color: black;
        """)
        
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
        
        # Control buttons
        self.setup_control_buttons()

        # Camera controls panel
        self.controls_widget = CameraControlsWidget()
        self.controls_widget.setFixedWidth(400)
        self.controls_widget.setMaximumHeight(600)

        self.setup_layout()
        
    
    def setup_control_buttons(self):        
        # Stream Control Button - Primary control
        self.stream_button = QPushButton()
        self.stream_button.setCheckable(True)
        self.stream_button.setChecked(False)
        
        # Load icons for stream control
        if os.path.exists("icons/StreamStart.png"):
            self.stream_start_icon = QIcon("icons/StreamStart.png")
        else:
            self.stream_start_icon = None
            
        if os.path.exists("icons/StreamStop.png"):
            self.stream_stop_icon = QIcon("icons/StreamStop.png")
        else:
            self.stream_stop_icon = None
        
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
        # 👀 Tracking Button - Enables wave detection
        self.tracking_button = QPushButton()
        self.tracking_button.setCheckable(True)
        if os.path.exists("icons/Tracking.png"):
            self.tracking_button.setIcon(QIcon("icons/Tracking.png"))
            self.tracking_button.setIconSize(QSize(200, 80))  # Keep icon size as desired
        

        self.tracking_button.toggled.connect(self.toggle_tracking)
        self.tracking_button.setFixedSize(220, 100)  # Slightly larger than icon
        #Fully transparent background with visual feedback when checked
        self.tracking_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
            }
        """)
        self.tracking_button.setToolTip("Toggle Wave Detection (Click to enable/disable)")
        self.tracking_button.setEnabled(False) 
        
        print("🎮 Camera control buttons initialized")

    def setup_layout(self):
        """Setup optimized layout with properly sized buttons"""
        video_layout = QVBoxLayout()
        video_layout.setContentsMargins(0, 10, 0, 0)
        video_layout.addWidget(self.video_label)
        video_layout.addWidget(self.stats_label)
        
        button_layout = QVBoxLayout()
        button_layout.setSpacing(20)  # Add spacing between buttons
        button_layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # Align to top
        button_layout.addWidget(self.controls_widget)
            
        control_buttons_layout = QHBoxLayout()
        control_buttons_layout.setSpacing(15)  # Space between the two buttons
        control_buttons_layout.addStretch()  # Center the buttons
        control_buttons_layout.addWidget(self.stream_button)  # Stream button on the left
        control_buttons_layout.addWidget(self.tracking_button)  # Tracking button on the right
        control_buttons_layout.addStretch()  # Center the buttons

        button_layout.addLayout(control_buttons_layout)
        button_layout.addStretch()  # Push buttons to top
        
        main_layout = QHBoxLayout()
        main_layout.addSpacing(90)
        main_layout.addLayout(video_layout)  # Give video more space
        main_layout.addLayout(button_layout)  # Buttons take less space
        main_layout.addStretch()  # Add some right margin
        
        self.setLayout(main_layout)

    def update_stream_button_appearance(self):
        """Update the stream button appearance based on current state"""
        if self.streaming_enabled:
            # Stream is ON - show stop button
            if self.stream_stop_icon:
                self.stream_button.setIcon(self.stream_stop_icon)
                self.stream_button.setIconSize(QSize(32, 32)) 
            self.stream_button.setText("🛑 Stop Stream")
            self.stream_button.setToolTip("Click to stop camera stream")
            self.stream_button.setChecked(True)
        else:
            # Stream is OFF - show start button  
            if self.stream_start_icon:
                self.stream_button.setIcon(self.stream_start_icon)
                self.stream_button.setIconSize(QSize(32, 32)) 
            self.stream_button.setText("▶️ Start Stream")
            self.stream_button.setToolTip("Click to start camera stream")
            self.stream_button.setChecked(False)

    @error_boundary
    def toggle_stream(self, checked):
        """Toggle camera stream on/off"""
        self.streaming_enabled = checked
        
        if self.streaming_enabled:
            # Start streaming
            print("📹 Starting camera stream...")
            self.stats_label.setText("Stream Stats: Starting stream...")
            
            # Send start command to proxy
            try:
                if self.camera_proxy_base_url:
                    response = requests.post(
                        f"{self.camera_proxy_base_url}/stream/start",
                        timeout=3
                    )
                    if response.status_code == 200:
                        print("✅ Stream start command sent to proxy")
                        # Enable tracking button now that stream might be available
                        self.tracking_button.setEnabled(True)
                        self.stream_can_change_settings = False  # Lock settings while streaming
                    else:
                        print(f"⚠️ Stream start failed: HTTP {response.status_code}")
                
            except Exception as e:
                print(f"❌ Failed to start stream: {e}")
                self.stats_label.setText(f"Stream Error: {str(e)[:50]}")
        else:
            # Stop streaming
            print("🛑 Stopping camera stream...")
            self.stats_label.setText("Stream Stats: Stopping stream...")
            
            # Disable tracking when stream stops
            if self.tracking_enabled:
                self.tracking_button.setChecked(False)
                self.toggle_tracking(False)
            self.tracking_button.setEnabled(False)
            
            # Send stop command to proxy
            try:
                if self.camera_proxy_base_url:
                    response = requests.post(
                        f"{self.camera_proxy_base_url}/stream/stop", 
                        timeout=3
                    )
                    if response.status_code == 200:
                        print("✅ Stream stop command sent to proxy")
                        self.stream_can_change_settings = True  # Unlock settings
                    else:
                        print(f"⚠️ Stream stop failed: HTTP {response.status_code}")
                        
            except Exception as e:
                print(f"❌ Failed to stop stream: {e}")
        
        # Update button appearance
        self.update_stream_button_appearance()

    @error_boundary  
    def check_stream_status(self):
        """Check if camera proxy stream is currently active"""
        try:
            if not self.camera_proxy_base_url:
                return
                
            response = requests.get(
                f"{self.camera_proxy_base_url}/stream/status",
                timeout=2
            )
            
            if response.status_code == 200:
                status = response.json()
                is_streaming = status.get("streaming", False)
                
                # Update UI to match actual stream state
                if is_streaming != self.streaming_enabled:
                    self.streaming_enabled = is_streaming
                    self.stream_button.setChecked(is_streaming)
                    self.update_stream_button_appearance()
                    
                    # Update tracking button availability
                    self.tracking_button.setEnabled(is_streaming)
                    
                    if is_streaming:
                        print("📹 Stream detected as active")
                        self.stats_label.setText("Stream Stats: Stream active")
                    else:
                        print("⏸️ Stream detected as inactive")
                        self.stats_label.setText("Stream Stats: Stream inactive")
                        
            else:
                print(f"❌ Stream status check failed: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"❌ Stream status check error: {e}")
            # Assume stream is not active if we can't check
            if self.streaming_enabled:
                self.streaming_enabled = False
                self.stream_button.setChecked(False)
                self.tracking_button.setEnabled(False)
                self.update_stream_button_appearance()

    def handle_stream_control(self, enabled):
        """Handle stream control changes from camera controls widget"""
        # This would be called if the camera controls widget had stream controls
        # For now, we handle streaming through the main stream button
        print(f"🎛️ Stream control change requested: {enabled}")
        
        if enabled != self.streaming_enabled:
            self.stream_button.setChecked(enabled)
            self.toggle_stream(enabled)

    def handle_settings_update(self, setting_name, value):
        """Handle camera settings update requests"""
        # This would be called if the camera controls widget wanted to update settings
        # The CameraControlsWidget already handles its own settings updates
        print(f"🎛️ Settings update requested: {setting_name} = {value}")
    
    @error_boundary
    def update_display(self, processed_data):
        """Update display with processed frame data"""
        try:
            frame_rgb = processed_data['frame']
            wave_detected = processed_data['wave_detected']
            
            if frame_rgb is None:
                # Handle case where OpenCV is not available
                self.video_label.setText("Camera not available\n(OpenCV not installed)")
                return
            
            # Handle wave detection logic - only if tracking is enabled
            if self.tracking_enabled and wave_detected:
                current_time = time.time()
                if current_time - self.last_sample_time >= 1.0 / SAMPLE_RATE:
                    self.sample_buffer.append(wave_detected)
                    self.last_sample_time = current_time
                
                if len(self.sample_buffer) == self.sample_buffer.maxlen:
                    confidence = sum(self.sample_buffer) / len(self.sample_buffer)
                    if confidence >= CONFIDENCE_THRESHOLD:
                        if current_time - self.last_wave_time >= STAND_DOWN_TIME:
                            # Send wave gesture detected
                            self.websocket.send_safe(json.dumps({
                                "type": "gesture",
                                "name": "wave"
                            }))
                            self.last_wave_time = current_time
                            self.sample_buffer.clear()
                            print("👋 Wave gesture detected and sent!")
            
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
            print(f"Display update error: {e}")
            self.video_label.setText(f"Display Error:\n{str(e)}")
    
    def update_stats(self, stats_text):
        """Update statistics display"""
        self.stats_label.setText(f"Stream Stats: {stats_text}")
    
    @error_boundary    
    def toggle_tracking(self, checked=None):
        """Toggle wave detection tracking with visual feedback"""
        # Handle both toggled signal (with checked param) and direct calls
        if checked is not None:
            self.tracking_enabled = checked
        else:
            self.tracking_enabled = self.tracking_button.isChecked()
        
        # Update the image thread with tracking state
        self.image_thread.set_tracking_enabled(self.tracking_enabled)
        
        # Update button icon based on state
        if self.tracking_enabled:
            # Change to pressed icon when tracking is enabled
            if os.path.exists("icons/Tracking_pressed.png"):
                self.tracking_button.setIcon(QIcon("icons/Tracking_pressed.png"))
                print("👀 Changed to Tracking_pressed.png icon")
            self.tracking_button.setToolTip("Wave Detection: ENABLED (Click to disable)")
            print("👀 Wave detection ENABLED")
        else:
            # Change back to normal icon when tracking is disabled
            if os.path.exists("icons/Tracking.png"):
                self.tracking_button.setIcon(QIcon("icons/Tracking.png"))
                print("👀 Changed to Tracking.png icon")
            self.tracking_button.setToolTip("Wave Detection: DISABLED (Click to enable)")
            print("👀 Wave detection DISABLED")
        
        # Send tracking state to backend
        self.websocket.send_safe(json.dumps({
            "type": "tracking",
            "state": self.tracking_enabled
        }))
        
        # Update stats to show tracking status
        status = "ENABLED" if self.tracking_enabled else "DISABLED"
        current_stats = self.stats_label.text()
        if "Wave Detection:" in current_stats:
            # Update existing status
            parts = current_stats.split(" | Wave Detection:")
            self.stats_label.setText(f"{parts[0]} | Wave Detection: {status}")
        else:
            # Add status
            self.stats_label.setText(f"{current_stats} | Wave Detection: {status}")
    
    @error_boundary
    def reconnect_stream(self):
        """Reconnect stream by restarting image thread"""
        print("🔄 Reconnecting camera stream...")
        
        # Stop current thread
        self.image_thread.stop()
        
        # Reload config in case URL changed
        config = config_manager.get_config("configs/steamdeck_config.json")
        camera_proxy_url = config.get("current", {}).get("camera_proxy_url", "")
        
        # Create new thread
        self.image_thread = ImageProcessingThread(camera_proxy_url)
        self.image_thread.frame_processed.connect(self.update_display)
        self.image_thread.stats_updated.connect(self.update_stats)
        
        # Restore tracking state if it was enabled
        if self.tracking_enabled:
            self.image_thread.set_tracking_enabled(True)
        
        # Start new thread
        self.image_thread.start()
        
        # Update status
        self.stats_label.setText("Stream Stats: Reconnecting...")
        print(f"🔄 Camera reconnected with URL: {camera_proxy_url}")
    
    def reload_wave_settings(self):
        """Reload wave detection settings"""
        try:
            config_manager.clear_cache()
            config = config_manager.get_config("configs/steamdeck_config.json")
            wave_config = config.get("current", {})
            wave_settings = wave_config.get("wave_detection", {})
            
            global SAMPLE_DURATION, SAMPLE_RATE, CONFIDENCE_THRESHOLD, STAND_DOWN_TIME
            SAMPLE_DURATION = wave_settings.get("sample_duration", 3)
            SAMPLE_RATE = wave_settings.get("sample_rate", 5)
            CONFIDENCE_THRESHOLD = wave_settings.get("confidence_threshold", 0.7)
            STAND_DOWN_TIME = wave_settings.get("stand_down_time", 30)
            
            self.sample_buffer = deque(maxlen=SAMPLE_DURATION * SAMPLE_RATE)
            self.last_sample_time = 0
            print("Wave detection settings reloaded.")
        except Exception as e:
            print(f"Failed to reload wave detection settings: {e}")
    
    def reload_camera_settings(self):
        """Reload camera proxy URL settings"""
        try:
            config_manager.clear_cache()
            config = config_manager.get_config("configs/steamdeck_config.json")
            camera_proxy_url = config.get("current", {}).get("camera_proxy_url", "")
            
            # Restart image thread with new URL
            self.reconnect_stream()
            
            print(f"Camera settings reloaded. New proxy URL: {camera_proxy_url}")
        except Exception as e:
            print(f"Failed to reload camera settings: {e}")
    
    @error_boundary
    def closeEvent(self, event):
        """Proper cleanup on close"""
        # Stop streaming first
        if self.streaming_enabled:
            self.toggle_stream(False)
        
        # Stop image processing thread
        if hasattr(self, 'image_thread'):
            self.image_thread.stop()
        
        event.accept()

class SceneScreen(QWidget):
    def __init__(self, websocket):
        super().__init__()
        self.websocket = websocket
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        self.setFixedWidth(1180)
        self.scene_widgets = {}
        self.selected_labels = []
        self.categories = [
            "Happy", "Sad", "Curious", "Angry", "Surprise",
            "Love", "Calm", "Sound Effect", "Misc"
        ]
        self.init_ui()
        self.load_config()
        self.websocket.textMessageReceived.connect(self.handle_message)
        self.request_scenes()

    def init_ui(self):
        self.layout = QVBoxLayout()
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
        self.import_btn = QPushButton("🔄 Import Scenes")
        self.import_btn.clicked.connect(self.request_scenes)
        self.save_btn = QPushButton("💾 Save Config")
        self.save_btn.clicked.connect(self.save_config)
        btn_layout.addWidget(self.import_btn)
        btn_layout.addWidget(self.save_btn)
        self.layout.addLayout(btn_layout)

        self.setLayout(self.layout)

    @error_boundary
    def request_scenes(self):
        self.websocket.send_safe(json.dumps({"type": "get_scenes"}))

    @error_boundary
    def handle_message(self, message):
        try:
            msg = json.loads(message)
            if msg.get("type") == "scene_list":
                self.update_grid(msg.get("scenes", []))
        except Exception as e:
            print(f"Failed to handle message: {e}")

    @error_boundary
    def update_grid(self, scenes):
        # Clear existing widgets
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        self.scene_widgets.clear()

        for idx, scene in enumerate(scenes):
            label = scene.get("label", "")
            emoji = scene.get("emoji", "")
            checkbox = QCheckBox()
            checkbox.setChecked(label in self.selected_labels)

            name_label = QLabel(f"{emoji} {label}")
            name_label.setStyleSheet("font-size: 20px;")

            category_cb = QComboBox()
            category_cb.addItems(self.categories)
            category_cb.setStyleSheet("font-size: 16px;")
            category_cb.setFixedWidth(150)

            test_btn = QPushButton("▶ Test")
            test_btn.setStyleSheet("font-size: 16px;")
            test_btn.clicked.connect(lambda _, name=label: self.test_scene(name))

            row = idx // 2
            col = (idx % 2) * 4
            self.grid_layout.addWidget(checkbox, row, col)
            self.grid_layout.addWidget(name_label, row, col + 1)
            self.grid_layout.addWidget(category_cb, row, col + 2)
            self.grid_layout.addWidget(test_btn, row, col + 3)

            self.scene_widgets[label] = (checkbox, emoji, category_cb)

    @error_boundary
    def test_scene(self, name):
        self.websocket.send_safe(json.dumps({"type": "scene", "emotion": name}))

    @error_boundary
    def save_config(self):
        selected = [
            {"label": label, "emoji": emoji, "category": cb.currentText()}
            for label, (cbx, emoji, cb) in self.scene_widgets.items()
            if cbx.isChecked()
        ]
        try:
            with open("configs/emotion_buttons.json", "w") as f:
                json.dump(selected, f, indent=2)
            config_manager.clear_cache()
            QMessageBox.information(self, "Saved", "Emotion buttons saved successfully.")
            self.load_config()

            # Reload HomeScreen emotion buttons
            app = QApplication.instance()
            if app:
                for widget in app.allWidgets():
                    if isinstance(widget, HomeScreen):
                        widget.load_emotion_buttons()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save config: {e}")

    @error_boundary
    def load_config(self):
        config = config_manager.get_config("configs/emotion_buttons.json")
        emotions = config if isinstance(config, list) else []
        self.selected_labels = [item.get("label", "") for item in emotions]

class SettingsScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        self.setFixedWidth(1180)
        self.config_path = "configs/steamdeck_config.json"
        self.init_ui()
        self.load_config()

    def init_ui(self):
        font = QFont("Arial", 16)
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(100, 20, 15, 5)
        self.grid = QGridLayout()
        self.grid.setVerticalSpacing(20)

        # ESP32 Cam Stream URL (for camera proxy backend)
        self.esp32_url_label = QLabel("ESP32 Cam Stream URL:")
        self.esp32_url_label.setFont(font)
        self.esp32_url_input = QLineEdit()
        self.esp32_url_input.setFont(font)
        self.esp32_url_input.setPlaceholderText("http://esp32.local:81/stream")

        # Camera Proxy URL (for frontend consumption)
        self.proxy_url_label = QLabel("Camera Proxy URL:")
        self.proxy_url_label.setFont(font)
        self.proxy_url_input = QLineEdit()
        self.proxy_url_input.setFont(font)
        self.proxy_url_input.setPlaceholderText("http://10.1.1.10:8081/stream")

        # Control WebSocket
        self.control_label = QLabel("Control WebSocket URL:")
        self.control_label.setFont(font)
        self.control_input = QLineEdit()
        self.control_input.setFont(font)
        self.control_input.setPlaceholderText("localhost:8766")

        # Wave detection settings (keeping existing)
        self.sample_duration_label = QLabel("Wave Sample Duration (sec):")
        self.sample_duration_label.setFont(font)
        self.sample_duration_spin = QSpinBox()
        self.sample_duration_spin.setFont(font)
        self.sample_duration_spin.setRange(1, 10)

        self.sample_rate_label = QLabel("Sample Rate (Hz):")
        self.sample_rate_label.setFont(font)
        self.sample_rate_spin = QSpinBox()
        self.sample_rate_spin.setFont(font)
        self.sample_rate_spin.setRange(1, 60)

        self.confidence_label = QLabel("Confidence Threshold (%):")
        self.confidence_label.setFont(font)
        self.confidence_slider = QSlider(Qt.Orientation.Horizontal)
        self.confidence_slider.setRange(0, 100)
        self.confidence_slider.setValue(70)
        self.confidence_slider.setFixedWidth(300)
        self.confidence_value = QLabel("70%")
        self.confidence_value.setFont(font)
        self.confidence_slider.valueChanged.connect(
            lambda val: self.confidence_value.setText(f"{val}%")
        )

        self.stand_down_label = QLabel("Stand Down Time (sec):")
        self.stand_down_label.setFont(font)
        self.stand_down_spin = QSpinBox()
        self.stand_down_spin.setFont(font)
        self.stand_down_spin.setRange(0, 300)

        # Add widgets to grid
        self.grid.addWidget(self.esp32_url_label, 0, 0)
        self.grid.addWidget(self.esp32_url_input, 0, 1)
        self.grid.addWidget(self.proxy_url_label, 1, 0)
        self.grid.addWidget(self.proxy_url_input, 1, 1)
        self.grid.addWidget(self.control_label, 2, 0)
        self.grid.addWidget(self.control_input, 2, 1)
        self.grid.addWidget(self.sample_duration_label, 3, 0)
        self.grid.addWidget(self.sample_duration_spin, 3, 1)
        self.grid.addWidget(self.sample_rate_label, 4, 0)
        self.grid.addWidget(self.sample_rate_spin, 4, 1)
        self.grid.addWidget(self.confidence_label, 5, 0)
        self.grid.addWidget(self.confidence_slider, 5, 1)
        self.grid.addWidget(self.confidence_value, 5, 2)
        self.grid.addWidget(self.stand_down_label, 6, 0)
        self.grid.addWidget(self.stand_down_spin, 6, 1)

        self.layout.addLayout(self.grid)

        # Buttons
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("💾 Update")
        self.save_btn.setFont(font)
        self.save_btn.clicked.connect(lambda checked: self.save_config())  # FIX: Ignore checked parameter
        self.reset_btn = QPushButton("🔄 Reset")
        self.reset_btn.setFont(font)
        self.reset_btn.clicked.connect(lambda checked: self.reset_to_defaults())  # FIX: Ignore checked parameter
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.reset_btn)
        self.layout.addLayout(btn_layout)

        self.setLayout(self.layout)

    @error_boundary
    def load_config(self):
        config = config_manager.get_config(self.config_path)
        current = config.get("current", {})
        wave = current.get("wave_detection", {})
        self.esp32_url_input.setText(current.get("esp32_cam_url", ""))
        self.proxy_url_input.setText(current.get("camera_proxy_url", ""))
        self.control_input.setText(current.get("control_websocket_url", "localhost:8766"))
        self.sample_duration_spin.setValue(wave.get("sample_duration", 3))
        self.sample_rate_spin.setValue(wave.get("sample_rate", 5))
        self.confidence_slider.setValue(int(wave.get("confidence_threshold", 0.7) * 100))
        self.stand_down_spin.setValue(wave.get("stand_down_time", 30))

    @error_boundary
    def save_config(self):
        try:
            config = config_manager.get_config(self.config_path)
        except:
            config = {}

        config["current"] = {
            "esp32_cam_url": self.esp32_url_input.text(),
            "camera_proxy_url": self.proxy_url_input.text(),
            "control_websocket_url": self.control_input.text(),
            "wave_detection": {
                "sample_duration": self.sample_duration_spin.value(),
                "sample_rate": self.sample_rate_spin.value(),
                "confidence_threshold": self.confidence_slider.value() / 100.0,
                "stand_down_time": self.stand_down_spin.value()
            }
        }

        try:
            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=2)
            config_manager.clear_cache()  # Clear cache after save
            
            # Send ESP32 URL update to backend to update camera_config.json
            app = QApplication.instance()
            if app:
                main_window = None
                for widget in app.allWidgets():
                    if isinstance(widget, MainWindow):
                        main_window = widget
                        break
                
                if main_window and hasattr(main_window, 'websocket'):
                    main_window.websocket.send_safe(json.dumps({
                        "type": "update_camera_config",
                        "esp32_url": self.esp32_url_input.text()
                    }))
            
            QMessageBox.information(self, "Update", "Configuration updated successfully.\nCamera proxy will restart with new settings.")
            
            # Reload settings in other components
            if app:
                for widget in app.allWidgets():
                    if hasattr(widget, "reload_wave_settings"):
                        widget.reload_wave_settings()
                    elif isinstance(widget, CameraFeedScreen):
                        widget.reload_camera_settings()
                        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save config: {e}")

    @error_boundary
    def reset_to_defaults(self):
        config = config_manager.get_config(self.config_path)
        defaults = config.get("defaults", {})
        config["current"] = defaults
        with open(self.config_path, "w") as f:
            json.dump(config, f, indent=2)
        config_manager.clear_cache()
        self.load_config()
        QMessageBox.information(self, "Reset", "Configuration reset to defaults.")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WALL-E Control System")
        self.setFixedSize(1280, 800)
        
        # Set background if available
        if os.path.exists("background.png"):
            background = QPixmap("background.png")
            palette = QPalette()
            palette.setBrush(QPalette.ColorRole.Window, QBrush(background))
            self.setPalette(palette)

        # FIXED: WebSocket setup with single connection to port 8766
        try:
            config = config_manager.get_config("configs/steamdeck_config.json")
            ws_url = config.get("current", {}).get("control_websocket_url", "localhost:8766")
        except:
            ws_url = "localhost:8766"
        
        if not ws_url.startswith("ws://"):
            ws_url = f"ws://{ws_url}"
        self.websocket = WebSocketManager(ws_url)
        # Connect websocket to header for voltage updates
        self.websocket.textMessageReceived.connect(self.update_header_from_telemetry)
        
        self.header = DynamicHeader("Home")
        self.header.setMaximumWidth(1000)

        self.stack = QStackedWidget()
        self.nav_buttons = {}

        # FIXED: Initialize screens with shared WebSocket
        self.health_screen = HealthScreen(self.websocket)  # Pass websocket parameter
        self.servo_screen = ServoConfigScreen(self.websocket)
        self.camera_screen = CameraFeedScreen(self.websocket)
        self.controller_screen = ControllerConfigScreen(self.websocket)
        self.settings_screen = SettingsScreen()
        self.scene_editor_screen = SceneScreen(self.websocket)
        self.scene_dashboard_screen = HomeScreen(self.websocket)

        self.stack.addWidget(self.scene_dashboard_screen)  # Home first
        self.stack.addWidget(self.camera_screen)
        self.stack.addWidget(self.health_screen)
        self.stack.addWidget(self.servo_screen)
        self.stack.addWidget(self.controller_screen)
        self.stack.addWidget(self.settings_screen)
        self.stack.addWidget(self.scene_editor_screen)

        # Setup memory management timer
        self.memory_timer = QTimer()
        self.memory_timer.timeout.connect(MemoryManager.periodic_cleanup)
        self.memory_timer.start(30000)  # Cleanup every 30 seconds

        self.setup_navigation()
        self.setup_layout()

    def update_header_from_telemetry(self, message):
        """Update header voltage from telemetry"""
        try:
            data = json.loads(message)
            if data.get("type") == "telemetry":
                voltage = data.get("battery_voltage", 0.0)
                if voltage > 0:
                    self.header.update_voltage(voltage)
                
                # Also update WiFi with a simulated value
                import random
                wifi_percent = random.randint(70, 100)
                self.header.update_wifi(wifi_percent)
                
        except Exception as e:
            print(f"Header update error: {e}")

    def setup_navigation(self):
        """Setup navigation with optimized button handling"""
        self.nav_bar = QHBoxLayout()
        self.nav_bar.addSpacing(100)
        
        buttons = [
            ("Home", self.scene_dashboard_screen),
            ("Camera", self.camera_screen),
            ("Health", self.health_screen),
            ("ServoConfig", self.servo_screen),
            ("Controller", self.controller_screen),
            ("Settings", self.settings_screen),
            ("Scene", self.scene_editor_screen)
        ]

        for name, screen in buttons:
            btn = QPushButton()
            if os.path.exists(f"icons/{name}.png"):
                btn.setIcon(QIcon(f"icons/{name}.png"))
                btn.setIconSize(QSize(64, 64))
            btn.clicked.connect(lambda _, s=screen, n=name: self.switch_screen(s, n))
            self.nav_bar.addWidget(btn)
            self.nav_buttons[name] = btn

        # Failsafe button
        self.failsafe_button = QPushButton()
        self.failsafe_button.setCheckable(True)
        if os.path.exists("icons/failsafe.png"):
            self.failsafe_button.setIcon(QIcon("icons/failsafe.png"))
            self.failsafe_button.setIconSize(QSize(300, 70))
        self.failsafe_button.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white;")
        self.failsafe_button.clicked.connect(self.toggle_failsafe_icon)

        self.nav_bar.addSpacing(20)
        self.nav_bar.addWidget(self.failsafe_button)
        self.nav_bar.addSpacing(100)

    def setup_layout(self):
        """Setup main window layout"""
        nav_frame = QFrame()
        nav_frame.setLayout(self.nav_bar)
        nav_frame.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white;")

        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.addSpacing(60)

        # Header container
        header_container = QWidget()
        header_layout = QHBoxLayout()
        header_layout.addWidget(self.header)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_container.setLayout(header_layout)

        layout.addWidget(header_container)
        layout.addSpacing(2)
        layout.addWidget(self.stack)
        layout.addWidget(nav_frame)
        layout.addSpacing(35)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Set initial screen
        self.switch_screen(self.scene_dashboard_screen, "Home")

    @error_boundary
    def switch_screen(self, screen, name):
        """Switch to a different screen with optimized icon updates"""
        self.stack.setCurrentWidget(screen)
        self.header.set_screen_name(name)
        
        # Update navigation icons
        for btn_name, btn in self.nav_buttons.items():
            if btn_name == name and os.path.exists(f"icons/{btn_name}_pressed.png"):
                btn.setIcon(QIcon(f"icons/{btn_name}_pressed.png"))
            elif os.path.exists(f"icons/{btn_name}.png"):
                btn.setIcon(QIcon(f"icons/{btn_name}.png"))

    @error_boundary
    def toggle_failsafe_icon(self):
        """Toggle failsafe with WebSocket communication"""
        sender = self.sender()
        if sender.isChecked():
            if os.path.exists("icons/failsafe_pressed.png"):
                sender.setIcon(QIcon("icons/failsafe_pressed.png"))
            state = True
        else:
            if os.path.exists("icons/failsafe.png"):
                sender.setIcon(QIcon("icons/failsafe.png"))
            state = False

        # Send state to backend
        self.websocket.send_safe(json.dumps({
            "type": "failsafe",
            "state": state
        }))

    def closeEvent(self, event):
        """Proper cleanup on application close"""
        # Stop all threads
        if hasattr(self.camera_screen, 'image_thread'):
            self.camera_screen.image_thread.stop()
        
        # FIXED: Close only the main WebSocket connection
        if hasattr(self, 'websocket'):
            self.websocket.close()
        
        # Stop timers
        if hasattr(self, 'memory_timer'):
            self.memory_timer.stop()
        
        # Final cleanup
        MemoryManager.cleanup_widgets(self)
        event.accept()


if __name__ == "__main__":
    # Optimize application settings
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    print("🤖 WALL-E Optimized Frontend Started")
    
    sys.exit(app.exec())