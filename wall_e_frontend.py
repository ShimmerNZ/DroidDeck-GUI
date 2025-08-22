# WALL-E Optimized Frontend - Complete Implementation with Performance and Reliability Improvements
import sys
import json
import time
import random
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

# PERFORMANCE IMPROVEMENT 3: Optimized image processing thread
class ImageProcessingThread(QThread):
    frame_processed = pyqtSignal(object)  # Emit processed frame
    stats_updated = pyqtSignal(str)      # Emit stats string
    
    def __init__(self, esp32_cam_url):
        super().__init__()
        self.esp32_cam_url = esp32_cam_url
        self.running = False
        self.tracking_enabled = False
        self.cap = None
        self.hog = None
        self.frame_skip_count = 0
        self.target_fps = 15  # Reduced from 30+ for better performance
        
    def set_tracking_enabled(self, enabled):
        self.tracking_enabled = enabled
        
    def run(self):
        if not CV2_AVAILABLE:
            print("Camera processing disabled - OpenCV not available")
            return
            
        self.running = True
        self.cap = cv2.VideoCapture(self.esp32_cam_url if self.esp32_cam_url else 0)
        
        # Optimize capture settings
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce buffer lag
        self.cap.set(cv2.CAP_PROP_FPS, self.target_fps)
        
        if self.tracking_enabled and self.hog is None:
            self.hog = cv2.HOGDescriptor()
            self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            
        frame_time = 1.0 / self.target_fps
        last_process_time = time.time()
        
        while self.running:
            current_time = time.time()
            
            # Frame rate limiting
            if current_time - last_process_time < frame_time:
                self.msleep(10)
                continue
                
            ret, frame = self.cap.read()
            if not ret:
                self.msleep(50)
                continue
                
            # Process every nth frame for performance
            self.frame_skip_count += 1
            if self.frame_skip_count % 2 == 0:  # Process every other frame
                processed_frame = self.process_frame(frame)
                self.frame_processed.emit(processed_frame)
                
            last_process_time = current_time
            
    def process_frame(self, frame):
        """Optimized frame processing"""
        if not CV2_AVAILABLE:
            return {'frame': None, 'wave_detected': False, 'stats': 'OpenCV not available'}
            
        try:
            # Resize frame for faster processing
            height, width = frame.shape[:2]
            if width > 640:
                scale = 640 / width
                new_width = int(width * scale)
                new_height = int(height * scale)
                frame = cv2.resize(frame, (new_width, new_height))
                
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Only do expensive processing if tracking is enabled
            wave_detected = False
            if self.tracking_enabled:
                if init_mediapipe():  # Lazy init with availability check
                    if pose is not None:
                        results = pose.process(frame_rgb)
                        if results.pose_landmarks:
                            lm = results.pose_landmarks.landmark
                            rw = lm[mp_pose.PoseLandmark.RIGHT_WRIST]
                            rs = lm[mp_pose.PoseLandmark.RIGHT_SHOULDER]
                            if rw.y < rs.y:
                                wave_detected = True
                                cv2.putText(frame_rgb, 'Wave Detected', (50, 50), 
                                          cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
                
                # HOG detection (less frequent)
                if self.hog is not None and self.frame_skip_count % 5 == 0:
                    boxes, weights = self.hog.detectMultiScale(frame_rgb, winStride=(8, 8))
                    for (x, y, w, h) in boxes:
                        cv2.rectangle(frame_rgb, (x, y), (x + w, y + h), (255, 0, 0), 2)
            
            return {
                'frame': frame_rgb,
                'wave_detected': wave_detected,
                'stats': f"Processing: {frame_rgb.shape[1]}x{frame_rgb.shape[0]}"
            }
        except Exception as e:
            print(f"Frame processing error: {e}")
            return {'frame': frame_rgb if 'frame_rgb' in locals() else None, 'wave_detected': False, 'stats': f"Error: {e}"}
    
    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()
        self.quit()
        self.wait()

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
    def __init__(self, websocket):
        super().__init__()
        self.websocket = websocket
        self.setFixedWidth(1180)
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        self.servo_config = self.load_config()
        self.active_sweep = None
        
        # 🔥 NEW: Track channel counts for each Maestro
        self.maestro_channel_counts = {1: 18, 2: 18}  # Default fallback
        self.current_maestro = 1
        self.channels_loaded = False
        
        # 🔥 NEW: Track servo widgets for position updates
        self.servo_widgets = {}  # Will store {channel_key: (slider, pos_label, ...)}
        self.position_update_timer = QTimer()
        self.position_update_timer.timeout.connect(self.update_all_positions)
        self.auto_update_positions = True  # Toggle for auto-refresh

        # Maestro selector dropdown
        self.maestro1_btn = QPushButton()
        self.maestro2_btn = QPushButton()
        self.maestro1_btn.setCheckable(True)
        self.maestro2_btn.setCheckable(True)
        
        # Load icons if they exist
        if os.path.exists("icons/M1.png"):
            self.maestro1_btn.setIcon(QIcon("icons/M1.png"))
            self.maestro1_btn.setIconSize(QSize(112,118))
        if os.path.exists("icons/M2.png"):
            self.maestro2_btn.setIcon(QIcon("icons/M2.png"))
            self.maestro2_btn.setIconSize(QSize(112,118))

        self.maestro_group = QButtonGroup()
        self.maestro_group.setExclusive(True)
        self.maestro_group.addButton(self.maestro1_btn, 0)
        self.maestro_group.addButton(self.maestro2_btn, 1)
        self.maestro_group.idClicked.connect(self.on_maestro_changed)

        self.maestro1_btn.setChecked(True)
        self.update_maestro_icons(0)

        # Add refresh button
        self.refresh_btn = QPushButton("Update")
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
        self.refresh_btn.clicked.connect(self.refresh_maestro_data)

        # 🔥 NEW: Add status label to show channel detection
        self.status_label = QLabel("Detecting channels...")
        self.status_label.setFont(QFont("Arial", 14))
        self.status_label.setStyleSheet("color: #FFAA00; padding: 5px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 🔥 NEW: Add position refresh controls
        self.setup_position_controls()

        # Scrollable grid area
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.grid_widget.setLayout(self.grid_layout)
        self.grid_widget.setStyleSheet("QWidget { border: 1px solid #555; border-radius: 12px; }")

        # 🔥 NEW: Connect to WebSocket for responses
        self.websocket.textMessageReceived.connect(self.handle_websocket_message)

        # Setup UI layout
        self.setup_layout()
        
        # 🔥 NEW: Request channel counts from backend on startup
        self.request_maestro_info()

    def setup_position_controls(self):
        """Setup controls for position reading"""
        # Auto-update checkbox
        self.auto_update_checkbox = QCheckBox("Auto-refresh positions")
        self.auto_update_checkbox.setChecked(True)
        self.auto_update_checkbox.setFont(QFont("Arial", 12))
        self.auto_update_checkbox.setStyleSheet("color: white;")
        self.auto_update_checkbox.toggled.connect(self.toggle_auto_update)
        
        # Manual refresh button
        self.read_positions_btn = QPushButton("📍 Read Positions")
        self.read_positions_btn.setFont(QFont("Arial", 12))
        self.read_positions_btn.clicked.connect(self.read_all_positions_now)
        self.read_positions_btn.setStyleSheet("""
            QPushButton {
                background-color: #444;
                color: white;
                border-radius: 8px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)

    def setup_layout(self):
        """Enhanced layout with position controls"""
        # Main layout
        grid_and_selector_layout = QHBoxLayout()
        grid_and_selector_layout.addSpacing(80)

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
        # 🔥 NEW: Add position controls
        selector_container.addWidget(self.auto_update_checkbox)
        selector_container.addWidget(self.read_positions_btn)
        selector_container.addStretch()

        # Create a QWidget to hold the selector layout
        selector_widget = QWidget()
        selector_widget.setLayout(selector_container)
        selector_widget.setStyleSheet("background-color: rgba(0, 0, 0, 0);")

        # Add selector widget to the right of the grid
        grid_and_selector_layout.addWidget(scroll_area, stretch=3)
        grid_and_selector_layout.addWidget(selector_widget)

        # Final layout with status
        layout = QVBoxLayout()
        layout.addWidget(self.status_label)
        layout.addLayout(grid_and_selector_layout)
        self.setLayout(layout)

    # 🔥 NEW: Handle WebSocket messages
    @error_boundary
    def handle_websocket_message(self, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "maestro_info":
                maestro_num = data.get("maestro")
                channels = data.get("channels", 0)
                connected = data.get("connected", False)
                
                if maestro_num in [1, 2]:
                    self.maestro_channel_counts[maestro_num] = channels
                    print(f"📡 Maestro {maestro_num}: {channels} channels, connected: {connected}")
                    
                    # Update status
                    if connected:
                        self.update_status(f"Maestro {maestro_num}: {channels} channels detected")
                    else:
                        self.update_status(f"Maestro {maestro_num}: Not connected")
                    
                    # Refresh grid if this is the current maestro
                    if maestro_num == self.current_maestro + 1:
                        self.update_grid()
            
            # 🔥 NEW: Handle servo position responses
            elif msg_type == "servo_position":
                channel_key = data.get("channel")
                position = data.get("position")
                
                if channel_key and position is not None:
                    self.update_servo_position_display(channel_key, position)
            
            # 🔥 NEW: Handle batch position responses
            elif msg_type == "all_servo_positions":
                maestro_num = data.get("maestro")
                positions = data.get("positions", {})
                
                print(f"📍 Received {len(positions)} positions for Maestro {maestro_num}")
                
                for channel, position in positions.items():
                    channel_key = f"m{maestro_num}_ch{channel}"
                    if position is not None:
                        self.update_servo_position_display(channel_key, position)
                        
        except Exception as e:
            print(f"Error handling WebSocket message: {e}")

    # 🔥 NEW: Update servo position display
    def update_servo_position_display(self, channel_key, position):
        """Update the UI to show actual servo position"""
        if channel_key in self.servo_widgets:
            slider, pos_label = self.servo_widgets[channel_key][:2]
            
            # Update slider position (without triggering servo movement)
            slider.blockSignals(True)  # Prevent triggering servo command
            slider.setValue(position)
            slider.blockSignals(False)
            
            # Update position label
            pos_label.setText(f"V: {position}")
            pos_label.setStyleSheet("color: white;")  # White for read position
            
            print(f"📍 Updated display: {channel_key} = {position}")

    # 🔥 NEW: Toggle auto-update
    def toggle_auto_update(self, enabled):
        """Toggle automatic position updates"""
        self.auto_update_positions = enabled
        
        if enabled:
            self.position_update_timer.start(200)  # Update every .2 seconds
            self.update_status("Auto-refresh positions: ON")
            print("🔄 Auto position updates enabled")
        else:
            self.position_update_timer.stop()
            self.update_status("Auto-refresh positions: OFF")
            print("⏸️ Auto position updates disabled")

    # 🔥 NEW: Read all positions now
    def read_all_positions_now(self):
        """Manually trigger reading all servo positions"""
        maestro_num = self.current_maestro + 1
        
        self.websocket.send_safe(json.dumps({
            "type": "get_all_servo_positions",
            "maestro": maestro_num
        }))
        
        self.update_status(f"Reading positions from Maestro {maestro_num}...")
        print(f"📡 Requesting all positions from Maestro {maestro_num}")

    # 🔥 NEW: Auto-update all positions
    def update_all_positions(self):
        """Automatically update all servo positions"""
        if not self.auto_update_positions:
            return
        
        maestro_num = self.current_maestro + 1
        
        # Only update if we have servo widgets and maestro is connected
        if self.servo_widgets:
            self.websocket.send_safe(json.dumps({
                "type": "get_all_servo_positions", 
                "maestro": maestro_num
            }))
            print(f"🔄 Auto-updating positions for Maestro {maestro_num}")

    # 🔥 NEW: Request maestro information
    def request_maestro_info(self):
        """Request channel count and status from both Maestros"""
        self.update_status("Requesting Maestro information...")
        
        # Request info for both Maestros
        for maestro_num in [1, 2]:
            self.websocket.send_safe(json.dumps({
                "type": "get_maestro_info",
                "maestro": maestro_num
            }))
        
        print("📡 Requested Maestro information from backend")

    # 🔥 NEW: Refresh maestro data
    def refresh_maestro_data(self):
        """Refresh maestro data and rebuild grid"""
        self.request_maestro_info()
        # Also refresh servo config
        self.reload_servo_config()

    # 🔥 NEW: Handle maestro selection change
    def on_maestro_changed(self, maestro_index):
        """Handle maestro selection change"""
        self.current_maestro = maestro_index
        self.update_maestro_icons(maestro_index)
        self.stop_all_sweeps()  # Stop any active sweeps
        self.update_grid()  # Rebuild grid for new maestro
        
        # Update status
        maestro_num = maestro_index + 1
        channels = self.maestro_channel_counts.get(maestro_num, 0)
        self.update_status(f"Maestro {maestro_num}: {channels} channels")

    # 🔥 NEW: Update status label
    def update_status(self, message):
        """Update the status label"""
        self.status_label.setText(message)
        print(f"🔄 Status: {message}")

    @error_boundary
    def update_maestro_icons(self, checked_id):
        # Set pressed icon for selected, normal for unselected
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
        return config_manager.get_config("configs/servo_config.json")

    @error_boundary
    def save_config(self):
        with open("configs/servo_config.json", "w") as f:
            json.dump(self.servo_config, f, indent=2)
        config_manager.clear_cache()  # Clear cache after save

    @error_boundary
    def reload_servo_config(self):
        config_manager.clear_cache()
        self.servo_config = config_manager.get_config("configs/servo_config.json")
        self.update_grid()
        print("Servo config reloaded successfully.")

    def update_config(self, key, field, value):
        if key not in self.servo_config:
            self.servo_config[key] = {}
        self.servo_config[key][field] = value
        self.save_config()

    # 🔥 UPDATED: Modified update_grid to use dynamic channel count and track widgets
    @error_boundary
    def update_grid(self):
        font = QFont("Arial", 16)

        # Stop any active sweeps when rebuilding grid
        self.stop_all_sweeps()
        
        # Stop position updates while rebuilding
        self.position_update_timer.stop()
        
        # Clear existing widgets and tracking
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        
        self.servo_widgets.clear()  # Clear widget tracking

        maestro_index = self.maestro_group.checkedId()
        maestro_num = maestro_index + 1
        
        # Get dynamic channel count
        channel_count = self.maestro_channel_counts.get(maestro_num, 18)
        
        print(f"🔄 Building grid for Maestro {maestro_num} with {channel_count} channels")
        
        # Create grid for actual detected channels
        for i in range(channel_count):
            channel_key = f"m{maestro_num}_ch{i}"
            config = self.servo_config.get(channel_key, {})
            row = i

            label = QLabel(f"Channel {i}")
            label.setFont(font)
            self.grid_layout.addWidget(label, row, 0)

            name_edit = QLineEdit(config.get("name", ""))
            name_edit.setFont(font)
            name_edit.setMaxLength(32)
            name_edit.setPlaceholderText("Friendly Name")
            name_edit.textChanged.connect(lambda text, k=channel_key: self.update_config(k, "name", text))
            self.grid_layout.addWidget(name_edit, row, 1)

            # Slider for position control
            slider = QSlider(Qt.Orientation.Horizontal)
            min_val = config.get("min", 992)
            max_val = config.get("max", 2000)
            slider.setMinimum(min_val)
            slider.setMaximum(max_val)
            slider.setValue((min_val + max_val) // 2)  # Default to center
            slider.setFixedWidth(150)
            self.grid_layout.addWidget(slider, row, 2)

            # Min value controls
            min_label = QLabel("Min")
            min_label.setFont(font)
            self.grid_layout.addWidget(min_label, row, 3)
            
            min_spin = QSpinBox()
            min_spin.setFont(font)
            min_spin.setRange(0, 2500)
            min_spin.setValue(min_val)
            min_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "min", val))
            min_spin.valueChanged.connect(lambda val, s=slider: s.setMinimum(val))
            self.grid_layout.addWidget(min_spin, row, 4)

            # Max value controls
            max_label = QLabel("Max")
            max_label.setFont(font)
            self.grid_layout.addWidget(max_label, row, 5)
            
            max_spin = QSpinBox()
            max_spin.setFont(font)
            max_spin.setRange(0, 2500)
            max_spin.setValue(max_val)
            max_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "max", val))
            max_spin.valueChanged.connect(lambda val, s=slider: s.setMaximum(val))
            self.grid_layout.addWidget(max_spin, row, 6)

            # Speed control
            speed_label = QLabel("S")
            speed_label.setFont(font)
            self.grid_layout.addWidget(speed_label, row, 7)
            
            speed_spin = QSpinBox()
            speed_spin.setFont(font)
            speed_spin.setRange(0, 100)
            speed_spin.setValue(config.get("speed", 0))
            speed_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "speed", val))
            self.grid_layout.addWidget(speed_spin, row, 8)

            # Acceleration control
            accel_label = QLabel("A")
            accel_label.setFont(font)
            self.grid_layout.addWidget(accel_label, row, 9)
            
            accel_spin = QSpinBox()
            accel_spin.setFont(font)
            accel_spin.setRange(0, 100)
            accel_spin.setValue(config.get("accel", 0))
            accel_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "accel", val))
            self.grid_layout.addWidget(accel_spin, row, 10)

            # Position label - will show actual position
            pos_label = QLabel("V: ---")  # 🔥 Changed default to show we're loading
            pos_label.setFont(font)
            pos_label.setStyleSheet("color: #FFAA00;")  # Orange while loading
            self.grid_layout.addWidget(pos_label, row, 11)

            # Play/sweep button
            play_btn = QPushButton("▶")
            play_btn.setFont(font)
            play_btn.setCheckable(True)
            play_btn.clicked.connect(lambda checked, k=channel_key, p=pos_label, b=play_btn, s=slider, min_spin=min_spin, max_spin=max_spin, speed_spin=speed_spin: self.toggle_sweep(k, p, b, s, min_spin.value(), max_spin.value(), speed_spin.value()))
            self.grid_layout.addWidget(play_btn, row, 12)

            # Connect slider to servo movement
            slider.valueChanged.connect(
                lambda val, k=channel_key, p=pos_label: self.update_servo_position(k, p, val)
            )

            # 🔥 NEW: Track widgets for position updates
            self.servo_widgets[channel_key] = (slider, pos_label, play_btn)

        # Update status to show completed grid
        self.update_status(f"Maestro {maestro_num}: {channel_count} channels loaded")
        
        # 🔥 NEW: Start reading positions after grid is built
        QTimer.singleShot(500, self.read_all_positions_now)  # Small delay to let UI settle
        
        # 🔥 NEW: Restart auto-updates if enabled
        if self.auto_update_positions:
            self.position_update_timer.start(2000)

    # 🔥 UPDATED: Enhanced servo position update with real movement
    def update_servo_position(self, channel_key, pos_label, value):
        """Update servo position with enhanced feedback"""
        
        # Get current channel configuration
        config = self.servo_config.get(channel_key, {})
        speed = config.get("speed", 0)
        accel = config.get("accel", 0)
        
        # Apply speed and acceleration settings if they exist
        if speed > 0 or accel > 0:
            print(f"⚙️ Applying settings to {channel_key}: speed={speed}, accel={accel}")
            
            # Send speed setting first (if configured)
            if speed > 0:
                self.websocket.send_safe(json.dumps({
                    "type": "servo_speed",
                    "channel": channel_key, 
                    "speed": speed
                }))
            
            # Send acceleration setting (if configured)
            if accel > 0:
                self.websocket.send_safe(json.dumps({
                    "type": "servo_acceleration", 
                    "channel": channel_key,
                    "acceleration": accel
                }))
        
        # Send position command
        self.websocket.send_safe(json.dumps({
            "type": "servo", 
            "channel": channel_key, 
            "pos": value
        }))
        
        # Update UI immediately (optimistic update)
        pos_label.setText(f"V: {value}")
        pos_label.setStyleSheet("color: #44FF44;")  # Green for commanded position
        
        print(f"📡 Servo command: {channel_key} → {value}")

    # 🔥 UPDATED: Enhanced sweep with real servo movement
    def toggle_sweep(self, key, pos_label, button, slider, min_val, max_val, speed):
        """Toggle servo sweep with real servo movement"""
        if self.active_sweep:
            self.active_sweep.stop()
            self.active_sweep = None
            button.setText("▶")
            button.setChecked(False)
            return

        class Sweep:
            def __init__(self, parent_screen, channel_key, label, btn, slider, minv, maxv, speedv):
                self.parent_screen = parent_screen  # Reference to ServoConfigScreen
                self.channel_key = channel_key      # e.g., "m1_ch5"
                self.label = label
                self.btn = btn
                self.slider = slider
                self.minv = minv
                self.maxv = maxv
                self.speedv = speedv
                
                # Calculate step size and timing
                self.step_size = max(1, (maxv - minv) // 50)  # ~50 steps across range
                self.timer = QTimer()
                self.timer.timeout.connect(self.step)
                
                # Position tracking
                self.pos = minv
                self.direction = 1
                
                # Timer interval based on speed (higher speed = faster updates)
                interval = max(20, 200 - (speedv * 2))
                self.timer.start(interval)
                
                print(f"🎭 Starting sweep on {channel_key}: {minv}-{maxv}, speed={speedv}, step={self.step_size}, interval={interval}ms")

            def step(self):
                """Execute one step of the sweep"""
                # Update position
                self.pos += self.direction * self.step_size
                
                # Check bounds and reverse direction
                if self.pos >= self.maxv:
                    self.pos = self.maxv
                    self.direction = -1
                elif self.pos <= self.minv:
                    self.pos = self.minv
                    self.direction = 1
                
                # Update UI
                self.label.setText(f"V: {self.pos}")
                self.slider.setValue(self.pos)
                
                # 🔥 THE KEY FIX: Actually move the servo!
                self.parent_screen.websocket.send_safe(json.dumps({
                    "type": "servo", 
                    "channel": self.channel_key, 
                    "pos": self.pos
                }))
                
                print(f"📡 Sweep step: {self.channel_key} → {self.pos}")

            def stop(self):
                """Stop the sweep"""
                self.timer.stop()
                
                # Reset to center position
                center_pos = (self.minv + self.maxv) // 2
                self.pos = center_pos
                self.label.setText(f"V: {center_pos}")
                self.slider.setValue(center_pos)
                
                # Move servo to center
                self.parent_screen.websocket.send_safe(json.dumps({
                    "type": "servo", 
                    "channel": self.channel_key, 
                    "pos": center_pos
                }))
                
                # Update UI
                self.btn.setText("▶")
                self.btn.setChecked(False)
                
                print(f"🛑 Sweep stopped: {self.channel_key} returned to center ({center_pos})")

        # Create sweep with reference to this screen instance
        sweep = Sweep(self, key, pos_label, button, slider, min_val, max_val, speed)
        self.active_sweep = sweep
        button.setText("⏸")
        print(f"▶️ Sweep started for {key}")

    def stop_all_sweeps(self):
        """Stop any active sweeps when switching Maestros"""
        if self.active_sweep:
            self.active_sweep.stop()
            self.active_sweep = None
            print("🛑 All sweeps stopped")
    def __init__(self, websocket):
        super().__init__()
        self.websocket = websocket
        self.setFixedWidth(1180)
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        self.servo_config = self.load_config()
        self.active_sweep = None
        
        # 🔥 NEW: Track channel counts for each Maestro
        self.maestro_channel_counts = {1: 18, 2: 18}  # Default fallback
        self.current_maestro = 1
        self.channels_loaded = False
        
        # 🔥 NEW: Track servo widgets for position updates
        self.servo_widgets = {}  # Will store {channel_key: (slider, pos_label, ...)}
        self.position_update_timer = QTimer()
        self.position_update_timer.timeout.connect(self.update_all_positions)
        self.auto_update_positions = True  # Toggle for auto-refresh

        # Maestro selector dropdown
        self.maestro1_btn = QPushButton()
        self.maestro2_btn = QPushButton()
        self.maestro1_btn.setCheckable(True)
        self.maestro2_btn.setCheckable(True)
        
        # Load icons if they exist
        if os.path.exists("icons/M1.png"):
            self.maestro1_btn.setIcon(QIcon("icons/M1.png"))
            self.maestro1_btn.setIconSize(QSize(112,118))
        if os.path.exists("icons/M2.png"):
            self.maestro2_btn.setIcon(QIcon("icons/M2.png"))
            self.maestro2_btn.setIconSize(QSize(112,118))

        self.maestro_group = QButtonGroup()
        self.maestro_group.setExclusive(True)
        self.maestro_group.addButton(self.maestro1_btn, 0)
        self.maestro_group.addButton(self.maestro2_btn, 1)
        self.maestro_group.idClicked.connect(self.on_maestro_changed)

        self.maestro1_btn.setChecked(True)
        self.update_maestro_icons(0)

        # Add refresh button
        self.refresh_btn = QPushButton("Update")
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
        self.refresh_btn.clicked.connect(self.refresh_maestro_data)

        # 🔥 NEW: Add status label to show channel detection
        self.status_label = QLabel("Detecting channels...")
        self.status_label.setFont(QFont("Arial", 14))
        self.status_label.setStyleSheet("color: #FFAA00; padding: 5px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 🔥 NEW: Add position refresh controls
        self.setup_position_controls()

        # Scrollable grid area
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.grid_widget.setLayout(self.grid_layout)
        self.grid_widget.setStyleSheet("QWidget { border: 1px solid #555; border-radius: 12px; }")

        # 🔥 NEW: Connect to WebSocket for responses
        self.websocket.textMessageReceived.connect(self.handle_websocket_message)

        # Setup UI layout
        self.setup_layout()
        
        # 🔥 NEW: Request channel counts from backend on startup
        self.request_maestro_info()

    def setup_position_controls(self):
        """Setup controls for position reading"""
        # Auto-update checkbox
        self.auto_update_checkbox = QCheckBox("Auto-refresh positions")
        self.auto_update_checkbox.setChecked(True)
        self.auto_update_checkbox.setFont(QFont("Arial", 12))
        self.auto_update_checkbox.setStyleSheet("color: white;")
        self.auto_update_checkbox.toggled.connect(self.toggle_auto_update)
        
        # Manual refresh button
        self.read_positions_btn = QPushButton("📍 Read Positions")
        self.read_positions_btn.setFont(QFont("Arial", 12))
        self.read_positions_btn.clicked.connect(self.read_all_positions_now)
        self.read_positions_btn.setStyleSheet("""
            QPushButton {
                background-color: #444;
                color: white;
                border-radius: 8px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)

    def setup_layout(self):
        """Enhanced layout with position controls"""
        # Main layout
        grid_and_selector_layout = QHBoxLayout()
        grid_and_selector_layout.addSpacing(80)

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
        # 🔥 NEW: Add position controls
        selector_container.addWidget(self.auto_update_checkbox)
        selector_container.addWidget(self.read_positions_btn)
        selector_container.addStretch()

        # Create a QWidget to hold the selector layout
        selector_widget = QWidget()
        selector_widget.setLayout(selector_container)
        selector_widget.setStyleSheet("background-color: rgba(0, 0, 0, 0);")

        # Add selector widget to the right of the grid
        grid_and_selector_layout.addWidget(scroll_area, stretch=3)
        grid_and_selector_layout.addWidget(selector_widget)

        # Final layout with status
        layout = QVBoxLayout()
        layout.addWidget(self.status_label)
        layout.addLayout(grid_and_selector_layout)
        self.setLayout(layout)

    # 🔥 NEW: Handle WebSocket messages
    @error_boundary
    def handle_websocket_message(self, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "maestro_info":
                maestro_num = data.get("maestro")
                channels = data.get("channels", 0)
                connected = data.get("connected", False)
                
                if maestro_num in [1, 2]:
                    self.maestro_channel_counts[maestro_num] = channels
                    print(f"📡 Maestro {maestro_num}: {channels} channels, connected: {connected}")
                    
                    # Update status
                    if connected:
                        self.update_status(f"Maestro {maestro_num}: {channels} channels detected")
                    else:
                        self.update_status(f"Maestro {maestro_num}: Not connected")
                    
                    # Refresh grid if this is the current maestro
                    if maestro_num == self.current_maestro + 1:
                        self.update_grid()
            
            # 🔥 NEW: Handle servo position responses
            elif msg_type == "servo_position":
                channel_key = data.get("channel")
                position = data.get("position")
                
                if channel_key and position is not None:
                    self.update_servo_position_display(channel_key, position)
            
            # 🔥 NEW: Handle batch position responses
            elif msg_type == "all_servo_positions":
                maestro_num = data.get("maestro")
                positions = data.get("positions", {})
                
                print(f"📍 Received {len(positions)} positions for Maestro {maestro_num}")
                
                for channel, position in positions.items():
                    channel_key = f"m{maestro_num}_ch{channel}"
                    if position is not None:
                        self.update_servo_position_display(channel_key, position)
                        
        except Exception as e:
            print(f"Error handling WebSocket message: {e}")

    # 🔥 NEW: Update servo position display
    def update_servo_position_display(self, channel_key, position):
        """Update the UI to show actual servo position"""
        if channel_key in self.servo_widgets:
            slider, pos_label = self.servo_widgets[channel_key][:2]
            
            # Update slider position (without triggering servo movement)
            slider.blockSignals(True)  # Prevent triggering servo command
            slider.setValue(position)
            slider.blockSignals(False)
            
            # Update position label
            pos_label.setText(f"V: {position}")
            pos_label.setStyleSheet("color: white;")  # White for read position
            
            print(f"📍 Updated display: {channel_key} = {position}")

    # 🔥 NEW: Toggle auto-update
    def toggle_auto_update(self, enabled):
        """Toggle automatic position updates"""
        self.auto_update_positions = enabled
        
        if enabled:
            self.position_update_timer.start(2000)  # Update every 2 seconds
            self.update_status("Auto-refresh positions: ON")
            print("🔄 Auto position updates enabled")
        else:
            self.position_update_timer.stop()
            self.update_status("Auto-refresh positions: OFF")
            print("⏸️ Auto position updates disabled")

    # 🔥 NEW: Read all positions now
    def read_all_positions_now(self):
        """Manually trigger reading all servo positions"""
        maestro_num = self.current_maestro + 1
        
        self.websocket.send_safe(json.dumps({
            "type": "get_all_servo_positions",
            "maestro": maestro_num
        }))
        
        self.update_status(f"Reading positions from Maestro {maestro_num}...")
        print(f"📡 Requesting all positions from Maestro {maestro_num}")

    # 🔥 NEW: Auto-update all positions
    def update_all_positions(self):
        """Automatically update all servo positions"""
        if not self.auto_update_positions:
            return
        
        maestro_num = self.current_maestro + 1
        
        # Only update if we have servo widgets and maestro is connected
        if self.servo_widgets:
            self.websocket.send_safe(json.dumps({
                "type": "get_all_servo_positions", 
                "maestro": maestro_num
            }))
            print(f"🔄 Auto-updating positions for Maestro {maestro_num}")

    # 🔥 NEW: Request maestro information
    def request_maestro_info(self):
        """Request channel count and status from both Maestros"""
        self.update_status("Requesting Maestro information...")
        
        # Request info for both Maestros
        for maestro_num in [1, 2]:
            self.websocket.send_safe(json.dumps({
                "type": "get_maestro_info",
                "maestro": maestro_num
            }))
        
        print("📡 Requested Maestro information from backend")

    # 🔥 NEW: Refresh maestro data
    def refresh_maestro_data(self):
        """Refresh maestro data and rebuild grid"""
        self.request_maestro_info()
        # Also refresh servo config
        self.reload_servo_config()

    # 🔥 NEW: Handle maestro selection change
    def on_maestro_changed(self, maestro_index):
        """Handle maestro selection change"""
        self.current_maestro = maestro_index
        self.update_maestro_icons(maestro_index)
        self.stop_all_sweeps()  # Stop any active sweeps
        self.update_grid()  # Rebuild grid for new maestro
        
        # Update status
        maestro_num = maestro_index + 1
        channels = self.maestro_channel_counts.get(maestro_num, 0)
        self.update_status(f"Maestro {maestro_num}: {channels} channels")

    # 🔥 NEW: Update status label
    def update_status(self, message):
        """Update the status label"""
        self.status_label.setText(message)
        print(f"🔄 Status: {message}")

    @error_boundary
    def update_maestro_icons(self, checked_id):
        # Set pressed icon for selected, normal for unselected
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
        return config_manager.get_config("configs/servo_config.json")

    @error_boundary
    def save_config(self):
        with open("configs/servo_config.json", "w") as f:
            json.dump(self.servo_config, f, indent=2)
        config_manager.clear_cache()  # Clear cache after save

    @error_boundary
    def reload_servo_config(self):
        config_manager.clear_cache()
        self.servo_config = config_manager.get_config("configs/servo_config.json")
        self.update_grid()
        print("Servo config reloaded successfully.")

    def update_config(self, key, field, value):
        if key not in self.servo_config:
            self.servo_config[key] = {}
        self.servo_config[key][field] = value
        self.save_config()

    # 🔥 UPDATED: Modified update_grid to use dynamic channel count and track widgets
    @error_boundary
    def update_grid(self):
        font = QFont("Arial", 16)

        # Stop any active sweeps when rebuilding grid
        self.stop_all_sweeps()
        
        # Stop position updates while rebuilding
        self.position_update_timer.stop()
        
        # Clear existing widgets and tracking
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        
        self.servo_widgets.clear()  # Clear widget tracking

        maestro_index = self.maestro_group.checkedId()
        maestro_num = maestro_index + 1
        
        # Get dynamic channel count
        channel_count = self.maestro_channel_counts.get(maestro_num, 18)
        
        print(f"🔄 Building grid for Maestro {maestro_num} with {channel_count} channels")
        
        # Create grid for actual detected channels
        for i in range(channel_count):
            channel_key = f"m{maestro_num}_ch{i}"
            config = self.servo_config.get(channel_key, {})
            row = i

            label = QLabel(f"Channel {i}")
            label.setFont(font)
            self.grid_layout.addWidget(label, row, 0)

            name_edit = QLineEdit(config.get("name", ""))
            name_edit.setFont(font)
            name_edit.setMaxLength(32)
            name_edit.setPlaceholderText("Friendly Name")
            name_edit.textChanged.connect(lambda text, k=channel_key: self.update_config(k, "name", text))
            self.grid_layout.addWidget(name_edit, row, 1)

            # Slider for position control
            slider = QSlider(Qt.Orientation.Horizontal)
            min_val = config.get("min", 992)
            max_val = config.get("max", 2000)
            slider.setMinimum(min_val)
            slider.setMaximum(max_val)
            slider.setValue((min_val + max_val) // 2)  # Default to center
            slider.setFixedWidth(150)
            self.grid_layout.addWidget(slider, row, 2)

            # Min value controls
            min_label = QLabel("Min")
            min_label.setFont(font)
            self.grid_layout.addWidget(min_label, row, 3)
            
            min_spin = QSpinBox()
            min_spin.setFont(font)
            min_spin.setRange(0, 2500)
            min_spin.setValue(min_val)
            min_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "min", val))
            min_spin.valueChanged.connect(lambda val, s=slider: s.setMinimum(val))
            self.grid_layout.addWidget(min_spin, row, 4)

            # Max value controls
            max_label = QLabel("Max")
            max_label.setFont(font)
            self.grid_layout.addWidget(max_label, row, 5)
            
            max_spin = QSpinBox()
            max_spin.setFont(font)
            max_spin.setRange(0, 2500)
            max_spin.setValue(max_val)
            max_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "max", val))
            max_spin.valueChanged.connect(lambda val, s=slider: s.setMaximum(val))
            self.grid_layout.addWidget(max_spin, row, 6)

            # Speed control
            speed_label = QLabel("S")
            speed_label.setFont(font)
            self.grid_layout.addWidget(speed_label, row, 7)
            
            speed_spin = QSpinBox()
            speed_spin.setFont(font)
            speed_spin.setRange(0, 100)
            speed_spin.setValue(config.get("speed", 0))
            speed_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "speed", val))
            self.grid_layout.addWidget(speed_spin, row, 8)

            # Acceleration control
            accel_label = QLabel("A")
            accel_label.setFont(font)
            self.grid_layout.addWidget(accel_label, row, 9)
            
            accel_spin = QSpinBox()
            accel_spin.setFont(font)
            accel_spin.setRange(0, 100)
            accel_spin.setValue(config.get("accel", 0))
            accel_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "accel", val))
            self.grid_layout.addWidget(accel_spin, row, 10)

            # Position label - will show actual position
            pos_label = QLabel("V: ---")  # 🔥 Changed default to show we're loading
            pos_label.setFont(font)
            pos_label.setStyleSheet("color: #FFAA00;")  # Orange while loading
            self.grid_layout.addWidget(pos_label, row, 11)

            # Play/sweep button
            play_btn = QPushButton("▶")
            play_btn.setFont(font)
            play_btn.setCheckable(True)
            play_btn.clicked.connect(lambda checked, k=channel_key, p=pos_label, b=play_btn, s=slider, min_spin=min_spin, max_spin=max_spin, speed_spin=speed_spin: self.toggle_sweep(k, p, b, s, min_spin.value(), max_spin.value(), speed_spin.value()))
            self.grid_layout.addWidget(play_btn, row, 12)

            # Connect slider to servo movement
            slider.valueChanged.connect(
                lambda val, k=channel_key, p=pos_label: self.update_servo_position(k, p, val)
            )

            # 🔥 NEW: Track widgets for position updates
            self.servo_widgets[channel_key] = (slider, pos_label, play_btn)

        # Update status to show completed grid
        self.update_status(f"Maestro {maestro_num}: {channel_count} channels loaded")
        
        # 🔥 NEW: Start reading positions after grid is built
        QTimer.singleShot(500, self.read_all_positions_now)  # Small delay to let UI settle
        
        # 🔥 NEW: Restart auto-updates if enabled
        if self.auto_update_positions:
            self.position_update_timer.start(2000)

    # 🔥 UPDATED: Enhanced servo position update with real movement
    def update_servo_position(self, channel_key, pos_label, value):
        """Update servo position with enhanced feedback"""
        
        # Get current channel configuration
        config = self.servo_config.get(channel_key, {})
        speed = config.get("speed", 0)
        accel = config.get("accel", 0)
        
        # Apply speed and acceleration settings if they exist
        if speed > 0 or accel > 0:
            print(f"⚙️ Applying settings to {channel_key}: speed={speed}, accel={accel}")
            
            # Send speed setting first (if configured)
            if speed > 0:
                self.websocket.send_safe(json.dumps({
                    "type": "servo_speed",
                    "channel": channel_key, 
                    "speed": speed
                }))
            
            # Send acceleration setting (if configured)
            if accel > 0:
                self.websocket.send_safe(json.dumps({
                    "type": "servo_acceleration", 
                    "channel": channel_key,
                    "acceleration": accel
                }))
        
        # Send position command
        self.websocket.send_safe(json.dumps({
            "type": "servo", 
            "channel": channel_key, 
            "pos": value
        }))
        
        # Update UI immediately (optimistic update)
        pos_label.setText(f"V: {value}")
        pos_label.setStyleSheet("color: #44FF44;")  # Green for commanded position
        
        print(f"📡 Servo command: {channel_key} → {value}")

    # 🔥 UPDATED: Enhanced sweep with real servo movement
    def toggle_sweep(self, key, pos_label, button, slider, min_val, max_val, speed):
        """Toggle servo sweep with real servo movement"""
        if self.active_sweep:
            self.active_sweep.stop()
            self.active_sweep = None
            button.setText("▶")
            button.setChecked(False)
            return

        class Sweep:
            def __init__(self, parent_screen, channel_key, label, btn, slider, minv, maxv, speedv):
                self.parent_screen = parent_screen  # Reference to ServoConfigScreen
                self.channel_key = channel_key      # e.g., "m1_ch5"
                self.label = label
                self.btn = btn
                self.slider = slider
                self.minv = minv
                self.maxv = maxv
                self.speedv = speedv
                
                # Calculate step size and timing
                self.step_size = max(1, (maxv - minv) // 50)  # ~50 steps across range
                self.timer = QTimer()
                self.timer.timeout.connect(self.step)
                
                # Position tracking
                self.pos = minv
                self.direction = 1
                
                # Timer interval based on speed (higher speed = faster updates)
                interval = max(20, 200 - (speedv * 2))
                self.timer.start(interval)
                
                print(f"🎭 Starting sweep on {channel_key}: {minv}-{maxv}, speed={speedv}, step={self.step_size}, interval={interval}ms")

            def step(self):
                """Execute one step of the sweep"""
                # Update position
                self.pos += self.direction * self.step_size
                
                # Check bounds and reverse direction
                if self.pos >= self.maxv:
                    self.pos = self.maxv
                    self.direction = -1
                elif self.pos <= self.minv:
                    self.pos = self.minv
                    self.direction = 1
                
                # Update UI
                self.label.setText(f"V: {self.pos}")
                self.slider.setValue(self.pos)
                
                # 🔥 THE KEY FIX: Actually move the servo!
                self.parent_screen.websocket.send_safe(json.dumps({
                    "type": "servo", 
                    "channel": self.channel_key, 
                    "pos": self.pos
                }))
                
                print(f"📡 Sweep step: {self.channel_key} → {self.pos}")

            def stop(self):
                """Stop the sweep"""
                self.timer.stop()
                
                # Reset to center position
                center_pos = (self.minv + self.maxv) // 2
                self.pos = center_pos
                self.label.setText(f"V: {center_pos}")
                self.slider.setValue(center_pos)
                
                # Move servo to center
                self.parent_screen.websocket.send_safe(json.dumps({
                    "type": "servo", 
                    "channel": self.channel_key, 
                    "pos": center_pos
                }))
                
                # Update UI
                self.btn.setText("▶")
                self.btn.setChecked(False)
                
                print(f"🛑 Sweep stopped: {self.channel_key} returned to center ({center_pos})")

        # Create sweep with reference to this screen instance
        sweep = Sweep(self, key, pos_label, button, slider, min_val, max_val, speed)
        self.active_sweep = sweep
        button.setText("⏸")
        print(f"▶️ Sweep started for {key}")

    def stop_all_sweeps(self):
        """Stop any active sweeps when switching Maestros"""
        if self.active_sweep:
            self.active_sweep.stop()
            self.active_sweep = None
            print("🛑 All sweeps stopped")
    def __init__(self, websocket):
        super().__init__()
        self.websocket = websocket
        self.setFixedWidth(1180)
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        self.servo_config = self.load_config()
        self.active_sweep = None

        # Maestro selector dropdown
        self.maestro1_btn = QPushButton()
        self.maestro2_btn = QPushButton()
        self.maestro1_btn.setCheckable(True)
        self.maestro2_btn.setCheckable(True)
        
        # Load icons if they exist
        if os.path.exists("icons/M1.png"):
            self.maestro1_btn.setIcon(QIcon("icons/M1.png"))
            self.maestro1_btn.setIconSize(QSize(112,118))
        if os.path.exists("icons/M2.png"):
            self.maestro2_btn.setIcon(QIcon("icons/M2.png"))
            self.maestro2_btn.setIconSize(QSize(112,118))

        self.maestro_group = QButtonGroup()
        self.maestro_group.setExclusive(True)
        self.maestro_group.addButton(self.maestro1_btn, 0)
        self.maestro_group.addButton(self.maestro2_btn, 1)
        self.maestro_group.idClicked.connect(self.update_grid)
        self.maestro_group.idClicked.connect(self.update_maestro_icons)

        self.maestro1_btn.setChecked(True)
        self.update_maestro_icons(0)

        # Add refresh button
        self.refresh_btn = QPushButton("Update")
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
        self.refresh_btn.clicked.connect(self.reload_servo_config)
        self.refresh_btn.clicked.connect(self.update_grid)

        # Scrollable grid area
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.grid_widget.setLayout(self.grid_layout)
        self.grid_widget.setStyleSheet("QWidget { border: 1px solid #555; border-radius: 12px; }")

        # Main layout
        grid_and_selector_layout = QHBoxLayout()
        grid_and_selector_layout.addSpacing(80)

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
        selector_container.addStretch()

        # Create a QWidget to hold the selector layout
        selector_widget = QWidget()
        selector_widget.setLayout(selector_container)
        selector_widget.setStyleSheet("background-color: rgba(0, 0, 0, 0);")

        # Add selector widget to the right of the grid
        grid_and_selector_layout.addWidget(scroll_area, stretch=3)
        grid_and_selector_layout.addWidget(selector_widget)

        # Final layout
        layout = QVBoxLayout()
        layout.addLayout(grid_and_selector_layout)
        self.setLayout(layout)
        self.update_grid()

    @error_boundary
    def update_maestro_icons(self, checked_id):
        # Set pressed icon for selected, normal for unselected
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
        return config_manager.get_config("configs/servo_config.json")

    @error_boundary
    def save_config(self):
        with open("configs/servo_config.json", "w") as f:
            json.dump(self.servo_config, f, indent=2)
        config_manager.clear_cache()  # Clear cache after save

    @error_boundary
    def reload_servo_config(self):
        config_manager.clear_cache()
        self.servo_config = config_manager.get_config("configs/servo_config.json")
        self.update_grid()
        print("Servo config reloaded successfully.")

    def update_config(self, key, field, value):
        if key not in self.servo_config:
            self.servo_config[key] = {}
        self.servo_config[key][field] = value
        self.save_config()

    @error_boundary
    def update_grid(self):
        font = QFont("Arial", 16)
        self.stop_all_sweeps()

        # Clear existing widgets
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        maestro_index = self.maestro_group.checkedId()

        for i in range(18):
            channel_key = f"m{maestro_index+1}_ch{i}"
            config = self.servo_config.get(channel_key, {})
            row = i

            label = QLabel(f"Channel {i}")
            label.setFont(font)
            self.grid_layout.addWidget(label, row, 0)

            name_edit = QLineEdit(config.get("name", ""))
            name_edit.setFont(font)
            name_edit.setMaxLength(32)
            name_edit.setPlaceholderText("Friendly Name")
            name_edit.textChanged.connect(lambda text, k=channel_key: self.update_config(k, "name", text))
            self.grid_layout.addWidget(name_edit, row, 1)

            min_spin = QSpinBox()
            min_spin.setFont(font)
            min_spin.setRange(0, 2500)
            min_spin.setValue(config.get("min", 992))
            min_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "min", val))
            
            min_label = QLabel("Min")
            min_label.setFont(font)
            self.grid_layout.addWidget(min_label, row, 3)
            self.grid_layout.addWidget(min_spin, row, 4)

            max_spin = QSpinBox()
            max_spin.setFont(font)
            max_spin.setRange(0, 2500)
            max_spin.setValue(config.get("max", 2000))
            max_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "max", val))
            max_label = QLabel("Max")
            max_label.setFont(font)
            self.grid_layout.addWidget(max_label, row, 5)
            self.grid_layout.addWidget(max_spin, row, 6)
            
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setMinimum(min_spin.value())
            slider.setMaximum(max_spin.value())
            slider.setValue((min_spin.value() + max_spin.value()) // 2)
            slider.setFixedWidth(150)
            self.grid_layout.addWidget(slider, row, 2)

            speed_spin = QSpinBox()
            speed_spin.setFont(font)
            speed_spin.setRange(0, 100)
            speed_spin.setValue(config.get("speed", 0))
            speed_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "speed", val))
            speed_label = QLabel("S")
            speed_label.setFont(font)
            self.grid_layout.addWidget(speed_label, row, 7)
            self.grid_layout.addWidget(speed_spin, row, 8)

            accel_spin = QSpinBox()
            accel_spin.setFont(font)
            accel_spin.setRange(0, 100)
            accel_spin.setValue(config.get("accel", 0))
            accel_spin.valueChanged.connect(lambda val, k=channel_key: self.update_config(k, "accel", val))
            accel_label = QLabel("A")
            accel_label.setFont(font)
            self.grid_layout.addWidget(accel_label, row, 9)
            self.grid_layout.addWidget(accel_spin, row, 10)

            play_btn = QPushButton("▶")
            play_btn.setFont(font)
            play_btn.setCheckable(True)
            pos_label = QLabel("V: 0")
            pos_label.setFont(font)
            self.grid_layout.addWidget(pos_label, row, 11)

            slider.valueChanged.connect(
                lambda val, k=channel_key, p=pos_label: self.update_servo_position(k, p, val)
            )

            play_btn.clicked.connect(lambda checked, k=channel_key, p=pos_label, b=play_btn, s=slider, min_spin=min_spin, max_spin=max_spin, speed_spin=speed_spin: self.toggle_sweep(k, p, b, s, min_spin.value(), max_spin.value(), speed_spin.value()))
            self.grid_layout.addWidget(play_btn, row, 12)
    
    def update_servo_position(self, channel_key, pos_label, value):
        """Update servo position with speed/acceleration settings applied"""
        
        # Get current channel configuration
        config = self.servo_config.get(channel_key, {})
        speed = config.get("speed", 0)
        accel = config.get("accel", 0)
        
        # Apply speed and acceleration settings if they exist
        if speed > 0 or accel > 0:
            print(f"⚙️ Applying settings to {channel_key}: speed={speed}, accel={accel}")
            
            # Send speed setting first (if configured)
            if speed > 0:
                self.websocket.send_safe(json.dumps({
                    "type": "servo_speed",
                    "channel": channel_key, 
                    "speed": speed
                }))
            
            # Send acceleration setting (if configured)
            if accel > 0:
                self.websocket.send_safe(json.dumps({
                    "type": "servo_acceleration", 
                    "channel": channel_key,
                    "acceleration": accel
                }))
        
        # Send position command
        self.websocket.send_safe(json.dumps({
            "type": "servo", 
            "channel": channel_key, 
            "pos": value
        }))
        
        # Update UI
        pos_label.setText(f"V: {value}")
        print(f"📡 Servo command: {channel_key} → {value}")

    def stop_all_sweeps(self):
        """Stop any active sweeps when switching Maestros"""
        if self.active_sweep:
            self.active_sweep.stop()
            self.active_sweep = None
            print("🛑 All sweeps stopped")

    def toggle_sweep(self, key, pos_label, button, slider, min_val, max_val, speed):
        """Toggle servo sweep with real servo movement"""
        if self.active_sweep:
            self.active_sweep.stop()
            self.active_sweep = None
            button.setText("▶")
            button.setChecked(False)
            return

        class Sweep:
            def __init__(self, parent_screen, channel_key, label, btn, slider, minv, maxv, speedv):
                self.parent_screen = parent_screen  # Reference to ServoConfigScreen
                self.channel_key = channel_key      # e.g., "m1_ch5"
                self.label = label
                self.btn = btn
                self.slider = slider
                self.minv = minv
                self.maxv = maxv
                self.speedv = speedv
                
                # Calculate step size and timing
                self.step_size = max(1, (maxv - minv) // 50)  # ~50 steps across range
                self.timer = QTimer()
                self.timer.timeout.connect(self.step)
                
                # Position tracking
                self.pos = minv
                self.direction = 1
                
                # Timer interval based on speed (higher speed = faster updates)
                # Speed 0-100 maps to 200ms-20ms intervals
                interval = max(20, 200 - (speedv * 2))
                self.timer.start(interval)
                
                print(f"🎭 Starting sweep on {channel_key}: {minv}-{maxv}, speed={speedv}, step={self.step_size}, interval={interval}ms")

            def step(self):
                """Execute one step of the sweep"""
                # Update position
                self.pos += self.direction * self.step_size
                
                # Check bounds and reverse direction
                if self.pos >= self.maxv:
                    self.pos = self.maxv
                    self.direction = -1
                elif self.pos <= self.minv:
                    self.pos = self.minv
                    self.direction = 1
                
                # Update UI
                self.label.setText(f"V: {self.pos}")
                self.slider.setValue(self.pos)
                
                # 🔥 THE KEY FIX: Actually move the servo!
                self.parent_screen.websocket.send_safe(json.dumps({
                    "type": "servo", 
                    "channel": self.channel_key, 
                    "pos": self.pos
                }))
                
                print(f"📡 Sweep step: {self.channel_key} → {self.pos}")

            def stop(self):
                """Stop the sweep"""
                self.timer.stop()
                
                # Reset to center position
                center_pos = (self.minv + self.maxv) // 2
                self.pos = center_pos
                self.label.setText(f"V: {center_pos}")
                self.slider.setValue(center_pos)
                
                # Move servo to center
                self.parent_screen.websocket.send_safe(json.dumps({
                    "type": "servo", 
                    "channel": self.channel_key, 
                    "pos": center_pos
                }))
                
                # Update UI
                self.btn.setText("▶")
                self.btn.setChecked(False)
                
                print(f"🛑 Sweep stopped: {self.channel_key} returned to center ({center_pos})")

        # Create sweep with reference to this screen instance
        sweep = Sweep(self, key, pos_label, button, slider, min_val, max_val, speed)
        self.active_sweep = sweep
        button.setText("⏸")
        print(f"▶️ Sweep started for {key}")


# PERFORMANCE IMPROVEMENT 5: Optimized Camera Screen
class CameraFeedScreen(QWidget):
    def __init__(self, websocket):
        super().__init__()
        self.websocket = websocket
        self.sample_buffer = deque(maxlen=SAMPLE_DURATION * SAMPLE_RATE)
        self.last_wave_time = 0
        self.last_sample_time = 0
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        self.tracking_enabled = False
        
        # Use threading for image processing
        config = config_manager.get_config("configs/steamdeck_config.json")
        esp32_url = config.get("current", {}).get("esp32_cam_url", "")
        self.image_thread = ImageProcessingThread(esp32_url)
        self.image_thread.frame_processed.connect(self.update_display)
        self.image_thread.stats_updated.connect(self.update_stats)
        
        self.init_ui()
        
    def init_ui(self):
        """Optimized UI setup"""
        self.video_label = QLabel()
        self.video_label.setFixedSize(640, 480)
        self.video_label.setStyleSheet("""
            border: 2px solid #555;
            border-radius: 20px;
            background-color: black;
        """)
        
        self.stats_label = QLabel("Stream Stats: Initializing...")
        self.stats_label.setStyleSheet("""
            border: 1px solid #555;
            border-radius: 4px;
            background-color: black;
            color: #aaa;   
        """)
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.stats_label.setFixedWidth(640)
        
        # Control buttons
        self.setup_control_buttons()
        self.setup_layout()
        
        # Start image processing thread
        self.image_thread.start()
    
    def setup_control_buttons(self):
        """Setup control buttons with proper styling"""
        self.reconnect_button = QPushButton()
        if os.path.exists("icons/Reconnect.png"):
            self.reconnect_button.setIcon(QIcon("icons/Reconnect.png"))
        self.reconnect_button.clicked.connect(self.reconnect_stream)
        self.reconnect_button.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white;")
        
        self.tracking_button = QPushButton()
        self.tracking_button.setCheckable(True)
        if os.path.exists("icons/Tracking.png"):
            self.tracking_button.setIcon(QIcon("icons/Tracking.png"))
        self.tracking_button.clicked.connect(self.toggle_tracking)
        self.tracking_button.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white;")
    
    def setup_layout(self):
        """Setup optimized layout"""
        video_layout = QVBoxLayout()
        video_layout.addWidget(self.video_label)
        video_layout.addWidget(self.stats_label)
        
        button_layout = QVBoxLayout()
        button_layout.setSpacing(0)
        button_layout.addWidget(self.reconnect_button)
        button_layout.addWidget(self.tracking_button)
        button_layout.addSpacing(200)
        
        main_layout = QHBoxLayout()
        main_layout.addSpacing(81)
        main_layout.addLayout(video_layout, 2)
        main_layout.addLayout(button_layout, 1)
        
        self.setLayout(main_layout)
    
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
            
            # Handle wave detection logic
            if self.tracking_enabled and wave_detected:
                current_time = time.time()
                if current_time - self.last_sample_time >= 1.0 / SAMPLE_RATE:
                    self.sample_buffer.append(wave_detected)
                    self.last_sample_time = current_time
                
                if len(self.sample_buffer) == self.sample_buffer.maxlen:
                    confidence = sum(self.sample_buffer) / len(self.sample_buffer)
                    if confidence >= CONFIDENCE_THRESHOLD:
                        if current_time - self.last_wave_time >= STAND_DOWN_TIME:
                            self.websocket.send_safe(json.dumps({
                                "type": "gesture",
                                "name": "wave"
                            }))
                            self.last_wave_time = current_time
                            self.sample_buffer.clear()
            
            # Convert to QPixmap and display
            height, width, channel = frame_rgb.shape
            bytes_per_line = 3 * width
            q_img = QImage(frame_rgb.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img).scaled(
                self.video_label.size(), 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.FastTransformation  # Use fast transformation
            )
            self.video_label.setPixmap(pixmap)
            
        except Exception as e:
            print(f"Display update error: {e}")
            self.video_label.setText(f"Display Error:\n{str(e)}")
    
    def update_stats(self, stats_text):
        """Update statistics display"""
        self.stats_label.setText(f"Stream Stats: {stats_text}")
    
    @error_boundary
    def toggle_tracking(self):
        """Toggle tracking with thread communication"""
        self.tracking_enabled = self.tracking_button.isChecked()
        self.image_thread.set_tracking_enabled(self.tracking_enabled)
        
        if self.tracking_enabled and os.path.exists("icons/Tracking_pressed.png"):
            self.tracking_button.setIcon(QIcon("icons/Tracking_pressed.png"))
        elif os.path.exists("icons/Tracking.png"):
            self.tracking_button.setIcon(QIcon("icons/Tracking.png"))
        
        self.websocket.send_safe(json.dumps({
            "type": "tracking",
            "state": self.tracking_enabled
        }))
    
    @error_boundary
    def reconnect_stream(self):
        """Reconnect stream by restarting image thread"""
        self.image_thread.stop()
        config = config_manager.get_config("configs/steamdeck_config.json")
        esp32_url = config.get("current", {}).get("esp32_cam_url", "")
        self.image_thread = ImageProcessingThread(esp32_url)
        self.image_thread.frame_processed.connect(self.update_display)
        self.image_thread.stats_updated.connect(self.update_stats)
        self.image_thread.start()
        self.stats_label.setText("Stream Stats: Reconnected")
    
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
    
    def closeEvent(self, event):
        """Proper cleanup on close"""
        self.image_thread.stop()
        event.accept()


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
        self.grid_layout.setSpacing(15)
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

# PERFORMANCE IMPROVEMENT 5: Optimized Camera Screen
class CameraFeedScreen(QWidget):
    def __init__(self, websocket):
        super().__init__()
        self.websocket = websocket
        self.sample_buffer = deque(maxlen=SAMPLE_DURATION * SAMPLE_RATE)
        self.last_wave_time = 0
        self.last_sample_time = 0
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        self.tracking_enabled = False
        
        # Use camera proxy URL instead of direct ESP32 URL
        config = config_manager.get_config("configs/steamdeck_config.json")
        camera_proxy_url = config.get("current", {}).get("camera_proxy_url", "")
        self.image_thread = ImageProcessingThread(camera_proxy_url)
        self.image_thread.frame_processed.connect(self.update_display)
        self.image_thread.stats_updated.connect(self.update_stats)
        
        self.init_ui()
        
    def init_ui(self):
        """Optimized UI setup"""
        self.video_label = QLabel()
        self.video_label.setFixedSize(640, 480)
        self.video_label.setStyleSheet("""
            border: 2px solid #555;
            border-radius: 20px;
            background-color: black;
        """)
        
        self.stats_label = QLabel("Stream Stats: Initializing...")
        self.stats_label.setStyleSheet("""
            border: 1px solid #555;
            border-radius: 4px;
            background-color: black;
            color: #aaa;   
        """)
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.stats_label.setFixedWidth(640)
        
        # Control buttons
        self.setup_control_buttons()
        self.setup_layout()
        
        # Start image processing thread
        self.image_thread.start()
    
    def setup_control_buttons(self):
        """Setup control buttons with proper styling"""
        self.reconnect_button = QPushButton()
        if os.path.exists("icons/Reconnect.png"):
            self.reconnect_button.setIcon(QIcon("icons/Reconnect.png"))
        self.reconnect_button.clicked.connect(self.reconnect_stream)
        self.reconnect_button.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white;")
        
        self.tracking_button = QPushButton()
        self.tracking_button.setCheckable(True)
        if os.path.exists("icons/Tracking.png"):
            self.tracking_button.setIcon(QIcon("icons/Tracking.png"))
        self.tracking_button.clicked.connect(self.toggle_tracking)
        self.tracking_button.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white;")
    
    def setup_layout(self):
        """Setup optimized layout"""
        video_layout = QVBoxLayout()
        video_layout.addWidget(self.video_label)
        video_layout.addWidget(self.stats_label)
        
        button_layout = QVBoxLayout()
        button_layout.setSpacing(0)
        button_layout.addWidget(self.reconnect_button)
        button_layout.addWidget(self.tracking_button)
        button_layout.addSpacing(200)
        
        main_layout = QHBoxLayout()
        main_layout.addSpacing(81)
        main_layout.addLayout(video_layout, 2)
        main_layout.addLayout(button_layout, 1)
        
        self.setLayout(main_layout)
    
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
            
            # Handle wave detection logic
            if self.tracking_enabled and wave_detected:
                current_time = time.time()
                if current_time - self.last_sample_time >= 1.0 / SAMPLE_RATE:
                    self.sample_buffer.append(wave_detected)
                    self.last_sample_time = current_time
                
                if len(self.sample_buffer) == self.sample_buffer.maxlen:
                    confidence = sum(self.sample_buffer) / len(self.sample_buffer)
                    if confidence >= CONFIDENCE_THRESHOLD:
                        if current_time - self.last_wave_time >= STAND_DOWN_TIME:
                            self.websocket.send_safe(json.dumps({
                                "type": "gesture",
                                "name": "wave"
                            }))
                            self.last_wave_time = current_time
                            self.sample_buffer.clear()
            
            # Convert to QPixmap and display
            height, width, channel = frame_rgb.shape
            bytes_per_line = 3 * width
            q_img = QImage(frame_rgb.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img).scaled(
                self.video_label.size(), 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.FastTransformation  # Use fast transformation
            )
            self.video_label.setPixmap(pixmap)
            
        except Exception as e:
            print(f"Display update error: {e}")
            self.video_label.setText(f"Display Error:\n{str(e)}")
    
    def update_stats(self, stats_text):
        """Update statistics display"""
        self.stats_label.setText(f"Stream Stats: {stats_text}")
    
    @error_boundary
    def toggle_tracking(self):
        """Toggle tracking with thread communication"""
        self.tracking_enabled = self.tracking_button.isChecked()
        self.image_thread.set_tracking_enabled(self.tracking_enabled)
        
        if self.tracking_enabled and os.path.exists("icons/Tracking_pressed.png"):
            self.tracking_button.setIcon(QIcon("icons/Tracking_pressed.png"))
        elif os.path.exists("icons/Tracking.png"):
            self.tracking_button.setIcon(QIcon("icons/Tracking.png"))
        
        self.websocket.send_safe(json.dumps({
            "type": "tracking",
            "state": self.tracking_enabled
        }))
    
    @error_boundary
    def reconnect_stream(self):
        """Reconnect stream by restarting image thread"""
        self.image_thread.stop()
        config = config_manager.get_config("configs/steamdeck_config.json")
        camera_proxy_url = config.get("current", {}).get("camera_proxy_url", "")
        self.image_thread = ImageProcessingThread(camera_proxy_url)
        self.image_thread.frame_processed.connect(self.update_display)
        self.image_thread.stats_updated.connect(self.update_stats)
        self.image_thread.start()
        self.stats_label.setText("Stream Stats: Reconnected")
    
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
        """NEW: Reload camera proxy URL settings"""
        try:
            config_manager.clear_cache()
            config = config_manager.get_config("configs/steamdeck_config.json")
            camera_proxy_url = config.get("current", {}).get("camera_proxy_url", "")
            
            # Restart image thread with new URL
            self.image_thread.stop()
            self.image_thread = ImageProcessingThread(camera_proxy_url)
            self.image_thread.frame_processed.connect(self.update_display)
            self.image_thread.stats_updated.connect(self.update_stats)
            self.image_thread.start()
            
            self.stats_label.setText("Stream Stats: Camera settings reloaded")
            print(f"Camera settings reloaded. New proxy URL: {camera_proxy_url}")
        except Exception as e:
            print(f"Failed to reload camera settings: {e}")
    
    def closeEvent(self, event):
        """Proper cleanup on close"""
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