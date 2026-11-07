#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Image Processing Thread - Camera stream, person tracking and gestures.
One multi-person MediaPipe pose model finds everyone in view; each person's
landmarks give their box for the tracker and any raised-arm gesture.
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
from threads.person_tracker import PersonTracker, Detection

# Overlay colours are RGB, matching the frame buffer
PERSON_BOX_COLOR = (230, 230, 230)
FOCUS_BOX_COLOR = (255, 190, 0)
ATTENTION_STATE_TIMEOUT = 5.0

# Person/body detection: a multi-pose MediaPipe Tasks model, tracking up to
# this many people at once
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
# MediaPipe pose landmark indices
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_ELBOW, RIGHT_ELBOW = 13, 14
LEFT_WRIST, RIGHT_WRIST = 15, 16
# Skeleton lines drawn on the overlay: shoulders, arms, torso and legs
SKELETON_CONNECTIONS = (
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24), (23, 25), (25, 27), (24, 26), (26, 28),
)
GESTURE_LABELS = {"left_wave": "WAVE", "right_wave": "WAVE", "hands_up": "HANDS UP"}


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
    def __init__(self, frame=None, people=None):
        self.frame = frame
        # None when person detection is unavailable, else a list of tracked
        # people; each carries a "gesture" of None, "left_wave", "right_wave"
        # or "hands_up"
        self.people = people

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
        self.source_size = None  # (width, height) of the camera's frames
        self.last_stats_time = time.time()
        self.tracking_enabled = False

        self.logger.info(f"ImageProcessingThread initialized with URL: {camera_url}")

        # MediaPipe state - initialised lazily when tracking is first enabled
        # so startup is fast and MediaPipe is not required for basic streaming
        self._mediapipe_load_attempted = False
        self._mp_module = None

        # Multi-pose body detection feeds the person tracker used for
        # attention behaviour and gestures
        self.person_landmarker = None
        self.people_detection_available = False
        self.person_tracker = PersonTracker()
        self._tracker_reset_pending = False
        self._pose_timestamp_ms = 0

        # Overlays are only drawn while the camera screen is on show
        self.display_active = True

        # Detection time per frame, averaged into the stats once a second
        self._detect_ms_total = 0.0
        self._detect_count = 0

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
        """Enable/disable person tracking and gestures"""
        self.tracking_enabled = enabled
        if enabled and not self._mediapipe_load_attempted:
            self._load_mediapipe()
        if not enabled:
            self._tracker_reset_pending = True
        self.logger.info(f"Person tracking {'enabled' if enabled else 'disabled'}")

    def set_display_active(self, active):
        """Draw overlays only while the camera screen is showing"""
        self.display_active = active

    def _load_mediapipe(self):
        """Lazily import and initialise MediaPipe on first tracking enable.
        Only ever attempted once; subsequent calls are no-ops."""
        self._mediapipe_load_attempted = True
        try:
            import mediapipe as mp
            self._mp_module = mp
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
                        detect_ms = (self._detect_ms_total / self._detect_count
                                     if self._detect_count else None)
                        self._detect_ms_total = 0.0
                        self._detect_count = 0
                        self.stats_updated.emit({
                            'fps': fps,
                            'frame_count': self.frame_count,
                            'detect_ms': detect_ms,
                            'frame_size': self.source_size,
                            'running': True
                        })
                        frame_count_local = 0
                        last_stats_time = current_time

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
            self.source_size = (width, height)
            if width > 800:
                scale = 800 / width
                new_width = int(width * scale)
                new_height = int(height * scale)
                frame_rgb = cv2.resize(frame_rgb, (new_width, new_height))

            tracked = self._detect_people(frame_rgb) if self.tracking_enabled else None

            if tracked is not None and self.display_active:
                self._draw_people_overlay(frame_rgb, tracked)

            return ProcessedFrameData(
                frame=frame_rgb,
                people=None if tracked is None else [t.as_dict() for t in tracked]
            )

        except Exception as e:
            self.logger.error(f"Frame processing error: {e}")
            return None

    def _draw_people_overlay(self, frame_rgb, people):
        """Draw a skeleton, box and id for each tracked person, highlighting the
        focused one and any gesture, and show the attention state along the
        bottom edge."""
        try:
            height, width = frame_rgb.shape[:2]
            state_fresh = (time.monotonic() - self._attention_updated_at) < ATTENTION_STATE_TIMEOUT
            focus_id = self._attention_focus_id if state_fresh else None

            for person in people:
                focused = person.track_id == focus_id
                color = FOCUS_BOX_COLOR if focused else PERSON_BOX_COLOR
                thickness = 3 if focused else 1

                points = person.points
                for a, b in SKELETON_CONNECTIONS:
                    if a < len(points) and b < len(points) and points[a] and points[b]:
                        pa = (int(points[a][0] * width), int(points[a][1] * height))
                        pb = (int(points[b][0] * width), int(points[b][1] * height))
                        cv2.line(frame_rgb, pa, pb, color, 1)

                half_w = person.w * width / 2.0
                half_h = person.h * height / 2.0
                x1 = int(person.cx * width - half_w)
                y1 = int(person.cy * height - half_h)
                x2 = int(person.cx * width + half_w)
                y2 = int(person.cy * height + half_h)
                cv2.rectangle(frame_rgb, (x1, y1), (x2, y2), color, thickness)

                label = f"#{person.track_id}"
                if person.gesture:
                    label += f" {GESTURE_LABELS.get(person.gesture, '')}"
                label_y = y1 - 6 if y1 > 22 else y2 + 18
                cv2.putText(frame_rgb, label, (x1, label_y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            if state_fresh and self._attention_state and self._attention_state.upper() != "OFF":
                cv2.putText(frame_rgb, self._attention_state.upper(), (10, height - 12),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, FOCUS_BOX_COLOR, 2)
        except Exception as e:
            self.logger.debug(f"People overlay error: {e}")

    def _detect_people(self, frame_rgb):
        """Detect bodies and return the tracked people.
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
            started = time.perf_counter()
            result = self.person_landmarker.detect_for_video(mp_image, timestamp_ms)
            self._detect_ms_total += (time.perf_counter() - started) * 1000.0
            self._detect_count += 1
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

            shoulder_width = 0.0
            left, right = landmarks[LEFT_SHOULDER], landmarks[RIGHT_SHOULDER]
            if min(left.visibility, right.visibility) >= MIN_LANDMARK_VISIBILITY:
                shoulder_width = abs(left.x - right.x)

            points = [(lm.x, lm.y) if lm.visibility >= MIN_LANDMARK_VISIBILITY else None
                      for lm in landmarks]
            detections.append(Detection(cx, cy, box_w, box_h, score, shoulder_width,
                                        self._detect_gesture(landmarks), points))

        return self.person_tracker.update(detections, time.monotonic())

    @staticmethod
    def _detect_gesture(landmarks):
        """
        Raised-arm gesture for one person: an arm counts as raised when the
        wrist is above the elbow and the elbow above the shoulder.
        Returns None, "left_wave", "right_wave" or "hands_up"; the camera
        view is mirrored, so the person's left arm is reported as a right wave.
        """
        def raised(wrist, elbow, shoulder):
            parts = (landmarks[wrist], landmarks[elbow], landmarks[shoulder])
            if any(part.visibility < MIN_LANDMARK_VISIBILITY for part in parts):
                return False
            return parts[0].y < parts[1].y < parts[2].y

        left = raised(LEFT_WRIST, LEFT_ELBOW, LEFT_SHOULDER)
        right = raised(RIGHT_WRIST, RIGHT_ELBOW, RIGHT_SHOULDER)
        if left and right:
            return "hands_up"
        if left:
            return "right_wave"
        if right:
            return "left_wave"
        return None

    def stop(self):
        """Legacy method for compatibility - calls stop_processing"""
        self.stop_processing()

    def _emit_stats(self):
        """Legacy method for compatibility - stats are now emitted in _process_mjpeg_stream"""
        pass