"""
WALL-E Control System - Network Monitoring Thread (Cleaned)
"""

import platform
import re
import subprocess
import time
from typing import Optional, Tuple
from dataclasses import dataclass

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from core.logger import get_logger


@dataclass
class NetworkConfig:
    """Network monitoring configuration"""
    UPDATE_INTERVAL: float = 5.0
    PING_SAMPLES: int = 3
    PING_TIMEOUT: int = 10
    HTTP_TIMEOUT: int = 30
    BANDWIDTH_TEST_SIZE_MB: int = 5
    CHUNK_SIZE: int = 8192
    
    # Signal strength thresholds
    SIGNAL_EXCELLENT: int = 80
    SIGNAL_GOOD: int = 60
    SIGNAL_FAIR: int = 40
    SIGNAL_POOR: int = 20
    
    # Ping quality thresholds (ms)
    PING_EXCELLENT: int = 20
    PING_GOOD: int = 50
    PING_FAIR: int = 100
    PING_POOR: int = 200


class NetworkQuality:
    """Network quality assessment utilities"""
    
    @staticmethod
    def get_signal_bars(signal_percent: int) -> str:
        """Convert signal percentage to visual bars"""
        if signal_percent >= NetworkConfig.SIGNAL_EXCELLENT:
            return "▂▄▆█"  # 4 bars
        elif signal_percent >= NetworkConfig.SIGNAL_GOOD:
            return "▂▄▆▁"  # 3 bars
        elif signal_percent >= NetworkConfig.SIGNAL_FAIR:
            return "▂▄▁▁"  # 2 bars
        elif signal_percent >= NetworkConfig.SIGNAL_POOR:
            return "▂▁▁▁"  # 1 bar
        else:
            return "▁▁▁▁"  # 0 bars
    
    @staticmethod
    def get_ping_quality_score(ping_ms: Optional[float]) -> int:
        """Convert ping time to quality score (0-100)"""
        if ping_ms is None:
            return 0
        
        if ping_ms <= NetworkConfig.PING_EXCELLENT:
            return 100
        elif ping_ms <= NetworkConfig.PING_GOOD:
            return 80
        elif ping_ms <= NetworkConfig.PING_FAIR:
            return 60
        elif ping_ms <= NetworkConfig.PING_POOR:
            return 40
        else:
            return 20


class PlatformNetworkDetector:
    """Platform-specific network detection utilities"""
    
    def __init__(self):
        self.platform = platform.system().lower()
        self.logger = get_logger("network")
    
    def get_wifi_signal_strength(self) -> Optional[int]:
        """Get WiFi signal strength percentage for current platform"""
        try:
            if self.platform == "linux":
                return self._get_linux_wifi_signal()
            elif self.platform == "darwin":
                return self._get_macos_wifi_signal()
            elif self.platform == "windows":
                return self._get_windows_wifi_signal()
            else:
                self.logger.warning(f"Unsupported platform: {self.platform}")
                return None
        except Exception as e:
            self.logger.debug(f"WiFi detection failed: {e}")
            return None
    
    def _get_linux_wifi_signal(self) -> Optional[int]:
        """Get WiFi signal on Linux using multiple methods"""
        # Method 1: Try iwconfig
        try:
            result = subprocess.run(['iwconfig'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                # Look for signal quality
                quality_match = re.search(r'Link Quality=(\d+)/(\d+)', result.stdout)
                if quality_match:
                    current, maximum = map(int, quality_match.groups())
                    return int((current / maximum) * 100)
                
                # Look for signal level in dBm
                signal_match = re.search(r'Signal level=(-?\d+) dBm', result.stdout)
                if signal_match:
                    dbm = int(signal_match.group(1))
                    # Convert dBm to percentage (rough approximation)
                    return max(0, min(100, (dbm + 100) * 2))
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        # Method 2: Try nmcli
        try:
            result = subprocess.run(['nmcli', '-t', '-f', 'SIGNAL', 'dev', 'wifi'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                signals = [int(line) for line in result.stdout.strip().split('\n') if line.isdigit()]
                if signals:
                    return max(signals)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        # Method 3: Try /proc/net/wireless
        try:
            with open('/proc/net/wireless', 'r') as f:
                lines = f.readlines()
                if len(lines) > 2:  # Skip header lines
                    for line in lines[2:]:
                        parts = line.split()
                        if len(parts) >= 3:
                            quality = float(parts[2])
                            return int(quality)
        except (FileNotFoundError, ValueError, IndexError):
            pass
        
        return None
    
    def _get_macos_wifi_signal(self) -> Optional[int]:
        """Get WiFi signal on macOS"""
        try:
            result = subprocess.run(['/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport', '-I'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                # Look for RSSI value
                rssi_match = re.search(r'agrCtlRSSI: (-?\d+)', result.stdout)
                if rssi_match:
                    rssi = int(rssi_match.group(1))
                    # Convert RSSI to percentage
                    return max(0, min(100, (rssi + 100) * 2))
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        return None
    
    def _get_windows_wifi_signal(self) -> Optional[int]:
        """Get WiFi signal on Windows"""
        try:
            result = subprocess.run(['netsh', 'wlan', 'show', 'profiles'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                # This is a basic implementation - Windows WiFi detection is complex
                # and would require WMI or other Windows-specific APIs for accuracy
                self.logger.debug("Windows WiFi detection - basic implementation")
                return 75  # Return a reasonable default for now
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        return None


class NetworkMonitorThread(QThread):
    """Background network monitoring with proper resource management"""
    
    # Signals for thread-safe communication
    status_updated = pyqtSignal(str, int, float)  # status_text, signal_percent, ping_ms
    bandwidth_tested = pyqtSignal(float, float, str)  # download_mbps, upload_mbps, status_text

    wifi_updated = pyqtSignal(int, str, float)  # signal_percent, status_text, ping_ms
    ping_updated = pyqtSignal(float)  # ping_ms
    
    def __init__(self, pi_ip: str, config: Optional[NetworkConfig] = None, 
                 update_interval: Optional[float] = None, **kwargs):
        super().__init__()
        self.pi_ip = pi_ip
        
        # Handle backward compatibility
        if config is None:
            config = NetworkConfig()
            
        # Override config with any passed parameters for backward compatibility
        if update_interval is not None:
            config.UPDATE_INTERVAL = update_interval
        
        self.config = config
        self.logger = get_logger("network")
        
        # Thread control
        self.running = False
        self.bandwidth_test_requested = False
        
        # Platform detector
        self.detector = PlatformNetworkDetector()
        
        self.logger.info(f"Network monitor initialized for Pi: {pi_ip}")
    
    def run(self):
        """Main monitoring loop with proper error handling"""
        self.running = True
        self.logger.info("Network monitoring started")
        
        try:
            while self.running:
                if self.bandwidth_test_requested:
                    self._run_bandwidth_test()
                    self.bandwidth_test_requested = False
                else:
                    self._update_network_status()
                
                # Wait for next update or exit signal
                self.msleep(int(self.config.UPDATE_INTERVAL * 1000))
                
        except Exception as e:
            self.logger.error(f"Network monitoring error: {e}")
        finally:
            self.logger.info("Network monitoring stopped")
    
    def _update_network_status(self):
        """Update network status and emit signals"""
        try:
            # Get WiFi signal strength
            wifi_percent = self.detector.get_wifi_signal_strength()
            if wifi_percent is None:
                wifi_percent = 0
                self.logger.debug("WiFi signal detection failed - using 0%")
            
            # Get ping quality
            ping_quality, ping_ms = self._get_ping_quality()
            
            # Format status text
            status_text = self._format_status(wifi_percent, ping_ms)
            
            # Emit update signals
            self.status_updated.emit(status_text, wifi_percent, ping_ms or 0.0)
            
            # Emit backward compatibility signals
            self.wifi_updated.emit(wifi_percent, status_text, ping_ms or 0.0)
            if ping_ms is not None:
                self.ping_updated.emit(ping_ms)
            
        except Exception as e:
            self.logger.error(f"Status update failed: {e}")
            self.status_updated.emit("Network Error", 0, 0.0)
            self.wifi_updated.emit(0, "Network Error", 0.0)
    
    def _get_ping_quality(self) -> Tuple[int, Optional[float]]:
        """Get connection quality based on ping to Raspberry Pi"""
        try:
            # Build platform-specific ping command
            if self.detector.platform == "windows":
                cmd = ['ping', '-n', str(self.config.PING_SAMPLES), '-w', '1000', self.pi_ip]
            else:  # macOS and Linux
                cmd = ['ping', '-c', str(self.config.PING_SAMPLES), '-W', '1', self.pi_ip]
            
            result = subprocess.run(cmd, capture_output=True, text=True, 
                                  timeout=self.config.PING_TIMEOUT)
            
            if result.returncode == 0:
                return self._parse_ping_output(result.stdout)
            else:
                self.logger.debug(f"Ping failed with return code {result.returncode}")
                return 0, None
                
        except subprocess.TimeoutExpired:
            self.logger.debug("Ping timeout")
            return 0, None
        except Exception as e:
            self.logger.debug(f"Ping test failed: {e}")
            return 0, None
    
    def _parse_ping_output(self, output: str) -> Tuple[int, Optional[float]]:
        """Parse ping output for different platforms"""
        times = []
        
        try:
            if self.detector.platform == "darwin":  # macOS
                # Look for round-trip statistics
                stats_match = re.search(r'round-trip min/avg/max/stddev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms', output)
                if stats_match:
                    avg_ping = float(stats_match.group(2))
                    times = [avg_ping]
                else:
                    # Fallback: individual time= lines
                    for line in output.split('\n'):
                        if 'time=' in line:
                            time_match = re.search(r'time=(\d+(?:\.\d+)?)', line)
                            if time_match:
                                times.append(float(time_match.group(1)))
            
            elif self.detector.platform == "linux":  # Linux
                for line in output.split('\n'):
                    if 'time=' in line:
                        time_match = re.search(r'time=(\d+(?:\.\d+)?)', line)
                        if time_match:
                            times.append(float(time_match.group(1)))
            
            elif self.detector.platform == "windows":  # Windows
                for line in output.split('\n'):
                    if 'time=' in line or 'time<' in line:
                        time_match = re.search(r'time[<=](\d+)ms', line)
                        if time_match:
                            times.append(float(time_match.group(1)))
            
            if times:
                avg_time = sum(times) / len(times)
                quality = NetworkQuality.get_ping_quality_score(avg_time)
                return quality, avg_time
            
        except (ValueError, AttributeError) as e:
            self.logger.debug(f"Ping parsing error: {e}")
        
        return 0, None
    
    def _format_status(self, wifi_percent: int, ping_ms: Optional[float]) -> str:
        """Format network status text"""
        signal_bars = NetworkQuality.get_signal_bars(wifi_percent)
        
        if ping_ms is not None:
            return f"WiFi: {signal_bars} {wifi_percent}% ({ping_ms:.0f}ms)"
        else:
            return f"WiFi: {signal_bars} {wifi_percent}% (timeout)"
    
    def request_bandwidth_test(self):
        """Request bandwidth test on next monitoring cycle"""
        self.bandwidth_test_requested = True
        self.logger.info("Bandwidth test requested")
    
    def _run_bandwidth_test(self):
        """Run bandwidth test to Raspberry Pi"""
        try:
            self.logger.info("Starting bandwidth test...")
            
            start_time = time.time()
            test_size = self.config.BANDWIDTH_TEST_SIZE_MB * 1024 * 1024
            
            response = requests.get(
                f"http://{self.pi_ip}:8081/bandwidth_test", 
                params={"size": test_size},
                timeout=self.config.HTTP_TIMEOUT, 
                stream=True
            )
            
            if response.status_code == 200:
                total_bytes = 0
                for chunk in response.iter_content(chunk_size=self.config.CHUNK_SIZE):
                    if not self.running:  # Check for stop signal
                        break
                    total_bytes += len(chunk)
                
                download_time = time.time() - start_time
                if download_time > 0:
                    download_mbps = (total_bytes * 8) / (download_time * 1000000)  # Convert to Mbps
                    status_text = f"Download: {download_mbps:.1f} Mbps"
                    
                    self.bandwidth_tested.emit(download_mbps, 0.0, status_text)
                    self.logger.info(f"Bandwidth test complete: {download_mbps:.1f} Mbps")
                else:
                    self.bandwidth_tested.emit(0.0, 0.0, "Test failed: invalid timing")
            else:
                self.bandwidth_tested.emit(0.0, 0.0, f"Test failed: HTTP {response.status_code}")
                self.logger.error(f"Bandwidth test failed: HTTP {response.status_code}")
                
        except requests.exceptions.Timeout:
            self.bandwidth_tested.emit(0.0, 0.0, "Test failed: timeout")
            self.logger.error("Bandwidth test timeout")
        except Exception as e:
            error_msg = f"Test failed: {str(e)[:30]}"
            self.bandwidth_tested.emit(0.0, 0.0, error_msg)
            self.logger.error(f"Bandwidth test error: {e}")
    
    def stop(self):
        """Stop the network monitoring thread with proper cleanup"""
        self.logger.info("Stopping network monitoring thread")
        self.running = False
        
        # Wait for thread to finish with timeout
        if not self.wait(3000):  # 3 second timeout
            self.logger.warning("Network monitor thread did not stop gracefully")
            self.terminate()
            self.wait(1000)  # Give it 1 more second after terminate
        
        self.logger.info("Network monitoring thread stopped")