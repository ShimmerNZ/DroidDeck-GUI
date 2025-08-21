import cv2
import time
import threading
import requests
from flask import Flask, Response, jsonify
import json
import os
import numpy as np

CONFIG_PATH = "config/camera_config.json"

class CameraProxy:
    def __init__(self):
        self.load_config()
        self.frame = None
        self.last_frame_time = 0
        self.frame_count = 0
        self.dropped_frames = 0
        self.running = True
        self.lock = threading.Lock()

    def load_config(self):
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
        self.esp32_url = config.get("esp32_url", "http://esp32.local:81/stream")
        self.rebroadcast_port = config.get("rebroadcast_port", 8081)
        self.enable_stats = config.get("enable_stats", True)

    def start_stream(self):
        def fetch_stream():
            try:
                stream = requests.get(self.esp32_url, stream=True)
                bytes_data = b""
                for chunk in stream.iter_content(chunk_size=1024):
                    bytes_data += chunk
                    a = bytes_data.find(b'\xff\xd8')
                    b = bytes_data.find(b'\xff\xd9')
                    if a != -1 and b != -1:
                        jpg = bytes_data[a:b+2]
                        bytes_data = bytes_data[b+2:]
                        img_array = np.frombuffer(jpg, dtype=np.uint8)
                        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                        if frame is not None:
                            encoded, buffer = cv2.imencode('.jpg', frame)
                            if encoded:
                                with self.lock:
                                    self.frame = buffer.tobytes()
                                    now = time.time()
                                    if self.last_frame_time:
                                        delta = now - self.last_frame_time
                                        if delta > 0.2:
                                            self.dropped_frames += 1
                                    self.last_frame_time = now
                                    self.frame_count += 1
            except Exception as e:
                print(f"[CameraProxy] Error fetching stream: {e}")

        threading.Thread(target=fetch_stream, daemon=True).start()

    def generate_stream(self):
        while self.running:
            with self.lock:
                if self.frame:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + self.frame + b'\r\n')
            time.sleep(0.03)

    def get_stats(self):
        with self.lock:
            elapsed = max(time.time() - self.last_frame_time, 1)
            return {
                "fps": round(self.frame_count / elapsed, 2),
                "dropped_frames": self.dropped_frames
            }

    def run_server(self):
        app = Flask(__name__)

        @app.route('/stream')
        def stream():
            return Response(self.generate_stream(),
                            mimetype='multipart/x-mixed-replace; boundary=frame')

        @app.route('/stats')
        def stats():
            return jsonify(self.get_stats()) if self.enable_stats else jsonify({})

        self.start_stream()
        app.run(host='0.0.0.0', port=self.rebroadcast_port, threaded=True)

if __name__ == "__main__":
    proxy = CameraProxy()
    proxy.run_server()
