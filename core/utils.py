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
        """Recursively cleanup widget resources"""
        if hasattr(widget, 'children'):
            for child in widget.children():
                if hasattr(child, 'deleteLater'):
                    child.deleteLater()
        gc.collect()
    
    @staticmethod
    def periodic_cleanup():
        """Periodic memory cleanup"""
        gc.collect()


class MediaPipeManager:
    """Manages MediaPipe initialization and state"""
    
    def __init__(self):
        self.logger = get_logger("camera")
        self.mp_pose = None
        self.pose = None
        self._initialized = False
        self._available = self._check_availability()
    
    def _check_availability(self) -> bool:
        """Check if MediaPipe is available"""
        try:
            import cv2
            import mediapipe as mp
            return True
        except ImportError:
            self.logger.warning("OpenCV and/or MediaPipe not available")
            return False
    
    def initialize(self) -> bool:
        """Initialize MediaPipe for pose detection"""
        if not self._available:
            self.logger.warning("MediaPipe not available - camera tracking disabled")
            return False
        
        if self._initialized:
            return True
            
        try:
            import mediapipe as mp
            self.mp_pose = mp.solutions.pose
            self.pose = self.mp_pose.Pose(
                static_image_mode=False,
                model_complexity=1,
                enable_segmentation=False,
                min_detection_confidence=0.75,
                min_tracking_confidence=0.9
            )
            self._initialized = True
            self.logger.info("MediaPipe initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize MediaPipe: {e}")
            return False
    
    @property
    def is_available(self) -> bool:
        """Check if MediaPipe is available"""
        return self._available
    
    @property
    def is_initialized(self) -> bool:
        """Check if MediaPipe is initialized"""
        return self._initialized


# Global MediaPipe manager
mediapipe_manager = MediaPipeManager()