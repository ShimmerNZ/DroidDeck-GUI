"""
Bandwidth Test Progress Splash Screen
Shows real-time progress of upload/download speed testing with controller calibration styling
"""

import sys
import time
import threading
import requests
from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                            QProgressBar, QWidget, QFrame, QApplication, QDialog,
                            QSpinBox, QComboBox)
from PyQt6.QtGui import QFont, QPainter, QBrush, QColor, QLinearGradient
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QRect
from typing import Optional, Callable


class BandwidthTestWorker(QThread):
    """Worker thread for bandwidth testing to avoid blocking UI"""
    
    # Signals for updating UI
    progress_updated = pyqtSignal(int)  # Progress percentage
    speed_updated = pyqtSignal(str, float)  # Test type, speed in MB/s
    test_completed = pyqtSignal(dict)  # Final results
    test_failed = pyqtSignal(str)  # Error message
    status_updated = pyqtSignal(str)  # Status message
    
    def __init__(self, camera_proxy_url: str = "http://10.1.1.230:8081", test_sizes=None):
        super().__init__()
        self.camera_proxy_url = camera_proxy_url
        self.test_cancelled = False
        
        # Configurable test sizes
        if test_sizes is None:
            test_sizes = [5*1024*1024, 10*1024*1024, 25*1024*1024]  # 5MB, 10MB, 25MB
        self.download_sizes = test_sizes
        self.upload_data_size = max(test_sizes)  # Use largest size for upload
        
    def cancel_test(self):
        """Cancel the bandwidth test"""
        self.test_cancelled = True
        
    def run(self):
        """Run the complete bandwidth test suite"""
        try:
            results = {
                "download_speeds": [],
                "upload_speed": 0.0,
                "average_download": 0.0,
                "latency_ms": 0.0,
                "test_duration": 0.0
            }
            
            start_time = time.time()
            
            # Test 1: Latency Test
            if not self.test_cancelled:
                self.status_updated.emit("Testing connection latency...")
                results["latency_ms"] = self._test_latency()
                self.progress_updated.emit(15)
            
            # Test 2: Download Tests (multiple sizes)
            download_progress_start = 15
            download_progress_range = 60  # 15% to 75%
            
            for i, size in enumerate(self.download_sizes):
                if self.test_cancelled:
                    return
                    
                size_mb = size / (1024 * 1024)
                self.status_updated.emit(f"Download test {i+1}/{len(self.download_sizes)}: {size_mb:.0f}MB...")
                
                speed = self._test_download_speed(size)
                if speed > 0:
                    results["download_speeds"].append(speed)
                    self.speed_updated.emit("download", speed)
                
                # Update progress
                progress = download_progress_start + (download_progress_range * (i + 1) / len(self.download_sizes))
                self.progress_updated.emit(int(progress))
            
            # Test 3: Upload Test
            if not self.test_cancelled:
                self.status_updated.emit("Testing upload speed...")
                self.progress_updated.emit(80)
                upload_speed = self._test_upload_speed()
                results["upload_speed"] = upload_speed
                if upload_speed > 0:
                    self.speed_updated.emit("upload", upload_speed)
                self.progress_updated.emit(95)
            
            # Calculate averages
            if results["download_speeds"]:
                results["average_download"] = sum(results["download_speeds"]) / len(results["download_speeds"])
            
            results["test_duration"] = time.time() - start_time
            
            self.status_updated.emit("Test completed successfully")
            self.progress_updated.emit(100)
            self.test_completed.emit(results)
            
        except Exception as e:
            self.test_failed.emit(f"Bandwidth test failed: {str(e)}")
    
    def _test_latency(self) -> float:
        """Test connection latency"""
        try:
            latencies = []
            for i in range(5):  # More samples for better accuracy
                if self.test_cancelled:
                    break
                start = time.time()
                response = requests.get(f"{self.camera_proxy_url}/stream/status", timeout=5)
                if response.status_code == 200:
                    latency = (time.time() - start) * 1000  # Convert to ms
                    latencies.append(latency)
                    # Show real-time latency updates
                    avg_so_far = sum(latencies) / len(latencies)
                    self.speed_updated.emit("latency", avg_so_far)
            
            return sum(latencies) / len(latencies) if latencies else 0.0
        except Exception:
            return 0.0
    
    def _test_download_speed(self, size_bytes: int) -> float:
        """Test download speed with specified data size"""
        try:
            start_time = time.time()
            response = requests.get(
                f"{self.camera_proxy_url}/bandwidth_test",
                params={"size": size_bytes},
                stream=True,
                timeout=60  # Longer timeout for larger files
            )
            
            if response.status_code != 200:
                return 0.0
            
            downloaded = 0
            last_update_time = start_time
            
            for chunk in response.iter_content(chunk_size=8192):
                if self.test_cancelled:
                    return 0.0
                    
                downloaded += len(chunk)
                current_time = time.time()
                
                # Update speed display every 0.5 seconds during download
                if current_time - last_update_time >= 0.5:
                    elapsed = current_time - start_time
                    if elapsed > 0:
                        current_speed = (downloaded / (1024 * 1024)) / elapsed
                        self.speed_updated.emit("download", current_speed)
                        last_update_time = current_time
            
            duration = time.time() - start_time
            if duration > 0:
                return (downloaded / (1024 * 1024)) / duration
            return 0.0
            
        except Exception:
            return 0.0
    
    def _test_upload_speed(self) -> float:
        """Test upload speed"""
        try:
            # Create test data
            upload_data = b'X' * self.upload_data_size
            
            start_time = time.time()
            # Simulate progress updates during upload
            response = requests.post(
                f"{self.camera_proxy_url}/bandwidth_test/upload",
                data=upload_data,
                headers={'Content-Type': 'application/octet-stream'},
                timeout=60
            )
            
            # Emit real-time upload speed updates
            current_time = time.time()
            elapsed = current_time - start_time
            if elapsed > 0.1:  # Avoid division by zero for very fast uploads
                upload_speed = (self.upload_data_size / (1024 * 1024)) / elapsed
                self.speed_updated.emit("upload", upload_speed)
            
            duration = time.time() - start_time
            
            if duration > 0:
                speed_mbps = (self.upload_data_size / (1024 * 1024)) / duration
                return speed_mbps
            return 0.0
            
        except Exception:
            return 0.0


class BandwidthTestSplash(QDialog):
    """Bandwidth test dialog matching exact controller calibration layout and styling"""
    
    # Signal emitted when test is complete
    test_finished = pyqtSignal(object)  # Test results dict or None if cancelled
    
    def __init__(self, camera_proxy_url: str = "http://10.1.1.230:8081", parent=None):
        super().__init__(parent)
        self.camera_proxy_url = camera_proxy_url
        self.test_worker = None
        self.test_results = None
        self.test_in_progress = False
        self.test_completed = False
        self.cancelled_by_user = False
        
        self.setWindowTitle("Network Bandwidth Test")
        self.setFixedSize(700, 500)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        
        # Center on parent or screen
        if parent:
            parent_center = parent.geometry().center()
            self.move(parent_center.x() - 350, parent_center.y() - 300)
        
        self._setup_ui()
        self._apply_controller_style()
        
        # Connect combo box change to reset handler
        self.size_combo.currentIndexChanged.connect(self._on_test_size_changed)
    
    def _setup_ui(self):
        """Setup UI exactly matching controller calibration layout"""
        # Main layout with no margins/spacing
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header area (dark blue outer area like controller calibration)
        header_widget = QWidget()
        header_widget.setObjectName("header_widget")
        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(30, 20, 30, 20)
        header_layout.setSpacing(15)
        
        # Main title (like controller calibration header)
        self.header_label = QLabel("Network Bandwidth Test")
        self.header_label.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        self.header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.header_label)
        
        # Progress bar under header (like controller calibration)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(20)
        header_layout.addWidget(self.progress_bar)
        
        header_widget.setLayout(header_layout)
        main_layout.addWidget(header_widget)
        
        # Main content area (like controller calibration main area)
        content_widget = QWidget()
        content_widget.setObjectName("content_widget")
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(30, 30, 30, 20)  # Reduced side margins to make room for side strips
        content_layout.setSpacing(25)
        
        # Description
        self.description_label = QLabel("This test will measure your network connection speed to the camera proxy server.")
        self.description_label.setFont(QFont("Arial", 14))
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.description_label.setWordWrap(True)
        content_layout.addWidget(self.description_label)
        
        # Test size selection
        size_layout = QHBoxLayout()
        size_label = QLabel("Test Data Size:")
        size_label.setFont(QFont("Arial", 14))
        
        self.size_combo = QComboBox()
        self.size_combo.addItems([
            "Quick Test (5, 10, 15 MB)",
            "Standard Test (5, 10, 25 MB)", 
            "Thorough Test (10, 25, 50 MB)",
            "Heavy Test (25, 50, 100 MB)"
        ])
        self.size_combo.setCurrentIndex(1)  # Standard by default
        self.size_combo.setFont(QFont("Arial", 12))
        
        size_layout.addWidget(size_label)
        size_layout.addStretch()
        size_layout.addWidget(self.size_combo)
        content_layout.addLayout(size_layout)
        
        # Real-time results display with borders on each field
        results_layout = QHBoxLayout()
        results_layout.setSpacing(30)
        
        # Download column with border
        download_frame = QFrame()
        download_frame.setFrameStyle(QFrame.Shape.Box)
        download_layout = QVBoxLayout()
        download_layout.setContentsMargins(20, 15, 20, 15)
        download_layout.setSpacing(10)
        
        download_header = QLabel("Download Speed")
        download_header.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        download_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.download_label = QLabel("---.-- MB/s")
        self.download_label.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        self.download_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        download_layout.addWidget(download_header)
        download_layout.addWidget(self.download_label)
        download_frame.setLayout(download_layout)
        
        # Upload column with border  
        upload_frame = QFrame()
        upload_frame.setFrameStyle(QFrame.Shape.Box)
        upload_layout = QVBoxLayout()
        upload_layout.setContentsMargins(20, 15, 20, 15)
        upload_layout.setSpacing(10)
        
        upload_header = QLabel("Upload Speed")
        upload_header.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        upload_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.upload_label = QLabel("---.-- MB/s")
        self.upload_label.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        self.upload_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        upload_layout.addWidget(upload_header)
        upload_layout.addWidget(self.upload_label)
        upload_frame.setLayout(upload_layout)
        
        # Latency column with border
        latency_frame = QFrame()
        latency_frame.setFrameStyle(QFrame.Shape.Box)
        latency_layout = QVBoxLayout()
        latency_layout.setContentsMargins(20, 15, 20, 15)
        latency_layout.setSpacing(10)
        
        latency_header = QLabel("Latency")
        latency_header.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        latency_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.latency_label = QLabel("--- ms")
        self.latency_label.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        self.latency_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        latency_layout.addWidget(latency_header)
        latency_layout.addWidget(self.latency_label)
        latency_frame.setLayout(latency_layout)
        
        results_layout.addWidget(download_frame)
        results_layout.addWidget(upload_frame)
        results_layout.addWidget(latency_frame)
        content_layout.addLayout(results_layout)
        
        content_layout.addStretch()
        
        # Status label
        self.status_label = QLabel("Make sure your network connection is stable before proceeding.")
        self.status_label.setFont(QFont("Arial", 12))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.status_label)
        
        content_widget.setLayout(content_layout)
        
        # Create horizontal layout for left strip + content + right strip
        content_with_sides_layout = QHBoxLayout()
        content_with_sides_layout.setContentsMargins(0, 0, 0, 0)
        content_with_sides_layout.setSpacing(0)
        
        # Left strip (dark blue)
        left_strip = QWidget()
        left_strip.setObjectName("side_strip")
        left_strip.setFixedWidth(15)  # Approximately 5mm
        content_with_sides_layout.addWidget(left_strip)
        
        # Main content
        content_with_sides_layout.addWidget(content_widget)
        
        # Right strip (dark blue)
        right_strip = QWidget()
        right_strip.setObjectName("side_strip")
        right_strip.setFixedWidth(15)  # Approximately 5mm
        content_with_sides_layout.addWidget(right_strip)
        
        # Container for the content with side strips
        content_container = QWidget()
        content_container.setLayout(content_with_sides_layout)
        main_layout.addWidget(content_container)
        
        # Button area (dark blue outer area like controller calibration)
        button_widget = QWidget()
        button_widget.setObjectName("button_widget")
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(30, 20, 30, 25)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setFont(QFont("Arial", 12))
        self.cancel_button.setFixedHeight(40)
        self.cancel_button.clicked.connect(self.cancel_test)
        
        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch()
        
        self.start_button = QPushButton("Start Test")
        self.start_button.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.start_button.setFixedHeight(40)
        self.start_button.clicked.connect(self.start_test)
        self.start_button.setDefault(True)
        
        button_layout.addWidget(self.start_button)
        
        button_widget.setLayout(button_layout)
        main_layout.addWidget(button_widget)
        
        self.setLayout(main_layout)
    
    def _apply_controller_style(self):
        """Apply exact controller calibration styling with proper outer areas"""
        self.setStyleSheet("""
            QDialog {
                background-color: #2a3a4a;
                color: white;
            }
            QWidget {
                color: white;
                background: transparent;
            }
            QWidget#header_widget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #12132b, stop:1 #2a3a4a);
            }
            QWidget#button_widget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #12132b, stop:1 #2a3a4a);
            }
            QWidget#side_strip {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a3a4a, stop:1 #12132b);
            }
            QWidget#content_widget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3a4a5a, stop:1 #2a3a4a);
            }
            QLabel {
                color: white;
                background: transparent;
            }
            QFrame[frameShape="4"] {
                background: transparent;
                border: 1px solid #5a6a7a;
                border-radius: 8px;
            }
            QFrame[frameShape="5"] {
                background-color: #5a6a7a;
                max-height: 1px;
                border: none;
            }
            QComboBox {
                background-color: #4a5a6a;
                border: none;
                border-radius: 4px;
                padding: 8px;
                color: white;
                min-width: 200px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid white;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: #4a5a6a;
                border: 1px solid #6a7a8a;
                selection-background-color: #5a7a9a;
                color: white;
            }
            QProgressBar {
                border: 1px solid #5a6a7a;
                border-radius: 8px;
                background-color: #3a4a5a;
                text-align: center;
                color: white;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4a9eff, stop:1 #1e7ce8);
                border-radius: 6px;
            }
            QPushButton {
                background-color: #5a6a7a;
                border: none;
                border-radius: 8px;
                color: white;
                padding: 10px 25px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6a7a8a;
            }
            QPushButton:pressed {
                background-color: #4a5a6a;
            }
            QPushButton:default {
                background-color: #1e7ce8;
            }
            QPushButton:default:hover {
                background-color: #4a9eff;
            }
        """)
        
        # Special styling for result labels to match controller calibration blue
        result_style = """
            QLabel {
                color: #4a9eff;
                background: transparent;
            }
        """
        self.download_label.setStyleSheet(result_style)
        self.upload_label.setStyleSheet(result_style)
        self.latency_label.setStyleSheet(result_style)
    
    def _get_test_sizes(self):
        """Get test sizes based on selection"""
        size_configs = {
            0: [5*1024*1024, 10*1024*1024, 15*1024*1024],      # Quick
            1: [5*1024*1024, 10*1024*1024, 25*1024*1024],      # Standard
            2: [10*1024*1024, 25*1024*1024, 50*1024*1024],     # Thorough
            3: [25*1024*1024, 50*1024*1024, 100*1024*1024]     # Heavy
        }
        return size_configs.get(self.size_combo.currentIndex(), size_configs[1])
    
    def _on_test_size_changed(self):
        """Handle test size dropdown change - reset if test completed"""
        if self.test_completed and not self.test_in_progress:
            self._reset_test_ui()
    
    def _reset_test_ui(self):
        """Reset UI to initial state"""
        self.test_completed = False
        self.test_results = None
        
        # Reset displays
        self.progress_bar.setValue(0)
        self.download_label.setText("---.-- MB/s")
        self.upload_label.setText("---.-- MB/s")
        self.latency_label.setText("--- ms")
        self.status_label.setText("Make sure your network connection is stable before proceeding.")
        
        # Reset button
        self.start_button.setText("Start Test")
        self.start_button.clicked.disconnect()
        self.start_button.clicked.connect(self.start_test)
        self.start_button.setEnabled(True)
        self.size_combo.setEnabled(True)
    
    def start_test(self):
        """Start the bandwidth test"""
        if self.test_worker and self.test_worker.isRunning():
            return
        
        self.test_in_progress = True
        self.test_completed = False
        self.cancelled_by_user = False
        
        # Disable controls
        self.size_combo.setEnabled(False)
        
        # Reset UI
        self.progress_bar.setValue(0)
        self.download_label.setText("---.-- MB/s")
        self.upload_label.setText("---.-- MB/s")
        self.latency_label.setText("--- ms")
        self.status_label.setText("Initializing test...")
        
        # Update buttons
        self.start_button.setText("Testing...")
        self.start_button.setEnabled(False)
        
        # Get selected test configuration
        test_sizes = self._get_test_sizes()
        
        # Create and start worker thread
        self.test_worker = BandwidthTestWorker(self.camera_proxy_url, test_sizes)
        self.test_worker.progress_updated.connect(self.update_progress)
        self.test_worker.speed_updated.connect(self.update_speed)
        self.test_worker.status_updated.connect(self.update_status)
        self.test_worker.test_completed.connect(self.test_completed_handler)
        self.test_worker.test_failed.connect(self.test_failed)
        self.test_worker.start()
    
    def cancel_test(self):
        """Cancel the running test or close dialog"""
        if self.test_in_progress and self.test_worker and self.test_worker.isRunning():
            self.cancelled_by_user = True
            self.test_worker.cancel_test()
            self.test_worker.wait()
            self.status_label.setText("Test cancelled")
            self.test_in_progress = False
        
        # Close dialog with None results to indicate cancellation
        self.test_results = None
        self.test_finished.emit(None)
        self.reject()
    
    def update_progress(self, progress: int):
        """Update progress bar"""
        self.progress_bar.setValue(progress)
    
    def update_speed(self, test_type: str, speed: float):
        """Update real-time speed display"""
        if test_type == "download":
            self.download_label.setText(f"{speed:.2f} MB/s")
        elif test_type == "upload":
            self.upload_label.setText(f"{speed:.2f} MB/s")
        elif test_type == "latency":
            self.latency_label.setText(f"{speed:.1f} ms")
    
    def update_status(self, status: str):
        """Update status message"""
        self.status_label.setText(status)
    
    def test_completed_handler(self, results: dict):
        """Handle test completion"""
        if self.cancelled_by_user:
            return
            
        self.test_results = results
        self.test_in_progress = False
        self.test_completed = True
        
        # Update final results
        if results.get("latency_ms", 0) > 0:
            self.latency_label.setText(f"{results['latency_ms']:.1f} ms")
        
        if results.get("average_download", 0) > 0:
            self.download_label.setText(f"{results['average_download']:.2f} MB/s")
        if results.get("upload_speed", 0) > 0:
            self.upload_label.setText(f"{results['upload_speed']:.2f} MB/s")
        
        # Update buttons for completion
        self.start_button.setText("Close")
        self.start_button.setEnabled(True)
        self.start_button.clicked.disconnect()
        self.start_button.clicked.connect(self.close_dialog)
        self.size_combo.setEnabled(True)
    
    def test_failed(self, error_message: str):
        """Handle test failure"""
        self.test_in_progress = False
        self.status_label.setText(f"Test failed: {error_message}")
        self.start_button.setText("Start Test")
        self.start_button.setEnabled(True)
        self.start_button.clicked.disconnect()
        self.start_button.clicked.connect(self.start_test)
        self.size_combo.setEnabled(True)
    
    def close_dialog(self):
        """Close dialog with results"""
        self.test_finished.emit(self.test_results)
        self.accept()


def show_bandwidth_test_splash(parent=None, camera_proxy_url: str = "http://10.1.1.230:8081"):
    """
    Show bandwidth test splash screen and return results
    Returns dict with test results or None if cancelled
    """
    dialog = BandwidthTestSplash(camera_proxy_url, parent)
    
    # Store results from signal
    results = None
    
    def capture_results(test_results):
        nonlocal results
        results = test_results
    
    dialog.test_finished.connect(capture_results)
    
    # Show dialog and wait for completion
    dialog.exec()
    
    return results


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Test the dialog
    results = show_bandwidth_test_splash()
    
    if results:
        print("Test Results:")
        print(f"Download Speed: {results.get('average_download', 0):.2f} MB/s")
        print(f"Upload Speed: {results.get('upload_speed', 0):.2f} MB/s")
        print(f"Latency: {results.get('latency_ms', 0):.1f} ms")
        print(f"Duration: {results.get('test_duration', 0):.1f} seconds")
    else:
        print("Test was cancelled")
    
    app.quit()