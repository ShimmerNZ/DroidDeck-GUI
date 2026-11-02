#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - Servo Configuration Screen
Channel list on the left, editor for the selected channel on the right.
The NEMA stepper uses the same two cards for its settings and position control.
"""

import time
from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
                             QWidget, QFrame, QLineEdit, QSlider, QButtonGroup,
                             QListWidget, QListWidgetItem, QStackedWidget, QSizePolicy,
                             QAbstractButton)
from PyQt6.QtGui import QFont, QIcon, QPainter, QColor, QPixmap, QPolygonF
from PyQt6.QtCore import Qt, QTimer, QSize, QRectF, QPointF, pyqtSignal

from widgets.base_screen import BaseScreen
from core.config_manager import config_manager
from core.theme_manager import theme_manager
from core.utils import error_boundary
from core.logger import get_logger

SERVO_CONFIG_PATH = "resources/configs/servo_config.json"

# Layout - matches the Health screen card positions
CONTENT_WIDTH = 1061
CONTENT_HEIGHT = 490
CARD_GAP = 12
CARD_HEIGHT = 434
LIST_CARD_WIDTH = 410
EDIT_CARD_WIDTH = 639
BAR_HEIGHT = 44
LIST_ROW_HEIGHT = 40
LIST_ROW_SPACING = 4

CARD_OBJECT_NAME = "servo_card"

# Pulse width limits (microseconds) and stepper button increments
PULSE_MIN = 800
PULSE_MAX = 2200
PULSE_STEP = 10
LONG_PRESS_MULTIPLIER = 5
NEMA_NUDGE_CM = 0.5

# Fixed colours shared by every theme
LABEL_GREY = "#9e9e9e"
TEXT_SOFT = "#d6d6d6"
TILE_BG = "#202020"
ROW_BG = "#1f1f1f"
DIVIDER = "#2e2e2e"
DIRTY_ORANGE = "#ff9800"
IDLE_GREY = "#bdbdbd"


def px_font(pixel_size: int, bold: bool = False, spacing: float = 0.0,
            family: str = "Arial") -> QFont:
    """Font sized in pixels so the layout matches the mockup"""
    font = QFont(family)
    if family != "Arial":
        font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPixelSize(pixel_size)
    font.setBold(bold)
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return font


def rgba(color: str, alpha: float) -> str:
    """CSS rgba() string for a theme colour at the given opacity"""
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def card_style() -> str:
    primary = theme_manager.get("primary_color")
    panel_bg = theme_manager.get("panel_bg")
    return f"""
        QFrame#{CARD_OBJECT_NAME} {{
            background-color: {panel_bg};
            border: 1px solid {rgba(primary, 0.45)};
            border-radius: 12px;
        }}
        QLabel {{
            border: none;
            background: transparent;
        }}
    """


def plain_button_style() -> str:
    primary = theme_manager.get("primary_color")
    return f"""
        QPushButton {{
            background-color: #2e2e2e;
            color: white;
            border: 1px solid #666;
            border-radius: 8px;
        }}
        QPushButton:hover {{
            border-color: {primary};
        }}
        QPushButton:pressed {{
            background-color: #1a1a1a;
            border-color: {primary};
        }}
        QPushButton:disabled {{
            background: #2a2a2a;
            color: #666;
            border-color: #444;
        }}
    """


def filled_button_style(fill: str) -> str:
    return f"""
        QPushButton {{
            background-color: {fill};
            color: #111111;
            border: 1px solid {fill};
            border-radius: 8px;
        }}
        QPushButton:hover {{
            border: 2px solid white;
        }}
        QPushButton:pressed {{
            background-color: #2e2e2e;
            color: {fill};
        }}
        QPushButton:disabled {{
            background: #2a2a2a;
            color: #666;
            border-color: #444;
        }}
    """


def toggle_button_style(fill: str) -> str:
    """Plain button that fills with a colour while checked"""
    return plain_button_style() + f"""
        QPushButton:checked {{
            background-color: {fill};
            color: #111111;
            border: 1px solid {fill};
        }}
    """


def sweep_button_style() -> str:
    """Primary action button that turns red while a sweep runs"""
    primary = theme_manager.get("primary_color")
    red = theme_manager.get("red")
    return f"""
        QPushButton {{
            background-color: {primary};
            color: #111111;
            border: 1px solid {primary};
            border-radius: 8px;
        }}
        QPushButton:hover {{
            border: 2px solid white;
        }}
        QPushButton:checked {{
            background-color: {red};
            border: 1px solid {red};
            color: white;
        }}
        QPushButton:disabled {{
            background: #2a2a2a;
            color: #666;
            border-color: #444;
        }}
    """


def step_button_style() -> str:
    primary = theme_manager.get("primary_color")
    return f"""
        QPushButton {{
            background-color: #2e2e2e;
            color: white;
            border: 1px solid #555;
            border-radius: 8px;
            padding: 0px;
        }}
        QPushButton:pressed {{
            background-color: {primary};
            color: #111111;
            border-color: {primary};
        }}
        QPushButton:disabled {{
            color: #555;
            border-color: #3a3a3a;
        }}
    """


def capture_button_style() -> str:
    primary = theme_manager.get("primary_color")
    return f"""
        QPushButton {{
            background: transparent;
            color: {primary};
            border: 1px solid {rgba(primary, 0.45)};
            border-radius: 8px;
        }}
        QPushButton:pressed {{
            background-color: {rgba(primary, 0.2)};
        }}
        QPushButton:disabled {{
            color: #555;
            border-color: #3a3a3a;
        }}
    """


def input_style() -> str:
    primary = theme_manager.get("primary_color")
    return f"""
        QLineEdit {{
            background-color: {TILE_BG};
            border: 1px solid #555;
            border-radius: 8px;
            padding: 0px 12px;
            color: white;
        }}
        QLineEdit:focus {{
            border: 2px solid {primary};
            padding: 0px 11px;
        }}
        QLineEdit:disabled {{
            color: #666;
            border-color: #3a3a3a;
        }}
    """


def _dot_icon(color: str) -> QIcon:
    pixmap = QPixmap(10, 10)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(QRectF(1, 1, 8, 8))
    painter.end()
    return QIcon(pixmap)


def _play_icon(color: str) -> QIcon:
    pixmap = QPixmap(14, 14)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawPolygon(QPolygonF([QPointF(2, 1), QPointF(13, 7), QPointF(2, 13)]))
    painter.end()
    return QIcon(pixmap)


class ToggleSwitch(QAbstractButton):
    """On/off switch sized for touch"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(52, 30)

    def sizeHint(self):
        return QSize(52, 30)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            track = QColor("#2a2a2a")
        elif self.isChecked():
            track = QColor(theme_manager.get("green"))
        else:
            track = QColor("#3a3a3a")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(0, 0, 52, 30), 15, 15)
        knob_x = 25 if self.isChecked() else 3
        painter.setBrush(QColor("white") if self.isEnabled() else QColor("#666666"))
        painter.drawEllipse(QRectF(knob_x, 3, 24, 24))
        painter.end()


class StepButton(QPushButton):
    """- / + button: one step per tap, larger repeating steps while held"""

    stepped = pyqtSignal(int)

    def __init__(self, direction: int, size: int = 44):
        super().__init__("−" if direction < 0 else "+")
        self._direction = direction
        self.setFixedSize(size, size)
        self.setFont(px_font(22 if size >= 44 else 20, bold=True))
        self.setAccessibleName("Decrease" if direction < 0 else "Increase")
        self._hold_delay = QTimer(self)
        self._hold_delay.setSingleShot(True)
        self._hold_delay.timeout.connect(self._start_repeat)
        self._repeat = QTimer(self)
        self._repeat.timeout.connect(self._on_repeat)
        self.pressed.connect(self._on_pressed)
        self.released.connect(self._on_released)

    def _on_pressed(self):
        self.stepped.emit(self._direction)
        self._hold_delay.start(400)

    def _start_repeat(self):
        self._on_repeat()
        self._repeat.start(150)

    def _on_repeat(self):
        if self.isDown():
            self.stepped.emit(self._direction * LONG_PRESS_MULTIPLIER)
        else:
            self._on_released()

    def _on_released(self):
        self._hold_delay.stop()
        self._repeat.stop()


class PositionSlider(QSlider):
    """Large touch slider with a home marker"""

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.home_position = None
        self.setFixedHeight(40)
        self.live = False
        self.apply_style()

    def set_home_position(self, position):
        self.home_position = position
        self.update()

    def set_live(self, live: bool):
        self.live = live
        self.apply_style()

    def apply_style(self):
        primary = theme_manager.get("primary_color")
        fill = theme_manager.get("green") if self.live else primary
        self.setStyleSheet(f"""
            QSlider {{
                background: transparent;
                border: none;
            }}
            QSlider::groove:horizontal {{
                height: 8px;
                background: #2a2a2a;
                border-radius: 4px;
            }}
            QSlider::sub-page:horizontal {{
                background: {fill};
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: {theme_manager.get("primary_light")};
                border: 2px solid #111111;
                width: 28px;
                height: 28px;
                margin: -12px 0px;
                border-radius: 16px;
            }}
            QSlider::handle:horizontal:disabled {{
                background: #555;
            }}
        """)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.home_position is None:
            return
        span = self.maximum() - self.minimum()
        if span <= 0:
            return
        ratio = (self.home_position - self.minimum()) / span
        if not 0.0 <= ratio <= 1.0:
            return
        usable = self.width() - 32
        x = 16 + ratio * usable
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("white"))
        painter.drawRoundedRect(QRectF(x - 1.5, 6, 3, 28), 1, 1)
        painter.end()


class RangeBar(QWidget):
    """Compact min / home / max band with the current position"""

    def __init__(self):
        super().__init__()
        self.setFixedSize(84, 12)
        self.min_value = 992
        self.max_value = 2000
        self.home = None
        self.position = None
        self.live = False

    def set_values(self, min_value, max_value, home, position, live):
        self.min_value, self.max_value = min_value, max_value
        self.home, self.position, self.live = home, position, live
        self.update()

    def _x(self, value) -> float:
        ratio = (value - PULSE_MIN) / (PULSE_MAX - PULSE_MIN)
        return max(0.0, min(1.0, ratio)) * self.width()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#2a2a2a"))
        painter.drawRoundedRect(QRectF(0, 3, self.width(), 6), 3, 3)
        left, right = self._x(self.min_value), self._x(self.max_value)
        painter.setBrush(QColor("#4a4a4a"))
        painter.drawRoundedRect(QRectF(left, 3, max(2.0, right - left), 6), 3, 3)
        if self.home is not None:
            painter.setBrush(QColor(LABEL_GREY))
            painter.drawRect(QRectF(self._x(self.home) - 1, 0, 2, 12))
        if self.position is not None:
            painter.setBrush(QColor(theme_manager.get("green") if self.live else IDLE_GREY))
            painter.drawEllipse(QPointF(self._x(self.position), 6), 5, 5)
        painter.end()


class ChannelRow(QFrame):
    """One servo channel in the list"""

    def __init__(self, channel: int):
        super().__init__()
        self.channel = channel
        self.setObjectName("channel_row")
        self.setFixedHeight(LIST_ROW_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)

        self.marker = QFrame()
        self.marker.setFixedSize(4, 18)
        self.num_label = QLabel(str(channel))
        self.num_label.setFont(px_font(13, family="Consolas"))
        self.num_label.setFixedWidth(24)
        self.name_label = QLabel()
        self.name_label.setFont(px_font(15))
        self.name_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.range_bar = RangeBar()
        self.pos_label = QLabel("---")
        self.pos_label.setFont(px_font(13, family="Consolas"))
        self.pos_label.setFixedWidth(40)
        self.pos_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(self.marker)
        layout.addWidget(self.num_label)
        layout.addWidget(self.name_label, 1)
        layout.addWidget(self.range_bar)
        layout.addWidget(self.pos_label)

        self._selected = False
        self._named = False
        self._live = False

    def refresh(self, config: dict, position, live: bool):
        name = config.get("name", "")
        self._named = bool(name)
        self._live = live
        self.name_label.setText(name or "Unnamed")
        min_value = config.get("min", 992)
        max_value = config.get("max", 2000)
        self.range_bar.set_values(min_value, max_value, config.get("home"), position, live)
        self.pos_label.setText("---" if position is None else str(position))
        self._apply_style()

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style()

    def _apply_style(self):
        primary = theme_manager.get("primary_color")
        if self._selected:
            background, border = rgba(primary, 0.14), f"1px solid {primary}"
        else:
            background, border = ROW_BG, "1px solid transparent"
        self.setStyleSheet(f"""
            QFrame#channel_row {{
                background-color: {background};
                border: {border};
                border-radius: 10px;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)
        self.marker.setStyleSheet(
            f"background-color: {primary if self._selected else 'transparent'}; border: none; border-radius: 2px;")
        self.num_label.setStyleSheet(f"color: {LABEL_GREY};")
        if not self._named:
            name_color = "#6a6a6a"
        else:
            name_color = "white" if self._selected else TEXT_SOFT
        self.name_label.setStyleSheet(f"color: {name_color};")
        pos_color = theme_manager.get("green") if self._live else IDLE_GREY
        self.pos_label.setStyleSheet(f"color: {pos_color};")
        self.range_bar.update()


class ChannelList(QListWidget):
    """Channel list whose rows always span the full list width"""

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = self.viewport().width()
        for i in range(self.count()):
            self.item(i).setSizeHint(QSize(width, LIST_ROW_HEIGHT))


class ServoConfigScreen(BaseScreen):
    """Real-time servo control and configuration interface"""

    # Qt signals for thread-safe communication
    position_update_signal = pyqtSignal(str, int)
    status_update_signal = pyqtSignal(str, bool, bool)

    def __init__(self, websocket=None):
        super().__init__(websocket)

        # WebSocket messages route through the central dispatcher; D-pad
        # navigation only applies while this screen is shown
        if websocket:
            self.subscribe("maestro_info", self.handle_maestro_info)
            self.subscribe("servo_position", self.handle_servo_position)
            self.subscribe("all_servo_positions", self.handle_all_servo_positions)
            self.subscribe("servo_config_response", self.handle_servo_config_response)
            self.subscribe("nema_position_update", self.handle_nema_position_update)
            self.subscribe("nema_sweep_status", self.handle_nema_sweep_status)
            self.subscribe("nema_homing_complete", self.handle_nema_homing_complete)
            self.subscribe("nema_status", self.handle_nema_status_update)
            self.subscribe("nema_error", self.handle_nema_error)
            self.subscribe("nema_enable_response", self.handle_nema_enable_response)
            self.subscribe_while_visible("navigation", self._on_navigation)

        theme_manager.register_callback(self._on_theme_changed)

        # Maestro detection once the WebSocket is up
        self.ws_connection_timer = QTimer()
        self.ws_connection_timer.timeout.connect(self.check_websocket_and_detect)
        self.ws_connection_timer.start(2000)
        self.initial_detection_done = False

    @error_boundary
    def load_config(self) -> dict:
        """Load servo configuration from file"""
        try:
            config = config_manager.get_config(SERVO_CONFIG_PATH)
            return config if config else {}
        except Exception as e:
            self.logger.error(f"Failed to load servo config: {e}")
            return {}

    def __del__(self):
        try:
            theme_manager.unregister_callback(self._on_theme_changed)
        except Exception:
            pass

    def _setup_screen(self):
        """Initialize servo configuration screen"""
        self.logger = get_logger("servo_screen")
        self.setFixedWidth(1180)
        self.servo_config = self.load_config()
        self.nema_test_sweeping = False
        self.position_update_timer = QTimer()
        self.position_update_timer.setSingleShot(True)
        self.position_update_timer.timeout.connect(self.send_position_to_backend)
        self.active_sweeps = {}

        # Maestro state tracking
        self.maestro_channel_counts = {1: 0, 2: 0}
        self.maestro_connected = {1: False, 2: False}
        self.current_maestro = 0  # 0=Maestro1, 1=Maestro2
        self.current_controller = 0  # 0=M1, 1=M2, 2=NEMA
        self.initialization_complete = False

        # Channel editor state
        self.channel_positions = {}
        self.channel_rows = []
        self.selected_channel = None
        self._dirty_channels = set()
        self._loading_editor = False

        # NEMA configuration
        self.nema_config = {
            "lead_screw_pitch": 8.0,
            "lead_screw_length": 20.0,
            "homing_speed": 400,
            "normal_speed": 800,
            "acceleration": 800,
            "min_position": 0.0,
            "max_position": 20.0,
            "current_position": 5.0
        }
        if "nema" in self.servo_config:
            for key, value in self.servo_config["nema"].items():
                if key in self.nema_config:
                    self.nema_config[key] = value
        self.nema_target = self.nema_config["current_position"]
        self.nema_state = None

        # Position reading state
        self.reading_positions = False
        self.position_read_timeout = QTimer()
        self.position_read_timeout.timeout.connect(self.handle_position_read_timeout)
        self.position_read_timeout.setSingleShot(True)

        self.position_update_signal.connect(self.update_servo_position_display)
        self.status_update_signal.connect(self.update_status_threadsafe)

        self.setup_layout()

        QTimer.singleShot(200, self.safe_initialization)

    # ========================================
    # WEBSOCKET MESSAGE HANDLING
    # ========================================

    def handle_nema_position_update(self, msg):
        """Handle position updates from NEMA controller"""
        try:
            position_cm = msg.get("position_cm", 0.0)
            self.nema_config["current_position"] = position_cm
            self._show_nema_current(position_cm)
            self.logger.debug(f"NEMA position updated: {position_cm:.1f} cm")
        except Exception as e:
            self.logger.error(f"Error handling NEMA position update: {e}")

    def handle_nema_sweep_status(self, msg):
        """Handle sweep status changes from NEMA controller"""
        try:
            sweeping = msg.get("sweeping", False)
            self.nema_test_sweeping = sweeping
            self._show_nema_sweep(sweeping)
            if self.current_controller == 2:
                if sweeping:
                    self.update_status(f"NEMA sweep active: {self.nema_config['min_position']:.1f} -> {self.nema_config['max_position']:.1f} cm")
                else:
                    self.update_status("NEMA sweep stopped")
            self.logger.info(f"NEMA sweep status: {'active' if sweeping else 'stopped'}")
        except Exception as e:
            self.logger.error(f"Error handling NEMA sweep status: {e}")

    def handle_nema_homing_complete(self, msg):
        """Handle homing completion notification"""
        try:
            success = msg.get("success", False)
            if success:
                self.update_status("NEMA homing completed successfully", color=theme_manager.get("green"))
                self.nema_config["current_position"] = 0.0
                self._show_nema_current(0.0)
                self._set_nema_target(0.0, send=False)
            else:
                self.update_status("NEMA homing failed", error=True)
            self.logger.info(f"NEMA homing completed: {'success' if success else 'failed'}")
        except Exception as e:
            self.logger.error(f"Error handling NEMA homing complete: {e}")

    def handle_nema_status_update(self, msg):
        """Handle NEMA status updates"""
        try:
            status = msg.get("status", {})
            state = status.get("state", "unknown")
            homed = status.get("homed", False)
            hardware_enabled = status.get("enabled", False)
            position_cm = status.get("position_cm", 0.0)

            self.nema_state = {"state": state, "homed": homed, "enabled": hardware_enabled}
            self.nema_config["current_position"] = position_cm

            self._show_nema_enabled(hardware_enabled)
            self._show_nema_status_pill()
            self._show_nema_current(position_cm)
            self._update_controller_dots()

            self.logger.debug(f"NEMA status: {state}, hardware_enabled={hardware_enabled}, homed={homed}, pos={position_cm:.1f}cm")
        except Exception as e:
            self.logger.error(f"Error handling NEMA status update: {e}")

    def handle_nema_enable_response(self, msg):
        """Handle enable/disable command responses"""
        try:
            success = msg.get("success", False)
            enabled = msg.get("enabled", False)
            message = msg.get("message", "")

            if success:
                action = "enabled" if enabled else "disabled"
                self.update_status(f"NEMA stepper {action} successfully", color=theme_manager.get("green"))
                self.logger.info(f"NEMA stepper {action} successfully")
                self._show_nema_enabled(enabled)
            else:
                self.update_status(f"Failed to change NEMA state: {message}", error=True)
                self.logger.error(f"NEMA enable command failed: {message}")
                self._show_nema_enabled(not enabled)
        except Exception as e:
            self.logger.error(f"Error handling NEMA enable response: {e}")

    def handle_nema_error(self, msg):
        """Handle NEMA error messages"""
        try:
            error_message = msg.get("error", "Unknown NEMA error")
            error_code = msg.get("error_code", None)

            full_message = f"NEMA Error: {error_message}"
            if error_code:
                full_message += f" (Code: {error_code})"

            self.update_status(full_message, error=True)
            self.logger.error(f"NEMA error received: {error_message} (code: {error_code})")

            if self.nema_test_sweeping:
                self.nema_test_sweeping = False
                self._show_nema_sweep(False)
        except Exception as e:
            self.logger.error(f"Error handling NEMA error message: {e}")

    def handle_maestro_info(self, data):
        """Handle maestro info messages"""
        maestro_num = data.get("maestro")
        channels = data.get("channels", 0)
        connected = data.get("connected", False)

        if maestro_num in [1, 2]:
            self.maestro_channel_counts[maestro_num] = channels
            self.maestro_connected[maestro_num] = connected
            self.logger.info(f"Maestro {maestro_num}: {channels} channels, connected: {connected}")
            self._update_controller_dots()

            if connected:
                self.update_status(f"Maestro {maestro_num}: {channels} channels detected")
                if maestro_num == self.current_maestro + 1 and self.current_controller < 2:
                    self.update_grid()
                    QTimer.singleShot(500, self.read_all_positions_now)
            else:
                self.update_status(f"Maestro {maestro_num}: Not connected", error=True)

    def handle_servo_position(self, data):
        """Handle servo position messages"""
        channel_key = data.get("channel")
        position = data.get("position")

        if channel_key and position is not None:
            self.position_update_signal.emit(channel_key, position)

            if channel_key in self.active_sweeps:
                try:
                    self.active_sweeps[channel_key].position_reached(position)
                except Exception as e:
                    self.logger.error(f"Error updating sweep position for {channel_key}: {e}")
                    if channel_key in self.active_sweeps:
                        self.active_sweeps[channel_key].stop()
                        del self.active_sweeps[channel_key]

    def handle_all_servo_positions(self, data):
        """Handle all servo positions messages"""
        maestro_num = data.get("maestro")
        positions = data.get("positions", {})

        if maestro_num == self.current_maestro + 1:
            self.logger.info(f"Received {len(positions)} positions for Maestro {maestro_num}")

            self.reading_positions = False
            self.position_read_timeout.stop()

            for channel, position in positions.items():
                channel_key = f"m{maestro_num}_ch{channel}"
                if position is not None:
                    self.position_update_signal.emit(channel_key, position)

            if len(positions) > 0:
                self.update_status(f"Read {len(positions)} positions from Maestro {maestro_num}")
            else:
                self.update_status(f"No positions received from Maestro {maestro_num}", warning=True)

    def handle_servo_config_response(self, data):
        """Handle servo config response from backend"""
        try:
            maestro = data.get("maestro")
            config = data.get("config", {})
            self.logger.info(f"[RECV] Received config from backend: {len(config)} entries for Maestro {maestro}")

            updated_count = 0
            for channel_key, channel_config in config.items():
                if channel_key.startswith("m"):
                    self.logger.info(
                        f"  Updating {channel_key}: name='{channel_config.get('name', '')}', "
                        f"min={channel_config.get('min')}, max={channel_config.get('max')}, "
                        f"home={channel_config.get('home')}")

                    if channel_key not in self.servo_config:
                        self.servo_config[channel_key] = {}
                    for field in ("name", "min", "max", "home"):
                        if field in channel_config:
                            self.servo_config[channel_key][field] = channel_config[field]
                    self._dirty_channels.discard(channel_key)
                    updated_count += 1

            if config_manager.save_config(SERVO_CONFIG_PATH, self.servo_config):
                self.logger.info(f"[OK] Saved merged config to frontend: {updated_count} channels")
            else:
                self.logger.error("Failed to save merged config to frontend file")

            if self.current_controller < 2:
                self.update_grid()

            self.update_status(f"[OK] Config refreshed from backend: {updated_count} channels updated")

        except Exception as e:
            self.logger.error(f"Error handling servo config response: {e}", exc_info=True)
            self.update_status(f"Error refreshing config: {str(e)}", error=True)

    def _on_navigation(self, msg: dict):
        """D-pad: up/down picks a channel, left/right nudges the selected slider"""
        action = msg.get("action")
        if self.current_controller == 2:
            if action in ("left", "right"):
                step = -NEMA_NUDGE_CM if action == "left" else NEMA_NUDGE_CM
                self._set_nema_target(self.nema_target + step, send=True)
            return

        if action in ("up", "down"):
            count = self.channel_list.count()
            if count == 0:
                return
            current = max(0, self.channel_list.currentRow())
            new_row = max(0, min(count - 1, current + (-1 if action == "up" else 1)))
            if new_row != self.channel_list.currentRow():
                self._select_row(new_row)
        elif action in ("left", "right"):
            if self.selected_channel is None:
                return
            if not self.live_switch.isChecked():
                self.update_status("Turn Live on to nudge the servo with the D-pad", warning=True)
                return
            step = -PULSE_STEP if action == "left" else PULSE_STEP
            self.position_slider.setValue(self.position_slider.value() + step)

    # ========================================
    # NEMA CONTROL METHODS
    # ========================================

    def send_position_to_backend(self):
        """Send the target position to backend (called after debounce)"""
        position_cm = self.nema_target
        min_pos = self.nema_config["min_position"]
        max_pos = self.nema_config["max_position"]

        if not (min_pos <= position_cm <= max_pos):
            self.logger.warning(f"Position {position_cm:.1f} cm outside bounds [{min_pos:.1f}, {max_pos:.1f}]")
            self.update_status(f"Position {position_cm:.1f} cm outside safe bounds", error=True)
            return

        success = self.send_websocket_message("nema_move_to_position", position_cm=position_cm)
        if success:
            self.logger.debug(f"Sent position to backend: {position_cm:.1f} cm")
        else:
            self.update_status("Failed to send position: WebSocket not connected", error=True)

    def toggle_nema_test_sweep(self):
        """Toggle NEMA test sweep between min and max"""
        if self.nema_test_sweeping:
            success = self.send_websocket_message("nema_stop_sweep")
            if success:
                self.logger.info("Sent stop sweep command")
            else:
                self.update_status("Failed to stop sweep: WebSocket not connected", error=True)
        else:
            min_cm = self.nema_config["min_position"]
            max_cm = self.nema_config["max_position"]
            if min_cm >= max_cm:
                self.update_status("Invalid sweep range: min >= max", error=True)
                self._show_nema_sweep(False)
                return

            success = self.send_websocket_message("nema_start_sweep",
                                                  min_cm=min_cm,
                                                  max_cm=max_cm,
                                                  acceleration=self.nema_config["acceleration"],
                                                  normal_speed=self.nema_config["normal_speed"])
            if success:
                self.logger.info(f"Sent start sweep command: {min_cm:.1f} to {max_cm:.1f} cm")
            else:
                self.update_status("Failed to start sweep: WebSocket not connected", error=True)
        # Button state follows the backend's nema_sweep_status
        self._show_nema_sweep(self.nema_test_sweeping)

    def save_nema_config(self):
        """Save NEMA configuration locally and send it to the backend"""
        config_to_save = {k: v for k, v in self.nema_config.items() if k != "current_position"}
        self.servo_config["nema"] = config_to_save

        if config_manager.save_config(SERVO_CONFIG_PATH, self.servo_config):
            self.logger.debug("NEMA configuration saved to file")
            if self.send_websocket_message("nema_config_update", config=config_to_save):
                self.logger.debug("NEMA configuration sent to backend")
                return True
            self.logger.warning("Failed to send config to backend: WebSocket not connected")
        else:
            self.logger.error("Failed to save NEMA configuration to file")
            self.update_status("Failed to save NEMA configuration", error=True)
        return False

    def home_nema_stepper(self):
        """Send homing command to NEMA controller"""
        success = self.send_websocket_message("nema_home")
        if success:
            self.update_status("NEMA homing started...")
            self.logger.info("Sent NEMA homing command")
        else:
            self.update_status("Failed to start homing: WebSocket not connected", error=True)

    def enable_nema_stepper(self, enabled: bool):
        """Enable/disable NEMA stepper motor"""
        success = self.send_websocket_message("nema_enable", enabled=enabled)
        if success:
            action = "enabled" if enabled else "disabled"
            self.update_status(f"NEMA stepper {action}")
            self.logger.info(f"Sent NEMA enable command: {action}")
        else:
            self.update_status("Failed to change NEMA enable state: WebSocket not connected", error=True)
            self._show_nema_enabled(not enabled)

    def request_nema_status(self):
        """Request current NEMA status from backend"""
        if self.send_websocket_message("nema_get_status"):
            self.logger.debug("Requested NEMA status from backend")
        else:
            self.logger.warning("Failed to request NEMA status: WebSocket not connected")

    def clamp_nema_position(self, position_cm: float) -> float:
        """Clamp position to configured bounds"""
        min_pos = self.nema_config["min_position"]
        max_pos = self.nema_config["max_position"]
        return max(min_pos, min(max_pos, position_cm))

    def init_nema_connection(self):
        """Request NEMA status now and every 5 seconds while selected"""
        if self.current_controller == 2:
            self.request_nema_status()
            if not hasattr(self, 'nema_status_timer'):
                self.nema_status_timer = QTimer()
                self.nema_status_timer.timeout.connect(self.request_nema_status)
            self.nema_status_timer.start(5000)
            self.logger.info("NEMA connection initialized")

    def cleanup_nema_connection(self):
        """Stop NEMA polling and any active sweep"""
        if hasattr(self, 'nema_status_timer'):
            self.nema_status_timer.stop()
        if self.nema_test_sweeping:
            self.send_websocket_message("nema_stop_sweep")
        self.logger.info("NEMA connection cleaned up")

    def update_nema_position(self, slider_value):
        """Target slider moved: update the target and send it after a short pause"""
        self._set_nema_target(float(slider_value) / 10.0, send=True)

    def _set_nema_target(self, position_cm: float, send: bool):
        clamped = self.clamp_nema_position(position_cm)
        if send and abs(clamped - position_cm) > 1e-6:
            self.update_status(f"Position clamped to {clamped:.1f} cm", color=DIRTY_ORANGE)
        self.nema_target = clamped

        self.nema_slider.blockSignals(True)
        self.nema_slider.setValue(int(round(clamped * 10)))
        self.nema_slider.blockSignals(False)
        self.nema_target_label.setText(f"{clamped:.1f}")

        if send:
            self.position_update_timer.stop()
            self.position_update_timer.start(300)

    def _step_nema_setting(self, key: str, delta: int):
        """Apply a - / + step to a NEMA setting, validate and save"""
        spec = self._nema_specs[key]
        current = self.nema_config[key]
        new_value = current + delta * spec["step"]
        new_value = max(spec["min"], min(spec["max"], new_value))
        if spec["float"]:
            new_value = float(new_value)
        else:
            new_value = int(new_value)
        if new_value == current:
            return

        if key == "min_position" and new_value >= self.nema_config["max_position"]:
            self.update_status(f"Min position {new_value:.1f} must be less than max {self.nema_config['max_position']:.1f}", error=True)
            return
        if key == "max_position" and new_value <= self.nema_config["min_position"]:
            self.update_status(f"Max position {new_value:.1f} must be greater than min {self.nema_config['min_position']:.1f}", error=True)
            return

        self.nema_config[key] = new_value
        self._nema_value_labels[key].setText(spec["fmt"].format(new_value))

        if key in ("min_position", "max_position"):
            self._apply_nema_limits()
            if not (self.nema_config["min_position"] <= self.nema_target <= self.nema_config["max_position"]):
                self._set_nema_target(self.nema_target, send=True)
                self.update_status(f"Target adjusted to new limit: {self.nema_target:.1f} cm", color=DIRTY_ORANGE)

        self.save_nema_config()

    def _apply_nema_limits(self):
        min_pos = self.nema_config["min_position"]
        max_pos = self.nema_config["max_position"]
        self.nema_slider.blockSignals(True)
        self.nema_slider.setRange(int(min_pos * 10), int(max_pos * 10))
        self.nema_slider.blockSignals(False)
        self.nema_min_label.setText(f"{min_pos:.1f}")
        self.nema_max_label.setText(f"{max_pos:.1f}")

    def _show_nema_current(self, position_cm: float):
        if hasattr(self, "nema_current_label"):
            self.nema_current_label.setText(f"{position_cm:.1f}")

    def _show_nema_enabled(self, enabled: bool):
        if not hasattr(self, "enable_btn"):
            return
        self.enable_btn.blockSignals(True)
        self.enable_btn.setChecked(enabled)
        self.enable_btn.setText("ENABLED" if enabled else "DISABLED")
        self.enable_btn.blockSignals(False)

    def _show_nema_sweep(self, sweeping: bool):
        if not hasattr(self, "nema_sweep_btn"):
            return
        self.nema_sweep_btn.blockSignals(True)
        self.nema_sweep_btn.setChecked(sweeping)
        self.nema_sweep_btn.setText("STOP SWEEP" if sweeping else "TEST SWEEP")
        self.nema_sweep_btn.blockSignals(False)

    def _show_nema_status_pill(self, disconnected: bool = False):
        green = theme_manager.get("green")
        red = theme_manager.get("red")
        if disconnected:
            text, color = "Disconnected", red
        elif self.nema_state is None:
            text, color = "Connecting...", DIRTY_ORANGE
        else:
            state = self.nema_state["state"]
            homed = self.nema_state["homed"]
            enabled = self.nema_state["enabled"]
            if state == "error":
                text, color = "Error", red
            else:
                text = f"{'Homed' if homed else 'Not homed'} · {'Enabled' if enabled else 'Disabled'}"
                if enabled and homed and state == "ready":
                    color = green
                elif enabled:
                    color = DIRTY_ORANGE
                else:
                    color = LABEL_GREY
        self.nema_status_pill.setText(text)
        self.nema_status_pill.setStyleSheet(
            f"color: {color}; background-color: {rgba(color, 0.15)}; border: none; "
            f"border-radius: 13px; padding: 0px 10px;")

    def on_enable_toggle(self, checked):
        """Enable button pressed"""
        self.enable_btn.setText("ENABLED" if checked else "DISABLED")
        self.enable_nema_stepper(checked)

    # ========================================
    # LAYOUT AND UI SETUP
    # ========================================

    def setup_layout(self):
        self._cards = []
        self._card_titles = []
        self._captions = []
        self._soft_labels = []
        self._plain_buttons = []
        self._step_buttons = []
        self._value_tiles = []

        root = QVBoxLayout()
        root.setContentsMargins(101, 40, 12, 6)
        root.setSpacing(0)

        content = QWidget()
        content.setFixedSize(CONTENT_WIDTH, CONTENT_HEIGHT)
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(CARD_GAP)

        cards = QHBoxLayout()
        cards.setSpacing(CARD_GAP)
        cards.addWidget(self._build_list_card())
        self.right_stack = QStackedWidget()
        self.right_stack.setFixedSize(EDIT_CARD_WIDTH, CARD_HEIGHT)
        self.right_stack.addWidget(self._build_editor_card())
        self.right_stack.addWidget(self._build_nema_control_card())
        cards.addWidget(self.right_stack)
        cards.addStretch(1)
        content_layout.addLayout(cards)
        content_layout.addLayout(self._build_bottom_bar())

        root.addWidget(content, 0, Qt.AlignmentFlag.AlignLeft)
        root.addStretch(1)
        self.setLayout(root)

        self._apply_styles()
        self._load_editor()
        self._update_controller_dots()

    def _make_card(self, width: int):
        card = QFrame()
        card.setObjectName(CARD_OBJECT_NAME)
        card.setFixedSize(width, CARD_HEIGHT)
        self._cards.append(card)
        return card

    def _card_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setFont(px_font(14, bold=True, spacing=1.5))
        self._card_titles.append(label)
        return label

    def _caption(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setFont(px_font(12, spacing=1.0))
        self._captions.append(label)
        return label

    def _step_button(self, direction: int, size: int = 44) -> StepButton:
        button = StepButton(direction, size)
        self._step_buttons.append(button)
        return button

    def _value_tile(self, width: int = None, height: int = 44, font_size: int = 22) -> QLabel:
        label = QLabel("---")
        label.setFont(px_font(font_size, bold=True, family="Consolas"))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if width:
            label.setFixedSize(width, height)
        self._value_tiles.append(label)
        return label

    def _build_list_card(self):
        card = self._make_card(LIST_CARD_WIDTH)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.selector_frame = QFrame()
        self.selector_frame.setObjectName("controller_selector")
        self.selector_frame.setFixedHeight(40)
        selector = QHBoxLayout(self.selector_frame)
        selector.setContentsMargins(3, 3, 3, 3)
        selector.setSpacing(3)
        self.maestro_group = QButtonGroup(self)
        self.maestro_group.setExclusive(True)
        self.controller_buttons = []
        for index, text in enumerate(("M1", "M2", "NEMA")):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setFixedHeight(32)
            button.setMinimumWidth(76)
            button.setFont(px_font(14, bold=True))
            button.setIconSize(QSize(10, 10))
            self.maestro_group.addButton(button, index)
            selector.addWidget(button)
            self.controller_buttons.append(button)
        self.controller_buttons[0].setChecked(True)
        self.maestro_group.idClicked.connect(self.on_maestro_changed)
        header.addWidget(self.selector_frame)

        self.channel_count_label = QLabel("")
        self.channel_count_label.setFont(px_font(13))
        self.channel_count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._captions.append(self.channel_count_label)
        header.addWidget(self.channel_count_label, 1)
        layout.addLayout(header)

        self.list_divider = QFrame()
        self.list_divider.setFixedHeight(1)
        layout.addWidget(self.list_divider)

        self.left_stack = QStackedWidget()
        self.channel_list = ChannelList()
        self.channel_list.setSpacing(LIST_ROW_SPACING // 2)
        self.channel_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.channel_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.channel_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.channel_list.currentRowChanged.connect(self._on_channel_row_changed)
        self.left_stack.addWidget(self.channel_list)
        self.left_stack.addWidget(self._build_nema_settings())
        layout.addWidget(self.left_stack, 1)
        return card

    def _build_nema_settings(self):
        self._nema_specs = {
            "lead_screw_pitch": {"label": "Lead screw pitch (mm)", "min": 1, "max": 20, "step": 1, "float": True, "fmt": "{:.0f}"},
            "lead_screw_length": {"label": "Lead screw length (cm)", "min": 10, "max": 50, "step": 1, "float": True, "fmt": "{:.0f}"},
            "homing_speed": {"label": "Homing speed (steps/s)", "min": 400, "max": 5000, "step": 100, "float": False, "fmt": "{}"},
            "normal_speed": {"label": "Normal speed (steps/s)", "min": 400, "max": 5000, "step": 100, "float": False, "fmt": "{}"},
            "acceleration": {"label": "Acceleration (steps/s²)", "min": 200, "max": 12000, "step": 100, "float": False, "fmt": "{}"},
            "min_position": {"label": "Min position (cm)", "min": 0, "max": 49, "step": 1, "float": True, "fmt": "{:.0f}"},
            "max_position": {"label": "Max position (cm)", "min": 1, "max": 50, "step": 1, "float": True, "fmt": "{:.0f}"},
        }
        self._nema_value_labels = {}

        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for key, spec in self._nema_specs.items():
            row = QHBoxLayout()
            row.setSpacing(6)
            label = QLabel(spec["label"])
            label.setFont(px_font(14))
            self._soft_labels.append(label)
            row.addWidget(label, 1)
            minus = self._step_button(-1, 42)
            minus.stepped.connect(lambda d, k=key: self._step_nema_setting(k, d))
            value = self._value_tile(92, 42, 17)
            value.setText(spec["fmt"].format(self.nema_config[key]))
            plus = self._step_button(1, 42)
            plus.stepped.connect(lambda d, k=key: self._step_nema_setting(k, d))
            row.addWidget(minus)
            row.addWidget(value)
            row.addWidget(plus)
            self._nema_value_labels[key] = value
            layout.addLayout(row)
        layout.addStretch(1)
        return widget

    def _build_editor_card(self):
        card = self._make_card(EDIT_CARD_WIDTH)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        self.editor_title = self._card_title("EDIT CHANNEL")
        header.addWidget(self.editor_title)
        header.addStretch(1)
        self.dirty_label = QLabel("Saved")
        self.dirty_label.setFont(px_font(13))
        header.addWidget(self.dirty_label)
        layout.addLayout(header)

        self.editor_body = QWidget()
        self.editor_body.setStyleSheet("background: transparent;")
        body = QVBoxLayout(self.editor_body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)

        # Name first, so it stays above the on-screen keyboard
        top = QHBoxLayout()
        top.setSpacing(14)
        name_col = QVBoxLayout()
        name_col.setSpacing(4)
        name_col.addWidget(self._caption("NAME"))
        self.name_edit = QLineEdit()
        self.name_edit.setFixedHeight(44)
        self.name_edit.setFont(px_font(18))
        self.name_edit.setMaxLength(25)
        self.name_edit.setPlaceholderText("Servo name")
        self.name_edit.textEdited.connect(self._on_name_edited)
        name_col.addWidget(self.name_edit)
        top.addLayout(name_col, 1)

        live_box = QHBoxLayout()
        live_box.setSpacing(10)
        self.live_label = QLabel("LIVE")
        self.live_label.setFont(px_font(15, bold=True))
        self.live_label.setFixedHeight(44)
        self.live_switch = ToggleSwitch()
        self.live_switch.toggled.connect(self._on_live_toggled)
        live_box.addWidget(self.live_label)
        live_box.addWidget(self.live_switch)
        top.addLayout(live_box)
        top.setAlignment(live_box, Qt.AlignmentFlag.AlignBottom)
        body.addLayout(top)

        # Position slider
        position = QVBoxLayout()
        position.setSpacing(6)
        readout_row = QHBoxLayout()
        readout_row.addWidget(self._caption("POSITION"))
        readout_row.addStretch(1)
        self.position_readout = QLabel("---")
        self.position_readout.setFont(px_font(22, bold=True, family="Consolas"))
        readout_row.addWidget(self.position_readout)
        position.addLayout(readout_row)
        self.position_slider = PositionSlider()
        self.position_slider.valueChanged.connect(self._on_slider_moved)
        position.addWidget(self.position_slider)
        range_row = QHBoxLayout()
        self.slider_min_label = QLabel("")
        self.slider_max_label = QLabel("")
        for label in (self.slider_min_label, self.slider_max_label):
            label.setFont(px_font(12, family="Consolas"))
            self._captions.append(label)
        range_row.addWidget(self.slider_min_label)
        range_row.addStretch(1)
        range_row.addWidget(self.slider_max_label)
        position.addLayout(range_row)
        body.addLayout(position)

        # Min / Home / Max tiles
        tiles = QGridLayout()
        tiles.setHorizontalSpacing(12)
        tiles.setVerticalSpacing(6)
        self.limit_values = {}
        self.capture_buttons = []
        self._tile_frames = []
        for col, (field, caption) in enumerate((("min", "MIN"), ("home", "HOME"), ("max", "MAX"))):
            tiles.addWidget(self._caption(caption), 0, col)
            frame = QFrame()
            frame.setObjectName("value_tile")
            frame.setFixedHeight(56)
            self._tile_frames.append(frame)
            row = QHBoxLayout(frame)
            row.setContentsMargins(6, 0, 6, 0)
            row.setSpacing(4)
            minus = self._step_button(-1)
            minus.stepped.connect(lambda d, f=field: self._step_limit(f, d * PULSE_STEP))
            value = QLabel("---")
            value.setFont(px_font(22, bold=True, family="Consolas"))
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            plus = self._step_button(1)
            plus.stepped.connect(lambda d, f=field: self._step_limit(f, d * PULSE_STEP))
            row.addWidget(minus)
            row.addWidget(value, 1)
            row.addWidget(plus)
            self.limit_values[field] = value
            tiles.addWidget(frame, 1, col)

            capture = QPushButton("SET FROM SLIDER")
            capture.setFixedHeight(34)
            capture.setFont(px_font(12, bold=True, spacing=0.5))
            capture.clicked.connect(lambda _, f=field: self._capture_from_slider(f))
            self.capture_buttons.append(capture)
            tiles.addWidget(capture, 2, col)
        for col in range(3):
            tiles.setColumnStretch(col, 1)
        body.addLayout(tiles)
        body.addStretch(1)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self.servo_hint = QLabel(f"D-pad ◀ ▶ nudges {PULSE_STEP} µs while Live")
        self.servo_hint.setFont(px_font(13))
        self._captions.append(self.servo_hint)
        bottom.addWidget(self.servo_hint)
        bottom.addStretch(1)
        self.sweep_btn = QPushButton("SWEEP TEST")
        self.sweep_btn.setCheckable(True)
        self.sweep_btn.setFixedSize(160, 44)
        self.sweep_btn.setFont(px_font(14, bold=True))
        self.sweep_btn.setIconSize(QSize(14, 14))
        self.sweep_btn.clicked.connect(self.toggle_selected_sweep)
        bottom.addWidget(self.sweep_btn)
        body.addLayout(bottom)

        layout.addWidget(self.editor_body, 1)
        return card

    def _build_nema_control_card(self):
        card = self._make_card(EDIT_CARD_WIDTH)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.addWidget(self._card_title("POSITION CONTROL"))
        header.addStretch(1)
        self.nema_status_pill = QLabel("Connecting...")
        self.nema_status_pill.setFont(px_font(13, bold=True))
        self.nema_status_pill.setFixedHeight(26)
        header.addWidget(self.nema_status_pill)
        layout.addLayout(header)

        self.nema_readout_frame = QFrame()
        self.nema_readout_frame.setObjectName("value_tile")
        self.nema_readout_frame.setFixedHeight(120)
        readout = QHBoxLayout(self.nema_readout_frame)
        readout.setSpacing(40)
        readout.addStretch(1)
        self.nema_current_label = self._nema_readout(readout, "CURRENT", primary=True)
        self.nema_readout_divider = QFrame()
        self.nema_readout_divider.setFixedSize(1, 70)
        readout.addWidget(self.nema_readout_divider)
        self.nema_target_label = self._nema_readout(readout, "TARGET", primary=False)
        readout.addStretch(1)
        layout.addWidget(self.nema_readout_frame)

        target = QVBoxLayout()
        target.setSpacing(6)
        target.addWidget(self._caption("TARGET POSITION"))
        self.nema_slider = PositionSlider()
        self.nema_slider.valueChanged.connect(self.update_nema_position)
        target.addWidget(self.nema_slider)
        range_row = QHBoxLayout()
        self.nema_min_label = QLabel("")
        self.nema_max_label = QLabel("")
        for label in (self.nema_min_label, self.nema_max_label):
            label.setFont(px_font(12, family="Consolas"))
            self._captions.append(label)
        range_row.addWidget(self.nema_min_label)
        range_row.addStretch(1)
        range_row.addWidget(self.nema_max_label)
        target.addLayout(range_row)
        layout.addLayout(target)
        layout.addStretch(1)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        hint = QLabel(f"D-pad ◀ ▶ nudges {NEMA_NUDGE_CM} cm")
        hint.setFont(px_font(13))
        self._captions.append(hint)
        bottom.addWidget(hint)
        bottom.addStretch(1)

        self.home_btn = QPushButton("HOME")
        self.home_btn.setFixedSize(110, 44)
        self.home_btn.setFont(px_font(14, bold=True))
        self.home_btn.clicked.connect(self.home_nema_stepper)
        self._plain_buttons.append(self.home_btn)
        bottom.addWidget(self.home_btn)

        self.enable_btn = QPushButton("DISABLED")
        self.enable_btn.setCheckable(True)
        self.enable_btn.setFixedSize(120, 44)
        self.enable_btn.setFont(px_font(14, bold=True))
        self.enable_btn.toggled.connect(self.on_enable_toggle)
        bottom.addWidget(self.enable_btn)

        self.nema_sweep_btn = QPushButton("TEST SWEEP")
        self.nema_sweep_btn.setCheckable(True)
        self.nema_sweep_btn.setFixedSize(150, 44)
        self.nema_sweep_btn.setFont(px_font(14, bold=True))
        self.nema_sweep_btn.setIconSize(QSize(14, 14))
        self.nema_sweep_btn.clicked.connect(self.toggle_nema_test_sweep)
        bottom.addWidget(self.nema_sweep_btn)
        layout.addLayout(bottom)

        self._apply_nema_limits()
        self._set_nema_target(self.nema_target, send=False)
        self.nema_current_label.setText(f"{self.nema_config['current_position']:.1f}")
        return card

    def _nema_readout(self, parent_layout, caption: str, primary: bool) -> QLabel:
        column = QVBoxLayout()
        column.setSpacing(4)
        cap = self._caption(caption)
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(cap)
        value_row = QHBoxLayout()
        value_row.setSpacing(4)
        value = QLabel("0.0")
        value.setFont(px_font(48, bold=True, family="Consolas"))
        unit = QLabel("cm")
        unit.setFont(px_font(22, family="Consolas"))
        unit.setAlignment(Qt.AlignmentFlag.AlignBottom)
        self._captions.append(unit)
        value_row.addWidget(value)
        value_row.addWidget(unit)
        column.addLayout(value_row)
        parent_layout.addLayout(column)
        if primary:
            self._nema_current_value = value
        else:
            self._nema_target_value = value
        return value

    def _build_bottom_bar(self):
        bar = QHBoxLayout()
        bar.setSpacing(12)

        self.refresh_btn = QPushButton("REFRESH")
        self.refresh_btn.setFixedSize(140, BAR_HEIGHT)
        self.refresh_btn.setToolTip("Resync settings from backend config")
        self.refresh_btn.clicked.connect(self.refresh_current)
        bar.addWidget(self.refresh_btn)

        self.read_btn = QPushButton("READ POSITIONS")
        self.read_btn.setFixedSize(180, BAR_HEIGHT)
        self.read_btn.setToolTip("Read current servo positions")
        self.read_btn.clicked.connect(self.read_all_positions_now)
        bar.addWidget(self.read_btn)

        self.go_home_btn = QPushButton("GO HOME")
        self.go_home_btn.setFixedSize(140, BAR_HEIGHT)
        self.go_home_btn.setToolTip("Move all servos to home positions")
        self.go_home_btn.clicked.connect(self.go_home_positions)
        bar.addWidget(self.go_home_btn)

        for button in (self.refresh_btn, self.read_btn, self.go_home_btn):
            button.setFont(px_font(15, bold=True))
            self._plain_buttons.append(button)

        self.status_label = QLabel("Initializing...")
        self.status_label.setFont(px_font(13))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setFixedHeight(BAR_HEIGHT)
        bar.addWidget(self.status_label, 1)

        self.save_btn = QPushButton("SAVE SETTINGS")
        self.save_btn.setFixedSize(180, BAR_HEIGHT)
        self.save_btn.setFont(px_font(15, bold=True))
        self.save_btn.setToolTip("Save min, max, home, and name settings")
        self.save_btn.clicked.connect(self.save_current)
        bar.addWidget(self.save_btn)
        return bar

    # ========================================
    # THEME HANDLING
    # ========================================

    def _apply_styles(self):
        primary = theme_manager.get("primary_color")
        green = theme_manager.get("green")

        for card in self._cards:
            card.setStyleSheet(card_style())
        for title in self._card_titles:
            title.setStyleSheet(f"color: {primary};")
        for caption in self._captions:
            caption.setStyleSheet(f"color: {LABEL_GREY}; background: transparent; border: none;")
        for label in self._soft_labels:
            label.setStyleSheet(f"color: {TEXT_SOFT}; background: transparent; border: none;")
        for button in self._plain_buttons:
            button.setStyleSheet(plain_button_style())
        for button in self._step_buttons:
            button.setStyleSheet(step_button_style())
        for tile in self._value_tiles:
            tile.setStyleSheet(
                f"color: white; background-color: {TILE_BG}; border: 1px solid #3a3a3a; border-radius: 8px;")
        tile_style = (f"QFrame#value_tile {{ background-color: {TILE_BG}; border: 1px solid #3a3a3a; "
                      f"border-radius: 8px; }} QLabel {{ background: transparent; border: none; color: white; }}")
        for frame in self._tile_frames + [self.nema_readout_frame]:
            frame.setStyleSheet(tile_style)
        for button in self.capture_buttons:
            button.setStyleSheet(capture_button_style())

        self.list_divider.setStyleSheet(f"background-color: {DIVIDER}; border: none;")
        self.nema_readout_divider.setStyleSheet("background-color: #3a3a3a; border: none;")
        self._nema_current_value.setStyleSheet(f"color: {primary};")
        self._nema_target_value.setStyleSheet("color: white;")
        self.selector_frame.setStyleSheet(
            "QFrame#controller_selector { background-color: #242424; border: 1px solid #3e3e3e; border-radius: 20px; }")
        for button in self.controller_buttons:
            button.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {TEXT_SOFT};
                    border: none;
                    border-radius: 16px;
                    padding: 0px 12px;
                }}
                QPushButton:checked {{
                    background-color: {primary};
                    color: #111111;
                }}
            """)

        self.name_edit.setStyleSheet(input_style())
        self.channel_list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item, QListWidget::item:selected, QListWidget::item:hover {{
                background: transparent;
                border: none;
                padding: 0px;
            }}
            QScrollBar:vertical {{
                background: #262626;
                width: 6px;
                border-radius: 3px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {primary};
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)

        self.refresh_btn.setStyleSheet(plain_button_style())
        self.save_btn.setStyleSheet(filled_button_style(green))
        self.sweep_btn.setStyleSheet(sweep_button_style())
        self.sweep_btn.setIcon(_play_icon("#111111"))
        self.nema_sweep_btn.setStyleSheet(sweep_button_style())
        self.nema_sweep_btn.setIcon(_play_icon("#111111"))
        self.enable_btn.setStyleSheet(toggle_button_style(green))

        self.position_slider.apply_style()
        self.nema_slider.apply_style()
        self.live_switch.update()
        self._update_live_label()
        for row in self.channel_rows:
            row._apply_style()
        self._update_dirty_label()
        self._update_controller_dots()
        self._show_nema_status_pill()
        self._update_position_readout()

    def _on_theme_changed(self):
        try:
            self._apply_styles()
            self.logger.info(f"Servo screen updated for theme: {theme_manager.get_theme_name()}")
        except Exception as e:
            self.logger.warning(f"Failed to apply theme changes: {e}")

    def _update_controller_dots(self):
        if not hasattr(self, "controller_buttons"):
            return
        green = theme_manager.get("green")
        red = theme_manager.get("red")
        for index, maestro_num in ((0, 1), (1, 2)):
            color = green if self.maestro_connected.get(maestro_num) else red
            self.controller_buttons[index].setIcon(_dot_icon(color))
        if self.nema_state is None:
            nema_color = LABEL_GREY
        elif self.nema_state.get("state") == "error":
            nema_color = red
        else:
            nema_color = green
        self.controller_buttons[2].setIcon(_dot_icon(nema_color))

    # ========================================
    # CONTROLLER MANAGEMENT
    # ========================================

    def on_maestro_changed(self, maestro_index: int):
        self.stop_all_sweeps()
        if self.position_update_timer.isActive():
            self.position_update_timer.stop()

        old_controller = self.current_controller
        if old_controller == 2:
            self.cleanup_nema_connection()

        self.current_controller = maestro_index
        self._set_live(False)

        if maestro_index < 2:
            self.current_maestro = maestro_index
            self.left_stack.setCurrentIndex(0)
            self.right_stack.setCurrentIndex(0)
            self._show_servo_bar(True)
            self.channel_count_label.setText("")
            self.clear_grid()

            maestro_num = maestro_index + 1
            if self.maestro_connected.get(maestro_num, False):
                channels = self.maestro_channel_counts.get(maestro_num, 0)
                self.update_status(f"Switched to Maestro {maestro_num}: {channels} channels")
                self.update_grid()
                QTimer.singleShot(200, self.read_all_positions_now)
            else:
                self.update_status(f"Loading Maestro {maestro_num}...")
                self.request_current_maestro_info()

            self.logger.info(f"Switched from controller {old_controller} to Maestro {maestro_num}")
        else:
            self.left_stack.setCurrentIndex(1)
            self.right_stack.setCurrentIndex(1)
            self._show_servo_bar(False)
            self.channel_count_label.setText("Stepper")
            self._set_nema_target(self.nema_config["current_position"], send=False)
            self._show_nema_status_pill()
            self.update_status("NEMA stepper controller selected")
            self.init_nema_connection()
            self.logger.info("Switched to NEMA controller")

    def _show_servo_bar(self, servo: bool):
        self.read_btn.setVisible(servo)
        self.go_home_btn.setVisible(servo)

    def clear_grid(self):
        """Clear the channel list"""
        self.channel_list.blockSignals(True)
        self.channel_list.clear()
        self.channel_list.blockSignals(False)
        self.channel_rows = []
        self.selected_channel = None
        self._load_editor()

    def check_websocket_and_detect(self):
        """Connection monitoring and first Maestro detection"""
        if not self.websocket or not self.websocket.is_connected():
            if self.current_controller == 2:
                self._show_nema_status_pill(disconnected=True)
            return

        if self.current_controller < 2:
            if not self.initial_detection_done:
                self.logger.info("WebSocket connected - triggering automatic maestro detection")
                self.detect_all_maestros()
                self.initial_detection_done = True
                self.ws_connection_timer.stop()
        else:
            if not hasattr(self, 'last_nema_status_request'):
                self.last_nema_status_request = 0
            current_time = time.time()
            if current_time - self.last_nema_status_request > 10:
                self.request_nema_status()
                self.last_nema_status_request = current_time

    def detect_all_maestros(self):
        """Detect both Maestro 1 and 2 automatically"""
        if not self.websocket or not self.websocket.is_connected():
            self.update_status("Cannot detect maestros: WebSocket not connected", error=True)
            return

        self.update_status("Auto-detecting maestro controllers...")
        for maestro_num in [1, 2]:
            if self.send_websocket_message("get_maestro_info", maestro=maestro_num):
                self.logger.info(f"Requested auto-detection for Maestro {maestro_num}")
            else:
                self.logger.warning(f"Failed to request info for Maestro {maestro_num}")

    def showEvent(self, event):
        """Trigger detection when the screen becomes visible"""
        super().showEvent(event)
        if (self.websocket and
                self.websocket.is_connected() and
                not self.initial_detection_done):
            self.logger.info("Servo screen shown - triggering maestro detection")
            QTimer.singleShot(500, self.detect_all_maestros)

    def safe_initialization(self):
        """Safe initialization that queries the selected Maestro"""
        try:
            self.update_status("Initializing servo configuration...")
            maestro_num = self.current_maestro + 1
            if (self.maestro_connected.get(maestro_num, False) and
                    self.maestro_channel_counts.get(maestro_num, 0) > 0):
                self.update_status(f"Using cached info for Maestro {maestro_num}")
                self.update_grid()
                QTimer.singleShot(300, self.read_all_positions_now)
            else:
                self.request_current_maestro_info()
        except Exception as e:
            self.logger.error(f"Initialization error: {e}")
            self.update_status(f"Initialization failed: {str(e)}", error=True)

    def request_current_maestro_info(self):
        """Maestro info request with retry"""
        maestro_num = self.current_maestro + 1
        self.update_status(f"Detecting Maestro {maestro_num} controller...")

        if not self.websocket or not self.websocket.is_connected():
            self.update_status("Cannot detect maestro: WebSocket not connected", error=True)
            if not self.ws_connection_timer.isActive():
                self.ws_connection_timer.start(2000)
            return

        if self.send_websocket_message("get_maestro_info", maestro=maestro_num):
            self.logger.info(f"Requested info for Maestro {maestro_num}")
            QTimer.singleShot(5000, self.check_detection_timeout)
        else:
            self.update_status("Failed to request Maestro info: WebSocket error", error=True)

    def refresh_current(self):
        """REFRESH: servo config from backend, or NEMA status"""
        if self.current_controller == 2:
            self.request_nema_status()
            self.update_status("Requesting NEMA status...")
        else:
            self.refresh_current_maestro()

    def refresh_current_maestro(self):
        """Request servo configuration from backend via WebSocket"""
        maestro_num = self.current_maestro + 1
        self.stop_all_sweeps()
        if self.position_update_timer.isActive():
            self.position_update_timer.stop()

        self.update_status(f"Requesting config from backend for Maestro {maestro_num}...")
        if not self.send_websocket_message("servo_request_config", maestro=maestro_num):
            self.logger.error("Failed to send config request to backend")
            self.update_status("Failed to request config from backend", error=True)

    def check_detection_timeout(self):
        """Retry detection if it timed out"""
        maestro_num = self.current_maestro + 1
        if not self.maestro_connected.get(maestro_num, False):
            self.logger.warning(f"Maestro {maestro_num} detection timed out, retrying...")
            self.request_current_maestro_info()

    def update_status_threadsafe(self, message: str, error: bool = False, warning: bool = False):
        """Thread-safe status update"""
        self.status_label.setText(message)
        if error:
            color = theme_manager.get("red")
        elif warning:
            color = theme_manager.get("primary_color")
        else:
            color = theme_manager.get("green")
        self.status_label.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        self.logger.info(f"Status: {message}")

    def update_status(self, message: str, error: bool = False, warning: bool = False, color: str = None):
        """Update status using Qt signal for thread safety"""
        if color:
            self.status_label.setText(message)
            self.status_label.setStyleSheet(f"color: {color}; background: transparent; border: none;")
            self.logger.info(f"Status: {message}")
        else:
            self.status_update_signal.emit(message, error, warning)

    # ========================================
    # CHANNEL LIST AND EDITOR
    # ========================================

    def _channel_key(self, channel: int) -> str:
        return f"m{self.current_maestro + 1}_ch{channel}"

    def _channel_config(self, channel_key: str) -> dict:
        return self.servo_config.get(channel_key, {})

    def update_grid(self):
        """Build the channel list for the selected Maestro"""
        maestro_num = self.current_maestro + 1
        channel_count = self.maestro_channel_counts.get(maestro_num, 0)

        if channel_count == 0:
            self.update_status(f"Maestro {maestro_num} not available", error=True)
            return

        self.logger.info(f"Building channel list for Maestro {maestro_num} with {channel_count} channels")
        previous = self.selected_channel
        self.stop_all_sweeps()

        self.channel_list.blockSignals(True)
        self.channel_list.clear()
        self.channel_rows = []
        width = self.channel_list.viewport().width()
        for channel in range(channel_count):
            item = QListWidgetItem()
            item.setSizeHint(QSize(width, LIST_ROW_HEIGHT))
            self.channel_list.addItem(item)
            row = ChannelRow(channel)
            self.channel_list.setItemWidget(item, row)
            self.channel_rows.append(row)
        self.channel_list.blockSignals(False)
        self._refresh_rows()

        self.channel_count_label.setText(f"{channel_count} channels")
        index = 0
        if previous and previous.startswith(f"m{maestro_num}_ch"):
            index = min(channel_count - 1, int(previous.split("_ch")[1]))
        self.selected_channel = None
        self._select_row(index)
        self._update_dirty_label()
        self.update_status(f"Maestro {maestro_num}: {channel_count} channels loaded")

    def _refresh_rows(self):
        for row in self.channel_rows:
            key = self._channel_key(row.channel)
            live = key == self.selected_channel and self.live_switch.isChecked()
            row.refresh(self._channel_config(key), self.channel_positions.get(key), live)

    def _refresh_row(self, channel_key: str):
        if not channel_key.startswith(f"m{self.current_maestro + 1}_ch"):
            return
        channel = int(channel_key.split("_ch")[1])
        if 0 <= channel < len(self.channel_rows):
            live = channel_key == self.selected_channel and self.live_switch.isChecked()
            self.channel_rows[channel].refresh(
                self._channel_config(channel_key), self.channel_positions.get(channel_key), live)

    def _select_row(self, index: int):
        self.channel_list.blockSignals(True)
        self.channel_list.setCurrentRow(index)
        self.channel_list.blockSignals(False)
        self._on_channel_row_changed(index)
        item = self.channel_list.item(index)
        if item is not None:
            self.channel_list.scrollToItem(item)

    def _on_channel_row_changed(self, index: int):
        if not (0 <= index < len(self.channel_rows)):
            return
        key = self._channel_key(self.channel_rows[index].channel)
        if key == self.selected_channel:
            return
        self.stop_all_sweeps()
        previous = self.selected_channel
        self.selected_channel = key
        self._set_live(False)
        if previous:
            self._refresh_row(previous)
        for i, row in enumerate(self.channel_rows):
            row.set_selected(i == index)
        self._load_editor()

    def _load_editor(self):
        """Show the selected channel in the editor"""
        key = self.selected_channel
        self._loading_editor = True
        try:
            self.editor_body.setEnabled(key is not None)
            if key is None:
                self.editor_title.setText("EDIT CHANNEL")
                self.name_edit.clear()
                for value in self.limit_values.values():
                    value.setText("---")
                self.slider_min_label.setText("")
                self.slider_max_label.setText("")
                self.position_slider.set_home_position(None)
                self._update_position_readout()
                return

            maestro_num, channel = key[1], key.split("_ch")[1]
            self.editor_title.setText(f"EDIT CHANNEL · M{maestro_num} CH {channel}")
            config = self._channel_config(key)
            self.name_edit.setText(config.get("name", ""))
            min_value = config.get("min", 992)
            max_value = config.get("max", 2000)
            home = config.get("home")
            self.limit_values["min"].setText(str(min_value))
            self.limit_values["max"].setText(str(max_value))
            self.limit_values["home"].setText(str(home if home is not None else (min_value + max_value) // 2))

            self.position_slider.blockSignals(True)
            self.position_slider.setRange(min_value, max_value)
            position = self.channel_positions.get(key)
            if position is None:
                position = home if home is not None else (min_value + max_value) // 2
            self.position_slider.setValue(position)
            self.position_slider.set_home_position(home)
            self.position_slider.blockSignals(False)
            self.slider_min_label.setText(str(min_value))
            self.slider_max_label.setText(str(max_value))
            self._show_sweep_state(key in self.active_sweeps)
            self._update_position_readout()
        finally:
            self._loading_editor = False
        self._update_dirty_label()

    def _update_position_readout(self, text: str = None, color: str = None):
        if self.selected_channel is None:
            self.position_readout.setText("---")
            self.position_readout.setStyleSheet(f"color: {LABEL_GREY};")
            return
        if text is None:
            text = f"{self.position_slider.value()} µs"
        if color is None:
            color = theme_manager.get("green") if self.live_switch.isChecked() else IDLE_GREY
        self.position_readout.setText(text)
        self.position_readout.setStyleSheet(f"color: {color};")

    def _set_live(self, live: bool):
        self.live_switch.blockSignals(True)
        self.live_switch.setChecked(live)
        self.live_switch.blockSignals(False)
        self.live_switch.update()
        self._apply_live_state()

    def _on_live_toggled(self, checked: bool):
        self._apply_live_state()
        if checked and self.selected_channel:
            self.update_status(f"Live: slider moves {self.selected_channel}")

    def _apply_live_state(self):
        live = self.live_switch.isChecked()
        self.position_slider.set_live(live)
        self._update_live_label()
        self._update_position_readout()
        if self.selected_channel:
            self._refresh_row(self.selected_channel)

    def _update_live_label(self):
        color = theme_manager.get("green") if self.live_switch.isChecked() else LABEL_GREY
        self.live_label.setStyleSheet(f"color: {color};")

    def _on_slider_moved(self, value: int):
        if self._loading_editor or self.selected_channel is None:
            return
        if self.live_switch.isChecked():
            self.update_servo_position(self.selected_channel, value)
            self.channel_positions[self.selected_channel] = value
            self._refresh_row(self.selected_channel)
        self._update_position_readout()

    def _on_name_edited(self, text: str):
        if self._loading_editor or self.selected_channel is None:
            return
        self._update_servo_config(self.selected_channel, "name", text)
        self._mark_dirty(self.selected_channel)

    def _limit_values(self, key: str):
        config = self._channel_config(key)
        min_value = config.get("min", 992)
        max_value = config.get("max", 2000)
        home = config.get("home")
        if home is None:
            home = (min_value + max_value) // 2
        return {"min": min_value, "max": max_value, "home": home}

    def _step_limit(self, field: str, delta: int):
        if self.selected_channel is None:
            return
        current = self._limit_values(self.selected_channel)[field]
        self._set_limit(field, current + delta)

    def _capture_from_slider(self, field: str):
        if self.selected_channel is None:
            return
        self._set_limit(field, self.position_slider.value())

    def _set_limit(self, field: str, value: int):
        """Validate and apply a new min / home / max for the selected channel"""
        key = self.selected_channel
        value = max(PULSE_MIN, min(PULSE_MAX, int(value)))
        limits = self._limit_values(key)
        if value == limits[field]:
            return

        if field == "min" and value >= limits["max"]:
            self.update_status(f"Min ({value}) must be less than Max ({limits['max']}) for {key}", error=True)
            return
        if field == "max" and value <= limits["min"]:
            self.update_status(f"Max ({value}) must be greater than Min ({limits['min']}) for {key}", error=True)
            return

        self._update_servo_config(key, field, value)
        self.limit_values[field].setText(str(value))
        if field == "min":
            self.position_slider.setMinimum(value)
            self.slider_min_label.setText(str(value))
        elif field == "max":
            self.position_slider.setMaximum(value)
            self.slider_max_label.setText(str(value))
        else:
            self.position_slider.set_home_position(value)
        self._mark_dirty(key)
        self.update_status("")

    def _mark_dirty(self, channel_key: str):
        self._dirty_channels.add(channel_key)
        self._refresh_row(channel_key)
        self._update_dirty_label()

    def _update_dirty_label(self):
        prefix = f"m{self.current_maestro + 1}_"
        dirty = any(k.startswith(prefix) for k in self._dirty_channels)
        self.dirty_label.setText("Unsaved changes" if dirty else "Saved")
        self.dirty_label.setStyleSheet(f"color: {DIRTY_ORANGE if dirty else LABEL_GREY};")

    def _update_servo_config(self, channel_key: str, field: str, value):
        """Update a servo configuration field; saved with SAVE SETTINGS"""
        if channel_key not in self.servo_config:
            self.servo_config[channel_key] = {}
        self.servo_config[channel_key][field] = value

    # ========================================
    # POSITION UPDATES AND SERVO CONTROL
    # ========================================

    def read_all_positions_now(self):
        """Read all servo positions for the selected Maestro"""
        if self.reading_positions:
            self.logger.debug("Already reading positions, skipping...")
            return

        maestro_num = self.current_maestro + 1
        if not self.maestro_connected.get(maestro_num, False):
            self.update_status(f"Maestro {maestro_num} not connected", error=True)
            return

        self.reading_positions = True
        self.position_read_timeout.start(3000)

        if self.send_websocket_message("get_all_servo_positions", maestro=maestro_num):
            self.update_status(f"Reading positions from Maestro {maestro_num}...")
            self.logger.info(f"Requested all positions from Maestro {maestro_num}")
        else:
            self.reading_positions = False
            self.position_read_timeout.stop()
            self.update_status("Failed to send position request: WebSocket not connected", error=True)

    def handle_position_read_timeout(self):
        """Handle timeout when reading positions"""
        self.reading_positions = False
        maestro_num = self.current_maestro + 1
        self.logger.warning(f"Timeout reading positions from Maestro {maestro_num}")
        self.update_status(f"Maestro {maestro_num} not responding - check connection", error=True)

    def update_servo_position_display(self, channel_key: str, position: int):
        """Show a position reported by the backend"""
        self.channel_positions[channel_key] = position
        self._refresh_row(channel_key)
        if channel_key == self.selected_channel:
            self.position_slider.blockSignals(True)
            self.position_slider.setValue(position)
            self.position_slider.blockSignals(False)
            if channel_key not in self.active_sweeps:
                self._update_position_readout()
        self.logger.debug(f"Updated display: {channel_key} = {position}")

    def update_servo_position(self, channel_key: str, value: int):
        """Send servo position command with its speed and acceleration"""
        config = self.servo_config.get(channel_key, {})
        speed = config.get("speed", 0)
        accel = config.get("accel", 0)

        self.send_websocket_message("servo_speed", channel=channel_key, speed=speed)
        self.send_websocket_message("servo_acceleration", channel=channel_key, acceleration=accel)
        self.send_websocket_message("servo", channel=channel_key, pos=value)

        self.logger.debug(f"Servo command: {channel_key} -> {value} (speed: {speed}, accel: {accel})")

    def save_current(self):
        """SAVE SETTINGS for the selected controller"""
        if self.current_controller == 2:
            if self.save_nema_config():
                self.update_status("NEMA settings saved", color=theme_manager.get("green"))
        else:
            self.save_all_settings()

    def save_all_settings(self):
        """Save min, max, home and name for every channel of the selected Maestro"""
        maestro_num = self.current_maestro + 1

        if not self.maestro_connected.get(maestro_num, False):
            self.update_status(f"Maestro {maestro_num} not connected", error=True)
            return

        channels_config = {}
        for channel in range(self.maestro_channel_counts.get(maestro_num, 0)):
            key = f"m{maestro_num}_ch{channel}"
            limits = self._limit_values(key)
            if limits["min"] >= limits["max"]:
                self.update_status(f"Cannot save: Min >= Max for {key}", error=True)
                return
            name = self._channel_config(key).get("name", "")
            if key not in self.servo_config:
                self.servo_config[key] = {}
            self.servo_config[key].update({"min": limits["min"], "max": limits["max"],
                                           "home": limits["home"], "name": name})
            channels_config[channel] = {"min": limits["min"], "max": limits["max"],
                                        "home": limits["home"], "name": name}

        if config_manager.save_config(SERVO_CONFIG_PATH, self.servo_config):
            self.send_websocket_message("servo_save_settings",
                                        maestro=maestro_num,
                                        channels=channels_config)
            prefix = f"m{maestro_num}_"
            self._dirty_channels = {k for k in self._dirty_channels if not k.startswith(prefix)}
            self._update_dirty_label()
            self.update_status(f"Saved settings for {len(channels_config)} servos")
        else:
            self.update_status("Failed to save settings", error=True)

    def go_home_positions(self):
        """Move all servos of the selected Maestro to their home positions"""
        maestro_num = self.current_maestro + 1

        if not self.maestro_connected.get(maestro_num, False):
            self.update_status(f"Maestro {maestro_num} not connected", error=True)
            return

        home_count = 0
        for channel in range(self.maestro_channel_counts.get(maestro_num, 0)):
            key = f"m{maestro_num}_ch{channel}"
            config = self.servo_config.get(key, {})
            home_pos = config.get("home")
            if home_pos is None:
                continue
            self.update_servo_position(key, home_pos)
            self.channel_positions[key] = home_pos
            home_count += 1

        if home_count > 0:
            self._refresh_rows()
            if self.selected_channel:
                self._load_editor()
            self.update_status(f"Moving {home_count} servos to home positions")
            self.logger.info(f"Sent {home_count} servos to home positions")
            self.send_websocket_message("servo_home_positions",
                                        maestro=maestro_num,
                                        home_positions=self.get_maestro_home_positions(maestro_num))
        else:
            self.update_status("No home positions set", warning=True)

    def get_maestro_home_positions(self, maestro_num: int) -> dict:
        """Get home positions for specific maestro"""
        home_positions = {}
        for channel_key, config in self.servo_config.items():
            if channel_key.startswith(f"m{maestro_num}_") and "home" in config:
                channel = int(channel_key.split("_ch")[1])
                home_positions[channel] = config["home"]
        return home_positions

    def toggle_selected_sweep(self):
        """SWEEP TEST for the selected channel"""
        key = self.selected_channel
        if key is None:
            self._show_sweep_state(False)
            return
        if key in self.active_sweeps:
            self.active_sweeps[key].stop()
            del self.active_sweeps[key]
            self.logger.info(f"Stopped sweep for {key}")
            return

        limits = self._limit_values(key)
        speed = self.servo_config.get(key, {}).get("speed", 0)
        self.logger.info(f"Starting sweep for {key}: min={limits['min']}, max={limits['max']}, speed={speed}")
        self.active_sweeps[key] = MinMaxSweep(self, key, limits["min"], limits["max"], speed)
        self._show_sweep_state(True)

    def _show_sweep_state(self, sweeping: bool):
        self.sweep_btn.blockSignals(True)
        self.sweep_btn.setChecked(sweeping)
        self.sweep_btn.setText("STOP SWEEP" if sweeping else "SWEEP TEST")
        self.sweep_btn.blockSignals(False)

    def sweep_display(self, channel_key: str, text: str, color: str):
        """Sweep progress shown in the position readout"""
        if channel_key == self.selected_channel:
            self._update_position_readout(text, color)

    def sweep_stopped(self, channel_key: str, center: int):
        self.channel_positions[channel_key] = center
        self._refresh_row(channel_key)
        if channel_key == self.selected_channel:
            self._show_sweep_state(False)
            self.position_slider.blockSignals(True)
            self.position_slider.setValue(center)
            self.position_slider.blockSignals(False)
            self._update_position_readout()

    def stop_all_sweeps(self):
        """Stop any active sweeps"""
        for channel_key, sweep in list(self.active_sweeps.items()):
            sweep.stop()
        self.active_sweeps.clear()
        if hasattr(self, "sweep_btn"):
            self._show_sweep_state(False)

    def stop_all_operations(self):
        """Stop all servo operations for cleanup"""
        self.stop_all_sweeps()
        if self.position_update_timer.isActive():
            self.position_update_timer.stop()

    # ========================================
    # CLEANUP METHODS
    # ========================================

    def cleanup(self):
        """Stop timers, sweeps and NEMA polling"""
        if self.nema_test_sweeping:
            self.send_websocket_message("nema_stop_sweep")
        self.position_update_timer.stop()
        if hasattr(self, 'nema_status_timer'):
            self.nema_status_timer.stop()
        if self.current_controller == 2:
            self.cleanup_nema_connection()
        self.stop_all_operations()
        if hasattr(self, 'ws_connection_timer'):
            self.ws_connection_timer.stop()
        self.logger.info("Servo screen cleanup completed")


class MinMaxSweep:
    """Min/Max sweep controller for automated servo testing"""

    def __init__(self, parent_screen, channel_key: str, minv: int, maxv: int, speedv: int):
        self.logger = parent_screen.logger
        self.parent_screen = parent_screen
        self.channel_key = channel_key
        self.min_val = minv
        self.max_val = maxv
        self.speed = speedv

        self.current_target = None
        self.going_to_max = True
        self.check_interval = 100
        self.hold_delay = 1000

        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.check_position)

        self.hold_timer = QTimer()
        self.hold_timer.setSingleShot(True)
        self.hold_timer.timeout.connect(self.continue_after_hold)

        self.start_sweep()
        self.logger.info(f"Starting min/max sweep on {channel_key}: {minv}->{maxv}, speed={speedv}")

    def start_sweep(self):
        """Configure the servo and move to the first target"""
        if self.speed >= 0:
            self.parent_screen.send_websocket_message("servo_speed", channel=self.channel_key, speed=self.speed)

        config = self.parent_screen.servo_config.get(self.channel_key, {})
        accel = config.get("accel", 0)
        if accel >= 0:
            self.parent_screen.send_websocket_message("servo_acceleration", channel=self.channel_key, acceleration=accel)

        self.move_to_next_target()
        self.check_timer.start(self.check_interval)

    def move_to_next_target(self):
        """Move to the next target position"""
        self.current_target = self.max_val if self.going_to_max else self.min_val
        self.logger.debug(f"{self.channel_key} -> {'MAX' if self.going_to_max else 'MIN'} ({self.current_target})")
        self.parent_screen.send_websocket_message("servo", channel=self.channel_key, pos=self.current_target)
        self.parent_screen.sweep_display(self.channel_key, f"-> {self.current_target} µs",
                                         theme_manager.get("primary_color"))

    def check_position(self):
        """Request current position for sweep validation"""
        self.parent_screen.send_websocket_message("get_servo_position", channel=self.channel_key)

    def position_reached(self, actual_position: int):
        """Called when position update received"""
        if self.current_target is None:
            return

        if actual_position == self.current_target:
            self.logger.debug(f"{self.channel_key} reached {self.current_target} precisely")
            self.parent_screen.sweep_display(self.channel_key, f"@ {actual_position} µs",
                                             theme_manager.get("green"))
            self.check_timer.stop()
            self.hold_timer.start(self.hold_delay)
        else:
            self.parent_screen.sweep_display(self.channel_key, f"{actual_position} µs",
                                             theme_manager.get("primary_light"))
            self.logger.debug(f"{self.channel_key}: {actual_position}/{self.current_target}")

    def continue_after_hold(self):
        """Continue sweep after hold delay"""
        self.going_to_max = not self.going_to_max
        self.move_to_next_target()
        self.check_timer.start(self.check_interval)

    def stop(self):
        """Stop the sweep and return to center"""
        self.check_timer.stop()
        self.hold_timer.stop()
        center_pos = (self.min_val + self.max_val) // 2
        self.parent_screen.send_websocket_message("servo", channel=self.channel_key, pos=center_pos)
        self.parent_screen.sweep_stopped(self.channel_key, center_pos)