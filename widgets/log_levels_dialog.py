#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - Log Levels Dialog
One row per log group with touch-sized level buttons. The caller applies the
chosen levels on the Deck and sends them to the robot.
"""

from typing import Dict

from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame, QButtonGroup

from core.theme_manager import theme_manager
from widgets.flow_dialog import (
    FlowDialog, LABEL_GREY, TEXT_SOFT, TILE_BG, px_font, _plain_button_style, _filled_button_style
)

# (key, name, where it applies, what it covers)
GROUPS = (
    ("camera", "Camera", "Deck + robot", "stream, proxy, person detection"),
    ("servo", "Servo & motion", "Deck + robot", "Maestros, mixer, NEMA"),
    ("controller", "Controller & IMU", "Deck + robot", "input, mappings, Bluetooth"),
    ("scenes", "Scenes & audio", "Deck + robot", "playback, sound, Bottango"),
    ("attention", "Attention", "Robot only", "tracking focus, scanning, reactions"),
    ("network", "Network", "Deck + robot", "WebSocket, Wi-Fi, web app"),
)

# (button text, saved level)
LEVELS = (("ERROR", "ERROR"), ("WARN", "WARNING"), ("INFO", "INFO"), ("DEBUG", "DEBUG"))


def _level_button_style(primary: str) -> str:
    return f"""
        QPushButton {{
            background-color: #2a2a2a;
            color: {TEXT_SOFT};
            border: 1px solid #3e3e3e;
            border-radius: 6px;
        }}
        QPushButton:checked {{
            background-color: {primary};
            color: #111111;
            border: none;
        }}
    """


class LogLevelsDialog(FlowDialog):
    """Pick a level for each log group; levels() holds the result after SAVE"""

    def __init__(self, parent, levels: Dict[str, str]):
        super().__init__(parent, "LOG LEVELS", "Applied straight away on the Deck and the robot", width=680)
        self._levels = {key: str(levels.get(key, "INFO")).upper() for key, *_ in GROUPS}
        self._groups: Dict[str, QButtonGroup] = {}
        self._build_rows()
        self._build_buttons()

    def _build_rows(self):
        primary = theme_manager.get("primary_color")
        rows = QVBoxLayout()
        rows.setSpacing(8)
        for key, name, scope, covers in GROUPS:
            tile = QFrame()
            tile.setObjectName("level_tile")
            tile.setStyleSheet(
                f"QFrame#level_tile {{ background-color: {TILE_BG}; border: 1px solid #2e2e2e; border-radius: 8px; }}"
                "QLabel { background: transparent; border: none; }")
            row = QHBoxLayout(tile)
            row.setContentsMargins(12, 8, 12, 8)
            row.setSpacing(12)

            text = QVBoxLayout()
            text.setSpacing(2)
            title = QLabel(name)
            title.setFont(px_font(16, bold=True))
            title.setStyleSheet(f"color: {TEXT_SOFT};")
            detail = QLabel(f"{scope} · {covers}")
            detail.setFont(px_font(12))
            detail.setStyleSheet(f"color: {LABEL_GREY};")
            text.addWidget(title)
            text.addWidget(detail)
            row.addLayout(text, 1)

            group = QButtonGroup(self)
            group.setExclusive(True)
            for label, level in LEVELS:
                button = QPushButton(label)
                button.setCheckable(True)
                button.setFixedSize(66, 40)
                button.setFont(px_font(12, bold=True))
                button.setStyleSheet(_level_button_style(primary))
                button.setAccessibleName(f"{name} {label}")
                button.setChecked(self._levels[key] == level)
                button.clicked.connect(lambda _checked, k=key, lv=level: self._levels.__setitem__(k, lv))
                group.addButton(button)
                row.addWidget(button)
            self._groups[key] = group
            rows.addWidget(tile)
        self.body_layout.addLayout(rows)

    def _make_button(self, text: str, handler, filled: bool = False, width: int = 130) -> QPushButton:
        button = QPushButton(text)
        button.setFixedHeight(44)
        button.setMinimumWidth(width)
        button.setFont(px_font(15, bold=True))
        button.setStyleSheet(_filled_button_style(theme_manager.get("primary_color")) if filled
                             else _plain_button_style())
        button.clicked.connect(handler)
        return button

    def _build_buttons(self):
        self.buttons.addWidget(self._make_button("CANCEL", self.reject))
        self.buttons.addWidget(self._make_button("ALL INFO", self._all_info))
        self.buttons.addStretch(1)
        self.buttons.addWidget(self._make_button("SAVE", self.accept, filled=True, width=160))

    def _all_info(self):
        for key, group in self._groups.items():
            self._levels[key] = "INFO"
            for button in group.buttons():
                button.setChecked(button.text() == "INFO")

    def levels(self) -> Dict[str, str]:
        return dict(self._levels)
