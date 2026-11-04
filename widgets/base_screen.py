#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - Base Screen Components
"""

from abc import ABC, abstractmethod
from PyQt6.QtWidgets import QWidget

from core.logger import get_logger
from core.utils import error_boundary


# Create a compatible metaclass for PyQt6 + ABC
class WidgetABCMeta(type(QWidget), type(ABC)):
    pass


class BaseScreen(QWidget, ABC, metaclass=WidgetABCMeta):
    """Abstract base class for all application screens.

    WebSocket messages are consumed through the central dispatcher on the
    WebSocketManager: subscribe() registers a handler that is always active,
    while subscribe_while_visible() registers a handler only while the
    screen is shown - high-rate types like telemetry then cost nothing on
    hidden screens. Handlers receive parsed dicts.
    """

    def __init__(self, websocket=None):
        super().__init__()
        self.logger = get_logger(self.__class__.__name__.lower())
        self.websocket = websocket
        self._ws_subscriptions = []           # (msg_type, handler) always active
        self._ws_visible_subscriptions = []   # (msg_type, handler) active while shown
        self._visible_handlers_registered = False
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        self._setup_screen()

    @abstractmethod
    def _setup_screen(self):
        """Setup screen-specific UI components"""
        pass

    def subscribe(self, msg_type: str, handler):
        """Register a message handler that stays active regardless of visibility."""
        if not self.websocket or not hasattr(self.websocket, "register_handler"):
            return
        self.websocket.register_handler(msg_type, handler)
        self._ws_subscriptions.append((msg_type, handler))

    def subscribe_while_visible(self, msg_type: str, handler):
        """Register a message handler that is only active while the screen is shown."""
        self._ws_visible_subscriptions.append((msg_type, handler))

    def showEvent(self, event):
        """Activate visibility-scoped message handlers."""
        if (not self._visible_handlers_registered and self.websocket
                and hasattr(self.websocket, "register_handler")):
            for msg_type, handler in self._ws_visible_subscriptions:
                self.websocket.register_handler(msg_type, handler)
            self._visible_handlers_registered = True
        super().showEvent(event)

    def hideEvent(self, event):
        """Deactivate visibility-scoped message handlers."""
        if (self._visible_handlers_registered and self.websocket
                and hasattr(self.websocket, "unregister_handler")):
            for msg_type, handler in self._ws_visible_subscriptions:
                self.websocket.unregister_handler(msg_type, handler)
            self._visible_handlers_registered = False
        super().hideEvent(event)

    def cleanup(self):
        """Override in subclasses for custom cleanup"""
        pass
    
    @error_boundary
    def send_websocket_message(self, message_type: str, **kwargs) -> bool:
        """Send message via WebSocket if available"""
        if self.websocket and self.websocket.is_connected():
            return self.websocket.send_command(message_type, **kwargs)
        else:
            self.logger.warning(f"Cannot send {message_type}: WebSocket not connected")
            return False