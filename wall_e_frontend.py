
# WALL-E Combined Frontend - HealthScreen + ServoConfigScreen with Maestro Dropdown
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
from PyQt6.QtCore import Qt, QTimer, QUrl, QRect, QSize
from PyQt6.QtWebSockets import QWebSocket
import pyqtgraph as pg
import cv2
import mediapipe as mp
from collections import deque

mp_pose = mp.solutions.pose
pose = mp_pose.Pose(
    static_image_mode=False,
    model_complexity=1,
    enable_segmentation=False,
    min_detection_confidence=0.75,  # Increase this to reduce false positives
    min_tracking_confidence=0.9    # Same here
)


try:
    with open("configs/steamdeck_config.json", "r") as f:
        config = json.load(f)
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
def load_servo_names():
    try:
        with open("configs/servo_config.json", "r") as f:
            config = json.load(f)
        return [v["name"] for v in config.values() if "name" in v and v["name"]]
    except:
        return []


def load_movement_controls():
    try:
        with open("configs/movement_controls.json", "r") as f:
            config = json.load(f)
        return config.get("steam_controls", []), config.get("nema_movements", [])
    except Exception as e:
        print(f"Failed to load movement controls: {e}")
        return [], []

STEAM_CONTROLS, NEMA_MOVEMENTS = load_movement_controls()


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

    def load_motion_config(self):
        try:
            with open("configs/motion_config.json", "r") as f:
                config = json.load(f)
            self.groups = config.get("groups", {})
            self.emotions = config.get("emotions", [])
            self.movements = config.get("movements", {})
        except:
            self.groups = {}
            self.emotions = []
            self.movements = {}

    def get_maestro_channel_by_name(self, name):
        try:
            with open("configs/servo_config.json", "r") as f:
                config = json.load(f)
            for key, value in config.items():
                if value.get("name") == name:
                    maestro = "Maestro 1" if key.startswith("m1") else "Maestro 2"
                    channel = key.split("_ch")[1]
                    return f"{maestro} / Ch {channel}"
        except:
            pass
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
        for widget in self.mapping_rows[index]:
            widget.deleteLater()
        self.mapping_rows[index] = None

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

    def load_config(self):
        try:
            with open("configs/controller_config.json", "r") as f:
                config = json.load(f)
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
        except Exception as e:
            print(f"Failed to load config: {e}")


class BackgroundWidget(QWidget):
    def __init__(self, background_path):
        super().__init__()
        self.setFixedSize(1280, 800)

        # Background image
        self.background_label = QLabel(self)
        self.background_label.setPixmap(QPixmap(background_path).scaled(self.size()))
        self.background_label.setGeometry(0, 0, 1280, 800)

        # Overlay layout
        self.overlay_layout = QVBoxLayout(self)
        self.overlay_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.overlay_layout)


class DynamicHeader(QFrame):
    def __init__(self, screen_name):
        super().__init__()

        self.setStyleSheet("background-color: #2e2e2e; color: white;")

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white;")
        

        
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.voltage_label = QLabel("  🔋 0.0V")
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

    def update_values(self):
        voltage = round(random.uniform(6.5, 15.5), 2)
        wifi = random.randint(70, 100)
        self.voltage_label.setText(f"🔋 {voltage}V")
        self.wifi_label.setText(f"📶 {wifi}%")

    def set_screen_name(self, name):
        self.screen_label.setText(name)


class HealthScreen(QWidget):
    def __init__(self, websocket):
        super().__init__()
        self.websocket = websocket
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        
        self.graph_widget = pg.PlotWidget()
        self.graph_widget.setBackground('#1e1e1e')
        self.graph_widget.showGrid(x=True, y=True)
        self.graph_widget.setTitle("Voltage & Current", color='white', size='12pt')
        self.graph_widget.setLabel('left', 'Voltage (V)', color='white')
        self.graph_widget.setLabel('bottom', 'Time (s)', color='white')
        self.graph_widget.setYRange(0, 20)
        self.graph_widget.setLimits(yMin=0, yMax=16)
        self.graph_widget.setMouseEnabled(x=False, y=False)
        self.voltage_curve = self.graph_widget.plot(pen=pg.mkPen(color='y', width=2), name="Voltage")
        self.current_curve = pg.ViewBox()
        self.graph_widget.scene().addItem(self.current_curve)
        self.graph_widget.getPlotItem().showAxis('right')
        self.graph_widget.getPlotItem().getAxis('right').setLabel('Current (A)', color='white')
        self.graph_widget.getPlotItem().getAxis('right').linkToView(self.current_curve)
        self.current_curve.setYRange(0, 150)
        self.graph_widget.getPlotItem().getViewBox().sigResized.connect(
            lambda: self.current_curve.setGeometry(self.graph_widget.getPlotItem().getViewBox().sceneBoundingRect())
        )
        self.current_plot = pg.PlotCurveItem(pen=pg.mkPen(color='c', width=2))
        self.current_curve.addItem(self.current_plot)
        self.voltage_data = []
        self.current_data = []
        self.time_data = []

        self.cpu_label = QLabel("CPU: 0%")
        

        self.mem_label = QLabel("Memory: 0%")
        self.temp_label = QLabel("Temp: 0°C")
        self.stream_label = QLabel("Stream: 0 FPS, 0x0, 0ms")
        self.dfplayer_label = QLabel("DFPlayer: Disconnected, 0 files")
        self.maestro1_label = QLabel("Maestro 1: Disconnected, 0 channels")
        self.maestro2_label = QLabel("Maestro 2: Disconnected, 0 channels")
        for label in [self.cpu_label, self.mem_label, self.temp_label, self.stream_label,
                      self.dfplayer_label, self.maestro1_label, self.maestro2_label]:
            label.setFont(QFont("Arial", 20))
            label.setStyleSheet("color: lime;")
 
        stats_layout = QGridLayout()
        stats_layout.setVerticalSpacing(2)
        stats_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        stats_layout.addWidget(self.cpu_label, 0, 0)
        stats_layout.addWidget(self.mem_label, 1, 0)
        stats_layout.addWidget(self.temp_label, 2, 0)
        stats_layout.addWidget(self.stream_label, 3, 0)
        stats_layout.addWidget(self.dfplayer_label, 0, 1)
        stats_layout.addWidget(self.maestro1_label, 1, 1)
        stats_layout.addWidget(self.maestro2_label, 2, 1)

        self.cpu_label.setFixedWidth(400)
        self.mem_label.setFixedWidth(400)
        self.temp_label.setFixedWidth(400)
        self.stream_label.setFixedWidth(400)
        self.dfplayer_label.setFixedWidth(400)
        self.maestro1_label.setFixedWidth(400)
        self.maestro2_label.setFixedWidth(400)




        self.failsafe_button = QPushButton("🔴 Failsafe")
        self.failsafe_button.setFont(QFont("Arial", 16))
        self.failsafe_button.setStyleSheet("background-color: red; color: white;")
        self.failsafe_button.clicked.connect(self.send_failsafe)

        main_layout = QVBoxLayout()

        # Wrap graph widget in a QFrame with soft border
        graph_frame = QFrame()
        graph_frame.setStyleSheet("""
            QFrame {
                border: 0px solid #444;
                border-radius: 10px;
                background-color: #1e1e1e;
            }
        """)
        graph_layout = QHBoxLayout(graph_frame)
        graph_layout.setContentsMargins(5, 0, 5, 0)
        self.graph_widget.setFixedWidth(1025)
        self.graph_widget.setFixedHeight(300)
        graph_layout.addStretch()
        graph_layout.addWidget(self.graph_widget)
        graph_layout.addStretch()

        graph_container = QWidget()
        container_layout = QHBoxLayout(graph_container)
        container_layout.addStretch()
        container_layout.addWidget(graph_frame)
        container_layout.addStretch()
        main_layout.addWidget(graph_container)

        self.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white;")
        stats_container = QWidget()
        stats_container_layout = QHBoxLayout()
        stats_container_layout.addStretch()
        stats_container_layout.addLayout(stats_layout)
        stats_container_layout.addStretch()
        stats_container.setLayout(stats_container_layout)
        main_layout.addWidget(stats_container)


        self.setLayout(main_layout)


        self.timer = QTimer()
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(5000)

    def update_stats(self):
        timestamp = time.time()
        voltage = round(random.uniform(6.5, 15.5), 2)
        current = round(random.uniform(0.5, 100.0), 2)
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        temp = round(random.uniform(40.0, 60.0), 1)
        fps = random.randint(15, 30)
        res = "640x480"
        latency = random.randint(50, 150)
        df_connected = random.choice([True, False])
        df_files = random.randint(0, 100)
        maestro1_connected = random.choice([True, False])
        maestro2_connected = random.choice([True, False])
        maestro1_channels = random.randint(0, 18)
        maestro2_channels = random.randint(0, 18)

        self.cpu_label.setText(f"CPU: {cpu}%")
        self.mem_label.setText(f"Memory: {mem}%")
        self.temp_label.setText(f"Temp: {temp}°C")
        self.stream_label.setText(f"Stream: {fps} FPS, {res}, {latency}ms")
        self.dfplayer_label.setText(f"DFPlayer: {'Connected' if df_connected else 'Disconnected'}, {df_files} files")
        self.maestro1_label.setText(f"Maestro 1: {'Connected' if maestro1_connected else 'Disconnected'}, {maestro1_channels} channels")
        self.maestro2_label.setText(f"Maestro 2: {'Connected' if maestro2_connected else 'Disconnected'}, {maestro2_channels} channels")

        if not self.time_data:
            self.start_time = timestamp
        self.time_data.append(timestamp - self.start_time)

        self.voltage_data.append(voltage)
        self.current_data.append(current)
        if len(self.time_data) > 60:
            self.time_data = self.time_data[-60:]
            self.voltage_data = self.voltage_data[-60:]
            self.current_data = self.current_data[-60:]
        self.voltage_curve.setData(self.time_data, self.voltage_data)
        self.current_plot.setData(self.time_data, self.current_data)

    def send_failsafe(self):
        self.websocket.sendTextMessage(json.dumps({"type": "failsafe"}))



class ServoConfigScreen(QWidget):
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
        self.maestro1_btn.setIcon(QIcon("icons/M1.png"))
        self.maestro2_btn.setIcon(QIcon("icons/M2.png"))
        self.maestro1_btn.setIconSize(QSize(112,118))
        self.maestro2_btn.setIconSize(QSize(112,118))


        self.maestro_group = QButtonGroup()
        self.maestro_group.setExclusive(True)
        self.maestro_group.addButton(self.maestro1_btn, 0)
        self.maestro_group.addButton(self.maestro2_btn, 1)
        self.maestro_group.idClicked.connect(self.update_grid)
        self.maestro_group.idClicked.connect(self.update_maestro_icons)  

        self.maestro1_btn.setChecked(True)  # <--- Add this line
        self.update_maestro_icons(0)        # <--- And this line

        #Add refresh button
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
        self.grid_layout.setContentsMargins(10, 10, 10, 10)  # Even left/right padding
        self.grid_widget.setLayout(self.grid_layout)
        self.grid_widget.setStyleSheet("""
            QWidget {
                border: 1px solid #555;
                border-radius: 12px;
                }
        """)
        

        # Main layout
        grid_and_selector_layout = QHBoxLayout()
        grid_and_selector_layout.addSpacing(80)

        #self.grid_widget.setFixedWidth(int(1200 * 2 / 3))
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setWidget(self.grid_widget)
        
        
        # Create a vertical layout to center the maestro selector
        selector_container = QVBoxLayout()
        selector_container.addStretch()
        selector_container.addWidget(self.maestro1_btn)
        selector_container.addWidget(self.maestro2_btn)
        selector_container.addSpacing(20)  # Add space between buttons and refresh
        selector_container.addWidget(self.refresh_btn)
        selector_container.addStretch()

        # Create a QWidget to hold the selector layout
        selector_widget = QWidget()
        selector_widget.setLayout(selector_container)
        selector_widget.setStyleSheet("background-color: rgba(0, 0, 0, 0);")  # Transparent background

        # Add selector widget to the right of the grid
        grid_and_selector_layout.addWidget(scroll_area, stretch=3)
        grid_and_selector_layout.addWidget(selector_widget)

        # Final layout
        layout = QVBoxLayout()
        layout.addLayout(grid_and_selector_layout)
        self.setLayout(layout)
        self.update_grid()

    def update_maestro_icons(self, checked_id):
        # Set pressed icon for selected, normal for unselected
        if self.maestro_group.checkedId() == 0:
            self.maestro1_btn.setIcon(QIcon("icons/M1_pressed.png"))
            self.maestro2_btn.setIcon(QIcon("icons/M2.png"))
        else:
            self.maestro1_btn.setIcon(QIcon("icons/M1.png"))
            self.maestro2_btn.setIcon(QIcon("icons/M2_pressed.png"))

    def load_config(self):
        try:
            with open("configs/servo_config.json", "r") as f:
                return json.load(f)
        except:
            return {}

    def save_config(self):
        with open("configs/servo_config.json", "w") as f:
            json.dump(self.servo_config, f, indent=2)

    def reload_servo_config(self):
        try:
            with open("configs/servo_config.json", "r") as f:
                self.servo_config = json.load(f)
            self.update_grid()
            print("Servo config reloaded successfully.")
        except Exception as e:
            print(f"Failed to reload servo config: {e}")


    def update_config(self, key, field, value):
        if key not in self.servo_config:
            self.servo_config[key] = {}
        self.servo_config[key][field] = value
        self.save_config()

    def update_grid(self):
        font = QFont("Arial", 16)

        # Clear existing widgets
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        maestro_index = self.maestro_group.checkedId()
        base_channel = maestro_index * 18

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
            speed_label = QLabel("A")
            speed_label.setFont(font)
            self.grid_layout.addWidget(speed_label, row, 9)
            self.grid_layout.addWidget(accel_spin, row, 10)


            play_btn = QPushButton("▶")
            play_btn.setFont(font)
            play_btn.setCheckable(True)
            pos_label = QLabel("V: 0")
            pos_label.setFont(font)
            self.grid_layout.addWidget(pos_label, row, 11)

            slider.valueChanged.connect(
                lambda val, k=channel_key, p=pos_label: (
                    self.websocket.sendTextMessage(json.dumps({"type": "servo", "channel": k, "pos": val})),
                    p.setText(f"V: {val}")
                )
            )

            play_btn.clicked.connect(lambda checked, k=channel_key, p=pos_label, b=play_btn, s=slider, min_spin=min_spin, max_spin=max_spin, speed_spin=speed_spin: self.toggle_sweep(k, p, b, s, min_spin.value(), max_spin.value(), speed_spin.value()))
            self.grid_layout.addWidget(play_btn, row, 12)

        # Layout adjustments
        grid_and_selector_layout = QHBoxLayout()

    
    def toggle_sweep(self, key, pos_label, button, slider, min_val, max_val, speed):

        if self.active_sweep:
            self.active_sweep.stop()
            self.active_sweep = None
            button.setText("▶")
            button.setChecked(False)
            return

        class Sweep:
            def __init__(self, label, btn, slider, minv, maxv, speedv):
                self.label = label
                self.btn = btn
                self.slider = slider
                self.minv = minv
                self.maxv = maxv
                self.speedv = speedv
                self.timer = QTimer()
                self.timer.timeout.connect(self.step)
                self.pos = minv
                self.direction = 1
                self.timer.start(max(10, 100 - speedv))

            def step(self):
                self.label.setText(f"Pos: {self.pos}")
                self.slider.setValue(self.pos)
                self.pos += self.direction * 10
                if self.pos >= self.maxv:
                    self.pos = self.maxv
                    self.direction = -1
                elif self.pos <= self.minv:
                    self.pos = self.minv
                    self.direction = 1

            def stop(self):
                self.timer.stop()
                self.label.setText("Pos: 0")
                self.btn.setText("▶")
                self.btn.setChecked(False)

        sweep = Sweep(pos_label, button, slider, min_val, max_val, speed)

        self.active_sweep = sweep
        button.setText("⏹")



class CameraFeedScreen(QWidget):
    def __init__(self, websocket):
        super().__init__()
        self.websocket = websocket
        self.sample_buffer = deque(maxlen=SAMPLE_DURATION * SAMPLE_RATE)
        self.last_wave_time = 0
        self.last_sample_time = 0
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        self.tracking_enabled = False
        
        self.cap = cv2.VideoCapture(ESP32_CAM_URL if ESP32_CAM_URL else 0)

        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)
        self.dropped_frames = 0
        self.last_frame_time = None
        self.init_ui()

    def init_ui(self):
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

        self.reconnect_button = QPushButton()
        self.reconnect_button.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white;")
        self.reconnect_button.setIcon(QIcon("icons/Reconnect.png"))
        self.reconnect_button.setIconSize(self.reconnect_button.size())
        self.reconnect_button.clicked.connect(self.reconnect_stream)
        self.reconnect_button.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white;")

        self.tracking_button = QPushButton()
        self.tracking_button.setCheckable(True)
        self.tracking_button.setIcon(QIcon("icons/Tracking.png"))
        self.tracking_button.setIconSize(self.reconnect_button.size())
        self.tracking_button.clicked.connect(self.toggle_tracking)
        self.tracking_button.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white;")

        video_layout = QVBoxLayout()
        video_layout.addWidget(self.video_label)
        video_layout.addWidget(self.stats_label)

        button_layout = QVBoxLayout()
        button_layout.setSpacing(0)  # Remove vertical space
        button_layout.addWidget(self.reconnect_button)
        button_layout.addWidget(self.tracking_button)
        button_layout.addSpacing(200)  # Push buttons to the top
        

        main_layout = QHBoxLayout()
        main_layout.addSpacing(81)
        main_layout.addLayout(video_layout, 2)
        main_layout.addLayout(button_layout, 1)

        self.setLayout(main_layout)

    def reconnect_stream(self):
        self.cap.release()
        self.cap = cv2.VideoCapture(ESP32_CAM_URL if ESP32_CAM_URL else 0)
        self.stats_label.setText("Stream Stats: Reconnected")

    def toggle_tracking(self):
        self.tracking_enabled = self.tracking_button.isChecked()
        icon_path = "icons/Tracking_pressed.png" if self.tracking_enabled else "icons/Tracking.png"
        self.tracking_button.setIcon(QIcon(icon_path))
        self.websocket.sendTextMessage(json.dumps({
            "type": "tracking",
            "state": self.tracking_enabled
        }))


    def update_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            self.dropped_frames += 1
            self.stats_label.setText("Stream Stats: Failed to read frame")
            return

        current_time = time.time()
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(frame_rgb)

        wave_detected = False
        if results.pose_landmarks:
            lm = results.pose_landmarks.landmark
            rw = lm[mp_pose.PoseLandmark.RIGHT_WRIST]
            rs = lm[mp_pose.PoseLandmark.RIGHT_SHOULDER]
            if rw.y < rs.y:
                wave_detected = True

        # Sampling logic
        if self.tracking_enabled:
            if current_time - self.last_sample_time >= 1.0 / SAMPLE_RATE:
                self.sample_buffer.append(wave_detected)
                self.last_sample_time = current_time

            if len(self.sample_buffer) == self.sample_buffer.maxlen:
                confidence = sum(self.sample_buffer) / len(self.sample_buffer)
                if confidence >= CONFIDENCE_THRESHOLD:
                    if current_time - self.last_wave_time >= STAND_DOWN_TIME:
                        self.websocket.sendTextMessage(json.dumps({
                            "type": "gesture",
                            "name": "wave"
                        }))
                        self.last_wave_time = current_time
                        self.sample_buffer.clear()

        if self.tracking_enabled:
            boxes, weights = self.hog.detectMultiScale(frame_rgb, winStride=(8, 8))
            for (x, y, w, h) in boxes:
                cv2.rectangle(frame_rgb, (x, y), (x + w, y + h), (255, 0, 0), 2)

        if wave_detected:
            cv2.putText(frame_rgb, 'Wave Detected', (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)

        height, width = frame.shape[:2]
        bytes_per_line = 3 * width
        q_img = QImage(frame_rgb.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img).scaled(
            self.video_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.video_label.setPixmap(pixmap)

        fps = int(1000 / self.timer.interval())
        latency = 0
        self.stats_label.setText(
            f"Stream Stats: {fps} FPS, {width}x{height}, {latency}ms latency, {self.dropped_frames} dropped frames"
        )

    def closeEvent(self, event):
        self.cap.release()
        event.accept()

    def reload_wave_settings(self):
        try:
            with open("configs/steamdeck_config.json", "r") as f:
                config = json.load(f)
            wave_config = config.get("current", {})
            wave_settings = wave_config.get("wave_detection", {})
            self.esp32_cam_url = wave_config.get("esp32_cam_url", "")
            self.sample_duration = wave_settings.get("sample_duration", 3)
            self.sample_rate = wave_settings.get("sample_rate", 5)
            self.confidence_threshold = wave_settings.get("confidence_threshold", 0.7)
            self.stand_down_time = wave_settings.get("stand_down_time", 30)
            self.sample_buffer = deque(maxlen=self.sample_duration * self.sample_rate)
            self.last_sample_time = 0
            print("Wave detection settings reloaded.")
        except Exception as e:
            print(f"Failed to reload wave detection settings: {e}")


      

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
        image_container.addStretch()  # Push image to bottom
        self.image_label = QLabel()
        self.image_label.setPixmap(QPixmap("walle.png").scaled(400, 400, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignBottom)
        image_container.addWidget(self.image_label)

        image_widget = QWidget()
        image_widget.setLayout(image_container)
        image_widget.setStyleSheet("background-color: rgba(0, 0, 0, 0);")  # Transparent background
        layout.addWidget(image_widget)

        # Scrollable area for emotion buttons
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none; padding: 10px; background: transparent;")

        button_container = QWidget()
        button_container.setStyleSheet("""
        background-color: #222;
        border-radius: 30px;
        """)
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(15)
        button_container.setLayout(self.grid_layout)

        # Wrap emotion buttons in a frame
        button_frame = QFrame()
        button_frame.setStyleSheet("""
        QFrame {
            border: 1px solid #555;
            border-radius: 12px;
            background-color: #1e1e1e;
        }
        """)
        frame_layout = QVBoxLayout(button_frame)
        frame_layout.setContentsMargins(10, 10, 10, 10)
        frame_layout.addWidget(button_container)
        scroll_area.setWidget(button_frame)

        # Create Idle and Demo Mode buttons
        mode_frame = QFrame()
        mode_frame.setStyleSheet("""
        QFrame {
            border: 0px solid #555;
            border-radius: 12px;
            background-color: #1e1e1e;
        }
        """)
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
        mode_container_layout.addSpacing(20)  # Add spacing to the left
        mode_container_layout.addWidget(mode_frame)
        mode_container_layout.addSpacing(20)  # Add spacing to the right
        mode_container.setLayout(mode_container_layout)
        mode_container.setStyleSheet("background-color: rgba(0, 0, 0, 0);")  # Transparent background

        right_layout.addWidget(mode_container)


        layout.addLayout(right_layout)
        self.setLayout(layout)
        self.load_emotion_buttons()

    def load_emotion_buttons(self):
        try:
            with open("configs/emotion_buttons.json", "r") as f:
                emotions = json.load(f)
        except Exception as e:
            emotions = []

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

    def send_emotion(self, name):
        self.websocket.sendTextMessage(json.dumps({"type": "scene", "emotion": name}))

    def send_mode_state(self, mode, state):
        self.websocket.sendTextMessage(json.dumps({
            "type": "mode",
            "name": mode,
            "state": state
        }))



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

        self.url_label = QLabel("ESP32 Cam Stream URL:")
        self.url_label.setFont(font)
        self.url_input = QLineEdit()
        self.url_input.setFont(font)
        self.url_input.setPlaceholderText("http://10.1.1.10/stream")

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

        self.grid.addWidget(self.url_label, 0, 0)
        self.grid.addWidget(self.url_input, 0, 1)
        self.grid.addWidget(self.sample_duration_label, 1, 0)
        self.grid.addWidget(self.sample_duration_spin, 1, 1)
        self.grid.addWidget(self.sample_rate_label, 2, 0)
        self.grid.addWidget(self.sample_rate_spin, 2, 1)
        self.grid.addWidget(self.confidence_label, 3, 0)
        self.grid.addWidget(self.confidence_slider, 3, 1)
        self.grid.addWidget(self.confidence_value, 3, 2)
        self.grid.addWidget(self.stand_down_label, 4, 0)
        self.grid.addWidget(self.stand_down_spin, 4, 1)
        self.ws_label = QLabel("WebSocket IP:Port:")
        self.ws_label.setFont(font)
        self.ws_input = QLineEdit()
        self.ws_input.setFont(font)
        self.ws_input.setPlaceholderText("localhost:8765")
        self.grid.addWidget(self.ws_label, 5, 0)
        self.grid.addWidget(self.ws_input, 5, 1)

        self.layout.addLayout(self.grid)

        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("💾 Update")
        self.save_btn.setFont(font)
        self.save_btn.clicked.connect(self.save_config)
        self.reset_btn = QPushButton("🔄 Reset")
        self.reset_btn.setFont(font)
        self.reset_btn.clicked.connect(self.reset_to_defaults)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.reset_btn)
        self.layout.addLayout(btn_layout)

        self.setLayout(self.layout)

    def load_config(self):
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
            current = config.get("current", {})
            wave = current.get("wave_detection", {})
            self.url_input.setText(current.get("esp32_cam_url", ""))
            self.ws_input.setText(current.get("websocket_url", "localhost:8765"))
            self.sample_duration_spin.setValue(wave.get("sample_duration", 3))
            self.sample_rate_spin.setValue(wave.get("sample_rate", 5))
            self.confidence_slider.setValue(int(wave.get("confidence_threshold", 0.7) * 100))
            self.stand_down_spin.setValue(wave.get("stand_down_time", 30))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load config: {e}")

    def save_config(self):
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
        except:
            config = {}

        config["current"] = {
        "websocket_url": self.ws_input.text(),
            "esp32_cam_url": self.url_input.text(),
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
            QMessageBox.information(self, "Update", "Wave detection configuration updated successfully.")
            app = QApplication.instance()
            if app:
                for widget in app.allWidgets():
                    if hasattr(widget, "reload_wave_settings"):
                        widget.reload_wave_settings()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save config: {e}")

    def reset_to_defaults(self):
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
            defaults = config.get("defaults", {})
            config["current"] = defaults
            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=2)
            self.load_config()
            QMessageBox.information(self, "Reset", "Configuration reset to defaults.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to reset config: {e}")



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

    def request_scenes(self):
        self.websocket.sendTextMessage(json.dumps({ "type": "get_scenes" }))

    def handle_message(self, message):
        try:
            msg = json.loads(message)
            if msg.get("type") == "scene_list":
                self.update_grid(msg.get("scenes", []))
        except Exception as e:
            print(f"Failed to handle message: {e}")

    def update_grid(self, scenes):
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

    def test_scene(self, name):
        self.websocket.sendTextMessage(json.dumps({ "type": "play_scene", "scene": name }))

    def save_config(self):
        selected = [
            { "label": label, "emoji": emoji, "category": cb.currentText() }
            for label, (cbx, emoji, cb) in self.scene_widgets.items()
            if cbx.isChecked()
        ]
        try:
            with open("configs/emotion_buttons.json", "w") as f:
                json.dump(selected, f, indent=2)
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


    def load_config(self):
        try:
            with open("configs/emotion_buttons.json", "r") as f:
                emotions = json.load(f)
            self.selected_labels = [item.get("label", "") for item in emotions]
        except:
            self.selected_labels = []


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WALL-E Control System")
        self.setFixedSize(1280, 800)
        background = QPixmap("background.png")
        palette = QPalette()
        palette.setBrush(QPalette.ColorRole.Window, QBrush(background))
        self.setPalette(palette)

        self.websocket = QWebSocket()
        try:
            with open("configs/steamdeck_config.json", "r") as f:
                config = json.load(f)
            ws_url = config.get("current", {}).get("websocket_url", "localhost:8765")
        except:
            ws_url = "localhost:8765"
        self.websocket.open(QUrl(f"ws://{ws_url}"))
        
        self.header = DynamicHeader("Home")
        self.header.setMaximumWidth(1000)

        self.stack = QStackedWidget()
        self.nav_buttons = {}

        self.health_screen = HealthScreen(self.websocket)
        self.servo_screen = ServoConfigScreen(self.websocket)
        self.camera_screen = CameraFeedScreen(self.websocket)
        self.controller_screen = ControllerConfigScreen(self.websocket)
        self.settings_screen = SettingsScreen()
        self.scene_editor_screen = SceneScreen(self.websocket)
        self.scene_dashboard_screen = HomeScreen(self.websocket)

        self.stack.addWidget(self.health_screen)
        self.stack.addWidget(self.servo_screen)
        self.stack.addWidget(self.camera_screen)
        self.stack.addWidget(self.controller_screen)
        self.stack.addWidget(self.settings_screen)
        self.stack.addWidget(self.scene_editor_screen)
        self.stack.addWidget(self.scene_dashboard_screen)

        nav_bar = QHBoxLayout()
        nav_bar.addSpacing(100)
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
            btn.setIcon(QIcon(f"icons/{name}.png"))
            btn.setIconSize(QSize(64, 64))
            btn.clicked.connect(lambda _, s=screen, n=name: self.switch_screen(s,n))
            nav_bar.addWidget(btn)
            self.nav_buttons[name] = btn

        nav_frame = QFrame()

        nav_frame.setLayout(nav_bar)
        nav_frame.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white;")

        

        # Create image button
        image_button = QPushButton()
        image_button.setCheckable(True)
        image_button.setIcon(QIcon("icons/failsafe.png"))
        image_button.setIconSize(QSize(300, 70))
        image_button.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white;")
        image_button.clicked.connect(self.toggle_failsafe_icon)

        # Add stretch and image button to the right of nav_bar
        nav_bar.addSpacing(20)
        nav_bar.addWidget(image_button)
        nav_bar.addSpacing(100)

        layout = QVBoxLayout()
        layout.setSpacing(0) 

        # Add spacing to push header down
        layout.addSpacing(60)

        # Create and configure header
        header = DynamicHeader(name)
        header.setMaximumWidth(1000)  # Limit horizontal space

        # Wrap header in a container to centre it
        header_container = QWidget()
        header_layout = QHBoxLayout()
        header_layout.addWidget(self.header)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_container.setLayout(header_layout)

        # Add header container to layout
        layout.addWidget(header_container)

        # Continue with rest of layout
        layout.addSpacing(2)
        layout.addWidget(self.stack)
        layout.addWidget(nav_frame)
        layout.addSpacing(35)

        self.switch_screen(self.scene_dashboard_screen, "Home")

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def switch_screen(self, screen, name):
        self.stack.setCurrentWidget(screen)
        self.header.set_screen_name(name)
        for btn_name, btn in self.nav_buttons.items():
            icon_file = f"icons/{btn_name}_pressed.png" if btn_name == name else f"icons/{btn_name}.png"
            btn.setIcon(QIcon(icon_file))


    def toggle_failsafe_icon(self):
        sender = self.sender()
        if sender.isChecked():
            sender.setIcon(QIcon("icons/failsafe_pressed.png"))
            state = True
        else:
            sender.setIcon(QIcon("icons/failsafe.png"))
            state = False

        # Send state to backend
        self.websocket.sendTextMessage(json.dumps({
           "type": "failsafe",
            "state": state
        }))




if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
