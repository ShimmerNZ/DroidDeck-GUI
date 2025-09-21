#!/usr/bin/env python3
"""
Image Processing Thread - Enhanced Gesture Detection
Handles camera stream processing and multiple gesture detection types.
ENHANCED: Added left hand, right hand, and both hands detection
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
    def __init__(self, frame=None, gesture_detected=None, pose_landmarks=None):
        self.frame = frame
        self.gesture_detected = gesture_detected  # None, "left_wave", "right_wave", or "hands_up"
        self.pose_landmarks = pose_landmarks

class ImageProcessingThread(QThread):
    """Thread for processing camera stream with enhanced gesture detection"""
    
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
        self.running = False
        self.should_connect = False
        if self.isRunning():
            self.quit()
            self.wait(5000)  # Wait up to 5 seconds
        self.logger.info("Image processing thread stopped")

    def set_tracking_enabled(self, enabled):
        """Enable/disable gesture tracking"""
        self.tracking_enabled = enabled
        self.logger.info(f"Gesture tracking {'enabled' if enabled else 'disabled'}")

    def run(self):
        """Main thread loop"""
        reconnect_delay = 1
        max_reconnect_delay = 30
        
        while self.running:
            if self.should_connect:
                success = self._connect_to_stream()
                if not success and self.running:
                    self.logger.warning(f"Reconnecting in {reconnect_delay} seconds...")
                    time.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                else:
                    reconnect_delay = 1
            else:
                time.sleep(0.1)

    def start_connecting(self):
        """Start connection attempts"""
        self.should_connect = True

    def stop_connecting(self):
        """Stop connection attempts"""
        self.should_connect = False

    @error_boundary
    def _connect_to_stream(self):
        """Connect to camera stream and process frames"""
        try:
            if not self.camera_url:
                self.logger.error("No camera URL configured")
                return False

            self.logger.info(f"Connecting to camera stream: {self.camera_url}")
            
            # Use requests with stream=True for MJPEG
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
                    bytes_buffer = bytes_buffer[end_idx + 2:]
                    
                    # Process JPEG frame
                    if self._process_jpeg_frame(jpeg_data):
                        frame_count_local += 1
                        current_time = time.time()
                        
                        # Emit stats every second
                        if current_time - last_stats_time >= 1.0:
                            fps = frame_count_local / (current_time - last_stats_time)
                            self.stats_updated.emit({
                                'fps': fps,
                                'frame_count': self.frame_count,
                                'running': True
                            })
                            frame_count_local = 0
                            last_stats_time = current_time
                        
                        # Limit frame rate to ~30 FPS
                        frame_delay = 1.0 / 30.0
                        elapsed = current_time - last_frame_time
                        if elapsed < frame_delay:
                            time.sleep(frame_delay - elapsed)
                        last_frame_time = time.time()
            
            return True
            
        except Exception as e:
            self.logger.error(f"MJPEG stream processing error: {e}")
            return False

    @error_boundary
    def _process_jpeg_frame(self, jpeg_data):
        """Process a single JPEG frame"""
        try:
            # Decode JPEG
            nparr = np.frombuffer(jpeg_data, np.uint8)
            frame_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame_bgr is None:
                return False
            
            # Convert BGR to RGB for processing
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            
            # Process frame for gestures
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
        """Process a single frame with enhanced gesture detection"""
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
            
            gesture_detected = None
            pose_landmarks = None
            
            # Gesture detection if available and tracking enabled
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
                        
                        # Enhanced gesture detection
                        gesture_detected = self._detect_gestures(results.pose_landmarks.landmark)
                        
                        # Draw gesture indicator if detected
                        if gesture_detected:
                            frame_bgr_for_text = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                            gesture_text = gesture_detected.replace("_", " ").upper() + " DETECTED!"
                            color = (0, 255, 0) if gesture_detected != "hands_up" else (255, 165, 0)  # Green for waves, orange for hands up
                            cv2.putText(frame_bgr_for_text, gesture_text, (10, 30), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
                            frame_rgb = cv2.cvtColor(frame_bgr_for_text, cv2.COLOR_BGR2RGB)
                
                except Exception as e:
                    self.logger.debug(f"Pose detection error: {e}")
            
            return ProcessedFrameData(
                frame=frame_rgb,
                gesture_detected=gesture_detected,
                pose_landmarks=pose_landmarks
            )
            
        except Exception as e:
            self.logger.error(f"Frame processing error: {e}")
            return None

    def _detect_gestures(self, landmarks):
        """
        Enhanced gesture detection for multiple gesture types
        Returns: None, "left_wave", "right_wave", or "hands_up"
        """
        try:
            # Get all required landmarks
            left_wrist = landmarks[self.mp_pose.PoseLandmark.LEFT_WRIST]
            left_elbow = landmarks[self.mp_pose.PoseLandmark.LEFT_ELBOW]
            left_shoulder = landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER]
            
            right_wrist = landmarks[self.mp_pose.PoseLandmark.RIGHT_WRIST]
            right_elbow = landmarks[self.mp_pose.PoseLandmark.RIGHT_ELBOW]
            right_shoulder = landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER]
            
            # Check visibility thresholds
            visibility_threshold = 0.5
            
            # Check if left arm is raised (waving position)
            left_arm_raised = (
                left_wrist.y < left_elbow.y < left_shoulder.y and
                left_wrist.visibility > visibility_threshold and
                left_elbow.visibility > visibility_threshold and
                left_shoulder.visibility > visibility_threshold
            )
            
            # Check if right arm is raised (waving position) 
            right_arm_raised = (
                right_wrist.y < right_elbow.y < right_shoulder.y and
                right_wrist.visibility > visibility_threshold and
                right_elbow.visibility > visibility_threshold and
                right_shoulder.visibility > visibility_threshold
            )
            
            # Determine gesture type based on arm positions
            if left_arm_raised and right_arm_raised:
                return "hands_up"
            elif left_arm_raised:
                return "right_wave"
            elif right_arm_raised:
                return "left_wave"
            else:
                return None
                
        except Exception as e:
            self.logger.debug(f"Gesture detection error: {e}")
            return None

    def stop(self):
        """Legacy method for compatibility - calls stop_processing"""
        self.stop_processing()

    def _emit_stats(self):
        """Legacy method for compatibility - stats are now emitted in _process_mjpeg_stream"""
        pass