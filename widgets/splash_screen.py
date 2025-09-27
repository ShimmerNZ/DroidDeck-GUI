"""
DroidDeck Splash Screen with Steam Deck-style loading animations and audio
"""

import sys
import os
from PyQt6.QtWidgets import QApplication, QSplashScreen, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QProgressBar
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty, QRect
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QPen, QBrush, QLinearGradient

# Import pygame for audio
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


def get_audio_path(filename: str) -> str:
    """Get audio file path from current theme directory"""
    try:
        from core.theme_manager import theme_manager
        theme_name = theme_manager.get_theme_name()
        audio_path = os.path.join("resources", "theme", theme_name, "audio", filename)
        
        if os.path.exists(audio_path):
            return audio_path
        else:
            # Fallback to default theme
            audio_path = os.path.join("resources", "theme", "Wall-e", "audio", filename)
            if os.path.exists(audio_path):
                return audio_path
    except Exception as e:
        print(f"Error getting audio path: {e}")
    
    return None


class DroidDeckSplashScreen(QSplashScreen):
    """Custom splash screen for DroidDeck application startup"""
    
    def __init__(self):
        # Get screen dimensions
        screen = QApplication.primaryScreen().geometry()
        
        # Scale splash to 40% of screen width, maintain aspect ratio
        splash_width = int(screen.width() * 0.4)
        splash_height = int(splash_width * 0.67)
        
        # Create a blank pixmap for the base
        pixmap = QPixmap(splash_width, splash_height)
        pixmap.fill(QColor("#0f1419"))
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
        QTimer.singleShot(1200, self._init_audio)
        
    def _init_audio(self):
        """Initialize pygame mixer and play startup sound"""
        if not PYGAME_AVAILABLE:
            return
        
        try:
            # Initialize pygame mixer if not already initialized
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            
            # Get startup audio path
            audio_path = get_audio_path("startup.mp3")
            
            if audio_path and os.path.exists(audio_path):
                pygame.mixer.music.load(audio_path)
                pygame.mixer.music.play()
        except Exception as e:
            print(f"Failed to play startup audio: {e}")
        
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
    
    def closeEvent(self, event):
        """Clean up audio when closing"""
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.music.stop()
            except:
                pass
        super().closeEvent(event)
    
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
        center_x = int(self.width() * 0.25)
        center_y = int(self.height() * 0.30)
        
        painter.save()
        painter.translate(center_x, center_y)
        painter.rotate(self.progress * 3)
        
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
        painter.setFont(QFont("Arial", int(self.height() * 0.08), QFont.Weight.Bold))
        title_rect = QRect(
            int(self.width() * 0.42),
            int(self.height() * 0.25),
            int(self.width() * 0.33),
            int(self.height() * 0.13)
        )
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft, "DROID DECK")
        
        # Subtitle
        painter.setPen(QColor("#87ceeb"))
        painter.setFont(QFont("Arial", int(self.height() * 0.035)))
        subtitle_rect = QRect(
            0,
            int(self.height() * 0.40),
            self.width(),
            int(self.height() * 0.075)
        )
        painter.drawText(subtitle_rect, Qt.AlignmentFlag.AlignCenter, "Professional Droid Control System")
        
        # Progress bar background
        progress_rect = QRect(
            int(self.width() * 0.17),
            int(self.height() * 0.55),
            int(self.width() * 0.67),
            int(self.height() * 0.02)
        )
        painter.setPen(QColor("#1e3a5f"))
        painter.setBrush(QColor("#0f1419"))
        painter.drawRoundedRect(progress_rect, 4, 4)
        
        # Progress bar fill
        fill_width = int((int(self.width() * 0.67) * min(self.progress, 100)) / 100)
        if fill_width > 4:
            fill_rect = QRect(
                int(self.width() * 0.17) + 2,
                int(self.height() * 0.55) + 2,
                fill_width - 4,
                int(self.height() * 0.01)
            )
            gradient = QLinearGradient(fill_rect.left(), 0, fill_rect.right(), 0)
            gradient.setColorAt(0, QColor("#1e90ff"))
            gradient.setColorAt(0.5, QColor("#00bfff"))
            gradient.setColorAt(1, QColor("#87ceeb"))
            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(fill_rect, 2, 2)
        
        # Status text
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Arial", int(self.height() * 0.03)))
        status_rect = QRect(
            0,
            int(self.height() * 0.625),
            self.width(),
            int(self.height() * 0.075)
        )
        current_msg = self.messages[min(self.current_message, len(self.messages) - 1)]
        painter.drawText(status_rect, Qt.AlignmentFlag.AlignCenter, current_msg)
        
        # Version
        painter.setPen(QColor("#6c757d"))
        painter.setFont(QFont("Arial", int(self.height() * 0.025)))
        version_rect = QRect(
            0,
            int(self.height() * 0.80),
            self.width(),
            int(self.height() * 0.05)
        )
        painter.drawText(version_rect, Qt.AlignmentFlag.AlignCenter, "Version 1.0 - Steam Deck Edition")


class DroidDeckShutdownSplash(QSplashScreen):
    """Shutdown splash screen for DroidDeck"""
    
    def __init__(self):
        # Get screen dimensions
        screen = QApplication.primaryScreen().geometry()
        
        # Scale splash to 35% of screen width
        splash_width = int(screen.width() * 0.35)
        splash_height = int(splash_width * 0.6)
        
        pixmap = QPixmap(splash_width, splash_height)
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
        QTimer.singleShot(1500, self._init_audio)
        
    def _init_audio(self):
        """Initialize pygame mixer and play shutdown sound"""
        if not PYGAME_AVAILABLE:
            return
        
        try:
            # Initialize pygame mixer if not already initialized
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            
            # Get shutdown audio path
            audio_path = get_audio_path("shutdown.mp3")
            
            if audio_path and os.path.exists(audio_path):
                pygame.mixer.music.load(audio_path)
                pygame.mixer.music.play()
        except Exception as e:
            print(f"Failed to play shutdown audio: {e}")
        
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
    
    def closeEvent(self, event):
        """Clean up audio when closing"""
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.music.stop()
            except:
                pass
        super().closeEvent(event)
        
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
        painter.setFont(QFont("Arial", int(self.height() * 0.08), QFont.Weight.Bold))
        title_rect = QRect(
            0,
            int(self.height() * 0.20),
            self.width(),
            int(self.height() * 0.13)
        )
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, "DROID DECK")
        
        # Shutdown message
        painter.setPen(QColor("#87ceeb"))
        painter.setFont(QFont("Arial", int(self.height() * 0.047)))
        subtitle_rect = QRect(
            0,
            int(self.height() * 0.37),
            self.width(),
            int(self.height() * 0.10)
        )
        painter.drawText(subtitle_rect, Qt.AlignmentFlag.AlignCenter, "Shutting Down...")
        
        # Progress bar
        progress_rect = QRect(
            int(self.width() * 0.15),
            int(self.height() * 0.53),
            int(self.width() * 0.70),
            int(self.height() * 0.02)
        )
        painter.setPen(QColor("#1e3a5f"))
        painter.setBrush(QColor("#0f1419"))
        painter.drawRoundedRect(progress_rect, 3, 3)
        
        # Progress fill
        fill_width = int((int(self.width() * 0.70) * self.progress) / 100)
        if fill_width > 0:
            fill_rect = QRect(
                int(self.width() * 0.15),
                int(self.height() * 0.53),
                fill_width,
                int(self.height() * 0.02)
            )
            painter.setBrush(QColor("#1e90ff"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(fill_rect, 3, 3)
        
        # Status text
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Arial", int(self.height() * 0.037)))
        if self.current_step < len(self.shutdown_steps):
            status_rect = QRect(
                0,
                int(self.height() * 0.63),
                self.width(),
                int(self.height() * 0.08)
            )
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