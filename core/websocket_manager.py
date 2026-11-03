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

    Liveness: a backend that loses power or WiFi never sends a FIN/RST, so
    the socket would otherwise report "connected" until TCP retransmits
    finally give up. While connected, the manager pings the backend and
    treats any received traffic (pong or message) as proof of life. If
    nothing arrives for _DEAD_AFTER_S the socket is aborted and the normal
    reconnect path takes over.

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

    # Liveness watchdog
    _PING_INTERVAL_MS = 2000   # How often to ping and check for silence
    _DEAD_AFTER_S     = 6.0    # Silence longer than this means the link is dead
    _STALL_GRACE_S    = 4.0    # A tick this late means the event loop stalled, not the link
    _CONNECT_TIMEOUT_MS = 5000 # A connect attempt still pending after this is abandoned

    # Pending command queue limits
    _PENDING_MAX = 50          # Maximum queued commands while disconnected
    _PENDING_MAX_AGE = 10.0    # Seconds - older queued commands are stale and dropped

    # Command types that must never be queued for later delivery - replaying
    # stale realtime input after a reconnect would move the robot unexpectedly
    _NEVER_QUEUE_TYPES = {
        "steamdeck_controller",
        "controller_input",
        "frontend_controller",
        "people",
    }

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.logger = get_logger("websocket")
        self.url = url
        self.reconnect_timer = QTimer()
        self.reconnect_timer.setSingleShot(True)
        self.reconnect_timer.timeout.connect(self.attempt_reconnect)
        self.reconnect_attempts = 0
        self._shutting_down = False

        # Liveness watchdog state
        self._last_rx = time.monotonic()
        self._last_liveness_tick = self._last_rx
        self._liveness_timer = QTimer(self)
        self._liveness_timer.timeout.connect(self._check_liveness)
        self._connect_timer = QTimer(self)
        self._connect_timer.setSingleShot(True)
        self._connect_timer.timeout.connect(self._on_connect_timeout)

        # Per-type message handlers: msg_type -> list of callables(dict)
        self._type_handlers: Dict[str, List[Callable]] = {}

        # Commands queued while disconnected: (timestamp, json_string)
        self._pending_commands: List[tuple] = []

        self.connected.connect(self.on_connected)
        self.disconnected.connect(self.on_disconnected)
        self.error.connect(self.on_error)
        self.textMessageReceived.connect(self._dispatch_message)
        self.pong.connect(self._on_pong)

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
        self._last_rx = time.monotonic()
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
            self._connect_timer.start(self._CONNECT_TIMEOUT_MS)
        except Exception as e:
            self.logger.error(f"WebSocket connection error: {e}")
            self._schedule_reconnect()

    def on_connected(self):
        """Handle successful connection."""
        self.logger.info(f"WebSocket connected to {self.url}")
        self.reconnect_attempts = 0
        self.reconnect_timer.stop()
        self._connect_timer.stop()

        self._last_rx = time.monotonic()
        self._last_liveness_tick = self._last_rx
        self._liveness_timer.start(self._PING_INTERVAL_MS)

        # Disable Nagle algorithm so controller frames are sent immediately
        # rather than being batched — reduces latency by up to 40ms
        try:
            self.setSocketOption(
                QAbstractSocket.SocketOption.LowDelayOption, 1
            )
        except Exception as e:
            self.logger.debug(f"Could not set TCP_NODELAY: {e}")

        self._flush_pending_commands()

    def close(self, *args, **kwargs):
        """Close for good: an app shutdown must not reconnect"""
        self._shutting_down = True
        self.reconnect_timer.stop()
        self._connect_timer.stop()
        self._liveness_timer.stop()
        super().close(*args, **kwargs)

    def on_disconnected(self):
        """Handle disconnection."""
        self.logger.warning(f"WebSocket disconnected from {self.url}")
        self._liveness_timer.stop()
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
        if self._shutting_down or self.reconnect_timer.isActive():
            return

        delay = min(
            self._INITIAL_DELAY_MS * (2 ** self.reconnect_attempts),
            self._MAX_DELAY_MS
        )
        self.logger.info(f"Reconnecting in {delay / 1000:.1f}s (attempt {self.reconnect_attempts + 1})")
        self.reconnect_timer.start(delay)

    def attempt_reconnect(self):
        """Attempt to reconnect to WebSocket."""
        if self._shutting_down:
            return
        self.reconnect_attempts += 1
        self.logger.info(f"Reconnect attempt {self.reconnect_attempts}")

        # A previous attempt that never completed (no error, no response)
        # would otherwise stay in flight and block this one
        if self.state() != QAbstractSocket.SocketState.UnconnectedState:
            self.abort()
        self.connect_to_server()

    def _on_connect_timeout(self):
        """Abandon a connect attempt that is neither succeeding nor failing."""
        if self.state() in (
            QAbstractSocket.SocketState.ConnectedState,
            QAbstractSocket.SocketState.UnconnectedState,
        ):
            return
        self.logger.warning("Connection attempt timed out - retrying")
        self.abort()
        self._schedule_reconnect()

    # ---- Liveness ----

    def _on_pong(self, elapsed_ms, payload):
        """Any pong proves the backend is still answering."""
        self._last_rx = time.monotonic()

    def _check_liveness(self):
        """Ping the backend and drop the connection if it has gone silent."""
        if self.state() != QAbstractSocket.SocketState.ConnectedState:
            return

        now = time.monotonic()

        # If this tick fired late the event loop was blocked, so replies that
        # are already waiting in the socket have not been processed yet
        if now - self._last_liveness_tick > self._STALL_GRACE_S:
            self._last_rx = now
        self._last_liveness_tick = now

        silent_for = now - self._last_rx
        if silent_for > self._DEAD_AFTER_S:
            self.logger.warning(
                f"No traffic from backend for {silent_for:.1f}s - dropping stale connection"
            )
            self.abort()
            self._schedule_reconnect()
            return

        self.ping()

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

        # Releasing failsafe re-enables motion; replaying it after a
        # reconnect could start the robot moving unexpectedly
        if command_type == "failsafe" and not kwargs.get("state", False):
            self.logger.warning("Not connected - failsafe release dropped, not queued")
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