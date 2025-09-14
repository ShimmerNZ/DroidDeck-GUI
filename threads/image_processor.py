#!/usr/bin/env python3
"""
Image Processing Thread - Fixed for Camera Proxy MJPEG Stream
Handles camera stream processing and pose detection in dedicated thread.
FIXED: Better stream handling and error recovery
"""

import cv2
import time
import requests
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from core.logger import get_logger
from core.utils import error_boundary

class ProcessedFrameData:
    """Container for processed frame data"""
    def __init__(self, frame=None, wave_detected=False, pose_landmarks=None):
        self.frame = frame
        self.wave_detected = wave_detected
        self.pose_landmarks = pose_landmarks

class ImageProcessingThread(QThread):
    """Thread for processing camera stream with pose detection"""
    
    frame_processed = pyqtSignal(ProcessedFrameData)
    stats_updated = pyqtSignal(dict)
    
    def __init__(self, camera_url):
        super().__init__()
        self.logger = get_logger("camera")
        self.camera_url = camera_url
        self.running = False
        self.should_connect = False
        self.frame_count = 0
        self.last_stats_time = time.time()
        self.tracking_enabled = False
        
        self.logger.info(f"ImageProcessingThread initialized with URL: {camera_url}")
        
        # Initialize MediaPipe if available
        self.mp_pose = None
        self.pose = None
        self.mp_drawing = None
        self.pose_detection_available = False
        
        try:
            import mediapipe as mp
            self.mp_pose = mp.solutions.pose
            self.pose = self.mp_pose.Pose(
                static_image_mode=False,
                model_complexity=1,
                enable_segmentation=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
            self.mp_drawing = mp.solutions.drawing_utils
            self.pose_detection_available = True
            self.logger.info("MediaPipe pose detection initialized")
        except ImportError:
            self.logger.warning("MediaPipe not available - pose detection disabled")
        except Exception as e:
            self.logger.error(f"Failed to initialize MediaPipe: {e}")

    def start_processing(self):
        """Start the image processing thread"""
        if not self.running:
            self.running = True
            self.should_connect = True
            self.start()
            self.logger.info("Image processing thread started")

    def stop_processing(self):
        """Stop the image processing thread"""
        if self.running:
            self.running = False
            self.should_connect = False
            self.wait(3000)  # Wait up to 3 seconds for thread to finish
            self.logger.info("Image processing thread stopped")

    def start_connecting(self):
        """Signal the thread to start connecting to stream"""
        self.should_connect = True
        self.logger.info("Image thread: start connecting requested")

    def stop_connecting(self):
        """Signal the thread to stop connecting to stream"""
        self.should_connect = False
        self.logger.info("Image thread: stop connecting requested")

    def set_tracking_enabled(self, enabled):
        """Enable/disable pose tracking"""
        self.tracking_enabled = enabled
        self.logger.info(f"Pose tracking {'enabled' if enabled else 'disabled'}")

    @error_boundary
    def run(self):
        """Main processing loop with improved error handling"""
        self.logger.info(f"Starting camera stream processing from: {self.camera_url}")
        
        last_connection_attempt = 0
        connection_retry_delay = 2.0
        max_retry_delay = 30.0
        consecutive_failures = 0
        
        while self.running:
            try:
                current_time = time.time()
                
                if not self.should_connect:
                    time.sleep(0.1)
                    continue
                
                # Rate limit connection attempts
                if current_time - last_connection_attempt < connection_retry_delay:
                    time.sleep(0.1)
                    continue
                
                last_connection_attempt = current_time
                
                # FIXED: Check if camera proxy is available first
                if not self._check_camera_proxy_status():
                    self.logger.warning("Camera proxy not available, retrying...")
                    consecutive_failures += 1
                    connection_retry_delay = min(connection_retry_delay * 1.2, max_retry_delay)
                    continue
                
                # Connect to camera stream
                if self._connect_to_mjpeg_stream():
                    # Reset retry delay on successful connection
                    connection_retry_delay = 2.0
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    # Exponential backoff for connection retries
                    connection_retry_delay = min(connection_retry_delay * 1.5, max_retry_delay)
                    self.logger.warning(f"Stream connection failed, retrying in {connection_retry_delay:.1f}s")
                
                # If too many consecutive failures, wait longer
                if consecutive_failures > 10:
                    self.logger.error("Too many consecutive failures, waiting 30 seconds...")
                    time.sleep(30)
                    consecutive_failures = 0
                    connection_retry_delay = 2.0
                
            except Exception as e:
                self.logger.error(f"Image processing error: {e}")
                time.sleep(1)
        
        self.logger.info("Image processing thread finished")

    def _check_camera_proxy_status(self):
        """Check if camera proxy is running and responding"""
        if not self.camera_url:
            return False
            
        try:
            # Extract base URL from stream URL
            base_url = self.camera_url.replace("/stream", "")
            
            # Try to get status from camera proxy
            response = requests.get(f"{base_url}/stream/status", timeout=2)
            if response.status_code == 200:
                status = response.json()
                streaming_enabled = status.get("streaming_enabled", False)
                stream_active = status.get("stream_active", False)
                self.logger.debug(f"Proxy status: enabled={streaming_enabled}, active={stream_active}")
                return streaming_enabled or stream_active
        except requests.exceptions.RequestException:
            pass
        except Exception as e:
            self.logger.debug(f"Status check error: {e}")
        
        return False

    def _connect_to_mjpeg_stream(self):
        """FIXED: Connect to MJPEG stream using requests (not OpenCV)"""
        if not self.camera_url:
            self.logger.error("No camera URL configured")
            return False
        
        try:
            self.logger.info(f"Connecting to MJPEG stream: {self.camera_url}")
            
            # FIXED: Use requests with stream=True for MJPEG
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'WALL-E-ImageProcessor/1.0',
                'Accept': 'multipart/x-mixed-replace',
                'Connection': 'keep-alive'
            })
            
            response = session.get(
                self.camera_url,
                stream=True,
                timeout=10,
                allow_redirects=True
            )
            
            if response.status_code != 200:
                self.logger.error(f"HTTP {response.status_code} from camera stream")
                return False
            
            self.logger.info("Connected to MJPEG stream, processing frames...")
            
            # Process MJPEG stream
            return self._process_mjpeg_stream(response)
            
        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Stream connection error: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected stream error: {e}")
            return False

    def _process_mjpeg_stream(self, response):
        """Process MJPEG stream from requests response"""
        try:
            bytes_buffer = bytearray()
            frame_count_local = 0
            last_frame_time = time.time()
            last_stats_time = time.time()
            
            self.logger.info("Starting MJPEG frame processing...")
            
            for chunk in response.iter_content(chunk_size=8192):
                if not self.running or not self.should_connect:
                    self.logger.info("MJPEG processing stopped by request")
                    break
                
                bytes_buffer.extend(chunk)
                
                # Look for JPEG frames in the buffer
                while True:
                    # Find JPEG start marker
                    start_idx = bytes_buffer.find(b'\xff\xd8')
                    if start_idx == -1:
                        break
                    
                    # Find JPEG end marker
                    end_idx = bytes_buffer.find(b'\xff\xd9', start_idx)
                    if end_idx == -1:
                        break
                    
                    # Extract JPEG frame
                    jpeg_data = bytes_buffer[start_idx:end_idx + 2]
                    
                    # Remove processed data from buffer
                    del bytes_buffer[:end_idx + 2]
                    
                    # Decode and process frame
                    current_time = time.time()
                    
                    # Limit frame rate to prevent overwhelming (30 FPS max)
                    if current_time - last_frame_time >= 0.033:
                        if self._process_jpeg_frame(jpeg_data):
                            frame_count_local += 1
                            last_frame_time = current_time
                    
                    # Emit stats periodically (every 2 seconds)
                    if current_time - last_stats_time >= 2.0:
                        fps = frame_count_local / (current_time - last_stats_time) if (current_time - last_stats_time) > 0 else 0
                        stats = {
                            'fps': fps,
                            'frame_count': self.frame_count,
                            'pose_detection': self.pose_detection_available,
                            'tracking_enabled': self.tracking_enabled,
                            'camera_url': self.camera_url,
                            'running': self.running
                        }
                        self.stats_updated.emit(stats)
                        self.logger.debug(f"Stats: {fps:.1f} FPS, {self.frame_count} total frames")
                        last_stats_time = current_time
                        frame_count_local = 0
            
            return True
            
        except Exception as e:
            self.logger.error(f"MJPEG processing error: {e}")
            return False

    def _process_jpeg_frame(self, jpeg_data):
        """Process a JPEG frame from bytes"""
        try:
            # Decode JPEG to numpy array
            nparr = np.frombuffer(jpeg_data, np.uint8)
            frame_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame_bgr is None:
                self.logger.debug("Failed to decode JPEG frame")
                return False
            
            # Convert BGR to RGB for Qt display
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            
            # Process the frame (pose detection, etc.)
            processed_data = self._process_frame(frame_rgb)
            
            # Emit the processed frame
            if processed_data:
                self.frame_processed.emit(processed_data)
                self.frame_count += 1
                self.logger.debug(f"Processed frame {self.frame_count}: {frame_rgb.shape}")
                return True
            
        except Exception as e:
            self.logger.debug(f"JPEG frame processing error: {e}")
        
        return False

    @error_boundary
    def _process_frame(self, frame_rgb):
        """Process a single frame with pose detection"""
        try:
            if frame_rgb is None:
                return None
            
            # Resize frame if too large (for performance)
            height, width = frame_rgb.shape[:2]
            if width > 800:
                scale = 800 / width
                new_width = int(width * scale)
                new_height = int(height * scale)
                frame_rgb = cv2.resize(frame_rgb, (new_width, new_height))
            
            wave_detected = False
            pose_landmarks = None
            
            # Pose detection if available and tracking enabled
            if self.pose_detection_available and self.pose and self.tracking_enabled:
                try:
                    # MediaPipe expects RGB, and we already have RGB
                    results = self.pose.process(frame_rgb)
                    
                    if results.pose_landmarks:
                        pose_landmarks = results.pose_landmarks
                        
                        # Draw pose landmarks on frame (convert to BGR for drawing, then back to RGB)
                        frame_bgr_for_drawing = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                        self.mp_drawing.draw_landmarks(
                            frame_bgr_for_drawing, 
                            results.pose_landmarks, 
                            self.mp_pose.POSE_CONNECTIONS
                        )
                        frame_rgb = cv2.cvtColor(frame_bgr_for_drawing, cv2.COLOR_BGR2RGB)
                        
                        # Simple wave detection (check if right hand is raised)
                        landmarks = results.pose_landmarks.landmark
                        right_wrist = landmarks[self.mp_pose.PoseLandmark.RIGHT_WRIST]
                        right_elbow = landmarks[self.mp_pose.PoseLandmark.RIGHT_ELBOW]
                        right_shoulder = landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER]
                        
                        # Wave detected if wrist is above elbow and elbow is above shoulder
                        if (right_wrist.y < right_elbow.y < right_shoulder.y and 
                            right_wrist.visibility > 0.5):
                            wave_detected = True
                            
                            # Draw wave indicator
                            frame_bgr_for_text = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                            cv2.putText(frame_bgr_for_text, "WAVE DETECTED!", (10, 30), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                            frame_rgb = cv2.cvtColor(frame_bgr_for_text, cv2.COLOR_BGR2RGB)
                
                except Exception as e:
                    self.logger.debug(f"Pose detection error: {e}")
            
            return ProcessedFrameData(
                frame=frame_rgb,
                wave_detected=wave_detected,
                pose_landmarks=pose_landmarks
            )
            
        except Exception as e:
            self.logger.error(f"Frame processing error: {e}")
            return None

    def stop(self):
        """Legacy method for compatibility - calls stop_processing"""
        self.stop_processing()

    def _emit_stats(self):
        """Legacy method for compatibility - stats are now emitted in _process_mjpeg_stream"""
        pass