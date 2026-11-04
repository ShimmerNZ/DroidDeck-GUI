#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - Flow Dialog
One themed window that steps through a task: choose, progress, result.
Used for the GUI / server updates, the network test, and the themed
message and confirmation pop-ups shared by every screen.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QFrame,
    QButtonGroup, QScrollArea, QSizePolicy
)
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QPixmap, QPainterPath
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal

from core.theme_manager import theme_manager

LABEL_GREY = "#9e9e9e"
TEXT_SOFT = "#d6d6d6"
TILE_BG = "#202020"
ROW_BG = "#1f1f1f"
DIVIDER = "#2e2e2e"
WARN_ORANGE = "#ff9800"
INFO_BLUE = "#4fa3ff"

STEP_PENDING = "pending"
STEP_ACTIVE = "active"
STEP_DONE = "done"
STEP_ERROR = "error"


def px_font(pixel_size: int, bold: bool = False, spacing: float = 0.0,
            family: str = "Arial") -> QFont:
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


def _step_icon(state: str, size: int = 24) -> QPixmap:
    """Round status icon: tick, active ring, empty ring or cross"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    scale = size / 24.0
    painter.scale(scale, scale)
    if state == STEP_DONE:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme_manager.get("green")))
        painter.drawEllipse(QRectF(1, 1, 22, 22))
        pen = QPen(QColor("#111111"), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        path = QPainterPath()
        path.moveTo(7, 12.5)
        path.lineTo(10.5, 16)
        path.lineTo(17, 8.5)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
    elif state == STEP_ERROR:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme_manager.get("red")))
        painter.drawEllipse(QRectF(1, 1, 22, 22))
        pen = QPen(QColor("white"), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(8, 8), QPointF(16, 16))
        painter.drawLine(QPointF(16, 8), QPointF(8, 16))
    elif state == STEP_ACTIVE:
        primary = QColor(theme_manager.get("primary_color"))
        painter.setPen(QPen(primary, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(2, 2, 20, 20))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(primary)
        painter.drawEllipse(QRectF(7, 7, 10, 10))
    else:
        painter.setPen(QPen(QColor("#4a4a4a"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(2, 2, 20, 20))
    painter.end()
    return pixmap


def _result_icon(success: bool) -> QPixmap:
    """Large tick or cross in a tinted circle"""
    pixmap = QPixmap(56, 56)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(theme_manager.get("green") if success else theme_manager.get("red"))
    fill = QColor(color)
    fill.setAlphaF(0.15)
    painter.setPen(QPen(color, 2))
    painter.setBrush(fill)
    painter.drawEllipse(QRectF(1, 1, 54, 54))
    pen = QPen(color if success else QColor("#ff7777"), 3.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if success:
        path = QPainterPath()
        path.moveTo(17, 29)
        path.lineTo(25, 37)
        path.lineTo(40, 20)
        painter.drawPath(path)
    else:
        painter.drawLine(QPointF(19, 19), QPointF(37, 37))
        painter.drawLine(QPointF(37, 19), QPointF(19, 37))
    painter.end()
    return pixmap


def _power_icon() -> QPixmap:
    """Power symbol in a tinted circle, in the theme colour"""
    pixmap = QPixmap(56, 56)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(theme_manager.get("primary_color"))
    fill = QColor(color)
    fill.setAlphaF(0.15)
    painter.setPen(QPen(color, 2))
    painter.setBrush(fill)
    painter.drawEllipse(QRectF(1, 1, 54, 54))
    pen = QPen(color, 3.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(QPointF(28, 15), QPointF(28, 28))
    painter.drawArc(QRectF(16, 16, 24, 24), 125 * 16, 290 * 16)
    painter.end()
    return pixmap


def _warning_icon() -> QPixmap:
    """Exclamation mark in an amber tinted circle"""
    pixmap = QPixmap(56, 56)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(WARN_ORANGE)
    fill = QColor(color)
    fill.setAlphaF(0.15)
    painter.setPen(QPen(color, 2))
    painter.setBrush(fill)
    painter.drawEllipse(QRectF(1, 1, 54, 54))
    pen = QPen(color, 3.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(QPointF(28, 16), QPointF(28, 32))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(QPointF(28, 39.5), 2.4, 2.4)
    painter.end()
    return pixmap


def _plain_button_style() -> str:
    primary = theme_manager.get("primary_color")
    return f"""
        QPushButton {{
            background-color: #2e2e2e;
            color: white;
            border: 1px solid #666;
            border-radius: 8px;
            padding: 0px 16px;
        }}
        QPushButton:hover {{ border-color: {primary}; }}
        QPushButton:pressed {{ background-color: #1a1a1a; border-color: {primary}; }}
    """


def _filled_button_style(fill: str) -> str:
    return f"""
        QPushButton {{
            background-color: {fill};
            color: #111111;
            border: 1px solid {fill};
            border-radius: 8px;
            padding: 0px 16px;
        }}
        QPushButton:hover {{ border: 2px solid white; }}
        QPushButton:pressed {{ background-color: #2e2e2e; color: {fill}; }}
    """


class FlowDialog(QDialog):
    """Themed modal window over a dimmed screen, rebuilt for each stage of a task"""

    start_requested = pyqtSignal(str)
    primary_clicked = pyqtSignal()
    secondary_clicked = pyqtSignal()
    cancel_requested = pyqtSignal()

    def __init__(self, parent, title: str, subtitle: str = "", width: int = 560):
        super().__init__(parent.window() if parent is not None else None)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self._steps = []
        self._closable = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)

        primary = theme_manager.get("primary_color")
        self.card = QFrame()
        self.card.setObjectName("flow_card")
        self.card.setFixedWidth(width)
        self.card.setStyleSheet(f"""
            QFrame#flow_card {{
                background-color: {theme_manager.get("panel_bg")};
                border: 1px solid {rgba(primary, 0.45)};
                border-radius: 12px;
            }}
            QLabel {{ background: transparent; border: none; }}
        """)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(14)

        header = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setFont(px_font(15, bold=True, spacing=1.5))
        self.title_label.setStyleSheet(f"color: {primary};")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setFont(px_font(13))
        self.subtitle_label.setStyleSheet(f"color: {LABEL_GREY};")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.title_label)
        header.addWidget(self.subtitle_label, 1)
        card_layout.addLayout(header)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {DIVIDER}; border: none;")
        card_layout.addWidget(divider)

        self.body = QWidget()
        self.body.setStyleSheet("background: transparent;")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(14)
        card_layout.addWidget(self.body)

        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(12)
        card_layout.addLayout(self.buttons)

        row.addWidget(self.card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

    # ---------- Window ----------

    def showEvent(self, event):
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.geometry())
        super().showEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 158))
        painter.end()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and not self._closable:
            return
        super().keyPressEvent(event)

    def reject(self):
        if self._closable:
            super().reject()

    def set_subtitle(self, text: str):
        self.subtitle_label.setText(text)

    # ---------- Building blocks ----------

    def _clear(self, layout=None):
        layout = self.body_layout if layout is None else layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self._clear(child.layout())

    def _caption(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setFont(px_font(12, spacing=1.0))
        label.setStyleSheet(f"color: {LABEL_GREY};")
        return label

    def _set_buttons(self, secondary: str = None, primary: str = None, primary_fill: str = None):
        self._clear(self.buttons)
        self.buttons.addStretch(1)
        if secondary:
            button = QPushButton(secondary)
            button.setFixedHeight(44)
            button.setMinimumWidth(130)
            button.setFont(px_font(15, bold=True))
            button.setStyleSheet(_plain_button_style())
            button.clicked.connect(lambda: self.secondary_clicked.emit())
            self.buttons.addWidget(button)
        if primary:
            button = QPushButton(primary)
            button.setFixedHeight(44)
            button.setMinimumWidth(160)
            button.setFont(px_font(15, bold=True))
            button.setStyleSheet(_filled_button_style(primary_fill or theme_manager.get("primary_color")))
            button.clicked.connect(lambda: self.primary_clicked.emit())
            self.buttons.addWidget(button)

    def _add_steps(self, labels):
        self._steps = []
        holder = QVBoxLayout()
        holder.setSpacing(10)
        for label_text in labels:
            row = QHBoxLayout()
            row.setSpacing(12)
            icon = QLabel()
            icon.setFixedSize(24, 24)
            text = QLabel(label_text)
            text.setFont(px_font(16))
            detail = QLabel("")
            detail.setFont(px_font(14, family="Consolas"))
            detail.setStyleSheet("color: #bdbdbd;")
            row.addWidget(icon)
            row.addWidget(text, 1)
            row.addWidget(detail)
            holder.addLayout(row)
            self._steps.append((icon, text, detail))
            self._show_step(len(self._steps) - 1, STEP_PENDING)
        self.body_layout.addLayout(holder)

    def _show_step(self, index: int, state: str):
        icon, text, _ = self._steps[index]
        icon.setPixmap(_step_icon(state))
        icon.setProperty("state", state)
        if state == STEP_PENDING:
            color = "#6a6a6a"
        elif state == STEP_ERROR:
            color = "#ff9999"
        else:
            color = "white"
        text.setStyleSheet(f"color: {color};")

    # ---------- Stages ----------

    def show_choose(self, notes, branches=("main", "dev"), action: str = "UPDATE"):
        """Branch pill, what will happen, CANCEL / action"""
        self._closable = True
        self._clear()
        primary = theme_manager.get("primary_color")

        branch_col = QVBoxLayout()
        branch_col.setSpacing(6)
        branch_col.addWidget(self._caption("BRANCH"))
        pill = QFrame()
        pill.setObjectName("branch_pill")
        pill.setFixedHeight(48)
        pill.setStyleSheet(
            "QFrame#branch_pill { background-color: #242424; border: 1px solid #3e3e3e; border-radius: 24px; }")
        pill_layout = QHBoxLayout(pill)
        pill_layout.setContentsMargins(3, 3, 3, 3)
        pill_layout.setSpacing(3)
        self._branch_group = QButtonGroup(pill)
        self._branch_group.setExclusive(True)
        for index, branch in enumerate(branches):
            button = QPushButton(branch)
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.setFixedHeight(40)
            button.setFont(px_font(16, bold=True))
            button.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {TEXT_SOFT}; border: none; border-radius: 20px; }}
                QPushButton:checked {{ background-color: {primary}; color: #111111; }}
            """)
            self._branch_group.addButton(button)
            pill_layout.addWidget(button, 1)
        branch_col.addWidget(pill)
        self.body_layout.addLayout(branch_col)

        notes_col = QVBoxLayout()
        notes_col.setSpacing(8)
        notes_col.addWidget(self._caption("WHAT HAPPENS"))
        for note in notes:
            line = QLabel(f"✓   {note}")
            line.setFont(px_font(15))
            line.setStyleSheet(f"color: {TEXT_SOFT};")
            notes_col.addWidget(line)
        self.body_layout.addLayout(notes_col)

        self._set_buttons("CANCEL", action)
        self._disconnect_buttons()
        self.secondary_clicked.connect(self.reject)
        self.primary_clicked.connect(self._emit_start)

    def _emit_start(self):
        button = self._branch_group.checkedButton()
        if button is not None:
            self.start_requested.emit(button.text())

    def _disconnect_buttons(self):
        for signal in (self.primary_clicked, self.secondary_clicked):
            try:
                signal.disconnect()
            except TypeError:
                pass

    def show_progress(self, labels, cancellable: bool = False):
        """Step list, progress bar and status line"""
        self._closable = cancellable
        self._clear()
        self._disconnect_buttons()
        self._add_steps(labels)

        bar_col = QVBoxLayout()
        bar_col.setSpacing(8)
        track = QFrame()
        track.setObjectName("bar_track")
        track.setFixedHeight(8)
        track.setStyleSheet("QFrame#bar_track { background-color: #2a2a2a; border-radius: 4px; }")
        self._bar_fill = QFrame(track)
        self._bar_fill.setStyleSheet(
            f"background-color: {theme_manager.get('primary_color')}; border-radius: 4px;")
        self._bar_fill.setGeometry(0, 0, 0, 8)
        self._bar_track = track
        self._bar_fraction = 0.0
        bar_col.addWidget(track)
        self._status_label = QLabel("")
        self._status_label.setFont(px_font(13))
        self._status_label.setStyleSheet(f"color: {LABEL_GREY};")
        self._status_label.setWordWrap(True)
        bar_col.addWidget(self._status_label)
        self.body_layout.addLayout(bar_col)

        if cancellable:
            self._set_buttons("CANCEL")
            self.secondary_clicked.connect(lambda: self.cancel_requested.emit())
        else:
            self._set_buttons()

    def set_step(self, index: int, state: str, detail: str = None):
        if 0 <= index < len(self._steps):
            self._show_step(index, state)
            if detail is not None:
                self._steps[index][2].setText(detail)

    def advance_to(self, index: int, detail: str = None):
        """Mark earlier steps done and this one active"""
        for i in range(len(self._steps)):
            if i < index and self._steps[i][0].property("state") != STEP_DONE:
                self.set_step(i, STEP_DONE)
        current = self._steps[index][0].property("state") if 0 <= index < len(self._steps) else None
        if current != STEP_ACTIVE or detail is not None:
            self.set_step(index, STEP_ACTIVE, detail)

    def active_step(self) -> int:
        for i, (icon, _, _) in enumerate(self._steps):
            if icon.property("state") == STEP_ACTIVE:
                return i
        return -1

    def complete_steps(self):
        for i in range(len(self._steps)):
            self.set_step(i, STEP_DONE)
        self.set_progress(1.0)

    def set_progress(self, fraction: float):
        self._bar_fraction = max(0.0, min(1.0, fraction))
        self._resize_bar()

    def _resize_bar(self):
        if hasattr(self, "_bar_track"):
            width = int(self._bar_track.width() * self._bar_fraction)
            self._bar_fill.setGeometry(0, 0, width, 8)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_bar()

    def set_status(self, text: str):
        if hasattr(self, "_status_label"):
            self._status_label.setText(text)
            self._resize_bar()

    def show_result(self, success: bool, title: str, text: str = "", error: str = None,
                    secondary: str = None, primary: str = None, primary_fill: str = None,
                    keep_steps: bool = False, warning: bool = False):
        """Tick, cross or warning with a message; the step list can stay above it"""
        self._closable = True
        self._disconnect_buttons()
        if keep_steps:
            self._remove_progress_bar()
        else:
            self._clear()
            self._steps = []

        row = QHBoxLayout()
        row.setSpacing(16)
        icon = QLabel()
        icon.setPixmap(_warning_icon() if warning else _result_icon(success))
        icon.setFixedSize(56, 56)
        row.addWidget(icon)
        texts = QVBoxLayout()
        texts.setSpacing(6)
        title_label = QLabel(title)
        title_label.setFont(px_font(20, bold=True))
        title_label.setStyleSheet("color: white;")
        texts.addWidget(title_label)
        if text:
            text_label = QLabel(text)
            text_label.setFont(px_font(15))
            text_label.setStyleSheet(f"color: {TEXT_SOFT};")
            text_label.setWordWrap(True)
            texts.addWidget(text_label)
        row.addLayout(texts, 1)
        self.body_layout.addLayout(row)

        if error:
            box = QLabel(error)
            box.setWordWrap(True)
            box.setFont(px_font(13, family="Consolas"))
            box.setStyleSheet(
                f"color: #ff9999; background-color: {TILE_BG}; border: 1px solid #3a3a3a; "
                f"border-radius: 8px; padding: 10px 12px;")
            self.body_layout.addWidget(box)

        self._set_buttons(secondary, primary, primary_fill)

    def show_confirm(self, title: str, text: str, secondary: str = "CANCEL",
                     primary: str = "OK", primary_fill: str = None, warning: bool = False):
        """Question with a power (or warning) icon; primary accepts, secondary rejects"""
        self._closable = True
        self._disconnect_buttons()
        self._clear()
        self._steps = []

        row = QHBoxLayout()
        row.setSpacing(18)
        icon = QLabel()
        icon.setPixmap(_warning_icon() if warning else _power_icon())
        icon.setFixedSize(56, 56)
        row.addWidget(icon)
        texts = QVBoxLayout()
        texts.setSpacing(6)
        title_label = QLabel(title)
        title_label.setFont(px_font(20, bold=True))
        title_label.setStyleSheet("color: white;")
        texts.addWidget(title_label)
        text_label = QLabel(text)
        text_label.setFont(px_font(15))
        text_label.setStyleSheet(f"color: {TEXT_SOFT};")
        text_label.setWordWrap(True)
        texts.addWidget(text_label)
        row.addLayout(texts, 1)
        self.body_layout.addLayout(row)

        self._set_buttons(secondary, primary, primary_fill)
        self.secondary_clicked.connect(self.reject)
        self.primary_clicked.connect(self.accept)

    def _remove_progress_bar(self):
        """Drop the bar and status line, keeping the step list"""
        count = self.body_layout.count()
        if count > 1:
            item = self.body_layout.takeAt(count - 1)
            if item.layout():
                self._clear(item.layout())
        for name in ("_bar_track", "_bar_fill", "_status_label"):
            if hasattr(self, name):
                delattr(self, name)

    def show_report(self, summary: str, ok: bool, groups, secondary: str = None, primary: str = None):
        """Summary banner and grouped result rows: groups = [(name, [(status, text)])]"""
        self._closable = True
        self._disconnect_buttons()
        self._clear()
        self._steps = []

        color = theme_manager.get("green") if ok else WARN_ORANGE
        banner = QLabel(summary)
        banner.setFont(px_font(14))
        banner.setWordWrap(True)
        banner.setStyleSheet(
            f"color: {color}; background-color: {rgba(color, 0.12)}; border: 1px solid {color}; "
            f"border-radius: 8px; padding: 10px 12px;")
        self.body_layout.addWidget(banner)

        dots = {
            "success": theme_manager.get("green"),
            "warning": WARN_ORANGE,
            "info": INFO_BLUE,
            "error": theme_manager.get("red"),
        }
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 6, 0)
        content_layout.setSpacing(12)
        for name, rows in groups:
            group = QVBoxLayout()
            group.setSpacing(6)
            group.addWidget(self._caption(name))
            for status, text in rows:
                row = QFrame()
                row.setObjectName("report_row")
                row.setStyleSheet(
                    f"QFrame#report_row {{ background-color: {ROW_BG}; border-radius: 8px; }}"
                    "QLabel { background: transparent; border: none; }")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(12, 6, 12, 6)
                row_layout.setSpacing(10)
                dot = QLabel()
                dot.setFixedSize(10, 10)
                dot.setStyleSheet(f"background-color: {dots.get(status, dots['error'])}; border-radius: 5px;")
                label = QLabel(text)
                label.setWordWrap(True)
                label.setFont(px_font(14))
                label.setStyleSheet(f"color: {'#ff9999' if status == 'error' else TEXT_SOFT};")
                label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                row_layout.addWidget(dot)
                row_layout.addWidget(label, 1)
                group.addWidget(row)
            content_layout.addLayout(group)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        scroll.setMaximumHeight(380)
        scroll.setMinimumHeight(min(380, content.sizeHint().height()))
        primary_color = theme_manager.get("primary_color")
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: #262626; width: 6px; border-radius: 3px; }}
            QScrollBar::handle:vertical {{ background: {primary_color}; border-radius: 3px; min-height: 30px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)
        self.body_layout.addWidget(scroll)
        self._set_buttons(secondary, primary)


def show_message(parent, header: str, title: str, text: str = "", kind: str = "success",
                 error: str = None, button: str = "OK"):
    """Themed pop-up with a tick, cross or warning and a single button.

    kind is "success", "error" or "warning". Blocks until dismissed.
    """
    dialog = FlowDialog(parent, header)
    dialog.show_result(kind == "success", title, text, error=error, primary=button,
                       warning=(kind == "warning"))
    dialog.primary_clicked.connect(dialog.accept)
    dialog.exec()


def ask_confirm(parent, header: str, title: str, text: str, confirm: str = "OK",
                danger: bool = False) -> bool:
    """Themed yes/no question; returns True when confirmed. Danger makes the button red."""
    dialog = FlowDialog(parent, header)
    dialog.show_confirm(title, text, secondary="CANCEL", primary=confirm,
                        primary_fill=theme_manager.get("red") if danger else None, warning=True)
    return dialog.exec() == QDialog.DialogCode.Accepted
