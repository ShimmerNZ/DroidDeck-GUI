#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - WebSocket Connection Management
"""

import json
from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWebSockets import QWebSocket
from PyQt6.QtNetwork import QAbstractSocket

from .logger import get_logger


class WebSocketManager(QWebSocket):
    """WebSocket connection manager with automatic reconnection.

    Reconnection uses exponential backoff starting at 1s, capping at 30s.
    There is no attempt limit — the manager retries indefinitely until the
    backend is reachable again, which handles network switches cleanly.
    """

    # Backoff config
    _INITIAL_DELAY_MS = 1000
    _MAX_DELAY_MS     = 5000

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.logger = get_logger("websocket")
        self.url = url
        self.reconnect_timer = QTimer()
        self.reconnect_timer.setSingleShot(True)
        self.reconnect_timer.timeout.connect(self.attempt_reconnect)
        self.reconnect_attempts = 0

        self.connected.connect(self.on_connected)
        self.disconnected.connect(self.on_disconnected)
        self.error.connect(self.on_error)

        self.connect_to_server()

    def connect_to_server(self):
        """Attempt to connect to WebSocket server."""
        try:
            if not self.url.startswith("ws://") and not self.url.startswith("wss://"):
                self.url = f"ws://{self.url}"
            self.open(QUrl(self.url))
        except Exception as e:
            self.logger.error(f"WebSocket connection error: {e}")
            self._schedule_reconnect()

    def on_connected(self):
        """Handle successful connection."""
        self.logger.info(f"WebSocket connected to {self.url}")
        self.reconnect_attempts = 0
        self.reconnect_timer.stop()

        # Disable Nagle algorithm so controller frames are sent immediately
        # rather than being batched — reduces latency by up to 40ms
        try:
            self.setSocketOption(
                QAbstractSocket.SocketOption.LowDelayOption, 1
            )
        except Exception as e:
            self.logger.debug(f"Could not set TCP_NODELAY: {e}")

    def on_disconnected(self):
        """Handle disconnection."""
        self.logger.warning(f"WebSocket disconnected from {self.url}")
        self._schedule_reconnect()

    def on_error(self, error):
        """Handle connection error."""
        self.logger.error(f"WebSocket error: {error}")
        self._schedule_reconnect()

    def _schedule_reconnect(self):
        """Schedule the next reconnect attempt with exponential backoff.

        No attempt limit — retries indefinitely so network switches are
        recovered automatically without needing to restart the app.
        """
        if self.reconnect_timer.isActive():
            return

        delay = min(
            self._INITIAL_DELAY_MS * (2 ** self.reconnect_attempts),
            self._MAX_DELAY_MS
        )
        self.logger.info(f"Reconnecting in {delay / 1000:.1f}s (attempt {self.reconnect_attempts + 1})")
        self.reconnect_timer.start(delay)

    def attempt_reconnect(self):
        """Attempt to reconnect to WebSocket."""
        self.reconnect_attempts += 1
        self.logger.info(f"Reconnect attempt {self.reconnect_attempts}")
        self.connect_to_server()

    def send_safe(self, message: str) -> bool:
        """Safe message sending with connection check."""
        if self.state() == QAbstractSocket.SocketState.ConnectedState:
            if isinstance(message, dict):
                message = json.dumps(message)
            try:
                self.sendTextMessage(message)
                return True
            except Exception as e:
                self.logger.error(f"sendTextMessage failed: {e}")
                return False
        else:
            self.logger.warning(f"NOT CONNECTED - state is {self.state()}, not sending")
            return False

    def send_command(self, command_type: str, **kwargs) -> bool:
        """Send a structured command message."""
        message = {"type": command_type, **kwargs}
        return self.send_safe(json.dumps(message))

    def is_connected(self) -> bool:
        """Check if WebSocket is currently connected."""
        return self.state() == QAbstractSocket.SocketState.ConnectedState