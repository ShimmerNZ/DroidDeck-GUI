"""
DroidDeck Splash Screen with Steam Deck-style loading animations - Complete Version
"""

import sys
from PyQt6.QtWidgets import QApplication, QSplashScreen, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QProgressBar
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty, QRect
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QPen, QBrush, QLinearGradient

class DroidDeckSplashScreen(QSplashScreen):
    """Custom splash screen for DroidDeck application startup"""
    
    def __init__(self):
        # Create a blank pixmap for the base
        pixmap = QPixmap(600, 400)
        pixmap.fill(QColor("#0f1419"))  # Steam Deck dark background
        super().__init__(pixmap)
        
        # Make splash stay on top and come to front
        self.setWindowFlags(Qt.WindowType.SplashScreen | 
                           Qt.WindowType.WindowStaysOnTopHint)
        
        # Initialize messages FIRST
        self.messages = [
            "Initializing DroidDeck...",
            "Loading configurations...",
            "Establishing connections...",
            "Loading interface modules...",
            "Configuring navigation...",
            "Finalizing DroidDeck..."
        ]
        self.current_message = 0
        self.current_step = 0
        self.progress = 0
        
        # Center on screen
        self._center_on_screen()
        
        # Force to front after showing
        QTimer.singleShot(100, self._bring_to_front)
        
    def _center_on_screen(self):
        """Center splash screen on display"""
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def _bring_to_front(self):
        """Bring splash screen to front"""
        self.show()
        self.raise_()
        self.activateWindow()
        
    def update_progress(self, step, message):
        """Update progress based on actual initialization steps"""
        self.current_step = step
        self.progress = int((step / len(self.messages)) * 100)
        self.current_message = min(step, len(self.messages) - 1)
        
        # Update the message if provided
        if message and step < len(self.messages):
            self.messages[step] = message
            
        # Force repaint
        self.update()
        QApplication.processEvents()
        
    def set_message(self, message):
        """Set custom message without changing step"""
        if self.current_message < len(self.messages):
            self.messages[self.current_message] = message
        self.update()
        QApplication.processEvents()
    
    def finish_loading(self):
        """Mark loading as complete"""
        self.progress = 100
        self.current_message = len(self.messages) - 1
        self.messages[-1] = "DroidDeck Ready!"
        self.update()
        QApplication.processEvents()
        
        # Close after a brief delay
        QTimer.singleShot(2000, self.close)
    
    def paintEvent(self, event):
        """Custom paint event to draw the splash screen"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw background gradient
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor("#0f1419"))
        gradient.setColorAt(1, QColor("#1e2328"))
        painter.fillRect(self.rect(), QBrush(gradient))
        
        # Draw servo icon (simplified rotating animation)
        self._draw_servo_icon(painter)
        
        # Draw the UI elements
        self._draw_ui_elements(painter)
    
    def _draw_servo_icon(self, painter):
        """Draw animated servo icon"""
        center_x = self.width() // 2 - 100
        center_y = 120
        
        painter.save()
        painter.translate(center_x, center_y)
        painter.rotate(self.progress * 3)  # Rotate based on progress
        
        # Draw servo horn style icon
        painter.setPen(QPen(QColor("#1e90ff"), 3))
        painter.setBrush(QBrush(QColor("#1e90ff")))
        
        # Central circle
        painter.drawEllipse(-8, -8, 16, 16)
        
        # Servo arms
        for angle in [0, 45, 90, 135, 180, 225, 270, 315]:
            painter.save()
            painter.rotate(angle)
            painter.drawRect(-2, -25, 4, 20)
            painter.restore()
        
        painter.restore()
    
    def _draw_ui_elements(self, painter):
        """Draw UI elements manually"""
        # Title
        painter.setPen(QColor("#1e90ff"))
        painter.setFont(QFont("Arial", 32, QFont.Weight.Bold))
        title_rect = QRect(self.width() // 2 - 50, 100, 200, 50)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft, "DROID DECK")
        
        # Subtitle
        painter.setPen(QColor("#87ceeb"))
        painter.setFont(QFont("Arial", 14))
        subtitle_rect = QRect(0, 160, self.width(), 30)
        painter.drawText(subtitle_rect, Qt.AlignmentFlag.AlignCenter, "Professional Droid Control System")
        
        # Progress bar background
        progress_rect = QRect(100, 220, 400, 8)
        painter.setPen(QColor("#1e3a5f"))
        painter.setBrush(QColor("#0f1419"))
        painter.drawRoundedRect(progress_rect, 4, 4)
        
        # Progress bar fill
        fill_width = int((400 * min(self.progress, 100)) / 100)
        if fill_width > 4:
            fill_rect = QRect(102, 222, fill_width - 4, 4)
            gradient = QLinearGradient(fill_rect.left(), 0, fill_rect.right(), 0)
            gradient.setColorAt(0, QColor("#1e90ff"))
            gradient.setColorAt(0.5, QColor("#00bfff"))
            gradient.setColorAt(1, QColor("#87ceeb"))
            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(fill_rect, 2, 2)
        
        # Status text
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Arial", 12))
        status_rect = QRect(0, 250, self.width(), 30)
        current_msg = self.messages[min(self.current_message, len(self.messages) - 1)]
        painter.drawText(status_rect, Qt.AlignmentFlag.AlignCenter, current_msg)
        
        # Version
        painter.setPen(QColor("#6c757d"))
        painter.setFont(QFont("Arial", 10))
        version_rect = QRect(0, 320, self.width(), 20)
        painter.drawText(version_rect, Qt.AlignmentFlag.AlignCenter, "Version 1.0 - Steam Deck Edition")


class DroidDeckShutdownSplash(QSplashScreen):
    """Shutdown splash screen for DroidDeck"""
    
    def __init__(self):
        pixmap = QPixmap(500, 300)
        pixmap.fill(QColor("#0f1419"))
        super().__init__(pixmap)
        
        # Make it stay on top
        self.setWindowFlags(Qt.WindowType.SplashScreen | 
                           Qt.WindowType.WindowStaysOnTopHint)
        
        self.shutdown_steps = [
            "Saving configurations...",
            "Closing connections...", 
            "Stopping background processes...",
            "Cleaning up resources...",
            "DroidDeck shutdown complete"
        ]
        self.current_step = 0
        self.progress = 0
        
        self._center_on_screen()
        
    def _center_on_screen(self):
        """Center shutdown splash on screen"""
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
    
    def update_shutdown_progress(self, step):
        """Update shutdown progress"""
        self.current_step = min(step, len(self.shutdown_steps) - 1)
        self.progress = int((step / len(self.shutdown_steps)) * 100)
        self.update()
        QApplication.processEvents()
        
    def paintEvent(self, event):
        """Draw shutdown splash"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Background gradient
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor("#0f1419"))
        gradient.setColorAt(1, QColor("#1e2328"))
        painter.fillRect(self.rect(), QBrush(gradient))
        
        # Title
        painter.setPen(QColor("#1e90ff"))
        painter.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        title_rect = QRect(0, 60, self.width(), 40)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, "DROID DECK")
        
        # Shutdown message
        painter.setPen(QColor("#87ceeb"))
        painter.setFont(QFont("Arial", 14))
        subtitle_rect = QRect(0, 110, self.width(), 30)
        painter.drawText(subtitle_rect, Qt.AlignmentFlag.AlignCenter, "Shutting Down...")
        
        # Progress bar
        progress_rect = QRect(75, 160, 350, 6)
        painter.setPen(QColor("#1e3a5f"))
        painter.setBrush(QColor("#0f1419"))
        painter.drawRoundedRect(progress_rect, 3, 3)
        
        # Progress fill
        fill_width = int((350 * self.progress) / 100)
        if fill_width > 0:
            fill_rect = QRect(75, 160, fill_width, 6)
            painter.setBrush(QColor("#1e90ff"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(fill_rect, 3, 3)
        
        # Status text
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Arial", 11))
        if self.current_step < len(self.shutdown_steps):
            status_rect = QRect(0, 190, self.width(), 25)
            painter.drawText(status_rect, Qt.AlignmentFlag.AlignCenter, 
                           self.shutdown_steps[self.current_step])


# Function to show shutdown splash
def show_shutdown_splash():
    """Show shutdown splash screen"""
    splash = DroidDeckShutdownSplash()
    splash.show()
    splash.raise_()
    splash.activateWindow()
    return splash