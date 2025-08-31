import json
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QCheckBox, QComboBox, QMessageBox,
    QLineEdit, QDoubleSpinBox, QSpinBox, QListWidget, QListWidgetItem,
    QHeaderView, QTableWidget, QTableWidgetItem, QFrame, QDialog,
    QDialogButtonBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QRect, QParallelAnimationGroup
from PyQt6.QtGui import QFont, QPainter, QPalette
from widgets.base_screen import BaseScreen
from core.config_manager import config_manager
from core.utils import error_boundary

YELLOW = "#e1a014"
YELLOW_LIGHT = "#f4c430"
GREY = "#888"
GREY_LIGHT = "#aaa"
GREEN = "#44bb44"
RED = "#cc4444"
DARK_BG = "#1a1a1a"
CARD_BG = "#252525"
EXPANDED_BG = "#2a2a2a"

# Category definitions with emojis
CATEGORIES = {
    "Happy": "😊",
    "Sad": "😢", 
    "Curious": "🤔",
    "Angry": "😠",
    "Surprise": "😲",
    "Love": "❤️",
    "Calm": "😌",
    "Sound Effect": "🔊",
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
        self.display_label.setStyleSheet(f"""
            QLabel {{
                background-color: {CARD_BG};
                border: 2px solid {YELLOW};
                border-radius: 6px;
                color: {YELLOW};
                padding: 10px 15px;
                font-size: 14px;
                font-weight: 500;
            }}
            QLabel:hover {{
                background-color: #2d2d2d;
                border-color: {YELLOW_LIGHT};
                color: {YELLOW_LIGHT};
            }}
        """)
        self.display_label.setMinimumHeight(45)
        self.display_label.mousePressEvent = self.open_selector
        
        layout.addWidget(self.display_label)
        
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
        
    def setup_ui(self):
        self.setWindowTitle("Select Categories")
        self.setModal(True)
        self.setFixedSize(350, 450)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: #222;
                border: 3px solid {YELLOW};
                border-radius: 12px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Header
        header = QLabel("Select Categories:")
        header.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        header.setStyleSheet(f"color: {YELLOW}; padding: 15px;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)
        
        # Scrollable area for categories
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 2px solid {GREY};
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
            checkbox.setStyleSheet(f"""
                QCheckBox {{
                    color: {YELLOW};
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
                    background-color: {YELLOW};
                    border: 2px solid {YELLOW};
                    border-radius: 4px;
                }}
                QCheckBox::indicator:unchecked {{
                    background-color: #555;
                    border: 2px solid {GREY};
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
        button_box.setStyleSheet(f"""
            QDialogButtonBox QPushButton {{
                background-color: {CARD_BG};
                border: 2px solid {GREY};
                border-radius: 6px;
                color: {YELLOW};
                font-weight: bold;
                padding: 12px 24px;
                font-size: 16px;
                min-width: 80px;
            }}
            QDialogButtonBox QPushButton:hover {{
                background-color: #333;
                border: 2px solid {YELLOW};
                color: {YELLOW_LIGHT};
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

class EnhancedSceneRow(QWidget):
    """Enhanced expandable scene row with better styling and layout"""
    
    def __init__(self, scene_data, audio_files, row_index, parent_screen):
        super().__init__()
        self.scene_data = scene_data
        self.audio_files = audio_files
        self.row_index = row_index
        self.parent_screen = parent_screen  # FIXED: Direct reference to parent
        self.is_expanded = False
        self.details_widget = None
        self.animation_group = None
        self.setup_ui()
    
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
    
    def create_main_row(self):
        self.main_row = QWidget()
        self.main_row.setFixedHeight(70)
        self.main_row.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {CARD_BG}, stop:1 #1f1f1f);
                border: 2px solid {GREY};
                border-radius: 8px;
                margin: 2px;
            }}
            QWidget:hover {{
                border: 2px solid {YELLOW};
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a2a2a, stop:1 #232323);
            }}
        """)
        
        # Make the main row clickable
        self.main_row.mousePressEvent = self.toggle_expansion
        
        layout = QHBoxLayout(self.main_row)
        layout.setContentsMargins(10, 15, 10, 15)
        layout.setSpacing(15)
        
        # Expand/collapse indicator
        self.expand_indicator = QLabel("▶")
        self.expand_indicator.setStyleSheet(f"""
            QLabel {{
                color: {YELLOW};
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
        self.name_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {CARD_BG};
                border: 2px solid {YELLOW};
                border-radius: 6px;
                color: {YELLOW};
                padding: 5px 15px;
                font-size: 16px;
                font-weight: bold;
            }}
            QLineEdit:focus {{
                border-color: {YELLOW_LIGHT};
                background-color: #2a2a2a;
            }}
        """)
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
        self.audio_indicator.setStyleSheet(f"""
            QLabel {{
                font-size: 14px;
                border: 2px solid #666;
                background: {YELLOW if audio_enabled else 'transparent'};
                color: {'white' if audio_enabled else GREY};
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
                background: {YELLOW if script_enabled else 'transparent'};
                color: {'white' if script_enabled else GREY};
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
        self.test_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {GREEN}, stop:1 #2d8f2d);
                border: 2px solid {GREEN};
                border-radius: 6px;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 8px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #55dd55, stop:1 {GREEN});
            }}
        """)
        self.test_btn.setFixedSize(70, 35)
        self.test_btn.clicked.connect(self.test_scene)
        actions_layout.addWidget(self.test_btn)
        
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {RED}, stop:1 #8b2635);
                border: 2px solid {RED};
                border-radius: 6px;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 8px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ee5555, stop:1 {RED});
            }}
        """)
        self.delete_btn.setFixedSize(80, 35)
        self.delete_btn.clicked.connect(self.delete_scene)
        actions_layout.addWidget(self.delete_btn)
        
        layout.addLayout(actions_layout)
        self.main_layout.addWidget(self.main_row)

# CONTINUED FROM PART 1: EnhancedSceneRow methods
    
    def create_details_row(self):
        self.details_widget = QWidget()
        self.details_widget.setFixedHeight(75)
        self.details_widget.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {EXPANDED_BG}, stop:1 {DARK_BG});
                margin: 2px;
                margin-top: 0px;
            }}
        """)
        
        layout = QHBoxLayout(self.details_widget)
        layout.setContentsMargins(20, 15, 25, 15)
        layout.setSpacing(20)
        
        # Audio section
        self.audio_cb = QCheckBox("Audio:")
        self.audio_cb.setChecked(self.scene_data.get("audio_enabled", False))
        self.audio_cb.setStyleSheet(f"""
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
                background-color: {YELLOW};
                border: 2px solid {YELLOW};
                border-radius: 3px;
            }}
            QCheckBox::indicator:unchecked {{
                background-color: #555;
                border: 2px solid {GREY};
                border-radius: 3px;
            }}
        """)
        
        # Audio file dropdown
        self.audio_file_combo = QComboBox()
        self.audio_file_combo.addItems(self.audio_files)
        current_audio = self.scene_data.get("audio_file", "")
        if current_audio and current_audio in self.audio_files:
            self.audio_file_combo.setCurrentText(current_audio)
        elif self.audio_files:
            self.audio_file_combo.setCurrentIndex(0)
        
        self.audio_file_combo.setEnabled(self.audio_cb.isChecked())
        self.audio_file_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {CARD_BG};
                border: 2px solid {YELLOW};
                border-radius: 4px;
                color: {YELLOW};
                padding: 4px 8px;
                font-size: 12px;
                min-height: 25px;
                min-width: 200px;
            }}
            QComboBox:disabled {{
                background-color: #333;
                border-color: {GREY};
                color: {GREY};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid {YELLOW};
                margin-right: 5px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {CARD_BG};
                border: 2px solid {YELLOW};
                color: {YELLOW};
                selection-background-color: {YELLOW};
                selection-color: black;
            }}
        """)
        
        self.audio_cb.stateChanged.connect(
            lambda state: self.audio_file_combo.setEnabled(state == Qt.CheckState.Checked)
        )
        self.audio_cb.stateChanged.connect(self.update_indicators)
        
        layout.addWidget(self.audio_cb)
        layout.addWidget(self.audio_file_combo)
        
        # Script section
        self.script_cb = QCheckBox("Script:")
        self.script_cb.setChecked(self.scene_data.get("script_enabled", False))
        self.script_cb.setStyleSheet(f"""
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
                background-color: {YELLOW};
                border: 2px solid {YELLOW};
                border-radius: 3px;
            }}
            QCheckBox::indicator:unchecked {{
                background-color: #555;
                border: 2px solid {GREY};
                border-radius: 3px;
            }}
        """)
        
        # Script input
        self.script_input = QLineEdit()
        script_value = self.scene_data.get("script_name", "")
        if script_value and script_value != 0:
            self.script_input.setText(str(script_value))
        else:
            self.script_input.setText("")
        
        self.script_input.setPlaceholderText("Script #")
        self.script_input.setEnabled(self.script_cb.isChecked())
        self.script_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {CARD_BG};
                border: 2px solid {YELLOW};
                border-radius: 4px;
                color: {YELLOW};
                padding: 4px 8px;
                font-size: 12px;
                min-height: 25px;
                max-width: 80px;
            }}
            QLineEdit:disabled {{
                background-color: #333;
                border-color: {GREY};
                color: {GREY};
            }}
            QLineEdit::placeholder {{
                color: {GREY};
            }}
        """)
        
        def update_script_input_enabled():
            enabled = self.script_cb.isChecked()
            self.script_input.setEnabled(enabled)
        
        self.script_input.textChanged.connect(self.validate_script_input)
        self.script_cb.stateChanged.connect(lambda: update_script_input_enabled())
        self.script_cb.stateChanged.connect(self.update_indicators)
        
        layout.addWidget(self.script_cb)
        layout.addWidget(self.script_input)
        
        # Duration section
        duration_label = QLabel("Duration:")
        duration_label.setStyleSheet("color: white; font-weight: bold; font-size: 13px; min-width: 65px; border: none; background: transparent;")
        
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(0.1, 99.9)
        self.duration_spin.setSingleStep(0.1)
        self.duration_spin.setValue(self.scene_data.get("duration", 1.0))
        self.duration_spin.setSuffix("s")
        self.duration_spin.setStyleSheet(f"""
            QDoubleSpinBox {{
                background-color: {CARD_BG};
                border: 2px solid {YELLOW};
                border-radius: 4px;
                color: white;
                padding: 4px 6px 8px 6px;
                font-size: 12px;
                min-height: 25px;
                max-width: 70px;
            }}
        """)
        
        layout.addWidget(duration_label)
        layout.addWidget(self.duration_spin)
        
        # Delay section
        delay_label = QLabel("Delay:")
        delay_label.setStyleSheet("color: white; font-weight: bold; font-size: 13px; min-width: 45px; border: none; background: transparent;")
        
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 10000)
        self.delay_spin.setValue(self.scene_data.get("delay", 0))
        self.delay_spin.setSuffix("ms")
        self.delay_spin.setEnabled(self.audio_cb.isChecked() and self.script_cb.isChecked())
        self.delay_spin.setStyleSheet(f"""
            QSpinBox {{
                background-color: {CARD_BG};
                border: 2px solid {YELLOW};
                border-radius: 4px;
                color: white;
                padding: 4px 6px 8px 6px;
                font-size: 12px;
                min-height: 25px;
                max-width: 70px;
            }}
        """)
        
        def update_delay_enabled():
            self.delay_spin.setEnabled(self.audio_cb.isChecked() and self.script_cb.isChecked())
        
        self.audio_cb.stateChanged.connect(update_delay_enabled)
        self.script_cb.stateChanged.connect(update_delay_enabled)
        
        layout.addWidget(delay_label)
        layout.addWidget(self.delay_spin)
        layout.addStretch()
        
        self.main_layout.addWidget(self.details_widget)
    
    def validate_script_input(self, text):
        """Only allow digits in script input"""
        if text and not text.isdigit():
            filtered_text = ''.join(c for c in text if c.isdigit())
            self.script_input.setText(filtered_text)
    
    def update_indicators(self):
        """Update the type indicators based on checkbox states"""
        audio_enabled = self.audio_cb.isChecked()
        script_enabled = self.script_cb.isChecked()
        
        self.audio_indicator.setText("🎵 Audio" if audio_enabled else "Audio")
        self.audio_indicator.setStyleSheet(f"""
            QLabel {{
                font-size: 14px;
                border: 2px solid {'#666' if not audio_enabled else YELLOW};
                background: {YELLOW if audio_enabled else 'transparent'};
                color: {'white' if audio_enabled else GREY};
                padding: 4px;
                font-weight: bold;
            }}
        """)
        
        self.script_indicator.setText("🎬 Script" if script_enabled else "Script")
        self.script_indicator.setStyleSheet(f"""
            QLabel {{
                font-size: 14px;
                border: 2px solid {'#666' if not script_enabled else YELLOW};
                background: {YELLOW if script_enabled else 'transparent'};
                color: {'white' if script_enabled else GREY};
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
            self.expand_indicator.setStyleSheet(f"""
                QLabel {{
                    color: {YELLOW_LIGHT};
                    font-weight: bold;
                    font-size: 18px;
                    border: none;
                    background: transparent;
                }}
            """)
            self.details_widget.show()
            
            self.main_row.setStyleSheet(f"""
                QWidget {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {CARD_BG}, stop:1 #1f1f1f);
                    border: 2px solid {YELLOW};
                    border-bottom: 1px solid {GREY};
                    border-radius: 8px 8px 0px 0px;
                    margin: 2px;
                    margin-bottom: 0px;
                }}
            """)
    
    def collapse(self):
        """Collapse to hide details"""
        if self.is_expanded:
            self.is_expanded = False
            self.expand_indicator.setText("▶")
            self.expand_indicator.setStyleSheet(f"""
                QLabel {{
                    color: {YELLOW};
                    font-weight: bold;
                    font-size: 18px;
                    border: none;
                    background: transparent;
                }}
            """)
            self.details_widget.hide()
            
            self.main_row.setStyleSheet(f"""
                QWidget {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {CARD_BG}, stop:1 #1f1f1f);
                    border: 2px solid {GREY};
                    border-radius: 8px;
                    margin: 2px;
                }}
                QWidget:hover {{
                    border: 2px solid {YELLOW};
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #2a2a2a, stop:1 #232323);
                }}
            """)
    
    def test_scene(self):
        """Test this scene"""
        scene_data = self.get_scene_data()
        self.parent_screen.test_scene_data(scene_data)  # FIXED: Use direct reference
    
    def delete_scene(self):
        """Delete this scene"""
        self.parent_screen.delete_scene_row(self.row_index)  # FIXED: Use direct reference
    
    def get_scene_data(self):
        """Extract current scene data from widgets"""
        script_value = self.script_input.text().strip()
        if script_value.isdigit():
            script_num = int(script_value)
        else:
            script_num = None
        
        audio_file = self.audio_file_combo.currentText() if self.audio_cb.isChecked() else ""
        
        return {
            "label": self.name_edit.text().strip(),
            "emoji": "🎭",  # Default emoji
            "categories": self.category_selector.get_selected_categories(),
            "audio_enabled": self.audio_cb.isChecked(),
            "audio_file": audio_file,
            "script_enabled": self.script_cb.isChecked(),
            "script_name": script_num if (self.script_cb.isChecked() and script_num is not None) else None,
            "duration": self.duration_spin.value(),
            "delay": self.delay_spin.value() if (self.audio_cb.isChecked() and self.script_cb.isChecked()) else 0
        }

class SceneScreen(BaseScreen):
    """Interface for managing emotion scenes and audio mappings with enhanced accordion layout"""
    
    scenes_updated = pyqtSignal()  # Signal to notify HomeScreen of changes

    def _setup_screen(self):
        self.setFixedWidth(1200)
        self.scenes_data = []
        self.audio_files = []
        self.scene_rows = []
        
        self.init_ui()
        
        if self.websocket:
            self.websocket.textMessageReceived.connect(self.handle_message)
        
        # FIXED: Load from local cache first, then get audio files from backend
        self.load_local_config()
        self.request_audio_files()

    def init_ui(self):
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(100, 25, 40, 10)
        
        # Main container with enhanced styling
        self.main_frame = QFrame()
        self.main_frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a1a, stop:1 #0f0f0f);
                border: 2px solid {YELLOW};
                border-radius: 15px;
                padding: 10px;
            }}
        """)
        
        frame_layout = QVBoxLayout(self.main_frame)
        frame_layout.setSpacing(5)
        
        self.create_enhanced_scroll_area(frame_layout)
        self.create_enhanced_control_buttons(frame_layout)
        
        self.layout.addWidget(self.main_frame)
        self.setLayout(self.layout)

    def create_enhanced_scroll_area(self, parent_layout):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(520)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 3px solid {GREY};
                border-radius: 12px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1e1e1e, stop:1 #141414);
            }}
            QScrollArea::corner {{
                background: {DARK_BG};
            }}
            QScrollBar:vertical {{
                background: {DARK_BG};
                width: 16px;
                border-radius: 8px;
            }}
            QScrollBar::handle:vertical {{
                background: {YELLOW};
                border-radius: 8px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {YELLOW_LIGHT};
            }}
        """)
        
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
        scroll.setWidget(main_container)
        parent_layout.addWidget(scroll)

    def create_enhanced_control_buttons(self, parent_layout):
        btn_container = QWidget()
        btn_container.setFixedHeight(80)
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, 5, 0, 5)
        btn_layout.setSpacing(20)
        
        # Add Scene button
        self.add_btn = QPushButton("✨ Add New Scene")
        self.add_btn.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self.add_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {YELLOW_LIGHT}, stop:1 {YELLOW});
                border: 3px solid {YELLOW};
                border-radius: 10px;
                color: black;
                font-weight: bold;
                padding: 15px 25px;
                min-width: 180px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f8d547, stop:1 {YELLOW_LIGHT});
            }}
        """)
        self.add_btn.clicked.connect(lambda: self.add_scene())
        
        # Status indicator
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {GREEN};
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                background: transparent;
                border: none;
            }}
        """)
        
        # Action buttons
        self.refresh_btn = QPushButton("🔄 Refresh from Backend")
        self.refresh_btn.setStyleSheet(self.get_enhanced_button_style(False))

        self.refresh_btn.clicked.connect(lambda: self.refresh_from_backend())
        
        self.save_btn = QPushButton("💾 Save Configuration")
        self.save_btn.setStyleSheet(self.get_enhanced_button_style(False))
        self.save_btn.clicked.connect(lambda: self.save_config())
        
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.status_label)
        btn_layout.addStretch()
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addWidget(self.save_btn)
        
        parent_layout.addWidget(btn_container)

    def get_enhanced_button_style(self, primary=False):
        if primary:
            return f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {YELLOW_LIGHT}, stop:1 {YELLOW});
                    border: 3px solid {YELLOW};
                    border-radius: 10px;
                    color: black;
                    font-weight: bold;
                    padding: 15px 25px;
                    font-size: 16px;
                    min-width: 150px;
                }}
            """
        else:
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
                    border: 2px solid {YELLOW};
                    color: {YELLOW};
                }}
            """

    @error_boundary
    def request_audio_files(self):
        self.update_status("Requesting audio files...", YELLOW)
        success = self.send_websocket_message("get_audio_files")
        if not success:
            self.logger.warning("Failed to request audio files - using fallback list")
            self.update_status("Using fallback audio list", "orange")
            self.audio_files = [
                "Call1-8d855208-7523-4181-ba90-0844bd0386e3 (1).MP3",
                "SPK1950 - Spark Spotify 30sec Radio Dad Rock -14LKFS Radio Mix 05-08-25.mp3",
                "Audio-clip-_CILW-2022_-Goodbye-I_m-off-now.mp3",
                "Audio-clip-_CILW-2022_-Greetings.mp3",
                "Audio-clip-_CILW-2022_-Thank-you.mp3"
            ]


    @error_boundary
    def refresh_from_backend(self):
        """Refresh both scenes and audio files from backend in parallel"""
        self.update_status("Refreshing from backend...", YELLOW)
        
        # Initialize refresh tracking
        self.refresh_status = {
            "scenes_complete": False,
            "audio_complete": False,
            "scenes_count": 0,
            "audio_count": 0,
            "scenes_success": False,
            "audio_success": False
        }
        
        # Send both requests in parallel
        scenes_success = self.send_websocket_message("get_scenes")
        audio_success = self.send_websocket_message("get_audio_files")
        
        if not (scenes_success or audio_success):
            self.update_status("Backend unavailable - keeping local data", "orange")
            self.logger.warning("Failed to refresh from backend")

    def update_status(self, message, color=GREEN):
        """Update the status indicator"""
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
                        self.update_status(f"Loaded {len(scenes)} scenes from backend", GREEN)
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
                        self.update_status(f"Loaded {len(files)} audio files", GREEN)
                else:
                    self.logger.warning("No audio files received from backend")
                    if hasattr(self, 'refresh_status'):
                        self.refresh_status["audio_complete"] = True
                        self.refresh_status["audio_success"] = False
                        self.check_refresh_completion()
                    else:
                        self.update_status("No audio files from backend", "orange")

                    
            elif msg_type == "scenes_saved":
                success = msg.get("success", False)
                if success:
                    QMessageBox.information(self, "Saved", "Scenes saved successfully to backend.")
                    self.update_status("Saved successfully", GREEN)
                    self.scenes_updated.emit()
                else:
                    error = msg.get("error", "Unknown error")
                    QMessageBox.critical(self, "Error", f"Failed to save to backend: {error}")
                    self.update_status("Save failed", RED)
                    
        except Exception as e:
            self.logger.error(f"Failed to handle message: {e}")
            self.update_status("Communication error", RED)

    def check_refresh_completion(self):
        """Check if refresh is complete and update status accordingly"""
        if not hasattr(self, 'refresh_status'):
            return
        
        # Check if both are complete
        if self.refresh_status["scenes_complete"] and self.refresh_status["audio_complete"]:
            scenes_count = self.refresh_status["scenes_count"]
            audio_count = self.refresh_status["audio_count"]
            scenes_ok = self.refresh_status["scenes_success"]
            audio_ok = self.refresh_status["audio_success"]
            
            if scenes_ok and audio_ok:
                self.update_status(f"Loaded {scenes_count} scenes and {audio_count} audio files", GREEN)
            elif scenes_ok:
                self.update_status(f"Loaded {scenes_count} scenes, audio failed", "orange")
            elif audio_ok:
                self.update_status(f"Scenes failed, loaded {audio_count} audio files", "orange")
            else:
                self.update_status("Failed to load scenes and audio files", RED)
            
            # Clear refresh tracking
            del self.refresh_status

    @error_boundary
    def load_local_config(self):
        """FIXED: Load from standardized path that matches backend"""
        # Try primary config path first (matches backend)
        config = config_manager.get_config("resources/configs/scenes_config.json")
        if isinstance(config, list) and config:
            self.scenes_data = config
            self.update_scene_rows()
            self.update_status(f"Loaded {len(self.scenes_data)} scenes from local cache", GREEN)
            self.logger.debug(f"Loaded {len(self.scenes_data)} scenes from resources/configs/scenes_config.json")
            return
        
        
        # No config found - start with empty
        self.scenes_data = []
        self.update_scene_rows()
        self.update_status("No local config found - starting empty", YELLOW)
        self.logger.info("No local config found - starting with empty scene list")

    def convert_old_format(self, old_scenes):
        """Convert old emotion_buttons.json format to new scenes.json format"""
        converted = []
        for scene in old_scenes:
            new_scene = {
                "label": scene.get("label", ""),
                "emoji": "🎭",
                "categories": scene.get("categories", []),
                "audio_enabled": scene.get("audio_enabled", False),
                "audio_file": scene.get("audio_file", ""),
                "script_enabled": scene.get("script_enabled", False),
                "script_name": scene.get("script_name", 0),
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
        
        # Create new enhanced rows with proper parent reference
        for i, scene_data in enumerate(self.scenes_data):
            scene_row = EnhancedSceneRow(scene_data, self.audio_files, i, self)  # FIXED: Added self reference
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
            "script_name": 0,
            "duration": 2.0,
            "delay": 0
        }
        
        self.scenes_data.append(new_scene)
        
        # Create and add new enhanced row with proper parent reference
        scene_row = EnhancedSceneRow(new_scene, self.audio_files, len(self.scene_rows), self)  # FIXED: Added self reference
        self.scene_rows.append(scene_row)
        self.scenes_layout.insertWidget(self.scenes_layout.count() - 1, scene_row)
        
        scene_row.collapse()
        self.update_status(f"Added new scene", GREEN)

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
                
                self.update_status(f"Deleted scene: {scene_name}", GREEN)
                self.logger.info(f"Deleted scene: {scene_name} (index: {row_index})")

    @error_boundary
    def test_scene_data(self, scene_data):
        """Test a scene with given data"""
        scene_name = scene_data.get("label", "Test Scene")
        self.logger.info(f"Testing scene: {scene_name}")
        self.update_status(f"Testing: {scene_name}", YELLOW)
        
        # Send test command to backend
        test_data = {
            "type": "test_scene",
            "scene": scene_data
        }
        success = self.send_websocket_message(test_data)
        if not success:
            self.update_status(f"Failed to test {scene_name}", RED)

    @error_boundary
    def save_config(self):
        """Save configuration from accordion rows"""
        self.update_status("Validating configuration...", YELLOW)
        
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
            self.update_status("Validation failed: Duplicate names", RED)
            return
        
        # Check for empty names
        if any(not name.strip() for name in names):
            QMessageBox.critical(self, "Error", "All scenes must have names.")
            self.update_status("Validation failed: Empty names", RED)
            return
        
        self.update_status("Saving configuration...", YELLOW)
        
        # FIXED: Save locally first using standardized path
        success = config_manager.save_config("resources/configs/scenes_config.json", scene_data)
        if not success:
            QMessageBox.critical(self, "Error", "Failed to save local configuration.")
            self.update_status("Local save failed", RED)
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
            self.update_status("Saved locally, waiting for backend...", YELLOW)
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