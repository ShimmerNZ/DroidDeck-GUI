#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Image Processing Thread - Camera stream and gesture detection.
MediaPipe is imported lazily on first tracking enable so normal camera use
has no startup cost and does not require MediaPipe to be installed.
"""

import cv2
import time
import threading
import requests
import numpy as np
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal
from core.logger import get_logger
from core.utils import error_boundary
from threads.person_tracker import PersonTracker

# Overlay colours are RGB, matching the frame buffer
PERSON_BOX_COLOR = (230, 230, 230)
FOCUS_BOX_COLOR = (255, 190, 0)
ATTENTION_STATE_TIMEOUT = 5.0

# Person/body detection (separate from the single-person gesture pose below):
# a multi-pose MediaPipe Tasks model, tracking up to this many people at once
POSE_LANDMARKER_MODEL_FILENAME = "pose_landmarker_lite.task"
MAX_TRACKED_PEOPLE = 4
# A landmark counts toward a person's bounding box only above this visibility
MIN_LANDMARK_VISIBILITY = 0.5
# A pose needs at least this many visible landmarks to count as a person at all
MIN_VISIBLE_LANDMARKS = 4
# Elbow, wrist and hand landmarks (MediaPipe pose indices 13-22) are left out
# of a person's bounding box: raised or outstretched arms would otherwise
# drag the box edges, and the point the head aims at, toward the hands, and
# hand landmarks flicker across the visibility cut-off far more than the
# head, torso and legs do
BOX_EXCLUDED_LANDMARKS = frozenset(range(13, 23))
# The single-person gesture model runs on 1 in this many frames; the frames in
# between reuse its last result. Multi-person detection still runs every frame.
GESTURE_DETECTION_INTERVAL = 4


def _read_mjpeg_part(raw):
    """
    Read the next part of a multipart MJPEG stream and return its JPEG bytes,
    or None when the stream ends.

    Parts are read by their Content-Length so each frame is returned as soon
    as it has fully arrived. Reading fixed-size chunks instead blocks until
    the chunk is full, which holds frames back and hands several over at once.
    """
    content_length = None
    while True:
        line = raw.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            if content_length is not None:
                break
            continue
        name, _, value = line.partition(b':')
        if name.strip().lower() == b'content-length':
            try:
                content_length = int(value.strip())
            except ValueError:
                content_length = None

    data = bytearray()
    while len(data) < content_length:
        chunk = raw.read(content_length - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)


class ProcessedFrameData:
    """Container for processed frame data"""
    def __init__(self, frame=None, gesture_detected=None, pose_landmarks=None, people=None):
        self.frame = frame
        self.gesture_detected = gesture_detected  # None, "left_wave", "right_wave", or "hands_up"
        self.pose_landmarks = pose_landmarks
        self.people = people  # None when person detection is unavailable, else a list of tracked people

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

        # MediaPipe state - initialised lazily when tracking is first enabled
        # so startup is fast and MediaPipe is not required for basic streaming
        self.mp_pose = None
        self.pose = None
        self.mp_drawing = None
        self.pose_detection_available = False
        self._mediapipe_load_attempted = False
        self._mp_module = None

        # Last gesture model result, reused on frames where the model is skipped
        self._gesture_frame_counter = 0
        self._last_gesture_landmarks = None
        self._last_gesture = None

        # Multi-pose body detection feeds the person tracker used for
        # attention behaviour - separate from self.pose above, which is a
        # single-person model used only for gesture detection
        self.person_landmarker = None
        self.people_detection_available = False
        self.person_tracker = PersonTracker()
        self._tracker_reset_pending = False
        self._pose_timestamp_ms = 0

        # Attention state reported by the backend, used to highlight the focused person
        self._attention_state = None
        self._attention_focus_id = None
        self._attention_updated_at = 0.0

    def set_attention_state(self, state, focus_id):
        """Record the backend attention state for the overlay"""
        self._attention_state = state
        self._attention_focus_id = focus_id
        self._attention_updated_at = time.monotonic()

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
        if enabled and not self._mediapipe_load_attempted:
            self._load_mediapipe()
        if not enabled:
            self._tracker_reset_pending = True
            self._gesture_frame_counter = 0
            self._last_gesture_landmarks = None
            self._last_gesture = None
        self.logger.info(f"Gesture tracking {'enabled' if enabled else 'disabled'}")

    def _load_mediapipe(self):
        """Lazily import and initialise MediaPipe on first tracking enable.
        Only ever attempted once; subsequent calls are no-ops."""
        self._mediapipe_load_attempted = True
        try:
            import mediapipe as mp
            self._mp_module = mp
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
            self.logger.info("MediaPipe pose detection initialised")
        except ImportError:
            self.logger.warning("MediaPipe not available - pose detection disabled")
            return
        except Exception as e:
            self.logger.error(f"Failed to initialise MediaPipe: {e}")
            return

        try:
            from mediapipe.tasks.python import BaseOptions
            from mediapipe.tasks.python.vision import (
                PoseLandmarker, PoseLandmarkerOptions, RunningMode
            )

            model_path = Path(__file__).resolve().parent.parent / "resources" / "models" / POSE_LANDMARKER_MODEL_FILENAME
            if not model_path.exists():
                self.logger.error(
                    f"Pose landmarker model not found at {model_path} - download "
                    f"{POSE_LANDMARKER_MODEL_FILENAME} from the MediaPipe model zoo "
                    "and place it there to enable person tracking"
                )
                return

            options = PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(model_path)),
                running_mode=RunningMode.VIDEO,
                num_poses=MAX_TRACKED_PEOPLE,
                min_pose_detection_confidence=0.5,
                min_pose_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self.person_landmarker = PoseLandmarker.create_from_options(options)
            self.people_detection_available = True
            self.logger.info(f"MediaPipe multi-pose person detection initialised (max {MAX_TRACKED_PEOPLE})")
        except Exception as e:
            self.logger.error(f"Failed to initialise person detection: {e}")

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
        """
        Process an MJPEG stream from a requests response.

        A reader thread drains the stream continuously and keeps only the
        newest frame; this thread processes whichever frame is newest each
        time it is ready for another. When processing is slower than the
        frame rate (e.g. with tracking enabled) frames are skipped rather
        than queued, so the display never falls behind the live feed.
        """
        latest = {'jpeg': None}
        frame_lock = threading.Lock()
        frame_ready = threading.Event()
        reader_done = threading.Event()
        reader_failed = threading.Event()

        def read_frames():
            try:
                while self.running and self.should_connect:
                    jpeg_data = _read_mjpeg_part(response.raw)
                    if jpeg_data is None:
                        break
                    with frame_lock:
                        latest['jpeg'] = jpeg_data
                    frame_ready.set()
            except Exception as e:
                if self.running and self.should_connect:
                    self.logger.warning(f"MJPEG read error: {e}")
                    reader_failed.set()
            finally:
                reader_done.set()
                frame_ready.set()

        reader_thread = threading.Thread(target=read_frames, daemon=True)
        reader_thread.start()

        try:
            frame_count_local = 0
            last_frame_time = time.time()
            last_stats_time = time.time()

            self.logger.info("Starting MJPEG frame processing...")

            while True:
                if not self.running or not self.should_connect:
                    self.logger.info("MJPEG processing stopped by request")
                    break

                frame_ready.wait(timeout=0.5)
                frame_ready.clear()

                with frame_lock:
                    jpeg_data = latest['jpeg']
                    latest['jpeg'] = None

                if jpeg_data is None:
                    if reader_done.is_set():
                        break
                    continue

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

            return not reader_failed.is_set()

        except Exception as e:
            self.logger.error(f"MJPEG stream processing error: {e}")
            return False

        finally:
            response.close()
            reader_thread.join(timeout=2)

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
            people = self._detect_people(frame_rgb) if self.tracking_enabled else None

            # Gesture detection if available and tracking enabled
            if self.pose_detection_available and self.pose and self.tracking_enabled:
                try:
                    # Run the gesture model on 1 in GESTURE_DETECTION_INTERVAL
                    # frames and reuse its last result on the frames between,
                    # so gestures are still reported on every frame
                    if self._gesture_frame_counter % GESTURE_DETECTION_INTERVAL == 0:
                        # MediaPipe expects RGB, and we already have RGB
                        results = self.pose.process(frame_rgb)
                        self._last_gesture_landmarks = results.pose_landmarks
                        self._last_gesture = (
                            self._detect_gestures(results.pose_landmarks.landmark)
                            if results.pose_landmarks else None
                        )
                    self._gesture_frame_counter += 1

                    if self._last_gesture_landmarks:
                        pose_landmarks = self._last_gesture_landmarks

                        # Draw pose landmarks on frame (convert to BGR for drawing, then back to RGB)
                        frame_bgr_for_drawing = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                        self.mp_drawing.draw_landmarks(
                            frame_bgr_for_drawing,
                            pose_landmarks,
                            self.mp_pose.POSE_CONNECTIONS
                        )
                        frame_rgb = cv2.cvtColor(frame_bgr_for_drawing, cv2.COLOR_BGR2RGB)

                        gesture_detected = self._last_gesture

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

            if people is not None:
                self._draw_people_overlay(frame_rgb, people)

            return ProcessedFrameData(
                frame=frame_rgb,
                gesture_detected=gesture_detected,
                pose_landmarks=pose_landmarks,
                people=people
            )

        except Exception as e:
            self.logger.error(f"Frame processing error: {e}")
            return None

    def _draw_people_overlay(self, frame_rgb, people):
        """Draw a box and id for each tracked person, highlighting the focused one,
        and show the attention state along the bottom edge."""
        try:
            height, width = frame_rgb.shape[:2]
            state_fresh = (time.monotonic() - self._attention_updated_at) < ATTENTION_STATE_TIMEOUT
            focus_id = self._attention_focus_id if state_fresh else None

            for person in people:
                focused = person["id"] == focus_id
                color = FOCUS_BOX_COLOR if focused else PERSON_BOX_COLOR
                thickness = 3 if focused else 1

                half_w = person["w"] * width / 2.0
                half_h = person["h"] * height / 2.0
                x1 = int(person["cx"] * width - half_w)
                y1 = int(person["cy"] * height - half_h)
                x2 = int(person["cx"] * width + half_w)
                y2 = int(person["cy"] * height + half_h)
                cv2.rectangle(frame_rgb, (x1, y1), (x2, y2), color, thickness)

                label = f"#{person['id']}"
                label_y = y1 - 6 if y1 > 22 else y2 + 18
                cv2.putText(frame_rgb, label, (x1, label_y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            if state_fresh and self._attention_state and self._attention_state.upper() != "OFF":
                cv2.putText(frame_rgb, self._attention_state.upper(), (10, height - 12),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, FOCUS_BOX_COLOR, 2)
        except Exception as e:
            self.logger.debug(f"People overlay error: {e}")

    def _detect_people(self, frame_rgb):
        """Detect bodies and return the tracked people as a list of dicts.
        Returns None when person detection is unavailable so callers can tell
        'nobody in view' (empty list) apart from 'not looking'."""
        if not (self.people_detection_available and self.person_landmarker):
            return None

        if self._tracker_reset_pending:
            self.person_tracker.reset()
            self._tracker_reset_pending = False

        try:
            mp_image = self._mp_module.Image(
                image_format=self._mp_module.ImageFormat.SRGB, data=frame_rgb
            )
            # Tasks API requires strictly increasing timestamps in VIDEO mode
            timestamp_ms = max(int(time.monotonic() * 1000), self._pose_timestamp_ms + 1)
            self._pose_timestamp_ms = timestamp_ms
            result = self.person_landmarker.detect_for_video(mp_image, timestamp_ms)
        except Exception as e:
            self.logger.debug(f"Person detection error: {e}")
            return None

        detections = []
        for landmarks in result.pose_landmarks:
            visible = [lm for index, lm in enumerate(landmarks)
                       if index not in BOX_EXCLUDED_LANDMARKS
                       and lm.visibility >= MIN_LANDMARK_VISIBILITY]
            if len(visible) < MIN_VISIBLE_LANDMARKS:
                continue

            xs = [lm.x for lm in visible]
            ys = [lm.y for lm in visible]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            cx = min(1.0, max(0.0, (x_min + x_max) / 2.0))
            cy = min(1.0, max(0.0, (y_min + y_max) / 2.0))
            box_w = min(1.0, x_max - x_min)
            box_h = min(1.0, y_max - y_min)
            score = sum(lm.visibility for lm in visible) / len(visible)
            detections.append((cx, cy, box_w, box_h, score))

        return self.person_tracker.update(detections, time.monotonic())

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