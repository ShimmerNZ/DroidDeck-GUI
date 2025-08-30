"""
WALL-E Control System - Network Monitoring Thread
"""

import subprocess
import re
import statistics
import time
import requests
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
        
        # Thread control
        self.running = False
        self.bandwidth_test_requested = False
        
        self.logger.info(f"Network monitor initialized for {pi_ip}")

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
        """Get WiFi signal strength percentage using multiple methods"""
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

        # Fallback: Generate random signal strength for demo purposes
        import random
        random_signal = random.randint(0, 100)
        self.logger.warning(f"All WiFi detection methods failed - using random value: {random_signal}%")
        return random_signal

    def get_ping_quality(self, samples: int = 3) -> tuple:
        """Get connection quality based on ping to Raspberry Pi"""
        try:
            cmd = ['ping', '-c', str(samples), '-W', '1', self.pi_ip]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                # Parse ping times
                times = []
                for line in result.stdout.split('\n'):
                    if 'time=' in line:
                        time_match = re.search(r'time=(\d+\.?\d*)', line)
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
                    
                    return quality, avg_ping
            
            return 0, None
            
        except Exception as e:
            self.logger.debug(f"Ping test failed: {e}")
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
        """Generate signal bar representation"""
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