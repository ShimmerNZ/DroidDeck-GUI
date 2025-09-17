import os
import json
import time
from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QWidget, QFrame, QListWidget, QListWidgetItem, QSizePolicy, QGridLayout,
    QMessageBox, QApplication
)
from PyQt6.QtGui import QPixmap, QFont, QColor
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from widgets.base_screen import BaseScreen
from core.config_manager import config_manager
from core.theme_manager import theme_manager
from core.utils import error_boundary

# Symbols for scene types
SCENE_TYPE_SYMBOLS = {
    "MP3": "🎵",
    "Animation": "🎬",
    "Combo": "🎵 🎬"
}

# Tight top gap above the "SCENE SELECTION" header:
FRAME_TOP_PADDING_PX = 6
LAYOUT_TOP_MARGIN_PX = 4


class HomeScreen(BaseScreen):
    """Scene selection dashboard with WebSocket-based controller navigation."""
    
    # Signal emitted when a scene should be triggered
    scene_triggered = pyqtSignal(str, int)  # category, scene_index

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Navigation state tracking
        self.current_scene_index = 0
        self.auto_advance_enabled = True
        self.is_playing_scene = False
        self.last_triggered_scene = None

        # Connect to WebSocket messages for navigation and scene completion
        if hasattr(self, 'websocket') and self.websocket:
            self.websocket.textMessageReceived.connect(self._handle_websocket_message)
        
        # Remove focus policy - no local input handling
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        # Register for theme change notifications
        theme_manager.register_callback(self._on_theme_changed)

    def _handle_websocket_message(self, message):
        """Handle WebSocket messages including controller navigation and scene events"""
        try:
            data = json.loads(message)
            
            # Handle controller navigation commands from backend
            if data.get('type') == 'navigation':
                action = data.get('action')
                self._handle_navigation_command(action)
                return
                
            # Handle scene completion notifications
            if data.get('type') == 'scene_completed':
                scene_name = data.get("scene_name", "")
                success = data.get("success", False)
                
                if success and self.auto_advance_enabled:
                    self.is_playing_scene = False
                    self._advance_to_next_scene()
                return
                    
            # Handle scene started notifications
            if data.get('type') == 'scene_started':
                self.is_playing_scene = True
                scene_name = data.get("scene_name", "")
                self.last_triggered_scene = scene_name
                return
                
            # Handle scene errors
            if data.get('type') == 'scene_error':
                self.is_playing_scene = False
                return
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse WebSocket message: {e}")
        except Exception as e:
            self.logger.error(f"Error handling WebSocket message: {e}")

    def _handle_navigation_command(self, action):
        """Handle navigation commands from controller via backend"""
        self.logger.debug(f"Received navigation command: {action}")
        
        if action == 'up':
            self._navigate_scenes(-1)
        elif action == 'down':
            self._navigate_scenes(1)
        elif action == 'left':
            self._navigate_categories(-1)
        elif action == 'right':
            self._navigate_categories(1)
        elif action == 'select':
            self._trigger_selected_scene()
        elif action == 'exit':
            self._handle_exit_command()

    def _handle_exit_command(self):
        """Handle exit command from controller"""
        # If playing a scene, stop it
        if self.is_playing_scene:
            self._stop_current_scene()
            return
        
        # If on home screen, show exit confirmation
        reply = QMessageBox.question(
            self, 'Exit Application', 
            'Do you want to exit the application?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if hasattr(self, 'parent') and hasattr(self.parent(), 'close'):
                self.parent().close()
            else:
                QApplication.quit()

    def _stop_current_scene(self):
        """Stop currently playing scene"""
        if self.websocket:
            stop_message = {
                "type": "scene_stop",
                "timestamp": time.time()
            }
            self.websocket.sendTextMessage(json.dumps(stop_message))
        
        self.is_playing_scene = False
        self.last_triggered_scene = None

    def _navigate_scenes(self, direction):
        """Navigate scene list up/down with visual feedback"""
        if self.queue_list.count() == 0:
            return
        
        current = self.queue_list.currentRow()
        if current == -1:  # No selection
            current = 0
            
        # Calculate new index with bounds checking (no looping for scenes)
        new_index = current + direction
        new_index = max(0, min(self.queue_list.count() - 1, new_index))
        
        # Update selection with visual feedback
        self.queue_list.setCurrentRow(new_index)
        self.current_scene_index = new_index
        self._highlight_selected_scene()

    def _navigate_categories(self, direction):
        """Navigate categories left/right with looping and visual feedback"""
        if not hasattr(self, 'category_buttons') or not self.category_buttons:
            return
            
        current = self.selected_category_idx
        total = len(self.category_buttons)
        
        # Calculate new index with looping
        new_index = (current + direction) % total
        
        # Update selection with visual feedback
        self._on_category_selected(new_index)
        self._highlight_selected_category()

    def _highlight_selected_scene(self):
        """Provide visual feedback for selected scene"""
        current_item = self.queue_list.currentItem()
        if current_item:
            # Add temporary highlighting
            primary_color = theme_manager.get("primary_color", "#ffa500")
            current_item.setBackground(QColor(primary_color))
            
            # Reset highlight after a short delay
            QTimer.singleShot(300, lambda: current_item.setBackground(QColor("transparent")))

    def _highlight_selected_category(self):
        """Provide visual feedback for selected category"""
        if hasattr(self, 'category_buttons') and self.selected_category_idx < len(self.category_buttons):
            button = self.category_buttons[self.selected_category_idx]
            
            # Add temporary glow effect
            original_style = button.styleSheet()
            primary_color = theme_manager.get("primary_color", "#ffa500")
            highlight_style = original_style + f"""
                border: 3px solid {primary_color};
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255, 165, 0, 40), stop:1 rgba(255, 165, 0, 20));
            """
            
            button.setStyleSheet(highlight_style)
            
            # Reset after short delay
            QTimer.singleShot(400, lambda: button.setStyleSheet(original_style))

    def _trigger_selected_scene(self):
        """Trigger the currently selected scene with controller feedback"""
        if not hasattr(self, "categories") or not self.categories:
            return
            
        # Don't trigger if already playing (prevent rapid-fire)
        if self.is_playing_scene:
            self.logger.debug("Scene already playing, ignoring trigger")
            return
            
        cat = self.categories[self.selected_category_idx]
        scenes = self.category_to_scenes.get(cat, [])
        
        current_row = self.queue_list.currentRow()
        if 0 <= current_row < len(scenes):
            scene = scenes[current_row]
            scene_name = scene.get("label", "Unknown")
            
            # Don't re-trigger same scene immediately
            if (scene_name == self.last_triggered_scene and self.is_playing_scene):
                self.logger.debug(f"Scene {scene_name} is currently playing, ignoring trigger")
                return
            
            # Provide immediate visual feedback
            self._provide_trigger_feedback()
            
            # Send WebSocket command to backend
            success = self.send_websocket_message("scene", emotion=scene_name)
            
            if success:
                # Emit signal and update UI
                self.scene_triggered.emit(cat, current_row)
                self.progress_label.setText(f"Progress: Playing '{scene_name}'")
                
                # Update state tracking
                self.is_playing_scene = True
                scene_duration = scene.get("duration", 3.0)
                fallback_timeout = int((scene_duration + 2) * 1000)
                QTimer.singleShot(fallback_timeout, self._reset_scene_state)
                self.last_triggered_scene = scene_name
                
                self.logger.info(f"Triggered scene: {scene_name} from category: {cat}")
            else:
                self.logger.error(f"Failed to trigger scene: {scene_name}")

    def _provide_trigger_feedback(self):
        """Provide immediate visual feedback for scene trigger"""
        current_item = self.queue_list.currentItem()
        if current_item:
            # Flash green to show activation
            original_bg = current_item.background()
            current_item.setBackground(QColor("#00ff00"))  # Green flash
            QTimer.singleShot(200, lambda: current_item.setBackground(original_bg))

    def _reset_scene_state(self):
        """Reset scene playing state as fallback"""
        if self.is_playing_scene:
            self.is_playing_scene = False
            self.logger.debug("Scene state reset by fallback timer")

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
        root = QHBoxLayout()
        # Outer screen margins
        root.setContentsMargins(80, 20, 90, 5)

        # Left WALL-E image
        self._create_image_section(root)

        # Right control panel
        self._create_right_panel(root)

        self.setLayout(root)

    def _create_image_section(self, parent_layout: QHBoxLayout):
        image_container = QVBoxLayout()
        image_container.addStretch()
        self.image_label = QLabel()
        self._update_main_image()
        image_container.addWidget(self.image_label)

        image_widget = QWidget()
        image_widget.setLayout(image_container)
        image_widget.setStyleSheet("background-color: rgba(0, 0, 0, 0);")
        parent_layout.addWidget(image_widget)

    def _update_main_image(self):
        """Update the main character image based on current theme"""
        image_path = theme_manager.get_image_path("main")
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path).scaled(
                320, 320,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(pixmap)
            self.image_label.setAlignment(Qt.AlignmentFlag.AlignBottom)

    def _create_right_panel(self, parent_layout: QHBoxLayout):
        self.right_frame = QFrame()
        self._update_right_frame_style()
        right_layout = QVBoxLayout(self.right_frame)
        right_layout.setSpacing(8)
        right_layout.setContentsMargins(8, LAYOUT_TOP_MARGIN_PX, 8, 8)

        # Header
        self.header = QLabel("SCENE SELECTION")
        self.header.setFont(QFont("Arial", 22, QFont.Weight.Bold))
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_header_style()
        right_layout.addWidget(self.header)

        # Category bar with wrapping
        self._create_category_bar(right_layout)

        # Scene queue panel
        scene_panel = self._create_scene_queue_panel()
        right_layout.addWidget(scene_panel, 1)

        # Mode selector + Idle
        self._create_mode_selector(right_layout)

        parent_layout.addWidget(self.right_frame)

    def _update_right_frame_style(self):
        """Update the right frame style based on current theme"""
        primary_color = theme_manager.get("primary_color")
        panel_bg = theme_manager.get("panel_bg")
        self.right_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {panel_bg};
                border: 2px solid {primary_color};
                border-radius: 12px;
                padding: {FRAME_TOP_PADDING_PX}px 12px 12px 12px;
            }}
        """)

    def _update_header_style(self):
        """Update the header style based on current theme"""
        primary_color = theme_manager.get("primary_color")
        self.header.setStyleSheet(f"""
            QLabel {{
                color: {primary_color};
                padding-bottom: 4px;
                font-weight: bold;
                border: none;
            }}
        """)

    def _create_category_bar(self, parent_layout: QVBoxLayout):
        # Create a widget to contain the grid layout
        category_widget = QWidget()
        self.category_grid = QGridLayout(category_widget)
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

        font = QFont("Arial", 18, QFont.Weight.Bold)
        buttons_per_row = 5
        
        for idx, cat in enumerate(self.categories):
            btn = QPushButton(cat)
            btn.setCheckable(True)
            btn.setFont(font)
            btn.setMinimumSize(130, 40)
            btn.setStyleSheet(self._get_category_button_style(selected=(idx == 0)))
            btn.clicked.connect(lambda checked, i=idx: self._on_category_selected(i))
            
            # Calculate row and column for grid placement
            row = idx // buttons_per_row
            col = idx % buttons_per_row
            
            self.category_grid.addWidget(btn, row, col)
            self.category_buttons.append(btn)

        # Make sure all columns have equal stretch
        for col in range(buttons_per_row):
            self.category_grid.setColumnStretch(col, 1)

        # default selection
        self.selected_category_idx = 0
        
        # Add the category widget to the parent layout
        parent_layout.addWidget(category_widget)

    def _get_category_button_style(self, selected: bool) -> str:
        """Get category button style based on current theme"""
        base_style = theme_manager.get_button_style("primary", checked=selected)
        
        # Add custom padding to prevent text cutoff
        custom_padding = """
            QPushButton {
                padding: 2px 4px;
            }
        """
        
        return base_style + custom_padding

    def _on_category_selected(self, idx: int):
        # Ensure single-selection behaviour
        for i, btn in enumerate(self.category_buttons):
            btn.setChecked(i == idx)
            btn.setStyleSheet(self._get_category_button_style(selected=(i == idx)))
        self.selected_category_idx = idx
        self.last_triggered_scene = None  # Clear to allow re-triggering scenes
        self._update_scene_queue_panel()
        
        # Reset scene selection when category changes
        if self.queue_list.count() > 0:
            self.queue_list.setCurrentRow(0)
            self.current_scene_index = 0

    def _create_scene_queue_panel(self) -> QWidget:
        self.scene_panel = QFrame()
        self._update_scene_panel_style()
        self.scene_layout = QVBoxLayout(self.scene_panel)
        self.scene_layout.setSpacing(6)
        self.scene_layout.setContentsMargins(0, 0, 0, 0)

        # Category status header
        self.current_scene_label = QLabel("Category: --")
        self.current_scene_label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        self._update_current_scene_label_style()
        self.scene_layout.addWidget(self.current_scene_label, 0)

        # Queue list
        self.queue_list = QListWidget()
        self.queue_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.queue_list.setMinimumHeight(120)
        self._update_queue_list_style()
        self.scene_layout.addWidget(self.queue_list, 1)

        # Progress
        self.progress_label = QLabel("Progress: --")
        self.progress_label.setFont(QFont("Arial", 13))
        self._update_progress_label_style()
        self.scene_layout.addWidget(self.progress_label, 0)

        # Stretch priorities
        self.scene_layout.setStretch(0, 0)  # header - fixed size
        self.scene_layout.setStretch(1, 1)  # list - expands to fill space
        self.scene_layout.setStretch(2, 0)  # progress - fixed size

        # Initial population
        self._update_scene_queue_panel()
        return self.scene_panel

    def _update_scene_panel_style(self):
        """Update scene panel style based on current theme"""
        grey = theme_manager.get("grey")
        panel_dark = theme_manager.get("panel_dark")
        self.scene_panel.setStyleSheet(f"""
            QFrame {{
                background-color: {panel_dark};
                border: 2px solid {grey};
                border-radius: 8px;
                padding: 6px;
            }}
        """)

    def _update_current_scene_label_style(self):
        """Update current scene label style based on current theme"""
        grey = theme_manager.get("grey")
        primary_color = theme_manager.get("primary_color")
        self.current_scene_label.setStyleSheet(f"""
            QLabel {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {grey}, stop:1 #444);
                border: 2px solid {grey};
                border-radius: 6px;
                color: {primary_color};
                padding: 4px 0px;
            }}
        """)

    def _update_queue_list_style(self):
        """Update queue list style based on current theme"""
        grey = theme_manager.get("grey")
        primary_color = theme_manager.get("primary_color")
        self.queue_list.setStyleSheet(f"""
            QListWidget {{
                background: #222;
                border: 1px solid {grey};
                border-radius: 8px;
                color: white;
                font-size: 16px;
                padding: 6px;
                show-decoration-selected: 1;
                outline: none;
            }}
            QListWidget::item {{
                padding: 8px 12px;
                border-radius: 6px;
                color: white;
            }}
            QListWidget::item:selected {{
                border: 2px solid {primary_color};
                background: #444;
                color: white;
                padding: 8px 12px;
                border-radius: 8px;
            }}
        """)

    def _update_progress_label_style(self):
        """Update progress label style based on current theme"""
        primary_color = theme_manager.get("primary_color")
        self.progress_label.setStyleSheet(f"color: {primary_color}; padding: 2px;")

    def _update_scene_queue_panel(self):
        # Determine selected category
        if not hasattr(self, "categories") or not self.categories:
            self.current_scene_label.setText("Category: --")
            self.queue_list.clear()
            self.progress_label.setText("Progress: --")
            return

        cat = self.categories[self.selected_category_idx]
        scenes = self.category_to_scenes.get(cat, [])
        self.current_scene_label.setText(f"Category: {cat}")
        self.queue_list.clear()

        if not scenes:
            self.progress_label.setText("Progress: No scenes in this category")
            return

        # Populate queue with scenes from selected category
        for s in scenes:
            label = s.get("label", "--")
            audio_enabled = s.get("audio_enabled", False)
            script_enabled = s.get("script_enabled", False)
            if audio_enabled and script_enabled:
                sym = SCENE_TYPE_SYMBOLS["Combo"]
            elif audio_enabled:
                sym = SCENE_TYPE_SYMBOLS["MP3"]
            elif script_enabled:
                sym = SCENE_TYPE_SYMBOLS["Animation"]
            else:
                sym = "⌘"
            duration = f"{s.get('duration', '--')}s"
            text = f"{sym}  {label}    {duration}"
            self.queue_list.addItem(QListWidgetItem(text))

        # Select first by default
        if self.queue_list.count() > 0:
            self.queue_list.setCurrentRow(0)
            self.current_scene_index = 0
        self.progress_label.setText("Progress: Ready to play")

    def _create_mode_selector(self, parent_layout: QVBoxLayout):
        self.mode_bar = QHBoxLayout()
        self.mode_buttons = []
        modes = ["Sequential", "Random"]
        font = QFont("Arial", 16, QFont.Weight.Bold)
        for idx, mode in enumerate(modes):
            btn = QPushButton(mode)
            btn.setCheckable(True)
            btn.setFont(font)
            btn.setMinimumSize(110, 36)
            btn.setStyleSheet(self._get_mode_button_style(selected=(idx == 0)))
            btn.clicked.connect(lambda checked, i=idx: self._on_mode_selected(i))
            self.mode_bar.addWidget(btn)
            self.mode_buttons.append(btn)

        self.selected_mode_idx = 0  # Sequential default

        # Idle toggle button
        self.idle_button = QPushButton("Idle")
        self.idle_button.setCheckable(True)
        self.idle_button.setFont(font)
        self.idle_button.setMinimumSize(110, 36)
        self.idle_button.setStyleSheet(self._get_idle_button_style(selected=False))
        self.idle_button.setChecked(False)
        self.idle_button.clicked.connect(self._on_idle_toggled)
        self.mode_bar.addWidget(self.idle_button)

        parent_layout.addLayout(self.mode_bar)

    def _get_mode_button_style(self, selected: bool) -> str:
        """Get mode button style based on current theme"""
        return theme_manager.get_button_style("primary", checked=selected)

    def _get_idle_button_style(self, selected: bool) -> str:
        """Get idle button style based on current theme"""
        green = theme_manager.get("green")
        green_gradient = theme_manager.get("green_gradient")
        
        if selected:
            return f"""
            QPushButton {{
                background: {green_gradient};
                border: 2px solid {green};
                border-radius: 8px;
                color: #222;
                font-weight: bold;
            }}
            """
        else:
            return f"""
            QPushButton {{
                background: #222;
                border: 2px solid {green};
                border-radius: 8px;
                color: {green};
                font-weight: bold;
            }}
            """

    def _on_mode_selected(self, idx: int):
        for i, btn in enumerate(self.mode_buttons):
            btn.setChecked(i == idx)
            btn.setStyleSheet(self._get_mode_button_style(selected=(i == idx)))
        self.selected_mode_idx = idx

    def _on_idle_toggled(self):
        self.idle_button.setStyleSheet(self._get_idle_button_style(selected=self.idle_button.isChecked()))
        if self.idle_button.isChecked():
            # Send idle mode activation to backend
            success = self.send_websocket_message("mode", name="idle", state=True)
            if success:
                self.logger.info("Idle mode activated - sent to backend")
            else:
                self.logger.error("Failed to send idle activation to backend")
                
            self.idle_timer = QTimer(self)
            self.auto_advance_enabled = False
            self.idle_timer.timeout.connect(self._play_idle_scene)
            self.idle_timer.start(20000)
        else:
            # Send idle mode deactivation to backend  
            self.auto_advance_enabled = True
            success = self.send_websocket_message("mode", name="idle", state=False)
            if success:
                self.logger.info("Idle mode deactivated - sent to backend")
            else:
                self.logger.error("Failed to send idle deactivation to backend")
                
            if hasattr(self, 'idle_timer'):
                self.idle_timer.stop()

    def _play_idle_scene(self):
        """Play an idle scene with backend integration"""
        try:
            # Look for scenes in "Idle" category
            idle_scenes = self.category_to_scenes.get("Idle", [])
            
            if idle_scenes:
                # Pick random idle scene
                import random
                idle_scene = random.choice(idle_scenes)
                scene_name = idle_scene.get("label", "Unknown Idle Scene")
                
                # Send to backend
                success = self.send_websocket_message("scene", emotion=scene_name)
                if success:
                    self.logger.info(f"Triggered idle scene: {scene_name}")
                else:
                    self.logger.error(f"Failed to trigger idle scene: {scene_name}")
            else:
                self.logger.warning("No idle scenes available for idle mode")
                
        except Exception as e:
            self.logger.error(f"Error playing idle scene: {e}")

    def _on_theme_changed(self):
        """Handle theme change by updating all styled components"""
        try:
            # Update main image
            self._update_main_image()
            
            # Update right frame style
            self._update_right_frame_style()
            
            # Update header style
            self._update_header_style()
            
            # Update category buttons
            for i, btn in enumerate(self.category_buttons):
                btn.setStyleSheet(self._get_category_button_style(selected=(i == self.selected_category_idx)))
            
            # Update scene panel styles
            self._update_scene_panel_style()
            self._update_current_scene_label_style()
            self._update_queue_list_style()
            self._update_progress_label_style()
            
            # Update mode buttons
            for i, btn in enumerate(self.mode_buttons):
                btn.setStyleSheet(self._get_mode_button_style(selected=(i == self.selected_mode_idx)))
            
            # Update idle button
            self.idle_button.setStyleSheet(self._get_idle_button_style(selected=self.idle_button.isChecked()))
            
            self.logger.info(f"Home screen updated for theme: {theme_manager.get_display_name()}")
        except Exception as e:
            self.logger.error(f"Error updating theme: {e}")

    @error_boundary
    def reload_emotions(self):
        """Backward-compatible: refresh categories when SceneScreen updates."""
        # Clear existing buttons
        for btn in getattr(self, "category_buttons", []):
            btn.setParent(None)
        self.category_buttons = []

        # Clear the grid layout
        if hasattr(self, 'category_grid'):
            while self.category_grid.count():
                item = self.category_grid.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)

        # Find the category widget in the right frame layout and remove it
        right_layout = self.right_frame.layout()
        for i in range(right_layout.count()):
            item = right_layout.itemAt(i)
            if item and item.widget() and hasattr(item.widget(), 'layout') and isinstance(item.widget().layout(), QGridLayout):
                widget = right_layout.takeAt(i).widget()
                if widget:
                    widget.setParent(None)
                break

        # Recreate the category bar at the correct position (after header)
        header_inserted = False
        for i in range(right_layout.count()):
            item = right_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QLabel):
                if item.widget().text() == "SCENE SELECTION":
                    # Insert category bar after header
                    self._create_category_bar(right_layout)
                    header_inserted = True
                    break
        
        if not header_inserted:
            # Fallback: add at position 1 (after header)
            temp_layout = QVBoxLayout()
            self._create_category_bar(temp_layout)
            if temp_layout.count() > 0:
                widget = temp_layout.itemAt(0).widget()
                right_layout.insertWidget(1, widget)
        
        self._update_scene_queue_panel()
        self.logger.info("Categories reloaded from updated scene configuration")

    def connect_scene_screen_signals(self, scene_screen):
        """Connect signals from SceneScreen to update categories when changed."""
        scene_screen.scenes_updated.connect(self.reload_emotions)

    # Backward compatibility methods (now handled via WebSocket)
    def select_queue_item(self, idx: int):
        """Select a specific queue item by index (for compatibility)"""
        count = self.queue_list.count()
        if 0 <= idx < count:
            self.queue_list.setCurrentRow(idx)
            self.current_scene_index = idx

    def trigger_selected_scene(self):
        """Trigger the currently selected scene (backwards compatibility)"""
        self._trigger_selected_scene()

    def __del__(self):
        """Clean up theme manager callback on destruction"""
        try:
            theme_manager.unregister_callback(self._on_theme_changed)
        except:
            pass  # Ignore errors during cleanup