#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - Updated Base Screen Components with WiFi Monitoring
"""

import random
from abc import ABC, abstractmethod
from PyQt6.QtWidgets import QWidget, QLabel, QFrame, QHBoxLayout
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QTimer

from core.logger import get_logger
from core.utils import error_boundary
from threads.network_monitor import NetworkMonitorThread


# Create a compatible metaclass for PyQt6 + ABC
class WidgetABCMeta(type(QWidget), type(ABC)):
    pass


class BaseScreen(QWidget, ABC, metaclass=WidgetABCMeta):
    """Abstract base class for all application screens"""
    
    def __init__(self, websocket=None):
        super().__init__()
        self.logger = get_logger(self.__class__.__name__.lower())
        self.websocket = websocket
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        self._setup_screen()
    
    @abstractmethod
    def _setup_screen(self):
        """Setup screen-specific UI components"""
        pass
    
    def cleanup(self):
        """Override in subclasses for custom cleanup"""
        pass
    
    @error_boundary
    def send_websocket_message(self, message_type: str, **kwargs) -> bool:
        """Send message via WebSocket if available"""
        if self.websocket and self.websocket.is_connected():
            return self.websocket.send_command(message_type, **kwargs)
        else:
            self.logger.warning(f"Cannot send {message_type}: WebSocket not connected")
            return False

from PyQt6.QtGui import QPainter, QColor, QFont
from PyQt6.QtCore import QRect

class RightStatusWidget(QWidget):
    """Combined right-side header widget: [BattIcon BattPct GAP WifiBars WifiPct].
    Battery section is only rendered on Linux (Steam Deck). WiFi is always shown.
    """

    def __init__(self, battery_widget: "SteamDeckBatteryWidget"):
        super().__init__()
        self._battery = battery_widget   # shared reference so we can read its state

        # WiFi / connection state
        self.current_signal = 0
        self.ws_connected = False        # driven by WebSocket signals, not ping
        self.wifi_color = "#FF4444"

        # WiFi flash timer
        self.flash_timer = QTimer()
        self.flash_timer.timeout.connect(self._toggle_wifi_flash)
        self.flash_state = True

        self.setFixedHeight(32)
        self.setFixedWidth(310)

    # ── Public API ────────────────────────────────────────────────────────────
    def update_display(self, signal_percent: int, ping_ms: float = None):
        """Update WiFi signal strength (ping_ms kept for API compat, ignored)."""
        self.current_signal = signal_percent
        self.update()

    def set_websocket_connected(self, connected: bool):
        """Called by DynamicHeader when WebSocket connects or disconnects."""
        self.ws_connected = connected
        if connected:
            self.wifi_color = "#44FF44"
            self._stop_wifi_flash()
        else:
            self.wifi_color = "#FF4444"
            self._start_wifi_flash()
        self.update()

    # ── WiFi flash helpers ────────────────────────────────────────────────────
    def _start_wifi_flash(self):
        if not self.flash_timer.isActive():
            self.flash_timer.start(500)

    def _stop_wifi_flash(self):
        self.flash_timer.stop()
        self.flash_state = True

    def _toggle_wifi_flash(self):
        self.flash_state = not self.flash_state
        self.update()

    # ── Keep legacy callers working ───────────────────────────────────────────
    def start_flashing(self):
        self._start_wifi_flash()

    def stop_flashing(self):
        self._stop_wifi_flash()

    def toggle_flash(self):
        self._toggle_wifi_flash()

    # ── Paint ────────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        base_y = 28         # text baseline / bar base

        # ── Measure total content width first so we can right-align everything ──
        painter.setFont(QFont("Arial", 22))
        fm = painter.fontMetrics()

        wifi_text = f"{self.current_signal}%"
        wifi_text_w = fm.horizontalAdvance(wifi_text)
        bar_width = 4
        bar_spacing = 2
        bar_heights = [10, 15, 20, 25, 30]
        n_bars = 5
        bars_total_w = n_bars * bar_width + (n_bars - 1) * bar_spacing
        wifi_section_w = bars_total_w + 6 + wifi_text_w   # bars + gap + text

        batt_section_w = 0
        if self._battery._visible and self._battery._percent >= 0:
            batt_text = f"{self._battery._percent}%"
            batt_text_w = fm.horizontalAdvance(batt_text)
            batt_icon_w = 18 + 3  # body + tip
            batt_section_w = batt_icon_w + 10 + batt_text_w + 14  # icon + gap + text + separator gap

        total_w = batt_section_w + wifi_section_w
        # Start x so content ends 4px from right edge
        start_x = w - total_w - 4

        # ── Battery section (Linux / Steam Deck only) ─────────────────────
        if self._battery._visible and self._battery._percent >= 0:
            batt_color = QColor(self._battery._color)
            if not self._battery._flash_state:
                batt_color.setAlpha(80)

            bx = start_x
            by, bw, bh = 7, 18, 14
            tip_w, tip_h = 3, 6
            tip_x = bx + bw
            tip_y = by + (bh - tip_h) // 2

            painter.setPen(batt_color)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(bx, by, bw, bh)

            painter.setBrush(batt_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(tip_x, tip_y, tip_w, tip_h)

            fill_w = max(1, int((bw - 4) * self._battery._percent / 100))
            painter.drawRect(bx + 2, by + 2, fill_w, bh - 4)

            # Battery percentage text
            painter.setPen(batt_color)
            painter.setFont(QFont("Arial", 22))
            batt_text = f"{self._battery._percent}%"
            batt_text_x = bx + bw + tip_w + 10
            painter.drawText(batt_text_x, base_y - 2, batt_text)

            wifi_start_x = start_x + batt_section_w
        else:
            wifi_start_x = start_x

        # ── WiFi bars ────────────────────────────────────────────────────────
        bars_x = wifi_start_x

        if self.current_signal >= 95:
            active_bars = 5
        elif self.current_signal >= 75:
            active_bars = 4
        elif self.current_signal >= 50:
            active_bars = 3
        elif self.current_signal >= 25:
            active_bars = 2
        elif self.current_signal > 0:
            active_bars = 1
        else:
            active_bars = 0

        for i in range(n_bars):
            x = bars_x + i * (bar_width + bar_spacing)
            y = base_y - bar_heights[i]
            if i < active_bars:
                c = QColor(self.wifi_color)
                if not self.flash_state:
                    c.setAlpha(80)
            else:
                c = QColor("#333333")
            painter.fillRect(QRect(x, y, bar_width, bar_heights[i]), c)

        # WiFi percentage text
        painter.setPen(QColor(self.wifi_color))
        painter.setFont(QFont("Arial", 22))
        wifi_text_x = bars_x + bars_total_w + 6
        painter.drawText(wifi_text_x, base_y - 2, wifi_text)




class SteamDeckBatteryWidget(QWidget):
    """Widget displaying Steam Deck internal battery percentage with colour coding and low-battery flash"""

    LOW_BATTERY_THRESHOLD = 20
    CRITICAL_BATTERY_THRESHOLD = 10

    # Candidate sysfs paths - BAT0 is standard, BAT1 seen on some devices
    BATTERY_PATHS = [
        "/sys/class/power_supply/BAT0/capacity",
        "/sys/class/power_supply/BAT1/capacity",
    ]
    CHARGING_PATHS = [
        "/sys/class/power_supply/BAT0/status",
        "/sys/class/power_supply/BAT1/status",
    ]

    def __init__(self):
        super().__init__()
        import platform as _platform
        self._platform = _platform.system().lower()

        self.setFixedSize(160, 32)
        self._percent = -1
        self._charging = False
        self._color = "#44FF44"
        self._flash_state = True

        # Visible on Linux only - hide completely on macOS/Windows
        self._visible = (self._platform == "linux")

        self._battery_path = None
        self._charging_path = None

        self._flash_timer = QTimer()
        self._flash_timer.timeout.connect(self._toggle_flash)

        if self._visible:
            self._poll_timer = QTimer()
            self._poll_timer.timeout.connect(self._read_battery)
            self._poll_timer.start(30000)
            self._read_battery()

    def _find_paths(self):
        """Locate the sysfs battery paths, trying all candidates"""
        import os
        for cap_path, status_path in zip(self.BATTERY_PATHS, self.CHARGING_PATHS):
            if os.path.exists(cap_path):
                self._battery_path = cap_path
                self._charging_path = status_path
                return True
        return False

    def _read_battery(self):
        """Read battery capacity - tries sysfs first, falls back to upower"""
        # Try to find sysfs path if not yet located
        if self._battery_path is None:
            self._find_paths()

        # Method 1: sysfs direct read
        if self._battery_path:
            try:
                with open(self._battery_path, "r") as f:
                    self._percent = int(f.read().strip())
                try:
                    with open(self._charging_path, "r") as f:
                        self._charging = f.read().strip().lower() in ("charging", "full")
                except Exception:
                    self._charging = False
                self._update_state()
                self.update()
                return
            except Exception:
                pass  # Fall through to upower

        # Method 2: upower command (works inside Distrobox containers)
        try:
            import subprocess, re
            result = subprocess.run(
                ["upower", "-i", "/org/freedesktop/UPower/devices/battery_BAT0"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                pct_match = re.search(r"percentage:\s+(\d+)", result.stdout)
                state_match = re.search(r"state:\s+(\w+)", result.stdout)
                if pct_match:
                    self._percent = int(pct_match.group(1))
                    self._charging = state_match and state_match.group(1) in ("charging", "fully-charged")
                    self._update_state()
                    self.update()
                    return
        except Exception:
            pass

        # Method 3: acpi command
        try:
            import subprocess, re
            result = subprocess.run(["acpi", "-b"], capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                pct_match = re.search(r"(\d+)%", result.stdout)
                if pct_match:
                    self._percent = int(pct_match.group(1))
                    self._charging = "charging" in result.stdout.lower()
                    self._update_state()
        except Exception:
            pass

        self.update()

    def _update_state(self):
        """Set colour and flashing based on current percentage"""
        if self._charging:
            self._color = "#44AAFF"
            self._stop_flash()
        elif self._percent <= self.CRITICAL_BATTERY_THRESHOLD:
            self._color = "#FF4444"
            self._start_flash()
        elif self._percent <= self.LOW_BATTERY_THRESHOLD:
            self._color = "#FF8800"
            self._start_flash()
        elif self._percent <= 50:
            self._color = "#FFAA00"
            self._stop_flash()
        else:
            self._color = "#44FF44"
            self._stop_flash()

    def _start_flash(self):
        if not self._flash_timer.isActive():
            self._flash_timer.start(500)

    def _stop_flash(self):
        self._flash_timer.stop()
        self._flash_state = True

    def _toggle_flash(self):
        self._flash_state = not self._flash_state
        self.update()

    def paintEvent(self, event):
        """Draw battery icon and percentage"""
        if not self._visible or self._percent < 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = QColor(self._color)
        if not self._flash_state:
            color.setAlpha(80)

        # Battery body outline
        body_x, body_y, body_w, body_h = 2, 6, 22, 18
        tip_w, tip_h = 4, 8
        tip_x = body_x + body_w
        tip_y = body_y + (body_h - tip_h) // 2

        painter.setPen(color)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(body_x, body_y, body_w, body_h)

        # Battery tip
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(tip_x, tip_y, tip_w, tip_h)

        # Fill level
        fill_w = max(1, int((body_w - 4) * self._percent / 100))
        painter.drawRect(body_x + 2, body_y + 2, fill_w, body_h - 4)

        # Percentage text
        painter.setPen(color)
        painter.setFont(QFont("Arial", 30))
        painter.drawText(32, 28, f"{self._percent}%")

class DynamicHeader(QFrame):
    """Dynamic header showing system status at top of application"""
    
    def __init__(self, screen_name: str, pi_ip: str = "10.1.1.230"):
        super().__init__()
        self.logger = get_logger("ui")
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white;")
        self.pi_ip = pi_ip
        self._setup_ui(screen_name)
        self._setup_network_monitoring()
    
    def _setup_ui(self, screen_name: str):
        """Setup header UI components"""
        layout = QHBoxLayout()
        layout.setContentsMargins(140, 7, 140, 0)   # match pill box inset on background image
        layout.setSpacing(0)

        # Create battery widget first so RightStatusWidget can reference it
        self.battery_widget = SteamDeckBatteryWidget()

        # Status labels
        self.voltage_label = QLabel("🔋 --.-V")
        self.right_widget = RightStatusWidget(self.battery_widget)
        self.screen_label = QLabel(screen_name)

        # Keep wifi_widget as alias so existing callers (update_wifi_display etc.) still work
        self.wifi_widget = self.right_widget

        # Font styling
        header_font = QFont("Arial", 30)
        self.voltage_label.setFont(header_font)
        self.screen_label.setFont(header_font)

        # Center align the screen label
        self.screen_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Left-align the voltage label text within its fixed width
        self.voltage_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.voltage_label.setFixedWidth(300)
        self.screen_label.setFixedWidth(400)
        self.right_widget.setFixedWidth(310)

        # Battery widget is hidden from layout - its state is read by RightStatusWidget
        self.battery_widget.setFixedSize(0, 0)
        self.battery_widget.hide()

        # Layout: voltage | stretch | screen name | stretch | right status
        # Two stretches keep screen_label centred; right_widget is pinned to the right
        layout.addWidget(self.voltage_label)
        layout.addStretch(1)
        layout.addWidget(self.screen_label)
        layout.addStretch(1)
        layout.addWidget(self.right_widget)

        self.setLayout(layout)

    def _setup_network_monitoring(self):
        """Setup WiFi signal monitoring"""
        self.network_monitor = NetworkMonitorThread(pi_ip=self.pi_ip, update_interval=2.0)
        self.network_monitor.wifi_updated.connect(self.update_wifi_display)
        self.network_monitor.start()
        self.logger.info("Network monitoring started for header")

        # Poll WebSocket connection state every 3 seconds as a fallback
        self._ws_poll_timer = QTimer()
        self._ws_poll_timer.timeout.connect(self._poll_websocket_state)
        self._ws_poll_timer.start(3000)

    def connect_websocket_signals(self, websocket):
        """Wire WebSocket connected/disconnected signals to the WiFi indicator."""
        if websocket is None:
            return
        try:
            websocket.connected.connect(lambda: self.right_widget.set_websocket_connected(True))
            websocket.disconnected.connect(lambda: self.right_widget.set_websocket_connected(False))
            # Set initial state
            self.right_widget.set_websocket_connected(websocket.is_connected())
            self._websocket = websocket
            self.logger.info("WebSocket signals connected to WiFi indicator")
        except Exception as e:
            self.logger.warning(f"Could not connect WebSocket signals: {e}")

    def _poll_websocket_state(self):
        """Periodically sync WiFi indicator with actual WebSocket state."""
        if hasattr(self, '_websocket') and self._websocket:
            try:
                connected = self._websocket.is_connected()
                if connected != self.right_widget.ws_connected:
                    self.right_widget.set_websocket_connected(connected)
            except Exception:
                pass

    def update_voltage(self, voltage: float):
        """Update voltage display with color coding based on level"""
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

    def update_wifi_display(self, signal_percent: int, status_text: str, ping_ms: float):
        """Update WiFi signal strength display (ping_ms no longer used for status)."""
        self.wifi_widget.update_display(signal_percent)

    def update_wifi(self, percentage: int):
        """Legacy method for compatibility."""
        self.wifi_widget.update_display(percentage)

    def set_screen_name(self, name: str):
        """Update the current screen name display"""
        self.screen_label.setText(name)

    def cleanup(self):
        """Cleanup header resources"""
        if hasattr(self, 'network_monitor'):
            self.network_monitor.stop()


class StatusMixin:
    """Mixin class providing status update functionality"""
    
    def __init__(self):
        self._status_callbacks = []
    
    def add_status_callback(self, callback):
        """Add callback function for status updates"""
        self._status_callbacks.append(callback)
    
    def update_status(self, message: str, level: str = "info"):
        """Update status with specified message and level"""
        for callback in self._status_callbacks:
            try:
                callback(message, level)
            except Exception as e:
                if hasattr(self, 'logger'):
                    self.logger.error(f"Status callback error: {e}")


class PlaceholderScreen(BaseScreen):
    """Placeholder screen for features under development"""
    
    def __init__(self, title: str, websocket=None):
        self.title = title
        super().__init__(websocket)
    
    def _setup_screen(self):
        """Setup placeholder screen UI"""
        from PyQt6.QtWidgets import QVBoxLayout
        
        self.setFixedSize(1280, 800)
        
        label = QLabel(f"{self.title} Screen Coming Soon")
        label.setFont(QFont("Arial", 24))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout = QVBoxLayout()
        layout.addWidget(label)
        self.setLayout(layout)