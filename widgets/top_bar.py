#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Top bar drawn over the header band of every screen.

Left to right: robot pack charge, live track and electronics current,
the most serious active problem (or the drive mode when there is none),
the WiFi link to the robot, and the Steam Deck's own battery.
"""

import re
import subprocess
import sys

from PyQt6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QWidget
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics, QPen, QPolygonF, QLinearGradient, QImage
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF

from core.logger import get_logger
from core.theme_manager import theme_manager
from core.battery import battery_profile
from threads.network_monitor import NetworkMonitorThread

# Recess over the header band, lined up with the edges of the body panel;
# the bar sits inside it like the screens sit inside the body panel
RECESS_X, RECESS_Y, RECESS_WIDTH, RECESS_HEIGHT = 102, 64, 1084, 76
RECESS_INSET = 5
RECESS_RADIUS = 16
BAR_WIDTH = RECESS_WIDTH - 2 * RECESS_INSET
BAR_HEIGHT = RECESS_HEIGHT - 2 * RECESS_INSET

ROBOT_CELL_WIDTH = 190
GAUGE_CELL_WIDTH = 250
WIFI_CELL_WIDTH = 160
DECK_CELL_WIDTH = 180

# Room left for the alert text: the status cell less its margins, icon and gaps
STATUS_TEXT_WIDTH = (BAR_WIDTH - 2 - 4 - ROBOT_CELL_WIDTH - GAUGE_CELL_WIDTH
                     - WIFI_CELL_WIDTH - DECK_CELL_WIDTH - 28 - 20 - 10)
ALERT_COUNT_WIDTH = 40
SSID_TEXT_WIDTH = WIFI_CELL_WIDTH - 16 - 12 - 30 - 12

AMBER = "#ff9800"
CURRENT_ORANGE = "#ff8c00"
LABEL_GREY = "#9e9e9e"
TEXT_SOFT = "#bdbdbd"
UNLIT = "#333333"
IDLE_GREY = "#777777"
DIVIDER = "#3a3a3a"

TRACK_MAX_AMPS = 60.0
ELECTRONICS_MAX_AMPS = 25.0
GAUGE_WARN_FRACTION = 0.8

DECK_LOW_PERCENT = 20
DECK_CRITICAL_PERCENT = 10
DECK_BATTERY_POLL_MS = 30000

WEAK_SIGNAL_PERCENT = 40
SLOW_PING_MS = 80.0


def px_font(pixel_size: int, bold: bool = False, spacing: float = 0.0) -> QFont:
    font = QFont("Arial")
    font.setPixelSize(pixel_size)
    font.setBold(bold)
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return font


def rgba(color: str, alpha: float) -> str:
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


# Point inside the body panel of every background image; the bar takes its colour
# from here so it matches the area behind the screens
BODY_PANEL_SAMPLE = (640, 400)
BODY_PANEL_FALLBACK = "#131313"
_body_panel_colors = {}


def body_panel_color() -> str:
    """Colour of the current theme's body panel, read from its background image"""
    path = theme_manager.get_image_path("background")
    if path not in _body_panel_colors:
        image = QImage(path)
        if image.isNull():
            _body_panel_colors[path] = BODY_PANEL_FALLBACK
        else:
            _body_panel_colors[path] = image.pixelColor(*BODY_PANEL_SAMPLE).name()
    return _body_panel_colors[path]


def bolt_polygon(cx: float, cy: float, scale: float) -> QPolygonF:
    """Lightning bolt centred on (cx, cy)"""
    points = [(1, -11), (-5, 1), (0, 1), (-2, 11), (6, -2), (1, -2)]
    return QPolygonF([QPointF(cx + x * scale, cy + y * scale) for x, y in points])


class BatteryIcon(QWidget):
    """Battery outline filled to a level, with optional alert marks and charging bolt"""

    def __init__(self):
        super().__init__()
        self.setFixedSize(70, 28)
        self._fraction = None
        self._color = IDLE_GREY
        self._marks = []
        self._charging = False

    def set_state(self, fraction, color: str, marks=(), charging: bool = False):
        self._fraction = None if fraction is None else max(0.0, min(1.0, fraction))
        self._color = color
        self._marks = list(marks)
        self._charging = charging
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self._color)

        painter.setPen(QPen(color, 2))
        painter.setBrush(QColor("#1c1c1c"))
        painter.drawRoundedRect(QRectF(1, 1, 62, 26), 5, 5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(63, 9, 5, 10), 1.5, 1.5)

        if self._fraction:
            painter.drawRoundedRect(QRectF(4, 4, 56 * self._fraction, 20), 3, 3)

        painter.setBrush(QColor(17, 17, 17, 180))
        for mark in self._marks:
            if 0.0 < mark < 1.0:
                painter.drawRect(QRectF(4 + 56 * mark, 4, 1.5, 20))

        if self._charging:
            painter.setBrush(QColor("#111111"))
            painter.drawPolygon(bolt_polygon(33, 14, 0.95))


class DialGauge(QWidget):
    """Three-quarter ring gauge"""

    def __init__(self):
        super().__init__()
        self.setFixedSize(40, 40)
        self._fraction = 0.0
        self._color = CURRENT_ORANGE

    def set_value(self, fraction: float, color: str):
        self._fraction = max(0.0, min(1.0, fraction))
        self._color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(4, 4, 32, 32)
        start = 225 * 16
        span = -270 * 16

        track = QPen(QColor("#2c2c2c"), 5)
        track.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(track)
        painter.drawArc(rect, start, span)

        if self._fraction > 0:
            value = QPen(QColor(self._color), 5)
            value.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(value)
            painter.drawArc(rect, start, int(span * self._fraction))


class SignalBars(QWidget):
    """Four signal bars, lit up to a count"""

    def __init__(self):
        super().__init__()
        self.setFixedSize(30, 26)
        self._count = 0
        self._color = IDLE_GREY

    def set_state(self, count: int, color: str):
        self._count = count
        self._color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(4):
            height = 8 + i * 6
            painter.setBrush(QColor(self._color if i < self._count else UNLIT))
            painter.drawRoundedRect(QRectF(i * 8, 26 - height, 5, height), 1, 1)


class WarningIcon(QWidget):
    """Outlined warning triangle"""

    def __init__(self):
        super().__init__()
        self.setFixedSize(20, 19)
        self._color = AMBER

    def set_color(self, color: str):
        self._color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self._color)
        pen = QPen(color, 1.8)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(QPolygonF([QPointF(10, 1.5), QPointF(18.5, 17.5), QPointF(1.5, 17.5)]))
        painter.drawLine(QPointF(10, 7), QPointF(10, 12))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(10, 14.7), 1.1, 1.1)


class DriveModeIcon(QWidget):
    """Two people for crowd mode, a speedometer for full speed"""

    def __init__(self):
        super().__init__()
        self.setFixedSize(20, 18)
        self._color = AMBER
        self._crowd = True

    def set_mode(self, crowd: bool, color: str):
        self._crowd = crowd
        self._color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(self._color), 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self._crowd:
            painter.drawEllipse(QPointF(6.5, 5), 2.6, 2.6)
            painter.drawEllipse(QPointF(13.5, 5), 2.6, 2.6)
            painter.drawArc(QRectF(1.5, 10, 10, 12), 0, 180 * 16)
            painter.drawArc(QRectF(8.5, 10, 10, 12), 0, 180 * 16)
        else:
            painter.drawArc(QRectF(2, 3, 16, 16), 0, 180 * 16)
            painter.drawLine(QPointF(10, 11), QPointF(14.5, 6))


class TopBar(QWidget):
    """Status bar in its own recess over the header band; parented to the main window"""

    def __init__(self, parent: QWidget, pi_ip: str = "10.42.0.1"):
        super().__init__(parent)
        self.logger = get_logger("ui")
        self.setGeometry(RECESS_X, RECESS_Y, RECESS_WIDTH, RECESS_HEIGHT)
        self.panel = QFrame(self)
        self.panel.setObjectName("top_bar")
        self.panel.setGeometry(RECESS_INSET, RECESS_INSET, BAR_WIDTH, BAR_HEIGHT)
        self.pi_ip = pi_ip

        # Last good readings; None until one arrives
        self._volts = None
        self._soc = None
        self._tracks = None
        self._total = None
        self._signal = None
        self._ping = None
        self._ssid = ""
        self._deck_percent = None
        self._deck_charging = False

        self._ws_connected = False
        self._websocket = None
        self._backend_alerts = []
        self._maestro_alerts = []
        self._alert_color = None
        self._drive_mode = None

        self._build()
        self._apply_theme()

        battery_profile.changed.connect(self._refresh_robot)
        theme_manager.register_callback(self._apply_theme)

        self._deck_battery_path = None
        self._deck_status_path = None
        self._deck_timer = QTimer(self)
        self._deck_timer.timeout.connect(self._read_deck_battery)
        self._deck_timer.start(DECK_BATTERY_POLL_MS)
        self._read_deck_battery()

        self.network_monitor = NetworkMonitorThread(pi_ip=pi_ip, update_interval=2.0)
        self.network_monitor.wifi_updated.connect(self._on_wifi)
        self.network_monitor.connectivity_updated.connect(self._on_ping)
        self.network_monitor.ssid_updated.connect(self._on_ssid)
        self.network_monitor.start()

        self._refresh_all()

    # ---------- Layout ----------

    def paintEvent(self, event):
        """Dark recess with a shaded top edge and a faint lit lower lip"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)

        painter.setPen(QPen(QColor(0, 0, 0), 1))
        painter.setBrush(QColor(10, 11, 13))
        painter.drawRoundedRect(rect, RECESS_RADIUS, RECESS_RADIUS)

        shade = QLinearGradient(0, 0, 0, RECESS_INSET * 2)
        shade.setColorAt(0, QColor(0, 0, 0, 150))
        shade.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shade)
        painter.drawRoundedRect(rect, RECESS_RADIUS, RECESS_RADIUS)

        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        lip = QRectF(rect.left() + RECESS_RADIUS, rect.bottom() - 0.5,
                     rect.width() - 2 * RECESS_RADIUS, 0)
        painter.drawLine(lip.topLeft(), lip.topRight())

    def _build(self):
        layout = QHBoxLayout(self.panel)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        self.robot_icon, self.robot_value, self.robot_sub = self._battery_cell(layout, "ROBOT", ROBOT_CELL_WIDTH)
        layout.addWidget(self._divider())
        layout.addWidget(self._gauge_cell())
        layout.addWidget(self._divider())
        layout.addWidget(self._status_cell(), 1)
        layout.addWidget(self._divider())
        layout.addWidget(self._wifi_cell())
        layout.addWidget(self._divider())
        self.deck_icon, self.deck_value, self.deck_sub = self._battery_cell(layout, "DECK", DECK_CELL_WIDTH)

    def _label(self, text: str, font: QFont, color: str = "#ffffff") -> QLabel:
        label = QLabel(text)
        label.setFont(font)
        label.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        return label

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFixedWidth(1)
        line.setStyleSheet(f"background: {DIVIDER}; border: none;")
        return line

    def _cell(self, width: int) -> QWidget:
        cell = QWidget()
        cell.setFixedWidth(width)
        cell.setStyleSheet("background: transparent;")
        return cell

    def _battery_cell(self, parent_layout: QHBoxLayout, caption: str, width: int):
        cell = self._cell(width)
        row = QHBoxLayout(cell)
        row.setContentsMargins(15, 0, 10, 0)
        row.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(5)
        left.addStretch(1)
        left.addWidget(self._label(caption, px_font(11, spacing=1.5), LABEL_GREY))
        icon = BatteryIcon()
        left.addWidget(icon)
        left.addStretch(1)
        row.addLayout(left)

        right = QVBoxLayout()
        right.setSpacing(0)
        right.addStretch(1)
        value = self._label("--%", px_font(26, bold=True), IDLE_GREY)
        sub = self._label("", px_font(13), TEXT_SOFT)
        right.addWidget(value)
        right.addWidget(sub)
        right.addStretch(1)
        row.addLayout(right, 1)

        parent_layout.addWidget(cell)
        return icon, value, sub

    def _gauge_cell(self) -> QWidget:
        cell = self._cell(GAUGE_CELL_WIDTH)
        row = QHBoxLayout(cell)
        row.setContentsMargins(6, 0, 6, 0)
        row.setSpacing(5)
        self.gauges = {}
        for key, caption in (("tracks", "TRACKS"), ("electronics", "ELECTRONICS")):
            gauge = DialGauge()
            text = QVBoxLayout()
            text.setSpacing(0)
            text.addStretch(1)
            text.addWidget(self._label(caption, px_font(10, spacing=0.5), LABEL_GREY))
            value = self._label("-- A", px_font(18, bold=True))
            text.addWidget(value)
            text.addStretch(1)
            row.addWidget(gauge)
            row.addLayout(text, 1)
            self.gauges[key] = (gauge, value)
        return cell

    def _status_cell(self) -> QWidget:
        self.status_cell = QWidget()
        self.status_cell.setObjectName("top_bar_status")
        row = QHBoxLayout(self.status_cell)
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(10)
        row.addStretch(1)
        self.alert_icon = WarningIcon()
        self.alert_text = self._label("", px_font(16, bold=True))
        self.alert_count = QLabel()
        self.alert_count.setFont(px_font(12, bold=True))
        self.alert_count.setFixedHeight(22)
        self.alert_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.alert_icon)
        row.addWidget(self.alert_text)
        row.addWidget(self.alert_count)

        # Drive mode pill, shown in place of the alert when nothing is wrong
        self.drive_pill = QFrame()
        self.drive_pill.setObjectName("top_bar_drive")
        self.drive_pill.setFixedHeight(32)
        pill_row = QHBoxLayout(self.drive_pill)
        pill_row.setContentsMargins(14, 0, 14, 0)
        pill_row.setSpacing(8)
        self.drive_icon = DriveModeIcon()
        self.drive_text = QLabel()
        self.drive_text.setFont(px_font(15, bold=True, spacing=1.0))
        pill_row.addWidget(self.drive_icon)
        pill_row.addWidget(self.drive_text)
        self.drive_pill.setVisible(False)
        row.addWidget(self.drive_pill)

        row.addStretch(1)
        return self.status_cell

    def _wifi_cell(self) -> QWidget:
        cell = self._cell(WIFI_CELL_WIDTH)
        row = QHBoxLayout(cell)
        row.setContentsMargins(16, 0, 12, 0)
        row.setSpacing(12)
        self.signal_bars = SignalBars()
        row.addWidget(self.signal_bars)
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addStretch(1)
        self.ssid_label = self._label("", px_font(15, bold=True))
        self.ping_label = self._label("", px_font(13), TEXT_SOFT)
        text.addWidget(self.ssid_label)
        text.addWidget(self.ping_label)
        text.addStretch(1)
        row.addLayout(text, 1)
        return cell

    # ---------- Theme ----------

    def _apply_theme(self):
        frame = self._alert_color or rgba(theme_manager.get("primary_color"), 0.45)
        self.panel.setStyleSheet(f"""
            QFrame#top_bar {{
                background-color: {body_panel_color()};
                border: 1px solid {frame};
                border-radius: 12px;
            }}
        """)
        tint = rgba(self._alert_color, 0.16) if self._alert_color else "transparent"
        self.status_cell.setStyleSheet(f"QWidget#top_bar_status {{ background: {tint}; }}")
        self._refresh_all()

    # ---------- Inputs ----------

    def connect_websocket_signals(self, websocket):
        """Follow the backend connection for the robot readings and alerts"""
        if websocket is None:
            return
        self._websocket = websocket
        websocket.connected.connect(self._on_websocket_connected)
        websocket.disconnected.connect(self._on_websocket_disconnected)
        register_handler = getattr(websocket, "register_handler", None)
        if register_handler:
            register_handler("drive_mode", self._on_drive_mode)
        self._ws_connected = websocket.is_connected()
        self._refresh_all()

    def _on_websocket_connected(self):
        self._ws_connected = True
        self._refresh_all()

    def _on_websocket_disconnected(self):
        self._ws_connected = False
        self._drive_mode = None
        self._refresh_all()

    def _on_drive_mode(self, data: dict):
        """Crowd mode state, from telemetry or from a change broadcast"""
        crowd_mode = data.get("crowd_mode")
        percent = data.get("crowd_speed_percent")
        if isinstance(crowd_mode, bool) and isinstance(percent, (int, float)):
            self._drive_mode = (crowd_mode, int(percent))
            self._refresh_status()

    def update_telemetry(self, data: dict):
        """Apply a telemetry message; zero or missing readings keep the last value"""
        for attr, key in (("_volts", "battery_voltage"), ("_soc", "battery_soc"),
                          ("_tracks", "current_tracks"), ("_total", "current_total")):
            value = data.get(key)
            if value is not None and value != 0.0:
                setattr(self, attr, float(value))

        alerts = data.get("active_alerts")
        if isinstance(alerts, list):
            self._backend_alerts = [
                (alert.get("level", "WARNING"), alert.get("name", "Alert"))
                for alert in alerts if isinstance(alert, dict)
            ]

        maestro_alerts = []
        for key, name in (("maestro1", "Maestro 1"), ("maestro2", "Maestro 2")):
            status = data.get(key)
            if isinstance(status, dict) and status.get("connected") is False:
                maestro_alerts.append(("WARNING", f"{name} offline"))
        self._maestro_alerts = maestro_alerts

        drive_mode = data.get("drive_mode")
        if isinstance(drive_mode, dict):
            crowd_mode = drive_mode.get("crowd_mode")
            percent = drive_mode.get("crowd_speed_percent")
            if isinstance(crowd_mode, bool) and isinstance(percent, (int, float)):
                self._drive_mode = (crowd_mode, int(percent))

        self._refresh_robot()
        self._refresh_gauges()
        self._refresh_status()

    def _on_wifi(self, signal_percent: int, _status: str, _unused: float):
        self._signal = signal_percent
        self._refresh_wifi()
        self._refresh_status()

    def _on_ping(self, ping_ms: float, reachable: bool):
        self._ping = ping_ms if reachable else None
        self._refresh_wifi()
        self._refresh_status()

    def _on_ssid(self, ssid: str):
        self._ssid = ssid
        self._refresh_wifi()

    # ---------- Display ----------

    def _refresh_all(self):
        if not hasattr(self, "gauges"):
            return
        self._refresh_robot()
        self._refresh_gauges()
        self._refresh_wifi()
        self._refresh_deck()
        self._refresh_status()

    def _set_label(self, label: QLabel, text: str, color: str):
        label.setText(text)
        label.setStyleSheet(f"color: {color}; background: transparent; border: none;")

    def _pack_fraction(self, volts: float) -> float:
        span = battery_profile.full_voltage - battery_profile.empty_voltage
        if span <= 0:
            return 0.0
        return (volts - battery_profile.empty_voltage) / span

    def _refresh_robot(self):
        if not self._ws_connected or self._volts is None:
            self.robot_icon.set_state(None, IDLE_GREY)
            self._set_label(self.robot_value, "--%", IDLE_GREY)
            self._set_label(self.robot_sub, "--.- V", TEXT_SOFT)
            return

        if self._volts < battery_profile.critical_voltage:
            color = theme_manager.get("red")
        elif self._volts < battery_profile.low_voltage:
            color = AMBER
        else:
            color = theme_manager.get("green")

        marks = [self._pack_fraction(battery_profile.low_voltage),
                 self._pack_fraction(battery_profile.critical_voltage)]
        self.robot_icon.set_state(self._pack_fraction(self._volts), color, marks)
        percent = f"{self._soc:.0f}%" if self._soc is not None else "--%"
        self._set_label(self.robot_value, percent, color)
        self._set_label(self.robot_sub, f"{self._volts:.1f} V", TEXT_SOFT)

    def _refresh_gauges(self):
        tracks = self._tracks
        electronics = None
        if self._tracks is not None and self._total is not None:
            electronics = max(self._total - self._tracks, 0.0)
        for key, amps, maximum in (("tracks", tracks, TRACK_MAX_AMPS),
                                   ("electronics", electronics, ELECTRONICS_MAX_AMPS)):
            gauge, value = self.gauges[key]
            if amps is None or not self._ws_connected:
                gauge.set_value(0.0, CURRENT_ORANGE)
                self._set_label(value, "-- A", IDLE_GREY)
                continue
            fraction = amps / maximum
            color = AMBER if fraction > GAUGE_WARN_FRACTION else CURRENT_ORANGE
            gauge.set_value(fraction, color)
            self._set_label(value, f"{amps:.1f} A", "#ffffff")

    def _link_is_weak(self) -> bool:
        weak_signal = self._signal is not None and self._signal < WEAK_SIGNAL_PERCENT
        slow_ping = self._ping is not None and self._ping > SLOW_PING_MS
        return weak_signal or slow_ping

    def _refresh_wifi(self):
        signal = self._signal or 0
        bars = 4 if signal >= 75 else 3 if signal >= 50 else 2 if signal >= 25 else 1 if signal > 0 else 0

        if not self._ws_connected:
            color = theme_manager.get("red")
            ping_text = "no backend"
        elif self._link_is_weak():
            color = AMBER
            ping_text = f"{self._ping:.0f} ms · weak" if self._ping is not None else "weak signal"
        else:
            color = theme_manager.get("green")
            ping_text = f"{self._ping:.0f} ms" if self._ping is not None else ""

        self.signal_bars.set_state(bars, color)
        ssid = QFontMetrics(self.ssid_label.font()).elidedText(
            self._ssid or "No WiFi", Qt.TextElideMode.ElideRight, SSID_TEXT_WIDTH)
        self._set_label(self.ssid_label, ssid, "#ffffff" if self._ssid else IDLE_GREY)
        self._set_label(self.ping_label, ping_text, color)

    def _refresh_deck(self):
        percent = self._deck_percent
        if percent is None:
            self.deck_icon.set_state(None, IDLE_GREY)
            self._set_label(self.deck_value, "--%", IDLE_GREY)
            self._set_label(self.deck_sub, "", TEXT_SOFT)
            return
        if percent <= DECK_CRITICAL_PERCENT and not self._deck_charging:
            color = theme_manager.get("red")
        elif percent <= DECK_LOW_PERCENT and not self._deck_charging:
            color = AMBER
        else:
            color = theme_manager.get("green")
        self.deck_icon.set_state(percent / 100.0, color, charging=self._deck_charging)
        self._set_label(self.deck_value, f"{percent}%", color)
        self._set_label(self.deck_sub, "charging" if self._deck_charging else "on battery", TEXT_SOFT)

    def _active_alerts(self):
        """(level, text) pairs, most severe first"""
        if not self._ws_connected:
            return [("CRITICAL", "Backend disconnected")]
        alerts = list(self._backend_alerts) + list(self._maestro_alerts)
        if self._link_is_weak():
            alerts.append(("WARNING", "Weak WiFi link"))
        alerts.sort(key=lambda alert: 0 if alert[0] == "CRITICAL" else 1)
        return alerts

    def _refresh_status(self):
        alerts = self._active_alerts()
        if alerts:
            level, text = alerts[0]
            color = theme_manager.get("red") if level == "CRITICAL" else AMBER
        else:
            color = None

        visible = color is not None
        self.alert_icon.setVisible(visible)
        self.alert_text.setVisible(visible)
        self.alert_count.setVisible(visible and len(alerts) > 1)
        if visible:
            self.alert_icon.set_color(color)
            width = STATUS_TEXT_WIDTH - (ALERT_COUNT_WIDTH if len(alerts) > 1 else 0)
            self.alert_text.setText(QFontMetrics(self.alert_text.font()).elidedText(
                text, Qt.TextElideMode.ElideRight, width))
            self.alert_count.setText(f"+{len(alerts) - 1}")
            self.alert_count.setStyleSheet(
                f"background: {color}; color: #111111; border-radius: 11px; padding: 0 8px;"
            )

        self._refresh_drive_pill(show=not visible)

        if color != self._alert_color:
            self._alert_color = color
            self._apply_theme()

    def _refresh_drive_pill(self, show: bool):
        """Crowd mode in green, full speed in amber; hidden while an alert is showing"""
        if not show or not self._ws_connected or self._drive_mode is None:
            self.drive_pill.setVisible(False)
            return
        crowd_mode, percent = self._drive_mode
        color = theme_manager.get("green") if crowd_mode else AMBER
        self.drive_text.setText(f"CROWD MODE · {percent}%" if crowd_mode else "FULL SPEED")
        self.drive_text.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        self.drive_icon.set_mode(crowd_mode, color)
        self.drive_pill.setStyleSheet(
            f"QFrame#top_bar_drive {{ background: {rgba(color, 0.10)}; "
            f"border: 1px solid {rgba(color, 0.55)}; border-radius: 16px; }}"
        )
        self.drive_pill.setVisible(True)

    # ---------- Steam Deck battery ----------

    def _read_deck_battery(self):
        """Steam Deck battery from sysfs, falling back to upower inside the container"""
        if not sys.platform.startswith("linux"):
            return
        if self._deck_battery_path is None:
            import os
            for name in ("BAT0", "BAT1"):
                base = f"/sys/class/power_supply/{name}"
                if os.path.exists(f"{base}/capacity"):
                    self._deck_battery_path = f"{base}/capacity"
                    self._deck_status_path = f"{base}/status"
                    break

        if self._deck_battery_path:
            try:
                with open(self._deck_battery_path) as f:
                    self._deck_percent = int(f.read().strip())
                try:
                    with open(self._deck_status_path) as f:
                        self._deck_charging = f.read().strip().lower() in ("charging", "full")
                except OSError:
                    self._deck_charging = False
                self._refresh_deck()
                return
            except (OSError, ValueError):
                pass

        try:
            result = subprocess.run(
                ["upower", "-i", "/org/freedesktop/UPower/devices/battery_BAT0"],
                capture_output=True, text=True, timeout=3
            )
            percent = re.search(r"percentage:\s+(\d+)", result.stdout)
            state = re.search(r"state:\s+(\S+)", result.stdout)
            if percent:
                self._deck_percent = int(percent.group(1))
                self._deck_charging = bool(state) and state.group(1) in ("charging", "fully-charged")
        except Exception as e:
            self.logger.debug(f"Deck battery read failed: {e}")
        self._refresh_deck()

    # ---------- Shutdown ----------

    def cleanup(self):
        self._deck_timer.stop()
        try:
            theme_manager.unregister_callback(self._apply_theme)
        except Exception:
            pass
        if self._websocket is not None:
            for signal, slot in ((self._websocket.connected, self._on_websocket_connected),
                                 (self._websocket.disconnected, self._on_websocket_disconnected)):
                try:
                    signal.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
        self.network_monitor.stop()