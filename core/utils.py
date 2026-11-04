#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - Utility Functions and Decorators
"""

import gc
from functools import wraps
from typing import Any, Callable, Optional

from .logger import get_logger


def error_boundary(func: Callable) -> Callable:
    """Decorator to catch and log errors without crashing"""
    @wraps(func)
    def wrapper(*args, **kwargs) -> Optional[Any]:
        logger = get_logger("error")
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}")
            return None
    return wrapper


class MemoryManager:
    """Memory management utilities"""

    @staticmethod
    def cleanup_widgets(widget):
        """Recursively cleanup widget resources at shutdown"""
        if hasattr(widget, 'children'):
            for child in widget.children():
                if hasattr(child, 'deleteLater'):
                    child.deleteLater()
        gc.collect()

    @staticmethod
    def periodic_cleanup():
        """Periodic memory cleanup, called on a timer while the app is running"""
        gc.collect()
