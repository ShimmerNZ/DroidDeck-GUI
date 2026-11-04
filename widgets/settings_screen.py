#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Settings Screen (Themed)
"""
import requests
import socket
import time
import atexit
import os
import sys
import zipfile
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse 
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QLineEdit, QSpinBox, QSlider, QPushButton,
    QComboBox, QMessageBox, QGroupBox, QFrame, QScrollArea, QWidget, QApplication
)
from PyQt6.QtGui import QFont, QColor, QValidator
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal

from widgets.base_screen import BaseScreen
from widgets.flow_dialog import FlowDialog, STEP_ERROR
from core.version import save_build_info
from core.config_manager import config_manager
from core.theme_manager import theme_manager
from core.utils import error_boundary

# Card layout - matches the Health screen card style
CARD_OBJECT_NAME = "settings_card"
CARD_GAP = 12
CONTENT_WIDTH = 1067
TOP_CARD_HEIGHT = 176
NETWORK_CARD_WIDTH = 640
MIDDLE_CARD_HEIGHT = 246
TEST_BUTTON_WIDTH = 100

# Fixed colours shared by every theme
LABEL_GREY = "#9e9e9e"
TEXT_SOFT = "#bdbdbd"
TILE_BG = "#202020"


def px_font(pixel_size: int, bold: bool = False, spacing: float = 0.0) -> QFont:
    """Font sized in pixels so the layout matches the mockup"""
    font = QFont("Arial")
    font.setPixelSize(pixel_size)
    font.setBold(bold)
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return font


def card_style() -> str:
    """Card frame: panel background with the theme colour as a soft border"""
    primary = QColor(theme_manager.get("primary_color"))
    panel_bg = theme_manager.get("panel_bg")
    border = f"rgba({primary.red()}, {primary.green()}, {primary.blue()}, 0.45)"
    return f"""
        QFrame#{CARD_OBJECT_NAME} {{
            background-color: {panel_bg};
            border: 1px solid {border};
            border-radius: 10px;
        }}
        QLabel {{
            border: none;
            background: transparent;
        }}
    """


def button_style(checked_fill: str = None) -> str:
    """Button matching the Health screen buttons; checkable ones fill when on"""
    primary = theme_manager.get("primary_color")
    style = f"""
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #4a4a4a, stop:1 #2a2a2a);
            color: white;
            border: 1px solid #666;
            border-radius: 8px;
            padding: 4px;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #5a5a5a, stop:1 #3a3a3a);
            border-color: {primary};
        }}
        QPushButton:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #3a3a3a, stop:1 #1a1a1a);
            border-color: {primary};
        }}
        QPushButton:disabled {{
            background: #333;
            color: #666;
            border-color: #444;
        }}
    """
    if checked_fill:
        style += f"""
        QPushButton:checked {{
            background: {checked_fill};
            border: 1px solid {checked_fill};
            color: #111111;
        }}
        """
    return style


def filled_button_style(fill: str) -> str:
    """Solid button for the main action"""
    return f"""
        QPushButton {{
            background: {fill};
            color: #111111;
            border: 1px solid {fill};
            border-radius: 8px;
            padding: 4px;
        }}
        QPushButton:hover {{
            border: 2px solid white;
        }}
        QPushButton:pressed {{
            background: #2e2e2e;
            color: {fill};
        }}
        QPushButton:disabled {{
            background: #333;
            color: #666;
            border-color: #444;
        }}
    """


# Battery types in button order; the backend supplies each type's cell values
BATTERY_TYPES = [("lithium", "Lithium"), ("lifepo4", "LiFePO4"), ("lead_acid", "Lead acid")]
LEAD_ACID_CELLS_PER_BATTERY = 6
LEAD_ACID_BATTERY_VOLTS = 12


class OptionSpinBox(QSpinBox):
    """Spin box that steps through a list of options shown by label"""

    def __init__(self):
        super().__init__()
        self._options = []
        self._labels = []
        self.lineEdit().setReadOnly(True)

    def set_options(self, options, labels, current):
        """Replace the options and select current (or the nearest option)"""
        self.blockSignals(True)
        self._options = list(options)
        self._labels = list(labels)
        self.setRange(0, max(0, len(self._options) - 1))
        if self._options:
            nearest = min(range(len(self._options)), key=lambda i: abs(self._options[i] - current))
            self.setValue(nearest)
        self.blockSignals(False)
        self.lineEdit().setText(self.textFromValue(self.value()))

    def option(self):
        """The selected option, or None before options are set"""
        if not self._options:
            return None
        return self._options[self.value()]

    def textFromValue(self, value):
        if 0 <= value < len(self._labels):
            return self._labels[value]
        return ""

    def valueFromText(self, text):
        return self._labels.index(text) if text in self._labels else self.value()

    def validate(self, text, pos):
        return (QValidator.State.Acceptable, text, pos)


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


class UpdateThread(QThread):
    """Background thread for downloading and installing GUI updates from GitHub"""

    progress_updated = pyqtSignal(str)
    update_completed = pyqtSignal(bool, str)

    GITHUB_REPO = "ShimmerNZ/DroidDeck-GUI"

    def __init__(self, branch: str = "main"):
        super().__init__()
        self.branch = branch
        self.app_root = self._get_app_root()

    @property
    def GITHUB_ZIP_URL(self):
        return f"https://github.com/{self.GITHUB_REPO}/archive/refs/heads/{self.branch}.zip"
    
    # Files/folders to protect (will NOT be overwritten)
    PROTECTED_PATHS = [
        "resources/configs/",
        "resources/configs/controller_config.json",
        "resources/configs/controller_mappings.json",
        "resources/configs/motion_config.json",
        "resources/configs/movement_controls.json",
        "resources/configs/scenes_config.json",
        "resources/configs/servo_config.json",
        "resources/configs/steamdeck_config.json",
        "resources/configs/theme_config.json",
        "resources/configs/voltage_alert_config.json",
    ]
    
    def _get_app_root(self) -> Path:
        """Determine the application root directory"""
        # If running from a script, use that directory
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            return Path(sys.executable).parent
        else:
            # Running as script - find main.py location
            # Assume this file is in widgets/ and main.py is in parent
            return Path(__file__).parent.parent
    
    def run(self):
        """Download and install update"""
        temp_dir = None
        try:
            # Step 1: Download
            self.progress_updated.emit("Downloading update from GitHub...")
            temp_dir = Path(tempfile.mkdtemp())
            zip_path = temp_dir / "update.zip"

            # connect timeout, read timeout (seconds per chunk)
            response = requests.get(self.GITHUB_ZIP_URL, stream=True, timeout=(15, 30))

            if response.status_code == 404:
                raise Exception(
                    f"Branch '{self.branch}' not found on GitHub.\n"
                    "Check the branch name and try again."
                )
            elif response.status_code == 403:
                raise Exception(
                    "GitHub rate limit reached or access denied.\n"
                    "Wait a few minutes and try again."
                )
            elif response.status_code != 200:
                raise Exception(
                    f"GitHub returned an unexpected error (HTTP {response.status_code}).\n"
                    "Try again later."
                )

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size:
                            percent = int((downloaded / total_size) * 100)
                            self.progress_updated.emit(f"Downloading: {percent}%")

            # Step 2: Extract
            self.progress_updated.emit("Extracting files...")
            extract_dir = temp_dir / "extracted"
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
                # GitHub archives carry the commit id as the zip comment
                commit = zip_ref.comment.decode("ascii", "ignore").strip()

            # Find the extracted folder (GitHub adds repo name prefix)
            extracted_folders = list(extract_dir.iterdir())
            if not extracted_folders:
                raise Exception("No files found in downloaded archive.")

            source_dir = extracted_folders[0]

            # Step 3: Update files (skip protected configs)
            self.progress_updated.emit("Installing update...")
            self._update_files(source_dir, self.app_root)
            try:
                save_build_info(self.app_root, self.branch, commit)
            except Exception as e:
                print(f"Warning: Could not record installed version: {e}")

            self.update_completed.emit(True, "Update completed successfully! Please restart the application.")

        except requests.exceptions.ConnectionError:
            self.update_completed.emit(False, "Could not reach GitHub. Check the network connection and try again.")
        except requests.exceptions.Timeout:
            self.update_completed.emit(False, "Download timed out. Check the network connection and try again.")
        except requests.exceptions.RequestException as e:
            self.update_completed.emit(False, f"Download failed: {str(e)}")
        except zipfile.BadZipFile:
            self.update_completed.emit(False, "Downloaded file is corrupted. Try again.")
        except Exception as e:
            self.update_completed.emit(False, f"Update failed: {str(e)}")
        finally:
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
    
    def _update_files(self, source_dir: Path, target_dir: Path):
        """Copy files from source to target, protecting config files"""
        for item in source_dir.rglob('*'):
            if item.is_file():
                # Get relative path from source
                rel_path = item.relative_to(source_dir)
                target_path = target_dir / rel_path
                
                # Check if this file is protected
                if self._is_protected(rel_path):
                    continue  # Skip protected files
                
                # Create parent directory if needed
                target_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy file
                try:
                    shutil.copy2(item, target_path)
                except Exception as e:
                    # Log but don't fail on individual file errors
                    print(f"Warning: Could not update {rel_path}: {e}")
    
    def _is_protected(self, rel_path: Path) -> bool:
        """Check if a file path should be protected from updates"""
        path_str = str(rel_path).replace('\\', '/')
        
        for protected in self.PROTECTED_PATHS:
            if path_str.startswith(protected) or path_str == protected:
                return True
        
        return False


class SettingsScreen(BaseScreen):
    """Configuration interface for system settings with theme manager integration"""

    SERVER_UPDATE_REPO = "ShimmerNZ/Wall-e-Backend"
    SERVER_UPDATE_TIMEOUT_MS = 120000

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
        """Initialize settings interface: network card on top, three cards, action buttons"""
        self.config_path = "resources/configs/steamdeck_config.json"

        # Styled widgets, re-styled on theme change
        self._cards = []
        self._card_titles = []
        self._captions = []
        self._soft_labels = []
        self._value_tiles = []
        self._plain_buttons = []

        root = QVBoxLayout()
        root.setContentsMargins(101, 40, 12, 6)
        root.setSpacing(CARD_GAP)

        content = QWidget()
        content.setFixedWidth(CONTENT_WIDTH)
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(CARD_GAP)

        # Network sits at the top so the fields stay visible above the on-screen keyboard
        top = QHBoxLayout()
        top.setSpacing(CARD_GAP)
        network = self._build_network()
        network.setFixedWidth(NETWORK_CARD_WIDTH)
        top.addWidget(network)
        top.addWidget(self._build_wave(), 1)
        content_layout.addLayout(top)

        middle = QHBoxLayout()
        middle.setSpacing(CARD_GAP)
        middle.addWidget(self._create_theme_selector(), 1)
        middle.addWidget(self._build_battery(), 2)
        middle.addWidget(self._build_logging(), 1)
        content_layout.addLayout(middle)

        content_layout.addLayout(self._create_control_buttons())

        root.addWidget(content, 0, Qt.AlignmentFlag.AlignLeft)
        root.addStretch(1)
        self.setLayout(root)

        self._apply_styles()

        self._server_update_pending = False
        self.subscribe("server_update_progress", self._on_server_update_progress)
        self.subscribe("server_update_complete", self._on_server_update_complete)
        self.subscribe("battery_config_data", self._on_battery_config)

        # Load config on open
        self.load_config()

    # ---------- Widget helpers ----------

    def _make_card(self, title: str, height: int):
        """Titled card; returns (card, layout)"""
        card = QFrame()
        card.setObjectName(CARD_OBJECT_NAME)
        card.setFixedHeight(height)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setFont(px_font(14, bold=True, spacing=1.5))
        layout.addWidget(title_label)

        self._cards.append(card)
        self._card_titles.append(title_label)
        return card, layout

    def _make_caption(self, text: str) -> QLabel:
        """Small grey caption above a control"""
        label = QLabel(text)
        label.setFont(px_font(12, spacing=1.0))
        self._captions.append(label)
        return label

    def _make_soft_label(self, text: str, pixel_size: int) -> QLabel:
        """Setting name label"""
        label = QLabel(text)
        label.setFont(px_font(pixel_size))
        self._soft_labels.append(label)
        return label

    def _make_button(self, text: str, height: int = 44, pixel_size: int = 16) -> QPushButton:
        """Standard button in the shared card style"""
        button = QPushButton(text)
        button.setFont(px_font(pixel_size, bold=True))
        button.setFixedHeight(height)
        self._plain_buttons.append(button)
        return button

    def _make_value_tile(self, text: str, height: int, pixel_size: int) -> QLabel:
        """Read-only value between - and + buttons"""
        label = QLabel(text)
        label.setFont(px_font(pixel_size))
        label.setFixedHeight(height)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._value_tiles.append(label)
        return label

    def _make_spinbox(self, minimum: int, maximum: int, value: int, suffix: str) -> QSpinBox:
        spin = QSpinBox()
        spin.setFont(px_font(18))
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.setFixedHeight(40)
        return spin

    # ---------- Theme selector ----------

    def _create_theme_selector(self) -> QFrame:
        """Appearance card: theme buttons and system volume"""
        card, layout = self._make_card("APPEARANCE", MIDDLE_CARD_HEIGHT)

        layout.addWidget(self._make_caption("THEME"))
        themes_row = QHBoxLayout()
        themes_row.setSpacing(8)

        self.theme_buttons = {}  # Use dict for easier lookup

        # Use available themes reported by ThemeManager
        theme_names = theme_manager.available_themes()
        current_theme = theme_manager.get_theme_name()

        for name in theme_names:
            display_name = "WALL-E" if name == "Wall-e" else name
            btn = QPushButton(display_name)
            btn.setCheckable(True)
            btn.setFont(px_font(16, bold=True))
            btn.setFixedHeight(44)

            # Set initial state based on current theme
            btn.setChecked(name == current_theme)

            # Connect with theme name, not display name
            btn.clicked.connect(lambda checked, theme_name=name: self._on_theme_selected(theme_name))

            self.theme_buttons[name] = btn
            themes_row.addWidget(btn, 1)
        layout.addLayout(themes_row)

        layout.addSpacing(6)
        layout.addWidget(self._make_caption("SYSTEM VOLUME"))

        vol_control = QHBoxLayout()
        vol_control.setSpacing(8)

        self.volume_minus_btn = self._make_button("−", 44, 22)
        self.volume_minus_btn.setFixedWidth(44)
        self.volume_minus_btn.setAccessibleName("Volume down")
        self.volume_minus_btn.clicked.connect(lambda: self._adjust_volume(-5))

        self.volume_value = self._make_value_tile("70%", 44, 20)

        self.volume_plus_btn = self._make_button("+", 44, 22)
        self.volume_plus_btn.setFixedWidth(44)
        self.volume_plus_btn.setAccessibleName("Volume up")
        self.volume_plus_btn.clicked.connect(lambda: self._adjust_volume(5))

        vol_control.addWidget(self.volume_minus_btn)
        vol_control.addWidget(self.volume_value, 1)
        vol_control.addWidget(self.volume_plus_btn)
        layout.addLayout(vol_control)

        layout.addStretch(1)
        return card

    def _update_theme_button_styles(self):
        """Update all theme button styles based on current selection"""
        current_theme = theme_manager.get_theme_name()
        primary = theme_manager.get("primary_color")
        for theme_name, btn in self.theme_buttons.items():
            btn.setChecked(theme_name == current_theme)
            btn.setStyleSheet(button_style(checked_fill=primary))

    def _on_theme_selected(self, theme_name: str):
        """Handle theme selection"""
        # Only proceed if this is actually a different theme
        if theme_name == theme_manager.get_theme_name():
            # Clicking the current theme must not leave it unchecked
            self._update_theme_button_styles()
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

    def _build_network(self) -> QFrame:
        """Network card: full-width URL fields, with the connection test beside the WebSocket"""
        card, layout = self._make_card("NETWORK", TOP_CARD_HEIGHT)
        layout.setSpacing(6)

        labels = [
            ("ESP32 Camera", "esp32_url", "http://192.168.1.100:81/stream"),
            ("Camera Proxy", "proxy_url", "http://10.1.1.230:8081/stream"),
            ("Control WebSocket", "control_ws", "ws://10.1.1.230:8766"),
        ]
        self.network_inputs = {}

        for text, key, placeholder in labels:
            row = QHBoxLayout()
            row.setSpacing(12)

            lab = self._make_soft_label(text, 16)
            lab.setFixedWidth(150)

            edit = QLineEdit()
            edit.setFont(px_font(17))
            edit.setFixedHeight(40)
            edit.setPlaceholderText(placeholder)

            row.addWidget(lab)
            row.addWidget(edit, 1)

            if key == "control_ws":
                self.test_connection_btn = self._make_button("TEST", 40, 15)
                self.test_connection_btn.setFixedWidth(TEST_BUTTON_WIDTH)
                self.test_connection_btn.clicked.connect(self.test_websocket_connection)
                row.addWidget(self.test_connection_btn)
            else:
                row.addSpacing(TEST_BUTTON_WIDTH)

            self.network_inputs[key] = edit
            layout.addLayout(row)

        return card

    def _build_logging(self) -> QFrame:
        """Logging card: one debug level per row"""
        card, layout = self._make_card("LOGGING", MIDDLE_CARD_HEIGHT)

        items = [
            ("Global debug", "debug_combo"),
            ("Camera debug", "camera_debug_combo"),
            ("Servo debug", "servo_debug_combo"),
            ("Network debug", "network_debug_combo"),
        ]
        self.debug_combos = {}

        for label_text, key in items:
            row = QHBoxLayout()
            row.setSpacing(10)
            lab = self._make_soft_label(label_text, 15)

            combo = QComboBox()
            combo.setFont(px_font(15))
            combo.addItems(["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"])
            combo.setFixedHeight(38)
            combo.setFixedWidth(110)

            self.debug_combos[key] = combo
            row.addWidget(lab, 1)
            row.addWidget(combo)
            layout.addLayout(row)

        layout.addStretch(1)
        return card

    def _build_wave(self) -> QFrame:
        """Wave detection card: 2x2 grid of controls"""
        card, layout = self._make_card("WAVE DETECTION", TOP_CARD_HEIGHT)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self.sample_duration_spin = self._make_spinbox(1, 10, 3, " s")
        self.sample_rate_spin = self._make_spinbox(1, 60, 5, " /s")
        self.stand_down_spin = self._make_spinbox(0, 300, 30, " s")

        # Confidence: - value +
        conf_row = QHBoxLayout()
        conf_row.setSpacing(4)

        self.confidence_minus_btn = self._make_button("−", 40, 20)
        self.confidence_minus_btn.setFixedWidth(40)
        self.confidence_minus_btn.setAccessibleName("Confidence down")
        self.confidence_minus_btn.clicked.connect(lambda: self._adjust_confidence(-5))

        self.confidence_value = self._make_value_tile("70%", 40, 18)

        self.confidence_plus_btn = self._make_button("+", 40, 20)
        self.confidence_plus_btn.setFixedWidth(40)
        self.confidence_plus_btn.setAccessibleName("Confidence up")
        self.confidence_plus_btn.clicked.connect(lambda: self._adjust_confidence(5))

        conf_row.addWidget(self.confidence_minus_btn)
        conf_row.addWidget(self.confidence_value, 1)
        conf_row.addWidget(self.confidence_plus_btn)

        cells = [
            ("SAMPLE DURATION", self.sample_duration_spin, 0, 0),
            ("SAMPLE RATE", self.sample_rate_spin, 0, 1),
            ("CONFIDENCE", conf_row, 1, 0),
            ("STAND DOWN", self.stand_down_spin, 1, 1),
        ]
        for caption, control, row, col in cells:
            cell = QVBoxLayout()
            cell.setSpacing(4)
            cell.addWidget(self._make_caption(caption))
            if isinstance(control, QHBoxLayout):
                cell.addLayout(control)
            else:
                cell.addWidget(control)
            grid.addLayout(cell, row, col)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        layout.addLayout(grid)
        layout.addStretch(1)
        return card

    def _build_battery(self) -> QFrame:
        """Battery card: type, pack size and capacity, with the derived alert levels"""
        card, layout = self._make_card("BATTERY", MIDDLE_CARD_HEIGHT)
        layout.setSpacing(6)

        self._battery_table = None
        self._battery_loaded_config = None

        # Type buttons and series / voltage
        type_row = QHBoxLayout()
        type_row.setSpacing(12)

        type_cell = QVBoxLayout()
        type_cell.setSpacing(4)
        type_cell.addWidget(self._make_caption("TYPE"))
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.battery_type_buttons = {}
        for key, label in BATTERY_TYPES:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFont(px_font(15, bold=True))
            btn.setFixedHeight(40)
            btn.clicked.connect(lambda checked, chemistry=key: self._on_battery_type_selected(chemistry))
            self.battery_type_buttons[key] = btn
            buttons.addWidget(btn, 1)
        type_cell.addLayout(buttons)
        type_row.addLayout(type_cell, 1)

        series_cell = QVBoxLayout()
        series_cell.setSpacing(4)
        self.battery_series_caption = self._make_caption("SERIES")
        series_cell.addWidget(self.battery_series_caption)
        self.battery_series_spin = OptionSpinBox()
        self.battery_series_spin.setFont(px_font(17))
        self.battery_series_spin.setFixedSize(170, 40)
        self.battery_series_spin.valueChanged.connect(self._on_battery_series_changed)
        series_cell.addWidget(self.battery_series_spin)
        type_row.addLayout(series_cell)
        layout.addLayout(type_row)

        # Capacity
        capacity_row = QHBoxLayout()
        capacity_row.setSpacing(12)
        self.battery_packs_spin = self._make_spinbox(1, 10, 1, "")
        self.battery_parallel_spin = self._make_spinbox(1, 40, 12, "P")
        self.battery_cell_mah_spin = self._make_spinbox(100, 20000, 3000, "")
        self.battery_cell_mah_spin.setSingleStep(100)
        self.battery_ah_spin = self._make_spinbox(1, 400, 20, "")
        self.battery_capacity_cells = {}
        for key, caption, spin in (
            ("packs", "PACKS", self.battery_packs_spin),
            ("parallel", "PARALLEL", self.battery_parallel_spin),
            ("cell_mah", "CELL mAh", self.battery_cell_mah_spin),
            ("battery_ah", "BATTERY Ah", self.battery_ah_spin),
        ):
            spin.setFont(px_font(17))
            cell = QWidget()
            cell.setStyleSheet("background: transparent;")
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(4)
            cell_layout.addWidget(self._make_caption(caption))
            cell_layout.addWidget(spin)
            self.battery_capacity_cells[key] = cell
            capacity_row.addWidget(cell, 1)
        layout.addLayout(capacity_row)

        # Alert levels, worked out from the type and series
        alert_row = QHBoxLayout()
        alert_row.setSpacing(12)
        alert_caption = self._make_caption("ALERT LEVELS")
        alert_caption.setFixedWidth(110)
        alert_row.addWidget(alert_caption)
        self.battery_alert_tiles = []
        self.battery_alert_values = {}
        for key, caption in (("low", "LOW"), ("critical", "CRITICAL")):
            tile = QFrame()
            tile.setFixedHeight(40)
            tile_layout = QHBoxLayout(tile)
            tile_layout.setContentsMargins(12, 0, 12, 0)
            tile_layout.setSpacing(10)
            name = QLabel(caption)
            name.setFont(px_font(12, spacing=1.0))
            name.setObjectName(f"battery_alert_{key}")
            value = QLabel("--")
            value.setFont(px_font(17))
            tile_layout.addWidget(name)
            tile_layout.addWidget(value, 1)
            self.battery_alert_tiles.append((tile, name, value, key))
            self.battery_alert_values[key] = value
            alert_row.addWidget(tile, 1)
        layout.addLayout(alert_row)

        # Pack voltages, or a warning when the pack is beyond the voltage sensor
        self.battery_info_label = QLabel("Waiting for the robot connection")
        self.battery_info_label.setFont(px_font(13))
        self.battery_info_label.setFixedHeight(20)
        layout.addWidget(self.battery_info_label)

        layout.addStretch(1)
        self._set_battery_enabled(False)
        self._show_capacity_fields("lithium")
        return card

    def _set_battery_enabled(self, enabled: bool):
        """Battery controls only work once the backend has sent the battery types"""
        for btn in self.battery_type_buttons.values():
            btn.setEnabled(enabled)
        for spin in (self.battery_series_spin, self.battery_packs_spin, self.battery_parallel_spin,
                     self.battery_cell_mah_spin, self.battery_ah_spin):
            spin.setEnabled(enabled)

    def _show_capacity_fields(self, chemistry: str):
        """Cell packs show parallel count and cell mAh; lead acid shows battery Ah"""
        mode = "cells"
        if self._battery_table and chemistry in self._battery_table:
            mode = self._battery_table[chemistry].get("capacity_mode", "cells")
        elif chemistry == "lead_acid":
            mode = "battery"
        self.battery_capacity_cells["parallel"].setVisible(mode == "cells")
        self.battery_capacity_cells["cell_mah"].setVisible(mode == "cells")
        self.battery_capacity_cells["battery_ah"].setVisible(mode == "battery")
        self.battery_series_caption.setText("VOLTAGE" if chemistry == "lead_acid" else "SERIES")

    def _selected_battery_type(self) -> str:
        for key, btn in self.battery_type_buttons.items():
            if btn.isChecked():
                return key
        return "lithium"

    def _series_label(self, chemistry: str, series: int) -> str:
        """Series option as shown: '4S · 14.8 V', or '36 V · 3 × 12 V' for lead acid"""
        if chemistry == "lead_acid":
            batteries = series // LEAD_ACID_CELLS_PER_BATTERY
            text = f"{batteries * LEAD_ACID_BATTERY_VOLTS} V"
            if batteries > 1:
                text += f" · {batteries} × {LEAD_ACID_BATTERY_VOLTS} V"
            return text
        nominal = self._battery_table[chemistry]["cell"]["nominal"] * series
        return f"{series}S · {nominal:.1f} V"

    def _set_series_options(self, chemistry: str, current: int):
        options = self._battery_table[chemistry]["series_options"]
        labels = [self._series_label(chemistry, option) for option in options]
        self.battery_series_spin.set_options(options, labels, current)

    def _on_battery_type_selected(self, chemistry: str):
        """Switch type: keep one button checked and refresh the series options"""
        for key, btn in self.battery_type_buttons.items():
            btn.setChecked(key == chemistry)
        if not self._battery_table or chemistry not in self._battery_table:
            return
        current = self.battery_series_spin.option() or 0
        self._set_series_options(chemistry, current)
        self._show_capacity_fields(chemistry)
        self._update_battery_display()

    def _on_battery_series_changed(self, _index: int):
        self._update_battery_display()

    def _update_battery_display(self):
        """Alert levels and pack voltages for the selected type and series"""
        chemistry = self._selected_battery_type()
        series = self.battery_series_spin.option()
        if not self._battery_table or chemistry not in self._battery_table or series is None:
            return
        cell = self._battery_table[chemistry]["cell"]
        self.battery_alert_values["low"].setText(f"{cell['low'] * series:.1f} V")
        self.battery_alert_values["critical"].setText(f"{cell['critical'] * series:.1f} V")

        full = cell["full"] * series
        sensor_max = (self._battery_loaded_config or {}).get("sensor_max_voltage", full)
        if full > sensor_max:
            self.battery_info_label.setText(
                f"{full:.1f} V full is above the sensor range ({sensor_max:.1f} V). "
                "Rewire the divider first."
            )
            self.battery_info_label.setStyleSheet(
                f"color: {theme_manager.get('red')}; background: transparent; border: none;"
            )
        else:
            self.battery_info_label.setText(
                f"Full {full:.1f} V · Nominal {cell['nominal'] * series:.1f} V · "
                f"Empty {cell['empty'] * series:.1f} V"
            )
            self.battery_info_label.setStyleSheet(
                f"color: {LABEL_GREY}; background: transparent; border: none;"
            )

    def _battery_form_config(self) -> dict:
        """Battery config as currently set on the card"""
        config = dict(self._battery_loaded_config or {})
        config.update({
            "chemistry": self._selected_battery_type(),
            "series": self.battery_series_spin.option(),
            "packs": self.battery_packs_spin.value(),
            "parallel": self.battery_parallel_spin.value(),
            "cell_mah": self.battery_cell_mah_spin.value(),
            "battery_ah": self.battery_ah_spin.value(),
        })
        return config

    def _request_battery_config(self):
        if self.websocket and self.websocket.is_connected():
            self.send_websocket_message("get_battery_config")

    def _on_battery_config(self, data: dict):
        """Fill the battery card from the backend's config and battery types"""
        table = data.get("chemistries")
        config = data.get("config")
        if not isinstance(table, dict) or not isinstance(config, dict):
            return
        self._battery_table = table
        self._battery_loaded_config = dict(config)

        chemistry = config.get("chemistry", "lithium")
        if chemistry not in table:
            chemistry = next(iter(table))
        for key, btn in self.battery_type_buttons.items():
            btn.setChecked(key == chemistry)
        self._set_series_options(chemistry, config.get("series", 0))
        for key, spin in (("packs", self.battery_packs_spin), ("parallel", self.battery_parallel_spin),
                          ("cell_mah", self.battery_cell_mah_spin), ("battery_ah", self.battery_ah_spin)):
            if key in config:
                spin.setValue(int(config[key]))
        self._show_capacity_fields(chemistry)
        self._set_battery_enabled(True)
        self._update_battery_display()
        if data.get("saved"):
            self.logger.info("Battery config saved on backend")

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "_battery_table", None) is None:
            self._request_battery_config()

    # ---------- Buttons row ----------

    def _create_control_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(CARD_GAP)

        self.save_btn = QPushButton("SAVE SETTINGS")
        self.save_btn.setFont(px_font(16, bold=True))
        self.save_btn.setFixedSize(220, 44)
        self.save_btn.clicked.connect(self.save_config)

        self.reset_btn = self._make_button("RESET")
        self.reset_btn.setFixedWidth(160)
        self.reset_btn.clicked.connect(self.reset_to_defaults)

        self.update_btn = self._make_button("UPDATE GUI")
        self.update_btn.setFixedWidth(180)
        self.update_btn.clicked.connect(self.check_for_updates)

        self.update_server_btn = self._make_button("UPDATE SERVER")
        self.update_server_btn.setFixedWidth(180)
        self.update_server_btn.clicked.connect(self.check_for_server_updates)

        row.addWidget(self.save_btn)
        row.addWidget(self.reset_btn)
        row.addStretch(1)
        row.addWidget(self.update_btn)
        row.addWidget(self.update_server_btn)
        return row

    # ---------- Styling ----------

    def _apply_styles(self):
        """Apply theme colours to every styled widget"""
        primary = theme_manager.get("primary_color")
        green = theme_manager.get("green")

        for card in self._cards:
            card.setStyleSheet(card_style())
        for title in self._card_titles:
            title.setStyleSheet(f"color: {primary}; background: transparent; border: none;")
        for caption in self._captions:
            caption.setStyleSheet(f"color: {LABEL_GREY}; background: transparent; border: none;")
        for label in self._soft_labels:
            label.setStyleSheet(f"color: {TEXT_SOFT}; background: transparent; border: none;")
        for tile in self._value_tiles:
            tile.setStyleSheet(
                f"color: white; background-color: {TILE_BG}; border: none; border-radius: 8px;"
            )
        for button in self._plain_buttons:
            button.setStyleSheet(button_style())
        self.save_btn.setStyleSheet(filled_button_style(green))

        for edit in self.network_inputs.values():
            self._update_input_style(edit)
        for combo in self.debug_combos.values():
            self._update_combo_style(combo)
        for spin in (self.sample_duration_spin, self.sample_rate_spin, self.stand_down_spin,
                     self.battery_series_spin, self.battery_packs_spin, self.battery_parallel_spin,
                     self.battery_cell_mah_spin, self.battery_ah_spin):
            self._update_spinbox_style(spin)

        for btn in self.battery_type_buttons.values():
            btn.setStyleSheet(button_style(checked_fill=primary))
        red = theme_manager.get("red")
        for tile, name, value, key in self.battery_alert_tiles:
            tile.setStyleSheet(f"QFrame {{ background-color: {TILE_BG}; border: none; border-radius: 6px; }}")
            name.setStyleSheet(f"color: {red if key == 'critical' else primary}; background: transparent;")
            value.setStyleSheet("color: white; background: transparent;")
        self._update_battery_display()

        self._update_theme_button_styles()

    def _update_input_style(self, input_field: QLineEdit):
        primary = theme_manager.get("primary_color")
        input_field.setStyleSheet(f"""
        QLineEdit {{
            background-color: {TILE_BG};
            border: 1px solid #555;
            border-radius: 6px;
            padding: 0px 12px;
            color: white;
        }}
        QLineEdit:focus {{
            border: 2px solid {primary};
            padding: 0px 11px;
        }}
        """)

    def _update_combo_style(self, combo: QComboBox):
        primary = theme_manager.get("primary_color")
        combo.setStyleSheet(f"""
        QComboBox {{
            background-color: {TILE_BG};
            border: 1px solid #555;
            border-radius: 6px;
            padding: 0px 10px;
            color: white;
        }}
        QComboBox:focus {{
            border-color: {primary};
        }}
        QComboBox QAbstractItemView {{
            background-color: {TILE_BG};
            color: white;
            selection-background-color: {primary};
            selection-color: black;
            border: 1px solid #555;
        }}
        """)

    def _update_spinbox_style(self, spinbox: QSpinBox):
        primary = theme_manager.get("primary_color")
        spinbox.setStyleSheet(f"""
        QSpinBox {{
            background-color: {TILE_BG};
            border: 1px solid #555;
            border-radius: 6px;
            padding-left: 10px;
            color: white;
        }}
        QSpinBox:focus {{
            border-color: {primary};
        }}
        """)

    # ---------- Theme change hook ----------

    def _on_theme_changed(self):
        """Handle theme change by updating all styled components"""
        try:
            self._apply_styles()
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
        self.confidence_value.setText(f"{conf_pct}%")
        self.stand_down_spin.setValue(wave.get("stand_down_time", 30))

        # Audio - Load volume
        volume = current.get("volume", 70)
        self.volume_value.setText(f"{volume}%")

        # Theme selector state - ensure buttons reflect current theme
        self._update_theme_button_styles()

    def _adjust_confidence(self, delta: int):
        """Adjust confidence value by delta (e.g., +5 or -5)"""
        current = self._get_confidence_value()
        new_value = max(0, min(100, current + delta))
        self.confidence_value.setText(f"{new_value}%")
    
    def _get_confidence_value(self) -> int:
        """Get current confidence value from label text"""
        try:
            return int(self.confidence_value.text().rstrip('%'))
        except ValueError:
            return 70  # Default value

    def _adjust_volume(self, delta: int):
        """Adjust volume value by delta (e.g., +5 or -5)"""
        current = self._get_volume_value()
        new_value = max(0, min(100, current + delta))
        self.volume_value.setText(f"{new_value}%")
    
    def _get_volume_value(self) -> int:
        """Get current volume value from label text"""
        try:
            return int(self.volume_value.text().rstrip('%'))
        except ValueError:
            return 70  # Default value

    
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
                    "confidence_threshold": self._get_confidence_value() / 100.0,
                    "stand_down_time": self.stand_down_spin.value(),
                },
                "volume": self._get_volume_value()
            },
            "defaults": existing.get("defaults", {})
        }
        try:
            success = config_manager.save_config(self.config_path, new_config)
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")
            success = False

        if success:
            # ALSO save volume to hardware_config.json so it persists on backend restart
            try:
                volume_float = self._get_volume_value() / 100.0  # Convert to 0.0-1.0
                hw_config = config_manager.get_config("configs/hardware_config.json")
                if "hardware" not in hw_config:
                    hw_config["hardware"] = {}
                if "audio" not in hw_config["hardware"]:
                    hw_config["hardware"]["audio"] = {}
                    
                hw_config["hardware"]["audio"]["volume"] = volume_float
                
                if config_manager.save_config("configs/hardware_config.json", hw_config):
                    self.logger.info(f"Volume {volume_float:.2f} saved to hardware_config.json")
            except Exception as e:
                self.logger.warning(f"Could not save volume to hardware_config: {e}")
            
            if self.websocket:
                # Send volume update to backend
                volume_val = self._get_volume_value()
                self.logger.info(f"Sending volume update to backend: {volume_val}%")
                self.send_websocket_message(
                    "set_system_volume",
                    volume=volume_val
                )

                # Send camera URL update to backend so proxy reconnects to new address
                esp32_url = self.network_inputs["esp32_url"].text().strip()
                if esp32_url:
                    self.logger.info(f"Sending camera URL update to backend: {esp32_url}")
                    self.send_websocket_message(
                        "update_camera_url",
                        esp32_url=esp32_url
                    )

                # Apply debug level changes live on the backend
                self.send_websocket_message(
                    "update_debug_levels",
                    debug_level=self.debug_combos["debug_combo"].currentText(),
                    module_debug={
                        "camera": self.debug_combos["camera_debug_combo"].currentText(),
                        "servo":  self.debug_combos["servo_debug_combo"].currentText(),
                        "network": self.debug_combos["network_debug_combo"].currentText(),
                    }
                )

                # Battery settings live on the Pi; only send them when changed,
                # since applying them restarts the run-time estimate
                if self._battery_table is not None:
                    battery_config = self._battery_form_config()
                    if battery_config != self._battery_loaded_config:
                        self.logger.info(f"Sending battery config to backend: {battery_config}")
                        self.send_websocket_message("save_battery_config", config=battery_config)
            else:
                self.logger.warning("WebSocket not available - settings not sent to backend")

            QMessageBox.information(
                self,
                "Settings Saved",
                "Configuration updated successfully.\n\n"
                "Note: Some changes (e.g., global log level, volume) may require app restart."
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

    NETWORK_TEST_STEPS = [
        "Check URL formats",
        "Check camera proxy",
        "Test ESP32 camera",
        "Test camera proxy",
        "Test WebSocket",
    ]

    @error_boundary
    def test_websocket_connection(self, checked=False):
        """Network connectivity test shown in a themed step dialog"""
        ws_url = self.network_inputs["control_ws"].text().strip()
        esp32_url = self.network_inputs["esp32_url"].text().strip()
        proxy_url = self.network_inputs["proxy_url"].text().strip()

        urls = [u for u in (ws_url, esp32_url, proxy_url) if u]
        if not urls:
            QMessageBox.warning(self, "No URLs to Test", "Please enter at least one network URL before testing.")
            return

        noun = "address" if len(urls) == 1 else "addresses"
        self.test_dialog = FlowDialog(self, "NETWORK TEST", f"Testing {len(urls)} {noun}")
        self.test_dialog.show_progress(self.NETWORK_TEST_STEPS, cancellable=True)
        self.test_dialog.set_status("Initializing network tests...")
        self.test_dialog.cancel_requested.connect(self._cancel_network_test)
        self.test_dialog.show()

        self.test_thread = NetworkTestThread(
            esp32_url=esp32_url,
            proxy_url=proxy_url,
            ws_url=ws_url,
            websocket_sender=self.send_websocket_message if hasattr(self, 'send_websocket_message') else None
        )
        self.test_thread.progress_updated.connect(self.update_test_progress)
        self.test_thread.test_completed.connect(self.show_test_results)
        self.test_thread.start()

    def _cancel_network_test(self):
        if hasattr(self, 'test_thread') and self.test_thread.isRunning():
            self.test_thread.terminate()
        if getattr(self, 'test_dialog', None):
            self.test_dialog.close()
            self.test_dialog = None

    # ---------- Network Testing ----------

    def _network_test_step(self, message: str) -> int:
        """Which step of the test a progress message belongs to"""
        text = message.lower()
        if text.startswith("validating"):
            return 0
        if text.startswith("checking camera proxy"):
            return 1
        if ("esp32" in text or text.startswith("temporarily disabling")
                or text.startswith("restoring camera proxy (was")):
            return 2
        if "camera proxy" in text or "proxy test" in text:
            return 3
        if "websocket" in text:
            return 4
        return -1

    def update_test_progress(self, message, status):
        """Advance the test dialog to the step the thread is on"""
        dialog = getattr(self, 'test_dialog', None)
        if not dialog:
            return
        dialog.set_status(message)
        step = self._network_test_step(message)
        if step >= 0:
            dialog.advance_to(step)
            dialog.set_progress((step + 0.5) / len(self.NETWORK_TEST_STEPS))

    def show_test_results(self, results):
        """Show the grouped test results in the test dialog"""
        dialog = getattr(self, 'test_dialog', None)
        if not dialog:
            return

        if 'error' in results:
            dialog.show_result(False, "Test failed", error=results['error'], primary="CLOSE")
            dialog.primary_clicked.connect(dialog.close)
            return

        test_categories = [
            ("URL FORMAT", ['ws_format', 'esp32_format', 'proxy_format']),
            ("CAMERA PROXY", ['proxy_initial_status', 'proxy_control']),
            ("CONNECTIVITY", ['esp32_connection', 'proxy_connection', 'websocket_connection'])
        ]

        groups = []
        passed = failed = 0
        for category, keys in test_categories:
            rows = []
            for key in keys:
                result = results.get(key)
                if not isinstance(result, dict):
                    continue
                status = result.get('status', 'error')
                rows.append((status, result.get('message', '')))
                if status == 'error':
                    failed += 1
                elif status == 'success':
                    passed += 1
            if rows:
                groups.append((category, rows))

        overall_success = failed == 0
        if overall_success:
            summary = f"All {passed} tests passed · your network configuration looks good"
        else:
            noun = "test" if failed == 1 else "tests"
            summary = f"{failed} {noun} failed · {passed} passed · check the issues below"

        dialog.show_report(summary, overall_success, groups, secondary="RUN AGAIN", primary="CLOSE")
        dialog.primary_clicked.connect(dialog.close)
        dialog.secondary_clicked.connect(self._rerun_network_test)

        passed_count = len([r for r in results.values() if isinstance(r, dict) and r.get('status') == 'success'])
        total_count = len([r for r in results.values() if isinstance(r, dict)])
        self.logger.info(f"Network connectivity test completed: {passed_count}/{total_count} tests passed")

    def _rerun_network_test(self):
        if getattr(self, 'test_dialog', None):
            self.test_dialog.close()
            self.test_dialog = None
        self.test_websocket_connection()


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
                "volume": 70,
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
                elif hasattr(widget, "reload_controller_settings"):
                    widget.reload_controller_settings()

        except Exception as e:
            self.logger.warning(f"Failed to notify components of config changes: {e}")

    # ---------- Update System ----------

    GUI_UPDATE_STEPS = ["Download", "Extract", "Install"]
    SERVER_UPDATE_STEPS = ["Download", "Extract", "Back up & install", "Restart service"]

    def check_for_updates(self):
        """Choose a branch, then download and install a GUI update from GitHub"""
        self.update_dialog = FlowDialog(self, "UPDATE DROIDDECK GUI", "Installs on this Steam Deck")
        self.update_dialog.show_choose([
            "Downloads the latest GUI from GitHub",
            "Your config files are kept",
            "DroidDeck restarts to finish",
        ])
        self.update_dialog.start_requested.connect(self._start_gui_update)
        self.update_dialog.show()

    def _start_gui_update(self, branch: str):
        dialog = self.update_dialog
        self._update_branch = branch
        dialog.set_subtitle(f"{branch} branch")
        dialog.show_progress(self.GUI_UPDATE_STEPS)
        dialog.set_status("Preparing to update...")

        self.update_thread = UpdateThread(branch=branch)
        self.update_thread.progress_updated.connect(self._on_gui_update_progress)
        self.update_thread.update_completed.connect(self._on_gui_update_complete)
        self.update_thread.start()

    def _on_gui_update_progress(self, message: str):
        """Map the update thread's messages onto the step list"""
        dialog = getattr(self, 'update_dialog', None)
        if not dialog:
            return
        dialog.set_status(message)
        if message.startswith("Downloading:"):
            try:
                percent = int(message.split(":")[1].strip().rstrip("%"))
            except (IndexError, ValueError):
                percent = 0
            dialog.advance_to(0, f"{percent}%")
            dialog.set_progress(0.6 * percent / 100.0)
        elif message.startswith("Downloading"):
            dialog.advance_to(0)
        elif message.startswith("Extracting"):
            dialog.advance_to(1)
            dialog.set_progress(0.7)
        elif message.startswith("Installing"):
            dialog.advance_to(2)
            dialog.set_progress(0.85)

    def _on_gui_update_complete(self, success: bool, message: str):
        """Show the result; offer to restart the app after a successful update"""
        dialog = getattr(self, 'update_dialog', None)
        if not dialog:
            return
        if success:
            dialog.complete_steps()
            dialog.show_result(True, "Update installed", "DroidDeck needs to restart to use it.",
                               secondary="LATER", primary="RESTART NOW",
                               primary_fill=theme_manager.get("green"))
            dialog.secondary_clicked.connect(dialog.close)
            dialog.primary_clicked.connect(self._restart_application)
        else:
            self._mark_failed_step(dialog)
            dialog.show_result(False, "Update failed", "The update did not finish.", error=message,
                               secondary="CLOSE", primary="TRY AGAIN", keep_steps=True)
            dialog.secondary_clicked.connect(dialog.close)
            dialog.primary_clicked.connect(lambda: self._start_gui_update(self._update_branch))

    def _mark_failed_step(self, dialog):
        step = dialog.active_step()
        dialog.set_step(step if step >= 0 else 0, STEP_ERROR)

    def _restart_application(self):
        """Close the app normally, then relaunch the same command in place once shutdown finishes"""
        argv = [sys.executable] + list(getattr(sys, "orig_argv", [sys.executable] + sys.argv)[1:])

        def relaunch():
            try:
                os.execv(sys.executable, argv)
            except Exception as e:
                print(f"Restart failed, please start DroidDeck manually: {e}")

        atexit.register(relaunch)
        self.logger.info("Restarting application after update")
        window = self.window()
        if window is not None:
            window.close()
        else:
            QApplication.quit()

    def check_for_server_updates(self):
        """Choose a branch, then trigger a backend server update from GitHub"""
        self.update_dialog = FlowDialog(self, "UPDATE DROIDDECK SERVER", "Installs on the Pi")
        self.update_dialog.show_choose([
            "Downloads the latest backend from GitHub",
            "Config files are NOT overwritten",
            "The backend service restarts automatically",
        ])
        self.update_dialog.start_requested.connect(self._start_server_update)
        self.update_dialog.show()

    def _start_server_update(self, branch: str):
        dialog = self.update_dialog
        self._update_branch = branch
        dialog.set_subtitle(f"Pi backend · {branch} branch")
        dialog.show_progress(self.SERVER_UPDATE_STEPS)

        self._server_update_token = getattr(self, '_server_update_token', 0) + 1
        token = self._server_update_token
        self._server_update_pending = True
        sent = self.send_websocket_message(
            "server_update", branch=branch, repo=self.SERVER_UPDATE_REPO
        )
        if not sent:
            self._server_update_pending = False
            self._show_server_result(False, "Could not send the update command - the backend is not connected.")
            return

        dialog.set_status(f"Update command sent ({branch} branch) - waiting for backend...")
        QTimer.singleShot(self.SERVER_UPDATE_TIMEOUT_MS, lambda: self._on_server_update_timeout(token))

    def _server_update_step(self, message: str) -> int:
        text = message.lower()
        if text.startswith("downloading"):
            return 0
        if text.startswith("extracting"):
            return 1
        if text.startswith("backing up") or text.startswith("installing"):
            return 2
        if "restarting" in text:
            return 3
        return -1

    def _on_server_update_progress(self, data: dict):
        """Show backend update progress while an update started from this screen is running"""
        dialog = getattr(self, 'update_dialog', None)
        if not self._server_update_pending or not dialog:
            return
        message = data.get("message", "")
        dialog.set_status(message)
        step = self._server_update_step(message)
        if step >= 0:
            dialog.advance_to(step)
            dialog.set_progress((step + 0.5) / len(self.SERVER_UPDATE_STEPS))

    def _on_server_update_complete(self, data: dict):
        """Report the backend's actual update result"""
        if not self._server_update_pending:
            return
        self._server_update_pending = False
        self._show_server_result(bool(data.get("success")), data.get("message", ""))

    def _on_server_update_timeout(self, token: int):
        """Release the dialog if the backend never reports a result"""
        if not self._server_update_pending or token != getattr(self, '_server_update_token', 0):
            return
        self._server_update_pending = False
        self._show_server_result(
            False,
            "The backend did not report a result. Check the backend log for 'server_update'."
        )

    def _show_server_result(self, success: bool, message: str):
        dialog = getattr(self, 'update_dialog', None)
        if not dialog:
            return
        if success:
            dialog.complete_steps()
            dialog.show_result(True, "Server updated", message or "The backend service is restarting.",
                               primary="DONE", primary_fill=theme_manager.get("green"))
            dialog.primary_clicked.connect(dialog.close)
        else:
            self._mark_failed_step(dialog)
            dialog.show_result(False, "Update failed", "The server update did not finish.", error=message,
                               secondary="CLOSE", primary="TRY AGAIN", keep_steps=True)
            dialog.secondary_clicked.connect(dialog.close)
            dialog.primary_clicked.connect(lambda: self._start_server_update(self._update_branch))