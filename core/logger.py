#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - Centralized Logging System
"""

import logging
from typing import Dict, List, Optional

LEVEL_NAMES = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG")

# Settings screen groups -> Deck logger names. Screens log under their class
# name in lower case. The backend has its own map for its modules.
LOG_GROUPS: Dict[str, List[str]] = {
    "camera": ["camera", "camerafeedscreen"],
    "servo": ["servo_screen", "servoconfigscreen"],
    "controller": ["controller", "controllerconfigscreen"],
    "scenes": ["home_screen", "homescreen", "scenescreen"],
    "attention": [],
    "network": ["network", "websocket", "http"],
}


def _level(name) -> int:
    name = str(name or "").upper()
    return getattr(logging, name) if name in LEVEL_NAMES else logging.INFO


class WalleLogger:
    """Centralized logging system with configurable debug levels"""
    _instance = None
    _loggers: Dict[str, logging.Logger] = {}
    _configured = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def configure(self, debug_level: str = "INFO", module_debug: Optional[Dict[str, str]] = None):
        """Set up log output once, then apply the levels"""
        if not self._configured:
            try:
                logging.basicConfig(
                    level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                    datefmt='%H:%M:%S'
                )
                self._configured = True
            except Exception as e:
                logging.basicConfig(level=logging.INFO)
                logging.error(f"Failed to configure logging: {e}")
        self.apply_levels(debug_level, module_debug)

    def apply_levels(self, debug_level: str = "INFO", module_debug: Optional[Dict[str, str]] = None):
        """Set the root level and each group's loggers; can be called again at any time.
        Keys that are not a group are treated as a logger name."""
        logging.getLogger().setLevel(_level(debug_level))
        for key, level_name in (module_debug or {}).items():
            level = _level(level_name)
            for name in LOG_GROUPS.get(key, [key]):
                logging.getLogger(name).setLevel(level)

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Get logger for specified module"""
        if name not in cls._loggers:
            cls._loggers[name] = logging.getLogger(name)
        return cls._loggers[name]
    
    def reset(self):
        """Reset logging configuration (for testing)"""
        self._configured = False
        self._loggers.clear()


# Global logger instance
logger_manager = WalleLogger()


def get_logger(name: str) -> logging.Logger:
    """Convenience function to get a logger"""
    return logger_manager.get_logger(name)