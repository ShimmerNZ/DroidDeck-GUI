#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - IMU Calibration Dialog
Live tilt bars for the Steam Deck accelerometer, plus a recording mode that
keeps the furthest tilt reached on each side and saves it as the full-travel
limit used by IMU tilt.
"""

from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QFrame
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtCore import Qt, QRectF, QTimer

from core.config_manager import config_manager
from core.logger import get_logger
from core.theme_manager import theme_manager
from threads.steamdeck import (
    ACCEL_MAX, IMU_DEADZONE, IMU_CALIBRATION_PATH, IMU_LIMIT_KEYS, IMU_LIMIT_MAX
)
from widgets.flow_dialog import (
    FlowDialog, LABEL_GREY, TEXT_SOFT, TILE_BG, px_font, ask_confirm,
    _plain_button_style, _filled_button_style
)

UPDATE_INTERVAL_MS = 33
SMOOTHING = 0.35
REACHED_G = 0.25
TRACK_BG = "#141414"
TRACK_BORDER = "#3e3e3e"
LIMIT_MARK = "#ffffff"

# sign is applied to the raw axis so that a tilt to the left side of the bar reads negative
AXES = (
    {
        "name": "Roll", "hint": "tilt left / right", "raw": "accel_x", "axis": "roll", "sign": -1,
        "low_key": "roll_left", "high_key": "roll_right", "low_word": "left", "high_word": "right",
    },
    {
        "name": "Pitch", "hint": "tilt forward / back", "raw": "accel_y", "axis": "pitch", "sign": 1,
        "low_key": "pitch_forward", "high_key": "pitch_back", "low_word": "forward", "high_word": "back",
    },
)


class TiltBar(QWidget):
    """Centred bar: live fill from level, deadzone band, limit marks and recorded range"""

    def __init__(self, height: int = 30, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self._value = 0.0
        self._low_limit = None
        self._high_limit = None
        self._low_peak = 0.0
        self._high_peak = 0.0
        self._recording = False
        self._show_deadzone = True

    def set_value(self, value: float):
        self._value = max(-1.0, min(1.0, value))
        self.update()

    def set_limits(self, low, high):
        self._low_limit = low
        self._high_limit = high
        self.update()

    def set_peaks(self, low: float, high: float):
        self._low_peak = low
        self._high_peak = high
        self.update()

    def set_recording(self, recording: bool):
        self._recording = recording
        self.update()

    def set_show_deadzone(self, show: bool):
        self._show_deadzone = show
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        margin = 4
        track = QRectF(1, margin, self.width() - 2, self.height() - 2 * margin)
        centre = track.center().x()
        half = track.width() / 2.0

        painter.setPen(QPen(QColor(TRACK_BORDER), 1))
        painter.setBrush(QColor(TRACK_BG))
        painter.drawRoundedRect(track, 6, 6)
        painter.setPen(Qt.PenStyle.NoPen)

        inner_top = track.top() + 3
        inner_height = track.height() - 6

        if self._recording:
            shade = QColor(theme_manager.get("green"))
            shade.setAlphaF(0.25)
            low = min(1.0, self._low_peak)
            high = min(1.0, self._high_peak)
            painter.setBrush(shade)
            painter.drawRect(QRectF(centre - low * half, inner_top, (low + high) * half, inner_height))
        elif self._show_deadzone:
            low = (self._low_limit if self._low_limit is not None else 1.0) * IMU_DEADZONE
            high = (self._high_limit if self._high_limit is not None else 1.0) * IMU_DEADZONE
            painter.setBrush(QColor("#2c2c2c"))
            painter.drawRect(QRectF(centre - low * half, inner_top, (low + high) * half, inner_height))

        fill = QColor(theme_manager.get("primary_color"))
        painter.setBrush(fill)
        if self._value >= 0:
            painter.drawRect(QRectF(centre, inner_top, self._value * half, inner_height))
        else:
            painter.drawRect(QRectF(centre + self._value * half, inner_top, -self._value * half, inner_height))

        painter.setBrush(QColor("#ffffff"))
        painter.drawRect(QRectF(centre - 1, track.top(), 2, track.height()))

        if self._recording:
            mark = QColor(theme_manager.get("green"))
            marks = (
                -self._low_peak if self._low_peak >= REACHED_G else None,
                self._high_peak if self._high_peak >= REACHED_G else None,
            )
        else:
            mark = QColor(LIMIT_MARK)
            marks = (
                -self._low_limit if self._low_limit is not None else None,
                self._high_limit if self._high_limit is not None else None,
            )
        painter.setBrush(mark)
        for position in marks:
            if position is None:
                continue
            x = centre + max(-1.0, min(1.0, position)) * half
            x = max(track.left() + 1.5, min(track.right() - 1.5, x))
            painter.drawRoundedRect(QRectF(x - 1.5, 0, 3, self.height()), 1.5, 1.5)
        painter.end()


class ImuCalibrationDialog(FlowDialog):
    """Live IMU bars with a recording mode that saves the tilt limits"""

    def __init__(self, parent, controller_thread):
        super().__init__(parent, "IMU CALIBRATION", "", width=760)
        self.logger = get_logger("controller")
        self.controller_thread = controller_thread
        self._recording = False
        self._smoothed = None
        self._zero = None
        self._limits = self.controller_thread.get_imu_calibration()
        self._peaks = {key: 0.0 for key in IMU_LIMIT_KEYS}
        self._rows = []

        self._build_body()
        self._show_idle_buttons()
        self._refresh_limits()
        self._refresh_status()

        self._timer = QTimer(self)
        self._timer.setInterval(UPDATE_INTERVAL_MS)
        self._timer.timeout.connect(self._update_values)
        self._timer.start()

    # ---------- Layout ----------

    def _build_body(self):
        primary = theme_manager.get("primary_color")

        status_col = QVBoxLayout()
        status_col.setSpacing(8)
        self._status_label = QLabel("")
        self._status_label.setFont(px_font(13))
        self._status_label.setStyleSheet(f"color: {LABEL_GREY};")
        status_col.addWidget(self._status_label)
        track = QFrame()
        track.setObjectName("bar_track")
        track.setFixedHeight(8)
        track.setStyleSheet("QFrame#bar_track { background-color: #2a2a2a; border-radius: 4px; }")
        self._bar_fill = QFrame(track)
        self._bar_fill.setStyleSheet(f"background-color: {primary}; border-radius: 4px;")
        self._bar_fill.setGeometry(0, 0, 0, 8)
        self._bar_track = track
        self._bar_fraction = 0.0
        status_col.addWidget(track)
        self.body_layout.addLayout(status_col)

        for axis in AXES:
            self.body_layout.addWidget(self._build_axis_tile(axis))
        self.body_layout.addWidget(self._build_vertical_tile())

        self._hint_label = QLabel("")
        self._hint_label.setFont(px_font(13))
        self._hint_label.setStyleSheet(f"color: {TEXT_SOFT};")
        self._hint_label.setWordWrap(True)
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setMinimumHeight(36)
        self.body_layout.addWidget(self._hint_label)

    def _tile(self) -> QFrame:
        tile = QFrame()
        tile.setObjectName("imu_tile")
        tile.setStyleSheet(
            f"QFrame#imu_tile {{ background-color: {TILE_BG}; border: 1px solid #2e2e2e; border-radius: 8px; }}"
            "QLabel { background: transparent; border: none; }")
        return tile

    def _build_axis_tile(self, axis: dict) -> QFrame:
        primary = theme_manager.get("primary_color")
        tile = self._tile()
        layout = QVBoxLayout(tile)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(10)
        name = QLabel(axis["name"])
        name.setFont(px_font(16, bold=True))
        name.setStyleSheet("color: white;")
        hint = QLabel(axis["hint"])
        hint.setFont(px_font(13))
        hint.setStyleSheet(f"color: {LABEL_GREY};")
        note = QLabel("")
        note.setFont(px_font(13))
        note.setStyleSheet(f"color: {LABEL_GREY};")
        note.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value = QLabel("--")
        value.setFont(px_font(20, bold=True, family="Consolas"))
        value.setStyleSheet(f"color: {primary};")
        value.setFixedWidth(190)
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(name)
        top.addWidget(hint)
        top.addWidget(note, 1)
        top.addWidget(value)
        layout.addLayout(top)

        bar = TiltBar(30)
        layout.addWidget(bar)

        scale = QHBoxLayout()
        low_label = QLabel("")
        level_label = QLabel("level")
        high_label = QLabel("")
        for label, alignment in ((low_label, Qt.AlignmentFlag.AlignLeft),
                                 (level_label, Qt.AlignmentFlag.AlignHCenter),
                                 (high_label, Qt.AlignmentFlag.AlignRight)):
            label.setFont(px_font(12))
            label.setStyleSheet(f"color: {LABEL_GREY};")
            label.setAlignment(alignment | Qt.AlignmentFlag.AlignVCenter)
            scale.addWidget(label, 1)
        layout.addLayout(scale)

        self._rows.append({
            "axis": axis, "bar": bar, "value": value, "note": note,
            "low_label": low_label, "high_label": high_label,
        })
        return tile

    def _build_vertical_tile(self) -> QFrame:
        primary = theme_manager.get("primary_color")
        tile = self._tile()
        layout = QHBoxLayout(tile)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(16)

        names = QVBoxLayout()
        names.setSpacing(2)
        name = QLabel("Vertical")
        name.setFont(px_font(16, bold=True))
        name.setStyleSheet("color: white;")
        hint = QLabel("display only")
        hint.setFont(px_font(12))
        hint.setStyleSheet(f"color: {LABEL_GREY};")
        names.addWidget(name)
        names.addWidget(hint)
        holder = QWidget()
        holder.setFixedWidth(130)
        holder.setLayout(names)
        layout.addWidget(holder)

        self._vertical_bar = TiltBar(24)
        self._vertical_bar.set_show_deadzone(False)
        layout.addWidget(self._vertical_bar, 1)

        self._vertical_value = QLabel("--")
        self._vertical_value.setFont(px_font(18, bold=True, family="Consolas"))
        self._vertical_value.setStyleSheet(f"color: {primary};")
        self._vertical_value.setFixedWidth(110)
        self._vertical_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._vertical_value)
        return tile

    def _make_button(self, text: str, handler, filled: bool = False, width: int = 130) -> QPushButton:
        button = QPushButton(text)
        button.setFixedHeight(44)
        button.setMinimumWidth(width)
        button.setFont(px_font(15, bold=True))
        if filled:
            button.setStyleSheet(_filled_button_style(theme_manager.get("primary_color")))
        else:
            button.setStyleSheet(_plain_button_style())
        button.clicked.connect(handler)
        return button

    def _show_idle_buttons(self):
        self._clear(self.buttons)
        self.buttons.addWidget(self._make_button("CLOSE", self.reject))
        self.buttons.addWidget(self._make_button("RESET", self._reset_to_defaults))
        self.buttons.addStretch(1)
        self._start_button = self._make_button("START CALIBRATION", self._start_recording, filled=True, width=210)
        self.buttons.addWidget(self._start_button)

    def _show_recording_buttons(self):
        self._clear(self.buttons)
        self._start_button = None
        self.buttons.addWidget(self._make_button("CANCEL", self._cancel_recording))
        self.buttons.addWidget(self._make_button("START AGAIN", self._start_recording, width=150))
        self.buttons.addStretch(1)
        self.buttons.addWidget(self._make_button("FINISH AND SAVE", self._finish_recording, filled=True, width=210))

    # ---------- Live values ----------

    def _update_values(self):
        raw = self.controller_thread.get_imu_raw()
        if raw is None:
            self._smoothed = None
            for row in self._rows:
                row["value"].setText("--")
                row["bar"].set_value(0.0)
            self._vertical_value.setText("--")
            self._vertical_bar.set_value(0.0)
            if not self._recording:
                self._status_label.setText("No IMU data from the Steam Deck")
                if self._start_button is not None:
                    self._start_button.setEnabled(False)
            return

        sample = {key: float(raw.get(key, 0)) for key in ("accel_x", "accel_y", "accel_z")}
        if self._smoothed is None:
            self._smoothed = sample
            if not self._recording:
                self._refresh_status()
                if self._start_button is not None:
                    self._start_button.setEnabled(True)
        else:
            for key, value in sample.items():
                self._smoothed[key] += SMOOTHING * (value - self._smoothed[key])
        if self._zero is None:
            self._zero = dict(self._smoothed)

        for row in self._rows:
            axis = row["axis"]
            counts = self._smoothed[axis["raw"]] - self._zero[axis["raw"]]
            position = axis["sign"] * counts / ACCEL_MAX
            row["bar"].set_value(position)
            magnitude = abs(position)
            if magnitude < 0.005:
                row["value"].setText("0.00 g")
            else:
                word = axis["low_word"] if position < 0 else axis["high_word"]
                row["value"].setText(f"{magnitude:.2f} g {word}")

            if self._recording:
                low_key, high_key = axis["low_key"], axis["high_key"]
                self._peaks[low_key] = max(self._peaks[low_key], -position)
                self._peaks[high_key] = max(self._peaks[high_key], position)
                row["bar"].set_peaks(self._peaks[low_key], self._peaks[high_key])
            else:
                output = self.controller_thread.imu_axis_output(axis["axis"], counts)
                row["note"].setText(f"Output {output:+.2f}")

        vertical = self._smoothed["accel_z"] / ACCEL_MAX
        self._vertical_bar.set_value(vertical)
        self._vertical_value.setText(f"{vertical:+.2f} g")

        if self._recording:
            self._refresh_recording()
        self._resize_bar()

    def _refresh_limits(self):
        """Show the saved limits on the bars and under them"""
        for row in self._rows:
            axis = row["axis"]
            low = self._limits[axis["low_key"]] / ACCEL_MAX
            high = self._limits[axis["high_key"]] / ACCEL_MAX
            row["bar"].set_recording(False)
            row["bar"].set_limits(low, high)
            row["low_label"].setText(f"{axis['low_word'].capitalize()} limit {low:.2f} g")
            row["high_label"].setText(f"{axis['high_word'].capitalize()} limit {high:.2f} g")
            row["note"].setStyleSheet(f"color: {LABEL_GREY};")

    def _refresh_status(self):
        calibrated = any(self._limits[key] != ACCEL_MAX for key in IMU_LIMIT_KEYS)
        if calibrated:
            self._status_label.setText("Calibration saved")
            self._set_bar(1.0)
        else:
            self._status_label.setText("Not calibrated - using the 1 g defaults")
            self._set_bar(0.0)
        self._hint_label.setText(
            "Bars update live. White marks are the saved limits and the darker centre band is the deadzone. "
            "Level is taken from how the Deck is held when this window opens.")

    def _refresh_recording(self):
        green = theme_manager.get("green")
        reached = 0
        for row in self._rows:
            axis = row["axis"]
            low_peak = self._peaks[axis["low_key"]]
            high_peak = self._peaks[axis["high_key"]]
            low_done = low_peak >= REACHED_G
            high_done = high_peak >= REACHED_G
            reached += int(low_done) + int(high_done)
            low_text = f"{low_peak:.2f} g" if low_done else "--"
            high_text = f"{high_peak:.2f} g" if high_done else "--"
            row["low_label"].setText(f"{axis['low_word'].capitalize()} peak {low_text}")
            row["high_label"].setText(f"{axis['high_word'].capitalize()} peak {high_text}")
            if low_done and high_done:
                row["note"].setText("Both sides recorded")
                row["note"].setStyleSheet(f"color: {green};")
            elif low_done or high_done:
                missing = axis["high_word"] if low_done else axis["low_word"]
                row["note"].setText(f"Waiting for {missing}")
                row["note"].setStyleSheet(f"color: {LABEL_GREY};")
            else:
                row["note"].setText(f"Waiting for {axis['low_word']} and {axis['high_word']}")
                row["note"].setStyleSheet(f"color: {LABEL_GREY};")
        total = len(IMU_LIMIT_KEYS)
        self._status_label.setText(f"Recording - {reached} of {total} limits reached")
        self._set_bar(reached / total)

    def _set_bar(self, fraction: float):
        self._bar_fraction = max(0.0, min(1.0, fraction))
        self._resize_bar()

    # ---------- Actions ----------

    def _start_recording(self):
        if self._smoothed is None:
            return
        self._zero = dict(self._smoothed)
        self._peaks = {key: 0.0 for key in IMU_LIMIT_KEYS}
        was_recording = self._recording
        self._recording = True
        for row in self._rows:
            row["bar"].set_peaks(0.0, 0.0)
            row["bar"].set_recording(True)
        if not was_recording:
            self._show_recording_buttons()
        self._hint_label.setText(
            "Tilt the Deck left, right, forward and back as far as you would in normal use. "
            "The furthest point on each side is kept automatically.")
        self._refresh_recording()

    def _cancel_recording(self):
        self._recording = False
        self._show_idle_buttons()
        self._refresh_limits()
        self._refresh_status()

    def _finish_recording(self):
        limits = dict(self._limits)
        changed = 0
        for key in IMU_LIMIT_KEYS:
            if self._peaks[key] >= REACHED_G:
                limits[key] = int(min(IMU_LIMIT_MAX, round(self._peaks[key] * ACCEL_MAX)))
                changed += 1
        self._recording = False
        self._show_idle_buttons()
        if changed == 0:
            self._refresh_limits()
            self._refresh_status()
            self._status_label.setText("No limits were reached - nothing changed")
            return
        saved = self._save_limits(limits)
        self._refresh_limits()
        self._refresh_status()
        if saved:
            self._status_label.setText(f"Calibration saved - {changed} of {len(IMU_LIMIT_KEYS)} limits updated")
        else:
            self._status_label.setText("Could not save the calibration file")

    def _reset_to_defaults(self):
        if not ask_confirm(self, "IMU CALIBRATION", "Reset tilt limits?",
                           "All four limits go back to the 1 g defaults.", confirm="RESET"):
            return
        saved = self._save_limits({key: ACCEL_MAX for key in IMU_LIMIT_KEYS})
        self._refresh_limits()
        self._refresh_status()
        if not saved:
            self._status_label.setText("Could not save the calibration file")

    def _save_limits(self, limits: dict) -> bool:
        """Write the limits to disk and apply them to the running controller thread"""
        if not config_manager.save_config(IMU_CALIBRATION_PATH, limits):
            self.logger.error("Failed to save IMU calibration")
            return False
        self.controller_thread.load_imu_calibration()
        self._limits = self.controller_thread.get_imu_calibration()
        self.logger.info(f"IMU calibration saved: {self._limits}")
        return True

    def done(self, result):
        self._timer.stop()
        super().done(result)
