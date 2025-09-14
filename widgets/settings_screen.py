"""
Settings Screen (Themed)
"""
import requests
import socket
import time
from urllib.parse import urlparse 
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QLineEdit, QSpinBox, QSlider, QPushButton,
    QComboBox, QMessageBox, QGroupBox, QFrame, QScrollArea, QWidget, QProgressDialog, QApplication
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from widgets.base_screen import BaseScreen
from core.config_manager import config_manager
from core.theme_manager import theme_manager
from core.utils import error_boundary

# ========================================
# STEP 1: Add these imports at the top of your settings_screen.py file
# ========================================

# Add these new imports to the existing import section:
import requests
import socket
import time
from PyQt6.QtWidgets import QProgressDialog
from PyQt6.QtCore import QThread, pyqtSignal

# ========================================
# STEP 2: Add the NetworkTestThread class INSIDE your settings_screen.py file
# (Add this after your existing imports but before the main SettingsScreen class)
# ========================================

class NetworkTestThread(QThread):
    """Background thread for network connectivity testing"""
    
    progress_updated = pyqtSignal(str, str)  # test_name, status
    test_completed = pyqtSignal(dict)  # results dictionary
    
    def __init__(self, esp32_url, proxy_url, ws_url, websocket_sender=None):
        super().__init__()
        self.esp32_url = esp32_url
        self.proxy_url = proxy_url 
        self.ws_url = ws_url
        self.websocket_sender = websocket_sender
        self.results = {}

    def run(self):
        """Run comprehensive network tests with proper proxy state management"""
        try:
            # Test 1: URL Format Validation
            self.progress_updated.emit("Validating URL formats...", "testing")
            self.validate_url_formats()
            
            # Test 2: Check Camera Proxy Status FIRST
            self.progress_updated.emit("Checking camera proxy status...", "testing")
            proxy_initial_state = self.check_camera_proxy_status()  # True=running, False=stopped
            
            # Test 3: Handle ESP32 testing (needs proxy OFF)
            proxy_needs_management = False
            if self.esp32_url:
                if proxy_initial_state:  # Proxy is currently running
                    self.progress_updated.emit("Temporarily disabling camera proxy for ESP32 test...", "testing")
                    self.disable_camera_proxy()
                    time.sleep(3)  # Wait for proxy to shut down
                    proxy_needs_management = True
                
                # Test ESP32 Camera Direct Connection (with proxy disabled)
                self.progress_updated.emit("Testing ESP32 camera connection...", "testing")
                self.test_esp32_connection()
                
                if proxy_needs_management:  # Restore proxy to original state (ON)
                    self.progress_updated.emit("Restoring camera proxy (was originally running)...", "testing")
                    self.enable_camera_proxy()
                    time.sleep(2)  # Wait for proxy to start up
            
            # Test 4: Handle Camera Proxy testing (needs proxy ON)
            if self.proxy_url:
                if not proxy_initial_state:  # Proxy was originally stopped
                    self.progress_updated.emit("Enabling camera proxy for proxy test...", "testing")
                    self.enable_camera_proxy()
                    time.sleep(3)  # Wait for proxy to start up
                    proxy_needs_management = True
                
                # Test Camera Proxy Connection (with proxy enabled)
                self.progress_updated.emit("Testing camera proxy connection...", "testing")
                self.test_proxy_connection()
                
                if proxy_needs_management and not proxy_initial_state:  # Restore proxy to original state (OFF)
                    self.progress_updated.emit("Restoring camera proxy to original state (off)...", "testing")
                    self.disable_camera_proxy()
            
            # Test 5: Test WebSocket Connection (doesn't need proxy management)
            if self.ws_url:
                self.progress_updated.emit("Testing WebSocket connection...", "testing")
                self.test_websocket_connection()
                
            self.progress_updated.emit("Tests completed!", "complete")
            self.test_completed.emit(self.results)
            
        except Exception as e:
            self.results['error'] = f"Test failed with error: {str(e)}"
            self.test_completed.emit(self.results)

    def validate_url_formats(self):
        """Validate URL formats"""
        # WebSocket URL
        if self.ws_url:
            try:
                if not (self.ws_url.startswith("ws://") or self.ws_url.startswith("wss://")):
                    test_ws_url = f"ws://{self.ws_url}"
                else:
                    test_ws_url = self.ws_url
                    
                parsed = urlparse(test_ws_url)
                if parsed.scheme in ['ws', 'wss'] and parsed.netloc:
                    self.results['ws_format'] = {'status': 'success', 'message': f'Valid format: {test_ws_url}'}
                else:
                    self.results['ws_format'] = {'status': 'error', 'message': f'Invalid WebSocket URL format: {test_ws_url}'}
            except Exception as e:
                self.results['ws_format'] = {'status': 'error', 'message': f'WebSocket URL validation failed: {str(e)}'}
        
        # ESP32 URL
        if self.esp32_url:
            try:
                parsed = urlparse(self.esp32_url)
                if parsed.scheme in ['http', 'https'] and parsed.netloc:
                    self.results['esp32_format'] = {'status': 'success', 'message': f'Valid format: {self.esp32_url}'}
                else:
                    self.results['esp32_format'] = {'status': 'error', 'message': f'Invalid ESP32 URL format: {self.esp32_url}'}
            except Exception as e:
                self.results['esp32_format'] = {'status': 'error', 'message': f'ESP32 URL validation failed: {str(e)}'}
        
        # Proxy URL 
        if self.proxy_url:
            try:
                parsed = urlparse(self.proxy_url)
                if parsed.scheme in ['http', 'https'] and parsed.netloc:
                    self.results['proxy_format'] = {'status': 'success', 'message': f'Valid format: {self.proxy_url}'}
                else:
                    self.results['proxy_format'] = {'status': 'error', 'message': f'Invalid proxy URL format: {self.proxy_url}'}
            except Exception as e:
                self.results['proxy_format'] = {'status': 'error', 'message': f'Proxy URL validation failed: {str(e)}'}

    def check_camera_proxy_status(self):
        """Check if camera proxy is currently running - returns True if running, False if stopped"""
        if not self.proxy_url:
            self.results['proxy_initial_status'] = {'status': 'info', 'message': 'No proxy URL configured'}
            return False
            
        try:
            # Try to access the proxy status endpoint or the stream directly
            proxy_base = self.proxy_url.replace('/stream', '')
            
            # First try a status endpoint
            try:
                response = requests.get(f"{proxy_base}/status", timeout=3)
                if response.status_code == 200:
                    self.results['proxy_initial_status'] = {'status': 'success', 'message': 'Camera proxy is currently running'}
                    return True
            except requests.exceptions.RequestException:
                pass  # Status endpoint might not exist, try stream directly
            
            # Try accessing the stream directly
            response = requests.get(self.proxy_url, timeout=3, stream=True)
            if response.status_code == 200:
                self.results['proxy_initial_status'] = {'status': 'success', 'message': 'Camera proxy is currently running (detected via stream)'}
                return True
            elif response.status_code == 404:
                self.results['proxy_initial_status'] = {'status': 'info', 'message': 'Camera proxy is stopped (404 response)'}
                return False
            else:
                self.results['proxy_initial_status'] = {'status': 'warning', 'message': f'Camera proxy responded with status {response.status_code}'}
                return True  # Assume running if we get any response
                
        except requests.exceptions.ConnectTimeout:
            self.results['proxy_initial_status'] = {'status': 'info', 'message': 'Camera proxy appears to be stopped (connection timeout)'}
            return False
        except requests.exceptions.ConnectionError:
            self.results['proxy_initial_status'] = {'status': 'info', 'message': 'Camera proxy appears to be stopped (connection refused)'}
            return False
        except Exception as e:
            self.results['proxy_initial_status'] = {'status': 'warning', 'message': f'Could not determine proxy status: {str(e)}'}
            return False  # Assume stopped if we can't determine

    def disable_camera_proxy(self):
        """Temporarily disable camera proxy"""
        if not self.websocket_sender:
            self.results['proxy_control'] = {'status': 'warning', 'message': 'Cannot control proxy - WebSocket not connected to backend'}
            return False
            
        try:
            success = self.websocket_sender("camera_proxy_control", action="stop")
            if success:
                self.results['proxy_control'] = {'status': 'success', 'message': 'Successfully disabled camera proxy'}
                return True
            else:
                self.results['proxy_control'] = {'status': 'error', 'message': 'Failed to disable camera proxy - WebSocket command failed'}
                return False
        except Exception as e:
            self.results['proxy_control'] = {'status': 'error', 'message': f'Error disabling proxy: {str(e)}'}
            return False

    def enable_camera_proxy(self):
        """Re-enable camera proxy"""
        if not self.websocket_sender:
            self.results['proxy_control'] = {'status': 'warning', 'message': 'Cannot control proxy - WebSocket not connected to backend'}
            return False
            
        try:
            success = self.websocket_sender("camera_proxy_control", action="start") 
            if success:
                self.results['proxy_control'] = {'status': 'success', 'message': 'Successfully enabled camera proxy'}
                return True
            else:
                self.results['proxy_control'] = {'status': 'error', 'message': 'Failed to enable camera proxy - WebSocket command failed'}
                return False
        except Exception as e:
            self.results['proxy_control'] = {'status': 'error', 'message': f'Error enabling proxy: {str(e)}'}
            return False

    def test_esp32_connection(self):
        """Test direct ESP32 camera connection"""
        try:
            response = requests.get(self.esp32_url, timeout=5, stream=True)
            if response.status_code == 200:
                # Check if we get image data
                content_type = response.headers.get('content-type', '').lower()
                if 'image' in content_type or 'multipart' in content_type:
                    self.results['esp32_connection'] = {'status': 'success', 'message': f'ESP32 camera accessible - Content-Type: {content_type}'}
                else:
                    self.results['esp32_connection'] = {'status': 'warning', 'message': f'ESP32 responded but unexpected content type: {content_type}'}
            else:
                self.results['esp32_connection'] = {'status': 'error', 'message': f'ESP32 camera returned status {response.status_code}'}
        except requests.exceptions.ConnectTimeout:
            self.results['esp32_connection'] = {'status': 'error', 'message': 'ESP32 camera connection timed out'}
        except requests.exceptions.ConnectionError:
            self.results['esp32_connection'] = {'status': 'error', 'message': 'Cannot reach ESP32 camera - check IP address and network'}
        except Exception as e:
            self.results['esp32_connection'] = {'status': 'error', 'message': f'ESP32 test failed: {str(e)}'}
    
    def test_proxy_connection(self):
        """Test camera proxy connection"""
        try:
            response = requests.get(self.proxy_url, timeout=5, stream=True)
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                if 'image' in content_type or 'multipart' in content_type:
                    self.results['proxy_connection'] = {'status': 'success', 'message': f'Camera proxy accessible - Content-Type: {content_type}'}
                else:
                    self.results['proxy_connection'] = {'status': 'warning', 'message': f'Proxy responded but unexpected content type: {content_type}'}
            else:
                self.results['proxy_connection'] = {'status': 'error', 'message': f'Camera proxy returned status {response.status_code}'}
        except requests.exceptions.ConnectTimeout:
            self.results['proxy_connection'] = {'status': 'error', 'message': 'Camera proxy connection timed out'}
        except requests.exceptions.ConnectionError:
            self.results['proxy_connection'] = {'status': 'error', 'message': 'Cannot reach camera proxy - check if service is running'}
        except Exception as e:
            self.results['proxy_connection'] = {'status': 'error', 'message': f'Proxy test failed: {str(e)}'}
    
    def test_websocket_connection(self):
        """Test WebSocket connection"""
        try:
            # Test basic TCP connectivity first
            if not (self.ws_url.startswith("ws://") or self.ws_url.startswith("wss://")):
                test_ws_url = f"ws://{self.ws_url}"
            else:
                test_ws_url = self.ws_url
                
            parsed = urlparse(test_ws_url)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == 'wss' else 80)
            
            # Test TCP connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                self.results['websocket_connection'] = {'status': 'success', 'message': f'WebSocket server reachable at {host}:{port}'}
            else:
                self.results['websocket_connection'] = {'status': 'error', 'message': f'Cannot reach WebSocket server at {host}:{port}'}
                
        except socket.gaierror:
            self.results['websocket_connection'] = {'status': 'error', 'message': f'Cannot resolve hostname: {host}'}
        except Exception as e:
            self.results['websocket_connection'] = {'status': 'error', 'message': f'WebSocket test failed: {str(e)}'}

    def cancel_network_test(self):
        """Cancel the running network test with better cleanup"""
        try:
            if hasattr(self, 'test_thread') and self.test_thread.isRunning():
                # Request thread to finish gracefully
                self.test_thread.requestInterruption()
                
                # Give thread a moment to finish naturally
                if not self.test_thread.wait(1000):  # Wait 1 second
                    # Force termination if needed
                    self.test_thread.terminate()
                    self.test_thread.wait(2000)  # Wait up to 2 more seconds
            
            if hasattr(self, 'progress_dialog'):
                self.progress_dialog.close()
                
        except Exception as e:
            self.logger.warning(f"Error during test cleanup: {e}")


class SettingsScreen(BaseScreen):
    """Configuration interface for system settings with theme manager integration"""

    # ---------- Lifecycle ----------

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Register for theme change notifications
        theme_manager.register_callback(self._on_theme_changed)

    def __del__(self):
        """Clean up theme manager callback on destruction"""
        try:
            theme_manager.unregister_callback(self._on_theme_changed)
        except Exception:
            pass  # Ignore errors during cleanup

    # ---------- UI Build ----------

    def _setup_screen(self):
        """Initialize settings interface"""
        self.config_path = "resources/configs/steamdeck_config.json"

        # Root layout (similar outer margins to Home screen)
        root = QVBoxLayout()
        root.setContentsMargins(98, 22, 90, 8)
        root.setSpacing(8)

        # Main themed frame (like Home right panel)
        self.main_frame = QFrame()
        self._update_main_frame_style()

        main = QVBoxLayout(self.main_frame)
        main.setContentsMargins(0, 10, 0, 0)
        main.setSpacing(10)

        # Add header
        self.header = QLabel("Settings Configuration")
        self.header.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_header_style()
        main.addWidget(self.header)

        # Theme selector (top row)
        self._create_theme_selector(main)

        # Scrollable content area (to fit lots of options neatly)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._update_scroll_area_style()

        content_widget = QWidget()
        content_layout = QGridLayout(content_widget)
        content_layout.setContentsMargins(8, 0, 8, 0)
        content_layout.setHorizontalSpacing(12)
        content_layout.setVerticalSpacing(10)

        # Sections
        self.network_group = self._create_section("Network Configuration")
        self._build_network(self.network_group)

        self.logging_group = self._create_section("Logging Configuration")
        self._build_logging(self.logging_group)

        self.wave_group = self._create_section("Wave Detection")
        self._build_wave(self.wave_group)

        # Two-column placement to use width
        content_layout.addWidget(self.network_group, 0, 0, 2, 1)  # row, col, rowspan, colspan
        content_layout.addWidget(self.logging_group, 0, 1)
        content_layout.addWidget(self.wave_group, 1, 1)
        # Add spacing below network configuration
        content_layout.setRowMinimumHeight(2, 10)  # 20px spacing row
        # Buttons row (full width) - moved to row 3 to account for spacing
        content_layout.setRowStretch(1, 1)
        buttons_layout = self._create_control_buttons()
        content_layout.addLayout(buttons_layout, 3, 0, 1, 2)  # Changed from row 2 to 3

        self.scroll_area.setWidget(content_widget)
        main.addWidget(self.scroll_area)

        # Assemble
        root.addWidget(self.main_frame)
        self.setLayout(root)

        # Load config on open
        self.load_config()

    # ---------- Themed header & frame ----------

    def _update_main_frame_style(self):
        """Apply themed frame style (similar to Home right frame)"""
        primary_color = theme_manager.get("primary_color")
        panel_bg = theme_manager.get("panel_bg")
        self.main_frame.setStyleSheet(f"""
        QFrame {{
            background-color: {panel_bg};
            border: 2px solid {primary_color};
            border-radius: 12px;
            padding: 6px 6px 12px 6px;
        }}
        """)

    def _update_header_style(self):
        """Apply themed header style"""
        primary = theme_manager.get("primary_color")
        self.header.setStyleSheet(f"""
            QLabel {{
                color: {primary};
                padding-bottom: 8px;
                font-weight: bold;
                border: none;
                background: transparent;
            }}
        """)

    def _update_scroll_area_style(self):
        """Themed scroll bars"""
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        self.scroll_area.setStyleSheet(f"""
        QScrollArea {{
            border: none;
            background-color: transparent;
        }}
        QScrollBar:vertical {{
            background: #2d2d2d;
            width: 12px;
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical {{
            background: {primary};
            border-radius: 6px;
            min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {primary_light};
        }}
        """)

    # ---------- Theme selector ----------

    def _create_theme_selector(self, parent_layout: QVBoxLayout):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(20, 0, 10, 0)

        label = QLabel("Theme:")
        label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        self._update_label_style(label)
        row.addWidget(label)

        self.theme_buttons = {}  # Use dict for easier lookup
        
        # Use available themes reported by ThemeManager
        theme_names = theme_manager.available_themes()
        current_theme = theme_manager.get_theme_name()

        for name in theme_names:
            display_name = "WALL-E" if name == "Wall-e" else name
            btn = QPushButton(display_name)
            btn.setCheckable(True)
            btn.setFont(QFont("Arial", 16, QFont.Weight.Bold))
            btn.setMinimumSize(120, 36)
            
            # Set initial state based on current theme
            is_current = (name == current_theme)
            btn.setChecked(is_current)
            
            # Connect with theme name, not display name
            btn.clicked.connect(lambda checked, theme_name=name: self._on_theme_selected(theme_name))
            
            self.theme_buttons[name] = btn
            row.addWidget(btn)

        # Apply initial styling
        self._update_theme_button_styles()

        row.addStretch()
        parent_layout.addLayout(row)

    def _update_theme_button_styles(self):
        """Update all theme button styles based on current selection"""
        current_theme = theme_manager.get_theme_name()
        for theme_name, btn in self.theme_buttons.items():
            is_selected = (theme_name == current_theme)
            btn.setChecked(is_selected)
            btn.setStyleSheet(theme_manager.get_button_style("primary", checked=is_selected))

    def _on_theme_selected(self, theme_name: str):
        """Handle theme selection"""
        # Only proceed if this is actually a different theme
        if theme_name == theme_manager.get_theme_name():
            return
            
        # Update the theme
        success = theme_manager.set_theme(theme_name)
        if success:
            # Update button states - this will be handled by the theme change callback
            self.logger.info(f"Theme changed to: {theme_name}")
        else:
            # Revert button state if theme change failed
            self._update_theme_button_styles()
            self.logger.error(f"Failed to change theme to: {theme_name}")

    # ---------- Sections ----------

    def _create_section(self, title: str) -> QGroupBox:
        group = QGroupBox(title)
        group.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self._update_section_style(group)
        return group

    def _update_section_style(self, group: QGroupBox):
        primary = theme_manager.get("primary_color")
        panel_bg = theme_manager.get("panel_bg")
        group.setStyleSheet(f"""
        QGroupBox {{
            font-weight: bold;
            border: 2px solid {primary};
            border-radius: 6px;
            margin-top: 18px;
            padding-top: 12px;
            color: {primary};
            background-color: rgba(0, 0, 0, 0.3);
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 15px;
            padding: 0 8px 0 8px;
            top: 5px;
            border-radius: 6px;
            background-color: {panel_bg};
            color: {primary};
        }}
        """)

    def _build_network(self, group: QGroupBox):
        layout = QGridLayout()
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(6)

        font = QFont("Arial", 16)
        labels = [
            ("ESP32 Camera:", "esp32_url", "http://192.168.1.100:81/stream"),
            ("Camera Proxy:", "proxy_url", "http://10.1.1.230:8081/stream"),
            ("Control WebSocket:", "control_ws", "ws://10.1.1.230:8766"),
        ]
        self.network_inputs = {}

        for i, (text, key, placeholder) in enumerate(labels):
            lab = QLabel(text)
            lab.setFont(font)
            lab.setMinimumWidth(170)
            self._update_label_style(lab)

            edit = QLineEdit()
            edit.setFont(font)
            edit.setFixedHeight(30)
            edit.setMinimumWidth(230)
            edit.setPlaceholderText(placeholder)
            self._update_input_style(edit)

            self.network_inputs[key] = edit
            layout.addWidget(lab, i, 0)
            layout.addWidget(edit, i, 1, 1, 3)

        group.setLayout(layout)

    def _build_logging(self, group: QGroupBox):
        layout = QGridLayout()
        layout.setContentsMargins(10, 0, 10, 10)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        font = QFont("Arial", 16)

        items = [
            ("Global Debug:", "debug_combo"),
            ("Camera Debug:", "camera_debug_combo"),
            ("Servo Debug:", "servo_debug_combo"),
            ("Network Debug:", "network_debug_combo"),
        ]
        self.debug_combos = {}

        for i, (label_text, key) in enumerate(items):
            row = i // 2
            col = (i % 2) * 2
            lab = QLabel(label_text)
            lab.setFont(font)
            self._update_label_style(lab)

            combo = QComboBox()
            combo.setFont(font)
            combo.addItems(["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"])
            combo.setFixedHeight(30)
            combo.setFixedWidth(120)
            self._update_combo_style(combo)

            self.debug_combos[key] = combo
            layout.addWidget(lab, row, col)
            layout.addWidget(combo, row, col + 1)

        group.setLayout(layout)

    def _build_wave(self, group: QGroupBox):
        layout = QGridLayout()
        layout.setContentsMargins(10, 0, 10, 10)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        font = QFont("Arial", 16)

        # Row 0: Sample Duration / Sample Rate
        dur_lab = QLabel("Sample Duration:")
        self._update_label_style(dur_lab)
        layout.addWidget(dur_lab, 0, 0)

        self.sample_duration_spin = QSpinBox()
        self.sample_duration_spin.setFont(font)
        self.sample_duration_spin.setRange(1, 10)
        self.sample_duration_spin.setValue(3)
        self.sample_duration_spin.setFixedHeight(30)
        self.sample_duration_spin.setMaximumWidth(70)
        self._update_spinbox_style(self.sample_duration_spin)
        layout.addWidget(self.sample_duration_spin, 0, 1)

        rate_lab = QLabel("Sample Rate:")
        self._update_label_style(rate_lab)
        layout.addWidget(rate_lab, 0, 2)

        self.sample_rate_spin = QSpinBox()
        self.sample_rate_spin.setFont(font)
        self.sample_rate_spin.setRange(1, 60)
        self.sample_rate_spin.setValue(5)
        self.sample_rate_spin.setFixedHeight(30)
        self.sample_rate_spin.setMaximumWidth(70)
        self._update_spinbox_style(self.sample_rate_spin)
        layout.addWidget(self.sample_rate_spin, 0, 3)

        # Row 1: Confidence / Stand down
        conf_lab = QLabel("Confidence:")
        self._update_label_style(conf_lab)
        layout.addWidget(conf_lab, 1, 0)

        conf_row = QHBoxLayout()
        self.confidence_slider = QSlider(Qt.Orientation.Horizontal)
        self.confidence_slider.setRange(0, 100)
        self.confidence_slider.setValue(70)
        self.confidence_slider.setMaximumWidth(140)
        self.confidence_slider.setFixedHeight(30)
        self._update_slider_style(self.confidence_slider)

        self.confidence_value = QLabel("70%")
        self.confidence_value.setFont(font)
        self.confidence_value.setMinimumWidth(48)
        self._update_value_label_style(self.confidence_value)

        self.confidence_slider.valueChanged.connect(
            lambda v: self.confidence_value.setText(f"{v}%")
        )

        conf_row.addWidget(self.confidence_slider)
        conf_row.addWidget(self.confidence_value)
        layout.addLayout(conf_row, 1, 1)

        sd_lab = QLabel("Stand Down:")
        self._update_label_style(sd_lab)
        layout.addWidget(sd_lab, 1, 2)

        self.stand_down_spin = QSpinBox()
        self.stand_down_spin.setFont(font)
        self.stand_down_spin.setRange(0, 300)
        self.stand_down_spin.setValue(30)
        self.stand_down_spin.setFixedHeight(30)
        self.stand_down_spin.setMaximumWidth(90)
        self._update_spinbox_style(self.stand_down_spin)
        layout.addWidget(self.stand_down_spin, 1, 3)

        group.setLayout(layout)

    # ---------- Buttons row ----------

    def _create_control_buttons(self) -> QHBoxLayout:
        font = QFont("Arial", 20, QFont.Weight.Bold)
        row = QHBoxLayout()
        row.setSpacing(12)

        self.save_btn = QPushButton("💾 Save Settings")
        self.save_btn.setFont(font)
        self.save_btn.clicked.connect(self.save_config)
        self.save_btn.setFixedHeight(45)
        self.save_btn.setMinimumWidth(160)
        self._update_save_button_style()

        self.reset_btn = QPushButton("🔄 Reset")
        self.reset_btn.setFont(font)
        self.reset_btn.clicked.connect(self.reset_to_defaults)
        self.reset_btn.setFixedHeight(45)
        self.reset_btn.setMinimumWidth(120)
        self._update_reset_button_style()

        self.test_connection_btn = QPushButton("🔗 Test")
        self.test_connection_btn.setFont(font)
        self.test_connection_btn.clicked.connect(self.test_websocket_connection)
        self.test_connection_btn.setFixedHeight(45)
        self.test_connection_btn.setMinimumWidth(110)
        self._update_test_button_style()

        row.addWidget(self.save_btn)
        row.addWidget(self.reset_btn)
        row.addWidget(self.test_connection_btn)
        row.addStretch()
        return row

    def _update_save_button_style(self):
        green = theme_manager.get("green")
        green_gradient = theme_manager.get("green_gradient")
        self.save_btn.setStyleSheet(f"""
        QPushButton {{
            background: {green_gradient};
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: bold;
        }}
        QPushButton:hover {{ 
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #55cc55, stop:1 #339933);
        }}
        QPushButton:pressed {{ 
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #339933, stop:1 #226622);
        }}
        """)

    def _update_reset_button_style(self):
        red = theme_manager.get("red")
        self.reset_btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {red};
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: #da190b; }}
        QPushButton:pressed {{ background-color: #c41e3a; }}
        """)

    def _update_test_button_style(self):
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        self.test_connection_btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {primary};
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: {primary_light}; }}
        QPushButton:pressed {{ 
            background-color: {primary};
        }}
        """)

    # ---------- Widget styling helpers ----------

    def _update_label_style(self, label: QLabel):
        label.setStyleSheet("color: white; background: transparent;")

    def _update_input_style(self, input_field: QLineEdit):
        primary = theme_manager.get("primary_color")
        input_field.setStyleSheet(f"""
        QLineEdit {{
            background-color: #2d2d2d;
            border: 1px solid #555;
            border-radius: 4px;
            padding: 6px;
            color: white;
        }}
        QLineEdit:focus {{ 
            border-color: {primary}; 
            background-color: #333333;
        }}
        """)

    def _update_combo_style(self, combo: QComboBox):
        primary = theme_manager.get("primary_color")
        combo.setStyleSheet(f"""
        QComboBox {{
            background-color: #2d2d2d;
            border: 1px solid #555;
            border-radius: 4px;
            padding: 6px;
            color: white;
        }}
        QComboBox:focus {{ 
            border-color: {primary}; 
            background-color: #333333;
        }}
        QComboBox::drop-down {{ border: none; }}
        QComboBox::down-arrow {{ image: none; border: none; }}
        QComboBox QAbstractItemView {{
            background-color: #2d2d2d;
            color: white;
            selection-background-color: {primary};
        }}
        """)

    def _update_spinbox_style(self, spinbox: QSpinBox):
        primary = theme_manager.get("primary_color")
        spinbox.setStyleSheet(f"""
        QSpinBox {{
            background-color: #2d2d2d;
            border: 1px solid #555;
            border-radius: 4px;
            padding: 6px;
            color: white;
        }}
        QSpinBox:focus {{ 
            border-color: {primary}; 
            background-color: #333333;
        }}
        """)

    def _update_slider_style(self, slider: QSlider):
        primary = theme_manager.get("primary_color")
        primary_light = theme_manager.get("primary_light")
        slider.setStyleSheet(f"""
        QSlider::groove:horizontal {{
            border: 1px solid #555;
            height: 6px;
            background: #2d2d2d;
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: {primary};
            border: 1px solid {primary};
            width: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{
            background: {primary_light};
            border-color: {primary_light};
        }}
        """)

    def _update_value_label_style(self, label: QLabel):
        primary = theme_manager.get("primary_color")
        label.setStyleSheet(f"color: {primary}; padding-left: 4px; background: transparent;")

    # ---------- Theme change hook ----------

    def _on_theme_changed(self):
        """Handle theme change by updating all styled components"""
        try:
            # Frame + header
            self._update_main_frame_style()
            if hasattr(self, 'header'):
                self._update_header_style()
            self._update_scroll_area_style()

            # Theme buttons - update all button styles
            self._update_theme_button_styles()

            # Sections
            for group in self.findChildren(QGroupBox):
                self._update_section_style(group)

            # Labels
            for label in self.findChildren(QLabel):
                if label is getattr(self, "header", None):
                    self._update_header_style()
                elif label is getattr(self, "confidence_value", None):
                    self._update_value_label_style(label)
                else:
                    self._update_label_style(label)

            # Inputs
            for edit in self.findChildren(QLineEdit):
                self._update_input_style(edit)
            for combo in self.findChildren(QComboBox):
                self._update_combo_style(combo)
            for spin in self.findChildren(QSpinBox):
                self._update_spinbox_style(spin)
            for slider in self.findChildren(QSlider):
                self._update_slider_style(slider)

            # Buttons
            self._update_save_button_style()
            self._update_reset_button_style()
            self._update_test_button_style()

            self.logger.info(f"Settings screen updated for theme: {theme_manager.get_theme_name()}")
        except Exception as e:
            self.logger.warning(f"Failed to apply theme changes: {e}")

    # ---------- Config I/O ----------

    @error_boundary
    def load_config(self):
        """Load current configuration settings"""
        cfg = config_manager.get_config(self.config_path)
        current = cfg.get("current", {})
        wave = current.get("wave_detection", {})
        module_debug = current.get("module_debug", {})

        # Network
        self.network_inputs["esp32_url"].setText(current.get("esp32_cam_url", ""))
        self.network_inputs["proxy_url"].setText(current.get("camera_proxy_url", ""))
        self.network_inputs["control_ws"].setText(current.get("control_websocket_url", "localhost:8766"))

        # Logging
        self.debug_combos["debug_combo"].setCurrentText(current.get("debug_level", "INFO"))
        self.debug_combos["camera_debug_combo"].setCurrentText(module_debug.get("camera", "INFO"))
        self.debug_combos["servo_debug_combo"].setCurrentText(module_debug.get("servo", "INFO"))
        self.debug_combos["network_debug_combo"].setCurrentText(module_debug.get("network", "INFO"))

        # Wave
        self.sample_duration_spin.setValue(wave.get("sample_duration", 3))
        self.sample_rate_spin.setValue(wave.get("sample_rate", 5))
        conf_pct = int(wave.get("confidence_threshold", 0.7) * 100)
        self.confidence_slider.setValue(conf_pct)
        self.confidence_value.setText(f"{conf_pct}%")
        self.stand_down_spin.setValue(wave.get("stand_down_time", 30))

        # Theme selector state - ensure buttons reflect current theme
        self._update_theme_button_styles()

    
    def save_config(self):
        """Validate and save settings to file"""
        if not self._validate_inputs():
            return
        
        try:
            existing = config_manager.get_config(self.config_path)
        except Exception:
            existing = {}

        new_config = {
            "current": {
                "esp32_cam_url": self.network_inputs["esp32_url"].text().strip(),
                "camera_proxy_url": self.network_inputs["proxy_url"].text().strip(),
                "control_websocket_url": self.network_inputs["control_ws"].text().strip(),
                "debug_level": self.debug_combos["debug_combo"].currentText(),
                "module_debug": {
                    "camera": self.debug_combos["camera_debug_combo"].currentText(),
                    "servo": self.debug_combos["servo_debug_combo"].currentText(),
                    "network": self.debug_combos["network_debug_combo"].currentText(),
                    **{
                        k: v for k, v in existing.get("current", {}).get("module_debug", {}).items()
                        if k not in {"camera", "servo", "network"}
                    }
                },
                "wave_detection": {
                    "sample_duration": self.sample_duration_spin.value(),
                    "sample_rate": self.sample_rate_spin.value(),
                    "confidence_threshold": self.confidence_slider.value() / 100.0,
                    "stand_down_time": self.stand_down_spin.value(),
                }
            },
            "defaults": existing.get("defaults", {})
        }
        try:
            success = config_manager.save_config(self.config_path, new_config)
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")
            success = False

        if success:
            if self.websocket:
                self.send_websocket_message(
                    "update_camera_config",
                    esp32_url=self.network_inputs["esp32_url"].text().strip()
                )

            QMessageBox.information(
                self,
                "Settings Saved",
                "Configuration updated successfully.\n\n"
                "Note: Some changes (e.g., global log level) may require app restart."
            )
            self.logger.info("Configuration updated successfully")
            self._notify_config_changes()
        else:
            QMessageBox.critical(
                self,
                "Save Failed",
                "Failed to save configuration.\n\nPlease check file permissions and try again."
            )
            self.logger.error("Failed to save configuration")

    @error_boundary
    def reset_to_defaults(self):
        """Reset configuration to default values"""
        reply = QMessageBox.question(
            self,
            "Reset to Defaults",
            "Are you sure you want to reset all settings to default values?\n\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        cfg = config_manager.get_config(self.config_path)
        defaults = cfg.get("defaults", {})
        if defaults:
            cfg["current"] = defaults.copy()
            if config_manager.save_config(self.config_path, cfg):
                self.load_config()
                QMessageBox.information(self, "Reset Complete", "Configuration has been reset to defaults.")
                self.logger.info("Configuration reset to defaults")
            else:
                QMessageBox.critical(self, "Reset Failed", "Failed to reset configuration.")
        else:
            self._create_default_config()
            QMessageBox.information(self, "Defaults Created", "Default configuration has been created and applied.")

    @error_boundary
    def test_websocket_connection(self, checked=False):
        """Comprehensive network connectivity test with progress dialog"""
        # Get all network URLs
        ws_url = self.network_inputs["control_ws"].text().strip()
        esp32_url = self.network_inputs["esp32_url"].text().strip()
        proxy_url = self.network_inputs["proxy_url"].text().strip()
        
        if not any([ws_url, esp32_url, proxy_url]):
            QMessageBox.warning(self, "No URLs to Test", "Please enter at least one network URL before testing.")
            return

        # Create and configure progress dialog
        self.progress_dialog = QProgressDialog("Initializing network tests...", "Cancel", 0, 0, self)
        self.progress_dialog.setWindowTitle("Network Connectivity Test")
        self.progress_dialog.setModal(True)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.show()
        
        # Create and start test thread
        self.test_thread = NetworkTestThread(
            esp32_url=esp32_url,
            proxy_url=proxy_url, 
            ws_url=ws_url,
            websocket_sender=self.send_websocket_message if hasattr(self, 'send_websocket_message') else None
        )
        
        # Connect signals
        self.test_thread.progress_updated.connect(self.update_test_progress)
        self.test_thread.test_completed.connect(self.show_test_results)
        self.progress_dialog.canceled.connect(self.test_thread.terminate)
        
        # Start testing
        self.test_thread.start()
    # ---------- Network Testing ----------

    def update_test_progress(self, message, status):
        """Update progress dialog with current test status"""
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.setLabelText(message)
            QApplication.processEvents()  # Keep UI responsive

    def show_test_results(self, results):
        """Display comprehensive test results"""
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()
        
        if 'error' in results:
            QMessageBox.critical(self, "Test Failed", results['error'])
            return
        
        # Build results display
        result_lines = ["Network Connectivity Test Results:", ""]
        
        test_categories = [
            ("URL Format Validation", ['ws_format', 'esp32_format', 'proxy_format']),
            ("Camera Proxy Management", ['proxy_status', 'proxy_disable', 'proxy_enable']), 
            ("Network Connectivity", ['esp32_connection', 'proxy_connection', 'websocket_connection'])
        ]
        
        overall_success = True
        
        for category, test_keys in test_categories:
            result_lines.append(f"🔍 {category}:")
            
            for key in test_keys:
                if key in results:
                    result = results[key]
                    status = result['status']
                    message = result['message']
                    
                    if status == 'success':
                        icon = "✅"
                    elif status == 'warning':
                        icon = "⚠️"
                    elif status == 'info':
                        icon = "ℹ️"
                    else:
                        icon = "❌"
                        overall_success = False
                    
                    result_lines.append(f"  {icon} {message}")
            
            result_lines.append("")
        
        # Add summary
        if overall_success:
            result_lines.append("🎉 All critical tests passed! Your network configuration looks good.")
        else:
            result_lines.append("⚠️ Some tests failed. Please check the issues above and verify your network configuration.")
        
        # Show results in appropriate dialog type
        result_text = "\n".join(result_lines)
        if overall_success:
            QMessageBox.information(self, "Network Test - Success", result_text)
        else:
            QMessageBox.warning(self, "Network Test - Issues Found", result_text)
        
        # Log results
        passed_count = len([r for r in results.values() if isinstance(r, dict) and r.get('status') == 'success'])
        total_count = len([r for r in results.values() if isinstance(r, dict)])
        self.logger.info(f"Network connectivity test completed: {passed_count}/{total_count} tests passed")


    # ---------- Validation / Notifications ----------

    def _validate_inputs(self) -> bool:
        errors = []

        esp32_url = self.network_inputs["esp32_url"].text().strip()
        proxy_url = self.network_inputs["proxy_url"].text().strip()
        ws_url = self.network_inputs["control_ws"].text().strip()

        if esp32_url and not (esp32_url.startswith("http://") or esp32_url.startswith("https://")):
            errors.append("ESP32 URL must start with http:// or https://")
        if proxy_url and not (proxy_url.startswith("http://") or proxy_url.startswith("https://")):
            errors.append("Camera Proxy URL must start with http:// or https://")
        if not ws_url:
            errors.append("WebSocket URL is required")

        if self.sample_duration_spin.value() < 1:
            errors.append("Sample duration must be at least 1 second")
        if self.sample_rate_spin.value() < 1:
            errors.append("Sample rate must be at least 1 Hz")

        if errors:
            QMessageBox.warning(
                self,
                "Invalid Settings",
                "Please correct the following errors:\n\n" + "\n".join(f"• {e}" for e in errors)
            )
            return False
        return True

    def _create_default_config(self):
        default_config = {
            "current": {
                "esp32_cam_url": "http://esp32.local:81/stream",
                "camera_proxy_url": "http://10.1.1.230:8081/stream",
                "control_websocket_url": "localhost:8766",
                "debug_level": "INFO",
                "module_debug": {
                    "camera": "INFO",
                    "servo": "INFO",
                    "network": "INFO",
                    "websocket": "WARNING",
                    "telemetry": "INFO",
                    "ui": "INFO",
                    "config": "WARNING",
                    "main": "INFO",
                    "controller": "INFO",
                    "error": "ERROR",
                },
                "network_monitoring": {"update_interval": 5.0, "ping_samples": 3},
                "wave_detection": {
                    "sample_duration": 3,
                    "sample_rate": 5,
                    "confidence_threshold": 0.7,
                    "stand_down_time": 30,
                },
            }
        }
        default_config["defaults"] = default_config["current"].copy()
        config_manager.save_config(self.config_path, default_config)
        self.load_config()

    def _notify_config_changes(self):
        """Notify other components about configuration changes"""
        try:
            from PyQt6.QtWidgets import QApplication

            app = QApplication.instance()
            if not app:
                return

            for widget in app.allWidgets():
                if hasattr(widget, "reload_wave_settings"):
                    widget.reload_wave_settings()
                elif hasattr(widget, "reload_camera_settings"):
                    widget.reload_camera_settings()
                elif hasattr(widget, "reload_network_settings"):
                    widget.reload_network_settings()

        except Exception as e:
            self.logger.warning(f"Failed to notify components of config changes: {e}")

