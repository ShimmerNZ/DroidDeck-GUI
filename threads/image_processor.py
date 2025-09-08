"""
WALL-E Control System - Image Processing Thread (Cleaned)
"""

import time
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

import requests
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from core.logger import get_logger
from core.utils import mediapipe_manager


class ConnectionState(Enum):
    """Connection state enumeration"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class ProcessingConfig:
    """Image processing configuration"""
    TARGET_FPS: int = 15
    MAX_FRAME_WIDTH: int = 640
    STATS_FETCH_INTERVAL: float = 2.0
    
    # Connection settings
    STREAM_TIMEOUT: int = 5
    STATS_TIMEOUT: int = 2
    CHUNK_SIZE: int = 1024
    
    # Reconnection settings
    MAX_RECONNECT_ATTEMPTS: int = 5
    BASE_RECONNECT_DELAY: float = 1.0
    MAX_RECONNECT_DELAY: float = 30.0
    
    # Wave detection settings
    WAVE_TEXT_POSITION: Tuple[int, int] = (50, 50)
    WAVE_FONT_SCALE: float = 0.5
    WAVE_COLOR: Tuple[int, int, int] = (0, 255, 0)
    WAVE_THICKNESS: int = 1
    
    # Error frame settings
    ERROR_FRAME_SIZE: Tuple[int, int] = (320, 240)
    ERROR_TEXT_POSITION: Tuple[int, int] = (10, 120)
    ERROR_COLOR: Tuple[int, int, int] = (255, 255, 255)


@dataclass
class FrameResult:
    """Frame processing result"""
    frame: Optional[np.ndarray]
    wave_detected: bool
    stats: str
    processing_time_ms: float = 0.0
    frame_size: Optional[Tuple[int, int]] = None


class StreamProcessor:
    """Handles MJPEG stream processing"""
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        self.logger = get_logger("camera")
        self._bytes_buffer = b""
    
    def process_stream_chunk(self, chunk: bytes) -> Optional[np.ndarray]:
        """Process incoming stream chunk and extract JPEG frames"""
        if not chunk:
            return None
        
        self._bytes_buffer += chunk
        
        # Look for JPEG markers
        start_marker = self._bytes_buffer.find(b'\xff\xd8')  # JPEG start
        end_marker = self._bytes_buffer.find(b'\xff\xd9')    # JPEG end
        
        if start_marker != -1 and end_marker != -1 and end_marker > start_marker:
            # Extract JPEG data
            jpeg_data = self._bytes_buffer[start_marker:end_marker + 2]
            self._bytes_buffer = self._bytes_buffer[end_marker + 2:]
            
            return self._decode_jpeg(jpeg_data)
        
        # Prevent buffer from growing too large
        if len(self._bytes_buffer) > 1024 * 1024:  # 1MB limit
            self.logger.warning("Stream buffer overflow, clearing")
            self._bytes_buffer = b""
        
        return None
    
    def _decode_jpeg(self, jpeg_data: bytes) -> Optional[np.ndarray]:
        """Decode JPEG data to numpy array"""
        try:
            if not mediapipe_manager.is_available:
                return None
            
            import cv2
            img_array = np.frombuffer(jpeg_data, dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            return frame
            
        except Exception as e:
            self.logger.debug(f"JPEG decode error: {e}")
            return None
    
    def reset_buffer(self):
        """Reset the internal buffer"""
        self._bytes_buffer = b""


class PoseDetector:
    """Handles pose detection and wave recognition"""
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        self.logger = get_logger("camera")
    
    def detect_wave(self, frame: np.ndarray) -> Tuple[bool, np.ndarray]:
        """Detect wave gesture in frame and return annotated frame"""
        if not mediapipe_manager.is_initialized:
            return False, frame
        
        try:
            import cv2
            
            # Convert to RGB for MediaPipe
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Process with MediaPipe
            results = mediapipe_manager.pose.process(frame_rgb)
            
            wave_detected = False
            if results.pose_landmarks:
                landmarks = results.pose_landmarks.landmark
                
                # Get key points
                right_wrist = landmarks[mediapipe_manager.mp_pose.PoseLandmark.RIGHT_WRIST]
                right_shoulder = landmarks[mediapipe_manager.mp_pose.PoseLandmark.RIGHT_SHOULDER]
                
                # Simple wave detection: right wrist above right shoulder
                if right_wrist.y < right_shoulder.y and right_wrist.visibility > 0.5:
                    wave_detected = True
                    
                    # Annotate frame
                    cv2.putText(
                        frame_rgb, 
                        'Wave Detected', 
                        self.config.WAVE_TEXT_POSITION,
                        cv2.FONT_HERSHEY_SIMPLEX, 
                        self.config.WAVE_FONT_SCALE, 
                        self.config.WAVE_COLOR, 
                        self.config.WAVE_THICKNESS
                    )
            
            return wave_detected, frame_rgb
            
        except Exception as e:
            self.logger.debug(f"Pose detection error: {e}")
            return False, frame


class FrameProcessor:
    """Handles individual frame processing"""
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        self.logger = get_logger("camera")
        self.pose_detector = PoseDetector(config)
    
    def process_frame(self, frame: np.ndarray, tracking_enabled: bool) -> FrameResult:
        """Process a single frame"""
        start_time = time.time()
        
        try:
            if frame is None:
                return FrameResult(
                    frame=None,
                    wave_detected=False,
                    stats="No frame data",
                    processing_time_ms=0.0
                )
            
            # Resize frame if too large for performance
            processed_frame = self._resize_frame_if_needed(frame)
            
            # Pose detection and wave recognition
            wave_detected = False
            if tracking_enabled:
                wave_detected, processed_frame = self.pose_detector.detect_wave(processed_frame)
            else:
                # Convert BGR to RGB for display consistency
                try:
                    import cv2
                    processed_frame = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB)
                except ImportError:
                    pass  # Keep original frame if OpenCV not available
            
            processing_time = (time.time() - start_time) * 1000  # Convert to ms
            frame_size = (processed_frame.shape[1], processed_frame.shape[0]) if processed_frame is not None else None
            
            return FrameResult(
                frame=processed_frame,
                wave_detected=wave_detected,
                stats=f"Processing: {frame_size[0]}x{frame_size[1]}" if frame_size else "Processing",
                processing_time_ms=processing_time,
                frame_size=frame_size
            )
            
        except Exception as e:
            self.logger.error(f"Frame processing error: {e}")
            return self._create_error_frame(str(e), time.time() - start_time)
    
    def _resize_frame_if_needed(self, frame: np.ndarray) -> np.ndarray:
        """Resize frame if it exceeds maximum width"""
        try:
            height, width = frame.shape[:2]
            if width > self.config.MAX_FRAME_WIDTH:
                scale = self.config.MAX_FRAME_WIDTH / width
                import cv2
                new_width = int(width * scale)
                new_height = int(height * scale)
                return cv2.resize(frame, (new_width, new_height))
            return frame
        except Exception as e:
            self.logger.debug(f"Frame resize error: {e}")
            return frame
    
    def _create_error_frame(self, error_msg: str, processing_time: float) -> FrameResult:
        """Create an error frame with error message"""
        try:
            import cv2
            
            width, height = self.config.ERROR_FRAME_SIZE
            error_frame = np.zeros((height, width, 3), dtype=np.uint8)
            
            # Truncate error message to fit frame
            truncated_msg = f"Error: {error_msg[:25]}"
            
            cv2.putText(
                error_frame, 
                truncated_msg, 
                self.config.ERROR_TEXT_POSITION,
                cv2.FONT_HERSHEY_SIMPLEX, 
                self.config.WAVE_FONT_SCALE, 
                self.config.ERROR_COLOR, 
                self.config.WAVE_THICKNESS
            )
            
            return FrameResult(
                frame=error_frame,
                wave_detected=False,
                stats=f"Error: {error_msg}",
                processing_time_ms=processing_time * 1000,
                frame_size=self.config.ERROR_FRAME_SIZE
            )
            
        except ImportError:
            return FrameResult(
                frame=None,
                wave_detected=False,
                stats=f"Error: {error_msg}",
                processing_time_ms=processing_time * 1000
            )


class ImageProcessingThread(QThread):
    """Enhanced image processing thread with proper resource management"""
    
    # Signals for thread-safe communication
    frame_processed = pyqtSignal(object)  # FrameResult
    stats_updated = pyqtSignal(str)
    connection_state_changed = pyqtSignal(str)  # ConnectionState
    
    def __init__(self, camera_proxy_url: str, stats_url: Optional[str] = None, 
                 config: Optional[ProcessingConfig] = None):
        super().__init__()
        
        self.config = config or ProcessingConfig()
        self.logger = get_logger("camera")
        
        # URLs
        self.camera_proxy_url = camera_proxy_url
        self.stats_url = stats_url or self._build_stats_url(camera_proxy_url)
        
        # Thread control
        self.running = False
        self.tracking_enabled = False
        
        # Processing components
        self.stream_processor = StreamProcessor(self.config)
        self.frame_processor = FrameProcessor(self.config)
        
        # State tracking
        self.connection_state = ConnectionState.DISCONNECTED
        self.last_stats_update = 0.0
        self.frame_count = 0
        self.reconnect_attempts = 0
        
        self.logger.info(f"Image processor initialized - Camera: {self.camera_proxy_url}")
    
    def _build_stats_url(self, camera_url: str) -> str:
        """Build stats URL from camera URL"""
        try:
            # Extract base URL and port from camera URL
            import re
            match = re.match(r'https?://([^:]+):(\d+)', camera_url)
            if match:
                host, port = match.groups()
                return f"http://{host}:{port}/stats"
            return camera_url.replace('/stream', '/stats')
        except Exception:
            return "http://10.1.1.230:8081/stats"
    
    def set_tracking_enabled(self, enabled: bool):
        """Enable or disable pose tracking"""
        self.tracking_enabled = enabled
        if enabled:
            mediapipe_manager.initialize()
        self.logger.info(f"Tracking {'enabled' if enabled else 'disabled'}")
    
    def run(self):
        """Main thread execution with proper error handling and reconnection"""
        if not mediapipe_manager.is_available:
            self.logger.error("Camera processing disabled - OpenCV/MediaPipe not available")
            self.stats_updated.emit("OpenCV/MediaPipe not available")
            self.connection_state_changed.emit(ConnectionState.ERROR.value)
            return
        
        self.running = True
        self.logger.info("Image processing thread started")
        
        frame_interval = 1.0 / self.config.TARGET_FPS
        last_frame_time = 0.0
        
        while self.running:
            try:
                if self._should_attempt_connection():
                    self._attempt_connection()
                
                if self.connection_state == ConnectionState.CONNECTED:
                    current_time = time.time()
                    
                    # Process frames at target FPS
                    if current_time - last_frame_time >= frame_interval:
                        self._process_stream_data()
                        last_frame_time = current_time
                    
                    # Update stats periodically
                    if current_time - self.last_stats_update >= self.config.STATS_FETCH_INTERVAL:
                        self._update_camera_stats()
                        self.last_stats_update = current_time
                
                # Small sleep to prevent CPU spinning
                self.msleep(10)
                
            except Exception as e:
                self.logger.error(f"Unexpected error in processing loop: {e}")
                self._handle_connection_error(str(e))
                self.msleep(1000)  # Wait before retrying
        
        self.logger.info("Image processing thread stopped")
    
    def _should_attempt_connection(self) -> bool:
        """Check if we should attempt a connection"""
        return (self.connection_state in [ConnectionState.DISCONNECTED, ConnectionState.ERROR] and
                self.reconnect_attempts < self.config.MAX_RECONNECT_ATTEMPTS)
    
    def _attempt_connection(self):
        """Attempt to connect to the camera stream"""
        self.connection_state = ConnectionState.CONNECTING
        self.connection_state_changed.emit(ConnectionState.CONNECTING.value)
        
        delay = min(
            self.config.BASE_RECONNECT_DELAY * (2 ** self.reconnect_attempts),
            self.config.MAX_RECONNECT_DELAY
        )
        
        self.stats_updated.emit(f"Connecting... (Attempt {self.reconnect_attempts + 1}/{self.config.MAX_RECONNECT_ATTEMPTS})")
        
        try:
            self.stream = requests.get(
                self.camera_proxy_url, 
                stream=True, 
                timeout=self.config.STREAM_TIMEOUT
            )
            self.stream.raise_for_status()
            
            self.connection_state = ConnectionState.CONNECTED
            self.connection_state_changed.emit(ConnectionState.CONNECTED.value)
            self.stats_updated.emit("Stream connected")
            self.reconnect_attempts = 0
            self.stream_processor.reset_buffer()
            
            self.logger.info("Successfully connected to MJPEG stream")
            
        except Exception as e:
            self.reconnect_attempts += 1
            self._handle_connection_error(f"Connection failed: {e}")
            
            if self.reconnect_attempts < self.config.MAX_RECONNECT_ATTEMPTS:
                self.logger.warning(f"Connection attempt {self.reconnect_attempts} failed, retrying in {delay:.1f}s")
                time.sleep(delay)
            else:
                self.logger.error("Max reconnection attempts reached")
                self.stats_updated.emit("Connection failed - max attempts reached")
    
    def _process_stream_data(self):
        """Process incoming stream data"""
        if not hasattr(self, 'stream') or self.connection_state != ConnectionState.CONNECTED:
            return
        
        try:
            # Read chunk from stream
            chunk = self.stream.raw.read(self.config.CHUNK_SIZE)
            if not chunk:
                raise requests.exceptions.ConnectionError("Empty chunk received")
            
            # Process chunk to extract frame
            frame = self.stream_processor.process_stream_chunk(chunk)
            
            if frame is not None:
                # Process frame
                result = self.frame_processor.process_frame(frame, self.tracking_enabled)
                self.frame_processed.emit(result)
                self.frame_count += 1
                
        except Exception as e:
            self.logger.error(f"Stream processing error: {e}")
            self._handle_connection_error(f"Stream error: {e}")
    
    def _update_camera_stats(self):
        """Update camera statistics"""
        try:
            response = requests.get(self.stats_url, timeout=self.config.STATS_TIMEOUT)
            if response.status_code == 200:
                stats_data = response.json()
                fps = stats_data.get("fps", 0)
                frame_count = stats_data.get("frame_count", 0)
                latency = stats_data.get("latency", 0)
                status = stats_data.get("status", "unknown")
                
                stats_text = f"FPS: {fps}, Frames: {frame_count}, Latency: {latency}ms, Status: {status}"
                self.stats_updated.emit(stats_text)
            else:
                self.stats_updated.emit(f"Stats Error: HTTP {response.status_code}")
                
        except Exception as e:
            self.logger.debug(f"Stats fetch error: {e}")
            # Don't emit stats errors as they're not critical
    
    def _handle_connection_error(self, error_msg: str):
        """Handle connection errors"""
        self.connection_state = ConnectionState.ERROR
        self.connection_state_changed.emit(ConnectionState.ERROR.value)
        
        if hasattr(self, 'stream'):
            try:
                self.stream.close()
            except:
                pass
            delattr(self, 'stream')
        
        self.stats_updated.emit(f"Error: {error_msg[:50]}")
    
    def stop(self):
        """Stop the image processing thread with proper cleanup"""
        self.logger.info("Stopping image processing thread")
        self.running = False
        
        # Close stream connection
        if hasattr(self, 'stream'):
            try:
                self.stream.close()
            except:
                pass
        
        # Wait for thread to finish with timeout
        if not self.wait(3000):  # 3 second timeout
            self.logger.warning("Image processing thread did not stop gracefully")
            self.terminate()
            self.wait(1000)  # Give it 1 more second after terminate
        
        self.logger.info("Image processing thread stopped")