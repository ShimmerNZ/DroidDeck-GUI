#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - Health Monitoring Screen (Themed)
Displays pack voltage and current, motion, Raspberry Pi and network status
"""

import math
import time
from collections import deque
from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame,
                             QWidget, QPushButton, QProgressBar, QSizePolicy)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
import pyqtgraph as pg

from core.config_manager import config_manager as _config_manager

from widgets.base_screen import BaseScreen
from core.theme_manager import theme_manager
from core.utils import error_boundary
from core.battery import battery_profile
from widgets.bandwidth_test_splash import show_bandwidth_test_splash


class HealthScreen(BaseScreen):
    """System health dashboard: graph, power, motion, Pi and link cards"""

    # Qt signals for thread-safe updates
    status_update_signal = pyqtSignal(dict)

    # Fixed colours shared by every theme
    AMBER = "#ff9800"
    WHITE = "#ffffff"
    LABEL_GREY = "#9e9e9e"
    TEXT_SOFT = "#bdbdbd"
    TILE_BG = "#202020"
    TILE_ERROR_BG = "#3a1c1c"
    UNKNOWN_BADGE_BG = "#3a3a3a"
    TOTAL_CURRENT_COLOR = "#FF8C00"

    # Card heights - the two columns each total 490px including gaps
    GRAPH_CARD_HEIGHT = 266
    POWER_CARD_HEIGHT = 212
    MOTION_CARD_HEIGHT = 172
    PI_CARD_HEIGHT = 112
    LINK_CARD_HEIGHT = 182

    MAESTRO_ROWS = (
        ("maestro1", "M1", "Head, eyes, hands"),
        ("maestro2", "M2", "Arms, neck, eyelids, tracks"),
    )

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

        # Fixed time window (seconds) shown on the telemetry graph, regardless
        # of how fast telemetry updates actually arrive
        self.graph_window_seconds = 100.0

        # Initialise early so signal handlers never find these missing
        self.battery_voltage_data = deque()
        self.current_a1_data = deque()
        self.current_a2_data = deque()
        self.time_data = deque()

        # Carry-forward cache so zero/missing readings don't wipe displayed values
        self._last_system_stats = {
            "cpu": None, "memory": None, "temperature": None,
            "current_total": None, "current_tracks": None, "sabertooth_temp": None,
        }
        # Latest pack voltage, used for the pack badge and state of charge colour
        self._last_battery_voltage = None
        # Last known throughput bytes for delta calculation
        self._last_net_bytes = None
        self._last_net_time = None

        # Rate limiting for telemetry updates, tracked per message type
        self._last_update_by_type = {"telemetry": 0.0, "system_status": 0.0}
        self.telemetry_update_interval = 0.25

        # Last valid readings, carried forward into the graph when a reading is missing
        self._last_graph_values = {"voltage": None, "tracks": None, "total": None}

        # Track start time for relative time calculation
        self.start_time = time.time()

        # Styled widgets, re-styled on theme change
        self._cards = []
        self._card_titles = []
        self._captions = []
        self._soft_labels = []
        self._tiles = []
        self._buttons = []
        self._maestro_widgets = {}

        # Connect signals for thread-safe updates
        self.status_update_signal.connect(self._update_status_displays)

        self.init_ui()

        # Telemetry stays subscribed while hidden so the graph history and
        # runtime estimate keep up to date in the background
        self.subscribe("telemetry", self._on_telemetry)
        self.subscribe("system_status", self._on_system_status)

        # Periodic timer to poll system_status (mixer stats, run-time estimate, hardware)
        self.status_poll_timer = QTimer()
        self.status_poll_timer.timeout.connect(self._request_system_status)
        self.status_poll_timer.start(2000)  # Poll every 2 seconds

    # ------------------------------------------------------------------
    # Widget helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _font(pixel_size: int, bold: bool = False, spacing: float = 0.0,
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

    def _make_card(self, title: str, height: int):
        """Create a titled card; returns (card, body_layout, header_row)"""
        card = QFrame()
        card.setObjectName("health_card")
        card.setFixedHeight(height)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(5)

        title_label = QLabel(title)
        title_label.setFont(self._font(14, bold=True, spacing=1.5))
        header_row.addWidget(title_label)
        header_row.addStretch(1)
        layout.addLayout(header_row)

        self._cards.append(card)
        self._card_titles.append(title_label)
        return card, layout, header_row

    def _make_caption(self, text: str, pixel_size: int = 11) -> QLabel:
        """Small grey caption above a value"""
        label = QLabel(text)
        label.setFont(self._font(pixel_size, spacing=1.0))
        self._captions.append(label)
        return label

    def _make_value(self, text: str, pixel_size: int, color: str = None) -> QLabel:
        """Value label with an initial colour"""
        label = QLabel(text)
        label.setFont(self._font(pixel_size))
        self._set_value(label, text, color or self.WHITE)
        return label

    def _make_stat(self, caption: str, caption_px: int, value_px: int):
        """Caption-over-value block; returns (widget, value_label)"""
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._make_caption(caption, caption_px))
        value = self._make_value("--", value_px)
        layout.addWidget(value)
        return widget, value

    def _make_tile(self) -> QFrame:
        """Dark rounded tile used inside cards"""
        tile = QFrame()
        tile.setObjectName("health_tile")
        self._tiles.append(tile)
        return tile

    def _make_badge(self) -> QLabel:
        """Small coloured status badge"""
        badge = QLabel("--")
        badge.setFont(self._font(12, bold=True))
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._set_badge(badge, "--", None)
        return badge

    def _make_button(self, text: str) -> QPushButton:
        """Button styled like the existing bandwidth test button"""
        button = QPushButton(text)
        button.setFont(self._font(14, bold=True))
        self._buttons.append(button)
        return button

    def _set_value(self, label: QLabel, text: str, color: str):
        """Set a value label's text and colour"""
        label.setText(text)
        label.setStyleSheet(f"color: {color}; background: transparent; border: none;")

    def _set_badge(self, badge: QLabel, text: str, background):
        """Set a badge's text and background; None background means unknown"""
        if background is None:
            text_color, background = self.TEXT_SOFT, self.UNKNOWN_BADGE_BG
        else:
            text_color = "#111111"
        badge.setText(text)
        badge.setStyleSheet(
            f"color: {text_color}; background: {background}; border: none; "
            f"border-radius: 4px; padding: 3px 8px;"
        )
        badge.adjustSize()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def init_ui(self):
        """Build the two-column card layout"""
        self.setup_telemetry_graph()

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(101, 40, 12, 6)
        main_layout.setSpacing(12)

        left_column = QVBoxLayout()
        left_column.setContentsMargins(0, 0, 0, 0)
        left_column.setSpacing(12)
        left_column.addWidget(self._create_graph_card())
        left_column.addWidget(self._create_power_card())
        left_column.addStretch(1)

        right_column = QVBoxLayout()
        right_column.setContentsMargins(0, 0, 0, 0)
        right_column.setSpacing(12)
        right_column.addWidget(self._create_motion_card())
        right_column.addWidget(self._create_pi_card())
        right_column.addWidget(self._create_link_card())
        right_column.addStretch(1)

        left_widget = QWidget()
        left_widget.setFixedWidth(576)
        left_widget.setStyleSheet("background: transparent;")
        left_widget.setLayout(left_column)

        right_widget = QWidget()
        right_widget.setFixedWidth(479)
        right_widget.setStyleSheet("background: transparent;")
        right_widget.setLayout(right_column)

        main_layout.addWidget(left_widget)
        main_layout.addWidget(right_widget)
        main_layout.addStretch(1)
        self.setLayout(main_layout)

        self._apply_styles()

    def setup_telemetry_graph(self):
        """Setup pack voltage and current graph over the last 100 seconds"""
        self.graph_widget = pg.PlotWidget()
        self._update_graph_theme()
        plot = self.graph_widget.getPlotItem()
        plot.setContentsMargins(0, 0, 0, 0)
        plot.hideButtons()
        self.graph_widget.setMouseEnabled(x=False, y=False)
        self.graph_widget.showGrid(x=False, y=True, alpha=0.15)

        self.graph_widget.setXRange(-self.graph_window_seconds, 0, padding=0)

        tick_font = self._font(11)
        for axis_name in ("left", "bottom", "right"):
            axis = plot.getAxis(axis_name)
            axis.setTextPen(self.LABEL_GREY)
            axis.setPen("#3a3a3a")
            axis.setStyle(tickFont=tick_font)

        half = int(self.graph_window_seconds / 2)
        full = int(self.graph_window_seconds)
        plot.getAxis("bottom").setTicks([[(-full, f"-{full} s"), (-half, f"-{half} s"), (0, "now")]])

        # Battery alarm thresholds
        self.low_threshold_line = pg.InfiniteLine(pos=battery_profile.low_voltage, angle=0)
        self.critical_threshold_line = pg.InfiniteLine(pos=battery_profile.critical_voltage, angle=0)
        plot.addItem(self.low_threshold_line)
        plot.addItem(self.critical_threshold_line)
        self._apply_battery_range()
        battery_profile.changed.connect(self._apply_battery_range)

        # Current curves on a second view box with the right-hand axis
        self.current_view = pg.ViewBox()
        self.graph_widget.scene().addItem(self.current_view)
        plot.showAxis("right")
        right_axis = plot.getAxis("right")
        right_axis.linkToView(self.current_view)
        right_axis.setTicks([[(a, f"{a}A" if a == 60 else str(a)) for a in (0, 20, 40, 60)]])
        self.current_view.setXLink(plot.getViewBox())
        self.current_view.setYRange(0, 60, padding=0)
        self.current_view.setMouseEnabled(x=False, y=False)
        plot.getViewBox().sigResized.connect(self.update_views)

        self.current_a2_plot = pg.PlotCurveItem(antialias=True)
        self.current_a1_plot = pg.PlotCurveItem(antialias=True)
        self.current_view.addItem(self.current_a2_plot)
        self.current_view.addItem(self.current_a1_plot)

        # Voltage curve (primary Y-axis)
        self.voltage_curve = plot.plot(antialias=True)

        self._update_graph_pens()

    def _apply_battery_range(self):
        """Zoom the voltage axis to the pack's range and move the alarm lines"""
        bottom = math.floor(battery_profile.empty_voltage)
        top = max(math.ceil(battery_profile.full_voltage), bottom + 2)
        span = top - bottom
        step = 1 if span <= 6 else (2 if span <= 12 else 5)

        ticks = list(range(math.ceil(bottom / step) * step, top + 1, step))
        self.graph_widget.setYRange(bottom, top, padding=0)
        self.graph_widget.getPlotItem().getAxis("left").setTicks(
            [[(v, f"{v}V" if v == ticks[-1] else str(v)) for v in ticks]]
        )
        self.low_threshold_line.setPos(battery_profile.low_voltage)
        self.critical_threshold_line.setPos(battery_profile.critical_voltage)

    def _create_graph_card(self) -> QFrame:
        """Graph card with a compact legend in the header"""
        card, layout, header_row = self._make_card(
            f"PACK VOLTAGE & CURRENT · {int(self.graph_window_seconds)} s",
            self.GRAPH_CARD_HEIGHT)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        self._legend_swatches = {}
        for key, text in (("voltage", "Pack V"), ("tracks", "Tracks A"), ("total", "Total A")):
            swatch = QFrame()
            swatch.setFixedSize(14, 3)
            label = QLabel(text)
            label.setFont(self._font(12))
            self._soft_labels.append(label)
            header_row.addSpacing(9)
            header_row.addWidget(swatch, 0, Qt.AlignmentFlag.AlignVCenter)
            header_row.addWidget(label)
            self._legend_swatches[key] = swatch

        layout.addWidget(self.graph_widget, 1)
        return card

    def _create_power_card(self) -> QFrame:
        """Pack voltage, state of charge, runtime and current tiles"""
        card, layout, _ = self._make_card("POWER", self.POWER_CARD_HEIGHT)

        content = QHBoxLayout()
        content.setSpacing(16)

        # Pack block
        pack_block = QVBoxLayout()
        pack_block.setContentsMargins(0, 0, 0, 0)
        pack_block.setSpacing(8)
        pack_block.addStretch(1)

        # Caption and state badge share a row so the voltage has the full width
        pack_header = QHBoxLayout()
        pack_header.setSpacing(10)
        pack_header.addWidget(self._make_caption("PACK", 12), 0, Qt.AlignmentFlag.AlignVCenter)
        pack_header.addStretch(1)
        self.pack_badge = self._make_badge()
        pack_header.addWidget(self.pack_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        pack_block.addLayout(pack_header)

        self.pack_value_label = self._make_value("--.-- V", 44)
        self.pack_value_label.setFont(self._font(44, bold=True))
        pack_block.addWidget(self.pack_value_label)

        self.soc_bar = QProgressBar()
        self.soc_bar.setRange(0, 100)
        self.soc_bar.setValue(0)
        self.soc_bar.setTextVisible(False)
        self.soc_bar.setFixedHeight(12)
        pack_block.addWidget(self.soc_bar)

        self.runtime_label = QLabel()
        self.runtime_label.setFont(self._font(16))
        self.runtime_label.setTextFormat(Qt.TextFormat.RichText)
        self.runtime_label.setText('<span style="color: #d8d8d8;">Runtime --</span>')
        pack_block.addWidget(self.runtime_label)

        self.usage_label = QLabel()
        self.usage_label.setFont(self._font(14))
        self.usage_label.setTextFormat(Qt.TextFormat.RichText)
        self.usage_label.setText(f'<span style="color: {self.TEXT_SOFT};">Used --</span>')
        pack_block.addWidget(self.usage_label)
        pack_block.addStretch(1)

        pack_widget = QWidget()
        pack_widget.setFixedWidth(236)
        pack_widget.setStyleSheet("background: transparent;")
        pack_widget.setLayout(pack_block)
        content.addWidget(pack_widget)

        # Current and temperature tiles
        tiles = QGridLayout()
        tiles.setSpacing(8)
        self.power_values = {}
        for index, (key, caption) in enumerate((("current_tracks", "TRACKS"),
                                                ("current_total", "TOTAL"),
                                                ("current_electronics", "ELECTRONICS"),
                                                ("sabertooth_temp", "SABERTOOTH"))):
            tile = self._make_tile()
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(10, 8, 10, 8)
            tile_layout.setSpacing(0)
            tile_layout.addStretch(1)
            tile_layout.addWidget(self._make_caption(caption, 12))
            value = self._make_value("--", 24)
            tile_layout.addWidget(value)
            tile_layout.addStretch(1)
            self.power_values[key] = value
            tiles.addWidget(tile, index // 2, index % 2)
        tiles.setColumnStretch(0, 1)
        tiles.setColumnStretch(1, 1)
        content.addLayout(tiles, 1)

        layout.addLayout(content, 1)
        return card

    def _create_motion_card(self) -> QFrame:
        """Maestro status rows with error clear, plus motion mixer stats"""
        card, layout, _ = self._make_card("MOTION", self.MOTION_CARD_HEIGHT)

        top = QHBoxLayout()
        top.setSpacing(10)

        rows = QVBoxLayout()
        rows.setSpacing(6)
        for key, name, detail in self.MAESTRO_ROWS:
            row = self._make_tile()
            row.setFixedHeight(36)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(10, 0, 10, 0)
            row_layout.setSpacing(10)

            name_label = self._make_value(name, 16)
            name_label.setFont(self._font(16, bold=True))
            name_label.setFixedWidth(48)
            detail_label = QLabel(detail)
            detail_label.setFont(self._font(13))
            detail_label.setMinimumWidth(0)
            detail_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            self._soft_labels.append(detail_label)
            badge = self._make_badge()
            code_label = self._make_value("--", 13, self.LABEL_GREY)
            code_label.setFont(self._font(13, family="Consolas"))
            code_label.setFixedWidth(58)
            code_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            row_layout.addWidget(name_label)
            row_layout.addWidget(detail_label, 1)
            row_layout.addWidget(badge)
            row_layout.addWidget(code_label)
            rows.addWidget(row)

            self._maestro_widgets[key] = {
                "row": row, "detail": detail_label, "default_detail": detail,
                "badge": badge, "code": code_label, "error": False,
            }
        top.addLayout(rows, 1)

        self.clear_errors_btn = self._make_button("CLEAR\nERRORS")
        self.clear_errors_btn.setFont(self._font(13, bold=True))
        self.clear_errors_btn.setFixedWidth(92)
        self.clear_errors_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.clear_errors_btn.setEnabled(False)
        self.clear_errors_btn.clicked.connect(self._clear_maestro_errors)
        top.addWidget(self.clear_errors_btn)
        layout.addLayout(top)

        mixer = QGridLayout()
        mixer.setHorizontalSpacing(6)
        self.mixer_values = {}
        for index, (key, caption) in enumerate((("serial_fps", "MIXER"), ("blend_ms", "BLEND"),
                                                ("serial_cmds", "CMDS/S"), ("active_ch", "ACTIVE CH"))):
            widget, value = self._make_stat(caption, 11, 18)
            self.mixer_values[key] = value
            mixer.addWidget(widget, 0, index)
            mixer.setColumnStretch(index, 1)
        layout.addLayout(mixer)
        return card

    def _create_pi_card(self) -> QFrame:
        """Raspberry Pi load, temperature and 5V supply flags"""
        card, layout, _ = self._make_card("RASPBERRY PI", self.PI_CARD_HEIGHT)

        row = QHBoxLayout()
        row.setSpacing(18)
        self.pi_values = {}
        for key, caption in (("cpu", "CPU"), ("memory", "MEMORY"), ("temperature", "TEMP")):
            widget, value = self._make_stat(caption, 11, 18)
            self.pi_values[key] = value
            row.addWidget(widget)
        row.addStretch(1)

        supply = QVBoxLayout()
        supply.setSpacing(4)
        supply.addWidget(self._make_caption("5V SUPPLY"), 0, Qt.AlignmentFlag.AlignRight)
        badges = QHBoxLayout()
        badges.setSpacing(6)
        badges.addStretch(1)
        self.supply_now_badge = self._make_badge()
        self.supply_history_badge = self._make_badge()
        self.supply_history_badge.hide()
        badges.addWidget(self.supply_now_badge)
        badges.addWidget(self.supply_history_badge)
        supply.addLayout(badges)
        row.addLayout(supply)

        layout.addLayout(row)
        layout.addStretch(1)
        return card

    def _create_link_card(self) -> QFrame:
        """What the Steam Deck and the Pi hotspot each see of the link"""
        card, layout, _ = self._make_card("LINK", self.LINK_CARD_HEIGHT)

        columns = QGridLayout()
        columns.setHorizontalSpacing(14)
        self.link_values = {}
        for column, (caption, rows) in enumerate((
                ("STEAM DECK SEES", (("wifi", "WiFi"), ("ping", "Pi ping"), ("throughput", "Down / Up"))),
                ("PI HOTSPOT SEES", (("signal", "Deck signal"), ("retries", "TX retries"), ("failed", "TX failed"))))):
            col_layout = QVBoxLayout()
            col_layout.setSpacing(3)
            col_layout.addWidget(self._make_caption(caption))
            for key, text in rows:
                line = QHBoxLayout()
                line.setSpacing(6)
                name = QLabel(text)
                name.setFont(self._font(15))
                self._soft_labels.append(name)
                value = self._make_value("--", 15)
                value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                line.addWidget(name)
                line.addStretch(1)
                line.addWidget(value)
                col_layout.addLayout(line)
                self.link_values[key] = value
            columns.addLayout(col_layout, 0, column)
            columns.setColumnStretch(column, 1)
        layout.addLayout(columns)
        layout.addStretch(1)

        self.bandwidth_btn = self._make_button("BANDWIDTH TEST")
        self.bandwidth_btn.setFixedHeight(44)
        self.bandwidth_btn.clicked.connect(self.start_bandwidth_test)
        layout.addWidget(self.bandwidth_btn)
        return card

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    def _border_color(self) -> str:
        """Card border: the theme's primary colour at reduced strength"""
        color = QColor(theme_manager.get("primary_color"))
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, 0.45)"

    def _apply_styles(self):
        """Apply theme colours to every styled widget"""
        primary = theme_manager.get("primary_color")
        panel_bg = theme_manager.get("panel_bg")
        border = self._border_color()

        for card in self._cards:
            card.setStyleSheet(f"""
                QFrame#health_card {{
                    background-color: {panel_bg};
                    border: 1px solid {border};
                    border-radius: 10px;
                }}
                QLabel {{
                    border: none;
                    background: transparent;
                }}
            """)
        for title in self._card_titles:
            title.setStyleSheet(f"color: {primary}; background: transparent; border: none;")
        for caption in self._captions:
            caption.setStyleSheet(f"color: {self.LABEL_GREY}; background: transparent; border: none;")
        for label in self._soft_labels:
            label.setStyleSheet(f"color: {self.TEXT_SOFT}; background: transparent; border: none;")
        for tile in self._tiles:
            self._style_tile(tile, self.TILE_BG)
        for widgets in self._maestro_widgets.values():
            self._style_tile(widgets["row"], self.TILE_ERROR_BG if widgets["error"] else self.TILE_BG)
        for button in self._buttons:
            self._style_button(button, primary)

        self._update_soc_bar_color()
        self._update_graph_pens()

    def _style_tile(self, tile: QFrame, background: str):
        tile.setStyleSheet(f"""
            QFrame#health_tile {{
                background-color: {background};
                border: none;
                border-radius: 8px;
            }}
        """)

    def _style_button(self, button: QPushButton, primary: str):
        button.setStyleSheet(f"""
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

    def _update_graph_theme(self):
        """Update graph background with theme colours"""
        self.graph_widget.setBackground(theme_manager.get("panel_bg"))

    def _update_graph_pens(self):
        """Theme colours for the graph curves, threshold lines and legend"""
        if not hasattr(self, "voltage_curve"):
            return
        green = theme_manager.get("green")
        primary = theme_manager.get("primary_color")
        red = theme_manager.get("red")

        self.voltage_curve.setPen(pg.mkPen(color=green, width=3))
        self.current_a1_plot.setPen(pg.mkPen(color=primary, width=2))
        self.current_a2_plot.setPen(pg.mkPen(color=self.TOTAL_CURRENT_COLOR, width=2))
        self.low_threshold_line.setPen(pg.mkPen(color=primary, width=1, style=Qt.PenStyle.DashLine))
        self.critical_threshold_line.setPen(pg.mkPen(color=red, width=1, style=Qt.PenStyle.DashLine))

        for key, color in (("voltage", green), ("tracks", primary), ("total", self.TOTAL_CURRENT_COLOR)):
            swatch = getattr(self, "_legend_swatches", {}).get(key)
            if swatch is not None:
                swatch.setStyleSheet(f"background-color: {color}; border: none;")

    def _on_theme_changed(self):
        """Handle theme change by updating all styled components"""
        try:
            self._update_graph_theme()
            self._apply_styles()
            if self._last_battery_voltage is not None:
                self._update_pack_display(self._last_battery_voltage)
            self.logger.info(f"Health screen updated for theme: {theme_manager.get_theme_name()}")
        except Exception as e:
            self.logger.warning(f"Failed to apply theme changes: {e}")

    def update_views(self):
        """Keep the current view box aligned with the main plot area"""
        self.current_view.setGeometry(
            self.graph_widget.getPlotItem().getViewBox().sceneBoundingRect()
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @error_boundary
    def start_bandwidth_test(self, checked=False):
        """Start bandwidth test with progress splash screen"""
        # Disable button during test
        self.bandwidth_btn.setEnabled(False)
        self.bandwidth_btn.setText("TESTING...")

        wave_config = _config_manager.get_wave_config()
        camera_proxy_url = wave_config.get("camera_proxy_url", "http://10.1.1.230:8081")
        if camera_proxy_url.endswith("/stream"):
            camera_proxy_url = camera_proxy_url[:-7]

        # Show the bandwidth test splash screen
        show_bandwidth_test_splash(self, camera_proxy_url)

        # Re-enable button
        self.bandwidth_btn.setEnabled(True)
        self.bandwidth_btn.setText("BANDWIDTH TEST")

    @error_boundary
    def _clear_maestro_errors(self, checked=False):
        """Ask the backend to read and clear both Maestro error registers"""
        if self.send_websocket_message("clear_maestro_errors"):
            self.logger.info("Requested Maestro error clear")
            # Refresh straight away rather than waiting for the next poll
            QTimer.singleShot(300, self._request_system_status)

    @error_boundary
    def _request_system_status(self):
        """Poll backend for system_status (mixer stats, run-time estimate, hardware)"""
        try:
            self.send_websocket_message("system_status")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    def _rate_limited(self, msg_type: str) -> bool:
        """Return True if a message of this type arrived too soon after the last one"""
        now = time.time()
        if now - self._last_update_by_type.get(msg_type, 0.0) < self.telemetry_update_interval:
            return True
        self._last_update_by_type[msg_type] = now
        return False

    def _on_system_status(self, data: dict):
        """Apply system_status replies - mixer stats, run-time estimate and hardware status"""
        if self._rate_limited("system_status"):
            return
        try:
            self.status_update_signal.emit({
                "battery_estimate": data.get("battery_estimate"),
                "serial_fps": data.get("serial_fps"),
                "blend_ms": data.get("blend_ms"),
                "serial_cmds_sec": data.get("serial_cmds_sec"),
                "active_channels": data.get("active_channels"),
                "hardware": data.get("hardware"),
                "maestro_errors": data.get("maestro_errors"),
                "pi_power": data.get("pi_power"),
                "hotspot_station": data.get("hotspot_station"),
            })
        except Exception as e:
            self.logger.error(f"System status processing failed: {e}")

    def _carry_forward(self, key: str, value, allow_zero: bool = False):
        """Return value if it is a valid reading, otherwise the last valid one.
        Track current is genuinely zero at rest, so currents pass allow_zero."""
        if value is not None and (value > 0 or (allow_zero and value == 0)):
            self._last_graph_values[key] = float(value)
        return self._last_graph_values[key]

    def _on_telemetry(self, data: dict):
        """Process incoming telemetry and update displays and graph"""
        if self._rate_limited("telemetry"):
            return
        try:
            voltage = data.get("battery_voltage")
            if voltage is not None and voltage > 0:
                self._last_battery_voltage = float(voltage)
                self._update_pack_display(self._last_battery_voltage)

            self.status_update_signal.emit(data)

            graph_voltage = self._carry_forward("voltage", voltage)
            graph_tracks = self._carry_forward("tracks", data.get("current_tracks"), allow_zero=True)
            graph_total = self._carry_forward("total", data.get("current_total"), allow_zero=True)

            # Nothing valid received yet - plot nothing rather than invent values
            if graph_voltage is None:
                return

            relative_time = time.time() - self.start_time

            self.battery_voltage_data.append(graph_voltage)
            self.current_a1_data.append(graph_tracks if graph_tracks is not None else 0.0)
            self.current_a2_data.append(graph_total if graph_total is not None else 0.0)
            self.time_data.append(relative_time)

            # Drop points older than the fixed display window so the graph
            # always shows the same span of time regardless of how fast
            # telemetry actually arrives
            cutoff = relative_time - self.graph_window_seconds
            while self.time_data and self.time_data[0] < cutoff:
                self.time_data.popleft()
                self.battery_voltage_data.popleft()
                self.current_a1_data.popleft()
                self.current_a2_data.popleft()

            self._update_graphs()

        except Exception as e:
            self.logger.error(f"Telemetry processing failed: {e}")

    # ------------------------------------------------------------------
    # Display updates
    # ------------------------------------------------------------------

    def _pack_state(self, voltage: float):
        """Return (state text, colour) for a pack voltage"""
        if voltage < battery_profile.critical_voltage:
            return "CRITICAL", theme_manager.get("red")
        if voltage < battery_profile.low_voltage:
            return "LOW", self.AMBER
        return "GOOD", theme_manager.get("green")

    def _update_pack_display(self, voltage: float):
        """Pack voltage value, state badge and state of charge bar colour"""
        state, color = self._pack_state(voltage)
        self._set_value(self.pack_value_label, f"{voltage:.2f} V", color)
        self._set_badge(self.pack_badge, state, color)
        self._update_soc_bar_color()

    def _update_soc_bar_color(self):
        """State of charge bar follows the pack state colour"""
        if self._last_battery_voltage is not None:
            _, color = self._pack_state(self._last_battery_voltage)
        else:
            color = theme_manager.get("green")
        self.soc_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #2c2c2c;
                border: none;
                border-radius: 6px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 6px;
            }}
        """)

    def _update_status_displays(self, data: dict):
        """Thread-safe status display updates with theme colours"""
        green = theme_manager.get("green")
        red = theme_manager.get("red")

        # Carry-forward: only update system stats when the values are actually present
        for key in ("cpu", "memory", "temperature"):
            value = data.get(key)
            if value not in (None, "--"):
                self._last_system_stats[key] = value

        cpu = self._last_system_stats["cpu"]
        if cpu is not None:
            self._set_value(self.pi_values["cpu"], f"{cpu}%", self.AMBER if float(cpu) > 90 else green)
        memory = self._last_system_stats["memory"]
        if memory is not None:
            self._set_value(self.pi_values["memory"], f"{memory}%", self.AMBER if float(memory) > 85 else green)
        temperature = self._last_system_stats["temperature"]
        if temperature is not None:
            temp = float(temperature)
            temp_color = red if temp >= 80 else (self.AMBER if temp >= 70 else green)
            self._set_value(self.pi_values["temperature"], f"{temp:.0f} °C", temp_color)

        # Currents and Sabertooth temperature - zero means missing for display
        for key in ("current_total", "current_tracks", "sabertooth_temp"):
            value = data.get(key)
            if value is not None and value != 0.0:
                self._last_system_stats[key] = value

        tracks = self._last_system_stats["current_tracks"]
        total = self._last_system_stats["current_total"]
        sabertooth = self._last_system_stats["sabertooth_temp"]
        if tracks is not None:
            self._set_value(self.power_values["current_tracks"], f"{tracks:.1f} A", green)
        if total is not None:
            self._set_value(self.power_values["current_total"], f"{total:.1f} A", green)
        if tracks is not None and total is not None:
            electronics = max(total - tracks, 0.0)
            self._set_value(self.power_values["current_electronics"], f"{electronics:.1f} A", green)
        if sabertooth is not None:
            self._set_value(self.power_values["sabertooth_temp"], f"{sabertooth:.1f} °C", green)

        # Battery run-time estimate (only present on system_status replies)
        battery_estimate = data.get("battery_estimate")
        if isinstance(battery_estimate, dict):
            self._update_runtime_display(battery_estimate)

        # Sample /proc/net/dev for throughput on wlan0
        self._update_throughput_display()

        # Motion mixer serial performance
        serial_fps = data.get("serial_fps")
        if serial_fps is not None:
            target_hz = 50.0
            if serial_fps >= target_hz * 0.9:
                color = green
            elif serial_fps >= target_hz * 0.7:
                color = self.AMBER
            else:
                color = red
            self._set_value(self.mixer_values["serial_fps"], f"{serial_fps} Hz", color)

        blend_ms = data.get("blend_ms")
        if blend_ms is not None:
            color = green if blend_ms < 5.0 else (self.AMBER if blend_ms < 15.0 else red)
            self._set_value(self.mixer_values["blend_ms"], f"{blend_ms} ms", color)

        serial_cmds = data.get("serial_cmds_sec")
        if serial_cmds is not None:
            self._set_value(self.mixer_values["serial_cmds"], f"{serial_cmds}", self.WHITE)

        active_ch = data.get("active_channels")
        if active_ch is not None:
            self._set_value(self.mixer_values["active_ch"], f"{active_ch}", self.WHITE)

        hardware = data.get("hardware")
        if isinstance(hardware, dict):
            self._update_maestro_display(hardware, data.get("maestro_errors"))

        if "pi_power" in data:
            self._update_supply_display(data.get("pi_power"))

        if "hotspot_station" in data:
            self._update_hotspot_display(data.get("hotspot_station"))

    def _update_runtime_display(self, estimate: dict):
        """Show estimated battery run-time and state of charge"""
        red = theme_manager.get("red")

        minutes = estimate.get("estimated_minutes_remaining") or 0.0
        soc = estimate.get("soc_percent")
        confidence = estimate.get("confidence")

        if confidence == "warming_up":
            runtime_text, runtime_color = "estimating", self.WHITE
        elif minutes > 0:
            total = int(round(minutes))
            hours, mins = divmod(total, 60)
            runtime_text = f"{hours}h {mins}m" if hours else f"{mins}m"
            runtime_color = red if minutes < 15 else (self.AMBER if minutes < 30 else self.WHITE)
        else:
            runtime_text, runtime_color = "--", self.WHITE

        text = (f'<span style="color: #d8d8d8;">Runtime </span>'
                f'<b style="color: {runtime_color};">{runtime_text}</b>')
        if soc is not None:
            text += f'<span style="color: #d8d8d8;"> · {soc:.0f}%</span>'
            self.soc_bar.setValue(max(0, min(100, int(round(soc)))))
        self.runtime_label.setText(text)

        self._update_usage_display(estimate)

    def _update_usage_display(self, estimate: dict):
        """Charge drawn, session length and peak current since the backend started"""
        used_mah = estimate.get("mah_consumed")
        session_minutes = estimate.get("session_minutes")
        peak = estimate.get("peak_current_session")
        if used_mah is None:
            return

        used = f"{used_mah / 1000:.1f} Ah" if used_mah >= 1000 else f"{used_mah:.0f} mAh"
        parts = [f'Used <b style="color: {self.WHITE};">{used}</b>']
        if session_minutes is not None:
            total = int(round(session_minutes))
            hours, mins = divmod(total, 60)
            parts.append(f"{hours}h {mins}m" if hours else f"{mins} min")
        if peak:
            parts.append(f'peak <b style="color: {self.WHITE};">{peak:.0f} A</b>')
        self.usage_label.setText(f'<span style="color: {self.TEXT_SOFT};">{" · ".join(parts)}</span>')

    def _update_maestro_display(self, hardware: dict, maestro_errors):
        """Maestro rows: connection, error code and error names when available"""
        green = theme_manager.get("green")
        red = theme_manager.get("red")
        errors_supported = isinstance(maestro_errors, dict)
        self.clear_errors_btn.setEnabled(errors_supported)

        for key, widgets in self._maestro_widgets.items():
            status = hardware.get(key) or {}
            errors = maestro_errors.get(key) if errors_supported else None
            in_error = False

            if not status.get("connected", False):
                self._set_badge(widgets["badge"], "OFFLINE", red)
                self._set_value(widgets["code"], "--", self.LABEL_GREY)
                widgets["detail"].setText(widgets["default_detail"])
                in_error = True
            elif isinstance(errors, dict) and errors.get("code") is not None:
                code = int(errors.get("code", 0))
                self._set_value(widgets["code"], f"0x{code:04X}", "#ff8a8a" if code else self.LABEL_GREY)
                if code:
                    in_error = True
                    self._set_badge(widgets["badge"], "ERROR", red)
                    names = ", ".join(errors.get("errors") or []) or "Error"
                    when = errors.get("last_error_time")
                    if when:
                        names += " · " + time.strftime("%H:%M:%S", time.localtime(when))
                    widgets["detail"].setText(names)
                else:
                    self._set_badge(widgets["badge"], "OK", green)
                    widgets["detail"].setText(widgets["default_detail"])
            else:
                self._set_badge(widgets["badge"], "OK", green)
                self._set_value(widgets["code"], "--", self.LABEL_GREY)
                widgets["detail"].setText(widgets["default_detail"])

            if in_error != widgets["error"]:
                widgets["error"] = in_error
                self._style_tile(widgets["row"], self.TILE_ERROR_BG if in_error else self.TILE_BG)

    def _update_supply_display(self, pi_power):
        """Pi 5V supply flags from the backend throttle status"""
        if not isinstance(pi_power, dict):
            self._set_badge(self.supply_now_badge, "--", None)
            self.supply_history_badge.hide()
            return

        if pi_power.get("under_voltage_now"):
            self._set_badge(self.supply_now_badge, "UNDER-VOLTAGE NOW", theme_manager.get("red"))
        elif pi_power.get("throttled_now"):
            self._set_badge(self.supply_now_badge, "THROTTLED NOW", theme_manager.get("red"))
        else:
            self._set_badge(self.supply_now_badge, "OK", theme_manager.get("green"))

        if pi_power.get("under_voltage_occurred") or pi_power.get("throttled_occurred"):
            self._set_badge(self.supply_history_badge, "THROTTLED SINCE BOOT", self.AMBER)
            self.supply_history_badge.show()
        else:
            self.supply_history_badge.hide()

    def _update_hotspot_display(self, station):
        """Steam Deck link quality as reported by the Pi hotspot"""
        green = theme_manager.get("green")
        if not isinstance(station, dict):
            for key in ("signal", "retries", "failed"):
                self._set_value(self.link_values[key], "--", self.WHITE)
            return

        signal = station.get("signal_dbm")
        if signal is not None:
            self._set_value(self.link_values["signal"], f"{signal} dBm", green if signal >= -65 else self.AMBER)
        retries = station.get("tx_retries_pct")
        if retries is not None:
            self._set_value(self.link_values["retries"], f"{retries:.1f}%", green if retries < 10 else self.AMBER)
        failed = station.get("tx_failed")
        if failed is not None:
            self._set_value(self.link_values["failed"], f"{failed}", self.WHITE)

    def _format_throughput(self, bytes_per_sec: float) -> str:
        """Convert bytes/sec to bits/sec, auto-scaled to kbps or Mbps"""
        bits_per_sec = max(bytes_per_sec, 0.0) * 8
        if bits_per_sec >= 999_500:
            return f"{bits_per_sec / 1_000_000:.1f} Mbps"
        return f"{bits_per_sec / 1000:.0f} kbps"

    def _update_throughput_display(self):
        """Sample /proc/net/dev to calculate wlan0 TX/RX throughput"""
        try:
            now = time.monotonic()
            rx_bytes = tx_bytes = None

            with open("/proc/net/dev", "r") as f:
                for line in f:
                    if "wlan0:" in line:
                        parts = line.split()
                        rx_bytes = int(parts[1])
                        tx_bytes = int(parts[9])
                        break

            if rx_bytes is None:
                return

            if self._last_net_bytes is not None:
                elapsed = now - self._last_net_time
                if elapsed > 0:
                    rx_rate = (rx_bytes - self._last_net_bytes[0]) / elapsed
                    tx_rate = (tx_bytes - self._last_net_bytes[1]) / elapsed
                    self._set_value(self.link_values["throughput"],
                                    f"{self._format_throughput(rx_rate)} / {self._format_throughput(tx_rate)}",
                                    self.WHITE)

            self._last_net_bytes = (rx_bytes, tx_bytes)
            self._last_net_time = now

        except (FileNotFoundError, PermissionError):
            # /proc/net/dev not available (macOS dev environment)
            pass
        except Exception as e:
            self.logger.debug(f"Throughput read failed: {e}")

    def connect_network_monitor(self, network_monitor):
        """Connect the shared network monitor from the header bar."""
        self._network_monitor = network_monitor
        network_monitor.wifi_updated.connect(self._update_wifi_display)
        network_monitor.connectivity_updated.connect(self._update_ping_display)

    def _update_wifi_display(self, signal_percent: int, status_text: str, _unused: float):
        """Update the Steam Deck WiFi signal value"""
        green = theme_manager.get("green")
        red = theme_manager.get("red")
        color = green if signal_percent >= 50 else (self.AMBER if signal_percent >= 25 else red)
        self._set_value(self.link_values["wifi"], f"{signal_percent}%", color)

    def _update_ping_display(self, ping_ms: float, is_connected: bool):
        """Update the Pi ping value"""
        green = theme_manager.get("green")
        red = theme_manager.get("red")
        if is_connected and ping_ms > 0:
            color = green if ping_ms < 30 else (self.AMBER if ping_ms < 80 else red)
            self._set_value(self.link_values["ping"], f"{ping_ms:.1f} ms", color)
        else:
            self._set_value(self.link_values["ping"], "unreachable", red)

    def _update_graphs(self):
        """Redraw the graph with times relative to the newest reading"""
        try:
            if len(self.time_data) < 2:
                return
            latest = self.time_data[-1]
            x_values = [t - latest for t in self.time_data]
            self.voltage_curve.setData(x_values, list(self.battery_voltage_data))
            self.current_a1_plot.setData(x_values, list(self.current_a1_data))
            self.current_a2_plot.setData(x_values, list(self.current_a2_data))
        except Exception as e:
            self.logger.error(f"Failed to update graph: {e}")

    def cleanup(self):
        """Cleanup health screen resources"""
        if hasattr(self, "status_poll_timer"):
            self.status_poll_timer.stop()
        super().cleanup()