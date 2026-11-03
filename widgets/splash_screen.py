#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DroidDeck startup and shutdown splash screens.
The theme's droid stands in a spotlight that brightens while loading and
fades while shutting down, beside a ticking list of steps.
"""

import os
from PyQt6.QtWidgets import QApplication, QSplashScreen
from PyQt6.QtCore import Qt, QTimer, QRect, QRectF, QPointF
from PyQt6.QtGui import (
    QPixmap, QPainter, QColor, QFont, QPen, QBrush, QRadialGradient, QPainterPath
)

from core.theme_manager import theme_manager
from core.version import GUI_VERSION, get_build_label

# Import pygame for audio
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

# Splash is drawn at its native size, pixel for pixel, so text stays sharp
SPLASH_WIDTH = 560
SPLASH_HEIGHT = 320
STAGE_WIDTH = 220
DROID_SIZE = 160

SUBTITLES = {
    "Wall-e": "Waste Allocation Load Lifter · Earth-Class",
    "Star Wars": "Astromech Droid Control",
}

LABEL_GREY = "#9e9e9e"
TEXT_SOFT = "#bdbdbd"
FOOTER_GREY = "#7a7a7a"


def get_audio_path(filename: str) -> str:
    """Get audio file path from current theme directory"""
    try:
        theme_name = theme_manager.get_theme_name()
        audio_path = os.path.join("resources", "theme", theme_name, "audio", filename)

        if os.path.exists(audio_path):
            return audio_path
        else:
            audio_path = os.path.join("resources", "theme", "Wall-e", "audio", filename)
            if os.path.exists(audio_path):
                return audio_path
    except Exception as e:
        print(f"Error getting audio path: {e}")

    return None


def _px_font(pixel_size: int, bold: bool = False, spacing: float = 0.0, family: str = "Arial") -> QFont:
    font = QFont(family)
    if family != "Arial":
        font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPixelSize(pixel_size)
    font.setBold(bold)
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return font


class _StageSplash(QSplashScreen):
    """Shared drawing for the startup and shutdown splash screens"""

    def __init__(self, steps):
        pixmap = QPixmap(SPLASH_WIDTH, SPLASH_HEIGHT)
        pixmap.fill(QColor("#0b0b0b"))
        super().__init__(pixmap)

        self.setWindowFlags(Qt.WindowType.SplashScreen |
                            Qt.WindowType.WindowStaysOnTopHint)

        self.steps = list(steps)
        self.current_step = 0
        self.progress = 0
        self.all_done = False
        self.status_text = ""
        self.status_color = LABEL_GREY

        droid = QPixmap(theme_manager.get_image_path("main"))
        if not droid.isNull():
            # Scaled once for the screen's pixel density so it is drawn 1:1
            ratio = QApplication.primaryScreen().devicePixelRatio()
            size = int(DROID_SIZE * ratio)
            droid = droid.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            droid.setDevicePixelRatio(ratio)
        self._droid = droid
        self._build_label = f"GUI v{GUI_VERSION}"
        self._commit_label = get_build_label()
        self._audio_started = False

        self._center_on_screen()

    def _center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    # Overridden by each splash
    def _stage_levels(self):
        """(glow strength, droid opacity, floor line opacity)"""
        return 0.2, 1.0, 0.9

    def _start_audio(self):
        pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Audio starts on the first paint so the screen is visible first
        if not self._audio_started:
            self._audio_started = True
            QTimer.singleShot(50, self._start_audio)

        painter.fillRect(self.rect(), QColor("#0b0b0b"))

        primary = QColor(theme_manager.get("primary_color"))
        panel = QColor(theme_manager.get("panel_bg"))

        # Card
        card = QRectF(0.5, 0.5, SPLASH_WIDTH - 1, SPLASH_HEIGHT - 1)
        border = QColor(primary)
        border.setAlphaF(0.45)
        painter.setPen(QPen(border, 1))
        painter.setBrush(panel)
        painter.drawRoundedRect(card, 12, 12)

        self._draw_stage(painter, primary)
        self._draw_text(painter, primary)
        painter.end()

    def _draw_stage(self, painter, primary):
        glow_strength, droid_opacity, line_opacity = self._stage_levels()

        painter.save()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(1, 1, STAGE_WIDTH, SPLASH_HEIGHT - 2), 11, 11)
        painter.setClipPath(clip)

        glow = QRadialGradient(QPointF(STAGE_WIDTH / 2, SPLASH_HEIGHT * 0.58), 170)
        inner = QColor(primary)
        inner.setAlphaF(glow_strength)
        mid = QColor(primary)
        mid.setAlphaF(glow_strength / 3)
        outer = QColor(primary)
        outer.setAlphaF(0.0)
        glow.setColorAt(0.0, inner)
        glow.setColorAt(0.4, mid)
        glow.setColorAt(0.7, outer)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawRect(QRectF(0, 0, STAGE_WIDTH, SPLASH_HEIGHT))
        painter.restore()

        # Floor shadow
        shadow_rect = QRectF(25, 246, 170, 20)
        shadow = QRadialGradient(shadow_rect.center(), 85)
        shadow.setColorAt(0.0, QColor(0, 0, 0, 190))
        shadow.setColorAt(0.7, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(shadow_rect)

        # Droid, bottom-aligned on the floor at its native pixel size
        if not self._droid.isNull():
            size = self._droid.deviceIndependentSize()
            x = int((STAGE_WIDTH - size.width()) // 2)
            y = int(240 - size.height())
            painter.setOpacity(droid_opacity)
            painter.drawPixmap(x, y, self._droid)
            painter.setOpacity(1.0)

        # Floor line
        line = QColor(primary)
        line.setAlphaF(line_opacity)
        painter.setBrush(line)
        painter.drawRect(30, 262, 160, 2)

    def _draw_text(self, painter, primary):
        left = STAGE_WIDTH + 6
        right = SPLASH_WIDTH - 22
        width = right - left
        left_align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        right_align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

        painter.setPen(primary)
        painter.setFont(_px_font(28, bold=True, spacing=3))
        painter.drawText(QRect(left, 18, width, 34), left_align, "DROIDDECK")

        subtitle = SUBTITLES.get(theme_manager.get_theme_name(), "")
        painter.setPen(QColor(TEXT_SOFT))
        painter.setFont(_px_font(12))
        painter.drawText(QRect(left, 54, width, 16), left_align, subtitle)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#2e2e2e"))
        painter.drawRect(left, 80, width, 1)

        # Step list
        y = 92
        painter.setFont(_px_font(13))
        for index, label in enumerate(self.steps):
            state = self._step_state(index)
            self._draw_step_icon(painter, QRectF(left, y + 2, 16, 16), state, primary)
            painter.setPen(QColor("#6a6a6a") if state == "pending" else QColor("white"))
            painter.drawText(QRect(left + 24, y, width - 24, 20), left_align, label.rstrip(". "))
            y += 24

        # Status, percentage and bar
        bar_top = 274
        painter.setFont(_px_font(12))
        painter.setPen(QColor(self.status_color))
        painter.drawText(QRect(left, bar_top - 20, width - 50, 16), left_align, self.status_text)
        painter.setPen(QColor(TEXT_SOFT))
        painter.setFont(_px_font(12, family="Consolas"))
        painter.drawText(QRect(right - 50, bar_top - 20, 50, 16), right_align, f"{int(self.progress)}%")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#2a2a2a"))
        painter.drawRoundedRect(QRectF(left, bar_top, width, 5), 2.5, 2.5)
        fill = round(width * max(0, min(100, self.progress)) / 100.0)
        if fill > 0:
            painter.setBrush(primary)
            painter.drawRoundedRect(QRectF(left, bar_top, fill, 5), 2.5, 2.5)

        painter.setPen(QColor(FOOTER_GREY))
        painter.setFont(_px_font(11, family="Consolas"))
        painter.drawText(QRect(left, bar_top + 13, width, 14), left_align, self._build_label)
        painter.drawText(QRect(left, bar_top + 13, width, 14), right_align, self._commit_label)

    def _step_state(self, index: int) -> str:
        if self.all_done or index < self.current_step:
            return "done"
        if index == self.current_step:
            return "active"
        return "pending"

    def _draw_step_icon(self, painter, rect, state, primary):
        painter.save()
        painter.translate(rect.topLeft())
        painter.scale(rect.width() / 24.0, rect.height() / 24.0)
        if state == "done":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme_manager.get("green")))
            painter.drawEllipse(QRectF(1, 1, 22, 22))
            pen = QPen(QColor("#111111"), 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.moveTo(7, 12.5)
            path.lineTo(10.5, 16)
            path.lineTo(17, 8.5)
            painter.drawPath(path)
        elif state == "active":
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
        painter.restore()

    def _play(self, filename: str):
        if not PYGAME_AVAILABLE:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            audio_path = get_audio_path(filename)
            if audio_path and os.path.exists(audio_path):
                pygame.mixer.music.load(audio_path)
                pygame.mixer.music.play()
        except Exception as e:
            print(f"Failed to play {filename}: {e}")


class DroidDeckSplashScreen(_StageSplash):
    """Startup splash: the spotlight brightens as DroidDeck loads"""

    def __init__(self):
        # Load the saved theme now so the splash is drawn in it from the first frame
        try:
            theme_manager.initialize()
        except Exception as e:
            print(f"Could not load saved theme for splash: {e}")

        self.messages = [
            "Initializing DroidDeck...",
            "Loading configurations...",
            "Establishing connections...",
            "Loading interface modules...",
            "Configuring navigation...",
            "Finalizing DroidDeck..."
        ]
        super().__init__(self.messages)
        self.current_message = 0
        self.status_text = self.messages[0]
        self._on_complete = None

        QTimer.singleShot(100, self._bring_to_front)

    def _stage_levels(self):
        if self.all_done:
            return 0.30, 1.0, 0.9
        return 0.12 + 0.16 * self.progress / 100.0, 1.0, 0.9

    def _start_audio(self):
        self._play("startup.mp3")

    def _bring_to_front(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def update_progress(self, step, message):
        """Update progress based on actual initialization steps"""
        self.current_step = step
        self.progress = int((step / len(self.messages)) * 100)
        self.current_message = min(step, len(self.messages) - 1)

        if message and step < len(self.messages):
            self.messages[step] = message
            self.steps[step] = message
        self.status_text = self.messages[self.current_message]
        self.status_color = LABEL_GREY

        self.update()
        QApplication.processEvents()

    def set_message(self, message):
        """Show a message in the status line without changing step"""
        self.status_text = message
        self.status_color = theme_manager.get("red") if "failed" in message.lower() else LABEL_GREY
        self.update()
        QApplication.processEvents()

    def finish_loading(self, on_complete=None):
        """Mark loading as complete and wait for startup audio to finish"""
        self.progress = 100
        self.all_done = True
        self.current_message = len(self.messages) - 1
        self.status_text = "Ready"
        self.status_color = theme_manager.get("green")
        self._on_complete = on_complete
        self.update()
        QApplication.processEvents()

        # The splash closes when the startup tune ends; a short fixed delay
        # is used when audio is not available
        QTimer.singleShot(300, self._start_audio_wait)

    def _start_audio_wait(self):
        """Begin polling pygame for audio completion"""
        if PYGAME_AVAILABLE:
            try:
                if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                    self._audio_poll_timer = QTimer()
                    self._audio_poll_timer.timeout.connect(self._check_audio_complete)
                    self._audio_poll_timer.start(200)
                    return
            except Exception:
                pass
        QTimer.singleShot(1000, self._finish)

    def _check_audio_complete(self):
        """Close splash when the startup audio track finishes"""
        try:
            if not pygame.mixer.music.get_busy():
                self._audio_poll_timer.stop()
                self._finish()
        except Exception:
            self._audio_poll_timer.stop()
            self._finish()

    def _finish(self):
        """Trigger the completion callback then close the splash"""
        if self._on_complete:
            self._on_complete()
        self.close()

    def closeEvent(self, event):
        """Clean up audio and timers when closing"""
        if hasattr(self, '_audio_poll_timer') and self._audio_poll_timer is not None:
            self._audio_poll_timer.stop()
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        super().closeEvent(event)


class DroidDeckShutdownSplash(_StageSplash):
    """Shutdown splash: the spotlight fades as DroidDeck powers down"""

    def __init__(self):
        self.shutdown_steps = [
            "Saving configurations",
            "Closing connections",
            "Stopping processes",
            "Cleaning resources",
            "Shutdown complete"
        ]
        super().__init__(self.shutdown_steps)
        self.status_text = "Shutting down..."

    def _stage_levels(self):
        fraction = self.progress / 100.0
        return 0.22 - 0.18 * fraction, 1.0 - 0.45 * fraction, 0.9 - 0.6 * fraction

    def _start_audio(self):
        self._play("shutdown.mp3")

    def update_shutdown_progress(self, step):
        """Update shutdown progress"""
        self.all_done = step >= len(self.shutdown_steps)
        self.current_step = min(step, len(self.shutdown_steps) - 1)
        self.progress = int((step / len(self.shutdown_steps)) * 100)
        if self.all_done:
            self.status_text = "Goodbye"
        else:
            self.status_text = f"{self.shutdown_steps[self.current_step]}..."
        self.update()
        QApplication.processEvents()

    def closeEvent(self, event):
        """Clean up audio when closing"""
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        super().closeEvent(event)


def show_shutdown_splash():
    """Show shutdown splash screen"""
    splash = DroidDeckShutdownSplash()
    splash.show()
    splash.raise_()
    splash.activateWindow()
    return splash