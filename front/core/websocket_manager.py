"""
WALL-E Control System - WebSocket Connection Management
"""

import json
from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWebSockets import QWebSocket
from PyQt6.QtNetwork import QAbstractSocket

from .logger import get_logger


class WebSocketManager(QWebSocket):
    """WebSocket connection manager with automatic reconnection"""
    
    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.logger = get_logger("websocket")
        self.url = url
        self.reconnect_timer = QTimer()
        self.reconnect_timer.timeout.connect(self.attempt_reconnect)
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        
        # Connection state management
        self.connected.connect(self.on_connected)
        self.disconnected.connect(self.on_disconnected)
        self.error.connect(self.on_error)
        
        self.connect_to_server()
    
    def connect_to_server(self):
        """Attempt to connect to WebSocket server"""
        try:
            if not self.url.startswith("ws://") and not self.url.startswith("wss://"):
                self.url = f"ws://{self.url}"
            self.open(QUrl(self.url))
        except Exception as e:
            self.logger.error(f"WebSocket connection error: {e}")
            self.start_reconnect_timer()
    
    def on_connected(self):
        """Handle successful connection"""
        self.logger.info(f"WebSocket connected to {self.url}")
        self.reconnect_attempts = 0
        self.reconnect_timer.stop()
    
    def on_disconnected(self):
        """Handle disconnection"""
        self.logger.warning(f"WebSocket disconnected from {self.url}")
        self.start_reconnect_timer()
    
    def on_error(self, error):
        """Handle connection error"""
        self.logger.error(f"WebSocket error: {error}")
        self.start_reconnect_timer()
    
    def start_reconnect_timer(self):
        """Start reconnection timer with exponential backoff"""
        if self.reconnect_attempts < self.max_reconnect_attempts:
            delay = min(1000 * (2 ** self.reconnect_attempts), 30000)
            self.reconnect_timer.start(delay)
        else:
            self.logger.error("Max reconnection attempts reached")
    
    def attempt_reconnect(self):
        """Attempt to reconnect to WebSocket"""
        self.reconnect_attempts += 1
        self.logger.info(f"Attempting to reconnect ({self.reconnect_attempts}/{self.max_reconnect_attempts})")
        self.connect_to_server()
    
    def send_safe(self, message: str) -> bool:
        """Safe message sending with connection check"""
        if self.state() == QAbstractSocket.SocketState.ConnectedState:
            if isinstance(message, dict):
                message = json.dumps(message)
            self.sendTextMessage(message)
            return True
        else:
            self.logger.warning("WebSocket not connected, message not sent")
            return False
    
    def send_command(self, command_type: str, **kwargs) -> bool:
        """Send a structured command message"""
        message = {"type": command_type, **kwargs}
        return self.send_safe(json.dumps(message))
    
    def is_connected(self) -> bool:
        """Check if WebSocket is currently connected"""
        return self.state() == QAbstractSocket.SocketState.ConnectedState