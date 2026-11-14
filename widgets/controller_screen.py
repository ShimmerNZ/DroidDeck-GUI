#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - Controller Configuration Screen
Mapping list on the left, editor for the selected mapping on the right.
Controller input is processed by the backend; this screen edits the mapping
config and runs system actions (exit / restart) the backend routes back here.
"""

import os
import time
from typing import Optional, Dict, Any
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QFrame,
    QGridLayout, QComboBox, QSlider, QScrollArea, QListWidget,
    QListWidgetItem, QListView, QButtonGroup, QSizePolicy, QAbstractButton, QApplication
)
from PyQt6.QtGui import QFont, QColor, QPainter
from PyQt6.QtCore import Qt, QTimer, QSize, QRectF, pyqtSignal

from widgets.base_screen import BaseScreen
from widgets.flow_dialog import show_message, ask_confirm
from core.config_manager import config_manager
from core.theme_manager import theme_manager
from core.utils import error_boundary
from core.restart import prepare_restart
from widgets.controller_status_splash import show_controller_status_splash

CONTROLLER_CONFIG_PATH = "resources/configs/controller_config.json"
SERVO_CONFIG_PATH = "resources/configs/servo_config.json"

# Layout - matches the Health screen card positions
CONTENT_WIDTH = 1061
CONTENT_HEIGHT = 490
CARD_GAP = 12
CARD_HEIGHT = 434
LIST_CARD_WIDTH = 480
EDIT_CARD_WIDTH = 569
BAR_HEIGHT = 44
LIST_ROW_HEIGHT = 40
LIST_ROW_SPACING = 4

CARD_OBJECT_NAME = "controller_card"

PULSE_STEP = 10
LONG_PRESS_MULTIPLIER = 5
JOYSTICK_BEHAVIORS = ("joystick_pair", "differential_tracks")
MAX_IMU_SERVOS = 2

# Fixed colours shared by every theme
LABEL_GREY = "#9e9e9e"
TEXT_SOFT = "#d6d6d6"
TILE_BG = "#202020"
ROW_BG = "#1f1f1f"
DIVIDER = "#2e2e2e"
DIRTY_ORANGE = "#ff9800"
CONFLICT_RED = "#cc4444"

# Display names (saved config keys are unchanged)
INPUT_NAMES = {
    "left_stick_x": "Left stick X", "left_stick_y": "Left stick Y",
    "right_stick_x": "Right stick X", "right_stick_y": "Right stick Y",
    "left_trigger": "L2 trigger", "right_trigger": "R2 trigger",
    "imu_roll": "IMU roll", "imu_pitch": "IMU pitch",
    "button_a": "A button", "button_b": "B button",
    "button_x": "X button", "button_y": "Y button",
    "shoulder_left": "L1 bumper", "shoulder_right": "R1 bumper",
    "button_menu": "Menu button",
    "left_trigger_btn": "L2 full press", "right_trigger_btn": "R2 full press",
    "stick_left_click": "L3 stick click", "stick_right_click": "R3 stick click",
    "grip_left_upper": "L4 grip", "grip_left_lower": "L5 grip",
    "grip_right_upper": "R4 grip", "grip_right_lower": "R5 grip",
    "button_left_pad": "Left pad click", "button_right_pad": "Right pad click",
    "dpad_up": "D-pad up", "dpad_down": "D-pad down",
    "dpad_left": "D-pad left", "dpad_right": "D-pad right",
}

BEHAVIOR_TAGS = {
    "direct_servo": "Servo", "multi_servo": "Multi servo", "toggle_servo": "Toggle servo",
    "joystick_pair": "Joystick pair", "differential_tracks": "Tracks",
    "scene_trigger": "Scene", "toggle_scenes": "Toggle scenes",
    "nema_stepper": "NEMA stepper", "system_control": "System",
    "imu_tilt": "IMU tilt", "imu_toggle": "IMU on/off",
}

BEHAVIOR_NAMES = {
    "direct_servo": "Servo (direct)", "multi_servo": "Multi servo",
    "toggle_servo": "Toggle servo", "joystick_pair": "Joystick pair",
    "differential_tracks": "Tracks (differential)", "scene_trigger": "Scene trigger",
    "toggle_scenes": "Toggle scenes", "nema_stepper": "NEMA stepper",
    "system_control": "System control", "imu_tilt": "IMU tilt", "imu_toggle": "IMU on/off",
}

NEMA_MODES = {
    "toggle_positions": "Toggle positions",
    "sweep_continuous": "Sweep continuously",
    "direct_control": "Direct control",
}

SYSTEM_ACTIONS = {
    "up": "Navigate up", "down": "Navigate down", "left": "Navigate left",
    "right": "Navigate right", "select": "Select", "exit": "Exit",
    "exit_app": "Exit app", "restart_app": "Restart app",
    "restart_pi": "Restart Pi", "shutdown_pi": "Shut down Pi",
}

SYSTEM_DESCRIPTIONS = {
    "up": "Navigate up in menus",
    "down": "Navigate down in menus",
    "left": "Navigate left in menus",
    "right": "Navigate right in menus",
    "select": "Select/confirm in menus",
    "exit_app": "Close app",
    "restart_pi": "Reboot the Raspberry Pi",
    "shutdown_pi": "Shutdown the Raspberry Pi",
}

FILTERS = ["All", "Sticks & triggers", "Buttons", "D-pad", "IMU"]


def input_display_name(control: str) -> str:
    if not control:
        return "Not set"
    return INPUT_NAMES.get(control, control.replace("_", " ").capitalize())


def input_group(control: str) -> str:
    if control.startswith("imu_"):
        return "IMU"
    if control.startswith("dpad_"):
        return "D-pad"
    if control.endswith("_x") or control.endswith("_y") or control in ("left_trigger", "right_trigger"):
        return "Sticks & triggers"
    return "Buttons"


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
    """


def outline_button_style(color: str, text: str) -> str:
    return f"""
        QPushButton {{
            background: transparent;
            color: {text};
            border: 1px solid {color};
            border-radius: 8px;
        }}
        QPushButton:pressed {{
            background-color: {rgba(color, 0.3)};
        }}
        QPushButton:disabled {{
            color: #555;
            border-color: #3a3a3a;
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
    """


def combo_style() -> str:
    primary = theme_manager.get("primary_color")
    return f"""
        QComboBox {{
            background-color: {TILE_BG};
            border: 1px solid #555;
            border-radius: 8px;
            padding: 0px 12px;
            color: white;
        }}
        QComboBox:focus, QComboBox:on {{
            border-color: {primary};
        }}
        QComboBox:disabled {{
            color: #666;
            border-color: #3a3a3a;
        }}
        QComboBox::drop-down {{
            border: none;
            width: 28px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {TILE_BG};
            color: white;
            border: 1px solid #555;
            outline: none;
            selection-background-color: {primary};
            selection-color: #111111;
        }}
        QComboBox QAbstractItemView::item {{
            min-height: 38px;
            padding: 0px 10px;
        }}
    """


def scroll_style() -> str:
    primary = theme_manager.get("primary_color")
    return f"""
        QScrollArea, QListWidget {{
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
    """


# ========================================
# BEHAVIOR HANDLER CLASSES
# ========================================

class BehaviorHandler:
    """Base class for all behavior handlers"""

    def __init__(self, websocket_sender=None, logger=None):
        self.websocket_sender = websocket_sender
        self.logger = logger

    def process(self, control_name: str, raw_value: float, config: Dict[str, Any]) -> bool:
        """Process controller input with behavior-specific logic"""
        raise NotImplementedError

    def send_websocket_message(self, message_type: str, **kwargs):
        """Helper to send websocket messages"""
        if self.websocket_sender:
            self.websocket_sender(message_type, **kwargs)


class SystemControlHandler(BehaviorHandler):
    """Handle system control commands - exit app, restart, shutdown"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app_instance = None

    def set_app_instance(self, app_instance):
        """Set reference to the main application for direct exit handling"""
        self.app_instance = app_instance

    def process(self, control_name: str, raw_value: float, config: Dict[str, Any]) -> bool:
        try:
            action = config.get('system_action')
            trigger_timing = config.get('trigger_timing', 'on_press')
            threshold = 0.5
            
            if not action:
                return False
            
            if trigger_timing == 'on_press' and raw_value > threshold:
                if action == "exit_app":
                    self._handle_exit_app()
                    if self.logger:
                        self.logger.info("Exit app command triggered")
                elif action == "restart_app":
                    self._handle_restart_app()
                    if self.logger:
                        self.logger.info("Restart app command triggered")
                elif action == "restart_pi":
                    self.send_websocket_message("pi_control", action="restart")
                    if self.logger:
                        self.logger.info("Restart Pi command sent to backend")
                elif action == "shutdown_pi":
                    self.send_websocket_message("pi_control", action="shutdown")
                    if self.logger:
                        self.logger.info("Shutdown Pi command sent to backend")
                
                return True
                
            return False
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error in system control handler: {e}")
            return False

    def _find_main_window(self):
        app = QApplication.instance()
        for widget in app.topLevelWidgets():
            if hasattr(widget, 'close_application'):
                return widget
        return None

    def _handle_exit_app(self):
        """Confirm, then close the app through the normal shutdown"""
        try:
            from widgets.flow_dialog import FlowDialog

            main_window = self._find_main_window()
            dialog = FlowDialog(main_window, "DROIDDECK", "Menu button", width=520)
            dialog.show_confirm("Exit DroidDeck?",
                                "DroidDeck saves, disconnects from WALL-E and closes.",
                                primary="EXIT", primary_fill=theme_manager.get("red"))

            if dialog.exec() == QDialog.DialogCode.Accepted:
                if self.logger:
                    self.logger.info("User confirmed app exit via controller")
                if main_window is not None:
                    QTimer.singleShot(100, main_window.close_application)
                else:
                    QTimer.singleShot(100, QApplication.instance().quit)
            else:
                if self.logger:
                    self.logger.info("User cancelled app exit")

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error handling exit app: {e}")
                import sys
                sys.exit(0)

    def _handle_restart_app(self):
        """Confirm, then close cleanly; the app is relaunched once shutdown finishes"""
        try:
            from widgets.flow_dialog import FlowDialog

            main_window = self._find_main_window()
            dialog = FlowDialog(main_window, "DROIDDECK", "Menu button", width=520)
            dialog.show_confirm("Restart DroidDeck?",
                                "The app closes and opens again straight away.",
                                primary="RESTART")

            if dialog.exec() != QDialog.DialogCode.Accepted:
                if self.logger:
                    self.logger.info("User cancelled app restart")
                return

            if self.logger:
                self.logger.info("User confirmed app restart via controller")

            prepare_restart()
            if main_window is not None:
                QTimer.singleShot(100, main_window.close)
            else:
                QTimer.singleShot(100, QApplication.instance().quit)

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error handling restart app: {e}")

# ========================================
# BEHAVIOR REGISTRY
# ========================================

class BehaviorHandlerRegistry:
    """Runs the system actions the backend routes to the frontend"""

    def __init__(self, websocket_sender=None, logger=None, app_instance=None):
        system_handler = SystemControlHandler(websocket_sender, logger)
        if app_instance:
            system_handler.set_app_instance(app_instance)
        self.handlers = {"system_control": system_handler}
        self.logger = logger

    def process_input(self, control_name: str, raw_value: float, mapping_config: Dict[str, Any]) -> bool:
        """Process an input through the matching handler"""
        behavior = mapping_config.get('behavior')
        if behavior not in self.handlers:
            return False
        return self.handlers[behavior].process(control_name, raw_value, mapping_config)


# ========================================
# WIDGETS
# ========================================

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
        self.setFont(px_font(22 if size >= 44 else 18, bold=True))
        self.setAccessibleName("Decrease" if direction < 0 else "Increase")
        self.setStyleSheet(step_button_style())
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


class MappingRow(QFrame):
    """One mapping in the list: input, behaviour tag, target summary"""

    def __init__(self):
        super().__init__()
        self.setObjectName("mapping_row")
        self.setFixedHeight(LIST_ROW_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)
        self.marker = QFrame()
        self.marker.setFixedSize(4, 18)
        self.input_label = QLabel()
        self.input_label.setFont(px_font(15))
        self.input_label.setFixedWidth(132)
        self.tag_label = QLabel()
        self.tag_label.setFont(px_font(11, bold=True))
        self.tag_label.setFixedHeight(22)
        self.target_label = QLabel()
        self.target_label.setFont(px_font(13))
        self.target_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.target_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.marker)
        layout.addWidget(self.input_label)
        layout.addWidget(self.tag_label)
        layout.addWidget(self.target_label, 1)
        self._selected = False
        self._conflict = False

    def set_content(self, input_text: str, tag: str, target: str, conflict: bool):
        self.input_label.setText(input_text)
        self.tag_label.setText(tag)
        self.tag_label.setVisible(bool(tag))
        self.target_label.setText(target)
        self._conflict = conflict
        self._apply_style()

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style()

    def _apply_style(self):
        primary = theme_manager.get("primary_color")
        if self._selected:
            background, border = rgba(primary, 0.14), f"1px solid {primary}"
        elif self._conflict:
            background, border = ROW_BG, f"1px solid {rgba(CONFLICT_RED, 0.6)}"
        else:
            background, border = ROW_BG, "1px solid transparent"
        self.setStyleSheet(f"""
            QFrame#mapping_row {{
                background-color: {background};
                border: {border};
                border-radius: 10px;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)
        if self._conflict:
            marker = CONFLICT_RED
        else:
            marker = primary if self._selected else "transparent"
        self.marker.setStyleSheet(f"background-color: {marker}; border: none; border-radius: 2px;")
        self.input_label.setStyleSheet(f"color: {'white' if self._selected else TEXT_SOFT};")
        self.tag_label.setStyleSheet(
            f"color: {TEXT_SOFT}; background-color: #2a2a2a; border-radius: 11px; padding: 0px 8px;")
        self.target_label.setStyleSheet("color: #bdbdbd;")


class MappingList(QListWidget):
    """Mapping list whose rows always span the full list width"""

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = self.viewport().width()
        for i in range(self.count()):
            self.item(i).setSizeHint(QSize(width, LIST_ROW_HEIGHT))


# ========================================
# MAIN CONTROLLER CONFIGURATION CLASS
# ========================================

class ControllerConfigScreen(BaseScreen):
    """Controller mapping configuration"""

    calibration_update = pyqtSignal(str, float)

    def __init__(self, websocket=None):
        self.behavior_registry = None
        self.mapping_rows = []
        self.selected_row_index = None
        self.controller_status_label = None

        self.maestro_channel_counts = {1: 0, 2: 0}
        self.maestro_connected = {1: False, 2: False}
        self._config_loaded = False
        self._loading_config = False

        super().__init__(websocket)
        theme_manager.register_callback(self.update_theme)

    def _detect_maestros(self):
        """Request maestro detection and controller config from backend"""
        if self.websocket and self.websocket.is_connected():
            self.send_websocket_message("get_maestro_info", maestro=1)
            self.send_websocket_message("get_maestro_info", maestro=2)
            self.send_websocket_message("get_controller_config")
            self.request_controller_info()
            self.logger.info("Requesting maestro detection and controller config from backend")
        else:
            self.logger.warning("WebSocket not connected - loading config from local file")
            QTimer.singleShot(2000, self._load_existing_configuration)
            return

        QTimer.singleShot(4000, self._ensure_config_loaded)

    def _ensure_config_loaded(self):
        """Load config with fallback channels if maestro info never arrived"""
        if not self._config_loaded:
            self.logger.warning("Maestro info not received - loading config with fallback channels")
            self._config_loaded = True
            self._load_existing_configuration()

    def _on_controller_config_data(self, msg: dict):
        """Apply controller config received from the backend"""
        try:
            self._load_config_from_backend_response(msg.get("config", {}))
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error applying controller config: {e}", exc_info=True)

    def _on_controller_config_saved(self, msg: dict):
        """Config was just saved - request it back so steamdeck.py
        picks up any imu_toggle mapping changes without a restart."""
        try:
            if msg.get("success"):
                self._suppress_grid_reload = True
                self.send_websocket_message("get_controller_config")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error handling config saved: {e}", exc_info=True)

    def _handle_system_control_command(self, msg):
        """Handle system control commands routed from backend"""
        try:
            action = msg.get("action")
            control_name = msg.get("control_name")
            config = msg.get("config", {})

            if not action:
                self.logger.warning("System control command missing action")
                return

            self.logger.info(f"Received system control command from backend: {action}")

            mapping_config = {
                'behavior': 'system_control',
                'system_action': action,
                **config
            }

            success = self.behavior_registry.process_input(control_name, 1.0, mapping_config)

            if success:
                self.logger.info(f"System control '{action}' executed successfully")
            else:
                self.logger.warning(f"System control '{action}' failed to execute")

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error handling system control command: {e}")

    def open_controller_status(self):
        """Open controller status display splash"""
        try:
            from PyQt6.QtWidgets import QApplication

            self.controller_status_splash = show_controller_status_splash(self)

            app = QApplication.instance()
            main_window = None
            for widget in app.topLevelWidgets():
                if hasattr(widget, 'controller_thread'):
                    main_window = widget
                    break

            if main_window and hasattr(main_window, 'controller_thread'):
                controller_thread = main_window.controller_thread

                try:
                    controller_thread.controller_input.disconnect(self.controller_status_splash.update_controller_input)
                except Exception:
                    pass
                try:
                    controller_thread.controller_connected.disconnect()
                except Exception:
                    pass
                try:
                    controller_thread.controller_disconnected.disconnect()
                except Exception:
                    pass

                controller_thread.controller_input.connect(
                    self.controller_status_splash.update_controller_input
                )
                controller_thread.controller_connected.connect(
                    lambda name, id: self.controller_status_splash.set_controller_info(name, True)
                )
                controller_thread.controller_disconnected.connect(
                    lambda reason: self.controller_status_splash.set_controller_info(f"Disconnected: {reason}", False)
                )

                controller_info = controller_thread.get_controller_info()
                self.controller_status_splash.set_controller_info(
                    controller_info.get("controller_name", "Steam Deck Controller"),
                    controller_info.get("connected", False)
                )

                self.logger.info("Controller status splash connected to controller thread")
            else:
                self.logger.warning("No controller thread available for status display")
                self.controller_status_splash.set_controller_info("No Controller Thread", False)

        except Exception as e:
            self.logger.error(f"Failed to open controller status splash: {e}")

    def handle_controller_input_signal(self, input_data):
        """Controller input from the controller thread (thread-safe)"""
        try:
            self._show_controller_state("Connected & Active", True)
            if (hasattr(self, 'controller_status_splash') and self.controller_status_splash
                    and self.controller_status_splash.isVisible()):
                self.controller_status_splash.update_controller_input(input_data)
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"Error handling controller input signal: {e}")

    def update_controller_status(self, status_text: str, connected: bool):
        """Update controller status display (thread-safe)"""
        try:
            self._show_controller_state(status_text, connected)
            if (hasattr(self, 'controller_status_splash') and self.controller_status_splash
                    and self.controller_status_splash.isVisible()):
                controller_name = status_text.replace("Connected: ", "").replace("Disconnected: ", "")
                self.controller_status_splash.set_controller_info(controller_name, connected)
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"Error updating controller status: {e}")

    def handle_controller_input_for_status(self, msg: dict):
        """Feed steamdeck controller input to the status splash while it is open"""
        try:
            if hasattr(self, 'controller_status_splash') and self.controller_status_splash.isVisible():
                from threads.steamdeck import ControllerInputData

                input_data = ControllerInputData(
                    axes=msg.get("axes", {}),
                    buttons=msg.get("buttons", {}),
                    timestamp=msg.get("timestamp", time.time()),
                    sequence=msg.get("sequence", 0)
                )
                self.controller_status_splash.update_controller_input(input_data)
        except Exception as e:
            self.logger.error(f"Error handling controller input for status: {e}")

    def _show_controller_state(self, text: str, connected: bool):
        label = self.controller_status_label
        if label is None:
            return
        state = (text, connected)
        if getattr(self, "_controller_state", None) == state:
            return
        self._controller_state = state
        color = theme_manager.get("green") if connected else theme_manager.get("red")
        label.setText(f"●  {text}")
        label.setStyleSheet(f"color: {color}; background: transparent; border: none;")

    def _handle_maestro_info(self, data):
        """Handle maestro detection results"""
        maestro_num = data.get("maestro")
        channels = data.get("channels", 0)
        connected = data.get("connected", False)

        if maestro_num in [1, 2]:
            self.maestro_channel_counts[maestro_num] = channels
            self.maestro_connected[maestro_num] = connected

            if self.logger:
                self.logger.info(f"Controller config - Maestro {maestro_num}: {channels} channels, connected: {connected}")

            self._update_servo_channels()

            if not self._config_loaded:
                self._config_loaded = True
                QTimer.singleShot(500, self._load_existing_configuration)

    def _update_servo_channels(self):
        """Update servo channels based on detected maestros"""
        self.servo_channels = []

        for maestro_num in [1, 2]:
            if self.maestro_connected.get(maestro_num, False):
                channel_count = self.maestro_channel_counts.get(maestro_num, 0)
                for ch in range(channel_count):
                    self.servo_channels.append(f"m{maestro_num}_ch{ch}")

        if not self.servo_channels:
            self.servo_channels = [f"m{m}_ch{c}" for m in [1, 2] for c in range(24)]

        if self.logger:
            self.logger.info(f"Updated servo channels: {len(self.servo_channels)} channels available")

    def _load_predefined_options(self):
        """Load dropdown options"""
        self.steam_inputs = [
            "left_stick_x", "left_stick_y",
            "left_trigger",
            "right_stick_x", "right_stick_y",
            "right_trigger",
            "imu_roll", "imu_pitch",
            "button_a", "button_b", "button_x", "button_y",
            "shoulder_left", "shoulder_right",
            "button_menu",
            "left_trigger_btn", "right_trigger_btn",
            "stick_left_click", "stick_right_click",
            "grip_left_lower", "grip_right_lower",
            "grip_left_upper", "grip_right_upper",
            "button_left_pad", "button_right_pad",
            "dpad_up", "dpad_down", "dpad_left", "dpad_right"
        ]
        self.current_inputs = self.steam_inputs.copy()

        self.behaviors = [
            "direct_servo", "multi_servo", "toggle_servo", "joystick_pair", "differential_tracks",
            "scene_trigger", "toggle_scenes", "nema_stepper", "system_control",
            "imu_tilt", "imu_toggle"
        ]

        self.servo_channels = []

        self.scene_names = []
        try:
            scenes_config = config_manager.get_config("resources/configs/scenes_config.json")
            if isinstance(scenes_config, list) and scenes_config:
                self.scene_names = [scene.get("label", "Unknown") for scene in scenes_config if scene.get("label")]
        except Exception:
            pass

        if not self.scene_names:
            try:
                motion_config = config_manager.get_config("resources/configs/motion_config.json")
                self.scene_names = motion_config.get("emotions", [])
            except Exception:
                self.scene_names = ["Happy", "Sad", "Curious", "Excited", "Alert"]

    def _setup_screen(self):
        """Initialize controller configuration screen"""
        self.setFixedWidth(1200)
        self._dirty = False
        self._suppress_grid_reload = False

        from PyQt6.QtWidgets import QApplication
        app_instance = QApplication.instance()

        self.behavior_registry = BehaviorHandlerRegistry(
            websocket_sender=self.send_websocket_message,
            logger=self.logger,
            app_instance=app_instance
        )

        self._load_predefined_options()
        self._update_servo_channels()
        self._init_ui()

        if self.websocket:
            # The status splash stream and D-pad only matter while shown
            self.subscribe_while_visible("steamdeck_controller", self.handle_controller_input_for_status)
            self.subscribe_while_visible("navigation", self._on_navigation)
            self.subscribe("maestro_info", self._handle_maestro_info)
            self.subscribe("controller_info", self.handle_controller_info_response)
            self.subscribe("controller_config_data", self._on_controller_config_data)
            self.subscribe("controller_config_saved", self._on_controller_config_saved)
            self.subscribe("system_control_command", self._handle_system_control_command)
            if self.websocket.is_connected():
                QTimer.singleShot(500, self._request_config_from_backend)
            else:
                self.websocket.connected.connect(self._on_websocket_connected)

        QTimer.singleShot(5000, self._ensure_config_loaded)

    def _on_websocket_connected(self):
        """Called when websocket connection is established"""
        self.logger.info("WebSocket connected - requesting controller config")
        QTimer.singleShot(300, self._request_config_from_backend)

    def _request_config_from_backend(self):
        """Request maestro info and controller config from backend"""
        self.send_websocket_message("get_maestro_info", maestro=1)
        self.send_websocket_message("get_maestro_info", maestro=2)
        self.send_websocket_message("get_controller_config")
        self.request_controller_info()
        self.logger.info("Requested controller config from backend")

    # ========================================
    # CONFIG LOADING
    # ========================================

    def _load_existing_configuration(self):
        """Load mappings from the local file - fallback when backend hasn't responded"""
        try:
            config = config_manager.get_config(CONTROLLER_CONFIG_PATH)
            if config and isinstance(config, dict):
                loaded = self._load_mappings(config)
                if self.logger:
                    self.logger.info(f"Loaded {loaded} existing controller mappings")
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Could not load controller config: {e}")

    def _load_mappings(self, config: dict) -> int:
        previous = self._selected_row()
        previous_key = (previous['input'], previous['behavior']) if previous else None
        self._clear_all_rows()
        loaded = 0
        for control_name, control_config in config.items():
            if isinstance(control_config, list):
                for single_config in control_config:
                    if isinstance(single_config, dict):
                        self._add_mapping_row_from_config(control_name, single_config)
                        loaded += 1
            elif isinstance(control_config, dict):
                self._add_mapping_row_from_config(control_name, control_config)
                loaded += 1
            else:
                self.logger.warning(f"Skipping '{control_name}': unexpected type {type(control_config).__name__}")
        self._dirty = False
        self._check_for_conflicts()
        index = 0
        if previous_key:
            index = next((i for i, r in enumerate(self.mapping_rows)
                          if (r['input'], r['behavior']) == previous_key), 0)
        self._rebuild_list(select_index=index if self.mapping_rows else None)
        return loaded

    def update_available_inputs(self, controller_type: str, available_inputs: list):
        """Update available inputs based on connected controller type"""
        if self._loading_config:
            return
        if controller_type.lower() in ['wii', 'wiimote', 'nintendo']:
            self.current_inputs = available_inputs if available_inputs else getattr(self, 'wii_inputs', self.steam_inputs)
            controller_name = "Wii Remote"
        else:
            self.current_inputs = available_inputs if available_inputs else self.steam_inputs
            controller_name = "Steam Deck"

        self._fill_input_combo()

        if self.logger:
            self.logger.info(f"Updated input options for {controller_name}: {len(self.current_inputs)} inputs available")

    def _add_mapping_row_from_config(self, control_name: str, control_config: Dict):
        """Add a mapping from saved configuration"""
        try:
            config = control_config.copy()
            behavior = config.pop('behavior', 'direct_servo')
            self.mapping_rows.append({
                'input': control_name,
                'behavior': behavior,
                'config': config,
                'conflict_detected': False,
            })
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error adding mapping row from config: {e}")

    def request_controller_info(self):
        """Request controller information from backend"""
        if self.websocket and self.websocket.is_connected():
            self.send_websocket_message("get_controller_info")
            if self.logger:
                self.logger.info("Requested controller info from backend")

    def reload_controller_settings(self):
        """Called by settings screen after a GUI update to reload config from backend."""
        self._refresh_from_backend()

    def _refresh_from_backend(self):
        """Refresh controller config from backend, then update controller status"""
        if self.websocket and self.websocket.is_connected():
            self.send_websocket_message("get_controller_config")
            QTimer.singleShot(1000, self.request_controller_info)
            if self.logger:
                self.logger.info("Requested controller config from backend")
        else:
            self.logger.warning("WebSocket not connected - cannot refresh from backend")

    def _load_config_from_backend_response(self, config: dict):
        """Populate the mapping list from config data received from backend"""
        if not config:
            self.logger.warning("Received empty controller config from backend")
            return

        # After a save the screen requests the config back so steamdeck.py can
        # hot-reload imu_toggle_buttons; the list is left as it is
        if getattr(self, '_suppress_grid_reload', False):
            self._suppress_grid_reload = False
            self.logger.info("Config hot-reload skipped for list (steamdeck.py updated via websocket)")
            return

        self._config_loaded = True
        self._loading_config = True
        try:
            loaded = self._load_mappings(config)
            self.logger.info(f"Loaded {loaded} controller mappings from backend")
        except Exception as e:
            self.logger.error(f"Error loading config from backend: {e}", exc_info=True)
        finally:
            self._loading_config = False

    def _clear_all_rows(self):
        """Remove all mappings"""
        self.mapping_rows.clear()
        self.selected_row_index = None

    def handle_controller_info_response(self, data: Dict):
        """Handle controller info response from backend"""
        try:
            controller_info = data.get("controller_info", {})
            connected = controller_info.get("connected", False)
            controller_type = controller_info.get("controller_type", "unknown")
            controller_name = controller_info.get("controller_name", "Unknown")
            available_inputs = controller_info.get("available_inputs", [])

            if connected:
                self._show_controller_state(f"{controller_name} · Connected", True)
                if available_inputs:
                    self.update_available_inputs(controller_type, available_inputs)
            else:
                self._show_controller_state("No controller connected", False)

            if self.logger:
                self.logger.info(f"Controller info updated: {controller_name} ({controller_type})")

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error handling controller info response: {e}")

    def __del__(self):
        try:
            theme_manager.unregister_callback(self.update_theme)
        except Exception:
            pass

    # ========================================
    # DISPLAY TEXT
    # ========================================

    def _servo_names(self) -> dict:
        try:
            config = config_manager.get_config(SERVO_CONFIG_PATH) or {}
        except Exception:
            config = {}
        return {k: v.get("name", "") for k, v in config.items() if isinstance(v, dict)}

    def _servo_label(self, channel: str, names: dict = None, short: bool = False) -> str:
        """'M1 ch2 · Left Eye Tilt', or the name alone when short"""
        if not channel:
            return ""
        if names is None:
            names = self._servo_names()
        name = names.get(channel, "")
        try:
            maestro, ch = channel[1:].split("_ch")
            code = f"M{maestro} ch{ch}"
        except ValueError:
            code = channel
        if short:
            return name or code
        return f"{code} · {name}" if name else code

    def _get_target_display_text(self, behavior: str, config: Dict[str, Any], names: dict = None) -> str:
        """Short summary of what a mapping drives"""
        if names is None:
            names = self._servo_names()

        def servo(key):
            return self._servo_label(config.get(key, ""), names, short=True)

        if behavior in ("direct_servo", "toggle_servo"):
            return servo('target') or "Not set"
        if behavior in ("multi_servo", "imu_tilt"):
            channels = [s.get('channel') for s in config.get('servos', []) if s.get('channel')]
            if not channels:
                return "No servos"
            if len(channels) <= 2:
                return " / ".join(self._servo_label(c, names, short=True) for c in channels)
            return f"{len(channels)} servos"
        if behavior == "joystick_pair":
            x, y = servo('x_servo'), servo('y_servo')
            return f"X: {x or '?'} · Y: {y or '?'}" if (x or y) else "Not set"
        if behavior == "differential_tracks":
            left, right = servo('left_servo'), servo('right_servo')
            return f"{left or '?'} / {right or '?'}" if (left or right) else "Not set"
        if behavior == "scene_trigger":
            return config.get('scene', '') or "Not set"
        if behavior == "toggle_scenes":
            return f"{config.get('scene_1', '?')} ⇄ {config.get('scene_2', '?')}"
        if behavior == "nema_stepper":
            mode = NEMA_MODES.get(config.get('nema_behavior', ''), "Not set")
            min_pos = config.get('min_position')
            max_pos = config.get('max_position')
            if isinstance(min_pos, (int, float)) and isinstance(max_pos, (int, float)):
                return f"{mode} {min_pos:g} – {max_pos:g} cm"
            return mode
        if behavior == "system_control":
            action = config.get('system_action', '')
            return SYSTEM_ACTIONS.get(action, action) or "Not set"
        return ""

    # ========================================
    # LAYOUT
    # ========================================

    def _init_ui(self):
        self._cards = []
        self._card_titles = []
        self._captions = []
        self._plain_buttons = []

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
        cards.addWidget(self._build_editor_card())
        cards.addStretch(1)
        content_layout.addLayout(cards)
        content_layout.addLayout(self._build_bottom_bar())

        root.addWidget(content, 0, Qt.AlignmentFlag.AlignLeft)
        root.addStretch(1)
        self.setLayout(root)

        self._apply_styles()
        self._show_editor()
        QTimer.singleShot(1000, self.request_controller_info)

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

    def _caption(self, text: str, track: bool = True) -> QLabel:
        label = QLabel(text)
        label.setFont(px_font(12, spacing=1.0))
        label.setStyleSheet(f"color: {LABEL_GREY}; background: transparent; border: none;")
        if track:
            self._captions.append(label)
        return label

    def _combo(self, height: int = 44, font_size: int = 16) -> QComboBox:
        combo = QComboBox()
        combo.setView(QListView())
        combo.setFixedHeight(height)
        combo.setFont(px_font(font_size))
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(8)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.setStyleSheet(combo_style())
        return combo

    def _build_list_card(self):
        card = self._make_card(LIST_CARD_WIDTH)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(self._card_title("MAPPINGS"))
        self.count_label = QLabel("")
        self.count_label.setFont(px_font(13))
        self._captions.append(self.count_label)
        header.addWidget(self.count_label, 1)
        header.addWidget(self._caption("SHOW"))
        self.filter_combo = self._combo(40, 15)
        self.filter_combo.setFixedWidth(170)
        self.filter_combo.addItems(FILTERS)
        self.filter_combo.currentTextChanged.connect(lambda _: self._rebuild_list())
        header.addWidget(self.filter_combo)
        layout.addLayout(header)

        self.list_divider = QFrame()
        self.list_divider.setFixedHeight(1)
        layout.addWidget(self.list_divider)

        self.mapping_list = MappingList()
        self.mapping_list.setSpacing(LIST_ROW_SPACING // 2)
        self.mapping_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.mapping_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.mapping_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mapping_list.currentRowChanged.connect(self._on_list_row_changed)
        layout.addWidget(self.mapping_list, 1)
        self._list_rows = []
        self._visible_indices = []
        return card

    def _build_editor_card(self):
        card = self._make_card(EDIT_CARD_WIDTH)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(self._card_title("EDIT MAPPING"))
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

        selectors = QGridLayout()
        selectors.setHorizontalSpacing(12)
        selectors.setVerticalSpacing(4)
        selectors.addWidget(self._caption("INPUT"), 0, 0)
        selectors.addWidget(self._caption("BEHAVIOUR"), 0, 1)
        self.input_combo = self._combo()
        self.input_combo.activated.connect(self._on_input_chosen)
        self.behavior_combo = self._combo()
        self.behavior_combo.addItem("Select behaviour…", "")
        for behavior in self.behaviors:
            self.behavior_combo.addItem(BEHAVIOR_NAMES.get(behavior, behavior), behavior)
        self.behavior_combo.activated.connect(self._on_behavior_chosen)
        selectors.addWidget(self.input_combo, 1, 0)
        selectors.addWidget(self.behavior_combo, 1, 1)
        selectors.setColumnStretch(0, 1)
        selectors.setColumnStretch(1, 1)
        body.addLayout(selectors)

        self.editor_divider = QFrame()
        self.editor_divider.setFixedHeight(1)
        body.addWidget(self.editor_divider)

        self.params_scroll = QScrollArea()
        self.params_scroll.setWidgetResizable(True)
        self.params_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.params_container = QWidget()
        self.params_container.setStyleSheet("background: transparent;")
        self.params_layout = QVBoxLayout(self.params_container)
        self.params_layout.setContentsMargins(0, 0, 8, 0)
        self.params_layout.setSpacing(10)
        self.params_scroll.setWidget(self.params_container)
        body.addWidget(self.params_scroll, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self.foot_hint = QLabel("")
        self.foot_hint.setFont(px_font(13))
        self._captions.append(self.foot_hint)
        bottom.addWidget(self.foot_hint, 1)
        self.delete_btn = QPushButton("DELETE")
        self.delete_btn.setFixedSize(110, 44)
        self.delete_btn.setFont(px_font(14, bold=True))
        self.delete_btn.clicked.connect(self._delete_selected)
        bottom.addWidget(self.delete_btn)
        body.addLayout(bottom)

        self.empty_label = QLabel("Select a mapping, or add one with + ADD MAPPING.")
        self.empty_label.setFont(px_font(15))
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self._captions.append(self.empty_label)

        layout.addWidget(self.editor_body, 1)
        layout.addWidget(self.empty_label, 1)
        return card

    def _build_bottom_bar(self):
        bar = QHBoxLayout()
        bar.setSpacing(12)

        self.add_btn = QPushButton("+ ADD MAPPING")
        self.add_btn.setFixedSize(180, BAR_HEIGHT)
        self.add_btn.clicked.connect(self._add_mapping_row)
        self.calibration_button = QPushButton("CALIBRATE")
        self.calibration_button.setFixedSize(130, BAR_HEIGHT)
        self.calibration_button.clicked.connect(self.open_calibration_dialog)
        self.status_button = QPushButton("STATUS")
        self.status_button.setFixedSize(120, BAR_HEIGHT)
        self.status_button.clicked.connect(self.open_controller_status)
        for button in (self.add_btn, self.calibration_button, self.status_button):
            button.setFont(px_font(15, bold=True))
            self._plain_buttons.append(button)
            bar.addWidget(button)

        self.controller_status_label = QLabel("●  Checking...")
        self.controller_status_label.setFont(px_font(13))
        self.controller_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.controller_status_label.setStyleSheet(f"color: {LABEL_GREY}; background: transparent;")
        bar.addWidget(self.controller_status_label, 1)

        self.refresh_btn = QPushButton("REFRESH")
        self.refresh_btn.setFixedSize(120, BAR_HEIGHT)
        self.refresh_btn.setFont(px_font(15, bold=True))
        self.refresh_btn.clicked.connect(self._refresh_from_backend)
        self._plain_buttons.append(self.refresh_btn)
        bar.addWidget(self.refresh_btn)

        self.save_btn = QPushButton("SAVE ALL")
        self.save_btn.setFixedSize(140, BAR_HEIGHT)
        self.save_btn.setFont(px_font(15, bold=True))
        self.save_btn.clicked.connect(self._save_all_mappings)
        bar.addWidget(self.save_btn)
        return bar

    def _apply_styles(self):
        primary = theme_manager.get("primary_color")
        for card in self._cards:
            card.setStyleSheet(card_style())
        for title in self._card_titles:
            title.setStyleSheet(f"color: {primary};")
        for caption in self._captions:
            caption.setStyleSheet(f"color: {LABEL_GREY}; background: transparent; border: none;")
        for button in self._plain_buttons:
            button.setStyleSheet(plain_button_style())
        self.save_btn.setStyleSheet(filled_button_style(theme_manager.get("green")))
        self.delete_btn.setStyleSheet(outline_button_style(theme_manager.get("red"), "#ff7777"))
        for combo in (self.filter_combo, self.input_combo, self.behavior_combo):
            combo.setStyleSheet(combo_style())
        self.list_divider.setStyleSheet(f"background-color: {DIVIDER}; border: none;")
        self.editor_divider.setStyleSheet(f"background-color: {DIVIDER}; border: none;")
        self.mapping_list.setStyleSheet(scroll_style())
        self.params_scroll.setStyleSheet(scroll_style())
        for row in self._list_rows:
            row._apply_style()
        self._update_dirty_label()
        state = getattr(self, "_controller_state", None)
        if state:
            self._controller_state = None
            self._show_controller_state(*state)

    def update_theme(self):
        """Update all UI elements when theme changes"""
        try:
            self._apply_styles()
            self._show_editor()
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to apply theme changes: {e}")

    # ========================================
    # CALIBRATION AND MESSAGES
    # ========================================

    def open_calibration_dialog(self):
        """Open the IMU calibration dialog"""
        try:
            from widgets.imu_calibration_dialog import ImuCalibrationDialog

            controller_thread = None
            for widget in QApplication.instance().topLevelWidgets():
                if hasattr(widget, 'controller_thread'):
                    controller_thread = widget.controller_thread
                    break

            if controller_thread is None:
                self.logger.warning("No controller thread available for IMU calibration")
                self.show_error_message("Calibration Error",
                                        "The Steam Deck controller is not running, so there is no IMU data to calibrate.")
                return

            dialog = ImuCalibrationDialog(self, controller_thread)
            dialog.exec()

        except ImportError as e:
            self.logger.error(f"Failed to import calibration dialog: {e}")
            self.show_error_message("Calibration Error",
                                    "Failed to load calibration interface. Please check the installation.")
        except Exception as e:
            self.logger.error(f"Failed to open calibration dialog: {e}")
            self.show_error_message("Calibration Error",
                                    f"Failed to open calibration dialog: {str(e)}")

    def show_error_message(self, title: str, message: str):
        show_message(self, "CONTROLLER", title, message, kind="error")

    def show_info_message(self, title: str, message: str):
        show_message(self, "CONTROLLER", title, message)

    # ========================================
    # MAPPING LIST
    # ========================================

    def _selected_row(self):
        if self.selected_row_index is not None and 0 <= self.selected_row_index < len(self.mapping_rows):
            return self.mapping_rows[self.selected_row_index]
        return None

    def _rebuild_list(self, select_index=None):
        """Rebuild the visible list for the current filter"""
        if select_index is None:
            select_index = self.selected_row_index
        group = self.filter_combo.currentText()
        names = self._servo_names()

        self._visible_indices = [
            i for i, row in enumerate(self.mapping_rows)
            if group == "All" or (row['input'] and input_group(row['input']) == group)
        ]

        self.mapping_list.blockSignals(True)
        self.mapping_list.clear()
        self._list_rows = []
        width = self.mapping_list.viewport().width()
        for index in self._visible_indices:
            item = QListWidgetItem()
            item.setSizeHint(QSize(width, LIST_ROW_HEIGHT))
            self.mapping_list.addItem(item)
            row_widget = MappingRow()
            self.mapping_list.setItemWidget(item, row_widget)
            self._list_rows.append(row_widget)
            self._refresh_list_row(index, names)
        self.mapping_list.blockSignals(False)

        total = len(self.mapping_rows)
        shown = len(self._visible_indices)
        noun = "mapping" if total == 1 else "mappings"
        self.count_label.setText(f"{total} {noun}" if group == "All" else f"{shown} of {total}")

        if select_index is not None and select_index in self._visible_indices:
            self._select_visible(self._visible_indices.index(select_index))
        elif self._visible_indices:
            self._select_visible(0)
        else:
            self.selected_row_index = None
            self._show_editor()

    def _refresh_list_row(self, row_index: int, names: dict = None):
        if row_index not in self._visible_indices:
            return
        row = self.mapping_rows[row_index]
        widget = self._list_rows[self._visible_indices.index(row_index)]
        widget.set_content(
            input_display_name(row['input']),
            BEHAVIOR_TAGS.get(row['behavior'], ""),
            self._get_target_display_text(row['behavior'], row['config'], names),
            row.get('conflict_detected', False))
        widget.set_selected(row_index == self.selected_row_index)

    def _select_visible(self, position: int):
        self.mapping_list.blockSignals(True)
        self.mapping_list.setCurrentRow(position)
        self.mapping_list.blockSignals(False)
        self._on_list_row_changed(position)
        item = self.mapping_list.item(position)
        if item is not None:
            self.mapping_list.scrollToItem(item)

    def _on_list_row_changed(self, position: int):
        if not (0 <= position < len(self._visible_indices)):
            return
        self.selected_row_index = self._visible_indices[position]
        for i, widget in enumerate(self._list_rows):
            widget.set_selected(i == position)
        self._show_editor()

    def _on_navigation(self, msg: dict):
        """D-pad up/down moves through the mapping list"""
        action = msg.get("action")
        if action not in ("up", "down") or not self._visible_indices:
            return
        current = max(0, self.mapping_list.currentRow())
        new_position = max(0, min(len(self._visible_indices) - 1, current + (-1 if action == "up" else 1)))
        if new_position != self.mapping_list.currentRow():
            self._select_visible(new_position)

    def _add_mapping_row(self):
        """Add a new, empty mapping and select it"""
        self.mapping_rows.append({'input': '', 'behavior': '', 'config': {}, 'conflict_detected': False})
        self._mark_dirty()
        if self.filter_combo.currentText() != "All":
            self.filter_combo.blockSignals(True)
            self.filter_combo.setCurrentText("All")
            self.filter_combo.blockSignals(False)
        self._rebuild_list(select_index=len(self.mapping_rows) - 1)

    def _delete_selected(self):
        row = self._selected_row()
        if row is None:
            return
        name = input_display_name(row['input'])
        if not ask_confirm(self, "CONTROLLER", "Delete mapping?",
                           f"Delete the {BEHAVIOR_TAGS.get(row['behavior'], 'mapping')} mapping on {name}?",
                           confirm="DELETE", danger=True):
            return
        self._remove_mapping_row(self.selected_row_index)

    def _remove_mapping_row(self, row_index: int):
        """Remove a mapping and select its neighbour"""
        if not (0 <= row_index < len(self.mapping_rows)):
            return
        self.mapping_rows.pop(row_index)
        self._mark_dirty()
        self._check_for_conflicts()
        if self.mapping_rows:
            self.selected_row_index = min(row_index, len(self.mapping_rows) - 1)
        else:
            self.selected_row_index = None
        self._rebuild_list(select_index=self.selected_row_index)

    def _check_for_conflicts(self):
        """Flag mappings that put different joystick behaviours on the same stick"""
        for row in self.mapping_rows:
            row['conflict_detected'] = self._conflict_info(row) is not None

    def _conflict_info(self, row) -> Optional[str]:
        control_name, behavior = row['input'], row['behavior']
        if not control_name or behavior not in JOYSTICK_BEHAVIORS:
            return None
        base_name = control_name.replace('_x', '').replace('_y', '')
        for other in self.mapping_rows:
            if other is row or not other['input']:
                continue
            other_base = other['input'].replace('_x', '').replace('_y', '')
            if (other_base == base_name
                    and other['behavior'] in JOYSTICK_BEHAVIORS
                    and other['behavior'] != behavior
                    and other['input'] != control_name):
                return (f"{input_display_name(other['input'])} already uses "
                        f"{BEHAVIOR_TAGS.get(other['behavior'], other['behavior'])}. "
                        f"Both axes of a stick must use the same joystick behaviour.")
        return None

    def _refresh_all_rows(self):
        names = self._servo_names()
        for index in self._visible_indices:
            self._refresh_list_row(index, names)

    def _mark_dirty(self):
        self._dirty = True
        self._update_dirty_label()

    def _update_dirty_label(self):
        self.dirty_label.setText("Unsaved changes" if self._dirty else "Saved")
        self.dirty_label.setStyleSheet(f"color: {DIRTY_ORANGE if self._dirty else LABEL_GREY};")

    # ========================================
    # EDITOR
    # ========================================

    def _fill_input_combo(self):
        row = self._selected_row()
        current = row['input'] if row else ""
        self.input_combo.blockSignals(True)
        self.input_combo.clear()
        self.input_combo.addItem("Select input…", "")
        inputs = list(self.current_inputs)
        if current and current not in inputs:
            inputs.insert(0, current)
        for control in inputs:
            self.input_combo.addItem(input_display_name(control), control)
        index = self.input_combo.findData(current)
        self.input_combo.setCurrentIndex(max(0, index))
        self.input_combo.blockSignals(False)

    def _show_editor(self):
        """Show the selected mapping in the editor"""
        row = self._selected_row()
        self.editor_body.setVisible(row is not None)
        self.empty_label.setVisible(row is None)
        if row is None:
            self._clear_parameters_layout()
            return
        self._fill_input_combo()
        self.behavior_combo.blockSignals(True)
        self.behavior_combo.setCurrentIndex(max(0, self.behavior_combo.findData(row['behavior'])))
        self.behavior_combo.blockSignals(False)
        self._create_behavior_parameters(row)

    def _on_input_chosen(self, index: int):
        row = self._selected_row()
        if row is None:
            return
        control = self.input_combo.itemData(index) or ""
        if control == row['input']:
            return
        row['input'] = control
        self._after_row_change(rebuild_params=True)

    def _on_behavior_chosen(self, index: int):
        row = self._selected_row()
        if row is None:
            return
        behavior = self.behavior_combo.itemData(index) or ""
        if behavior == row['behavior']:
            return
        row['behavior'] = behavior
        row['config'] = {}
        self._after_row_change(rebuild_params=True)

    def _after_row_change(self, rebuild_params: bool = False):
        self._mark_dirty()
        self._check_for_conflicts()
        self._refresh_all_rows()
        if rebuild_params:
            self._create_behavior_parameters(self._selected_row())

    def _update_row_config(self, row_data: Dict, key: str, value):
        """Update one config value of a mapping"""
        row_data['config'][key] = value
        self._mark_dirty()
        if row_data is self._selected_row():
            self._refresh_list_row(self.selected_row_index)

    def _clear_parameters_layout(self):
        """Remove every widget and layout from the parameters area"""
        def clear(layout):
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                elif child.layout():
                    clear(child.layout())
        clear(self.params_layout)

    def _create_behavior_parameters(self, row_data: Dict):
        """Create behaviour-specific parameter controls"""
        self._clear_parameters_layout()
        if row_data is None:
            return
        behavior = row_data['behavior']
        self.foot_hint.setText("")

        conflict = self._conflict_info(row_data)
        self.input_combo.setStyleSheet(combo_style() + (
            f"QComboBox {{ border: 1px solid {CONFLICT_RED}; }}" if conflict else ""))
        if conflict:
            self._add_conflict_banner(conflict)

        builders = {
            "direct_servo": self._create_direct_servo_params,
            "multi_servo": self._create_multi_servo_params,
            "toggle_servo": self._create_toggle_servo_params,
            "joystick_pair": self._create_joystick_pair_params,
            "differential_tracks": self._create_differential_tracks_params,
            "scene_trigger": self._create_scene_trigger_params,
            "toggle_scenes": self._create_toggle_scenes_params,
            "nema_stepper": self._create_nema_stepper_params,
            "system_control": self._create_system_control_params,
            "imu_tilt": self._create_imu_tilt_params,
            "imu_toggle": self._create_imu_toggle_params,
        }
        if behavior in builders:
            builders[behavior](row_data)
        else:
            self._add_note("Choose a behaviour for this input.")
        if conflict:
            self.foot_hint.setText("Fix the conflict before saving")
        self.params_layout.addStretch(1)

    # ---------- Parameter widgets ----------

    def _add_conflict_banner(self, text: str):
        banner = QLabel(f"⚠  {text}")
        banner.setWordWrap(True)
        banner.setFont(px_font(13))
        banner.setStyleSheet(
            f"color: #ff9999; background-color: {rgba(CONFLICT_RED, 0.15)}; "
            f"border: 1px solid {CONFLICT_RED}; border-radius: 8px; padding: 8px 12px;")
        self.params_layout.addWidget(banner)

    def _add_note(self, text: str, color: str = LABEL_GREY):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setFont(px_font(13))
        label.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        self.params_layout.addWidget(label)
        return label

    def _add_field(self, caption: str, widget: QWidget, layout=None):
        column = QVBoxLayout()
        column.setSpacing(4)
        column.addWidget(self._caption(caption, track=False))
        column.addWidget(widget)
        (self.params_layout if layout is None else layout).addLayout(column)
        return column

    def _servo_combo(self, current: str, height: int = 44, font_size: int = 16) -> QComboBox:
        combo = self._combo(height, font_size)
        names = self._servo_names()
        combo.addItem("Select servo…", "")
        channels = list(self.servo_channels)
        if current and current not in channels:
            channels.insert(0, current)
        for channel in channels:
            combo.addItem(self._servo_label(channel, names), channel)
        combo.setCurrentIndex(max(0, combo.findData(current)))
        return combo

    def _choice_combo(self, options: dict, current: str, placeholder: str = None) -> QComboBox:
        combo = self._combo()
        if placeholder:
            combo.addItem(placeholder, "")
        for value, text in options.items():
            combo.addItem(text, value)
        if current and combo.findData(current) < 0:
            combo.addItem(current, current)
        combo.setCurrentIndex(max(0, combo.findData(current)))
        return combo

    def _segmented(self, options: list, current: str, on_change, enabled: bool = True) -> QFrame:
        """Pill with one button per (value, text) option"""
        primary = theme_manager.get("primary_color")
        frame = QFrame()
        frame.setObjectName("segmented")
        frame.setFixedHeight(44)
        frame.setStyleSheet(
            "QFrame#segmented { background-color: #242424; border: 1px solid #3e3e3e; border-radius: 22px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)
        group = QButtonGroup(frame)
        group.setExclusive(True)
        for value, text in options:
            button = QPushButton(text)
            button.setCheckable(True)
            button.setFixedHeight(36)
            button.setFont(px_font(14, bold=True))
            button.setChecked(value == current)
            button.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {TEXT_SOFT};
                    border: none;
                    border-radius: 18px;
                }}
                QPushButton:checked {{
                    background-color: {primary};
                    color: #111111;
                }}
                QPushButton:disabled {{
                    color: #555;
                }}
                QPushButton:checked:disabled {{
                    background-color: #333333;
                    color: #777777;
                }}
            """)
            button.clicked.connect(lambda _, v=value: on_change(v))
            group.addButton(button)
            layout.addWidget(button, 1)
        frame.setEnabled(enabled)
        return frame

    def _invert_switch(self, checked: bool, on_change) -> QWidget:
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        label = QLabel("Invert")
        label.setFont(px_font(14))
        label.setStyleSheet(f"color: {TEXT_SOFT};")
        switch = ToggleSwitch()
        switch.setChecked(checked)
        switch.toggled.connect(on_change)
        layout.addWidget(label)
        layout.addWidget(switch)
        return holder

    def _stepper_tile(self, value: int, minimum: int, maximum: int, on_change,
                      caption: str = None, compact: bool = False) -> QFrame:
        """− value + tile; compact tiles carry their caption inside"""
        frame = QFrame()
        frame.setObjectName("stepper_tile")
        frame.setFixedHeight(40 if compact else 56)
        frame.setStyleSheet(
            f"QFrame#stepper_tile {{ background-color: {TILE_BG}; border: 1px solid #3a3a3a; border-radius: 8px; }}"
            "QLabel { background: transparent; border: none; color: white; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(2 if compact else 6, 0, 2 if compact else 6, 0)
        layout.setSpacing(2 if compact else 4)
        if compact and caption:
            cap = QLabel(caption)
            cap.setFont(px_font(10, spacing=0.5))
            cap.setFixedWidth(36)
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cap.setStyleSheet(f"color: {LABEL_GREY};")
            layout.addWidget(cap)
        size = 34 if compact else 44
        minus = StepButton(-1, size)
        plus = StepButton(1, size)
        label = QLabel(str(value))
        label.setFont(px_font(15 if compact else 22, bold=True, family="Consolas"))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        state = {"value": value}

        def step(direction):
            new_value = max(minimum, min(maximum, state["value"] + direction * PULSE_STEP))
            if new_value != state["value"]:
                state["value"] = new_value
                label.setText(str(new_value))
                on_change(new_value)

        minus.stepped.connect(step)
        plus.stepped.connect(step)
        layout.addWidget(minus)
        layout.addWidget(label, 1)
        layout.addWidget(plus)
        return frame

    def _readout_tile(self, caption: str, value) -> QFrame:
        """Read-only caption and value tile, the same size as a compact stepper tile"""
        frame = QFrame()
        frame.setObjectName("readout_tile")
        frame.setFixedHeight(40)
        frame.setStyleSheet(
            f"QFrame#readout_tile {{ background-color: {TILE_BG}; border: 1px solid #3a3a3a; border-radius: 8px; }}"
            "QLabel { background: transparent; border: none; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(2, 0, 10, 0)
        layout.setSpacing(2)
        cap = QLabel(caption)
        cap.setFont(px_font(10, spacing=0.5))
        cap.setFixedWidth(36)
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cap.setStyleSheet(f"color: {LABEL_GREY};")
        layout.addWidget(cap)
        label = QLabel(str(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else "--")
        label.setFont(px_font(15, bold=True, family="Consolas"))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"color: {LABEL_GREY};")
        layout.addWidget(label, 1)
        return frame

    def _timing_segment(self, row_data: Dict, options=("on_press", "on_release"), enabled: bool = True):
        labels = {"on_press": "Press", "on_release": "Release", "continuous": "Continuous"}
        current = row_data['config'].get('trigger_timing', 'on_press')
        return self._segmented([(o, labels[o]) for o in options], current,
                               lambda v: self._update_row_config(row_data, 'trigger_timing', v), enabled)

    # ---------- Behaviours ----------

    def _create_direct_servo_params(self, row_data: Dict):
        servo = self._servo_combo(row_data['config'].get('target', ''))
        servo.activated.connect(
            lambda i, c=servo: self._update_row_config(row_data, 'target', c.itemData(i)) if c.itemData(i) else None)
        row = QHBoxLayout()
        row.setSpacing(12)
        self._add_field("TARGET SERVO", servo, row)
        invert = self._invert_switch(row_data['config'].get('invert', False),
                                     lambda checked: self._update_row_config(row_data, 'invert', checked))
        row.addWidget(invert, 0, Qt.AlignmentFlag.AlignBottom)
        self.params_layout.addLayout(row)
        self.foot_hint.setText(f"Maps {input_display_name(row_data['input'])} to one servo")

    def _create_multi_servo_params(self, row_data: Dict):
        servos = row_data['config'].setdefault('servos', [])
        header = QHBoxLayout()
        header.addWidget(self._caption("SERVOS", track=False), 1)
        add_btn = QPushButton("+ ADD SERVO")
        add_btn.setFixedHeight(32)
        add_btn.setFont(px_font(12, bold=True))
        add_btn.setStyleSheet(outline_button_style(theme_manager.get("primary_color"),
                                                   theme_manager.get("primary_color")))
        add_btn.clicked.connect(lambda: self._add_multi_servo_row(row_data))
        header.addWidget(add_btn)
        self.params_layout.addLayout(header)

        for index, servo_info in enumerate(servos):
            self.params_layout.addLayout(self._create_multi_servo_row(row_data, index, servo_info))
        if not servos:
            self._add_note("No servos yet")
        self.foot_hint.setText("Each servo follows the input, with its own invert")

    def _create_multi_servo_row(self, row_data: Dict, index: int, servo_info: Dict):
        row = QHBoxLayout()
        row.setSpacing(10)
        combo = self._servo_combo(servo_info.get('channel', ''), 40, 15)
        combo.activated.connect(
            lambda i, c=combo: self._update_multi_servo_channel(row_data, index, c.itemData(i) or ""))
        row.addWidget(combo, 1)
        row.addWidget(self._invert_switch(
            servo_info.get('invert', False),
            lambda checked: self._update_multi_servo_invert(row_data, index, checked)))
        remove = QPushButton("×")
        remove.setFixedSize(40, 40)
        remove.setFont(px_font(20))
        remove.setAccessibleName("Remove servo")
        remove.setStyleSheet(outline_button_style(theme_manager.get("red"), "#ff7777"))
        remove.clicked.connect(lambda: self._remove_multi_servo_row(row_data, index))
        row.addWidget(remove)
        return row

    def _add_multi_servo_row(self, row_data: Dict):
        row_data['config'].setdefault('servos', []).append({'channel': '', 'invert': False})
        self._mark_dirty()
        self._create_behavior_parameters(row_data)

    def _remove_multi_servo_row(self, row_data: Dict, index: int):
        servos = row_data['config'].get('servos', [])
        if index < len(servos):
            servos.pop(index)
        self._mark_dirty()
        self._refresh_list_row(self.selected_row_index)
        self._create_behavior_parameters(row_data)

    def _update_multi_servo_channel(self, row_data: Dict, index: int, channel: str):
        servos = row_data['config'].get('servos', [])
        if index < len(servos) and channel:
            servos[index]['channel'] = channel
            self._mark_dirty()
            self._refresh_list_row(self.selected_row_index)

    def _update_multi_servo_invert(self, row_data: Dict, index: int, inverted: bool):
        servos = row_data['config'].get('servos', [])
        if index < len(servos):
            servos[index]['invert'] = inverted
            self._mark_dirty()

    def _create_toggle_servo_params(self, row_data: Dict):
        config = row_data['config']
        servo = self._servo_combo(config.get('target', ''))
        servo.activated.connect(
            lambda i, c=servo: self._update_row_config(row_data, 'target', c.itemData(i)) if c.itemData(i) else None)
        self._add_field("TARGET SERVO", servo)

        mode = config.get('trigger_mode', 'toggle')
        modes = QHBoxLayout()
        modes.setSpacing(12)
        self._add_field("MODE", self._segmented(
            [("toggle", "Toggle"), ("hold", "Hold")], mode,
            lambda v: self._set_toggle_mode(row_data, v)), modes)
        self._add_field("TOGGLE ON (TOGGLE MODE)", self._timing_segment(row_data, enabled=(mode == 'toggle')), modes)
        self.params_layout.addLayout(modes)

        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self._add_field("POSITION 1 · RELEASED", self._stepper_tile(
            config.get('position_1', 1000), 800, 2200,
            lambda v: self._update_row_config(row_data, 'position_1', v)), tiles)
        self._add_field("POSITION 2 · HELD", self._stepper_tile(
            config.get('position_2', 2000), 800, 2200,
            lambda v: self._update_row_config(row_data, 'position_2', v)), tiles)
        self.params_layout.addLayout(tiles)

        name = input_display_name(row_data['input'])
        if mode == 'hold':
            self.foot_hint.setText(f"Hold {name}: Position 2, release: Position 1")
        else:
            self.foot_hint.setText(f"Press {name} to swap between the positions")

    def _set_toggle_mode(self, row_data: Dict, mode: str):
        self._update_row_config(row_data, 'trigger_mode', mode)
        self._create_behavior_parameters(row_data)

    def _create_joystick_pair_params(self, row_data: Dict):
        row = QHBoxLayout()
        row.setSpacing(12)
        for key, caption in (('x_servo', "X SERVO"), ('y_servo', "Y SERVO")):
            combo = self._servo_combo(row_data['config'].get(key, ''))
            combo.activated.connect(
                lambda i, c=combo, k=key: self._update_row_config(row_data, k, c.itemData(i)) if c.itemData(i) else None)
            self._add_field(caption, combo, row)
        self.params_layout.addLayout(row)
        self.foot_hint.setText(f"Uses both X and Y axes of {input_display_name(row_data['input'])}")

    def _create_differential_tracks_params(self, row_data: Dict):
        config = row_data['config']
        for key, invert_key, caption in (('left_servo', 'invert_left', "LEFT TRACK"),
                                         ('right_servo', 'invert_right', "RIGHT TRACK")):
            row = QHBoxLayout()
            row.setSpacing(12)
            combo = self._servo_combo(config.get(key, ''))
            combo.activated.connect(
                lambda i, c=combo, k=key: self._update_row_config(row_data, k, c.itemData(i)) if c.itemData(i) else None)
            self._add_field(caption, combo, row)
            row.addWidget(self._invert_switch(
                config.get(invert_key, False),
                lambda checked, k=invert_key: self._set_tracks_invert(row_data, k, checked)),
                0, Qt.AlignmentFlag.AlignBottom)
            self.params_layout.addLayout(row)

        sensitivity = float(config.get('turn_sensitivity', 1.0))
        head = QHBoxLayout()
        head.addWidget(self._caption("TURN SENSITIVITY", track=False))
        head.addStretch(1)
        value_label = QLabel(f"{sensitivity:.2f}")
        value_label.setFont(px_font(20, bold=True, family="Consolas"))
        value_label.setStyleSheet("color: white;")
        head.addWidget(value_label)
        self.params_layout.addLayout(head)

        primary = theme_manager.get("primary_color")
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setFixedHeight(40)
        slider.setRange(1, 200)
        slider.setValue(int(sensitivity * 100))
        slider.setStyleSheet(f"""
            QSlider {{ background: transparent; }}
            QSlider::groove:horizontal {{ height: 8px; background: #2a2a2a; border-radius: 4px; }}
            QSlider::sub-page:horizontal {{ background: {primary}; border-radius: 4px; }}
            QSlider::handle:horizontal {{
                background: {theme_manager.get("primary_light")};
                border: 2px solid #111111;
                width: 28px; height: 28px; margin: -12px 0px; border-radius: 16px;
            }}
        """)
        slider.valueChanged.connect(lambda v: self._update_row_config(row_data, 'turn_sensitivity', v / 100.0))
        slider.valueChanged.connect(lambda v: value_label.setText(f"{v / 100.0:.2f}"))
        self.params_layout.addWidget(slider)
        self.foot_hint.setText(f"Uses both X and Y of {input_display_name(row_data['input'])} for tank steering")

    def _set_tracks_invert(self, row_data: Dict, key: str, checked: bool):
        """Apply a track invert flag to every differential_tracks mapping driving the same
        left/right channels, so the X and Y axis mappings always agree on motor polarity"""
        self._update_row_config(row_data, key, checked)

        left = row_data['config'].get('left_servo')
        right = row_data['config'].get('right_servo')
        if not left or not right:
            return

        for other in self.mapping_rows:
            if other is row_data:
                continue
            if (other['behavior'] == 'differential_tracks'
                    and other['config'].get('left_servo') == left
                    and other['config'].get('right_servo') == right):
                other['config'][key] = checked

    def _scene_combo(self, current: str, placeholder: str) -> QComboBox:
        return self._choice_combo({name: name for name in self.scene_names}, current, placeholder)

    def _create_scene_trigger_params(self, row_data: Dict):
        combo = self._scene_combo(row_data['config'].get('scene', ''), "Select scene…")
        combo.activated.connect(
            lambda i, c=combo: self._update_row_config(row_data, 'scene', c.itemData(i)) if c.itemData(i) else None)
        self._add_field("SCENE", combo)
        self._add_field("TRIGGER ON", self._timing_segment(row_data, ("on_press", "on_release", "continuous")))

    def _create_toggle_scenes_params(self, row_data: Dict):
        row = QHBoxLayout()
        row.setSpacing(12)
        for key, caption in (('scene_1', "SCENE 1"), ('scene_2', "SCENE 2")):
            combo = self._scene_combo(row_data['config'].get(key, ''), "Select scene…")
            combo.activated.connect(
                lambda i, c=combo, k=key: self._update_row_config(row_data, k, c.itemData(i)) if c.itemData(i) else None)
            self._add_field(caption, combo, row)
        self.params_layout.addLayout(row)
        self._add_field("TRIGGER ON", self._timing_segment(row_data))
        self.foot_hint.setText("Each press plays the other scene")

    def _create_nema_stepper_params(self, row_data: Dict):
        config = row_data['config']
        nema_config = self._get_nema_config()
        config['min_position'] = float(nema_config.get('min_position', 0.0))
        config['max_position'] = float(nema_config.get('max_position', 20.0))
        config['normal_speed'] = int(nema_config.get('normal_speed', 800))
        config['acceleration'] = int(nema_config.get('acceleration', 800))
        self._refresh_list_row(self.selected_row_index)

        mode_combo = self._choice_combo(NEMA_MODES, config.get('nema_behavior', ''), "Select mode…")
        mode_combo.activated.connect(lambda i, c=mode_combo: self._set_nema_mode(row_data, c.itemData(i)))
        self._add_field("MODE", mode_combo)

        info = QFrame()
        info.setObjectName("nema_info")
        info.setStyleSheet(
            f"QFrame#nema_info {{ background-color: {TILE_BG}; border: 1px solid #3a3a3a; border-radius: 8px; }}"
            "QLabel { background: transparent; border: none; }")
        grid = QGridLayout(info)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)
        items = [
            ("MIN", f"{config['min_position']:.1f} cm"),
            ("MAX", f"{config['max_position']:.1f} cm"),
            ("SPEED", f"{config['normal_speed']} steps/s"),
            ("ACCEL", f"{config['acceleration']} steps/s²"),
        ]
        for col, (caption, value) in enumerate(items):
            cap = QLabel(caption)
            cap.setFont(px_font(11, spacing=1.0))
            cap.setStyleSheet(f"color: {LABEL_GREY};")
            val = QLabel(value)
            val.setFont(px_font(14, bold=True, family="Consolas"))
            val.setStyleSheet("color: white;")
            grid.addWidget(cap, 0, col)
            grid.addWidget(val, 1, col)
        self._add_field("FROM SERVO CONFIG › NEMA", info)

        if config.get('nema_behavior', 'toggle_positions') == 'direct_control':
            self.params_layout.addWidget(self._invert_switch(
                config.get('invert', False),
                lambda checked: self._update_row_config(row_data, 'invert', checked)),
                0, Qt.AlignmentFlag.AlignLeft)
        else:
            self._add_field("TRIGGER ON", self._timing_segment(row_data))
        self.foot_hint.setText("Limits and speeds are set on the Servo screen")

    def _set_nema_mode(self, row_data: Dict, mode: str):
        if not mode:
            return
        self._update_row_config(row_data, 'nema_behavior', mode)
        self._create_behavior_parameters(row_data)

    def _get_nema_config(self):
        """Get NEMA configuration from servo config"""
        defaults = {"min_position": 0.0, "max_position": 20.0, "normal_speed": 800, "acceleration": 800}
        try:
            servo_config = config_manager.get_config(SERVO_CONFIG_PATH)
            return servo_config.get("nema", defaults)
        except Exception:
            return defaults

    def _create_system_control_params(self, row_data: Dict):
        action = row_data['config'].get('system_action', '')
        combo = self._choice_combo(SYSTEM_ACTIONS, action, "Select action…")
        combo.activated.connect(lambda i, c=combo: self._set_system_action(row_data, c.itemData(i)))
        self._add_field("ACTION", combo)
        self._add_field("TRIGGER ON", self._timing_segment(row_data))

        if action in SYSTEM_DESCRIPTIONS:
            self._add_note(SYSTEM_DESCRIPTIONS[action], theme_manager.get("green"))
        if action in ("restart_pi", "shutdown_pi"):
            self._add_note("This affects the whole Raspberry Pi", "#ff7777")
        elif action in ("exit_app", "restart_app"):
            self._add_note("Asks for confirmation before it runs")

    def _set_system_action(self, row_data: Dict, action: str):
        if not action:
            return
        self._update_row_config(row_data, 'system_action', action)
        self._create_behavior_parameters(row_data)

    def _create_imu_tilt_params(self, row_data: Dict):
        """Up to two servos, each with channel and invert; min / home / max are shown from the servo config"""
        servos = row_data['config'].setdefault('servos', [])
        try:
            servo_config = config_manager.get_config(SERVO_CONFIG_PATH) or {}
        except Exception:
            servo_config = {}
        header = QHBoxLayout()
        header.addWidget(self._caption("SERVOS · TILT MAPS MIN → HOME → MAX", track=False), 1)
        add_btn = QPushButton("+ ADD SERVO")
        add_btn.setFixedHeight(32)
        add_btn.setFont(px_font(12, bold=True))
        add_btn.setStyleSheet(outline_button_style(theme_manager.get("primary_color"),
                                                   theme_manager.get("primary_color")))
        add_btn.setEnabled(len(servos) < MAX_IMU_SERVOS)
        add_btn.clicked.connect(lambda: self._add_imu_servo(row_data))
        header.addWidget(add_btn)
        self.params_layout.addLayout(header)

        for index, servo in enumerate(servos):
            block = QFrame()
            block.setObjectName("imu_block")
            block.setStyleSheet(
                f"QFrame#imu_block {{ background-color: {ROW_BG}; border: 1px solid {DIVIDER}; border-radius: 10px; }}")
            block_layout = QVBoxLayout(block)
            block_layout.setContentsMargins(8, 8, 8, 8)
            block_layout.setSpacing(6)
            block_layout.addLayout(self._create_imu_servo_row(row_data, index, servo))
            pulses = QHBoxLayout()
            pulses.setSpacing(6)
            channel_config = servo_config.get(servo.get('channel', ''), {})
            if not isinstance(channel_config, dict):
                channel_config = {}
            for caption, key in (("MIN", "min"), ("HOME", "home"), ("MAX", "max")):
                pulses.addWidget(self._readout_tile(caption, channel_config.get(key)), 1)
            block_layout.addLayout(pulses)
            self.params_layout.addWidget(block)
        if not servos:
            self._add_note("No servos yet")
        self.foot_hint.setText("Active while the IMU is switched on")

    def _create_imu_servo_row(self, row_data: Dict, index: int, servo: Dict):
        row = QHBoxLayout()
        row.setSpacing(10)
        combo = self._servo_combo(servo.get('channel', ''), 40, 15)
        combo.activated.connect(
            lambda i, c=combo: self._update_imu_servo(row_data, index, 'channel', c.itemData(i) or ""))
        row.addWidget(combo, 1)
        row.addWidget(self._invert_switch(
            servo.get('invert', False),
            lambda checked: self._update_imu_servo(row_data, index, 'invert', checked)))
        remove = QPushButton("×")
        remove.setFixedSize(40, 40)
        remove.setFont(px_font(20))
        remove.setAccessibleName("Remove servo")
        remove.setStyleSheet(outline_button_style(theme_manager.get("red"), "#ff7777"))
        remove.clicked.connect(lambda: self._remove_imu_servo(row_data, index))
        row.addWidget(remove)
        return row

    def _update_imu_servo(self, row_data: Dict, index: int, key: str, value):
        servos = row_data['config'].get('servos', [])
        if index < len(servos):
            servos[index][key] = value
            self._mark_dirty()
            if key == 'channel':
                self._refresh_list_row(self.selected_row_index)
                self._create_behavior_parameters(row_data)

    def _add_imu_servo(self, row_data: Dict):
        servos = row_data['config'].setdefault('servos', [])
        if len(servos) < MAX_IMU_SERVOS:
            servos.append({'channel': '', 'invert': False})
            self._mark_dirty()
            self._create_behavior_parameters(row_data)

    def _remove_imu_servo(self, row_data: Dict, index: int):
        servos = row_data['config'].get('servos', [])
        if index < len(servos):
            servos.pop(index)
        self._mark_dirty()
        self._refresh_list_row(self.selected_row_index)
        self._create_behavior_parameters(row_data)

    def _create_imu_toggle_params(self, row_data: Dict):
        self._add_note(
            "IMU toggle is handled by the Steam Deck frontend. Map this behaviour to a "
            "button, save, and the Deck will detect it automatically on next connection.")

    # ========================================
    # SAVE
    # ========================================

    def _save_all_mappings(self):
        """Save all controller mappings to configuration"""
        self._check_for_conflicts()
        if any(row['conflict_detected'] for row in self.mapping_rows):
            self._refresh_all_rows()
            show_message(self, "CONTROLLER", "Conflicts detected",
                         "Resolve the joystick conflicts before saving.", kind="warning")
            return

        # List format supports multiple mappings per input
        controller_config = {}
        for row_data in self.mapping_rows:
            control_name = row_data['input']
            behavior = row_data['behavior']
            if control_name and behavior:
                entry = {'behavior': behavior, **row_data['config']}
                controller_config.setdefault(control_name, []).append(entry)

        try:
            config_manager.save_config(CONTROLLER_CONFIG_PATH, controller_config)
            if self.websocket and self.websocket.is_connected():
                if self.send_websocket_message("save_controller_config", config=controller_config):
                    self.logger.info("Controller config sent to backend")
                else:
                    self.logger.warning("Failed to send controller config to backend")
            else:
                self.logger.warning("WebSocket not connected - controller config not synced to backend")

            total_rows = sum(len(v) for v in controller_config.values())
            self._dirty = False
            self._update_dirty_label()
            show_message(self, "CONTROLLER", "Mappings saved",
                         f"Saved {total_rows} mappings across {len(controller_config)} inputs.")
            self.logger.info(f"Saved {total_rows} controller mappings")

        except Exception as e:
            show_message(self, "CONTROLLER", "Save failed",
                         "The controller mappings could not be saved.", kind="error", error=str(e))
            self.logger.error(f"Failed to save controller mappings: {e}")

    def cleanup(self):
        """Cleanup resources"""
        try:
            if hasattr(theme_manager, 'unregister_callback'):
                theme_manager.unregister_callback(self.update_theme)
        except Exception:
            pass