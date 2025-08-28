"""
WALL-E Control System - Image Processing Thread
"""

import time
import requests
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from core.logger import get_logger
from core.utils import mediapipe_manager


class ImageProcessingThread(QThread):
    """Thread for processing camera stream and pose detection"""
    
    frame_processed = pyqtSignal(object)
    stats_updated = pyqtSignal(str)

    def __init__(self, camera_proxy_url: str, stats_url: str = None):
        super().__init__()
        self.logger = get_logger("camera")
        self.camera_proxy_url = camera_proxy_url
        self.stats_url = stats_url or "http://10.1.1.230:8081/stats"
        
        # Thread control
        self.running = False
        self.tracking_enabled = False
        
        # Performance settings
        self.target_fps = 15
        self.frame_skip_count = 0
        self.last_stats_update = 0
        self.stats_fetch_interval = 2.0
        
        self.logger.info(f"Image processor initialized with URL: {camera_proxy_url}")

    def set_tracking_enabled(self, enabled: bool):
        """Enable or disable pose tracking"""
        self.tracking_enabled = enabled
        if enabled:
            mediapipe_manager.initialize()
        self.logger.info(f"Tracking enabled: {enabled}")

    def fetch_camera_stats(self) -> str:
        """Fetch camera statistics from proxy server"""
        try:
            response = requests.get(self.stats_url, timeout=2)
            if response.status_code == 200:
                stats_data = response.json()
                fps = stats_data.get("fps", 0)
                frame_count = stats_data.get("frame_count", 0)
                latency = stats_data.get("latency", 0)
                status = stats_data.get("status", "unknown")
                return f"FPS: {fps}, Frames: {frame_count}, Latency: {latency}ms, Status: {status}"
            else:
                return f"Stats Error: HTTP {response.status_code}"
        except Exception as e:
            return f"Stats Error: {str(e)[:50]}"

    def run(self):
        """Main thread execution - processes MJPEG stream"""
        if not mediapipe_manager.is_available:
            self.logger.error("Camera processing disabled - OpenCV not available")
            self.stats_updated.emit("OpenCV not available")
            return

        self.running = True
        frame_time = 1.0 / self.target_fps
        last_process_time = time.time()
        reconnect_attempts = 0
        max_retries = 5
        reconnect_delay = 3

        while self.running and reconnect_attempts < max_retries:
            try:
                self.stats_updated.emit(f"Connecting to stream... (Attempt {reconnect_attempts + 1})")
                stream = requests.get(self.camera_proxy_url, stream=True, timeout=5)
                stream.raise_for_status()
                self.logger.info("Connected to MJPEG stream")
                self.stats_updated.emit("Stream connected")
                reconnect_attempts = 0

                bytes_data = b""
                for chunk in stream.iter_content(chunk_size=1024):
                    if not self.running:
                        break

                    bytes_data += chunk
                    a = bytes_data.find(b'\xff\xd8')
                    b = bytes_data.find(b'\xff\xd9')

                    if a != -1 and b != -1:
                        jpg = bytes_data[a:b+2]
                        bytes_data = bytes_data[b+2:]

                        if not mediapipe_manager.is_available:
                            continue
                            
                        img_array = np.frombuffer(jpg, dtype=np.uint8)
                        
                        try:
                            import cv2
                            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                        except ImportError:
                            self.logger.error("OpenCV not available for frame decoding")
                            continue

                        if frame is not None:
                            current_time = time.time()
                            if current_time - last_process_time >= frame_time:
                                processed_frame = self.process_frame(frame)
                                self.frame_processed.emit(processed_frame)
                                last_process_time = current_time

                            if current_time - self.last_stats_update >= self.stats_fetch_interval:
                                stats_text = self.fetch_camera_stats()
                                self.stats_updated.emit(stats_text)
                                self.last_stats_update = current_time
                                
            except Exception as e:
                reconnect_attempts += 1
                self.logger.error(f"MJPEG stream error: {e}")
                self.stats_updated.emit(f"Stream error: {str(e)} - retrying in {reconnect_delay}s")
                time.sleep(reconnect_delay)

        if reconnect_attempts >= max_retries:
            self.stats_updated.emit("Failed to connect after multiple attempts")
            self.logger.error("Max reconnect attempts reached")

    def process_frame(self, frame) -> dict:
        """Process individual frame for pose detection"""
        try:
            if not mediapipe_manager.is_available:
                return {
                    'frame': None,
                    'wave_detected': False,
                    'stats': "OpenCV not available"
                }
            
            import cv2
            
            # Resize frame if too large
            height, width = frame.shape[:2]
            if width > 640:
                scale = 640 / width
                frame = cv2.resize(frame, (int(width * scale), int(height * scale)))

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            wave_detected = False

            # Pose detection if tracking enabled
            if self.tracking_enabled and mediapipe_manager.is_initialized:
                try:
                    results = mediapipe_manager.pose.process(frame_rgb)
                    if results.pose_landmarks:
                        lm = results.pose_landmarks.landmark
                        right_wrist = lm[mediapipe_manager.mp_pose.PoseLandmark.RIGHT_WRIST]
                        right_shoulder = lm[mediapipe_manager.mp_pose.PoseLandmark.RIGHT_SHOULDER]
                        
                        # Simple wave detection: right wrist above right shoulder
                        if right_wrist.y < right_shoulder.y:
                            wave_detected = True
                            cv2.putText(frame_rgb, 'Wave Detected', (50, 50),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                except Exception as pose_error:
                    self.logger.debug(f"Pose detection error: {pose_error}")

            return {
                'frame': frame_rgb,
                'wave_detected': wave_detected,
                'stats': f"Processing: {frame_rgb.shape[1]}x{frame_rgb.shape[0]}"
            }
            
        except Exception as e:
            self.logger.error(f"Frame processing error: {e}")
            
            # Return error frame
            try:
                import cv2
                black_frame = np.zeros((240, 320, 3), dtype=np.uint8)
                cv2.putText(black_frame, f"Error: {str(e)[:30]}", (10, 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                return {
                    'frame': black_frame, 
                    'wave_detected': False, 
                    'stats': f"Error: {e}"
                }
            except ImportError:
                return {
                    'frame': None,
                    'wave_detected': False,
                    'stats': f"Error: {e}"
                }

    def stop(self):
        """Stop the image processing thread"""
        self.logger.info("Stopping image processing thread")
        self.running = False
        self.quit()
        self.wait(3000)  # Wait up to 3 seconds for thread to finish