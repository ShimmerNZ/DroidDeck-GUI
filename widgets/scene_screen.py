#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - Scene Screen
Scene list on the left, editor for the selected scene on the right.
Text fields sit at the top of the editor so they stay visible above the
on-screen keyboard.
"""

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QWidget,
    QComboBox, QMessageBox, QLineEdit, QListWidget, QListWidgetItem,
    QListView, QFrame, QSizePolicy, QAbstractButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize, QPointF, QRectF, QRegularExpression
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QPen, QPixmap, QPainterPath, QIcon, QRegularExpressionValidator
)
from widgets.base_screen import BaseScreen
from core.config_manager import config_manager
from core.theme_manager import theme_manager
from core.utils import error_boundary

# Category definitions with emojis
CATEGORIES = {
    "Happy": "😊",
    "Sad": "😢",
    "Curious": "🤔",
    "Angry": "😠",
    "Surprise": "😲",
    "Love": "❤️",
    "Calm": "😌",
    "Sound Effect": "📊",
    "Misc": "⭐",
    "Idle": "💤",
    "Sleepy": "😴"
}

SCENES_CONFIG_PATH = "resources/configs/scenes_config.json"
NO_BOTTANGO_SCENES = "No scenes available"
FILTER_ALL = "All"

# Layout - matches the Health screen card positions
CONTENT_WIDTH = 1061
CONTENT_HEIGHT = 490
CARD_GAP = 12
CARD_HEIGHT = 434
LIST_CARD_WIDTH = 470
EDIT_CARD_WIDTH = 579
BAR_HEIGHT = 44
LIST_ROW_HEIGHT = 40
LIST_ROW_SPACING = 4
CATEGORIES_PER_ROW = 5

CARD_OBJECT_NAME = "scene_card"

# Fixed colours shared by every theme
LABEL_GREY = "#9e9e9e"
TEXT_SOFT = "#d6d6d6"
TILE_BG = "#202020"
ROW_BG = "#1f1f1f"
ICON_GREY = "#8a8a8a"
DIVIDER = "#2e2e2e"
DIRTY_ORANGE = "#ff9800"


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
    """Card frame: panel background with the theme colour as a soft border"""
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
    """Dark button used for secondary actions"""
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
    """Solid button for a main action"""
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


def outline_button_style(color: str, text: str) -> str:
    """Transparent button with a coloured outline (destructive actions)"""
    return f"""
        QPushButton {{
            background: transparent;
            color: {text};
            border: 1px solid {color};
            border-radius: 8px;
        }}
        QPushButton:hover {{
            background-color: {rgba(color, 0.15)};
        }}
        QPushButton:pressed {{
            background-color: {rgba(color, 0.3)};
        }}
        QPushButton:disabled {{
            color: #666;
            border-color: #444;
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


def _make_icon(kind: str, color: str) -> QPixmap:
    """Small line icon for a scene type: 'audio' (note) or 'anim' (film)"""
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.6))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "audio":
        path = QPainterPath()
        path.moveTo(5, 12)
        path.lineTo(5, 2)
        path.lineTo(13, 1)
        path.lineTo(13, 11)
        painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(QPointF(3.2, 12.5), 2.2, 2.2)
        painter.drawEllipse(QPointF(11.2, 11.5), 2.2, 2.2)
    elif kind == "anim":
        painter.drawRoundedRect(QRectF(1, 3, 14, 10), 1.5, 1.5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        triangle = QPainterPath()
        triangle.moveTo(6.5, 6)
        triangle.lineTo(10.5, 8)
        triangle.lineTo(6.5, 10)
        triangle.closeSubpath()
        painter.drawPath(triangle)
    else:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        triangle = QPainterPath()
        triangle.moveTo(3, 1)
        triangle.lineTo(14, 8)
        triangle.lineTo(3, 15)
        triangle.closeSubpath()
        painter.drawPath(triangle)
    painter.end()
    return pixmap


def _format_duration(value) -> str:
    try:
        return f"{float(value):.1f}s"
    except (TypeError, ValueError):
        return "--"


class ToggleSwitch(QAbstractButton):
    """On/off switch sized for touch"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(52, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

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


class SceneListRow(QFrame):
    """One scene in the list: marker, name, type icons, duration"""

    def __init__(self, scene: dict):
        super().__init__()
        self.scene = scene
        self.setObjectName("scene_list_row")
        self.setFixedHeight(LIST_ROW_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)

        self.marker = QFrame()
        self.marker.setFixedSize(4, 18)

        self.name_label = QLabel()
        self.name_label.setFont(px_font(16))
        self.name_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        icons_widget = QWidget()
        icons_widget.setFixedWidth(38)
        icons_widget.setStyleSheet("background: transparent;")
        icons = QHBoxLayout(icons_widget)
        icons.setContentsMargins(0, 0, 0, 0)
        icons.setSpacing(6)
        icons.addStretch(1)
        self.audio_icon = QLabel()
        self.audio_icon.setPixmap(_make_icon("audio", ICON_GREY))
        self.anim_icon = QLabel()
        self.anim_icon.setPixmap(_make_icon("anim", ICON_GREY))
        icons.addWidget(self.audio_icon)
        icons.addWidget(self.anim_icon)

        self.duration_label = QLabel()
        self.duration_label.setFont(px_font(13, family="Consolas"))
        self.duration_label.setFixedWidth(40)
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(self.marker)
        layout.addWidget(self.name_label, 1)
        layout.addWidget(icons_widget)
        layout.addWidget(self.duration_label)

        self._selected = False
        self.refresh()

    def refresh(self):
        """Redraw the row from its scene data"""
        self.name_label.setText(self.scene.get("label", ""))
        self.audio_icon.setVisible(bool(self.scene.get("audio_enabled")))
        self.anim_icon.setVisible(bool(self.scene.get("script_enabled")))
        self.duration_label.setText(_format_duration(self.scene.get("duration")))
        self.set_selected(self._selected)

    def set_selected(self, selected: bool):
        self._selected = selected
        primary = theme_manager.get("primary_color")
        if selected:
            background, border = rgba(primary, 0.14), f"1px solid {primary}"
        else:
            background, border = ROW_BG, "1px solid transparent"
        self.setStyleSheet(f"""
            QFrame#scene_list_row {{
                background-color: {background};
                border: {border};
                border-radius: 10px;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)
        marker = primary if selected else "transparent"
        self.marker.setStyleSheet(f"background-color: {marker}; border: none; border-radius: 2px;")
        name_color = "white" if selected else TEXT_SOFT
        self.name_label.setStyleSheet(f"color: {name_color}; background: transparent; border: none;")
        self.duration_label.setStyleSheet("color: #bdbdbd; background: transparent; border: none;")


class SceneList(QListWidget):
    """Scene list whose rows always span the full list width"""

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = self.viewport().width()
        for i in range(self.count()):
            self.item(i).setSizeHint(QSize(width, LIST_ROW_HEIGHT))


class SceneScreen(BaseScreen):
    """Interface for managing emotion scenes and their audio / animation"""

    scenes_updated = pyqtSignal()  # Signal to notify HomeScreen of changes

    def _setup_screen(self):
        self.setFixedWidth(1200)
        self.scenes_data = []
        self.audio_files = []
        self.bottango_scenes = []  # Available Bottango scenes from backend
        self.selected_scene = None
        self.filter_category = FILTER_ALL
        self._dirty_ids = set()
        self._structure_changed = False
        self._loading_editor = False
        self._row_widgets = []

        theme_manager.register_callback(self.update_theme)

        self.init_ui()
        self._load_editor()
        self._show_summary()

        if self.websocket:
            # All scene-related messages route through the central dispatcher;
            # registrations stay active while hidden so unsolicited updates
            # (e.g. the Bottango watcher) keep this screen's data current
            for msg_type in ("scene_list", "audio_files", "backend_refresh_response",
                             "scenes_saved", "bottango_scenes_updated",
                             "bottango_import_complete"):
                self.subscribe(msg_type, self.handle_message)
            # D-pad moves through the list only while this screen is shown
            self.subscribe_while_visible("navigation", self._on_navigation)
            # Wait for connection before requesting audio files
            if self.websocket.is_connected():
                self.request_audio_files()
            else:
                self.connection_check_timer = QTimer()
                self.connection_check_timer.timeout.connect(self.check_connection_and_request_audio)
                self.connection_check_timer.start(1000)
        else:
            self.use_fallback_audio_files()

    def check_connection_and_request_audio(self):
        """Check WebSocket connection and request audio files when ready"""
        if self.websocket and self.websocket.is_connected():
            self.connection_check_timer.stop()
            self.request_audio_files()

    # ---------- Layout ----------

    def init_ui(self):
        self._cards = []
        self._card_titles = []
        self._captions = []
        self._row_labels = []

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

    def _build_list_card(self):
        card = self._make_card(LIST_CARD_WIDTH)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(self._card_title("SCENES"))
        self.count_label = QLabel("0 of 0")
        self.count_label.setFont(px_font(13))
        self._captions.append(self.count_label)
        header.addWidget(self.count_label, 1)
        header.addWidget(self._caption("SHOW"))

        self.filter_combo = QComboBox()
        self.filter_combo.setView(QListView())
        self.filter_combo.setFixedSize(170, 40)
        self.filter_combo.setFont(px_font(15))
        self.filter_combo.addItem(FILTER_ALL)
        self.filter_combo.addItems(sorted(CATEGORIES.keys()))
        self.filter_combo.currentTextChanged.connect(self._on_filter_changed)
        header.addWidget(self.filter_combo)
        layout.addLayout(header)

        self.list_divider = QFrame()
        self.list_divider.setFixedHeight(1)
        layout.addWidget(self.list_divider)

        self.scene_list = SceneList()
        self.scene_list.setSpacing(LIST_ROW_SPACING // 2)
        self.scene_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.scene_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scene_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scene_list.currentRowChanged.connect(self._on_list_row_changed)
        layout.addWidget(self.scene_list, 1)
        return card

    def _build_editor_card(self):
        card = self._make_card(EDIT_CARD_WIDTH)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(self._card_title("EDIT SCENE"))
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

        # Name and delay first, so they stay above the on-screen keyboard
        fields = QHBoxLayout()
        fields.setSpacing(12)
        name_col = QVBoxLayout()
        name_col.setSpacing(4)
        name_col.addWidget(self._caption("NAME"))
        self.name_edit = QLineEdit()
        self.name_edit.setFixedHeight(44)
        self.name_edit.setFont(px_font(18))
        self.name_edit.setPlaceholderText("Scene name")
        self.name_edit.textEdited.connect(self._on_name_edited)
        name_col.addWidget(self.name_edit)
        fields.addLayout(name_col, 1)

        delay_col = QVBoxLayout()
        delay_col.setSpacing(4)
        delay_col.addWidget(self._caption("DELAY (MS)"))
        self.delay_input = QLineEdit()
        self.delay_input.setFixedSize(130, 44)
        self.delay_input.setFont(px_font(18))
        self.delay_input.setPlaceholderText("0")
        self.delay_input.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{0,6}")))
        self.delay_input.setToolTip("Audio starts this long after the animation (audio and animation both on)")
        self.delay_input.textEdited.connect(self._on_delay_edited)
        delay_col.addWidget(self.delay_input)
        fields.addLayout(delay_col)
        body.addLayout(fields)

        # Category pills
        cat_col = QVBoxLayout()
        cat_col.setSpacing(6)
        cat_col.addWidget(self._caption("CATEGORIES"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        self.category_buttons = {}
        for idx, category in enumerate(CATEGORIES.keys()):
            button = QPushButton(category)
            button.setCheckable(True)
            button.setFixedHeight(32)
            button.setFont(px_font(12, bold=True))
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.toggled.connect(lambda checked, c=category: self._on_category_toggled(c, checked))
            grid.addWidget(button, idx // CATEGORIES_PER_ROW, idx % CATEGORIES_PER_ROW)
            self.category_buttons[category] = button
        for col in range(CATEGORIES_PER_ROW):
            grid.setColumnStretch(col, 1)
        cat_col.addLayout(grid)
        body.addLayout(cat_col)

        # Audio row
        self.audio_switch = ToggleSwitch()
        self.audio_switch.toggled.connect(self._on_audio_toggled)
        self.audio_file_combo = self._make_editor_combo()
        self.audio_file_combo.currentTextChanged.connect(self._on_audio_file_changed)
        body.addLayout(self._switch_row("Audio", self.audio_switch, self.audio_file_combo))

        # Animation row
        self.script_switch = ToggleSwitch()
        self.script_switch.toggled.connect(self._on_script_toggled)
        self.bottango_combo = self._make_editor_combo()
        self.bottango_combo.currentTextChanged.connect(self._on_bottango_changed)
        body.addLayout(self._switch_row("Animation", self.script_switch, self.bottango_combo))

        body.addStretch(1)

        # Duration and actions
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self._caption("DURATION"))
        self.duration_value_label = QLabel("--")
        self.duration_value_label.setFont(px_font(16, family="Consolas"))
        self.duration_value_label.setToolTip("Calculated from the audio and Bottango scene lengths")
        actions.addWidget(self.duration_value_label)
        actions.addStretch(1)

        self.delete_btn = QPushButton("DELETE")
        self.delete_btn.setFixedSize(110, 44)
        self.delete_btn.setFont(px_font(14, bold=True))
        self.delete_btn.clicked.connect(lambda: self.delete_selected_scene())
        actions.addWidget(self.delete_btn)

        self.test_btn = QPushButton("TEST")
        self.test_btn.setFixedSize(130, 44)
        self.test_btn.setFont(px_font(14, bold=True))
        self.test_btn.setIconSize(QSize(14, 14))
        self.test_btn.clicked.connect(lambda: self.test_selected_scene())
        actions.addWidget(self.test_btn)
        body.addLayout(actions)

        layout.addWidget(self.editor_body, 1)
        return card

    def _make_editor_combo(self) -> QComboBox:
        combo = QComboBox()
        combo.setView(QListView())
        combo.setFixedHeight(40)
        combo.setFont(px_font(14))
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(10)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return combo

    def _switch_row(self, text: str, switch: ToggleSwitch, combo: QComboBox):
        row = QHBoxLayout()
        row.setSpacing(12)
        label = QLabel(text)
        label.setFont(px_font(15))
        label.setFixedSize(92, 44)
        self._row_labels.append(label)
        row.addWidget(label)
        row.addWidget(switch)
        row.addWidget(combo, 1)
        return row

    def _build_bottom_bar(self):
        bar = QHBoxLayout()
        bar.setSpacing(12)

        self.add_btn = QPushButton("+ ADD NEW SCENE")
        self.add_btn.setFixedSize(200, BAR_HEIGHT)
        self.add_btn.setFont(px_font(15, bold=True))
        self.add_btn.clicked.connect(lambda: self.add_scene())
        bar.addWidget(self.add_btn)

        self.status_label = QLabel("Ready")
        self.status_label.setFont(px_font(13))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setFixedHeight(BAR_HEIGHT)
        bar.addWidget(self.status_label, 1)

        self.refresh_btn = QPushButton("REFRESH")
        self.refresh_btn.setFixedSize(140, BAR_HEIGHT)
        self.refresh_btn.setToolTip("Refresh scenes, audio files and Bottango scenes from the backend")
        self.refresh_btn.setFont(px_font(15, bold=True))
        self.refresh_btn.clicked.connect(lambda: self.refresh_from_backend())
        bar.addWidget(self.refresh_btn)

        self.save_btn = QPushButton("SAVE CONFIGURATION")
        self.save_btn.setFixedSize(200, BAR_HEIGHT)
        self.save_btn.setFont(px_font(15, bold=True))
        self.save_btn.clicked.connect(lambda: self.save_config())
        bar.addWidget(self.save_btn)
        return bar

    # ---------- Styling ----------

    def _apply_styles(self):
        """Apply theme colours to every styled widget"""
        primary = theme_manager.get("primary_color")
        green = theme_manager.get("green")
        red = theme_manager.get("red")

        for card in self._cards:
            card.setStyleSheet(card_style())
        for title in self._card_titles:
            title.setStyleSheet(f"color: {primary}; background: transparent; border: none;")
        for caption in self._captions:
            caption.setStyleSheet(f"color: {LABEL_GREY}; background: transparent; border: none;")
        for label in self._row_labels:
            label.setStyleSheet(f"color: {TEXT_SOFT}; background: transparent; border: none;")
        self.list_divider.setStyleSheet(f"background-color: {DIVIDER}; border: none;")
        self.duration_value_label.setStyleSheet("color: white; background: transparent; border: none;")

        self.name_edit.setStyleSheet(input_style())
        self.delay_input.setStyleSheet(input_style())
        for combo in (self.filter_combo, self.audio_file_combo, self.bottango_combo):
            combo.setStyleSheet(combo_style())

        pill_style = f"""
            QPushButton {{
                background-color: #242424;
                color: {TEXT_SOFT};
                border: 1px solid #3e3e3e;
                border-radius: 16px;
                padding: 0px 4px;
            }}
            QPushButton:checked {{
                background-color: {primary};
                color: #111111;
                border: 1px solid {primary};
            }}
            QPushButton:disabled {{
                color: #555;
                border-color: #333;
            }}
        """
        for button in self.category_buttons.values():
            button.setStyleSheet(pill_style)

        self.scene_list.setStyleSheet(f"""
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

        self.add_btn.setStyleSheet(plain_button_style())
        self.refresh_btn.setStyleSheet(plain_button_style())
        self.save_btn.setStyleSheet(filled_button_style(green))
        self.delete_btn.setStyleSheet(outline_button_style(red, "#ff7777"))
        self.test_btn.setStyleSheet(filled_button_style(primary))
        self.test_btn.setIcon(QIcon(_make_icon("play", "#111111")))

        for row in self._row_widgets:
            row.set_selected(row.scene is self.selected_scene)
        self.audio_switch.update()
        self.script_switch.update()
        self._update_dirty_label()

    def update_theme(self):
        """Update all UI elements when theme changes"""
        self._apply_styles()

    # ---------- Scene list ----------

    def _visible_scenes(self):
        if self.filter_category == FILTER_ALL:
            return list(self.scenes_data)
        return [s for s in self.scenes_data if self.filter_category in s.get("categories", [])]

    def _sort_scenes(self):
        self.scenes_data.sort(key=lambda s: s.get("label", "").lower())

    def _rebuild_list(self, keep_scene=None):
        """Rebuild the list for the current filter and reselect a scene"""
        target = keep_scene if keep_scene is not None else self.selected_scene
        visible = self._visible_scenes()

        self.scene_list.blockSignals(True)
        self.scene_list.clear()
        self._row_widgets = []
        width = self.scene_list.viewport().width()
        for scene in visible:
            item = QListWidgetItem()
            item.setSizeHint(QSize(width, LIST_ROW_HEIGHT))
            self.scene_list.addItem(item)
            row = SceneListRow(scene)
            self.scene_list.setItemWidget(item, row)
            self._row_widgets.append(row)
        self.scene_list.blockSignals(False)

        self.count_label.setText(f"{len(visible)} of {len(self.scenes_data)}")

        index = next((i for i, s in enumerate(visible) if s is target), -1)
        if index < 0 and visible:
            index = 0
        if index >= 0:
            self._select_row(index)
        else:
            self.selected_scene = None
            self._load_editor()

    def _select_row(self, index: int):
        self.scene_list.blockSignals(True)
        self.scene_list.setCurrentRow(index)
        self.scene_list.blockSignals(False)
        self._on_list_row_changed(index)
        item = self.scene_list.item(index)
        if item is not None:
            self.scene_list.scrollToItem(item)

    def _on_list_row_changed(self, index: int):
        if not (0 <= index < len(self._row_widgets)):
            return
        self.selected_scene = self._row_widgets[index].scene
        for i, row in enumerate(self._row_widgets):
            row.set_selected(i == index)
        self._load_editor()

    def _on_filter_changed(self, text: str):
        self.filter_category = text or FILTER_ALL
        self._rebuild_list()

    def _refresh_selected_row(self):
        for row in self._row_widgets:
            if row.scene is self.selected_scene:
                row.refresh()
                break

    def _on_navigation(self, msg: dict):
        """D-pad up/down moves through the scene list"""
        action = msg.get("action")
        if action not in ("up", "down") or self.scene_list.count() == 0:
            return
        current = max(0, self.scene_list.currentRow())
        step = -1 if action == "up" else 1
        new_index = max(0, min(self.scene_list.count() - 1, current + step))
        if new_index != self.scene_list.currentRow():
            self._select_row(new_index)

    # ---------- Editor ----------

    def _load_editor(self):
        """Show the selected scene in the editor"""
        scene = self.selected_scene
        self._loading_editor = True
        try:
            self.editor_body.setEnabled(scene is not None)
            if scene is None:
                self.name_edit.clear()
                self.delay_input.clear()
                for button in self.category_buttons.values():
                    button.setChecked(False)
                self.audio_switch.setChecked(False)
                self.script_switch.setChecked(False)
                self.duration_value_label.setText("--")
                return

            self.name_edit.setText(scene.get("label", ""))
            self.delay_input.setText(str(scene.get("delay", 0) or 0))
            categories = scene.get("categories", [])
            for category, button in self.category_buttons.items():
                button.setChecked(category in categories)

            self.audio_switch.setChecked(bool(scene.get("audio_enabled")))
            self.script_switch.setChecked(bool(scene.get("script_enabled")))
            self._fill_audio_combo()
            self._fill_bottango_combo()
            self._update_enabled_fields()
            self.duration_value_label.setText(_format_duration(scene.get("duration")).replace("s", " s"))
        finally:
            self._loading_editor = False
        self._update_dirty_label()

    def _fill_audio_combo(self):
        """Audio file list, keeping the scene's file visible even if missing"""
        scene = self.selected_scene
        current = scene.get("audio_file", "") if scene else ""
        items = list(self.audio_files)
        if current and current not in items:
            items.insert(0, current)
        self.audio_file_combo.blockSignals(True)
        self.audio_file_combo.clear()
        self.audio_file_combo.addItems(items)
        if current in items:
            self.audio_file_combo.setCurrentText(current)
        elif items:
            self.audio_file_combo.setCurrentIndex(0)
        self.audio_file_combo.setToolTip(self.audio_file_combo.currentText())
        self.audio_file_combo.blockSignals(False)

    def _fill_bottango_combo(self):
        """Bottango scene list, preferring the scene's saved animation"""
        scene = self.selected_scene
        current = scene.get("bottango_scene", "") if scene else ""
        names = [s.get("name", "") for s in self.bottango_scenes if isinstance(s, dict)]
        if current and current not in names:
            names.insert(0, current)
        self.bottango_combo.blockSignals(True)
        self.bottango_combo.clear()
        if names:
            self.bottango_combo.addItems(names)
            if current in names:
                self.bottango_combo.setCurrentText(current)
        else:
            self.bottango_combo.addItem(NO_BOTTANGO_SCENES)
        self.bottango_combo.blockSignals(False)

    def _update_enabled_fields(self):
        audio_on = self.audio_switch.isChecked()
        script_on = self.script_switch.isChecked()
        self.audio_file_combo.setEnabled(audio_on)
        self.bottango_combo.setEnabled(script_on)
        self.delay_input.setEnabled(audio_on and script_on)

    def _mark_dirty(self):
        if self.selected_scene is not None:
            self._dirty_ids.add(id(self.selected_scene))
        self._update_dirty_label()
        self._show_summary()

    def _is_dirty(self) -> bool:
        return bool(self._dirty_ids) or self._structure_changed

    def _clear_dirty(self):
        self._dirty_ids.clear()
        self._structure_changed = False
        self._update_dirty_label()

    def _update_dirty_label(self):
        scene = self.selected_scene
        dirty = scene is not None and id(scene) in self._dirty_ids
        self.dirty_label.setText("Unsaved changes" if dirty else "Saved")
        color = DIRTY_ORANGE if dirty else LABEL_GREY
        self.dirty_label.setStyleSheet(f"color: {color}; background: transparent; border: none;")

    def _show_summary(self):
        """Footer line: scene count and unsaved state"""
        total = len(self.scenes_data)
        changes = len(self._dirty_ids)
        if changes:
            text = f"{total} scenes · {changes} unsaved change{'s' if changes != 1 else ''}"
            self.update_status(text, DIRTY_ORANGE)
        elif self._structure_changed:
            self.update_status(f"{total} scenes · unsaved changes", DIRTY_ORANGE)
        else:
            self.update_status(f"{total} scenes · all saved", LABEL_GREY)

    def _on_name_edited(self, text: str):
        if self._loading_editor or self.selected_scene is None:
            return
        self.selected_scene["label"] = text
        self._refresh_selected_row()
        self._mark_dirty()

    def _on_delay_edited(self, text: str):
        if self._loading_editor or self.selected_scene is None:
            return
        try:
            self.selected_scene["delay"] = int(text) if text else 0
        except ValueError:
            self.selected_scene["delay"] = 0
        self._mark_dirty()

    def _on_category_toggled(self, category: str, checked: bool):
        if self._loading_editor or self.selected_scene is None:
            return

        if category == "Idle" and checked:
            # Idle is exclusive: clear every other category
            for other, button in self.category_buttons.items():
                if other != "Idle" and button.isChecked():
                    button.blockSignals(True)
                    button.setChecked(False)
                    button.blockSignals(False)
            self._show_idle_info()
        elif category != "Idle" and checked:
            idle = self.category_buttons.get("Idle")
            if idle and idle.isChecked():
                idle.blockSignals(True)
                idle.setChecked(False)
                idle.blockSignals(False)

        self.selected_scene["categories"] = [
            c for c, button in self.category_buttons.items() if button.isChecked()
        ]
        self._mark_dirty()

    def _show_idle_info(self):
        primary = theme_manager.get("primary_color")
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("Idle Category")
        msg.setText("💤 Idle is an exclusive category")
        msg.setInformativeText(
            "Idle scenes use ADDITIVE blending and layer over joystick control.\n\n"
            "For safety, Idle scenes should only contain subtle head/neck movements.\n\n"
            "Other categories have been deselected."
        )
        msg.setStyleSheet(f"""
            QMessageBox {{
                background-color: #222;
            }}
            QMessageBox QLabel {{
                color: {primary};
                font-size: 14px;
            }}
            QPushButton {{
                background-color: #333;
                border: 2px solid {primary};
                border-radius: 6px;
                color: {primary};
                padding: 8px 16px;
                font-weight: bold;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: #444;
            }}
        """)
        msg.exec()

    def _on_audio_toggled(self, checked: bool):
        self._update_enabled_fields()
        if self._loading_editor or self.selected_scene is None:
            return
        self.selected_scene["audio_enabled"] = checked
        if checked and not self.selected_scene.get("audio_file"):
            self.selected_scene["audio_file"] = self.audio_file_combo.currentText()
        self._refresh_selected_row()
        self._mark_dirty()

    def _on_script_toggled(self, checked: bool):
        self._update_enabled_fields()
        if self._loading_editor or self.selected_scene is None:
            return
        self.selected_scene["script_enabled"] = checked
        if checked and not self.selected_scene.get("bottango_scene"):
            name = self.bottango_combo.currentText()
            self.selected_scene["bottango_scene"] = "" if name == NO_BOTTANGO_SCENES else name
        self._refresh_selected_row()
        self._mark_dirty()

    def _on_audio_file_changed(self, text: str):
        self.audio_file_combo.setToolTip(text)
        if self._loading_editor or self.selected_scene is None:
            return
        self.selected_scene["audio_file"] = text
        self._mark_dirty()

    def _on_bottango_changed(self, text: str):
        if self._loading_editor or self.selected_scene is None:
            return
        self.selected_scene["bottango_scene"] = "" if text == NO_BOTTANGO_SCENES else text
        self._mark_dirty()

    def _export_scene(self, scene: dict) -> dict:
        """Scene dict in the saved format"""
        audio_enabled = bool(scene.get("audio_enabled"))
        script_enabled = bool(scene.get("script_enabled"))

        audio_file = ""
        if audio_enabled:
            audio_file = scene.get("audio_file", "") or (self.audio_files[0] if self.audio_files else "")

        bottango_scene = ""
        if script_enabled:
            bottango_scene = scene.get("bottango_scene", "")
            if not bottango_scene and self.bottango_scenes:
                bottango_scene = self.bottango_scenes[0].get("name", "")

        try:
            duration = float(scene.get("duration", 1.0))
        except (TypeError, ValueError):
            duration = 1.0

        try:
            delay = int(scene.get("delay", 0) or 0)
        except (TypeError, ValueError):
            delay = 0
        if not (audio_enabled and script_enabled):
            delay = 0

        return {
            "label": str(scene.get("label", "")).strip(),
            "emoji": "🎭",
            "categories": [c for c in CATEGORIES if c in scene.get("categories", [])],
            "audio_enabled": audio_enabled,
            "audio_file": audio_file,
            "script_enabled": script_enabled,
            "bottango_scene": bottango_scene,
            "duration": duration,
            "delay": delay
        }

    # ---------- Backend communication ----------

    @error_boundary
    def request_audio_files(self):
        primary = theme_manager.get("primary_color")

        if not self.websocket or not self.websocket.is_connected():
            self.logger.warning("WebSocket not connected - using fallback audio list")
            self.use_fallback_audio_files()
            return

        self.update_status("Requesting audio files...", primary)
        success = self.send_websocket_message("get_audio_files")
        if not success:
            self.logger.warning("Failed to request audio files - using fallback list")
            self.use_fallback_audio_files()

    def use_fallback_audio_files(self):
        """Set fallback audio files and update all UI elements"""
        self.update_status("Using fallback audio list", "orange")
        self.audio_files = [
            "Audio Files Not Found.MP3"
        ]
        self.update_audio_files()

    @error_boundary
    def refresh_from_backend(self):
        """Refresh scenes, audio files, and Bottango scenes from backend"""
        primary = theme_manager.get("primary_color")
        self.update_status("Refreshing from backend...", primary)

        self.refresh_status = {
            "scenes_complete": False,
            "audio_complete": False,
            "bottango_complete": False,
            "scenes_count": 0,
            "audio_count": 0,
            "bottango_count": 0,
            "scenes_success": False,
            "audio_success": False,
            "bottango_success": False
        }

        # Backend returns audio + Bottango scenes; scenes are requested separately
        refresh_success = self.send_websocket_message("refresh_backend")
        scenes_success = self.send_websocket_message("get_scenes")

        if not (refresh_success or scenes_success):
            self.update_status("Backend unavailable - keeping local data", "orange")
            self.logger.warning("Failed to refresh from backend")

    def update_status(self, message, color=None):
        """Update the status line in the bottom bar"""
        if color is None:
            color = theme_manager.get("primary_color")
        self.status_label.setText(message)
        self.status_label.setStyleSheet(
            f"color: {color}; background: transparent; border: none;"
        )

    @error_boundary
    def handle_message(self, msg: dict):
        try:
            msg_type = msg.get("type")

            green = theme_manager.get("green")
            red = theme_manager.get("red")

            if msg_type == "scene_list":
                scenes = msg.get("scenes", [])
                if scenes:
                    self.scenes_data = scenes
                    self.update_scene_rows()
                    self._sync_calculated_durations(scenes)
                    if hasattr(self, 'refresh_status'):
                        self.refresh_status["scenes_complete"] = True
                        self.refresh_status["scenes_count"] = len(scenes)
                        self.refresh_status["scenes_success"] = True
                        self.check_refresh_completion()
                    else:
                        self.update_status(f"Loaded {len(scenes)} scenes from backend", green)
                else:
                    self.logger.warning("No scenes received from backend")
                    if hasattr(self, 'refresh_status'):
                        self.refresh_status["scenes_complete"] = True
                        self.refresh_status["scenes_success"] = False
                        self.check_refresh_completion()
                    else:
                        self.update_status("No scenes from backend", "orange")

            elif msg_type == "audio_files":
                files = msg.get("files", [])
                if files:
                    self.audio_files = files
                    self.logger.info(f"Loaded {len(files)} audio files from backend")
                    self.update_audio_files()
                    if hasattr(self, 'refresh_status'):
                        self.refresh_status["audio_complete"] = True
                        self.refresh_status["audio_count"] = len(files)
                        self.refresh_status["audio_success"] = True
                        self.check_refresh_completion()
                    else:
                        self.update_status(f"Loaded {len(files)} audio files", green)
                else:
                    self.logger.warning("No audio files received from backend")
                    if hasattr(self, 'refresh_status'):
                        self.refresh_status["audio_complete"] = True
                        self.refresh_status["audio_success"] = False
                        self.check_refresh_completion()
                    else:
                        self.update_status("No audio files from backend", "orange")

            elif msg_type == "backend_refresh_response":
                files = msg.get("audio_files", [])
                bottango_scenes = msg.get("bottango_scenes", [])

                if files:
                    self.audio_files = files
                    self.logger.info(f"Loaded {len(files)} audio files from backend")
                    self.update_audio_files()

                if bottango_scenes:
                    self.bottango_scenes = bottango_scenes
                    self.logger.info(f"Loaded {len(bottango_scenes)} Bottango scenes from backend")
                    self.update_bottango_scenes()

                if hasattr(self, 'refresh_status'):
                    self.refresh_status["audio_complete"] = True
                    self.refresh_status["audio_count"] = len(files)
                    self.refresh_status["audio_success"] = len(files) > 0
                    self.refresh_status["bottango_complete"] = True
                    self.refresh_status["bottango_count"] = len(bottango_scenes)
                    self.refresh_status["bottango_success"] = len(bottango_scenes) > 0
                    self.check_refresh_completion()
                else:
                    status_msg = f"Loaded {len(files)} audio files, {len(bottango_scenes)} Bottango scenes"
                    self.update_status(status_msg, green)

            elif msg_type == "scenes_saved":
                success = msg.get("success", False)
                if success:
                    self._sync_calculated_durations(msg.get("scenes", []), emit=False)
                    QMessageBox.information(self, "Saved", "Scenes saved successfully to backend.")
                    self.update_status(f"{len(self.scenes_data)} scenes · all saved", green)
                    self.scenes_updated.emit()
                else:
                    error = msg.get("error", "Unknown error")
                    QMessageBox.critical(self, "Error", f"Failed to save to backend: {error}")
                    self.update_status("Save failed", red)

            elif msg_type == "bottango_scenes_updated":
                # Fired automatically by the backend watcher when a new file is converted
                bottango_scenes = msg.get("bottango_scenes", [])
                if bottango_scenes:
                    self.bottango_scenes = bottango_scenes
                    self.update_bottango_scenes()
                    self.update_status(f"Bottango scenes updated ({len(bottango_scenes)} available)", green)
                    self.logger.info(f"Auto-refreshed Bottango scenes: {len(bottango_scenes)} available")

            elif msg_type == "bottango_import_complete":
                converted = msg.get("converted", 0)
                bottango_scenes = msg.get("bottango_scenes", [])
                error = msg.get("error")
                if error:
                    self.update_status(f"Import failed: {error}", red)
                else:
                    if bottango_scenes:
                        self.bottango_scenes = bottango_scenes
                        self.update_bottango_scenes()
                    if converted > 0:
                        self.update_status(f"Imported {converted} scene(s)", green)
                    else:
                        self.update_status(
                            f"No new files to import ({len(bottango_scenes)} scene(s) available)", green)

        except Exception as e:
            red = theme_manager.get("red")
            self.logger.error(f"Failed to handle message: {e}")
            self.update_status("Communication error", red)

    def _sync_calculated_durations(self, backend_scenes, emit: bool = True):
        """Copy the backend's calculated scene durations into the local scene
        config (which the home screen reads) and into the editor."""
        durations = {
            s.get("label"): s.get("duration")
            for s in backend_scenes
            if isinstance(s, dict) and isinstance(s.get("duration"), (int, float))
        }
        if not durations:
            return

        for scene in self.scenes_data:
            label = str(scene.get("label", "")).strip()
            if label in durations:
                scene["duration"] = durations[label]
        for row in self._row_widgets:
            row.refresh()
        if self.selected_scene is not None:
            self.duration_value_label.setText(
                _format_duration(self.selected_scene.get("duration")).replace("s", " s"))

        local = config_manager.get_config(SCENES_CONFIG_PATH)
        if not isinstance(local, list):
            return
        changed = False
        for scene in local:
            if not isinstance(scene, dict):
                continue
            new_duration = durations.get(scene.get("label"))
            if new_duration is not None and scene.get("duration") != new_duration:
                scene["duration"] = new_duration
                changed = True

        if changed:
            if config_manager.save_config(SCENES_CONFIG_PATH, local):
                self.logger.info("Updated local scene durations from backend")
                if emit:
                    self.scenes_updated.emit()
            else:
                self.logger.warning("Could not save calculated scene durations locally")

    def check_refresh_completion(self):
        """Check if refresh is complete and update status accordingly"""
        if not hasattr(self, 'refresh_status'):
            return

        green = theme_manager.get("green")
        red = theme_manager.get("red")

        scenes_done = self.refresh_status.get("scenes_complete", False)
        audio_done = self.refresh_status.get("audio_complete", False)
        bottango_done = self.refresh_status.get("bottango_complete", False)

        if scenes_done and audio_done and bottango_done:
            scenes_count = self.refresh_status["scenes_count"]
            audio_count = self.refresh_status["audio_count"]
            bottango_count = self.refresh_status["bottango_count"]
            scenes_ok = self.refresh_status["scenes_success"]
            audio_ok = self.refresh_status["audio_success"]
            bottango_ok = self.refresh_status["bottango_success"]

            if scenes_ok and audio_ok and bottango_ok:
                self.update_status(f"Loaded {scenes_count} scenes, {audio_count} audio files, {bottango_count} Bottango scenes", green)
            elif scenes_ok and audio_ok:
                self.update_status(f"Loaded {scenes_count} scenes, {audio_count} audio files (No Bottango scenes)", "orange")
            elif scenes_ok:
                self.update_status(f"Loaded {scenes_count} scenes only", "orange")
            else:
                self.update_status("Refresh completed with errors", red)

            del self.refresh_status

    @error_boundary
    def load_local_config(self):
        """Load from standardized path that matches backend"""
        primary = theme_manager.get("primary_color")
        config = config_manager.get_config(SCENES_CONFIG_PATH)
        if isinstance(config, list) and config:
            self.scenes_data = config
            self.update_scene_rows()
            self.update_status(f"Loaded {len(self.scenes_data)} scenes from local cache", primary)
            self.logger.debug(f"Loaded {len(self.scenes_data)} scenes from {SCENES_CONFIG_PATH}")
            return

        self.scenes_data = []
        self.update_scene_rows()
        self.update_status("No local config found - starting empty", primary)
        self.logger.info("No local config found - starting with empty scene list")

    def convert_old_format(self, old_scenes):
        """Convert old emotion_buttons.json format to new Bottango-based format"""
        converted = []
        for scene in old_scenes:
            new_scene = {
                "label": scene.get("label", ""),
                "emoji": "🎭",
                "categories": scene.get("categories", []),
                "audio_enabled": scene.get("audio_enabled", False),
                "audio_file": scene.get("audio_file", ""),
                "script_enabled": scene.get("script_enabled", False),
                "bottango_scene": scene.get("bottango_scene", ""),
                "duration": scene.get("duration", 1.0),
                "delay": scene.get("delay", 0)
            }
            converted.append(new_scene)
        return converted

    @error_boundary
    def update_scene_rows(self):
        """Rebuild the list from scenes_data, keeping the selected scene by name"""
        previous = self.selected_scene.get("label") if self.selected_scene else None
        self.scenes_data = [dict(s) for s in self.scenes_data if isinstance(s, dict)]
        self._sort_scenes()
        self._clear_dirty()
        keep = next((s for s in self.scenes_data if s.get("label") == previous), None)
        self.selected_scene = None
        self._rebuild_list(keep_scene=keep)

    @error_boundary
    def add_scene(self):
        labels = {s.get("label") for s in self.scenes_data}
        number = len(self.scenes_data) + 1
        while f"New Scene {number}" in labels:
            number += 1
        new_scene = {
            "label": f"New Scene {number}",
            "emoji": "🎭",
            "categories": [],
            "audio_enabled": False,
            "audio_file": "",
            "script_enabled": False,
            "bottango_scene": "",
            "duration": 2.0,
            "delay": 0
        }
        self.scenes_data.append(new_scene)
        self._structure_changed = True

        # A new scene has no categories, so it only shows under All
        if self.filter_category != FILTER_ALL:
            self.filter_combo.blockSignals(True)
            self.filter_combo.setCurrentText(FILTER_ALL)
            self.filter_combo.blockSignals(False)
            self.filter_category = FILTER_ALL
        self._rebuild_list(keep_scene=new_scene)
        self._mark_dirty()

    @error_boundary
    def delete_selected_scene(self):
        """Delete the scene shown in the editor after confirmation"""
        scene = self.selected_scene
        if scene is None:
            return
        scene_name = scene.get("label") or "this scene"

        reply = QMessageBox.question(
            self, "Delete Scene",
            f"Are you sure you want to delete '{scene_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        visible = self._visible_scenes()
        position = next((i for i, s in enumerate(visible) if s is scene), 0)
        self.scenes_data = [s for s in self.scenes_data if s is not scene]
        self._dirty_ids.discard(id(scene))
        self._structure_changed = True

        remaining = self._visible_scenes()
        keep = remaining[min(position, len(remaining) - 1)] if remaining else None
        self.selected_scene = None
        self._rebuild_list(keep_scene=keep)
        self._show_summary()
        self.logger.info(f"Deleted scene: {scene_name}")

    @error_boundary
    def test_selected_scene(self):
        if self.selected_scene is not None:
            self.test_scene_data(self._export_scene(self.selected_scene))

    @error_boundary
    def test_scene_data(self, scene_data):
        """Test a scene with given data"""
        scene_name = scene_data.get("label", "Test Scene")
        self.logger.info(f"Testing scene: {scene_name}")
        primary = theme_manager.get("primary_color")
        self.update_status(f"Testing: {scene_name}", primary)

        success = self.send_websocket_message("test_scene", scene=scene_data)
        if not success:
            red = theme_manager.get("red")
            self.update_status(f"Failed to test {scene_name}", red)

    @error_boundary
    def save_config(self):
        """Validate and save all scenes locally and to the backend"""
        primary = theme_manager.get("primary_color")
        red = theme_manager.get("red")

        self.update_status("Validating configuration...", primary)

        scene_data = [self._export_scene(s) for s in self.scenes_data]
        names = [s["label"] for s in scene_data]

        if len(names) != len(set(names)):
            QMessageBox.critical(self, "Error", "Scene names must be unique.")
            self.update_status("Validation failed: Duplicate names", red)
            return

        if any(not name for name in names):
            QMessageBox.critical(self, "Error", "All scenes must have names.")
            self.update_status("Validation failed: Empty names", red)
            return

        self.update_status("Saving configuration...", primary)

        success = config_manager.save_config(SCENES_CONFIG_PATH, scene_data)
        if not success:
            QMessageBox.critical(self, "Error", "Failed to save local configuration.")
            self.update_status("Local save failed", red)
            return

        self.scenes_data = scene_data
        self.update_scene_rows()

        backend_success = self.send_websocket_message("save_scenes", scenes=scene_data)

        if backend_success:
            self.logger.info("Scene configuration saved locally and sent to backend")
            self.update_status("Saved locally, waiting for backend...", primary)
        else:
            QMessageBox.warning(self, "Warning",
                "Scenes saved locally but could not sync to backend. "
                "Backend will use local file on restart.")
            self.update_status("Saved locally only", "orange")
            self.scenes_updated.emit()

    def reload_scenes(self):
        """Public method to reload scenes (called by HomeScreen)"""
        self.send_websocket_message("get_scenes")

    @error_boundary
    def update_audio_files(self):
        """Refresh the editor's audio file list"""
        self._loading_editor = True
        try:
            self._fill_audio_combo()
        finally:
            self._loading_editor = False

    @error_boundary
    def update_bottango_scenes(self, bottango_scenes=None):
        """Refresh the editor's Bottango scene list"""
        if bottango_scenes is not None:
            self.bottango_scenes = bottango_scenes
        self._loading_editor = True
        try:
            self._fill_bottango_combo()
        finally:
            self._loading_editor = False

    def get_scene_summary(self):
        """Get summary of current scene configuration"""
        return {
            "total_scenes": len(self.scenes_data),
            "categories": list(set(cat for scene in self.scenes_data for cat in scene.get("categories", []))),
            "audio_scenes": len([s for s in self.scenes_data if s.get("audio_enabled")]),
            "script_scenes": len([s for s in self.scenes_data if s.get("script_enabled")])
        }