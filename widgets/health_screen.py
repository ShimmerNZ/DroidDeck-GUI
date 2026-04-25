#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - Health Monitoring Screen (Themed)
Displays system telemetry, battery status, network quality, and performance graphs
"""

import json
import time
import requests
from collections import deque
from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QFrame, QWidget, 
                            QGridLayout, QMessageBox, QPushButton, QGroupBox)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal
import pyqtgraph as pg

from widgets.base_screen import BaseScreen
from core.theme_manager import theme_manager
from core.config_manager import config_manager
from core.utils import error_boundary
from widgets.voltage_alert_splash import VoltageAlertSplash
from widgets.bandwidth_test_splash import show_bandwidth_test_splash


class HealthScreen(BaseScreen):
    """System health monitoring with telemetry graphs and status displays"""
    
    # Qt signals for thread-safe updates
    voltage_update_signal = pyqtSignal(float)
    status_update_signal = pyqtSignal(dict)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Register for theme change notifications
        theme_manager.register_callback(self._on_theme_changed)

    def __del__(self):
        """Clean up theme manager callback on destruction"""
        try:
            theme_manager.unregister_callback(self._on_theme_changed)
        except Exception:
            pass
    
    def _setup_screen(self):
        """Initialize health monitoring interface"""
        self.setFixedWidth(1180)
        self.startup_complete = False
        
        # Voltage alarm state tracking
        self.last_voltage_alarm = None
        
        # Track start time for relative time calculation
        self.start_time = time.time()
        
        # Connect WebSocket for telemetry updates
        if self.websocket:
            self.websocket.textMessageReceived.connect(self.handle_telemetry)
        
        # Connect signals for thread-safe updates
        self.voltage_update_signal.connect(self._update_voltage_display)
        self.status_update_signal.connect(self._update_status_displays)
        
        self.init_ui()

        from PyQt6.QtCore import QTimer
        self.startup_timer = QTimer()
        self.startup_timer.timeout.connect(self._check_and_enable_alerts)
        self.startup_timer.start(500)  # Check every 500ms

        # Periodic timer to poll system_status (for serial FPS stats)
        self.status_poll_timer = QTimer()
        self.status_poll_timer.timeout.connect(self._request_system_status)
        self.status_poll_timer.start(2000)  # Poll every 2 seconds

        # Camera proxy URL for RSSI polling
        wave_config = config_manager.get_wave_config()
        raw_url = wave_config.get("camera_proxy_url", "http://10.1.1.230:8081")
        self._camera_proxy_base = raw_url.replace("/stream", "")

        # Poll ESP32 RSSI every 10 seconds
        self.rssi_poll_timer = QTimer()
        self.rssi_poll_timer.timeout.connect(self._poll_camera_rssi)
        self.rssi_poll_timer.start(10000)

    def _check_and_enable_alerts(self):
        """Check if application is ready and enable voltage alerts"""
        try:
            app_ready = False
            
            if (hasattr(self, 'parent') and self.parent() and 
                hasattr(self.parent(), 'isVisible') and 
                self.parent().isVisible()):
                app_ready = True
            
            if app_ready:
                self.voltage_alerts_enabled = True
                self.startup_complete = True
                self.startup_timer.stop()
                self.logger.info("Voltage alerts enabled - application fully loaded")
            else:
                if not hasattr(self, '_startup_check_count'):
                    self._startup_check_count = 0
                
                self._startup_check_count += 1
                if self._startup_check_count > 20:  # 10 seconds maximum wait
                    self.voltage_alerts_enabled = True
                    self.startup_complete = True
                    self.startup_timer.stop()
                    self.logger.info("Voltage alerts enabled - timeout reached")
                    
        except Exception as e:
            self.logger.warning(f"Error checking application state: {e}")

    def _enable_voltage_alerts(self):
        """Enable voltage alerts after startup is complete"""
        self.startup_complete = True
        self.logger.info("Voltage alerts enabled after startup delay")

    def check_voltage_alarms(self, voltage: float):
        """Check and display voltage alarms when thresholds are crossed"""
        if not getattr(self, 'voltage_alerts_enabled', False):
            return
        
    def init_ui(self):
        """Initialize health monitoring UI with graphs and status displays"""
        self.setup_telemetry_graph()
        self.setup_status_displays()
        self.setup_layout()
    
    def setup_telemetry_graph(self):
        """Setup battery voltage and current monitoring graph"""
        self.graph_widget = pg.PlotWidget()
        self._update_graph_theme()
        self.graph_widget.showGrid(x=True, y=True, alpha=0.3)
        self.graph_widget.setTitle("Battery Voltage & Current Draw", color='white', size='14pt')
        self.graph_widget.setLabel('left', 'Battery Voltage (V)', color='white')
        self.graph_widget.setLabel('bottom', 'Time (s)', color='white')
        
        # Set voltage range for 4S LiPo batteries
        self.graph_widget.setYRange(0, 20)
        self.graph_widget.setLimits(yMin=0, yMax=20)
        self.graph_widget.setMouseEnabled(x=False, y=False)
        
        self.graph_widget.addLegend(offset=(10, 20))
        self.graph_widget.getPlotItem().setContentsMargins(15, 15, 15, 15)
        
        # Data storage with performance limits
        self.max_data_points = 100
        self.battery_voltage_data = deque(maxlen=self.max_data_points)
        self.current_a0_data = deque(maxlen=self.max_data_points)
        self.current_a1_data = deque(maxlen=self.max_data_points)
        self.current_a2_data = deque(maxlen=self.max_data_points)
        self.time_data = deque(maxlen=self.max_data_points)
        
        green = theme_manager.get("green")
        self.voltage_curve = self.graph_widget.plot(
            pen=pg.mkPen(color=green, width=4),
            name="Battery Voltage",
            antialias=True
        )
        
        # Current curves (secondary Y-axis)
        self.current_view = pg.ViewBox()
        self.graph_widget.scene().addItem(self.current_view)
        self.graph_widget.getPlotItem().showAxis('right')
        self.graph_widget.getPlotItem().getAxis('right').setLabel('Current (A)', color='white')
        self.graph_widget.getPlotItem().getAxis('right').linkToView(self.current_view)

        self.current_view.setYRange(0, 70)  
        self.current_view.setLimits(yMin=-5, yMax=100)
        
        self.graph_widget.getPlotItem().getViewBox().sigResized.connect(self.update_views)
        
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        
        self.current_a0_plot = pg.PlotCurveItem(
            pen=pg.mkPen(color=primary, width=3), 
            name="Left Track Current",
            antialias=True
        )
        self.current_view.addItem(self.current_a0_plot)
        
        self.current_a1_plot = pg.PlotCurveItem(
            pen=pg.mkPen(color=primary_light, width=3), 
            name="Right Track Current",
            antialias=True
        )
        self.current_view.addItem(self.current_a1_plot)

        orange = "#FF8C00"
        self.current_a2_plot = pg.PlotCurveItem(
            pen=pg.mkPen(color=orange, width=3), 
            name="Electronics Current",
            antialias=True
        )
        self.current_view.addItem(self.current_a2_plot)
        
        legend = self.graph_widget.addLegend(offset=(30, 30))
        legend.addItem(self.current_a0_plot, "Left Track (A0)")
        legend.addItem(self.current_a1_plot, "Right Track (A1)")
        legend.addItem(self.current_a2_plot, "Electronics (A2)")

    def _update_graph_theme(self):
        """Update graph background and styling with theme colors"""
        panel_bg = theme_manager.get("panel_bg")
        self.graph_widget.setBackground(panel_bg)

    def setup_status_displays(self):
        """Setup system status display labels"""
        self.status_labels = {}

    def _create_control_panel(self):
        """Create the themed health monitoring control panel"""
        control_panel = QWidget()
        control_panel.setFixedWidth(340)
        self._update_control_panel_style(control_panel)
        
        panel_layout = QVBoxLayout()
        panel_layout.setContentsMargins(15, 5, 15, 15)
        panel_layout.setSpacing(15)
        
        self.header = QLabel("SYSTEM HEALTH")
        self.header.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_header_style()
        panel_layout.addWidget(self.header)
        
        status_section = self._create_status_display_section()
        panel_layout.addWidget(status_section)
        
        panel_layout.addSpacing(10)
        
        system_section = self._create_system_controls_section()
        panel_layout.addWidget(system_section)
        
        panel_layout.addStretch()
        control_panel.setLayout(panel_layout)
        self.control_panel = control_panel
        return control_panel

    def _update_control_panel_style(self, panel):
        """Apply themed styling to control panel"""
        primary = theme_manager.get("primary_color")
        panel_bg = theme_manager.get("panel_bg")
        panel.setStyleSheet(f"""
            QWidget {{
                background-color: {panel_bg};
                border: 2px solid {primary};
                border-radius: 12px;
                color: white;
            }}
        """)

    def _update_header_style(self):
        """Apply themed styling to header"""
        primary = theme_manager.get("primary_color")
        self.header.setStyleSheet(f"""
            QLabel {{
                border: none;
                background-color: rgba(0, 0, 0, 0.9);
                color: {primary};
                padding: 8px;
                border-radius: 6px;
                margin-bottom: 5px;
            }}
        """)

    def _create_status_display_section(self):
        """Create themed status display section within the control panel"""
        self.status_frame = QWidget()
        self._update_status_frame_style()
        
        status_layout = QVBoxLayout()
        status_layout.setContentsMargins(12, 8, 12, 18)
        status_layout.setSpacing(4)
        
        self.status_header = QLabel("STATUS")
        self.status_header.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self.status_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_section_header_style(self.status_header)
        status_layout.addWidget(self.status_header)
        
        label_configs = [
            ("cpu",          "CPU: 0%"),
            ("mem",          "Memory: 0%"),
            ("temp",         "Temp: 0°C"),
            ("battery",      "Battery: 0.0V"),
            ("runtime",      "Runtime: --m remaining"),
            ("current_total","Total Current: 0.0A"),
            ("adc_info",     "ADC: 4-Channel Mode"),
            ("dfplayer",     "Audio: Disconnected"),
            ("camera_rssi",  "Camera WiFi: --"),
            ("maestro1",     "M1: Disconnected"),
            ("maestro2",     "M2: Disconnected"),
        ]
        
        for key, text in label_configs:
            label = QLabel(text)
            label.setFont(QFont("Arial", 18))
            self._update_status_label_style(label)
            label.setWordWrap(True)
            self.status_labels[key] = label
            status_layout.addWidget(label)
        
        self.status_frame.setLayout(status_layout)
        return self.status_frame

    def _update_status_frame_style(self):
        """Apply themed styling to status frame"""
        primary = theme_manager.get("primary_color")
        self.status_frame.setStyleSheet(f"""
            QWidget {{
                border: 1px solid {primary};
                border-radius: 8px;
                background-color: rgba(0, 0, 0, 0.3);
            }}
        """)

    def _update_section_header_style(self, header):
        """Apply themed styling to section header"""
        primary = theme_manager.get("primary_color")
        header.setStyleSheet(f"color: {primary}; border: none; margin-bottom: 3px; background: transparent;")

    def _update_status_label_style(self, label):
        """Apply themed styling to status label"""
        green = theme_manager.get("green")
        label.setStyleSheet(f"color: {green}; padding: 1px; background: transparent;")

    def _create_system_controls_section(self):
        """Create themed system control operations section"""
        self.system_frame = QWidget()
        self._update_system_frame_style()
        
        system_layout = QVBoxLayout()
        system_layout.setContentsMargins(12, 8, 12, 12)
        system_layout.setSpacing(6)
        
        self.system_header = QLabel("NETWORK")
        self.system_header.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self.system_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_section_header_style(self.system_header)
        system_layout.addWidget(self.system_header)
        
        self.bandwidth_btn = QPushButton("🌐 BANDWIDTH TEST")
        self.bandwidth_btn.setFont(QFont("Arial", 14))
        self.bandwidth_btn.clicked.connect(self.start_bandwidth_test)
        self._update_bandwidth_button_style()
        system_layout.addWidget(self.bandwidth_btn)
        
        self.system_frame.setLayout(system_layout)
        return self.system_frame

    def _update_system_frame_style(self):
        """Apply themed styling to system frame"""
        primary = theme_manager.get("primary_color")
        self.system_frame.setStyleSheet(f"""
            QWidget {{
                border: 1px solid {primary};
                border-radius: 8px;
                background-color: rgba(0, 0, 0, 0.3);
            }}
        """)

    def _update_bandwidth_button_style(self):
        """Apply themed styling to bandwidth button"""
        primary = theme_manager.get("primary_color")
        self.bandwidth_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4a4a4a, stop:1 #2a2a2a);
                color: white;
                border: 1px solid #666;
                border-radius: 6px;
                padding: 6px;
                text-align: center;
                font-weight: bold;
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
        """)

    def _on_theme_changed(self):
        """Handle theme change by updating all styled components"""
        try:
            if hasattr(self, 'control_panel'):
                self._update_control_panel_style(self.control_panel)
            if hasattr(self, 'header'):
                self._update_header_style()
            
            self._update_graph_theme()
            
            if hasattr(self, 'voltage_curve'):
                green = theme_manager.get("green")
                self.voltage_curve.setPen(pg.mkPen(color=green, width=4))
            
            if hasattr(self, 'current_a0_plot') and hasattr(self, 'current_a1_plot'):
                primary = theme_manager.get("primary_color")
                primary_light = theme_manager.get("primary_light")
                orange = "#FF8C00"
                self.current_a0_plot.setPen(pg.mkPen(color=primary, width=3))
                self.current_a1_plot.setPen(pg.mkPen(color=primary_light, width=3))
                if hasattr(self, 'current_a2_plot'):
                    self.current_a2_plot.setPen(pg.mkPen(color=orange, width=3))

            if hasattr(self, 'status_frame'):
                self._update_status_frame_style()
            if hasattr(self, 'status_header'):
                self._update_section_header_style(self.status_header)
            
            if hasattr(self, 'system_frame'):
                self._update_system_frame_style()
            if hasattr(self, 'system_header'):
                self._update_section_header_style(self.system_header)
            if hasattr(self, 'bandwidth_btn'):
                self._update_bandwidth_button_style()
            
            for label in self.status_labels.values():
                self._update_status_label_style(label)
            
            if hasattr(self, 'graph_frame'):
                panel_bg = theme_manager.get("panel_bg")
                self.graph_frame.setStyleSheet(f"border: 2px solid #444; border-radius: 10px; background-color: {panel_bg};")

            self.logger.info(f"Health screen updated for theme: {theme_manager.get_theme_name()}")
        except Exception as e:
            self.logger.warning(f"Failed to apply theme changes: {e}")

    def setup_layout(self):
        """Setup main layout with full-height graph and wider control panel"""
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(98, 19, 15, 6)
        
        self.graph_frame = QFrame()
        panel_bg = theme_manager.get("panel_bg")
        self.graph_frame.setStyleSheet(f"border: 2px solid #444; border-radius: 10px; background-color: {panel_bg};")
        graph_layout = QVBoxLayout(self.graph_frame)
        graph_layout.setContentsMargins(10, 10, 10, 10)
        
        self.graph_widget.setFixedWidth(690)
        self.graph_widget.setFixedHeight(455)
        
        graph_layout.addWidget(self.graph_widget)
        
        control_panel = self._create_control_panel()
        
        main_layout.addWidget(self.graph_frame)
        main_layout.addWidget(control_panel)
        
        self.setLayout(main_layout)
    
    def update_views(self):
        """Update the current view geometry to match the main plot"""
        self.current_view.setGeometry(
            self.graph_widget.getPlotItem().getViewBox().sceneBoundingRect()
        )

    @error_boundary
    def start_bandwidth_test(self, checked=False):
        """Start bandwidth test with progress splash screen"""
        self.bandwidth_btn.setEnabled(False)
        self.bandwidth_btn.setText("TESTING...")
        
        camera_proxy_url = "http://10.1.1.230:8081"
        results = show_bandwidth_test_splash(self, camera_proxy_url)
        
        self.bandwidth_btn.setEnabled(True)
        self.bandwidth_btn.setText("🌐 BANDWIDTH TEST")

    def get_voltage_status_text(self, voltage: float) -> tuple:
        """Get voltage status with theme color coding"""
        red = theme_manager.get("red")
        primary = theme_manager.get("primary_color")
        green = theme_manager.get("green")
        
        if voltage < 13.2:
            return f"Battery: {voltage:.2f}V CRITICAL", f"color: {red}; font-weight: bold; background: transparent;"
        elif voltage < 14.0:
            return f"Battery: {voltage:.2f}V LOW", f"color: {primary}; font-weight: bold; background: transparent;"
        elif voltage > 14.0:
            return f"Battery: {voltage:.2f}V GOOD", f"color: {green}; background: transparent;"
        else:
            return f"Battery: {voltage:.2f}V OK", f"color: {green}; background: transparent;"

    def get_maestro_status_text(self, maestro_data: dict, maestro_name: str) -> tuple:
        """Format detailed Maestro status information with theme colors"""
        red = theme_manager.get("red")
        primary = theme_manager.get("primary_color")
        green = theme_manager.get("green")
        
        if not maestro_data or not maestro_data.get('connected', False):
            return f"{maestro_name}: Disconnected", f"color: {red}; background: transparent;"
        
        channels = maestro_data.get('channel_count', 0)
        error_flags = maestro_data.get('error_flags', {})
        script_status = maestro_data.get('script_status', {}).get('status', 'unknown')
        moving = maestro_data.get('moving', False)
        
        has_errors = error_flags.get('has_errors', False)
        if has_errors:
            error_details = error_flags.get('details', {})
            error_list = [k.replace('_error', '') for k, v in error_details.items() if v]
            error_text = ', '.join(error_list[:2])
            status = f"{maestro_name}: {channels}ch, Errors: {error_text}"
            color = f"color: {primary}; font-weight: bold; background: transparent;"
        else:
            move_text = "Moving" if moving else "Idle"
            status = f"{maestro_name}: {channels}ch, {script_status.title()}, {move_text}"
            color = f"color: {green}; background: transparent;"
        
        return status, color

    @error_boundary
    def _request_system_status(self):
        """Poll backend for system_status to update serial FPS stats"""
        try:
            self.send_websocket_message("system_status")
        except Exception:
            pass

    def handle_telemetry(self, message: str):
        """Process incoming telemetry data and update displays"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "system_status":
                # Extract only mixer performance stats from system_status polls.
                # Do not touch graph data or connection labels — system_status does
                # not carry ADC/voltage/maestro state, so merging it would flash
                # stale "Disconnected/Simulated" values between real telemetry packets.
                hw = data.get("hardware", {})
                mixer_data = {
                    "maestro1":      hw.get("maestro1", getattr(self, "_last_m1", {})),
                    "maestro2":      hw.get("maestro2", getattr(self, "_last_m2", {})),
                    "adc_available": getattr(self, "_last_adc_available", False),
                    "audio_system":  getattr(self, "_last_audio_system", {}),
                    "cpu":           data.get("cpu", "--"),
                    "memory":        data.get("memory", "--"),
                    "temperature":   data.get("temperature", "--"),
                    "current_total": data.get("current_total", 0.0),
                }
                self.status_update_signal.emit(mixer_data)
                return

            if msg_type != "telemetry":
                return

            # Cache connection/ADC state so system_status polls can carry it forward
            self._last_m1 = data.get("maestro1", {})
            self._last_m2 = data.get("maestro2", {})
            self._last_adc_available = data.get("adc_available", False)
            self._last_audio_system = data.get("audio_system", {})

            battery_voltage = data.get("battery_voltage") or data.get("voltage") or data.get("battery") or 12.6

            if battery_voltage > 0:
                self.voltage_update_signal.emit(battery_voltage)

            self.status_update_signal.emit(data)

            current_time = time.time()
            relative_time = current_time - self.start_time
            self.battery_voltage_data.append(float(battery_voltage))
            self.current_a0_data.append(float(data.get("current_left_track", 0.0)))
            self.current_a1_data.append(float(data.get("current_right_track", 0.0)))
            self.current_a2_data.append(float(data.get("current_total", 0.0)))
            self.time_data.append(relative_time)

            self._update_graphs()

        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode failed: {e}")
        except Exception as e:
            self.logger.error(f"Telemetry processing failed: {e}")

    def _update_voltage_display(self, voltage: float):
        """Thread-safe voltage display update"""
        battery_text, battery_style = self.get_voltage_status_text(voltage)
        self.status_labels["battery"].setText(battery_text)
        self.status_labels["battery"].setStyleSheet(battery_style)
        
        if (getattr(self, 'voltage_alerts_enabled', False) and 
            getattr(self, 'startup_complete', False)):
            self.check_voltage_alarms(voltage)
        else:
            alerts_enabled = getattr(self, 'voltage_alerts_enabled', False)
            startup_complete = getattr(self, 'startup_complete', False)
            self.logger.debug(f"Skipping voltage alert - alerts_enabled: {alerts_enabled}, startup_complete: {startup_complete}")

    def _update_status_displays(self, data: dict):
        """Thread-safe status display updates with theme colors"""
        green = theme_manager.get("green")
        red = theme_manager.get("red")
        
        updates = {}
        
        # Basic system stats - skip update if value is missing to avoid flickering
        cpu = data.get("cpu")
        mem = data.get("memory")
        temp = data.get("temperature")

        if cpu is not None and cpu != "--":
            updates["cpu"] = f"CPU: {cpu}%"
        if mem is not None and mem != "--":
            updates["mem"] = f"Memory: {mem}%"
        if temp is not None and temp != "--":
            updates["temp"] = f"Temp: {temp}°C"
        
        # Total current from A2 sensor
        current_total = data.get("current_total", 0.0)
        updates["current_total"] = f"Total Current: {current_total:.1f}A"
        
        # Audio system
        audio = data.get("audio_system", {})
        updates["dfplayer"] = f"Audio: {'Connected' if audio.get('connected') else 'Disconnected'}"
                
        # ADC info with 4-channel status
        adc_available = data.get("adc_available", False)
        updates["adc_info"] = "ADC: 4-Ch Active" if adc_available else "ADC: Simulated"

        # Battery run-time estimate
        estimate = data.get("battery_estimate")
        if estimate and "runtime" in self.status_labels:
            mins = estimate.get("estimated_minutes_remaining", 0.0)
            soc = estimate.get("soc_percent", 0.0)
            confidence = estimate.get("confidence", "")
            if confidence == "warming_up":
                runtime_text = "Runtime: estimating..."
                runtime_style = "color: gray; padding: 1px; background: transparent;"
            elif mins <= 0:
                runtime_text = f"Runtime: -- ({soc:.0f}%)"
                runtime_style = f"color: {red}; padding: 1px; background: transparent;"
            elif mins <= 10:
                runtime_text = f"Runtime: {mins:.0f}m left ({soc:.0f}%)"
                runtime_style = f"color: {red}; font-weight: bold; padding: 1px; background: transparent;"
            elif mins <= 30:
                runtime_text = f"Runtime: {mins:.0f}m left ({soc:.0f}%)"
                runtime_style = "color: orange; padding: 1px; background: transparent;"
            else:
                runtime_text = f"Runtime: {mins:.0f}m left ({soc:.0f}%)"
                runtime_style = f"color: {green}; padding: 1px; background: transparent;"
            self.status_labels["runtime"].setText(runtime_text)
            self.status_labels["runtime"].setStyleSheet(runtime_style)

        # Maestro status
        m1 = data.get("maestro1", {})
        m2 = data.get("maestro2", {})
        
        m1_connected = m1.get('connected', False)
        m2_connected = m2.get('connected', False)
        
        if m1_connected:
            channels = m1.get('channel_count', 0)
            updates["maestro1"] = f"M1: {channels}ch Connected"
            m1_style = f"color: {green}; padding: 1px; background: transparent;"
        else:
            updates["maestro1"] = "M1: Disconnected"
            m1_style = f"color: {red}; padding: 1px; background: transparent;"
            
        if m2_connected:
            channels = m2.get('channel_count', 0)
            updates["maestro2"] = f"M2: {channels}ch Connected"
            m2_style = f"color: {green}; padding: 1px; background: transparent;"
        else:
            updates["maestro2"] = "M2: Disconnected"
            m2_style = f"color: {red}; padding: 1px; background: transparent;"

        # Apply text updates
        for key, text in updates.items():
            if key in self.status_labels:
                self.status_labels[key].setText(text)

        # Apply individual styles
        if "maestro1" in self.status_labels:
            self.status_labels["maestro1"].setStyleSheet(m1_style)
        if "maestro2" in self.status_labels:
            self.status_labels["maestro2"].setStyleSheet(m2_style)

    def _update_graphs(self):
        """Update telemetry graphs with current data"""
        try:
            time_list = list(self.time_data)
            voltage_list = list(self.battery_voltage_data)
            current_a0_list = list(self.current_a0_data)
            current_a1_list = list(self.current_a1_data)
            current_a2_list = list(self.current_a2_data)
            
            if len(time_list) > 1 and len(voltage_list) > 1:
                self.voltage_curve.setData(time_list, voltage_list)
                self.current_a0_plot.setData(time_list, current_a0_list)
                self.current_a1_plot.setData(time_list, current_a1_list)
                self.current_a2_plot.setData(time_list, current_a2_list)
                self.graph_widget.update()
                
        except Exception as e:
            self.logger.error(f"Failed to update graph: {e}")

    def check_voltage_alarms(self, voltage: float):
        """Check and display voltage alarms when thresholds are crossed"""
        current_alarm = None
        
        if voltage < 11.0:
            current_alarm = "CRITICAL"
        elif voltage < 12.0:
            current_alarm = "LOW"
        
        if (current_alarm != self.last_voltage_alarm and 
            current_alarm is not None and 
            not hasattr(self, '_active_voltage_splash')):
            
            self._active_voltage_splash = VoltageAlertSplash(
                alert_type=current_alarm,
                voltage=voltage,
                parent=self
            )
            self._active_voltage_splash.splash_closed.connect(self._on_voltage_splash_closed)
            self.logger.info(f"Showing {current_alarm.lower()} voltage alert: {voltage:.2f}V")
        
        self.last_voltage_alarm = current_alarm

    def _on_voltage_splash_closed(self):
        """Handle voltage splash close event"""
        if hasattr(self, '_active_voltage_splash'):
            delattr(self, '_active_voltage_splash')
        self.logger.debug("Voltage alert splash closed")

    def get_battery_health_summary(self) -> str:
        """Get battery health summary for display"""
        if not self.battery_voltage_data:
            return "No battery data"
        
        current_voltage = self.battery_voltage_data[-1]
        if len(self.battery_voltage_data) > 10:
            avg_voltage = sum(list(self.battery_voltage_data)[-10:]) / 10
            if current_voltage > avg_voltage:
                voltage_trend = "Rising"
            elif current_voltage < avg_voltage:
                voltage_trend = "Falling"
            else:
                voltage_trend = "Stable"
        else:
            voltage_trend = "Stable"
        
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
        
        return f"{voltage_trend} | Est. Capacity: {capacity}"

    @error_boundary
    def _poll_camera_rssi(self):
        """Poll ESP32 RSSI from camera proxy status endpoint"""
        try:
            response = requests.get(f"{self._camera_proxy_base}/camera/status", timeout=2)
            if response.status_code == 200:
                rssi = response.json().get("rssi", "--")
                if "camera_rssi" in self.status_labels:
                    green = theme_manager.get("green")
                    red = theme_manager.get("red")
                    if isinstance(rssi, (int, float)):
                        style = f"color: {green}; padding: 1px; background: transparent;"
                        if rssi < -75:
                            style = "color: orange; padding: 1px; background: transparent;"
                        elif rssi < -85:
                            style = f"color: {red}; padding: 1px; background: transparent;"
                        self.status_labels["camera_rssi"].setText(f"Camera WiFi: {rssi}dBm")
                    else:
                        self.status_labels["camera_rssi"].setText("Camera WiFi: --")
                        style = f"color: {green}; padding: 1px; background: transparent;"
                    self.status_labels["camera_rssi"].setStyleSheet(style)
        except Exception:
            pass  # Keep last value if poll fails

    def cleanup(self):
        """Cleanup health screen resources"""
        if hasattr(self, 'rssi_poll_timer'):
            self.rssi_poll_timer.stop()

        if hasattr(self, '_active_voltage_splash'):
            self._active_voltage_splash.close_splash()
            delattr(self, '_active_voltage_splash')
        
        super().cleanup()