"""
WALL-E Control System - Centralized Logging System
"""

import logging
from enum import Enum
from typing import Dict, Optional


class LogLevel(Enum):
    """Available logging levels"""
    CRITICAL = 50
    ERROR = 40
    WARNING = 30
    INFO = 20
    DEBUG = 10


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
        """Configure logging system with specified levels"""
        if self._configured:
            return
            
        try:
            # Configure root logger
            root_level = getattr(logging, debug_level.upper(), logging.INFO)
            logging.basicConfig(
                level=root_level,
                format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                datefmt='%H:%M:%S'
            )
            
            # Configure module-specific loggers
            if module_debug:
                for module, level in module_debug.items():
                    logger = logging.getLogger(module)
                    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
                    
            self._configured = True
            
        except Exception as e:
            logging.basicConfig(level=logging.INFO)
            logging.error(f"Failed to configure logging: {e}")
    
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