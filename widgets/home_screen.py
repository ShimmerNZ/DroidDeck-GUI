#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - Home Screen
Scene selection dashboard with WebSocket-based controller navigation.
"""
import os
import time
import pygame
from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QProgressBar,
    QWidget, QFrame, QListWidget, QListWidgetItem, QSizePolicy, QGridLayout
)
from PyQt6.QtGui import QPixmap, QFont, QColor, QPainter, QPen, QBrush, QRadialGradient, QPainterPath
from PyQt6.QtCore import Qt, QTimer, QSize, QPointF, QRectF, pyqtSignal
from widgets.base_screen import BaseScreen
from core.config_manager import config_manager
from core.theme_manager import theme_manager
from core.utils import error_boundary
from core.logger import get_logger

# Layout - matches the Health screen card positions
STAGE_WIDTH = 376
COLUMN_GAP = 16
CARD_WIDTH = 669
CONTENT_HEIGHT = 490
STAGE_IMAGE_SIZE = 318
CAPTION_HEIGHT = 66
SCENE_ROW_HEIGHT = 44
CATEGORIES_PER_ROW = 5

# Fixed colours shared by every theme
LABEL_GREY = "#9e9e9e"
TEXT_SOFT = "#d6d6d6"
ROW_BG = "#1f1f1f"
PILL_BG = "#242424"
PILL_BORDER = "#3e3e3e"
ICON_GREY = "#8a8a8a"


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


def _make_icon(kind: str, color: str) -> QPixmap:
    """Small line icon for a scene type: 'audio' (note) or 'anim' (film)"""
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.6)
    painter.setPen(pen)
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
    else:
        painter.drawRoundedRect(QRectF(1, 3, 14, 10), 1.5, 1.5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        triangle = QPainterPath()
        triangle.moveTo(6.5, 6)
        triangle.lineTo(10.5, 8)
        triangle.lineTo(6.5, 10)
        triangle.closeSubpath()
        painter.drawPath(triangle)
    painter.end()
    return pixmap


def _draw_floor_shadow(painter: QPainter, center: QPointF, half_width: float, half_height: float):
    """Oval shadow whose gradient is squashed with the oval, so it fades vertically too"""
    painter.save()
    painter.translate(center)
    painter.scale(1.0, half_height / half_width)
    shadow = QRadialGradient(QPointF(0, 0), half_width)
    shadow.setColorAt(0.0, QColor(0, 0, 0, 190))
    shadow.setColorAt(0.6, QColor(0, 0, 0, 90))
    shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(shadow))
    painter.drawEllipse(QPointF(0, 0), half_width, half_width)
    painter.restore()


class StageWidget(QWidget):
    """WALL-E standing in a theme-coloured spotlight with a floor shadow"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._glow_color = QColor("#e1a014")
        self._glow_strength = 0.16
        self.setFixedSize(STAGE_WIDTH, STAGE_IMAGE_SIZE + 8)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_image(self, pixmap):
        self._pixmap = pixmap
        self.update()

    def set_glow(self, color: str, strength: float):
        self._glow_color = QColor(color)
        self._glow_strength = strength
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()

        # Spotlight behind WALL-E
        glow = QRadialGradient(QPointF(w / 2, h * 0.55), w * 0.62)
        inner = QColor(self._glow_color)
        inner.setAlphaF(self._glow_strength)
        mid = QColor(self._glow_color)
        mid.setAlphaF(0.05)
        outer = QColor(self._glow_color)
        outer.setAlphaF(0.0)
        glow.setColorAt(0.0, inner)
        glow.setColorAt(0.55, mid)
        glow.setColorAt(0.75, outer)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawRect(0, 0, w, h)

        # Floor shadow under the tracks: a soft oval fading out on every side
        _draw_floor_shadow(painter, QPointF(w / 2, h - 9), 120, 8)

        # WALL-E, bottom-aligned on the floor
        if self._pixmap is not None and not self._pixmap.isNull():
            x = (w - self._pixmap.width()) // 2
            y = h - 8 - self._pixmap.height()
            painter.drawPixmap(x, y, self._pixmap)
        painter.end()


class SceneRow(QFrame):
    """One scene in the list: marker, name, playing badge, type icons, duration"""

    def __init__(self, name: str, audio: bool, anim: bool, duration: str):
        super().__init__()
        self.setObjectName("scene_row")
        self.setFixedHeight(SCENE_ROW_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(12)

        self.marker = QFrame()
        self.marker.setFixedSize(4, 20)

        self.name_label = QLabel(name)
        self.name_label.setFont(px_font(17))
        self.name_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self.badge = QLabel("PLAYING")
        self.badge.setFont(px_font(11, bold=True, spacing=1.0))
        self.badge.hide()

        icons = QHBoxLayout()
        icons.setSpacing(6)
        icons_widget = QWidget()
        icons_widget.setFixedWidth(40)
        icons_widget.setStyleSheet("background: transparent;")
        icons_widget.setLayout(icons)
        icons.setContentsMargins(0, 0, 0, 0)
        icons.addStretch(1)
        if audio:
            note = QLabel()
            note.setPixmap(_make_icon("audio", ICON_GREY))
            icons.addWidget(note)
        if anim:
            film = QLabel()
            film.setPixmap(_make_icon("anim", ICON_GREY))
            icons.addWidget(film)

        self.duration_label = QLabel(duration)
        self.duration_label.setFont(px_font(14, family="Consolas"))
        self.duration_label.setFixedWidth(44)
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(self.marker)
        layout.addWidget(self.name_label, 1)
        layout.addWidget(self.badge)
        layout.addWidget(icons_widget)
        layout.addWidget(self.duration_label)

        self.set_state(selected=False, playing=False)

    def set_state(self, selected: bool, playing: bool):
        """Style the row for its selected / playing state"""
        primary = theme_manager.get("primary_color")
        green = theme_manager.get("green")

        if selected:
            background, border = rgba(primary, 0.14), f"1px solid {primary}"
        elif playing:
            background, border = rgba(green, 0.12), "1px solid transparent"
        else:
            background, border = ROW_BG, "1px solid transparent"
        marker = green if playing else (primary if selected else "transparent")
        name_color = "white" if (selected or playing) else TEXT_SOFT

        self.setStyleSheet(f"""
            QFrame#scene_row {{
                background-color: {background};
                border: {border};
                border-radius: 10px;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)
        self.marker.setStyleSheet(f"background-color: {marker}; border: none; border-radius: 2px;")
        self.name_label.setStyleSheet(f"color: {name_color}; background: transparent; border: none;")
        self.duration_label.setStyleSheet("color: #bdbdbd; background: transparent; border: none;")
        self.badge.setStyleSheet(
            f"color: #111111; background-color: {green}; border: none; border-radius: 4px; padding: 3px 8px;"
        )
        self.badge.setVisible(playing)


class SceneList(QListWidget):
    """Scene list whose rows always span the full list width"""

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = self.viewport().width()
        for i in range(self.count()):
            self.item(i).setSizeHint(QSize(width, SCENE_ROW_HEIGHT))


class HomeScreen(BaseScreen):
    """Scene selection dashboard with WebSocket-based controller navigation."""
    
    # Signal emitted when a scene should be triggered
    scene_triggered = pyqtSignal(str, int)  # category, scene_index

    # Slightly longer than the backend's 0.5s re-trigger guard, so a press
    # the backend would ignore is also ignored here
    SCENE_RETRIGGER_GUARD_SECONDS = 0.6

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Navigation state tracking
        self.current_scene_index = 0
        self.auto_advance_enabled = True
        self.is_playing_scene = False
        self.last_triggered_scene = None
        self.navigation_locked = False
        self.last_navigation_time = 0
        self.navigation_cooldown = 0.1
        self._last_scene_trigger_time = 0.0

        # Scene messages stay active regardless of visibility: scene state
        # (playing/locked) must track reality even while the operator is on
        # another screen. D-pad navigation only applies while Home is shown.
        self.subscribe("scene_completed", self._on_scene_completed)
        self.subscribe("scene_started", self._on_scene_started)
        self.subscribe("scene_error", self._on_scene_error)
        self.subscribe_while_visible("navigation", self._on_navigation)
        
        # Remove focus policy - no local input handling
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        # Register for theme change notifications
        theme_manager.register_callback(self._on_theme_changed)

        # Initialize logger
        self.logger = get_logger("home_screen")

        # Initialize pygame mixer for sound effects
        self._init_audio()


    def _on_scene_completed(self, msg: dict):
        """Reset playing state when the current scene completes"""
        try:
            # A scene cut off by a newer selection is not the end of playback:
            # the newer scene is still running, so leave state and selection alone
            if msg.get("interrupted") or (
                    self.last_triggered_scene and
                    msg.get("scene_name") != self.last_triggered_scene):
                return

            # Unlock navigation when the current scene completes. The selection
            # already advanced when the scene was triggered
            self._unlock_scene_state()
        except Exception as e:
            self.logger.error(f"Error handling scene_completed: {e}")
            self._unlock_scene_state()

    def _on_scene_started(self, msg: dict):
        """Track the scene that just started; navigation stays locked"""
        try:
            self.last_triggered_scene = msg.get("scene_name", "")
        except Exception as e:
            self.logger.error(f"Error handling scene_started: {e}")

    def _on_scene_error(self, msg: dict):
        """Unlock navigation when a scene fails"""
        self._unlock_scene_state()

    def _on_navigation(self, msg: dict):
        """Handle navigation commands from dpad/controller via the backend"""
        try:
            action = msg.get("action")
            if action == "left":
                self._navigate_categories(-1)
            elif action == "right":
                self._navigate_categories(1)
            elif action == "up":
                self._navigate_scenes(-1)
            elif action == "down":
                self._navigate_scenes(1)
            elif action == "select":
                self._trigger_selected_scene()
            elif action == "exit":
                self.logger.debug("Exit action received")

            self.logger.debug(f"Navigation action received: {action}")
        except Exception as e:
            self.logger.error(f"Error handling navigation: {e}")
            self._unlock_scene_state()

    def _navigate_scenes(self, direction):
        """Navigate scene list up/down"""
        if self.queue_list.count() == 0:
            return
    
        current = self.queue_list.currentRow()
        if current == -1:  # No selection
            current = 0
            
        # Calculate new index with bounds checking (no looping for scenes)
        new_index = current + direction
        new_index = max(0, min(self.queue_list.count() - 1, new_index))
        
        # Only play sound if we actually moved
        if new_index != current:
            self._play_sound_effect("move.mp3")
        
        # Update selection
        self.queue_list.setCurrentRow(new_index)
        self.current_scene_index = new_index
        
    def _navigate_categories(self, direction):
        """Navigate categories left/right with simple time-based debouncing"""
        if not hasattr(self, 'category_buttons') or not self.category_buttons:
            return

        import time
        current_time = time.time()
        
        # Simple time-based debouncing (matching your keyPressEvent approach)
        if current_time - self.last_navigation_time < self.navigation_cooldown:
            return
            
        self.last_navigation_time = current_time

        current = self.selected_category_idx
        total = len(self.category_buttons)
        
        # Calculate new index with looping
        new_index = (current + direction) % total
                
        # Play move sound effect when navigating categories
        self._play_sound_effect("move.mp3")

        # Update selection
        self._on_category_selected(new_index)

    def _trigger_selected_scene(self):
        """Trigger the currently selected scene with improved state management"""
        if not hasattr(self, "categories") or not self.categories:
            return
            
        # A scene can be selected while another plays: the backend ends the
        # current scene and starts this one. The backend ignores a press
        # within 0.5s of a scene starting, so presses inside that window are
        # dropped here too - otherwise the selection would move past a clip
        # that never played
        now = time.time()
        if now - self._last_scene_trigger_time < self.SCENE_RETRIGGER_GUARD_SECONDS:
            self.logger.debug("Scene select ignored - too soon after the last one")
            return
        self._play_sound_effect("select.mp3")

        cat = self.categories[self.selected_category_idx]
        scenes = self.category_to_scenes.get(cat, [])

        current_row = self.queue_list.currentRow()
        if 0 <= current_row < len(scenes):
            scene = scenes[current_row]
            scene_name = scene.get("label", "Unknown")

            # Send WebSocket command to backend
            success = self.send_websocket_message("scene", emotion=scene_name)

            if success:
                # Emit signal and update UI
                self.scene_triggered.emit(cat, current_row)
                self._show_playing(scene_name, scene.get("duration", 3.0))

                self.is_playing_scene = True
                self.last_triggered_scene = scene_name
                self._last_scene_trigger_time = now

                # Move the selection on straight away so repeated presses
                # play clips in quick succession
                if self.auto_advance_enabled:
                    self._advance_to_next_scene()

                # Fallback reset in case the completion message never
                # arrives; ignored if a newer scene has been selected since
                self._scene_trigger_token = getattr(self, "_scene_trigger_token", 0) + 1
                token = self._scene_trigger_token
                scene_duration = scene.get("duration", 3.0)
                fallback_timeout = int((scene_duration + 2) * 1000)  # Convert to ms
                QTimer.singleShot(fallback_timeout,
                                  lambda: self._fallback_unlock_scene_state(token))

    def _fallback_unlock_scene_state(self, token: int):
        """Reset scene state if no newer scene has been selected since"""
        if token == getattr(self, "_scene_trigger_token", 0):
            self._unlock_scene_state()

    def _unlock_scene_state(self):
        """Unlock scene state after playback"""
        if hasattr(self, 'is_playing_scene'):
            self.is_playing_scene = False
        self.navigation_locked = False
        self._show_ready()

    def keyPressEvent(self, event):
        """Handle keyboard/D-pad input with improved debouncing"""
        key = event.key()
        
        # Check navigation lock first
        if self.navigation_locked:
            event.accept()  # Accept but don't process
            return
        
        # Left/Right: Navigate categories with looping
        if key == Qt.Key.Key_Left:
            self._navigate_categories(-1)
            event.accept()
        elif key == Qt.Key.Key_Right:
            self._navigate_categories(1)
            event.accept()
        
        # Up/Down: Navigate scene list
        elif key == Qt.Key.Key_Up:
            self._navigate_scenes(-1)
            event.accept()
        elif key == Qt.Key.Key_Down:
            self._navigate_scenes(1)
            event.accept()
        
        # Enter/Space: Trigger selected scene
        elif key in [Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space]:
            self._trigger_selected_scene()
            event.accept()
        else:
            # Call parent implementation for unhandled keys
            super().keyPressEvent(event)


    def _advance_to_next_scene(self):
        """Advance to next scene based on current mode (Sequential/Random)"""
        try:
            if not hasattr(self, "categories") or not self.categories:
                return
                
            cat = self.categories[self.selected_category_idx]
            scenes = self.category_to_scenes.get(cat, [])
            
            if len(scenes) <= 1:
                return  # Don't auto-advance if only one scene
                
            current_row = self.queue_list.currentRow()
            if current_row < 0:
                current_row = 0
                
            # Sequential vs Random logic
            if self.selected_mode_idx == 0:  # Sequential mode
                next_index = (current_row + 1) % len(scenes)
            else:  # Random mode
                import random
                available_indices = list(range(len(scenes)))
                if len(scenes) > 1 and current_row in available_indices:
                    available_indices.remove(current_row)  # Avoid immediate repeat
                next_index = random.choice(available_indices)
            
            # Update UI selection ONLY - don't auto-trigger
            self.queue_list.setCurrentRow(next_index)
            self.current_scene_index = next_index
            
            self.logger.info(f"Auto-advancing from scene {current_row} to {next_index} (selected, not triggered)")
            
        except Exception as e:
            self.logger.error(f"Error advancing to next scene: {e}")

    def showEvent(self, event):
        """Set initial state when screen is shown"""
        super().showEvent(event)
        # Reset scene selection to first item
        if self.queue_list.count() > 0:
            self.queue_list.setCurrentRow(0)
            self.current_scene_index = 0

    def _setup_screen(self):
        """WALL-E stage on the left, scenes card on the right"""
        self._playing_scene_name = None
        self._playing_started = 0.0
        self._playing_duration = 0.0
        self._scene_rows = []

        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(100)
        self._progress_timer.timeout.connect(self._update_progress)

        root = QHBoxLayout()
        root.setContentsMargins(101, 40, 12, 6)
        root.setSpacing(COLUMN_GAP)

        root.addWidget(self._create_stage(), 0, Qt.AlignmentFlag.AlignTop)
        root.addWidget(self._create_scene_card(), 0, Qt.AlignmentFlag.AlignTop)
        root.addStretch(1)
        self.setLayout(root)

        self._apply_styles()
        self._show_ready()

    # ---------- Stage ----------

    def _create_stage(self) -> QWidget:
        """Playback caption, WALL-E in his spotlight, stage line, then the playback controls"""
        stage = QWidget()
        stage.setFixedSize(STAGE_WIDTH, CONTENT_HEIGHT)
        stage.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(stage)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Caption: READY, or NOW PLAYING with the scene name and progress
        caption = QWidget()
        caption.setFixedSize(340, CAPTION_HEIGHT)
        caption_layout = QVBoxLayout(caption)
        caption_layout.setContentsMargins(0, 0, 0, 0)
        caption_layout.setSpacing(4)

        self.status_label = QLabel("READY")
        self.status_label.setFont(px_font(12, spacing=2.0))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.playing_name_label = QLabel("")
        self.playing_name_label.setFont(px_font(26, bold=True))
        self.playing_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.playing_progress = QProgressBar()
        self.playing_progress.setRange(0, 1000)
        self.playing_progress.setTextVisible(False)
        self.playing_progress.setFixedSize(220, 4)

        caption_layout.addWidget(self.status_label)
        caption_layout.addWidget(self.playing_name_label)
        caption_layout.addSpacing(6)
        caption_layout.addWidget(self.playing_progress, 0, Qt.AlignmentFlag.AlignHCenter)
        caption_layout.addStretch(1)
        layout.addWidget(caption, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addSpacing(12)
        self.stage_widget = StageWidget()
        layout.addWidget(self.stage_widget, 0, Qt.AlignmentFlag.AlignHCenter)
        self._update_main_image()

        layout.addSpacing(6)
        self.stage_line = QFrame()
        self.stage_line.setFixedSize(340, 1)
        layout.addWidget(self.stage_line, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addSpacing(17)
        layout.addWidget(self._create_mode_selector(), 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        return stage

    def _update_main_image(self):
        """Update the main character image based on current theme"""
        image_path = theme_manager.get_image_path("main")
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path).scaled(
                STAGE_IMAGE_SIZE, STAGE_IMAGE_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.stage_widget.set_image(pixmap)

    def _create_mode_selector(self) -> QWidget:
        """Sequential / Random switch and the Idle toggle, as pills"""
        row_widget = QWidget()
        row_widget.setFixedWidth(340)
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.mode_segment = QFrame()
        self.mode_segment.setObjectName("mode_segment")
        self.mode_segment.setFixedHeight(44)
        segment_layout = QHBoxLayout(self.mode_segment)
        segment_layout.setContentsMargins(3, 3, 3, 3)
        segment_layout.setSpacing(0)

        self.mode_buttons = []
        for idx, mode in enumerate(["Sequential", "Random"]):
            btn = QPushButton(mode)
            btn.setCheckable(True)
            btn.setChecked(idx == 0)
            btn.setFont(px_font(14, bold=True))
            btn.setFixedHeight(38)
            btn.clicked.connect(lambda checked, i=idx: self._on_mode_selected(i))
            segment_layout.addWidget(btn, 1)
            self.mode_buttons.append(btn)

        self.selected_mode_idx = 0  # Sequential default

        # Idle toggle button
        self.idle_button = QPushButton("Idle")
        self.idle_button.setCheckable(True)
        self.idle_button.setChecked(False)
        self.idle_button.setFont(px_font(14, bold=True))
        self.idle_button.setFixedSize(104, 44)
        self.idle_button.clicked.connect(self._on_idle_toggled)

        row.addWidget(self.mode_segment, 1)
        row.addWidget(self.idle_button)
        return row_widget

    def _init_audio(self):
        """Initialize pygame mixer for sound effects"""
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
            self.audio_available = True
            self.logger.debug("HomeScreen audio system initialized successfully")
        except Exception as e:
            self.logger.warning(f"Failed to initialize HomeScreen audio: {e}")
            self.audio_available = False

    def _play_sound_effect(self, sound_file):
        """Play a themed sound effect"""
        if not self.audio_available:
            self.logger.debug("Audio not available, skipping sound playback")
            return
        
        try:
            # Get current theme name
            theme_name = theme_manager.get_theme_name()
            
            # Build path to themed audio file
            audio_path = os.path.join(
                "resources", "theme", theme_name, "audio", sound_file
            )
            
            # Fallback to other theme if file doesn't exist
            if not os.path.exists(audio_path):
                # Try the other theme
                fallback_theme = "Wall-e" if theme_name == "Star Wars" else "Star Wars"
                audio_path = os.path.join(
                    "resources", "theme", fallback_theme, "audio", sound_file
                )
            
            # Play audio if file exists
            if os.path.exists(audio_path):
                # Stop any current background music briefly to avoid conflicts
                was_playing_music = pygame.mixer.music.get_busy()
                if was_playing_music:
                    pygame.mixer.music.pause()
                
                # Play the sound effect
                sound = pygame.mixer.Sound(audio_path)
                sound.play()
                self.logger.debug(f"Playing sound effect: {audio_path}")
                
                # Resume background music if it was playing
                if was_playing_music:
                    # Short delay to let sound effect start, then resume music
                    QTimer.singleShot(100, lambda: pygame.mixer.music.unpause())
                    
            else:
                self.logger.debug(f"Sound effect file not found: {sound_file}")
                
        except Exception as e:
            self.logger.error(f"Failed to play sound effect {sound_file}: {e}")


    # ---------- Playback caption ----------

    def _show_playing(self, scene_name: str, duration: float):
        """Show NOW PLAYING with the scene name and start the progress line"""
        self._playing_scene_name = scene_name
        self._playing_started = time.monotonic()
        try:
            self._playing_duration = max(float(duration), 0.1)
        except (TypeError, ValueError):
            self._playing_duration = 3.0

        self.status_label.setText("NOW PLAYING")
        metrics = self.playing_name_label.fontMetrics()
        self.playing_name_label.setText(
            metrics.elidedText(scene_name, Qt.TextElideMode.ElideRight, 340))
        self.playing_name_label.setVisible(True)
        self.playing_progress.setValue(0)
        self.playing_progress.setVisible(True)
        self._progress_timer.start()
        self._apply_caption_style()
        self._refresh_row_states()

    def _show_ready(self):
        """Show READY with no scene name"""
        self._playing_scene_name = None
        self._progress_timer.stop()
        self.status_label.setText("READY")
        self.playing_name_label.setVisible(False)
        self.playing_progress.setVisible(False)
        self._apply_caption_style()
        self._refresh_row_states()

    def _update_progress(self):
        """Advance the progress line from the scene's known duration"""
        if self._playing_scene_name is None:
            self._progress_timer.stop()
            return
        fraction = (time.monotonic() - self._playing_started) / self._playing_duration
        self.playing_progress.setValue(int(min(fraction, 1.0) * 1000))
        if fraction >= 1.0:
            self._progress_timer.stop()

    def _apply_caption_style(self):
        """Caption and spotlight colours for the current playback state"""
        green = theme_manager.get("green")
        playing = self._playing_scene_name is not None
        self.status_label.setStyleSheet(
            f"color: {green if playing else LABEL_GREY}; background: transparent; border: none;")
        self.stage_widget.set_glow(theme_manager.get("primary_color"), 0.30 if playing else 0.16)

    # ---------- Scenes card ----------

    def _create_scene_card(self) -> QFrame:
        """Single card: title, category pills, divider, scene list"""
        self.scene_card = QFrame()
        self.scene_card.setObjectName("home_card")
        self.scene_card.setFixedSize(CARD_WIDTH, CONTENT_HEIGHT)

        layout = QVBoxLayout(self.scene_card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.header = QLabel("SCENES")
        self.header.setFont(px_font(14, bold=True, spacing=1.5))
        self.current_scene_label = QLabel("")
        self.current_scene_label.setFont(px_font(13))
        self.current_scene_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.header)
        header.addStretch(1)
        header.addWidget(self.current_scene_label)
        layout.addLayout(header)

        # Category pills live in their own holder so they can be rebuilt
        self.category_holder = QVBoxLayout()
        self.category_holder.setContentsMargins(0, 0, 0, 0)
        self._create_category_widget_only()
        self.category_holder.addWidget(self.category_widget)
        layout.addLayout(self.category_holder)

        self.divider = QFrame()
        self.divider.setFixedHeight(1)
        layout.addWidget(self.divider)

        self.queue_list = SceneList()
        self.queue_list.setSpacing(2)
        self.queue_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.queue_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.queue_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.queue_list.currentRowChanged.connect(lambda _row: self._refresh_row_states())
        layout.addWidget(self.queue_list, 1)

        # Initial population
        self._update_scene_queue_panel()
        return self.scene_card

    def _on_category_selected(self, idx: int):
        """Handle category selection with improved state management"""
        # Add bounds checking
        if not hasattr(self, 'category_buttons') or not self.category_buttons:
            return

        if idx < 0 or idx >= len(self.category_buttons):
            return

        # Exactly one category pill is checked
        for i, btn in enumerate(self.category_buttons):
            btn.setChecked(i == idx)

        # Update the selected category
        self.selected_category_idx = idx
        self.last_triggered_scene = None
        self._update_scene_queue_panel()

        # Reset scene selection when category changes
        if hasattr(self, 'queue_list') and self.queue_list.count() > 0:
            self.queue_list.setCurrentRow(0)
            if hasattr(self, 'current_scene_index'):
                self.current_scene_index = 0

    def _update_scene_queue_panel(self):
        """Fill the scene list for the selected category"""
        self.queue_list.clear()
        self._scene_rows = []

        if not hasattr(self, "categories") or not self.categories:
            self.current_scene_label.setText("")
            return

        cat = self.categories[self.selected_category_idx]
        scenes = self.category_to_scenes.get(cat, [])

        if not scenes:
            self.current_scene_label.setText(f"{cat} · No scenes in this category")
            return

        count = len(scenes)
        self.current_scene_label.setText(f"{cat} · {count} scene{'s' if count != 1 else ''}")

        # Populate queue with scenes from selected category
        for s in scenes:
            row = SceneRow(
                name=s.get("label", "--"),
                audio=bool(s.get("audio_enabled", False)),
                anim=bool(s.get("script_enabled", False)),
                duration=f"{s.get('duration', '--')}s",
            )
            item = QListWidgetItem()
            item.setSizeHint(QSize(self.queue_list.viewport().width(), SCENE_ROW_HEIGHT))
            self.queue_list.addItem(item)
            self.queue_list.setItemWidget(item, row)
            self._scene_rows.append((s.get("label", ""), row))

        # Select first by default
        if self.queue_list.count() > 0:
            self.queue_list.setCurrentRow(0)
            self.current_scene_index = 0
        self._refresh_row_states()

    def _refresh_row_states(self):
        """Mark the selected and playing rows"""
        if not hasattr(self, "queue_list"):
            return
        current = self.queue_list.currentRow()
        for index, (label, row) in enumerate(self._scene_rows):
            row.set_state(selected=(index == current),
                          playing=(label == self._playing_scene_name))

    # ---------- Styling ----------

    def _apply_styles(self):
        """Apply theme colours to every styled widget"""
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        green = theme_manager.get("green")
        panel_bg = theme_manager.get("panel_bg")

        self.scene_card.setStyleSheet(f"""
            QFrame#home_card {{
                background-color: {panel_bg};
                border: 1px solid {rgba(primary, 0.45)};
                border-radius: 12px;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)
        self.header.setStyleSheet(f"color: {primary}; background: transparent; border: none;")
        self.current_scene_label.setStyleSheet(f"color: {LABEL_GREY}; background: transparent; border: none;")
        self.divider.setStyleSheet("background-color: #2e2e2e; border: none;")

        for btn in getattr(self, "category_buttons", []):
            btn.setStyleSheet(self._get_category_button_style())

        self.queue_list.setStyleSheet(f"""
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

        self.playing_name_label.setStyleSheet("color: white; background: transparent; border: none;")
        self.playing_progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: #2c2c2c;
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {green};
                border-radius: 2px;
            }}
        """)
        self.stage_line.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {rgba(primary, 0)}, stop:0.5 {rgba(primary, 0.6)}, stop:1 {rgba(primary, 0)});
            border: none;
        """)

        self.mode_segment.setStyleSheet(f"""
            QFrame#mode_segment {{
                background-color: {panel_bg};
                border: 1px solid #555555;
                border-radius: 22px;
            }}
        """)
        for btn in self.mode_buttons:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: #bdbdbd;
                    border: none;
                    border-radius: 19px;
                }}
                QPushButton:checked {{
                    background: {primary};
                    color: #111111;
                }}
                QPushButton:pressed {{
                    background: {primary_light};
                    color: #111111;
                }}
            """)
        self.idle_button.setStyleSheet(self._get_idle_button_style())

        self._apply_caption_style()
        self._refresh_row_states()

    def _get_category_button_style(self) -> str:
        """Category pill style; the checked pill fills with the theme colour"""
        primary = theme_manager.get("primary_color")
        return f"""
            QPushButton {{
                background: {PILL_BG};
                color: {TEXT_SOFT};
                border: 1px solid {PILL_BORDER};
                border-radius: 18px;
                padding: 0px 6px;
            }}
            QPushButton:hover {{
                border-color: {primary};
            }}
            QPushButton:checked {{
                background: {primary};
                color: #111111;
                border-color: {primary};
            }}
        """

    def _get_idle_button_style(self) -> str:
        """Idle pill: green outline when off, filled green when on"""
        green = theme_manager.get("green")
        panel_bg = theme_manager.get("panel_bg")
        return f"""
            QPushButton {{
                background: {panel_bg};
                color: {green};
                border: 1px solid {green};
                border-radius: 22px;
            }}
            QPushButton:checked {{
                background: {green};
                color: #111111;
            }}
        """

    def _on_mode_selected(self, idx: int):
        for i, btn in enumerate(self.mode_buttons):
            btn.setChecked(i == idx)
        self.selected_mode_idx = idx

    def _on_idle_toggled(self):
        """Switch the backend idle loop on or off - idle scenes are scheduled on the Pi"""
        enabled = self.idle_button.isChecked()
        self.idle_button.setText("Idle On" if enabled else "Idle")
        success = self.send_websocket_message("mode", name="idle", state=enabled)
        if success:
            self.logger.info(f"Idle mode {'activated' if enabled else 'deactivated'} - sent to backend")
        else:
            self.logger.error(f"Failed to send idle {'activation' if enabled else 'deactivation'} to backend")

    def _on_theme_changed(self):
        """Handle theme change by updating all styled components"""
        try:
            self._update_main_image()
            self._apply_styles()
            self.logger.info(f"Home screen updated for theme: {theme_manager.get_display_name()}")
        except Exception as e:
            self.logger.error(f"Error updating theme: {e}")

    @error_boundary
    def reload_emotions(self):
        """Backward-compatible: refresh categories when SceneScreen updates."""
        # Remove the existing category pills
        if hasattr(self, 'category_widget') and self.category_widget:
            self.category_holder.removeWidget(self.category_widget)
            self.category_widget.setParent(None)
            self.category_widget = None
        self.category_buttons = []

        # Build and insert the new pills
        self._create_category_widget_only()
        self.category_holder.addWidget(self.category_widget)
        for btn in self.category_buttons:
            btn.setStyleSheet(self._get_category_button_style())

        self._update_scene_queue_panel()
        self.logger.info("Categories reloaded from updated scene configuration")

    def _create_category_widget_only(self):
        """Create the category pill grid without adding it to any layout"""
        self.category_widget = QWidget()
        self.category_widget.setStyleSheet("background: transparent;")
        self.category_grid = QGridLayout(self.category_widget)
        self.category_grid.setSpacing(8)
        self.category_grid.setContentsMargins(0, 0, 0, 0)

        self.category_buttons = []

        # Load scenes config
        cfg = config_manager.get_config("resources/configs/scenes_config.json")
        self.scenes = cfg if isinstance(cfg, list) else []

        # Build category list -> scenes map
        self.category_to_scenes = {}
        for scene in self.scenes:
            cats = scene.get("categories", []) or ["All"]
            for c in cats:
                self.category_to_scenes.setdefault(c, []).append(scene)

        # If no categories at all, create an "All" bucket
        if not self.category_to_scenes:
            self.category_to_scenes = {"All": self.scenes[:]}
        self.categories = sorted(self.category_to_scenes.keys(), key=lambda s: s.lower())

        font = px_font(14, bold=True)
        for idx, cat in enumerate(self.categories):
            btn = QPushButton(cat)
            btn.setCheckable(True)
            btn.setChecked(idx == 0)
            btn.setFont(font)
            btn.setFixedHeight(36)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda checked, i=idx: self._on_category_selected(i))

            row = idx // CATEGORIES_PER_ROW
            col = idx % CATEGORIES_PER_ROW
            self.category_grid.addWidget(btn, row, col)
            self.category_buttons.append(btn)

        # Make sure all columns have equal stretch
        for col in range(CATEGORIES_PER_ROW):
            self.category_grid.setColumnStretch(col, 1)

        # default selection
        self.selected_category_idx = 0

    def connect_scene_screen_signals(self, scene_screen):
        """Connect signals from SceneScreen to update categories when changed."""
        scene_screen.scenes_updated.connect(self.reload_emotions)

    def __del__(self):
        """Clean up theme manager callback on destruction"""
        try:
            theme_manager.unregister_callback(self._on_theme_changed)
        except:
            pass  # Ignore errors during cleanup