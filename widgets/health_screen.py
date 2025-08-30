"""
WALL-E Control System - Health Monitoring Screen (Updated with Styled Control Panel)
Displays system telemetry, battery status, network quality, and performance graphs
"""

import json
import time
from collections import deque
from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QFrame, QWidget, 
                            QGridLayout, QMessageBox, QPushButton, QGroupBox)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal
import pyqtgraph as pg

from widgets.base_screen import BaseScreen
from threads.network_monitor import NetworkMonitorThread
from core.utils import error_boundary


class HealthScreen(BaseScreen):
    """System health monitoring with telemetry graphs and status displays"""
    
    # Qt signals for thread-safe updates
    voltage_update_signal = pyqtSignal(float)
    status_update_signal = pyqtSignal(dict)
    
    def _setup_screen(self):
        """Initialize health monitoring interface"""
        self.setFixedWidth(1180)
        
        # Rate limiting for telemetry updates
        self.last_telemetry_update = 0
        self.telemetry_update_interval = 0.25
        
        # Voltage alarm state tracking
        self.last_voltage_alarm = None
        
        # Track start time for relative time calculation
        self.start_time = time.time()
        
        # Initialize network monitoring
        pi_ip = "10.1.1.230"  # You can move this to config later
        self.network_monitor = NetworkMonitorThread(pi_ip=pi_ip, update_interval=5.0)
        self.network_monitor.wifi_updated.connect(self.update_network_status)
        self.network_monitor.bandwidth_tested.connect(self.show_bandwidth_results)
        
        # Connect WebSocket for telemetry updates
        if self.websocket:
            self.websocket.textMessageReceived.connect(self.handle_telemetry)
        
        # Connect signals for thread-safe updates
        self.voltage_update_signal.connect(self._update_voltage_display)
        self.status_update_signal.connect(self._update_status_displays)
        
        self.init_ui()
        
        # Start network monitoring
        self.network_monitor.start()
    
    def init_ui(self):
        """Initialize health monitoring UI with graphs and status displays"""
        # Main graph for battery voltage and current
        self.setup_telemetry_graph()
        
        # Status display labels
        self.setup_status_displays()
        
        # Layout assembly with styled control panel
        self.setup_layout()
    
    def setup_telemetry_graph(self):
        """Setup battery voltage and current monitoring graph"""
        self.graph_widget = pg.PlotWidget()
        self.graph_widget.setBackground('#1e1e1e')
        self.graph_widget.showGrid(x=True, y=True, alpha=0.3)
        self.graph_widget.setTitle("Battery Voltage & Current Draw", color='white', size='14pt')
        self.graph_widget.setLabel('left', 'Battery Voltage (V)', color='white')
        self.graph_widget.setLabel('bottom', 'Time (s)', color='white')
        
        # Set voltage range for 4S LiPo batteries
        self.graph_widget.setYRange(0, 20)
        self.graph_widget.setLimits(yMin=0, yMax=20)
        self.graph_widget.setMouseEnabled(x=False, y=False)
        
        # Add legend
        self.graph_widget.addLegend(offset=(10, 20))
        self.graph_widget.getPlotItem().setContentsMargins(5, 5, 5, 5)
        
        # Data storage with performance limits
        self.max_data_points = 100
        self.battery_voltage_data = deque(maxlen=self.max_data_points)
        self.current_a0_data = deque(maxlen=self.max_data_points)
        self.current_a1_data = deque(maxlen=self.max_data_points)
        self.time_data = deque(maxlen=self.max_data_points)
        
        # Voltage curve (primary Y-axis)
        self.voltage_curve = self.graph_widget.plot(
            pen=pg.mkPen(color='#00FF00', width=4),
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
        
        # Link the views
        self.graph_widget.getPlotItem().getViewBox().sigResized.connect(self.update_views)
        
        # Current plots
        self.current_a0_plot = pg.PlotCurveItem(
            pen=pg.mkPen(color='#00FFFF', width=3), 
            name="Current Battery 1",
            antialias=True
        )
        self.current_view.addItem(self.current_a0_plot)
        
        self.current_a1_plot = pg.PlotCurveItem(
            pen=pg.mkPen(color='#FF00FF', width=3), 
            name="Current Battery 2",
            antialias=True
        )
        self.current_view.addItem(self.current_a1_plot)
        
        # Add current items to legend
        legend = self.graph_widget.addLegend(offset=(30, 30))
        legend.addItem(self.current_a0_plot, "Current A0")
        legend.addItem(self.current_a1_plot, "Current A1")

    def setup_status_displays(self):
        """Setup system status display labels"""
        self.status_labels = {}

    def _create_control_panel(self):
        """Create the styled health monitoring control panel"""
        # Main panel with same styling as servo screen - wider for better readability
        control_panel = QWidget()
        control_panel.setFixedWidth(340)  # Increased width
        control_panel.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                border: 2px solid #e1a014;
                border-radius: 12px;
                color: white;
            }
        """)
        
        panel_layout = QVBoxLayout()
        panel_layout.setContentsMargins(15, 5, 15, 15)
        panel_layout.setSpacing(15)
        
        # Header with same styling as settings
        header = QLabel("SYSTEM HEALTH")
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
        panel_layout.addWidget(header)
        
        # Status display section
        status_section = self._create_status_display_section()
        panel_layout.addWidget(status_section)
        
        panel_layout.addSpacing(10)
        
        # System controls section
        system_section = self._create_system_controls_section()
        panel_layout.addWidget(system_section)
        
        panel_layout.addStretch()
        control_panel.setLayout(panel_layout)
        return control_panel

    def _create_status_display_section(self):
        """Create status display section within the control panel"""
        status_frame = QWidget()
        status_frame.setStyleSheet("""
            QWidget {
                border: 1px solid #555;
                border-radius: 8px;
                background-color: rgba(0, 0, 0, 0.3);
            }
        """)
        
        status_layout = QVBoxLayout()
        status_layout.setContentsMargins(12, 8, 12, 18)
        status_layout.setSpacing(4)
        
        # Status header
        status_header = QLabel("STATUS")
        status_header.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        status_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_header.setStyleSheet("color: #e1a014; border: none; margin-bottom: 3px;")
        status_layout.addWidget(status_header)
        
        # Create status labels within the panel
        label_configs = [
            ("cpu", "CPU: 0%"),
            ("mem", "Memory: 0%"),
            ("temp", "Temp: 0°C"),
            ("battery", "Battery: 0.0V"),
            ("ping", "Ping: -- ms"),
            ("stream", "Stream: 0 FPS"),
            ("dfplayer", "Audio: Disconnected"),
            ("maestro1", "M1: Disconnected"),
            ("maestro2", "M2: Disconnected")
        ]
        
        for key, text in label_configs:
            label = QLabel(text)
            label.setFont(QFont("Arial", 14))
            label.setStyleSheet("color: lime; padding: 1px;")
            label.setWordWrap(True)
            self.status_labels[key] = label
            status_layout.addWidget(label)
        
        status_frame.setLayout(status_layout)
        return status_frame

    def _create_system_controls_section(self):
        """Create system control operations section"""
        system_frame = QWidget()
        system_frame.setStyleSheet("""
            QWidget {
                border: 1px solid #555;
                border-radius: 8px;
                background-color: rgba(0, 0, 0, 0.3);
            }
        """)
        
        system_layout = QVBoxLayout()
        system_layout.setContentsMargins(12, 8, 12, 12)
        system_layout.setSpacing(6)
        
        # System header
        system_header = QLabel("NETWORK")
        system_header.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        system_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        system_header.setStyleSheet("color: #e1a014; border: none; margin-bottom: 3px;")
        system_layout.addWidget(system_header)
        
        # Bandwidth test button with same styling as servo screen
        self.bandwidth_btn = QPushButton("🌐 BANDWIDTH TEST")
        self.bandwidth_btn.setFont(QFont("Arial", 14))
        self.bandwidth_btn.clicked.connect(self.start_bandwidth_test)
        self.bandwidth_btn.setStyleSheet("""
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
        """)
        system_layout.addWidget(self.bandwidth_btn)
        
        system_frame.setLayout(system_layout)
        return system_frame



    def setup_layout(self):
        """Setup main layout with full-height graph and wider control panel"""
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(100, 15, 15, 10)
        
        # Graph container - full height
        graph_frame = QFrame()
        graph_frame.setStyleSheet("border: 2px solid #444; border-radius: 10px; background-color: #1e1e1e;")
        graph_layout = QVBoxLayout(graph_frame)
        graph_layout.setContentsMargins(15, 10, 15, 10)
        
        # Graph sizing - larger and full height
        self.graph_widget.setFixedWidth(680)
        self.graph_widget.setFixedHeight(475)  # Increased height
        
        graph_layout.addWidget(self.graph_widget)
        
        # Create styled control panel
        control_panel = self._create_control_panel()
        
        # Add to main layout
        main_layout.addWidget(graph_frame)
        main_layout.addWidget(control_panel)
        
        self.setLayout(main_layout)
    
    def update_views(self):
        """Update the current view geometry to match the main plot"""
        self.current_view.setGeometry(
            self.graph_widget.getPlotItem().getViewBox().sceneBoundingRect()
        )

    @error_boundary
    def update_network_status(self, wifi_percent: int, status_text: str, ping_ms: float):
        """Update network status display"""
        if ping_ms > 0:
            ping_text = f"Ping: {ping_ms:.1f}ms"
            
            # Color coding based on ping quality
            if ping_ms < 20:
                ping_style = "color: #44FF44; padding: 2px;"  # Green
            elif ping_ms < 50:
                ping_style = "color: #FFAA00; padding: 2px;"  # Yellow
            elif ping_ms < 100:
                ping_style = "color: #FF8800; padding: 2px;"  # Orange
            else:
                ping_style = "color: #FF4444; padding: 2px;"  # Red
        else:
            ping_text = "Ping: timeout"
            ping_style = "color: #FF4444; padding: 2px; font-weight: bold;"  # Red for timeout
        
        self.status_labels["ping"].setText(ping_text)
        self.status_labels["ping"].setStyleSheet(ping_style)

    @error_boundary
    def start_bandwidth_test(self, checked=False):
        """Start bandwidth test"""
        self.bandwidth_btn.setEnabled(False)
        self.bandwidth_btn.setText("TESTING...")
        self.network_monitor.request_bandwidth_test()

    @error_boundary
    def run_ping_test(self):
        """Run a quick ping test"""
        # This method can be removed since we removed the ping button
        pass
        
        # The actual ping results will come through the network monitor

    @error_boundary
    def reset_graph_time(self):
        """Reset the graph time scale to start from 0"""
        # This method can be removed since we removed the telemetry section
        pass

    @error_boundary
    def clear_graph_data(self):
        """Clear all graph data"""
        # This method can be removed since we removed the telemetry section
        pass

    @error_boundary
    def export_telemetry_data(self):
        """Export telemetry data to CSV file"""
        # This method can be removed since we removed the telemetry section
        pass


    @error_boundary
    def show_bandwidth_results(self, download_mbps: float, upload_mbps: float, status_text: str):
        """Show bandwidth test results in a popup"""
        self.bandwidth_btn.setEnabled(True)
        self.bandwidth_btn.setText("🌐 BANDWIDTH TEST")
        
        if download_mbps > 0:
            QMessageBox.information(
                self,
                "Bandwidth Test Results",
                f"Network Speed Test to Raspberry Pi:\n\n"
                f"Download Speed: {download_mbps:.1f} Mbps\n"
                f"Upload Speed: {'Not tested' if upload_mbps == 0 else f'{upload_mbps:.1f} Mbps'}\n\n"
                f"Status: {status_text}"
            )
            self.logger.info(f"Bandwidth test results: {download_mbps:.1f} Mbps download")
        else:
            QMessageBox.warning(
                self,
                "Bandwidth Test Failed",
                f"Network speed test failed:\n\n{status_text}\n\n"
                "Check network connection to Raspberry Pi."
            )
            self.logger.warning(f"Bandwidth test failed: {status_text}")

    def get_voltage_status_text(self, voltage: float) -> tuple:
        """Get voltage status with color coding"""
        if voltage < 13.2:
            return f"Battery: {voltage:.2f}V CRITICAL", "color: #FF4444; font-weight: bold;"
        elif voltage < 14.0:
            return f"Battery: {voltage:.2f}V LOW", "color: #FFAA00; font-weight: bold;"
        elif voltage > 14.0:
            return f"Battery: {voltage:.2f}V GOOD", "color: #44FF44;"
        else:
            return f"Battery: {voltage:.2f}V OK", "color: #AAAAFF;"

    def get_maestro_status_text(self, maestro_data: dict, maestro_name: str) -> tuple:
        """Format detailed Maestro status information"""
        if not maestro_data or not maestro_data.get('connected', False):
            return f"{maestro_name}: Disconnected", "color: #FF4444;"
        
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
            status = f"{maestro_name}: {channels}ch, Errors: {error_text}"
            color = "color: #FFAA00; font-weight: bold;"
        else:
            move_text = "Moving" if moving else "Idle"
            status = f"{maestro_name}: {channels}ch, {script_status.title()}, {move_text}"
            color = "color: #44FF44;"
        
        return status, color

    @error_boundary
    def handle_telemetry(self, message: str):
        """Process incoming telemetry data and update displays"""
        current_time = time.time()
        
        # Rate limiting
        if current_time - self.last_telemetry_update < self.telemetry_update_interval:
            return
        
        try:
            data = json.loads(message)
            if data.get("type") != "telemetry":
                return
            
            self.logger.debug("Processing telemetry data")
            
            # Emit signals for thread-safe updates
            battery_voltage = (data.get("battery_voltage") or 
                             data.get("voltage") or 
                             data.get("battery") or 12.6)
            
            if battery_voltage > 0:
                self.voltage_update_signal.emit(battery_voltage)
            
            # Emit status updates
            self.status_update_signal.emit(data)
            
            # Update graph data
            current_a0 = data.get("current", 0.0)
            current_a1 = data.get("current_a1", 0.0)
            relative_time = current_time - self.start_time
            
            self.battery_voltage_data.append(float(battery_voltage))
            self.current_a0_data.append(float(current_a0))
            self.current_a1_data.append(float(current_a1))
            self.time_data.append(relative_time)
            
            # Update graphs
            self._update_graphs()
            
            self.last_telemetry_update = current_time
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode failed: {e}")
        except Exception as e:
            self.logger.error(f"Telemetry processing failed: {e}")

    def _update_voltage_display(self, voltage: float):
        """Thread-safe voltage display update"""
        battery_text, battery_style = self.get_voltage_status_text(voltage)
        self.status_labels["battery"].setText(battery_text)
        self.status_labels["battery"].setStyleSheet(battery_style)
        
        # Check for voltage alarms
        self.check_voltage_alarms(voltage)

    def _update_status_displays(self, data: dict):
        """Thread-safe status display updates"""
        updates = {}
        
        # Basic system stats
        cpu = data.get("cpu", "--")
        mem = data.get("memory", "--")
        temp = data.get("temperature", "--")
        
        updates["cpu"] = f"CPU: {cpu}%"
        updates["mem"] = f"Memory: {mem}%"
        updates["temp"] = f"Temp: {temp}°C"
        
        # Stream info
        stream = data.get("stream", {})
        updates["stream"] = f"Stream: {stream.get('fps', 0)} FPS"
        
        # Audio system
        audio = data.get("audio_system", {})
        updates["dfplayer"] = f"Audio: {'Connected' if audio.get('connected') else 'Disconnected'}"
        
        # Maestro status - shortened for panel
        m1 = data.get("maestro1", {})
        m2 = data.get("maestro2", {})
        
        m1_connected = m1.get('connected', False)
        m2_connected = m2.get('connected', False)
        
        if m1_connected:
            channels = m1.get('channel_count', 0)
            updates["maestro1"] = f"M1: {channels}ch Connected"
            m1_style = "color: #44FF44; padding: 1px;"
        else:
            updates["maestro1"] = "M1: Disconnected"
            m1_style = "color: #FF4444; padding: 1px;"
            
        if m2_connected:
            channels = m2.get('channel_count', 0)
            updates["maestro2"] = f"M2: {channels}ch Connected"
            m2_style = "color: #44FF44; padding: 1px;"
        else:
            updates["maestro2"] = "M2: Disconnected"
            m2_style = "color: #FF4444; padding: 1px;"
        
        # Update all text labels
        for key, text in updates.items():
            if key in self.status_labels:
                self.status_labels[key].setText(text)
        
        # Apply styles
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
            
            if len(time_list) > 1 and len(voltage_list) > 1:
                # Update curves
                self.voltage_curve.setData(time_list, voltage_list)
                self.current_a0_plot.setData(time_list, current_a0_list)
                self.current_a1_plot.setData(time_list, current_a1_list)
                
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
        
        # Only show popup if alarm state changed
        if current_alarm != self.last_voltage_alarm and current_alarm is not None:
            if current_alarm == "CRITICAL":
                QMessageBox.critical(
                    self, "Battery Critical", 
                    f"CRITICAL: Battery voltage is {voltage:.2f}V!\nLand immediately to prevent damage!"
                )
            elif current_alarm == "LOW":
                QMessageBox.warning(
                    self, "Battery Low", 
                    f"WARNING: Battery voltage is {voltage:.2f}V\nConsider landing soon."
                )
        
        self.last_voltage_alarm = current_alarm

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
        
        return f"{voltage_trend} | Est. Capacity: {capacity}"

    def cleanup(self):
        """Cleanup health screen resources"""
        if hasattr(self, 'network_monitor'):
            self.network_monitor.stop()
        super().cleanup()