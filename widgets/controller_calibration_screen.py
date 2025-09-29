"""
WALL-E Control System - Bluetooth Controller Calibration Screen
Wizard-style calibration with game controller visualization
"""

import json
import time
from typing import Dict, Optional, List, Tuple
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QStackedWidget, QProgressBar, QFrame, QGridLayout, QComboBox,
    QSlider, QSpinBox, QGroupBox, QTextEdit, QCheckBox, QLineEdit
)
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPixmap
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRect, QPoint

from core.config_manager import config_manager
from core.logger import get_logger


class ControllerVisualization(QWidget):
    """Game controller visualization widget showing real-time input"""
    
    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 300)
        
        # Controller state
        self.left_stick = QPoint(0, 0)  # -100 to 100 range
        self.right_stick = QPoint(0, 0)
        self.left_trigger = 0.0  # 0.0 to 1.0
        self.right_trigger = 0.0
        self.buttons = {}  # button_name: bool
        self.dpad = {'up': False, 'down': False, 'left': False, 'right': False}
        
        # Raw values for display
        self.raw_values = {}
        self.calibrated_values = {}
        
    def update_controller_state(self, controller_data: Dict):
        """Update controller state from websocket data"""
        # Update sticks (convert from -1.0/1.0 to -100/100 for display)
        self.left_stick.setX(int(controller_data.get('left_stick_x', 0) * 100))
        self.left_stick.setY(int(controller_data.get('left_stick_y', 0) * 100))
        self.right_stick.setX(int(controller_data.get('right_stick_x', 0) * 100))
        self.right_stick.setY(int(controller_data.get('right_stick_y', 0) * 100))
        
        # Update triggers
        self.left_trigger = controller_data.get('left_trigger', 0.0)
        self.right_trigger = controller_data.get('right_trigger', 0.0)
        
        # Update buttons
        button_names = ['button_a', 'button_b', 'button_x', 'button_y', 
                       'shoulder_left', 'shoulder_right', 'button_start', 'button_back']
        for btn in button_names:
            self.buttons[btn] = controller_data.get(btn, False)
        
        # Update D-pad
        for direction in ['up', 'down', 'left', 'right']:
            self.dpad[direction] = controller_data.get(f'dpad_{direction}', False)
        
        # Store raw values for display
        self.raw_values = controller_data.get('raw_values', {})
        self.calibrated_values = controller_data.get('calibrated_values', {})
        
        self.update()
    
    def paintEvent(self, event):
        """Draw the controller visualization"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw background
        painter.fillRect(self.rect(), QColor("#1a1a1a"))
        
        # Controller dimensions
        controller_width = 320
        controller_height = 180
        center_x = self.width() // 2
        center_y = self.height() // 2
        
        # Draw controller outline
        controller_rect = QRect(
            center_x - controller_width // 2,
            center_y - controller_height // 2,
            controller_width,
            controller_height
        )
        
        painter.setPen(QPen(QColor("#444444"), 2))
        painter.setBrush(QBrush(QColor("#2d2d2d")))
        painter.drawRoundedRect(controller_rect, 20, 20)
        
        # Draw joysticks in correct positions
        self._draw_joystick(painter, controller_rect.left() + 90, controller_rect.bottom() - 60, 
                           self.left_stick, "Left Stick")
        self._draw_joystick(painter, controller_rect.right() - 90, controller_rect.center().y() + 10, 
                           self.right_stick, "Right Stick")
        
        # Draw D-pad on upper left
        self._draw_dpad(painter, controller_rect.left() + 90, controller_rect.center().y() - 20)
        
        # Draw action buttons (ABXY) on upper right  
        self._draw_action_buttons(painter, controller_rect.right() - 90, controller_rect.center().y() - 20)
        
        # Draw shoulder buttons
        self._draw_shoulder_buttons(painter, controller_rect)
        
        # Draw triggers
        self._draw_triggers(painter, controller_rect)
        
        # Draw value displays if room available
        if self.width() > 500:
            self._draw_value_displays(painter)
    
    def _draw_joystick(self, painter, center_x, center_y, stick_pos, label):
        """Draw a joystick with position indicator"""
        radius = 25
        
        # Draw outer circle
        painter.setPen(QPen(QColor("#555555"), 2))
        painter.setBrush(QBrush(QColor("#333333")))
        painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)
        
        # Draw position indicator
        pos_x = center_x + (stick_pos.x() * radius // 100)
        pos_y = center_y + (stick_pos.y() * radius // 100)
        
        painter.setPen(QPen(QColor("#1e90ff"), 2))
        painter.setBrush(QBrush(QColor("#1e90ff")))
        painter.drawEllipse(pos_x - 6, pos_y - 6, 12, 12)
        
        # Draw crosshairs
        painter.setPen(QPen(QColor("#666666"), 1))
        painter.drawLine(center_x - radius, center_y, center_x + radius, center_y)
        painter.drawLine(center_x, center_y - radius, center_x, center_y + radius)
        
        # Label
        painter.setPen(QPen(QColor("#cccccc")))
        painter.setFont(QFont("Arial", 8))
        painter.drawText(center_x - 30, center_y + radius + 15, label)
    
    def _draw_dpad(self, painter, center_x, center_y):
        """Draw simple D-pad cross shape"""
        painter.setPen(QPen(QColor("#555555"), 2))
        painter.setBrush(QBrush(QColor("#444444")))
        
        # Draw cross shape
        # Horizontal bar
        painter.drawRoundedRect(center_x - 15, center_y - 5, 30, 10, 2, 2)
        # Vertical bar
        painter.drawRoundedRect(center_x - 5, center_y - 15, 10, 30, 2, 2)
        
        # Highlight pressed directions
        if self.dpad.get('up', False):
            painter.setBrush(QBrush(QColor("#1e90ff")))
            painter.drawRoundedRect(center_x - 5, center_y - 15, 10, 10, 2, 2)
        if self.dpad.get('down', False):
            painter.setBrush(QBrush(QColor("#1e90ff")))
            painter.drawRoundedRect(center_x - 5, center_y + 5, 10, 10, 2, 2)
        if self.dpad.get('left', False):
            painter.setBrush(QBrush(QColor("#1e90ff")))
            painter.drawRoundedRect(center_x - 15, center_y - 5, 10, 10, 2, 2)
        if self.dpad.get('right', False):
            painter.setBrush(QBrush(QColor("#1e90ff")))
            painter.drawRoundedRect(center_x + 5, center_y - 5, 10, 10, 2, 2)
    
    def _draw_action_buttons(self, painter, center_x, center_y):
        """Draw simple ABXY buttons in diamond formation"""
        button_radius = 10
        spacing = 22
        
        # Diamond layout positions
        positions = [
            ('button_y', center_x, center_y - spacing, 'Y'),      # Top
            ('button_a', center_x, center_y + spacing, 'A'),      # Bottom  
            ('button_x', center_x - spacing, center_y, 'X'),      # Left
            ('button_b', center_x + spacing, center_y, 'B')       # Right
        ]
        
        for button_name, x, y, label in positions:
            pressed = self.buttons.get(button_name, False)
            
            # Simple color scheme
            color = QColor("#1e90ff") if pressed else QColor("#555555")
            fill_color = QColor("#1e90ff") if pressed else QColor("#333333")
            
            painter.setPen(QPen(color, 2))
            painter.setBrush(QBrush(fill_color))
            painter.drawEllipse(x - button_radius, y - button_radius, 
                              button_radius * 2, button_radius * 2)
            
            # Button label
            painter.setPen(QPen(QColor("#ffffff")))
            painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            painter.drawText(x - 4, y + 3, label)
    
    def _draw_shoulder_buttons(self, painter, controller_rect):
        """Draw shoulder buttons (LB/RB)"""
        button_width = 30
        button_height = 12
        
        # Left shoulder
        lb_pressed = self.buttons.get('shoulder_left', False)
        color = QColor("#1e90ff") if lb_pressed else QColor("#555555")
        painter.setPen(QPen(color, 2))
        painter.setBrush(QBrush(color if lb_pressed else QColor("#333333")))
        
        lb_rect = QRect(controller_rect.left() + 20, controller_rect.top() - 15,
                       button_width, button_height)
        painter.drawRoundedRect(lb_rect, 5, 5)
        
        painter.setPen(QPen(QColor("#ffffff")))
        painter.setFont(QFont("Arial", 8))
        painter.drawText(lb_rect.center().x() - 8, lb_rect.center().y() + 3, "LB")
        
        # Right shoulder
        rb_pressed = self.buttons.get('shoulder_right', False)
        color = QColor("#1e90ff") if rb_pressed else QColor("#555555")
        painter.setPen(QPen(color, 2))
        painter.setBrush(QBrush(color if rb_pressed else QColor("#333333")))
        
        rb_rect = QRect(controller_rect.right() - 50, controller_rect.top() - 15,
                       button_width, button_height)
        painter.drawRoundedRect(rb_rect, 5, 5)
        
        painter.setPen(QPen(QColor("#ffffff")))
        painter.setFont(QFont("Arial", 8))
        painter.drawText(rb_rect.center().x() - 8, rb_rect.center().y() + 3, "RB")
    
    def _draw_triggers(self, painter, controller_rect):
        """Draw trigger indicators"""
        trigger_width = 20
        trigger_height = 50
        
        # Left trigger
        lt_rect = QRect(controller_rect.left() + 10, controller_rect.top() - 35,
                       trigger_width, trigger_height)
        painter.setPen(QPen(QColor("#555555"), 2))
        painter.setBrush(QBrush(QColor("#333333")))
        painter.drawRect(lt_rect)
        
        # Fill based on trigger value
        fill_height = int(self.left_trigger * trigger_height)
        if fill_height > 0:
            fill_rect = QRect(lt_rect.left(), lt_rect.bottom() - fill_height,
                            trigger_width, fill_height)
            painter.setBrush(QBrush(QColor("#1e90ff")))
            painter.drawRect(fill_rect)
        
        painter.setPen(QPen(QColor("#ffffff")))
        painter.setFont(QFont("Arial", 8))
        painter.drawText(lt_rect.left() + 5, lt_rect.bottom() + 12, "LT")
        
        # Right trigger
        rt_rect = QRect(controller_rect.right() - 30, controller_rect.top() - 35,
                       trigger_width, trigger_height)
        painter.setPen(QPen(QColor("#555555"), 2))
        painter.setBrush(QBrush(QColor("#333333")))
        painter.drawRect(rt_rect)
        
        # Fill based on trigger value
        fill_height = int(self.right_trigger * trigger_height)
        if fill_height > 0:
            fill_rect = QRect(rt_rect.left(), rt_rect.bottom() - fill_height,
                            trigger_width, fill_height)
            painter.setBrush(QBrush(QColor("#1e90ff")))
            painter.drawRect(fill_rect)
        
        painter.setPen(QPen(QColor("#ffffff")))
        painter.setFont(QFont("Arial", 8))
        painter.drawText(rt_rect.left() + 5, rt_rect.bottom() + 12, "RT")
    
    def _draw_value_displays(self, painter):
        """Draw raw and calibrated value displays"""
        if not self.raw_values and not self.calibrated_values:
            return
        
        # Position for value display
        display_x = 10
        display_y = 10
        
        painter.setPen(QPen(QColor("#cccccc")))
        painter.setFont(QFont("Courier", 9))
        
        y_offset = display_y
        painter.drawText(display_x, y_offset, "Raw Values:")
        y_offset += 15
        
        for key, value in self.raw_values.items():
            if isinstance(value, float):
                text = f"{key}: {value:.3f}"
            else:
                text = f"{key}: {value}"
            painter.drawText(display_x + 10, y_offset, text)
            y_offset += 12
        
        y_offset += 10
        painter.drawText(display_x, y_offset, "Calibrated Values:")
        y_offset += 15
        
        for key, value in self.calibrated_values.items():
            if isinstance(value, float):
                text = f"{key}: {value:.3f}"
            else:
                text = f"{key}: {value}"
            painter.drawText(display_x + 10, y_offset, text)
            y_offset += 12


class CalibrationWizardPage(QWidget):
    """Base class for calibration wizard pages"""
    
    def __init__(self, title: str):
        super().__init__()
        self.title = title
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the page UI - override in subclasses"""
        pass
    
    def on_page_enter(self):
        """Called when page becomes active"""
        pass
    
    def on_page_exit(self):
        """Called when leaving page"""
        pass
    
    def is_complete(self) -> bool:
        """Return True if page requirements are met"""
        # Default implementation returns True for all pages except WelcomePage
        return True


class WelcomePage(CalibrationWizardPage):
    """Welcome page explaining the calibration process"""
    
    def __init__(self):
        super().__init__("Controller Calibration")
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Bluetooth Controller Calibration")
        title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        title.setStyleSheet("color: #1e90ff; margin: 20px 0;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Instructions - Fixed Unicode bullet points
        instructions = QLabel(
            "This wizard will help you calibrate your controller for optimal performance.\n\n"
            "The calibration process involves:\n"
            "• Testing current controller input\n"
            "• Recording joystick movement ranges\n"
            "• Setting dead zone preferences\n"
            "• Saving your custom profile\n\n"
            "Make sure your controller is connected before proceeding."
        )
        instructions.setStyleSheet("color: #cccccc; font-size: 12px; line-height: 1.5;")
        instructions.setWordWrap(True)
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(instructions)
        
        # Status indicator
        self.status_label = QLabel("Controller Status: Checking...")
        self.status_label.setStyleSheet("color: #ffaa00; margin: 20px 0; font-weight: bold;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def update_controller_status(self, connected: bool, controller_name: str = ""):
        """Update controller connection status"""
        if connected:
            self.status_label.setText(f"Controller Status: Connected - {controller_name}")
            self.status_label.setStyleSheet("color: #c; margin: 20px 0; font-weight: bold;")
        else:
            self.status_label.setText("Controller Status: Not Connected")
            self.status_label.setStyleSheet("color: #ff4444; margin: 20px 0; font-weight: bold;")
    
    def is_complete(self) -> bool:
        """Welcome page is complete only when controller is connected"""
        return "Connected" in self.status_label.text()


class InputTestPage(CalibrationWizardPage):
    """Page for testing controller input"""
    
    def __init__(self):
        super().__init__("Input Test")
        self.controller_viz = None
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Instructions
        instructions = QLabel(
            "Test your controller by moving the joysticks, pressing buttons, and using the D-pad.\n"
            "Verify that all inputs are detected correctly before proceeding."
        )
        instructions.setStyleSheet("color: #cccccc; font-size: 12px; margin-bottom: 20px;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # Controller visualization
        self.controller_viz = ControllerVisualization()
        layout.addWidget(self.controller_viz)
        
        self.setLayout(layout)
    
    def update_controller_data(self, data: Dict):
        """Update controller visualization"""
        if self.controller_viz:
            self.controller_viz.update_controller_state(data)


class JoystickCalibrationPage(CalibrationWizardPage):
    """Page for joystick range calibration"""
    
    def __init__(self):
        super().__init__("Joystick Calibration")
        self.calibration_complete = False
        self.left_stick_ranges = {'x': [0, 0], 'y': [0, 0]}
        self.right_stick_ranges = {'x': [0, 0], 'y': [0, 0]}
        self.parent_dialog = None  # Fixed: Store parent dialog reference
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Instructions
        self.instructions = QLabel(
            "Click 'Start Calibration' then move both joysticks in complete circles\n"
            "to establish their full range of motion."
        )
        self.instructions.setStyleSheet("color: #cccccc; font-size: 12px; margin-bottom: 20px;")
        self.instructions.setWordWrap(True)
        layout.addWidget(self.instructions)
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Start button
        self.start_button = QPushButton("Start Calibration")
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #1e90ff;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #4dabf7; }
            QPushButton:disabled { background-color: #555555; }
        """)
        self.start_button.clicked.connect(self.start_calibration)
        layout.addWidget(self.start_button)
        
        # Range display
        self.range_display = QLabel("Move joysticks to see ranges...")
        self.range_display.setStyleSheet("color: #cccccc; font-family: monospace; margin: 20px 0;")
        layout.addWidget(self.range_display)
        
        self.setLayout(layout)
    
    def set_parent_dialog(self, parent_dialog):
        """Set reference to parent dialog for navigation updates"""
        self.parent_dialog = parent_dialog
    
    def start_calibration(self):
        """Start the joystick calibration process"""
        self.start_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.instructions.setText("Move both joysticks in complete circles for 10 seconds...")
        
        # Reset ranges
        self.left_stick_ranges = {'x': [0, 0], 'y': [0, 0]}
        self.right_stick_ranges = {'x': [0, 0], 'y': [0, 0]}
        
        # Start countdown timer
        self.calibration_timer = QTimer()
        self.calibration_timer.timeout.connect(self.update_calibration_progress)
        self.calibration_start_time = time.time()
        self.calibration_duration = 10.0
        self.calibration_timer.start(100)  # Update every 100ms
    
    def update_calibration_progress(self):
        """Update calibration progress"""
        elapsed = time.time() - self.calibration_start_time
        progress = min(100, int((elapsed / self.calibration_duration) * 100))
        self.progress_bar.setValue(progress)
        
        if progress >= 100:
            self.finish_calibration()
            
    def finish_calibration(self):
        """Complete the calibration process"""
        if hasattr(self, 'calibration_timer'):
            self.calibration_timer.stop()
        
        self.calibration_complete = True
        self.instructions.setText("Calibration complete! Joystick ranges have been recorded.")
        self.start_button.setText("Recalibrate")
        self.start_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        # Fixed: Use parent_dialog instead of main_dialog
        if self.parent_dialog:
            QTimer.singleShot(100, self.parent_dialog.update_navigation)
        
    def update_joystick_data(self, left_x, left_y, right_x, right_y):
        """Update joystick ranges during calibration"""
        if hasattr(self, 'calibration_timer') and self.calibration_timer.isActive():
            # Update left stick ranges
            if not self.left_stick_ranges['x'] == [0, 0]:
                self.left_stick_ranges['x'][0] = min(self.left_stick_ranges['x'][0], left_x)
                self.left_stick_ranges['x'][1] = max(self.left_stick_ranges['x'][1], left_x)
                self.left_stick_ranges['y'][0] = min(self.left_stick_ranges['y'][0], left_y)
                self.left_stick_ranges['y'][1] = max(self.left_stick_ranges['y'][1], left_y)
            else:
                self.left_stick_ranges['x'] = [left_x, left_x]
                self.left_stick_ranges['y'] = [left_y, left_y]
            
            # Update right stick ranges
            if not self.right_stick_ranges['x'] == [0, 0]:
                self.right_stick_ranges['x'][0] = min(self.right_stick_ranges['x'][0], right_x)
                self.right_stick_ranges['x'][1] = max(self.right_stick_ranges['x'][1], right_x)
                self.right_stick_ranges['y'][0] = min(self.right_stick_ranges['y'][0], right_y)
                self.right_stick_ranges['y'][1] = max(self.right_stick_ranges['y'][1], right_y)
            else:
                self.right_stick_ranges['x'] = [right_x, right_x]
                self.right_stick_ranges['y'] = [right_y, right_y]
            
            # Update display
            self.range_display.setText(
                f"Left Stick - X: [{self.left_stick_ranges['x'][0]:.3f}, {self.left_stick_ranges['x'][1]:.3f}] "
                f"Y: [{self.left_stick_ranges['y'][0]:.3f}, {self.left_stick_ranges['y'][1]:.3f}]\n"
                f"Right Stick - X: [{self.right_stick_ranges['x'][0]:.3f}, {self.right_stick_ranges['x'][1]:.3f}] "
                f"Y: [{self.right_stick_ranges['y'][0]:.3f}, {self.right_stick_ranges['y'][1]:.3f}]"
            )
    
    def is_complete(self) -> bool:
        return self.calibration_complete


class DeadZoneConfigPage(CalibrationWizardPage):
    """Page for configuring dead zone settings"""
    
    def __init__(self):
        super().__init__("Dead Zone Configuration")
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Instructions
        instructions = QLabel(
            "Set the dead zone size for each joystick. The dead zone eliminates\n"
            "small unintended movements when the stick is at rest."
        )
        instructions.setStyleSheet("color: #cccccc; font-size: 12px; margin-bottom: 20px;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # Dead zone controls
        controls_layout = QGridLayout()
        
        # Left stick dead zone
        controls_layout.addWidget(QLabel("Left Stick Dead Zone:"), 0, 0)
        self.left_deadzone_slider = QSlider(Qt.Orientation.Horizontal)
        self.left_deadzone_slider.setRange(0, 50)
        self.left_deadzone_slider.setValue(15)
        self.left_deadzone_slider.valueChanged.connect(self.update_deadzone_labels)
        controls_layout.addWidget(self.left_deadzone_slider, 0, 1)
        
        self.left_deadzone_label = QLabel("15%")
        self.left_deadzone_label.setStyleSheet("color: #1e90ff;")
        controls_layout.addWidget(self.left_deadzone_label, 0, 2)
        
        # Right stick dead zone
        controls_layout.addWidget(QLabel("Right Stick Dead Zone:"), 1, 0)
        self.right_deadzone_slider = QSlider(Qt.Orientation.Horizontal)
        self.right_deadzone_slider.setRange(0, 50)
        self.right_deadzone_slider.setValue(15)
        self.right_deadzone_slider.valueChanged.connect(self.update_deadzone_labels)
        controls_layout.addWidget(self.right_deadzone_slider, 1, 1)
        
        self.right_deadzone_label = QLabel("15%")
        self.right_deadzone_label.setStyleSheet("color: #1e90ff;")
        controls_layout.addWidget(self.right_deadzone_label, 1, 2)
        
        # Style the controls
        slider_style = """
        QSlider::groove:horizontal {
            border: 1px solid #555;
            height: 6px;
            background: #2d2d2d;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #1e90ff;
            border: 1px solid #1e90ff;
            width: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }
        """
        self.left_deadzone_slider.setStyleSheet(slider_style)
        self.right_deadzone_slider.setStyleSheet(slider_style)
        
        layout.addLayout(controls_layout)
        layout.addStretch()
        self.setLayout(layout)
    
    def update_deadzone_labels(self):
        """Update dead zone percentage labels"""
        self.left_deadzone_label.setText(f"{self.left_deadzone_slider.value()}%")
        self.right_deadzone_label.setText(f"{self.right_deadzone_slider.value()}%")
    
    def get_deadzone_values(self) -> Dict[str, float]:
        """Get dead zone values as decimals"""
        return {
            'left_stick': self.left_deadzone_slider.value() / 100.0,
            'right_stick': self.right_deadzone_slider.value() / 100.0
        }


class ProfileManagementPage(CalibrationWizardPage):
    """Page for saving/loading calibration profiles"""
    
    def __init__(self):
        super().__init__("Profile Management")
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Instructions
        instructions = QLabel(
            "Save your calibration as a profile or load an existing one."
        )
        instructions.setStyleSheet("color: #cccccc; font-size: 12px; margin-bottom: 20px;")
        layout.addWidget(instructions)
        
        # Profile selection
        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("Profile:"))
        
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(["Default", "Gaming", "Precision", "Custom"])
        self.profile_combo.setStyleSheet("""
            QComboBox {
                background-color: #2d2d2d;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px;
                color: white;
                min-width: 120px;
            }
            QComboBox:focus { 
                border-color: #1e90ff; 
                background-color: #333333;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                color: white;
                selection-background-color: #1e90ff;
            }
        """)
        profile_layout.addWidget(self.profile_combo)
        
        # Load button
        self.load_button = QPushButton("Load Profile")
        self.load_button.setStyleSheet(self._get_button_style())
        self.load_button.clicked.connect(self.load_profile)
        profile_layout.addWidget(self.load_button)
        
        profile_layout.addStretch()
        layout.addLayout(profile_layout)
        
        # Save section
        save_layout = QHBoxLayout()
        save_layout.addWidget(QLabel("Save as:"))
        
        self.save_name_input = QLineEdit()
        self.save_name_input.setPlaceholderText("Enter profile name...")
        self.save_name_input.setStyleSheet("""
            QLineEdit {
                background-color: #2d2d2d;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px;
                color: white;
            }
            QLineEdit:focus { 
                border-color: #1e90ff; 
                background-color: #333333;
            }
        """)
        save_layout.addWidget(self.save_name_input)
        
        self.save_button = QPushButton("Save Profile")
        self.save_button.setStyleSheet(self._get_button_style())
        self.save_button.clicked.connect(self.save_profile)
        save_layout.addWidget(self.save_button)
        
        save_layout.addStretch()
        layout.addLayout(save_layout)
        
        # Profile summary
        self.summary_text = QTextEdit()
        self.summary_text.setMaximumHeight(100)
        self.summary_text.setReadOnly(True)
        self.summary_text.setPlaceholderText("Profile summary will appear here...")
        self.summary_text.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a1a;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 8px;
                color: #cccccc;
                font-family: monospace;
                font-size: 10px;
            }
        """)
        layout.addWidget(self.summary_text)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def _get_button_style(self):
        return """
            QPushButton {
                background-color: #1e90ff;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #4dabf7; }
            QPushButton:disabled { background-color: #555555; }
        """
    
    def load_profile(self):
        """Load selected profile"""
        profile_name = self.profile_combo.currentText()
        # TODO: Implement profile loading
        self.summary_text.setText(f"Loaded profile: {profile_name}")
    
    def save_profile(self):
        """Save current calibration as profile"""
        profile_name = self.save_name_input.text().strip()
        if not profile_name:
            profile_name = "Custom"
        
        # TODO: Implement profile saving
        self.summary_text.setText(f"Saved profile: {profile_name}")
        self.save_name_input.clear()


class ControllerCalibrationDialog(QDialog):
    """Main controller calibration dialog with wizard interface"""
    
    # Signals
    calibration_completed = pyqtSignal(dict)
    
    def __init__(self, websocket=None, parent=None):
        super().__init__(parent)
        self.websocket = websocket
        self.logger = get_logger("controller_calibration")
        
        # Dialog setup
        self.setWindowTitle("Controller Calibration")
        self.setModal(True)
        self.setFixedSize(800, 600)
        self.setStyleSheet("""
            QDialog {
                background-color: #0f1419;
                color: white;
            }
        """)
        
        # Wizard pages
        self.current_page_index = 0
        self.pages = []
        
        self.setup_ui()
        self.setup_websocket()
        self.setup_timers()
        
    def setup_ui(self):
        """Setup the main UI layout"""
        layout = QVBoxLayout()
        
        # Header with progress
        header_layout = QHBoxLayout()
        
        # Title
        self.title_label = QLabel("Controller Calibration Wizard")
        self.title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #1e90ff; margin: 10px 0;")
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        # Progress indicator
        self.progress_label = QLabel("Step 1 of 5")
        self.progress_label.setStyleSheet("color: #cccccc; margin: 10px 0;")
        header_layout.addWidget(self.progress_label)
        
        layout.addLayout(header_layout)
        
        # Progress bar
        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 4)  # 5 steps, 0-based
        self.overall_progress.setValue(0)
        self.overall_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #555;
                border-radius: 5px;
                background-color: #2d2d2d;
                height: 8px;
            }
            QProgressBar::chunk {
                background-color: #1e90ff;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.overall_progress)
        
        # Page container
        self.page_stack = QStackedWidget()
        
        # Create and add pages
        self.welcome_page = WelcomePage()
        self.input_test_page = InputTestPage()
        self.joystick_cal_page = JoystickCalibrationPage()
        self.deadzone_page = DeadZoneConfigPage()
        self.profile_page = ProfileManagementPage()
        
        # Fixed: Set parent dialog reference for joystick calibration page
        self.joystick_cal_page.set_parent_dialog(self)
        
        self.pages = [
            self.welcome_page,
            self.input_test_page,
            self.joystick_cal_page,
            self.deadzone_page,
            self.profile_page
        ]
        
        for page in self.pages:
            self.page_stack.addWidget(page)
        
        layout.addWidget(self.page_stack, 1)
        
        # Navigation buttons - Fixed Unicode arrows
        nav_layout = QHBoxLayout()
        
        self.back_button = QPushButton("< Back")
        self.back_button.setEnabled(False)
        self.back_button.clicked.connect(self.previous_page)
        self.back_button.setStyleSheet(self._get_nav_button_style())
        nav_layout.addWidget(self.back_button)
        
        nav_layout.addStretch()
        
        self.next_button = QPushButton("Next >")
        self.next_button.clicked.connect(self.next_page)
        self.next_button.setStyleSheet(self._get_nav_button_style())
        nav_layout.addWidget(self.next_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.cancel_button.setStyleSheet(self._get_cancel_button_style())
        nav_layout.addWidget(self.cancel_button)
        
        layout.addLayout(nav_layout)
        self.setLayout(layout)
        
        self.update_navigation()
    
    def _get_nav_button_style(self):
        return """
            QPushButton {
                background-color: #1e90ff;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 12px;
                min-width: 80px;
            }
            QPushButton:hover { background-color: #4dabf7; }
            QPushButton:disabled { 
                background-color: #555555;
                color: #999999;
            }
        """
    
    def _get_cancel_button_style(self):
        return """
            QPushButton {
                background-color: #666666;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 12px;
                min-width: 80px;
            }
            QPushButton:hover { background-color: #888888; }
        """
    
    def setup_websocket(self):
        """Setup WebSocket communication"""
        if self.websocket:
            self.websocket.textMessageReceived.connect(self.handle_websocket_message)
            
            # Start calibration mode
            self.send_websocket_message("start_calibration_mode")
    
    def setup_timers(self):
        """Setup update timers"""
        # Controller status check timer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.check_controller_status)
        self.status_timer.start(1000)  # Check every second
    
    def send_websocket_message(self, message_type: str, **kwargs):
        """Send WebSocket message"""
        if self.websocket and self.websocket.isValid():
            message = {"type": message_type, **kwargs}
            self.websocket.sendTextMessage(json.dumps(message))
            self.logger.debug(f"Sent message: {message_type}")
    
    def handle_websocket_message(self, message: str):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "controller_status":
                self.handle_controller_status(data)
            elif msg_type == "calibration_data":
                self.handle_calibration_data(data)
            elif msg_type == "controller_info":
                self.handle_controller_info(data)
                
        except json.JSONDecodeError:
            self.logger.warning(f"Invalid JSON message: {message}")
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")
    
    def handle_controller_status(self, data: Dict):
        """Handle controller connection status"""
        connected = data.get("connected", False)
        controller_name = data.get("controller_name", "Unknown")
        
        if self.current_page_index == 0:  # Welcome page
            self.welcome_page.update_controller_status(connected, controller_name)
            self.update_navigation()
    
    def handle_calibration_data(self, data: Dict):
        """Handle real-time calibration data"""
        # Update input test page
        if self.current_page_index == 1:
            self.input_test_page.update_controller_data(data)
        
        # Update joystick calibration page
        elif self.current_page_index == 2:
            left_x = data.get("left_stick_x", 0.0)
            left_y = data.get("left_stick_y", 0.0)
            right_x = data.get("right_stick_x", 0.0)
            right_y = data.get("right_stick_y", 0.0)
            self.joystick_cal_page.update_joystick_data(left_x, left_y, right_x, right_y)
    
    def handle_controller_info(self, data: Dict):
        """Handle controller information"""
        self.logger.info(f"Controller info: {data}")
    
    def check_controller_status(self):
        """Request controller status update"""
        self.send_websocket_message("get_controller_status")
    
    def next_page(self):
        """Go to next page"""
        current_page = self.pages[self.current_page_index]
        if not current_page.is_complete():
            return
        
        current_page.on_page_exit()
        
        if self.current_page_index < len(self.pages) - 1:
            self.current_page_index += 1
            self.page_stack.setCurrentIndex(self.current_page_index)
            self.pages[self.current_page_index].on_page_enter()
            self.update_navigation()
        else:
            # Finish calibration
            self.finish_calibration()
    
    def previous_page(self):
        """Go to previous page"""
        if self.current_page_index > 0:
            self.pages[self.current_page_index].on_page_exit()
            self.current_page_index -= 1
            self.page_stack.setCurrentIndex(self.current_page_index)
            self.pages[self.current_page_index].on_page_enter()
            self.update_navigation()
    
    def update_navigation(self):
        """Update navigation button states and progress"""
        # Update progress
        self.overall_progress.setValue(self.current_page_index)
        self.progress_label.setText(f"Step {self.current_page_index + 1} of {len(self.pages)}")
        
        # Update buttons
        self.back_button.setEnabled(self.current_page_index > 0)
        
        current_page = self.pages[self.current_page_index]
        is_last_page = self.current_page_index == len(self.pages) - 1
        
        if is_last_page:
            self.next_button.setText("Finish")
        else:
            self.next_button.setText("Next >")
        
        page_complete = current_page.is_complete()
        self.next_button.setEnabled(page_complete)
        
        # Update title
        page_title = current_page.title
        self.title_label.setText(f"Controller Calibration - {page_title}")
    
    def finish_calibration(self):
        """Complete the calibration process"""
        # Collect calibration data
        calibration_data = {
            "joystick_ranges": {
                "left_stick": self.joystick_cal_page.left_stick_ranges,
                "right_stick": self.joystick_cal_page.right_stick_ranges
            },
            "dead_zones": self.deadzone_page.get_deadzone_values(),
            "timestamp": time.time()
        }
        
        # Send to backend
        self.send_websocket_message("save_calibration", calibration=calibration_data)
        
        # Stop calibration mode
        self.send_websocket_message("stop_calibration_mode")
        
        # Emit completion signal
        self.calibration_completed.emit(calibration_data)
        
        self.accept()
    
    def closeEvent(self, event):
        """Handle dialog close"""
        # Stop calibration mode
        self.send_websocket_message("stop_calibration_mode")
        super().closeEvent(event)
    
    def reject(self):
        """Handle dialog cancellation"""
        # Stop calibration mode
        self.send_websocket_message("stop_calibration_mode")
        super().reject()