#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - WebSocket Connection Management
"""

import json
import time
from typing import Callable, Dict, List

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWebSockets import QWebSocket
from PyQt6.QtNetwork import QAbstractSocket

from .logger import get_logger


class WebSocketManager(QWebSocket):
    """WebSocket connection manager with automatic reconnection.

    Reconnection uses exponential backoff starting at 1s, capping at 5s.
    There is no attempt limit — the manager retries indefinitely until the
    backend is reachable again, which handles network switches cleanly.

    Message dispatch: incoming messages are parsed once and routed to
    handlers registered per message type via register_handler(). Screens
    receive already-parsed dicts, so each message is json.loads'd exactly
    once regardless of how many screens consume it.

    Pending commands: non-realtime commands sent while disconnected are
    queued and flushed on reconnect (bounded, with a freshness limit), so
    a config save during a brief WiFi blip is delivered instead of
    silently vanishing.
    """

    # Backoff config
    _INITIAL_DELAY_MS = 1000
    _MAX_DELAY_MS     = 5000

    # Pending command queue limits
    _PENDING_MAX = 50          # Maximum queued commands while disconnected
    _PENDING_MAX_AGE = 10.0    # Seconds - older queued commands are stale and dropped

    # Command types that must never be queued for later delivery - replaying
    # stale realtime input after a reconnect would move the robot unexpectedly
    _NEVER_QUEUE_TYPES = {
        "steamdeck_controller",
        "controller_input",
        "frontend_controller",
    }

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.logger = get_logger("websocket")
        self.url = url
        self.reconnect_timer = QTimer()
        self.reconnect_timer.setSingleShot(True)
        self.reconnect_timer.timeout.connect(self.attempt_reconnect)
        self.reconnect_attempts = 0

        # Per-type message handlers: msg_type -> list of callables(dict)
        self._type_handlers: Dict[str, List[Callable]] = {}

        # Commands queued while disconnected: (timestamp, json_string)
        self._pending_commands: List[tuple] = []

        self.connected.connect(self.on_connected)
        self.disconnected.connect(self.on_disconnected)
        self.error.connect(self.on_error)
        self.textMessageReceived.connect(self._dispatch_message)

        self.connect_to_server()

    # ---- Message dispatch ----

    def register_handler(self, msg_type: str, handler: Callable) -> None:
        """
        Register a handler for a message type. The handler is called with
        the parsed message dict whenever a message of that type arrives.
        """
        handlers = self._type_handlers.setdefault(msg_type, [])
        if handler not in handlers:
            handlers.append(handler)

    def unregister_handler(self, msg_type: str, handler: Callable) -> None:
        """Remove a previously registered handler."""
        handlers = self._type_handlers.get(msg_type)
        if handlers and handler in handlers:
            handlers.remove(handler)
            if not handlers:
                del self._type_handlers[msg_type]

    def _dispatch_message(self, message: str) -> None:
        """Parse an incoming message once and route it to registered handlers."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError as e:
            self.logger.warning(f"Bad JSON from backend: {e}")
            return

        msg_type = data.get("type")
        if not msg_type:
            return

        for handler in self._type_handlers.get(msg_type, ()):
            try:
                handler(data)
            except Exception as e:
                self.logger.error(f"Handler error for '{msg_type}': {e}")

    # ---- Connection management ----

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

        self._flush_pending_commands()

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

    # ---- Sending ----

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
        """
        Send a structured command message.

        If disconnected, non-realtime commands are queued and flushed on
        reconnect (provided the gap is short — see _PENDING_MAX_AGE), so
        actions like config saves are not silently lost during a WiFi blip.
        Realtime input types are never queued.

        Returns True if the command was sent immediately, False if it was
        queued or dropped.
        """
        message = json.dumps({"type": command_type, **kwargs})

        if self.state() == QAbstractSocket.SocketState.ConnectedState:
            return self.send_safe(message)

        if command_type in self._NEVER_QUEUE_TYPES:
            return False

        if len(self._pending_commands) >= self._PENDING_MAX:
            self.logger.warning(f"Pending command queue full - dropping '{command_type}'")
            return False

        self._pending_commands.append((time.monotonic(), message))
        self.logger.info(f"Not connected - queued '{command_type}' for delivery on reconnect")
        return False

    def _flush_pending_commands(self):
        """Send commands queued while disconnected, dropping stale ones."""
        if not self._pending_commands:
            return

        pending = self._pending_commands
        self._pending_commands = []

        now = time.monotonic()
        sent = 0
        dropped = 0
        for queued_at, message in pending:
            if now - queued_at > self._PENDING_MAX_AGE:
                dropped += 1
                continue
            if self.send_safe(message):
                sent += 1
            else:
                dropped += 1

        if sent or dropped:
            self.logger.info(f"Flushed pending commands: {sent} sent, {dropped} dropped as stale")

    def is_connected(self) -> bool:
        """Check if WebSocket is currently connected."""
        return self.state() == QAbstractSocket.SocketState.ConnectedState
