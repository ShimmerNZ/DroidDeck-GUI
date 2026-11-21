#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - Controller Input Test
Live Steam Deck input drawn in the Deck's own layout, with what each input is
mapped to. Robot input can be paused so buttons can be tried without moving
WALL-E: the link stays up and every input is sent at rest.
"""

from typing import Callable, Dict, List, Optional, Set, Tuple

from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QFrame, QGridLayout
from PyQt6.QtGui import QColor, QPainter, QPen, QFont
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer

from core.logger import get_logger
from core.theme_manager import theme_manager
from widgets.flow_dialog import (
    FlowDialog, LABEL_GREY, TEXT_SOFT, TILE_BG, WARN_ORANGE, px_font,
    _plain_button_style, _filled_button_style
)

UPDATE_INTERVAL_MS = 33
LAYOUT_WIDTH = 740
LAYOUT_HEIGHT = 440
SIDE_WIDTH = 360
ACTIVE_ROWS = 7
PRESS_THRESHOLD = 0.5
AXIS_ACTIVE = 0.05

BODY_FILL = "#151515"
WELL_FILL = "#141414"
KEY_FILL = "#2a2a2a"
OUTLINE = "#3e3e3e"
GRID_LINE = "#2e2e2e"
SCREEN_FILL = "#0e0e0e"
DIM_TEXT = "#6f6f6f"
STICK_REST = "#5a5a5a"
CONNECTED_GREEN = "#44bb44"
DISCONNECTED_RED = "#cc4444"

# Names for Deck inputs that cannot be mapped
EXTRA_NAMES = {
    "button_back": "View button",
    "button_guide": "Steam button",
    "button_quick_access": "Quick access button",
}

TOUCH_NAMES = {
    "left_stick": "Left stick touch",
    "right_stick": "Right stick touch",
    "left_pad": "Left pad touch",
    "right_pad": "Right pad touch",
}


def _text_on(fill: str) -> str:
    """Dark or light text, whichever reads better on the fill colour"""
    c = QColor(fill)
    luminance = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return "#111111" if luminance > 140 else "#ffffff"


def _trigger_fraction(value: float) -> float:
    """Trigger axis runs -1.0 released to +1.0 fully pressed"""
    return max(0.0, min(1.0, (value + 1.0) / 2.0))


class DeckLayoutWidget(QWidget):
    """Steam Deck controls drawn in their physical positions"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(LAYOUT_WIDTH, LAYOUT_HEIGHT)
        self.setAccessibleName("Steam Deck input layout")
        self._state: Optional[Dict] = None
        self._mapped: Set[str] = set()

    def set_state(self, state: Optional[Dict], mapped: Set[str]):
        self._state = state
        self._mapped = mapped
        self.update()

    # ---------- State helpers ----------

    def _button(self, name: str) -> bool:
        return bool(self._state and self._state["buttons"].get(name, False))

    def _axis(self, name: str) -> float:
        if not self._state:
            return 0.0
        return float(self._state["axes"].get(name, 0.0))

    def _touch(self, name: str) -> bool:
        return bool(self._state and self._state["touch"].get(name, False))

    # ---------- Drawing helpers ----------

    def _font(self, size: int, bold: bool = False, mono: bool = False) -> QFont:
        font = QFont("Consolas" if mono else "Arial")
        if mono:
            font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPixelSize(size)
        font.setBold(bold)
        return font

    def _text(self, p: QPainter, cx: float, y: float, text: str, color: str,
              size: int = 11, bold: bool = False, mono: bool = False):
        """Text centred on cx with its baseline at y"""
        p.setFont(self._font(size, bold, mono))
        p.setPen(QColor(color))
        rect = QRectF(cx - 150, y - size, 300, size + 4)
        p.drawText(rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, text)

    def _mapped_dot(self, p: QPainter, x: float, y: float, *controls: str):
        if any(c in self._mapped for c in controls):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(self._accent))
            p.drawEllipse(QPointF(x, y), 3.5, 3.5)

    def _key(self, p: QPainter, rect: QRectF, radius: float, label: str, pressed: bool,
             size: int = 11, bold: bool = False):
        p.setPen(Qt.PenStyle.NoPen if pressed else QPen(QColor(OUTLINE), 1))
        p.setBrush(QColor(self._accent if pressed else KEY_FILL))
        p.drawRoundedRect(rect, radius, radius)
        p.setFont(self._font(size, bold or pressed))
        p.setPen(QColor(_text_on(self._accent) if pressed else TEXT_SOFT))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

    # ---------- Paint ----------

    def paintEvent(self, event):
        self._accent = theme_manager.get("primary_color")
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.setPen(QPen(QColor(OUTLINE), 2))
        p.setBrush(QColor(BODY_FILL))
        p.drawRoundedRect(QRectF(10, 60, 720, 300), 80, 80)

        self._draw_trigger(p, 40, "L2", "left_trigger", 200, "left_trigger_btn")
        self._draw_trigger(p, 550, "R2", "right_trigger", 540, "right_trigger_btn")
        self._key(p, QRectF(40, 36, 150, 18), 9, "L1", self._button("shoulder_left"))
        self._mapped_dot(p, 200, 45, "shoulder_left")
        self._key(p, QRectF(550, 36, 150, 18), 9, "R1", self._button("shoulder_right"))
        self._mapped_dot(p, 540, 45, "shoulder_right")

        self._draw_dpad(p, 110, 120)
        self._draw_stick(p, 200, 175, "left", "stick_left_click", 44)
        self._draw_pad(p, 140, 280, "left", "button_left_pad", "L PAD")
        self._draw_face_buttons(p, 630, 120)
        self._draw_stick(p, 540, 175, "right", "stick_right_click", -44)
        self._draw_pad(p, 600, 280, "right", "button_right_pad", "R PAD")
        self._draw_imu(p)
        self._draw_centre_buttons(p)
        self._draw_grips(p)

        if self._state is None:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawRoundedRect(QRectF(10, 60, 720, 300), 80, 80)
            self._text(p, 370, 216, "No input from the Steam Deck controller", TEXT_SOFT, 16, bold=True)
        p.end()

    def _draw_trigger(self, p: QPainter, x: float, label: str, axis: str, dot_x: float, click: str):
        fraction = _trigger_fraction(self._axis(axis))
        rect = QRectF(x, 8, 150, 20)
        p.setPen(QPen(QColor(OUTLINE), 1))
        p.setBrush(QColor(WELL_FILL))
        p.drawRoundedRect(rect, 6, 6)
        if fraction > 0.0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(self._accent))
            p.drawRoundedRect(QRectF(x, 8, max(12.0, 150 * fraction), 20), 6, 6)
        pressed = fraction >= PRESS_THRESHOLD
        p.setFont(self._font(12, pressed))
        p.setPen(QColor(_text_on(self._accent) if pressed else LABEL_GREY))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{label}  {round(fraction * 100)}%")
        self._mapped_dot(p, dot_x, 18, axis, click)

    def _draw_dpad(self, p: QPainter, cx: float, cy: float):
        directions = {
            "dpad_up": QRectF(cx - 12, cy - 36, 24, 24),
            "dpad_down": QRectF(cx - 12, cy + 12, 24, 24),
            "dpad_left": QRectF(cx - 36, cy - 12, 24, 24),
            "dpad_right": QRectF(cx + 12, cy - 12, 24, 24),
        }
        p.setPen(QPen(QColor(OUTLINE), 1))
        p.setBrush(QColor(KEY_FILL))
        p.drawRoundedRect(QRectF(cx - 12, cy - 36, 24, 72), 4, 4)
        p.drawRoundedRect(QRectF(cx - 36, cy - 12, 72, 24), 4, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self._accent))
        for name, rect in directions.items():
            if self._button(name):
                p.drawRoundedRect(rect, 4, 4)
        self._mapped_dot(p, cx, cy - 48, *directions.keys())
        self._text(p, cx, cy + 56, "D-PAD", LABEL_GREY)

    def _draw_stick(self, p: QPainter, cx: float, cy: float, side: str, click: str, dot_dx: float):
        x = self._axis(f"{side}_stick_x")
        y = self._axis(f"{side}_stick_y")
        clicked = self._button(click)
        p.setPen(QPen(QColor(self._accent if clicked else OUTLINE), 2))
        p.setBrush(QColor(WELL_FILL))
        p.drawEllipse(QPointF(cx, cy), 34, 34)
        p.setPen(QPen(QColor(GRID_LINE), 1))
        p.drawLine(QPointF(cx - 34, cy), QPointF(cx + 34, cy))
        p.drawLine(QPointF(cx, cy - 34), QPointF(cx, cy + 34))
        moved = abs(x) > AXIS_ACTIVE or abs(y) > AXIS_ACTIVE
        touched = self._touch(f"{side}_stick")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(TEXT_SOFT if (moved or touched) else STICK_REST))
        p.drawEllipse(QPointF(cx + x * 23, cy - y * 23), 11, 11)
        self._mapped_dot(p, cx + dot_dx, cy - 30, f"{side}_stick_x", f"{side}_stick_y", click)
        self._text(p, cx, cy + 54, f"{x:+.2f}  {y:+.2f}", LABEL_GREY, mono=True)

    def _draw_pad(self, p: QPainter, cx: float, cy: float, side: str, click: str, label: str):
        touched = self._touch(f"{side}_pad")
        pressed = self._button(click)
        rect = QRectF(cx - 45, cy - 45, 90, 90)
        p.setPen(QPen(QColor(self._accent if (touched or pressed) else OUTLINE), 2))
        p.setBrush(QColor(self._accent if pressed else WELL_FILL))
        p.drawRoundedRect(rect, 14, 14)
        if touched and self._state:
            px = self._state["trackpads"].get(f"{side}_trackpad_x", 0.0)
            py = self._state["trackpads"].get(f"{side}_trackpad_y", 0.0)
            point = QPointF(cx + px * 36, cy - py * 36)
            dot = _text_on(self._accent) if pressed else self._accent
            p.setPen(QPen(QColor(dot), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(point, 9, 9)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(dot))
            p.drawEllipse(point, 3, 3)
        self._mapped_dot(p, cx + 52, cy - 38, click)
        state = "click" if pressed else ("touch" if touched else "")
        self._text(p, cx, cy + 62, f"{label}  {state}".strip(), TEXT_SOFT if state else LABEL_GREY)

    def _draw_face_buttons(self, p: QPainter, cx: float, cy: float):
        buttons = (("Y", "button_y", 0, -24), ("X", "button_x", -24, 0),
                   ("B", "button_b", 24, 0), ("A", "button_a", 0, 24))
        for label, name, dx, dy in buttons:
            pressed = self._button(name)
            p.setPen(Qt.PenStyle.NoPen if pressed else QPen(QColor(OUTLINE), 1))
            p.setBrush(QColor(self._accent if pressed else KEY_FILL))
            centre = QPointF(cx + dx, cy + dy)
            p.drawEllipse(centre, 15, 15)
            p.setFont(self._font(12, True))
            p.setPen(QColor(_text_on(self._accent) if pressed else TEXT_SOFT))
            p.drawText(QRectF(centre.x() - 15, centre.y() - 15, 30, 30), Qt.AlignmentFlag.AlignCenter, label)
            if name in self._mapped:
                self._mapped_dot(p, cx + dx * 1.6 + (8 if dx == 0 else 0), cy + dy * 1.6 + (8 if dy == 0 else 0), name)

    def _draw_imu(self, p: QPainter):
        roll = self._axis("imu_roll")
        pitch = self._axis("imu_pitch")
        imu_on = bool(self._state and self._state.get("imu_enabled"))
        p.setPen(QPen(QColor(GRID_LINE), 1))
        p.setBrush(QColor(SCREEN_FILL))
        p.drawRoundedRect(QRectF(250, 90, 240, 180), 10, 10)
        self._text(p, 370, 112, "IMU TILT  ON" if imu_on else "IMU TILT  OFF (from flat)",
                   self._accent if imu_on else LABEL_GREY, 11, bold=imu_on)
        dashed = QPen(QColor(GRID_LINE), 1)
        dashed.setStyle(Qt.PenStyle.DashLine)
        p.setPen(dashed)
        p.drawLine(QPointF(270, 180), QPointF(470, 180))

        p.save()
        p.translate(370, 180 + pitch * 50)
        p.rotate(-roll * 45)
        p.setPen(QPen(QColor(self._accent if imu_on else LABEL_GREY), 3, cap=Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(-95, 0), QPointF(95, 0))
        p.restore()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self._accent if imu_on else LABEL_GREY))
        p.drawEllipse(QPointF(370, 180 + pitch * 50), 5, 5)
        self._mapped_dot(p, 480, 100, "imu_roll", "imu_pitch")
        self._text(p, 370, 256, f"roll {roll:+.2f}   pitch {pitch:+.2f}", TEXT_SOFT, 13, mono=True)

    def _draw_centre_buttons(self, p: QPainter):
        self._key(p, QRectF(268, 292, 44, 18), 9, "VIEW", self._button("button_back"), size=10)
        self._key(p, QRectF(428, 292, 44, 18), 9, "MENU", self._button("button_menu"), size=10)
        self._mapped_dot(p, 480, 301, "button_menu")
        self._key(p, QRectF(318, 320, 48, 18), 9, "STEAM", self._button("button_guide"), size=10)
        self._key(p, QRectF(374, 320, 48, 18), 9, "QUICK", self._button("button_quick_access"), size=10)

    def _draw_grips(self, p: QPainter):
        self._text(p, 370, 384, "BACK GRIPS", LABEL_GREY, 11)
        grips = (("L4 upper", "grip_left_upper", 60), ("L5 lower", "grip_left_lower", 150),
                 ("R4 upper", "grip_right_upper", 510), ("R5 lower", "grip_right_lower", 600))
        for label, name, x in grips:
            self._key(p, QRectF(x, 372, 80, 22), 6, label, self._button(name))
            self._mapped_dot(p, x + 40, 404, name)
        self._text(p, 370, 428, "Stick and pad clicks light the stick or pad outline", DIM_TEXT, 11)


class InputTesterDialog(FlowDialog):
    """Live Deck input with the mapping for each input"""

    def __init__(self, parent, controller_thread,
                 display_name: Callable[[str], str],
                 describe_mapping: Callable[[str], str],
                 mapped_controls: Callable[[], Set[str]]):
        super().__init__(parent, "CONTROLLER INPUT TEST",
                         "Press anything to see what it is mapped to", width=1180)
        self.logger = get_logger("controller")
        self.controller_thread = controller_thread
        self._display_name = display_name
        self._describe_mapping = describe_mapping
        self._mapped = mapped_controls()
        self._previous: Optional[Dict] = None
        self._last_control: Optional[str] = None
        self._sent_marks: List[Tuple[float, int]] = []
        self._elapsed = 0.0

        self._build_body()
        self._build_buttons()
        self._refresh_pause()

        self._timer = QTimer(self)
        self._timer.setInterval(UPDATE_INTERVAL_MS)
        self._timer.timeout.connect(self._update_values)
        self._timer.start()
        self._update_values()

    # ---------- Layout ----------

    def _tile(self, highlight: bool = False) -> QFrame:
        tile = QFrame()
        tile.setObjectName("tester_tile")
        border = theme_manager.get("primary_color") if highlight else "#2e2e2e"
        tile.setStyleSheet(
            f"QFrame#tester_tile {{ background-color: {TILE_BG}; border: 1px solid {border}; border-radius: 10px; }}"
            "QLabel { background: transparent; border: none; }")
        return tile

    def _label(self, text: str = "", size: int = 13, color: str = LABEL_GREY,
               bold: bool = False, mono: bool = False) -> QLabel:
        label = QLabel(text)
        label.setFont(px_font(size, bold=bold, family="Consolas" if mono else "Arial"))
        label.setStyleSheet(f"color: {color};")
        return label

    def _card_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setFont(px_font(12, bold=True, spacing=2.0))
        label.setStyleSheet(f"color: {LABEL_GREY};")
        return label

    def _build_body(self):
        primary = theme_manager.get("primary_color")

        legend = QHBoxLayout()
        legend.setSpacing(18)
        legend.addStretch(1)
        for text, style in (("Pressed", f"background-color: {primary}; border-radius: 3px;"),
                            ("Mapped", f"background-color: {primary}; border-radius: 4px;"),
                            ("Not mapped", "border: 1px solid #4a4a4a; border-radius: 3px;")):
            item = QHBoxLayout()
            item.setSpacing(6)
            swatch = QFrame()
            size = 8 if text == "Mapped" else 12
            swatch.setFixedSize(size, size)
            swatch.setStyleSheet(style)
            item.addWidget(swatch)
            item.addWidget(self._label(text))
            legend.addLayout(item)
        self.body_layout.addLayout(legend)

        row = QHBoxLayout()
        row.setSpacing(18)

        layout_tile = self._tile()
        tile_layout = QVBoxLayout(layout_tile)
        tile_layout.setContentsMargins(12, 12, 12, 12)
        self.deck_layout = DeckLayoutWidget()
        tile_layout.addWidget(self.deck_layout, 0, Qt.AlignmentFlag.AlignCenter)
        row.addWidget(layout_tile)

        side = QVBoxLayout()
        side.setSpacing(12)
        side.addWidget(self._build_link_card())
        side.addWidget(self._build_last_card())
        side.addWidget(self._build_active_card(), 1)
        side_holder = QWidget()
        side_holder.setFixedWidth(SIDE_WIDTH)
        side_holder.setLayout(side)
        side.setContentsMargins(0, 0, 0, 0)
        row.addWidget(side_holder)

        self.body_layout.addLayout(row)

    def _build_link_card(self) -> QFrame:
        card = self._tile()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(self._card_title("LINK"))

        status = QHBoxLayout()
        status.setSpacing(8)
        self._link_dot = QFrame()
        self._link_dot.setFixedSize(10, 10)
        self._link_text = self._label("", 16, TEXT_SOFT)
        status.addWidget(self._link_dot)
        status.addWidget(self._link_text, 1)
        layout.addLayout(status)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        self._link_values = {}
        for i, (key, caption) in enumerate((("rate", "Frames to robot"), ("sent", "Frames sent"),
                                            ("backend", "Backend"))):
            grid.addWidget(self._label(caption), i, 0)
            value = self._label("--", 13, TEXT_SOFT, mono=True)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(value, i, 1)
            self._link_values[key] = value
        layout.addLayout(grid)
        return card

    def _build_last_card(self) -> QFrame:
        card = self._tile(highlight=True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        layout.addWidget(self._card_title("LAST INPUT"))
        self._last_name = self._label("Press any control", 22, theme_manager.get("primary_color"), bold=True)
        self._last_name.setWordWrap(True)
        layout.addWidget(self._last_name)
        self._last_config = self._label("")
        layout.addWidget(self._last_config)
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: #2e2e2e; border: none;")
        layout.addWidget(divider)
        layout.addWidget(self._label("Mapped to"))
        self._last_mapping = self._label("--", 16, TEXT_SOFT)
        self._last_mapping.setWordWrap(True)
        layout.addWidget(self._last_mapping)
        return card

    def _build_active_card(self) -> QFrame:
        card = self._tile()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(self._card_title("ACTIVE NOW"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(7)
        self._active_rows = []
        for i in range(ACTIVE_ROWS):
            name = self._label("", 13, TEXT_SOFT)
            mapping = self._label("")
            mapping.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(name, i, 0)
            grid.addWidget(mapping, i, 1)
            self._active_rows.append((name, mapping))
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch(1)
        return card

    def _build_buttons(self):
        self._hint = self._label("", 13)
        self._hint.setWordWrap(True)
        self.buttons.addWidget(self._hint, 1)
        self._pause_button = QPushButton()
        self._pause_button.setFixedHeight(44)
        self._pause_button.setMinimumWidth(230)
        self._pause_button.setFont(px_font(15, bold=True))
        self._pause_button.clicked.connect(self._toggle_pause)
        self.buttons.addWidget(self._pause_button)
        close_button = QPushButton("CLOSE")
        close_button.setFixedHeight(44)
        close_button.setMinimumWidth(130)
        close_button.setFont(px_font(15, bold=True))
        close_button.setStyleSheet(_filled_button_style(theme_manager.get("primary_color")))
        close_button.clicked.connect(self.reject)
        self.buttons.addWidget(close_button)

    # ---------- Pause ----------

    def _toggle_pause(self):
        self.controller_thread.set_robot_input_paused(not self.controller_thread.robot_input_paused)
        self._refresh_pause()

    def _refresh_pause(self):
        paused = self.controller_thread.robot_input_paused
        if paused:
            self._pause_button.setText("RESUME ROBOT INPUT")
            self._pause_button.setStyleSheet(_filled_button_style(WARN_ORANGE))
            self._hint.setText("Robot input paused: WALL-E is sent every control at rest.")
            self._hint.setStyleSheet(f"color: {WARN_ORANGE};")
        else:
            self._pause_button.setText("PAUSE ROBOT INPUT")
            self._pause_button.setStyleSheet(_plain_button_style())
            self._hint.setText("Inputs are still sent to the robot while this is open.")
            self._hint.setStyleSheet(f"color: {LABEL_GREY};")

    # ---------- Names ----------

    def _name(self, control: str) -> str:
        if control in EXTRA_NAMES:
            return EXTRA_NAMES[control]
        if control.startswith("touch:"):
            return TOUCH_NAMES[control[6:]]
        return self._display_name(control)

    def _mapping_text(self, control: str) -> Tuple[str, str]:
        """Mapping description and its colour"""
        if control.startswith("touch:"):
            return "Touch only, not mappable", LABEL_GREY
        if control in EXTRA_NAMES:
            return "Not mappable", LABEL_GREY
        text = self._describe_mapping(control)
        return (text, LABEL_GREY) if text else ("Not mapped", WARN_ORANGE)

    # ---------- Live values ----------

    def _update_values(self):
        state = self.controller_thread.get_input_snapshot()
        self.deck_layout.set_state(state, self._mapped)
        self._update_link(state is not None)
        if state is None:
            self._previous = None
            for name, mapping in self._active_rows:
                name.setText("")
                mapping.setText("")
            return
        self._update_last_input(state)
        self._update_active(state)
        self._previous = state

    def _update_link(self, connected: bool):
        self._link_dot.setStyleSheet(
            f"background-color: {CONNECTED_GREEN if connected else DISCONNECTED_RED}; border-radius: 5px;")
        self._link_text.setText("Steam Deck connected" if connected else "Controller not detected")

        self._elapsed += UPDATE_INTERVAL_MS / 1000.0
        sent = self.controller_thread.stats.get("inputs_sent", 0)
        self._sent_marks.append((self._elapsed, sent))
        while len(self._sent_marks) > 2 and self._elapsed - self._sent_marks[0][0] > 1.0:
            self._sent_marks.pop(0)
        span = self._elapsed - self._sent_marks[0][0]
        rate = (sent - self._sent_marks[0][1]) / span if span > 0 else 0.0
        self._link_values["rate"].setText(f"{rate:.1f}/s")
        self._link_values["sent"].setText(f"{sent:,}")

        websocket = getattr(self.controller_thread, "websocket_manager", None)
        online = bool(websocket and websocket.is_connected())
        backend = self._link_values["backend"]
        if not online:
            backend.setText("not connected")
            backend.setStyleSheet(f"color: {DISCONNECTED_RED};")
        elif self.controller_thread.robot_input_paused:
            backend.setText("paused, at rest")
            backend.setStyleSheet(f"color: {WARN_ORANGE};")
        else:
            backend.setText("receiving")
            backend.setStyleSheet(f"color: {TEXT_SOFT};")

    def _newly_active(self, state: Dict) -> Optional[str]:
        """The control that has just been pressed or moved past halfway"""
        previous = self._previous
        if previous is None:
            return None
        for name, pressed in state["buttons"].items():
            if pressed and not previous["buttons"].get(name, False):
                return name
        for side in ("left", "right"):
            key = f"{side}_trigger"
            if (_trigger_fraction(state["axes"].get(key, -1.0)) >= PRESS_THRESHOLD
                    > _trigger_fraction(previous["axes"].get(key, -1.0))):
                return key
            x, y = (abs(state["axes"].get(f"{side}_stick_{a}", 0.0)) for a in ("x", "y"))
            px, py = (abs(previous["axes"].get(f"{side}_stick_{a}", 0.0)) for a in ("x", "y"))
            if max(x, y) >= PRESS_THRESHOLD > max(px, py):
                return f"{side}_stick_x" if x >= y else f"{side}_stick_y"
        for touch, on in state["touch"].items():
            if on and not previous["touch"].get(touch, False) and touch.endswith("pad"):
                return f"touch:{touch}"
        return None

    def _update_last_input(self, state: Dict):
        control = self._newly_active(state)
        if control is None or control == self._last_control:
            return
        self._last_control = control
        self._last_name.setText(self._name(control))
        if control.startswith("touch:") or control in EXTRA_NAMES:
            self._last_config.setText("")
        else:
            self._last_config.setText(f"Config name  {control}")
        text, color = self._mapping_text(control)
        self._last_mapping.setText(text)
        self._last_mapping.setStyleSheet(f"color: {WARN_ORANGE if color == WARN_ORANGE else TEXT_SOFT};")

    def _active_controls(self, state: Dict) -> List[Tuple[str, str]]:
        """(control, value label) for everything currently held or moved"""
        active = []
        for name, pressed in state["buttons"].items():
            if pressed:
                active.append((name, ""))
        axes = state["axes"]
        for side in ("left", "right"):
            fraction = _trigger_fraction(axes.get(f"{side}_trigger", -1.0))
            if fraction > AXIS_ACTIVE:
                active.append((f"{side}_trigger", f"{round(fraction * 100)}%"))
        for side in ("left", "right"):
            for axis in ("x", "y"):
                value = axes.get(f"{side}_stick_{axis}", 0.0)
                if abs(value) > AXIS_ACTIVE:
                    active.append((f"{side}_stick_{axis}", f"{value:+.2f}"))
        if state.get("imu_enabled"):
            for axis in ("imu_roll", "imu_pitch"):
                value = axes.get(axis, 0.0)
                if abs(value) > AXIS_ACTIVE:
                    active.append((axis, f"{value:+.2f}"))
        for touch in ("left_pad", "right_pad"):
            if state["touch"].get(touch):
                active.append((f"touch:{touch}", ""))
        return active

    def _update_active(self, state: Dict):
        active = self._active_controls(state)
        overflow = len(active) - ACTIVE_ROWS
        shown = active[:ACTIVE_ROWS - 1] if overflow > 0 else active
        for i, (name_label, mapping_label) in enumerate(self._active_rows):
            name_label.setStyleSheet(f"color: {TEXT_SOFT if active else LABEL_GREY};")
            mapping_label.setText("")
            if i < len(shown):
                control, value = shown[i]
                name_label.setText(f"{self._name(control)}  {value}".strip())
                text, color = self._mapping_text(control)
                mapping_label.setText(text)
                mapping_label.setStyleSheet(f"color: {color};")
            elif i == len(shown) and overflow > 0:
                name_label.setText(f"+{overflow + 1} more")
            else:
                name_label.setText("Nothing held" if i == 0 and not active else "")

    def done(self, result):
        self._timer.stop()
        if self.controller_thread.robot_input_paused:
            self.controller_thread.set_robot_input_paused(False)
        super().done(result)
