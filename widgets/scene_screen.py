#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QCheckBox, QComboBox, QMessageBox,
    QLineEdit, QDoubleSpinBox, QSpinBox, QListWidget, QListWidgetItem,
    QHeaderView, QTableWidget, QTableWidgetItem, QFrame, QDialog,
    QDialogButtonBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QRect, QParallelAnimationGroup, QTimer
from PyQt6.QtGui import QFont, QPainter, QPalette
from widgets.base_screen import BaseScreen
from core.config_manager import config_manager
from core.theme_manager import theme_manager  # Import theme manager
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

SCENE_TYPE_SYMBOLS = {
    "Audio": "🎵",
    "Script": "🎬"
}

class TouchFriendlyMultiSelect(QWidget):
    """Touch-friendly multi-select widget with modal dialog"""
    
    def __init__(self, categories, selected_categories=None):
        super().__init__()
        self.categories = categories
        self.selected_categories = selected_categories or []
        self.setup_ui()
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.display_label = QLabel(self.get_display_text())
        self.update_style()
        self.display_label.setMinimumHeight(45)
        self.display_label.mousePressEvent = self.open_selector
        
        layout.addWidget(self.display_label)
    
    def update_style(self):
        """Update styling based on current theme"""
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        card_bg = theme_manager.get("card_bg")
        
        self.display_label.setStyleSheet(f"""
            QLabel {{
                background-color: {card_bg};
                border: 2px solid {primary};
                border-radius: 6px;
                color: {primary};
                padding: 10px 15px;
                font-size: 14px;
                font-weight: 500;
            }}
            QLabel:hover {{
                background-color: #2d2d2d;
                border-color: {primary_light};
                color: {primary_light};
            }}
        """)
        
    def get_display_text(self):
        if not self.selected_categories:
            return "Select categories..."
        elif len(self.selected_categories) <= 2:
            return ", ".join(self.selected_categories)
        else:
            return f"{len(self.selected_categories)} categories selected"
    
    def open_selector(self, event):
        dialog = CategorySelectorDialog(self.categories, self.selected_categories, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.selected_categories = dialog.get_selected_categories()
            self.display_label.setText(self.get_display_text())
    
    def get_selected_categories(self):
        return self.selected_categories.copy()
    
    def set_selected_categories(self, categories):
        self.selected_categories = categories.copy()
        self.display_label.setText(self.get_display_text())

class CategorySelectorDialog(QDialog):
    """Modal dialog for category selection"""
    
    def __init__(self, categories, selected_categories, parent=None):
        super().__init__(parent)
        self.categories = categories
        self.selected_categories = selected_categories.copy()
        self.checkboxes = {}
        self.setup_ui()
        
        # Connect state change handlers for Idle category exclusivity
        for category, checkbox in self.checkboxes.items():
            checkbox.stateChanged.connect(
                lambda state, cat=category: self._on_category_changed(cat, state)
            )
        
    def setup_ui(self):
        self.setWindowTitle("Select Categories")
        self.setModal(True)
        self.setFixedSize(350, 450)
        
        primary = theme_manager.get("primary_color")
        self.setStyleSheet(f"""
            QDialog {{
                background-color: #222;
                border: 3px solid {primary};
                border-radius: 12px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Header
        header = QLabel("Select Categories:")
        header.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        header.setStyleSheet(f"color: {primary}; padding: 15px;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)
        
        # Scrollable area for categories
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        grey = theme_manager.get("grey")
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 2px solid {grey};
                border-radius: 8px;
                background-color: #333;
            }}
        """)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(5)
        
        # Create checkboxes for each category
        for category in self.categories:
            emoji = CATEGORIES.get(category, "⭐")
            checkbox = QCheckBox(f"{emoji} {category}")
            checkbox.setChecked(category in self.selected_categories)
            
            # Special styling for Idle category to highlight its exclusivity
            if category == "Idle":
                idle_color = "#88ccff"  # Light blue for Idle
                checkbox.setStyleSheet(f"""
                    QCheckBox {{
                        color: {idle_color};
                        font-size: 16px;
                        padding: 12px;
                        min-height: 40px;
                        font-weight: bold;
                        background-color: #2a2a3a;
                        border-radius: 4px;
                    }}
                    QCheckBox::indicator {{
                        width: 24px;
                        height: 24px;
                    }}
                    QCheckBox::indicator:checked {{
                        background-color: {idle_color};
                        border: 2px solid {idle_color};
                        border-radius: 4px;
                    }}
                    QCheckBox::indicator:unchecked {{
                        background-color: #555;
                        border: 2px solid {grey};
                        border-radius: 4px;
                    }}
                    QCheckBox:hover {{
                        background-color: #3a3a4a;
                    }}
                """)
            else:
                checkbox.setStyleSheet(f"""
                QCheckBox {{
                    color: {primary};
                    font-size: 16px;
                    padding: 12px;
                    min-height: 40px;
                    font-weight: 500;
                }}
                QCheckBox::indicator {{
                    width: 24px;
                    height: 24px;
                }}
                QCheckBox::indicator:checked {{
                    background-color: {primary};
                    border: 2px solid {primary};
                    border-radius: 4px;
                }}
                QCheckBox::indicator:unchecked {{
                    background-color: #555;
                    border: 2px solid {grey};
                    border-radius: 4px;
                }}
                QCheckBox:hover {{
                    background-color: #3a3a3a;
                }}
            """)
            self.checkboxes[category] = checkbox
            scroll_layout.addWidget(checkbox)
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        card_bg = theme_manager.get("card_bg")
        primary_light = theme_manager.get("primary_light")
        button_box.setStyleSheet(f"""
            QDialogButtonBox QPushButton {{
                background-color: {card_bg};
                border: 2px solid {grey};
                border-radius: 6px;
                color: {primary};
                font-weight: bold;
                padding: 12px 24px;
                font-size: 16px;
                min-width: 80px;
            }}
            QDialogButtonBox QPushButton:hover {{
                background-color: #333;
                border: 2px solid {primary};
                color: {primary_light};
            }}
        """)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_selected_categories(self):
        selected = []
        for category, checkbox in self.checkboxes.items():
            if checkbox.isChecked():
                selected.append(category)
        return selected
    
    def _on_category_changed(self, changed_category: str, state: int):
        """
        Handle category checkbox changes with Idle exclusivity rule
        
        Rule: Idle category is exclusive - cannot be combined with other categories
        - If Idle is checked: uncheck all other categories
        - If another category is checked while Idle is checked: uncheck Idle
        """
        from PyQt6.QtCore import Qt
        
        is_checked = (state == Qt.CheckState.Checked.value)
        
        if changed_category == "Idle" and is_checked:
            # Idle was just checked → uncheck all other categories
            for category, checkbox in self.checkboxes.items():
                if category != "Idle" and checkbox.isChecked():
                    checkbox.blockSignals(True)  # Prevent recursion
                    checkbox.setChecked(False)
                    checkbox.blockSignals(False)
            
            # Show info message
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
            
        elif changed_category != "Idle" and is_checked:
            # Non-Idle category was checked → uncheck Idle if it's checked
            idle_checkbox = self.checkboxes.get("Idle")
            if idle_checkbox and idle_checkbox.isChecked():
                idle_checkbox.blockSignals(True)
                idle_checkbox.setChecked(False)
                idle_checkbox.blockSignals(False)

    
class EnhancedSceneRow(QWidget):
    """Enhanced expandable scene row with better styling and layout"""
    
    def __init__(self, scene_data, audio_files, bottango_scenes, row_index, parent_screen):
        super().__init__()
        self.scene_data = scene_data
        self.audio_files = audio_files
        self.bottango_scenes = bottango_scenes
        self.row_index = row_index
        self.parent_screen = parent_screen
        self.is_expanded = False
        self.details_widget = None
        self.animation_group = None
        self.setup_ui()
        
        # Register for theme changes
        theme_manager.register_callback(self.update_theme)
    
    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Create main row (always visible)
        self.create_main_row()
        
        # Create details row (expandable)
        self.create_details_row()
        
        # Initially hide details
        self.details_widget.hide()
    
    def update_theme(self):
        """Update styling when theme changes"""
        self.update_main_row_style()
        self.update_details_style()
        self.update_name_edit_style()
        self.update_button_theme_colors()
        self.update_expand_indicator_style()  
        if hasattr(self, 'category_selector'):
            self.category_selector.update_style()
    
    def update_main_row_style(self):
        """Update main row styling"""
        card_bg = theme_manager.get("card_bg")
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        grey = theme_manager.get("grey")
        
        if self.is_expanded:
            self.main_row.setStyleSheet(f"""
                QWidget {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {card_bg}, stop:1 #1f1f1f);
                    border: 2px solid {primary};
                    border-bottom: 1px solid {grey};
                    border-radius: 8px 8px 0px 0px;
                    margin: 2px;
                    margin-bottom: 0px;
                }}
            """)
        else:
            self.main_row.setStyleSheet(f"""
                QWidget {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {card_bg}, stop:1 #1f1f1f);
                    border: 2px solid {grey};
                    border-radius: 8px;
                    margin: 2px;
                }}
                QWidget:hover {{
                    border: 2px solid {primary};
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #2a2a2a, stop:1 #232323);
                }}
            """)
    
    def update_name_edit_style(self):
        """Update name edit field styling"""
        card_bg = theme_manager.get("card_bg")
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        
        self.name_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {card_bg};
                border: 2px solid {primary};
                border-radius: 6px;
                color: {primary};
                padding: 5px 15px;
                font-size: 16px;
                font-weight: bold;
            }}
            QLineEdit:focus {{
                border-color: {primary_light};
                background-color: #2a2a2a;
            }}
        """)
    
    def update_button_theme_colors(self):
        """Update Audio and Script button colors based on theme"""
        primary = theme_manager.get("primary_color")
        grey = theme_manager.get("grey")
        
        audio_enabled = self.audio_cb.isChecked() if hasattr(self, 'audio_cb') else self.scene_data.get("audio_enabled", False)
        
        # Check if any script is specified
        if hasattr(self, 'script_m1_input') and hasattr(self, 'script_m2_input'):
            has_m1 = self.script_m1_input.text().strip() != ""
            has_m2 = self.script_m2_input.text().strip() != ""
            script_enabled = has_m1 or has_m2
        else:
            script_enabled = (self.scene_data.get("script_maestro1") is not None or 
                            self.scene_data.get("script_maestro2") is not None)
        
        # Update audio indicator
        self.audio_indicator.setStyleSheet(f"""
            QLabel {{
                font-size: 14px;
                border: 2px solid {'#666' if not audio_enabled else primary};
                background: {primary if audio_enabled else 'transparent'};
                color: {'white' if audio_enabled else grey};
                padding: 4px;
                font-weight: bold;
            }}
        """)
        
        # Update script indicator  
        self.script_indicator.setStyleSheet(f"""
            QLabel {{
                font-size: 14px;
                border: 2px solid {'#666' if not script_enabled else primary};
                background: {primary if script_enabled else 'transparent'};
                color: {'white' if script_enabled else grey};
                padding: 4px;
                font-weight: bold;
            }}
        """)
        
    def update_expand_indicator_style(self):
        """Update expand indicator color based on theme"""
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        
        if self.is_expanded:
            color = primary_light
        else:
            color = primary
            
        self.expand_indicator.setStyleSheet(f"""
            QLabel {{
                color: {color};
                font-weight: bold;
                font-size: 18px;
                border: none;
                background: transparent;
            }}
        """)

    def create_main_row(self):
        self.main_row = QWidget()
        self.main_row.setFixedHeight(70)
        self.update_main_row_style()
        
        # Make the main row clickable
        self.main_row.mousePressEvent = self.toggle_expansion
        
        layout = QHBoxLayout(self.main_row)
        layout.setContentsMargins(10, 15, 10, 15)
        layout.setSpacing(15)
        
        # Expand/collapse indicator
        self.expand_indicator = QLabel("▶")
        primary = theme_manager.get("primary_color")
        self.expand_indicator.setStyleSheet(f"""
            QLabel {{
                color: {primary};
                font-weight: bold;
                font-size: 18px;
                border: none;
                background: transparent;
            }}
        """)
        self.expand_indicator.setFixedSize(40, 40)
        self.expand_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.expand_indicator)
        
        # Name field
        self.name_edit = QLineEdit(self.scene_data.get("label", ""))
        self.update_name_edit_style()
        self.name_edit.setMaxLength(32)
        self.name_edit.setFixedSize(220, 45)
        layout.addWidget(self.name_edit)
        
        # Categories multi-select
        categories = list(CATEGORIES.keys())
        selected_categories = self.scene_data.get("categories", [])
        self.category_selector = TouchFriendlyMultiSelect(categories, selected_categories)
        self.category_selector.setFixedSize(220, 45)
        layout.addWidget(self.category_selector)
        
        # Type indicators
        type_widget = QWidget()
        type_widget.setFixedSize(220, 45)
        type_widget.setStyleSheet("QWidget { border: none; }")
        type_layout = QHBoxLayout(type_widget)
        type_layout.setContentsMargins(0, 0, 0, 0)
        type_layout.setSpacing(8)

        # Audio indicator
        audio_enabled = self.scene_data.get("audio_enabled", False)
        self.audio_indicator = QLabel("🎵 Audio" if audio_enabled else "Audio")
        grey = theme_manager.get("grey")
        self.audio_indicator.setStyleSheet(f"""
            QLabel {{
                font-size: 14px;
                border: 2px solid #666;
                background: {primary if audio_enabled else 'transparent'};
                color: {'white' if audio_enabled else grey};
                padding: 4px;
                font-weight: bold;
            }}
        """)
        self.audio_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.audio_indicator.setFixedSize(100, 35)
        type_layout.addWidget(self.audio_indicator)
        
        # Script indicator
        script_enabled = self.scene_data.get("script_enabled", False)
        self.script_indicator = QLabel("🎬 Script" if script_enabled else "Script")
        self.script_indicator.setStyleSheet(f"""
            QLabel {{
                font-size: 14px;
                border: 2px solid #666;
                background: {primary if script_enabled else 'transparent'};
                color: {'white' if script_enabled else grey};
                padding: 4px;
                font-weight: bold;
            }}
        """)
        self.script_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.script_indicator.setFixedSize(100, 35)
        type_layout.addWidget(self.script_indicator)
        
        layout.addWidget(type_widget)
        
        # Action buttons
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)
        actions_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        self.test_btn = QPushButton("Test")
        green = theme_manager.get("green")
        green_gradient = theme_manager.get("green_gradient", f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {green}, stop:1 #2d8f2d)")
        self.test_btn.setStyleSheet(f"""
            QPushButton {{
                background: {green_gradient};
                border: 2px solid {green};
                border-radius: 6px;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 8px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #55dd55, stop:1 {green});
            }}
        """)
        self.test_btn.setFixedSize(70, 35)
        self.test_btn.clicked.connect(self.test_scene)
        actions_layout.addWidget(self.test_btn)
        
        self.delete_btn = QPushButton("Delete")
        red = theme_manager.get("red")
        self.delete_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {red}, stop:1 #8b2635);
                border: 2px solid {red};
                border-radius: 6px;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 8px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ee5555, stop:1 {red});
            }}
        """)
        self.delete_btn.setFixedSize(80, 35)
        self.delete_btn.clicked.connect(self.delete_scene)
        actions_layout.addWidget(self.delete_btn)
        
        layout.addLayout(actions_layout)
        self.main_layout.addWidget(self.main_row)

    def create_details_row(self):
        self.details_widget = QWidget()
        self.details_widget.setFixedHeight(75)
        self.update_details_style()
        
        layout = QHBoxLayout(self.details_widget)
        layout.setContentsMargins(15, 15, 15, 15)  # Reduced from 20,15,25,15
        layout.setSpacing(12)  # Reduced from 20
        
        # Audio section
        self.audio_cb = QCheckBox("Audio:")
        self.audio_cb.setChecked(self.scene_data.get("audio_enabled", False))
        self.update_checkbox_style(self.audio_cb)
        
        # Audio file dropdown
        self.audio_file_combo = QComboBox()
        self.audio_file_combo.addItems(self.audio_files)
        current_audio = self.scene_data.get("audio_file", "")
        if current_audio and current_audio in self.audio_files:
            self.audio_file_combo.setCurrentText(current_audio)
        elif self.audio_files:
            self.audio_file_combo.setCurrentIndex(0)
        
        self.audio_file_combo.setEnabled(self.audio_cb.isChecked())
        self.audio_file_combo.setMaximumWidth(180)  # Limit width
        self.update_combo_style(self.audio_file_combo)
        
        self.audio_cb.stateChanged.connect(
            lambda state: self.audio_file_combo.setEnabled(state == Qt.CheckState.Checked.value)
        )
        self.audio_cb.stateChanged.connect(self.update_indicators)
        
        layout.addWidget(self.audio_cb)
        layout.addWidget(self.audio_file_combo)
        
        # Script (Bottango Scene) section
        self.script_cb = QCheckBox("Script:")
        self.script_cb.setChecked(self.scene_data.get("script_enabled", False))
        self.update_checkbox_style(self.script_cb)
        
        # Bottango scene dropdown
        self.bottango_combo = QComboBox()
        scene_names = [scene["name"] for scene in self.bottango_scenes]
        if scene_names:
            self.bottango_combo.addItems(scene_names)
        else:
            self.bottango_combo.addItem("No scenes available")
        
        current_bottango = self.scene_data.get("bottango_scene", "")
        if current_bottango and current_bottango in scene_names:
            self.bottango_combo.setCurrentText(current_bottango)
        elif scene_names:
            self.bottango_combo.setCurrentIndex(0)
        
        self.bottango_combo.setEnabled(self.script_cb.isChecked())
        self.bottango_combo.setMaximumWidth(180)  # Limit width
        self.update_combo_style(self.bottango_combo)
        
        self.script_cb.stateChanged.connect(
            lambda state: self.bottango_combo.setEnabled(state == Qt.CheckState.Checked.value)
        )
        self.script_cb.stateChanged.connect(self.update_indicators)
        
        layout.addWidget(self.script_cb)
        layout.addWidget(self.bottango_combo)
        
        # Duration section (plain text input)
        duration_label = QLabel("Duration(s):")
        duration_label.setStyleSheet("color: white; font-weight: bold; font-size: 12px; min-width: 68px; border: none; background: transparent;")
        
        self.duration_input = QLineEdit()
        self.duration_input.setText(str(self.scene_data.get("duration", 1.0)))
        self.duration_input.setPlaceholderText("1.0")
        self.duration_input.setMaximumWidth(60)  # Smaller input
        self.update_text_input_style(self.duration_input)
        self.duration_input.textChanged.connect(lambda text: self.validate_float_input(text, self.duration_input))
        
        layout.addWidget(duration_label)
        layout.addWidget(self.duration_input)
        
        # Delay section (plain text input)
        delay_label = QLabel("Delay(ms):")
        delay_label.setStyleSheet("color: white; font-weight: bold; font-size: 12px; min-width: 62px; border: none; background: transparent;")
        
        self.delay_input = QLineEdit()
        self.delay_input.setText(str(self.scene_data.get("delay", 0)))
        self.delay_input.setPlaceholderText("0")
        self.delay_input.setMaximumWidth(60)  # Smaller input
        self.update_text_input_style(self.delay_input)
        self.delay_input.textChanged.connect(lambda text: self.validate_int_input(text, self.delay_input))
        
        # Delay is enabled if audio is checked AND script is checked
        self.delay_input.setEnabled(self.audio_cb.isChecked() and self.script_cb.isChecked())
        
        def update_delay_enabled():
            self.delay_input.setEnabled(self.audio_cb.isChecked() and self.script_cb.isChecked())
        
        self.audio_cb.stateChanged.connect(update_delay_enabled)
        self.script_cb.stateChanged.connect(update_delay_enabled)
        
        layout.addWidget(delay_label)
        layout.addWidget(self.delay_input)
        layout.addStretch()
        
        self.main_layout.addWidget(self.details_widget)
        
    def update_details_style(self):
        """Update details styling when theme changes"""
        expanded_bg = theme_manager.get("expanded_bg")
        grey = theme_manager.get("grey")
        
        self.details_widget.setStyleSheet(f"""
            QWidget {{
                background: {expanded_bg};
                border: 2px solid {grey};
                border-top: none;
                border-radius: 0px 0px 8px 8px;
                margin: 2px;
                margin-top: 0px;
            }}
        """)
    
    def update_checkbox_style(self, checkbox):
        """Update checkbox styling"""
        primary = theme_manager.get("primary_color")
        grey = theme_manager.get("grey")
        
        checkbox.setStyleSheet(f"""
            QCheckBox {{
                color: white;
                font-weight: bold;
                font-size: 13px;
                min-width: 60px;
                border: none;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {primary};
                border: 2px solid {primary};
                border-radius: 3px;
            }}
            QCheckBox::indicator:unchecked {{
                background-color: #555;
                border: 2px solid {grey};
                border-radius: 3px;
            }}
        """)
    
    def update_combo_style(self, combo):
        """Update combobox styling"""
        card_bg = theme_manager.get("card_bg")
        primary = theme_manager.get("primary_color")
        grey = theme_manager.get("grey")
        
        combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {card_bg};
                border: 2px solid {primary};
                border-radius: 4px;
                color: {primary};
                padding: 4px 8px;
                font-size: 12px;
                min-height: 25px;
                min-width: 140px;
            }}
            QComboBox:disabled {{
                background-color: #333;
                border-color: {grey};
                color: {grey};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid {primary};
                margin-right: 5px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {card_bg};
                border: 2px solid {primary};
                color: {primary};
                selection-background-color: {primary};
                selection-color: black;
            }}
        """)
    
    def update_script_input_style(self, input_widget):
        """Update script input styling"""
        card_bg = theme_manager.get("card_bg")
        primary = theme_manager.get("primary_color")
        grey = theme_manager.get("grey")
        
        input_widget.setStyleSheet(f"""
            QLineEdit {{
                background-color: {card_bg};
                border: 2px solid {primary};
                border-radius: 4px;
                color: {primary};
                padding: 4px 8px;
                font-size: 12px;
                min-height: 25px;
                max-width: 80px;
            }}
            QLineEdit:disabled {{
                background-color: #333;
                border-color: {grey};
                color: {grey};
            }}
            QLineEdit::placeholder {{
                color: {grey};
            }}
        """)
    
    def update_text_input_style(self, input_widget):
        """Update text input styling (for duration and delay)"""
        card_bg = theme_manager.get("card_bg")
        primary = theme_manager.get("primary_color")
        grey = theme_manager.get("grey")
        
        input_widget.setStyleSheet(f"""
            QLineEdit {{
                background-color: {card_bg};
                border: 2px solid {primary};
                border-radius: 4px;
                color: {primary};
                padding: 4px 8px;
                font-size: 12px;
                min-height: 25px;
                min-width: 50px;
            }}
            QLineEdit:disabled {{
                background-color: #333;
                border-color: {grey};
                color: {grey};
            }}
            QLineEdit::placeholder {{
                color: {grey};
            }}
        """)
    
    def validate_float_input(self, text, input_widget):
        """Only allow valid float input for duration"""
        if text:
            # Allow digits, single decimal point
            filtered = ''.join(c for c in text if c.isdigit() or c == '.')
            # Ensure only one decimal point
            if filtered.count('.') > 1:
                filtered = filtered[:filtered.rfind('.')]
            if filtered != text:
                input_widget.setText(filtered)
    
    def validate_int_input(self, text, input_widget):
        """Only allow digits for delay"""
        if text and not text.isdigit():
            filtered_text = ''.join(c for c in text if c.isdigit())
            input_widget.setText(filtered_text)
    
    def update_bottango_scenes(self, bottango_scenes):
        """Update the Bottango scenes dropdown with new scenes"""
        self.bottango_scenes = bottango_scenes
        current_selection = self.bottango_combo.currentText()
        # Also check the original saved value — combo may show wrong text if it
        # was built before the scene list arrived (race condition on refresh)
        saved_selection = self.scene_data.get("bottango_scene", "")
        self.bottango_combo.clear()

        scene_names = [scene["name"] for scene in bottango_scenes]
        if scene_names:
            self.bottango_combo.addItems(scene_names)
            # Prefer the saved value, fall back to whatever was showing
            target = saved_selection if saved_selection in scene_names else current_selection
            if target in scene_names:
                self.bottango_combo.setCurrentText(target)
        else:
            self.bottango_combo.addItem("No scenes available")
    
    def update_indicators(self):
        """Update the type indicators based on checkbox states"""
        audio_enabled = self.audio_cb.isChecked()
        script_enabled = self.script_cb.isChecked()
        primary = theme_manager.get("primary_color")
        grey = theme_manager.get("grey")
        
        self.audio_indicator.setText("🎵 Audio" if audio_enabled else "Audio")
        self.audio_indicator.setStyleSheet(f"""
            QLabel {{
                font-size: 14px;
                border: 2px solid {'#666' if not audio_enabled else primary};
                background: {primary if audio_enabled else 'transparent'};
                color: {'white' if audio_enabled else grey};
                padding: 4px;
                font-weight: bold;
            }}
        """)
        
        self.script_indicator.setText("🎬 Script" if script_enabled else "Script")
        self.script_indicator.setStyleSheet(f"""
            QLabel {{
                font-size: 14px;
                border: 2px solid {'#666' if not script_enabled else primary};
                background: {primary if script_enabled else 'transparent'};
                color: {'white' if script_enabled else grey};
                padding: 4px;
                font-weight: bold;
            }}
        """)
    
    def toggle_expansion(self, event):
        """Toggle the expansion state"""
        if self.is_expanded:
            self.collapse()
        else:
            self.expand()
    
    def expand(self):
        """Expand to show details"""
        if not self.is_expanded:
            self.is_expanded = True
            self.expand_indicator.setText("▼")
            self.update_expand_indicator_style()  # Use theme-aware styling
            self.details_widget.show()
            self.update_main_row_style()
    
    def collapse(self):
        """Collapse to hide details"""
        if self.is_expanded:
            self.is_expanded = False
            self.expand_indicator.setText("▶")
            self.update_expand_indicator_style()  # Use theme-aware styling
            self.details_widget.hide()
            self.update_main_row_style()
    
    def test_scene(self):
        """Test this scene"""
        scene_data = self.get_scene_data()
        self.parent_screen.test_scene_data(scene_data)
    
    def delete_scene(self):
        """Delete this scene"""
        self.parent_screen.delete_scene_row(self.row_index)
    
    def get_scene_data(self):
        """Extract current scene data from widgets"""
        audio_file = self.audio_file_combo.currentText() if self.audio_cb.isChecked() else ""
        
        # Get bottango scene if script is enabled
        bottango_scene = ""
        if self.script_cb.isChecked():
            bottango_scene = self.bottango_combo.currentText()
            if bottango_scene == "No scenes available":
                bottango_scene = ""
        
        # Parse duration and delay with defaults
        try:
            duration = float(self.duration_input.text()) if self.duration_input.text() else 1.0
        except ValueError:
            duration = 1.0
        
        try:
            delay = int(self.delay_input.text()) if self.delay_input.text() else 0
        except ValueError:
            delay = 0
        
        # Only include delay if both audio and script are enabled
        if not (self.audio_cb.isChecked() and self.script_cb.isChecked()):
            delay = 0
        
        return {
            "label": self.name_edit.text().strip(),
            "emoji": "🎭",
            "categories": self.category_selector.get_selected_categories(),
            "audio_enabled": self.audio_cb.isChecked(),
            "audio_file": audio_file,
            "script_enabled": self.script_cb.isChecked(),
            "bottango_scene": bottango_scene,
            "duration": duration,
            "delay": delay
        }

class SceneScreen(BaseScreen):
    """Interface for managing emotion scenes and audio mappings with enhanced accordion layout"""
    
    scenes_updated = pyqtSignal()  # Signal to notify HomeScreen of changes

    def _setup_screen(self):
        self.setFixedWidth(1200)
        self.scenes_data = []
        self.audio_files = []
        self.bottango_scenes = []  # Available Bottango scenes from backend
        self.scene_rows = []
        
        # Register for theme changes
        theme_manager.register_callback(self.update_theme)
        
        self.init_ui()
        
        if self.websocket:
            self.websocket.textMessageReceived.connect(self.handle_message)
            # Wait for connection before requesting audio files
            if self.websocket.is_connected():
                self.request_audio_files()
            else:
                # Set up a timer to retry when connection is established
                self.connection_check_timer = QTimer()
                self.connection_check_timer.timeout.connect(self.check_connection_and_request_audio)
                self.connection_check_timer.start(1000)  # Check every second
        else:
            self.use_fallback_audio_files()

    def check_connection_and_request_audio(self):
        """Check WebSocket connection and request audio files when ready"""
        if self.websocket and self.websocket.is_connected():
            self.connection_check_timer.stop()
            self.request_audio_files()

    def update_theme(self):
        """Update all UI elements when theme changes"""
        self.update_main_frame_style()
        self.update_scroll_area_style()
        self.update_button_styles()
        self.update_status_label_style()
        
        # Update all scene rows
        for row in self.scene_rows:
            row.update_theme()

    def update_main_frame_style(self):
        """Update main frame styling"""
        primary = theme_manager.get("primary_color")
        self.main_frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a1a, stop:1 #0f0f0f);
                border: 2px solid {primary};
                border-radius: 15px;
                padding: 10px;
            }}
        """)

    def update_scroll_area_style(self):
        """Update scroll area styling"""
        grey = theme_manager.get("grey")
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        dark_bg = theme_manager.get("dark_bg")
        
        self.scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 3px solid {grey};
                border-radius: 12px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1e1e1e, stop:1 #141414);
            }}
            QScrollArea::corner {{
                background: {dark_bg};
            }}
            QScrollBar:vertical {{
                background: {dark_bg};
                width: 22px;
                margin: 26px 0 26px 0;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: {primary};
                border-radius: 6px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {primary_light};
            }}
            QScrollBar::add-line:vertical {{
                background: #3a3a3a;
                height: 26px;
                subcontrol-position: bottom;
                subcontrol-origin: margin;
                border-radius: 4px;
            }}
            QScrollBar::sub-line:vertical {{
                background: #3a3a3a;
                height: 26px;
                subcontrol-position: top;
                subcontrol-origin: margin;
                border-radius: 4px;
            }}
            QScrollBar::up-arrow:vertical {{
                width: 10px;
                height: 10px;
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                border-bottom: 10px solid {primary};
            }}
            QScrollBar::down-arrow:vertical {{
                width: 10px;
                height: 10px;
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                border-top: 10px solid {primary};
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)

    def update_button_styles(self):
        """Update button styling"""
        # Update add button
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        
        self.add_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {primary_light}, stop:1 {primary});
                border: 3px solid {primary};
                border-radius: 10px;
                color: black;
                font-weight: bold;
                padding: 15px 25px;
                min-width: 180px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f8d547, stop:1 {primary_light});
            }}
        """)
        
        # Update other buttons
        self.refresh_btn.setStyleSheet(self.get_enhanced_button_style(False))
        self.save_btn.setStyleSheet(self.get_enhanced_button_style(False))

    def update_status_label_style(self):
        """Update status label styling"""
        primary = theme_manager.get("primary_color")
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {primary};
                font-size: 13px;
                font-weight: bold;
                padding: 5px;
                background: transparent;
                border: none;
            }}
        """)

    def init_ui(self):
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(100, 25, 40, 10)
        
        # Main container with enhanced styling
        self.main_frame = QFrame()
        self.update_main_frame_style()
        
        frame_layout = QVBoxLayout(self.main_frame)
        frame_layout.setSpacing(5)
        
        self.create_enhanced_scroll_area(frame_layout)
        self.create_enhanced_control_buttons(frame_layout)
        
        self.layout.addWidget(self.main_frame)
        self.setLayout(self.layout)

    def create_enhanced_scroll_area(self, parent_layout):
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMaximumHeight(520)
        self.update_scroll_area_style()
        
        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.scenes_container = QWidget()
        self.scenes_container.setMinimumWidth(900)
        self.scenes_layout = QVBoxLayout(self.scenes_container)
        self.scenes_layout.setContentsMargins(10, 10, 10, 10)
        self.scenes_layout.setSpacing(4)
        self.scenes_layout.addStretch()
        
        main_layout.addWidget(self.scenes_container)
        self.scroll.setWidget(main_container)
        parent_layout.addWidget(self.scroll)

    def create_enhanced_control_buttons(self, parent_layout):
        btn_container = QWidget()
        btn_container.setFixedHeight(80)
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, 5, 0, 5)
        btn_layout.setSpacing(20)
        
        # Add Scene button
        self.add_btn = QPushButton("✨ Add New Scene")
        self.add_btn.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self.add_btn.clicked.connect(lambda: self.add_scene())
        
        # Status indicator with word wrap enabled
        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)  # Enable text wrapping
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)  # Center align
        primary = theme_manager.get("primary_color")
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {primary};
                font-size: 13px;
                font-weight: bold;
                padding: 5px;
                background: transparent;
                border: none;
            }}
        """)
        
        # Action buttons (removed emojis)
        self.refresh_btn = QPushButton("Refresh from Backend")
        self.refresh_btn.clicked.connect(lambda: self.refresh_from_backend())
        
        self.save_btn = QPushButton("Save Configuration")
        self.save_btn.clicked.connect(lambda: self.save_config())
        
        # Apply initial styling
        self.update_button_styles()
        
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.status_label, 1)  # Give status label stretch factor
        btn_layout.addStretch()
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addWidget(self.save_btn)
        
        parent_layout.addWidget(btn_container)

    def get_enhanced_button_style(self, primary=False):
        if primary:
            primary_color = theme_manager.get("primary_color")
            primary_light = theme_manager.get("primary_light")
            return f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {primary_light}, stop:1 {primary_color});
                    border: 3px solid {primary_color};
                    border-radius: 10px;
                    color: black;
                    font-weight: bold;
                    padding: 15px 25px;
                    font-size: 16px;
                    min-width: 150px;
                }}
            """
        else:
            primary = theme_manager.get("primary_color")
            return f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #4a4a4a, stop:1 #2a2a2a);
                    border: 2px solid #666;
                    border-radius: 8px;
                    color: #ccc;
                    font-weight: bold;
                    padding: 12px 20px;
                    font-size: 14px;
                    min-width: 140px;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #5a5a5a, stop:1 #3a3a3a);
                    border: 2px solid {primary};
                    color: {primary};
                }}
            """

    @error_boundary
    def request_audio_files(self):
        primary = theme_manager.get("primary_color")
        
        # Check if WebSocket is connected
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
        
        # Update existing scene rows with fallback audio files
        self.update_audio_files()

    @error_boundary
    def refresh_from_backend(self):
        """Refresh scenes, audio files, and Bottango scenes from backend"""
        primary = theme_manager.get("primary_color")
        self.update_status("Refreshing from backend...", primary)
        
        # Initialize refresh tracking
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
        
        # Send refresh request (backend will return audio + Bottango scenes)
        refresh_success = self.send_websocket_message("refresh_backend")
        
        # Also request scenes list separately
        scenes_success = self.send_websocket_message("get_scenes")
        
        if not (refresh_success or scenes_success):
            self.update_status("Backend unavailable - keeping local data", "orange")
            self.logger.warning("Failed to refresh from backend")

    def update_status(self, message, color=None):
        """Update the status indicator"""
        if color is None:
            color = theme_manager.get("primary_color")
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {color};
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                background: transparent;
                border: none;
            }}
        """)

    @error_boundary
    def handle_message(self, message: str):
        try:
            msg = json.loads(message)
            msg_type = msg.get("type")
            
            green = theme_manager.get("green")
            red = theme_manager.get("red")
            
            if msg_type == "scene_list":
                scenes = msg.get("scenes", [])
                if scenes:
                    self.scenes_data = scenes
                    self.update_scene_rows()
                    # Update refresh tracking
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
                    for row in self.scene_rows:
                        row.audio_files = files
                        current_selection = row.audio_file_combo.currentText()
                        row.audio_file_combo.clear()
                        row.audio_file_combo.addItems(files)
                        if current_selection in files:
                            row.audio_file_combo.setCurrentText(current_selection)
                        elif files:
                            row.audio_file_combo.setCurrentIndex(0)
                    # Update refresh tracking
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
                # Handle combined refresh response (audio + Bottango scenes)
                files = msg.get("audio_files", [])
                bottango_scenes = msg.get("bottango_scenes", [])
                
                # Update audio files
                if files:
                    self.audio_files = files
                    self.logger.info(f"Loaded {len(files)} audio files from backend")
                    for row in self.scene_rows:
                        row.audio_files = files
                        current_selection = row.audio_file_combo.currentText()
                        row.audio_file_combo.clear()
                        row.audio_file_combo.addItems(files)
                        if current_selection in files:
                            row.audio_file_combo.setCurrentText(current_selection)
                        elif files:
                            row.audio_file_combo.setCurrentIndex(0)
                    
                # Update Bottango scenes
                if bottango_scenes:
                    self.bottango_scenes = bottango_scenes
                    self.logger.info(f"Loaded {len(bottango_scenes)} Bottango scenes from backend")
                    # Update all scene rows with new Bottango scenes
                    for row in self.scene_rows:
                        row.update_bottango_scenes(bottango_scenes)
                
                # Update refresh tracking
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
                    QMessageBox.information(self, "Saved", "Scenes saved successfully to backend.")
                    self.update_status("Saved successfully", green)
                    self.scenes_updated.emit()
                else:
                    error = msg.get("error", "Unknown error")
                    QMessageBox.critical(self, "Error", f"Failed to save to backend: {error}")
                    self.update_status("Save failed", red)

            elif msg_type == "bottango_import_complete":
                converted = msg.get("converted", 0)
                bottango_scenes = msg.get("bottango_scenes", [])
                error = msg.get("error")
                if error:
                    self.update_status(f"Import failed: {error}", red)
                elif converted > 0:
                    if bottango_scenes:
                        self.bottango_scenes = bottango_scenes
                        for row in self.scene_rows:
                            row.update_bottango_scenes(bottango_scenes)
                    self.update_status(f"Imported {converted} scene(s)", green)
                else:
                    if bottango_scenes:
                        self.bottango_scenes = bottango_scenes
                        for row in self.scene_rows:
                            row.update_bottango_scenes(bottango_scenes)
                    self.update_status(f"No new files to import ({len(bottango_scenes)} scene(s) available)", green)
                    
        except Exception as e:
            red = theme_manager.get("red")
            self.logger.error(f"Failed to handle message: {e}")
            self.update_status("Communication error", red)

    def check_refresh_completion(self):
        """Check if refresh is complete and update status accordingly"""
        if not hasattr(self, 'refresh_status'):
            return
        
        green = theme_manager.get("green")
        red = theme_manager.get("red")
        
        # Check if all are complete
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
            
            # Clear refresh tracking
            del self.refresh_status

    @error_boundary
    def load_local_config(self):
        """Load from standardized path that matches backend"""
        # Try primary config path first (matches backend)
        config = config_manager.get_config("resources/configs/scenes_config.json")
        if isinstance(config, list) and config:
            self.scenes_data = config
            self.update_scene_rows()
            primary = theme_manager.get("primary_color")
            self.update_status(f"Loaded {len(self.scenes_data)} scenes from local cache", primary)
            self.logger.debug(f"Loaded {len(self.scenes_data)} scenes from resources/configs/scenes_config.json")
            return
        
        # No config found - start with empty
        self.scenes_data = []
        self.update_scene_rows()
        primary = theme_manager.get("primary_color")
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
                "bottango_scene": scene.get("bottango_scene", ""),  # New Bottango reference
                "duration": scene.get("duration", 1.0),
                "delay": scene.get("delay", 0)
            }
            converted.append(new_scene)
        return converted

    @error_boundary
    def update_scene_rows(self):
        """Update the enhanced accordion scene rows"""
        # Clear existing rows
        for row in self.scene_rows:
            row.setParent(None)
        self.scene_rows.clear()

        sorted_scenes = sorted(self.scenes_data, key=lambda s: s.get("label", "").lower())

        # Create new enhanced rows with proper parent reference
        for i, scene_data in enumerate(sorted_scenes):
            scene_row = EnhancedSceneRow(scene_data, self.audio_files, self.bottango_scenes, i, self)
            self.scene_rows.append(scene_row)
            # Insert before the stretch
            self.scenes_layout.insertWidget(self.scenes_layout.count() - 1, scene_row)

    @error_boundary
    def add_scene(self):
        new_scene = {
            "label": f"New Scene {len(self.scenes_data) + 1}",
            "emoji": "🎭",
            "categories": [],
            "audio_enabled": False,
            "audio_file": "",
            "script_enabled": False,
            "bottango_scene": "",  # Reference to Bottango scene
            "duration": 2.0,
            "delay": 0
        }
        
        self.scenes_data.append(new_scene)
        
        # Create and add new enhanced row with proper parent reference
        scene_row = EnhancedSceneRow(new_scene, self.audio_files, self.bottango_scenes, len(self.scene_rows), self)
        self.scene_rows.append(scene_row)
        self.scenes_layout.insertWidget(self.scenes_layout.count() - 1, scene_row)
        
        scene_row.collapse()
        primary = theme_manager.get("primary_color")
        self.update_status(f"Added new scene", primary)

    @error_boundary
    def delete_scene_row(self, row_index):
        """Delete a scene row by index"""
        if 0 <= row_index < len(self.scene_rows):
            scene_row = self.scene_rows[row_index]
            scene_name = scene_row.name_edit.text() or f"Scene {row_index + 1}"
            
            reply = QMessageBox.question(
                self, "Delete Scene", 
                f"Are you sure you want to delete '{scene_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Remove from data and UI
                if row_index < len(self.scenes_data):
                    del self.scenes_data[row_index]
                
                scene_row.setParent(None)
                del self.scene_rows[row_index]
                
                # Update row indices for remaining rows
                for i, row in enumerate(self.scene_rows):
                    row.row_index = i
                
                primary = theme_manager.get("primary_color")
                self.update_status(f"Deleted scene: {scene_name}", primary)
                self.logger.info(f"Deleted scene: {scene_name} (index: {row_index})")

    @error_boundary
    def test_scene_data(self, scene_data):
        """Test a scene with given data"""
        scene_name = scene_data.get("label", "Test Scene")
        self.logger.info(f"Testing scene: {scene_name}")
        primary = theme_manager.get("primary_color")
        self.update_status(f"Testing: {scene_name}", primary)
        
        # Send test command to backend
        test_data = {
            "type": "test_scene",
            "scene": scene_data
        }
        success = self.send_websocket_message(test_data)
        if not success:
            red = theme_manager.get("red")
            self.update_status(f"Failed to test {scene_name}", red)

    @error_boundary
    def save_config(self):
        """Save configuration from accordion rows"""
        primary = theme_manager.get("primary_color")
        red = theme_manager.get("red")
        
        self.update_status("Validating configuration...", primary)
        
        # Validate unique names and collect data
        names = []
        scene_data = []
        
        for row in self.scene_rows:
            scene = row.get_scene_data()
            names.append(scene["label"])
            scene_data.append(scene)
        
        # Check for unique names
        if len(names) != len(set(names)):
            QMessageBox.critical(self, "Error", "Scene names must be unique.")
            self.update_status("Validation failed: Duplicate names", red)
            return
        
        # Check for empty names
        if any(not name.strip() for name in names):
            QMessageBox.critical(self, "Error", "All scenes must have names.")
            self.update_status("Validation failed: Empty names", red)
            return
        
        self.update_status("Saving configuration...", primary)
        
        # Save locally first using standardized path
        success = config_manager.save_config("resources/configs/scenes_config.json", scene_data)
        if not success:
            QMessageBox.critical(self, "Error", "Failed to save local configuration.")
            self.update_status("Local save failed", red)
            return
        
        # Update internal data
        self.scenes_data = scene_data
        
        # Send to backend
        save_data = {
            "type": "save_scenes", 
            "scenes": scene_data
        }
        backend_success = self.send_websocket_message("save_scenes", scenes=scene_data)
        
        if backend_success:
            self.logger.info("Scene configuration saved locally and sent to backend")
            self.update_status("Saved locally, waiting for backend...", primary)
        else:
            QMessageBox.warning(self, "Warning", 
                "Scenes saved locally but could not sync to backend. "
                "Backend will use local file on restart.")
            self.update_status("Saved locally only", "orange")
            # Still emit signal since local save succeeded
            self.scenes_updated.emit()

    def reload_scenes(self):
        """Public method to reload scenes (called by HomeScreen)"""
        self.request_scenes()

    @error_boundary
    def update_audio_files(self):
        """Update audio files in all existing rows"""
        for row in self.scene_rows:
            row.audio_files = self.audio_files
            current_selection = row.audio_file_combo.currentText()
            row.audio_file_combo.clear()
            row.audio_file_combo.addItems(self.audio_files)
            if current_selection in self.audio_files:
                row.audio_file_combo.setCurrentText(current_selection)
            elif self.audio_files:
                row.audio_file_combo.setCurrentIndex(0)

    def get_scene_summary(self):
        """Get summary of current scene configuration"""
        return {
            "total_scenes": len(self.scenes_data),
            "categories": list(set(cat for scene in self.scenes_data for cat in scene.get("categories", []))),
            "audio_scenes": len([s for s in self.scenes_data if s.get("audio_enabled")]),
            "script_scenes": len([s for s in self.scenes_data if s.get("script_enabled")])
        }