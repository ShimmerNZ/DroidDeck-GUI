#!/usr/bin/env python3
"""
WALL-E Control System - Controller Status Display Splash
Matches the exact styling of controller calibration screen
"""

import json
import time
from typing import Dict, Any, Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QFrame,
    QGridLayout, QProgressBar, QApplication
)
from PyQt6.QtGui import QFont, QPainter, QPen, QBrush, QColor
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRect

from core.logger import get_logger
from core.theme_manager import theme_manager
from threads.steamdeck import ControllerInputData


class ControllerVisualizationWidget(QWidget):
    """Live controller visualization widget matching calibration screen styling"""
    
    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 300)
        
        # Controller state
        self.left_stick = (0.0, 0.0)
        self.right_stick = (0.0, 0.0)
        self.left_trigger = 0.0
        self.right_trigger = 0.0
        
        # Button states
        self.buttons = {
            'button_a': False, 'button_b': False, 'button_x': False, 'button_y': False,
            'shoulder_left': False, 'shoulder_right': False,
            'dpad_up': False, 'dpad_down': False, 'dpad_left': False, 'dpad_right': False,
            'button_start': False, 'button_back': False, 'button_guide': False
        }
        
        # Live values for display
        self.raw_values = {}
        self.input_rate = 0.0
        self.sequence_number = 0
        
    def update_controller_data(self, input_data: ControllerInputData):
        """Update controller visualization with new input data"""
        # Update stick positions
        self.left_stick = (
            input_data.axes.get('left_stick_x', 0.0),
            input_data.axes.get('left_stick_y', 0.0)
        )
        self.right_stick = (
            input_data.axes.get('right_stick_x', 0.0),
            input_data.axes.get('right_stick_y', 0.0)
        )
        
        # Update triggers
        self.left_trigger = abs(input_data.axes.get('left_trigger', 0.0))
        self.right_trigger = abs(input_data.axes.get('right_trigger', 0.0))
        
        # Update buttons
        for button_name in self.buttons.keys():
            self.buttons[button_name] = input_data.buttons.get(button_name, False)
        
        # Store raw values for display
        self.raw_values = {**input_data.axes, **{k: int(v) for k, v in input_data.buttons.items()}}
        self.sequence_number = input_data.sequence
        
        self.update()
    
    def set_input_rate(self, rate: float):
        """Set the current input rate"""
        self.input_rate = rate
        self.update()
        
    def paintEvent(self, event):
        """Draw the controller visualization"""
        painter = QPainter(self)
        try:
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
            
            # Draw joysticks
            self._draw_joystick(painter, controller_rect.left() + 90, controller_rect.bottom() - 60, 
                            self.left_stick, "L")
            self._draw_joystick(painter, controller_rect.right() - 90, controller_rect.center().y() + 10, 
                            self.right_stick, "R")
            
            # Draw D-pad
            self._draw_dpad(painter, controller_rect.left() + 90, controller_rect.center().y() - 20)
            
            # Draw action buttons (ABXY)
            self._draw_action_buttons(painter, controller_rect.right() - 90, controller_rect.center().y() - 20)
            
            # Draw shoulder buttons
            self._draw_shoulder_buttons(painter, controller_rect)
            
            # Draw triggers
            self._draw_triggers(painter, controller_rect)
            
            # Draw status info
            self._draw_status_info(painter)
            
        finally:
            painter.end()
    
    def _draw_joystick(self, painter, center_x, center_y, stick_pos, label):
        """Draw a joystick with position indicator"""
        radius = 25
        
        # Convert to integers for PyQt6 compatibility
        center_x = int(center_x)
        center_y = int(center_y)
        
        # Draw outer circle
        painter.setPen(QPen(QColor("#555555"), 2))
        painter.setBrush(QBrush(QColor("#333333")))
        painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)
        
        # Draw inner circle (stick position)
        stick_x = int(center_x + (stick_pos[0] * radius * 0.8))
        stick_y = int(center_y + (stick_pos[1] * radius * 0.8))
        inner_radius = 8
        
        painter.setPen(QPen(QColor("#1e90ff"), 2))
        painter.setBrush(QBrush(QColor("#1e90ff")))
        painter.drawEllipse(stick_x - inner_radius, stick_y - inner_radius, 
                          inner_radius * 2, inner_radius * 2)
        
        # Draw center crosshairs
        painter.setPen(QPen(QColor("#666666"), 1))
        painter.drawLine(center_x - radius//2, center_y, center_x + radius//2, center_y)
        painter.drawLine(center_x, center_y - radius//2, center_x, center_y + radius//2)
        
        # Label
        painter.setPen(QPen(QColor("#cccccc")))
        painter.setFont(QFont("Arial", 10))
        painter.drawText(center_x - 5, center_y + radius + 15, label)
    
    def _draw_dpad(self, painter, center_x, center_y):
        """Draw D-pad with current state"""
        size = 15
        gap = 5
        
        # Convert to integers for PyQt6 compatibility
        center_x = int(center_x)
        center_y = int(center_y)
        
        # Up
        color = QColor("#1e90ff") if self.buttons['dpad_up'] else QColor("#555555")
        painter.setPen(QPen(color, 2))
        painter.setBrush(QBrush(color if self.buttons['dpad_up'] else QColor("#333333")))
        painter.drawRect(center_x - size//2, center_y - size - gap, size, size)
        
        # Down  
        color = QColor("#1e90ff") if self.buttons['dpad_down'] else QColor("#555555")
        painter.setPen(QPen(color, 2))
        painter.setBrush(QBrush(color if self.buttons['dpad_down'] else QColor("#333333")))
        painter.drawRect(center_x - size//2, center_y + gap, size, size)
        
        # Left
        color = QColor("#1e90ff") if self.buttons['dpad_left'] else QColor("#555555")
        painter.setPen(QPen(color, 2))
        painter.setBrush(QBrush(color if self.buttons['dpad_left'] else QColor("#333333")))
        painter.drawRect(center_x - size - gap, center_y - size//2, size, size)
        
        # Right
        color = QColor("#1e90ff") if self.buttons['dpad_right'] else QColor("#555555")
        painter.setPen(QPen(color, 2))
        painter.setBrush(QBrush(color if self.buttons['dpad_right'] else QColor("#333333")))
        painter.drawRect(center_x + gap, center_y - size//2, size, size)
        
        # Center
        painter.setPen(QPen(QColor("#666666"), 1))
        painter.setBrush(QBrush(QColor("#333333")))
        painter.drawRect(center_x - size//2, center_y - size//2, size, size)
    
    def _draw_action_buttons(self, painter, center_x, center_y):
        """Draw action buttons (A, B, X, Y)"""
        button_radius = 12
        spacing = 20
        
        # Convert to integers for PyQt6 compatibility
        center_x = int(center_x)
        center_y = int(center_y)
        
        positions = [
            ('button_y', center_x, center_y - spacing, 'Y'),     # Top
            ('button_a', center_x, center_y + spacing, 'A'),     # Bottom  
            ('button_x', center_x - spacing, center_y, 'X'),     # Left
            ('button_b', center_x + spacing, center_y, 'B')      # Right
        ]
        
        for button_name, x, y, label in positions:
            pressed = self.buttons.get(button_name, False)
            
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
    
    def _draw_status_info(self, painter):
        """Draw status information"""
        if not hasattr(self, 'width') or self.width() < 500:
            return
            
        # Position for status display
        info_x = 10
        info_y = 10
        
        painter.setPen(QPen(QColor("#cccccc")))
        painter.setFont(QFont("Courier", 9))
        
        # Input rate and sequence
        painter.drawText(info_x, info_y, f"Input Rate: {self.input_rate:.1f} Hz")
        painter.drawText(info_x, info_y + 15, f"Sequence: #{self.sequence_number}")
        
        # Active inputs
        active_inputs = []
        for name, value in self.raw_values.items():
            if isinstance(value, (int, bool)) and value:
                active_inputs.append(name)
            elif isinstance(value, float) and abs(value) > 0.1:
                active_inputs.append(f"{name}:{value:.2f}")
        
        if active_inputs:
            painter.drawText(info_x, info_y + 35, "Active:")
            for i, input_name in enumerate(active_inputs[:8]):  # Limit display
                painter.drawText(info_x, info_y + 50 + (i * 12), f"  {input_name}")


class ControllerStatusSplash(QDialog):
    """Controller status display splash matching calibration screen styling exactly"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_logger("controller")
        
        # Dialog configuration 
        self.setModal(True)
        self.setWindowTitle("Controller Status Monitor")
        self.setFixedSize(700, 500)
        
        # Controller data tracking
        self.controller_connected = False
        self.controller_name = "No Controller"
        self.last_update_time = 0
        self.input_count = 0
        self.start_time = time.time()
        
        # Update timer for live display
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_display_stats)
        self.update_timer.start(1000)  # Update every second
        
        self._setup_ui()
        self._apply_controller_style()
        self._center_on_screen()
        
        self.logger.info("Controller status splash initialized")
    
    def _setup_ui(self):
        """Setup UI matching controller calibration screen layout exactly"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Content area (matches calibration screen)
        content_widget = QWidget()
        content_widget.setObjectName("content_widget")
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(25, 20, 25, 20)
        
        # Header section
        header_layout = QVBoxLayout()
        header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        title_label = QLabel("CONTROLLER STATUS MONITOR")
        title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setObjectName("title_label")
        header_layout.addWidget(title_label)
        
        self.status_label = QLabel("Monitoring SteamDeck controller input...")
        self.status_label.setFont(QFont("Arial", 11))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setObjectName("status_label")
        header_layout.addWidget(self.status_label)
        
        content_layout.addLayout(header_layout)
        
        # Controller visualization
        self.controller_widget = ControllerVisualizationWidget()
        content_layout.addWidget(self.controller_widget)
        
        # Status information panel
        self._create_status_panel(content_layout)
        
        content_widget.setLayout(content_layout)
        main_layout.addWidget(content_widget)
        
        # Button area (matches calibration screen exactly)
        button_widget = QWidget()
        button_widget.setObjectName("button_widget")
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(30, 20, 30, 25)
        
        # Close button
        self.close_button = QPushButton("Close")
        self.close_button.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.close_button.setFixedHeight(40)
        self.close_button.clicked.connect(self.accept)
        self.close_button.setDefault(True)
        
        button_layout.addStretch()
        button_layout.addWidget(self.close_button)
        
        button_widget.setLayout(button_layout)
        main_layout.addWidget(button_widget)
        
        self.setLayout(main_layout)
    
    def _create_status_panel(self, parent_layout):
        """Create status information panel"""
        status_frame = QFrame()
        status_frame.setObjectName("status_frame")
        status_layout = QGridLayout()
        status_layout.setSpacing(10)
        
        # Connection status
        self.connection_label = QLabel("Controller: Disconnected")
        self.connection_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        status_layout.addWidget(QLabel("Status:"), 0, 0)
        status_layout.addWidget(self.connection_label, 0, 1)
        
        # Controller type
        self.type_label = QLabel("Unknown")
        status_layout.addWidget(QLabel("Type:"), 1, 0)
        status_layout.addWidget(self.type_label, 1, 1)
        
        # Input rate
        self.rate_label = QLabel("0.0 Hz")
        status_layout.addWidget(QLabel("Input Rate:"), 2, 0)
        status_layout.addWidget(self.rate_label, 2, 1)
        
        # Total inputs
        self.count_label = QLabel("0")
        status_layout.addWidget(QLabel("Total Inputs:"), 3, 0)
        status_layout.addWidget(self.count_label, 3, 1)
        
        # Uptime
        self.uptime_label = QLabel("0s")
        status_layout.addWidget(QLabel("Monitor Time:"), 4, 0)
        status_layout.addWidget(self.uptime_label, 4, 1)
        
        status_frame.setLayout(status_layout)
        parent_layout.addWidget(status_frame)
    
    def _apply_controller_style(self):
        """Apply exact controller calibration styling"""
        self.setStyleSheet("""
            QDialog {
                background-color: #1e3a5f;
                border-radius: 12px;
            }
            QWidget#content_widget {
                background-color: #2a2a2a;
                border-radius: 8px;
                margin: 8px;
            }
            QLabel#title_label {
                color: #ffffff;
                font-weight: bold;
                padding: 5px 0px;
            }
            QLabel#status_label {
                color: #b3b3b3;
                padding: 2px 0px;
            }
            QWidget#button_widget {
                background-color: #1e3a5f;
                border-radius: 0px;
            }
            QPushButton {
                background-color: #4a9eff;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #66b3ff;
            }
            QPushButton:pressed {
                background-color: #3385ff;
            }
            QFrame#status_frame {
                background-color: #1a1a1a;
                border: 1px solid #444444;
                border-radius: 6px;
                padding: 10px;
                margin: 10px 0px;
            }
            QLabel {
                color: #cccccc;
                font-size: 10px;
            }
        """)
    
    def _center_on_screen(self):
        """Center the dialog on screen"""
        if self.parent():
            parent_center = self.parent().geometry().center()
            self.move(parent_center.x() - self.width() // 2, 
                     parent_center.y() - self.height() // 2)
        else:
            # Center on primary screen
            screen = QApplication.primaryScreen().availableGeometry()
            x = (screen.width() - self.width()) // 2
            y = (screen.height() - self.height()) // 2
            self.move(x, y)
    
    def update_controller_input(self, input_data: ControllerInputData):
        """Update display with new controller input"""
        self.controller_widget.update_controller_data(input_data)
        self.input_count += 1
        self.last_update_time = time.time()
        
        # Update controller status
        if not self.controller_connected:
            self.controller_connected = True
            self.connection_label.setText("Controller: Connected")
            self.connection_label.setStyleSheet("color: #4a9eff; font-weight: bold;")
            self.status_label.setText("Live controller input detected")
    
    def set_controller_info(self, controller_name: str, connected: bool):
        """Set controller connection info"""
        self.controller_connected = connected
        self.controller_name = controller_name
        
        if connected:
            self.connection_label.setText(f"Controller: Connected")
            self.connection_label.setStyleSheet("color: #4a9eff; font-weight: bold;")
            self.type_label.setText(controller_name)
            self.status_label.setText("Monitoring live controller input...")
        else:
            self.connection_label.setText("Controller: Disconnected")
            self.connection_label.setStyleSheet("color: #ff6b6b; font-weight: bold;")
            self.type_label.setText("No Controller")
            self.status_label.setText("No controller detected")
    
    def _update_display_stats(self):
        """Update display statistics"""
        current_time = time.time()
        uptime = current_time - self.start_time
        
        # Calculate input rate
        if self.last_update_time > 0 and uptime > 1:
            rate = self.input_count / uptime
            self.rate_label.setText(f"{rate:.1f} Hz")
            self.controller_widget.set_input_rate(rate)
        
        # Update counters
        self.count_label.setText(str(self.input_count))
        
        # Format uptime
        if uptime < 60:
            uptime_str = f"{uptime:.0f}s"
        elif uptime < 3600:
            uptime_str = f"{uptime/60:.1f}m"
        else:
            uptime_str = f"{uptime/3600:.1f}h"
        self.uptime_label.setText(uptime_str)
        
        # Check for disconnection (no input for 3 seconds)
        if self.controller_connected and current_time - self.last_update_time > 3:
            self.set_controller_info("Timeout", False)
    
    def closeEvent(self, event):
        """Handle close event"""
        self.update_timer.stop()
        self.logger.info("Controller status splash closed")
        event.accept()


# Helper function for easy integration
def show_controller_status_splash(parent=None) -> ControllerStatusSplash:
    """
    Show controller status splash screen
    
    Args:
        parent: Parent widget for centering
        
    Returns:
        ControllerStatusSplash instance for connecting signals
    """
    splash = ControllerStatusSplash(parent)
    splash.show()
    return splash


# Test standalone
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    splash = ControllerStatusSplash()
    splash.show()
    sys.exit(app.exec())