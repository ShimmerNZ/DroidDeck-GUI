"""
WALL-E Control System - Network Monitoring Thread (Cross-Platform)
"""

import subprocess
import re
import statistics
import time
import requests
import platform
from PyQt6.QtCore import QThread, pyqtSignal

from core.logger import get_logger


class NetworkMonitorThread(QThread):
    """Background thread for monitoring WiFi signal strength and connectivity"""
    
    # Signals for thread-safe communication
    wifi_updated = pyqtSignal(int, str, float)  # signal_percent, status_text, ping_ms
    bandwidth_tested = pyqtSignal(float, float, str)  # download_mbps, upload_mbps, status_text

    def __init__(self, pi_ip: str = "10.1.1.230", update_interval: float = 5.0):
        super().__init__()
        self.logger = get_logger("network")
        self.pi_ip = pi_ip
        self.update_interval = update_interval
        self.platform = platform.system().lower()
        
        # Thread control
        self.running = False
        self.bandwidth_test_requested = False
        
        self.logger.info(f"Network monitor initialized for {pi_ip} on {self.platform}")

    def run(self):
        """Main monitoring loop"""
        self.running = True
        while self.running:
            try:
                # Get WiFi signal strength and ping quality
                wifi_percent = self.get_wifi_signal_strength()
                ping_quality, avg_ping = self.get_ping_quality()
                
                # Format status text
                status_text = self.format_wifi_status(wifi_percent, avg_ping)
                
                # Emit WiFi update
                self.wifi_updated.emit(wifi_percent, status_text, avg_ping or 0.0)
                
                # Handle bandwidth test if requested
                if self.bandwidth_test_requested:
                    self.bandwidth_test_requested = False
                    self.run_bandwidth_test()
                
                time.sleep(self.update_interval)
                
            except Exception as e:
                self.logger.error(f"Network monitoring error: {e}")
                time.sleep(self.update_interval)

    def get_wifi_signal_strength(self) -> int:
        """Get WiFi signal strength percentage using platform-specific methods"""
        
        if self.platform == "darwin":  # macOS
            return self._get_wifi_signal_macos()
        elif self.platform == "linux":
            return self._get_wifi_signal_linux()
        elif self.platform == "windows":
            return self._get_wifi_signal_windows()
        else:
            self.logger.warning(f"Unsupported platform: {self.platform}")
            return self._get_fallback_wifi_signal()

    def _get_wifi_signal_macos(self) -> int:
        """Get WiFi signal strength on macOS"""
        try:
            # Method 1: airport command (if available)
            result = subprocess.run(['/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport', '-I'], 
                                  capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                # Look for RSSI value
                rssi_match = re.search(r'agrCtlRSSI:\s*(-?\d+)', result.stdout)
                if rssi_match:
                    rssi = int(rssi_match.group(1))
                    # Convert RSSI to percentage: -30 dBm = 100%, -90 dBm = 0%
                    percentage = max(0, min(100, (rssi + 90) * 100 / 60))
                    self.logger.debug(f"WiFi signal (airport): {rssi} dBm = {percentage:.1f}%")
                    return int(percentage)
        except Exception as e:
            self.logger.debug(f"airport command failed: {e}")

        try:
            # Method 2: Using networksetup and system_profiler
            result = subprocess.run(['system_profiler', 'SPAirPortDataType'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                # Look for signal strength or RSSI in output
                signal_match = re.search(r'Signal / Noise:\s*(-?\d+)', result.stdout)
                if signal_match:
                    rssi = int(signal_match.group(1))
                    percentage = max(0, min(100, (rssi + 90) * 100 / 60))
                    self.logger.debug(f"WiFi signal (system_profiler): {rssi} dBm = {percentage:.1f}%")
                    return int(percentage)
        except Exception as e:
            self.logger.debug(f"system_profiler failed: {e}")

        return self._get_fallback_wifi_signal()

    def _get_wifi_signal_linux(self) -> int:
        """Get WiFi signal strength on Linux (original methods)"""
        # Method 1: Try iwconfig
        try:
            result = subprocess.run(['iwconfig'], capture_output=True, text=True, timeout=3)
            output = result.stdout
            
            # Look for signal level in dBm
            signal_match = re.search(r'Signal level=(-?\d+) dBm', output)
            if signal_match:
                dbm = int(signal_match.group(1))
                # Convert dBm to percentage: -30 dBm = 100%, -90 dBm = 0%
                percentage = max(0, min(100, (dbm + 90) * 100 / 60))
                self.logger.debug(f"WiFi signal: {dbm} dBm = {percentage}%")
                return int(percentage)
        except Exception as e:
            self.logger.debug(f"iwconfig failed: {e}")

        # Method 2: Try NetworkManager
        try:
            result = subprocess.run(['nmcli', '-f', 'IN-USE,SIGNAL,SSID', 'dev', 'wifi'], 
                                  capture_output=True, text=True, timeout=3)
            lines = result.stdout.split('\n')
            for line in lines:
                if line.startswith('*'):  # Connected network
                    parts = line.split()
                    if len(parts) >= 2:
                        signal = re.search(r'(\d+)', parts[1])
                        if signal:
                            percentage = int(signal.group(1))
                            self.logger.debug(f"WiFi signal from nmcli: {percentage}%")
                            return percentage
        except Exception as e:
            self.logger.debug(f"nmcli failed: {e}")

        # Method 3: Try /proc/net/wireless
        try:
            with open('/proc/net/wireless', 'r') as f:
                lines = f.readlines()
                for line in lines[2:]:  # Skip headers
                    if ':' in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            signal = float(parts[2])
                            if signal < 0:  # dBm format
                                percentage = max(0, min(100, (signal + 90) * 100 / 60))
                            else:  # Already percentage
                                percentage = min(100, signal)
                            self.logger.debug(f"WiFi signal from /proc: {percentage}%")
                            return int(percentage)
        except Exception as e:
            self.logger.debug(f"/proc/net/wireless failed: {e}")

        return self._get_fallback_wifi_signal()

    def _get_wifi_signal_windows(self) -> int:
        """Get WiFi signal strength on Windows"""
        try:
            # Use netsh command
            result = subprocess.run(['netsh', 'wlan', 'show', 'profiles'], 
                                  capture_output=True, text=True, timeout=3)
            # This is a placeholder - would need more implementation for Windows
            self.logger.debug("Windows WiFi detection not fully implemented")
        except Exception as e:
            self.logger.debug(f"Windows WiFi detection failed: {e}")
        
        return self._get_fallback_wifi_signal()

    def _get_fallback_wifi_signal(self) -> int:
        """Fallback WiFi signal when platform-specific methods fail"""
        import random
        random_signal = random.randint(60, 90)  # Assume decent signal for demo
        self.logger.warning(f"All WiFi detection methods failed - using fallback value: {random_signal}%")
        return random_signal

    def get_ping_quality(self, samples: int = 3) -> tuple:
        """Get connection quality based on ping to Raspberry Pi (cross-platform)"""
        try:
            # Build ping command based on platform
            if self.platform == "windows":
                cmd = ['ping', '-n', str(samples), '-w', '1000', self.pi_ip]
            else:  # macOS and Linux
                cmd = ['ping', '-c', str(samples), '-W', '1', self.pi_ip]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                return self._parse_ping_output(result.stdout)
            else:
                self.logger.debug(f"Ping failed with return code {result.returncode}")
                return 0, None
            
        except Exception as e:
            self.logger.debug(f"Ping test failed: {e}")
            return 0, None

    def _parse_ping_output(self, output: str) -> tuple:
        """Parse ping output for different platforms"""
        times = []
        
        if self.platform == "darwin":  # macOS
            # Look for round-trip statistics line
            stats_match = re.search(r'round-trip min/avg/max/stddev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms', output)
            if stats_match:
                avg_ping = float(stats_match.group(2))
                self.logger.debug(f"macOS ping average: {avg_ping}ms")
                times = [avg_ping]  # Use average as single sample
            else:
                # Fallback: look for individual time= lines (some macOS versions)
                for line in output.split('\n'):
                    if 'time=' in line:
                        time_match = re.search(r'time=(\d+(?:\.\d+)?)', line)
                        if time_match:
                            times.append(float(time_match.group(1)))
        
        elif self.platform == "linux":  # Linux (including Steam Deck)
            # Look for individual time= lines
            for line in output.split('\n'):
                if 'time=' in line:
                    time_match = re.search(r'time=(\d+(?:\.\d+)?)', line)
                    if time_match:
                        times.append(float(time_match.group(1)))
        
        elif self.platform == "windows":  # Windows
            # Look for time< or time= patterns
            for line in output.split('\n'):
                time_match = re.search(r'time[<=](\d+)ms', line)
                if time_match:
                    times.append(float(time_match.group(1)))
        
        if times:
            avg_ping = statistics.mean(times)
            
            # Convert ping to quality score
            if avg_ping <= 20:
                quality = 100
            elif avg_ping <= 50:
                quality = 80
            elif avg_ping <= 100:
                quality = 60
            else:
                quality = 20
            
            self.logger.debug(f"Ping successful: {len(times)} samples, avg={avg_ping:.1f}ms")
            return quality, avg_ping
        
        self.logger.debug("No ping times found in output")
        return 0, None

    def format_wifi_status(self, wifi_percent: int, ping_ms: float = None) -> str:
        """Format WiFi status text with signal bars"""
        # Create signal bars based on WiFi strength
        bars = self.get_signal_bars(wifi_percent)
        
        if ping_ms is not None:
            return f"{bars} {wifi_percent}% - {ping_ms:.1f}ms"
        else:
            return f"{bars} {wifi_percent}% - timeout"

    def get_signal_bars(self, percentage: int) -> str:
        """Generate signal bar representation using ASCII characters"""
        if percentage >= 75:
            return "████"  # 4 bars
        elif percentage >= 50:
            return "███░"  # 3 bars
        elif percentage >= 25:
            return "██░░"  # 2 bars
        elif percentage > 0:
            return "█░░░"  # 1 bar
        else:
            return "░░░░"  # 0 bars

    def request_bandwidth_test(self):
        """Request bandwidth test on next monitoring cycle"""
        self.bandwidth_test_requested = True
        self.logger.info("Bandwidth test requested")

    def run_bandwidth_test(self):
        """Run bandwidth test to Raspberry Pi"""
        try:
            self.logger.info("Starting bandwidth test...")
            
            # Download test: request test file from Pi
            test_size_mb = 5  # 5MB test file
            start_time = time.time()
            
            response = requests.get(
                f"http://{self.pi_ip}:8081/bandwidth_test", 
                params={"size": test_size_mb * 1024 * 1024},
                timeout=30, 
                stream=True
            )
            
            if response.status_code == 200:
                total_bytes = 0
                for chunk in response.iter_content(chunk_size=8192):
                    total_bytes += len(chunk)
                
                download_time = time.time() - start_time
                download_mbps = (total_bytes * 8) / (download_time * 1000000)  # Convert to Mbps
                
                # Simple upload test (if Pi supports it)
                upload_mbps = 0  # Placeholder for now
                
                status_text = f"Download: {download_mbps:.1f} Mbps"
                if upload_mbps > 0:
                    status_text += f", Upload: {upload_mbps:.1f} Mbps"
                
                self.bandwidth_tested.emit(download_mbps, upload_mbps, status_text)
                self.logger.info(f"Bandwidth test complete: {download_mbps:.1f} Mbps download")
                
            else:
                self.bandwidth_tested.emit(0, 0, f"Test failed: HTTP {response.status_code}")
                self.logger.error(f"Bandwidth test failed: HTTP {response.status_code}")
                
        except requests.exceptions.Timeout:
            self.bandwidth_tested.emit(0, 0, "Test failed: timeout")
            self.logger.error("Bandwidth test timeout")
        except Exception as e:
            self.bandwidth_tested.emit(0, 0, f"Test failed: {str(e)[:50]}")
            self.logger.error(f"Bandwidth test error: {e}")

    def stop(self):
        """Stop the network monitoring thread"""
        self.logger.info("Stopping network monitoring thread")
        self.running = False
        self.quit()
        self.wait(3000)


# Test section for standalone running
if __name__ == "__main__":
    import sys
    import os
    
    # Add parent directory to path for imports
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    
    print(f"Testing NetworkMonitorThread on {platform.system()}")
    
    # Create a simple logger for testing
    class SimpleLogger:
        def info(self, msg): print(f"INFO: {msg}")
        def debug(self, msg): print(f"DEBUG: {msg}")
        def warning(self, msg): print(f"WARNING: {msg}")
        def error(self, msg): print(f"ERROR: {msg}")
    
    # Override logger for standalone testing
    import core.logger
    core.logger.get_logger = lambda name: SimpleLogger()
    
    monitor = NetworkMonitorThread(pi_ip='10.1.1.230')
    
    print("\n=== Testing Ping ===")
    quality, ping_ms = monitor.get_ping_quality()
    print(f"Ping Result: Quality={quality}, Time={ping_ms}ms")
    
    print("\n=== Testing WiFi Signal ===")
    wifi_percent = monitor.get_wifi_signal_strength()
    print(f"WiFi Signal: {wifi_percent}%")
    
    print("\n=== Testing Status Format ===")
    status = monitor.format_wifi_status(wifi_percent, ping_ms)
    print(f"Status: {status}")