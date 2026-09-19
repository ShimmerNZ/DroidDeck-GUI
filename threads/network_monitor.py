"""
WALL-E Control System - Network Monitoring Thread (Fixed with Upload Testing)
"""

import platform
import re
import subprocess
import time
from typing import Optional, Tuple

from PyQt6.QtCore import QThread, pyqtSignal

from core.logger import get_logger


class NetworkMonitorThread(QThread):
    """Background thread for monitoring WiFi signal strength and Pi connectivity"""

    # WiFi signal — emitted every 2 seconds
    wifi_updated = pyqtSignal(int, str, float)  # signal_percent, status_text, unused(0.0)

    # Pi backend connectivity — emitted every 5 seconds independently
    connectivity_updated = pyqtSignal(float, bool)  # ping_ms, is_connected

    bandwidth_tested = pyqtSignal(float, float, str)  # download_mbps, upload_mbps, status_text

    def __init__(self, pi_ip: str = "10.42.0.1", update_interval: float = 5.0):
        super().__init__()
        self.logger = get_logger("network")
        self.pi_ip = pi_ip
        self.platform = platform.system().lower()
        self.wifi_interval = 2.0
        self.connectivity_interval = 5.0

        self.running = False
        self.bandwidth_test_requested = False

        self.logger.info(f"Network monitor initialized for {pi_ip} on {self.platform}")

    def run(self):
        """Main monitoring loop — WiFi every 2s, Pi connectivity every 5s"""
        self.running = True
        last_connectivity_check = 0.0

        while self.running:
            try:
                # WiFi signal — always on every cycle
                wifi_percent = self.get_wifi_signal_strength()
                status_text = self.format_wifi_status(wifi_percent)
                self.wifi_updated.emit(wifi_percent, status_text, 0.0)

                # Pi connectivity — independent 5s cadence
                now = time.monotonic()
                if now - last_connectivity_check >= self.connectivity_interval:
                    last_connectivity_check = now
                    ping_ms, is_connected = self._check_pi_connectivity()
                    self.connectivity_updated.emit(ping_ms, is_connected)

                # Handle bandwidth test if requested
                if self.bandwidth_test_requested:
                    self.bandwidth_test_requested = False
                    self.run_bandwidth_test()

                self.msleep(int(self.wifi_interval * 1000))

            except Exception as e:
                self.logger.error(f"Network monitoring error: {e}")
                self.msleep(1000)

    def _check_pi_connectivity(self):
        """Check Pi backend reachability via a socket connection to the WebSocket port"""
        try:
            import socket
            start = time.monotonic()
            s = socket.create_connection((self.pi_ip, 8766), timeout=1)
            ping_ms = (time.monotonic() - start) * 1000
            s.close()
            self.logger.debug(f"Pi connectivity: {ping_ms:.1f}ms")
            return ping_ms, True
        except Exception:
            self.logger.debug("Pi connectivity: unreachable")
            return 0.0, False

    def get_wifi_signal_strength(self) -> int:
        """Get WiFi signal strength percentage for current platform"""
        try:
            if self.platform == "linux":
                return self._get_wifi_signal_linux()
            elif self.platform == "darwin":
                return self._get_wifi_signal_macos()
            elif self.platform == "windows":
                return self._get_wifi_signal_windows()
            else:
                self.logger.debug(f"Unsupported platform: {self.platform}")
                return self._get_fallback_wifi_signal()
        except Exception as e:
            self.logger.debug(f"WiFi detection failed: {e}")
            return self._get_fallback_wifi_signal()

    def _get_wifi_signal_linux(self) -> int:
        """Get WiFi signal strength on Linux using nl80211 (iw), nmcli, or iwconfig"""

        # Method 1: iw — modern nl80211, works on all current Linux WiFi drivers including Steam Deck
        # Requires: sudo apt install iw (included in DD_Install.sh)
        try:
            dev_result = subprocess.run(['iw', 'dev'], capture_output=True, text=True, timeout=3)
            if dev_result.returncode == 0:
                iface_match = re.search(r'Interface\s+(\S+)', dev_result.stdout)
                if iface_match:
                    iface = iface_match.group(1)
                    link_result = subprocess.run(
                        ['iw', iface, 'link'], capture_output=True, text=True, timeout=3
                    )
                    signal_match = re.search(r'signal:\s*(-?\d+)', link_result.stdout)
                    if signal_match:
                        dbm = int(signal_match.group(1))
                        percentage = max(0, min(100, int((dbm + 85) * 100 / 35)))
                        self.logger.debug(f"WiFi signal from iw: {dbm} dBm = {percentage}%")
                        return percentage
        except Exception as e:
            self.logger.debug(f"iw failed: {e}")

        # Method 2: nmcli — use IN-USE,SIGNAL so connected network is identifiable in terse mode
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'IN-USE,SIGNAL', 'dev', 'wifi'],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith('*:'):
                        signal_val = line.split(':', 1)[1].strip()
                        if signal_val.isdigit():
                            percentage = int(signal_val)
                            self.logger.debug(f"WiFi signal from nmcli: {percentage}%")
                            return percentage
        except Exception as e:
            self.logger.debug(f"nmcli failed: {e}")

        # Method 3: /proc/net/wireless — read column 3 (signal level in dBm, always negative)
        # Column 2 is link quality on a 0-70 scale — NOT a percentage, do not use it directly
        try:
            with open('/proc/net/wireless', 'r') as f:
                for line in f.readlines()[2:]:
                    if ':' not in line:
                        continue
                    parts = line.split()
                    if len(parts) >= 4:
                        try:
                            dbm = float(parts[3].rstrip('.'))
                            if dbm < 0:
                                percentage = max(0, min(100, int((dbm + 85) * 100 / 35)))
                                self.logger.debug(
                                    f"WiFi signal from /proc/net/wireless: {dbm} dBm = {percentage}%"
                                )
                                return int(percentage)
                        except ValueError:
                            pass
        except Exception as e:
            self.logger.debug(f"/proc/net/wireless failed: {e}")

        # Method 4: iwconfig — legacy WEXT, last resort
        try:
            result = subprocess.run(['iwconfig'], capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                quality_match = re.search(r'Link Quality=(\d+)/(\d+)', result.stdout)
                if quality_match:
                    current, maximum = map(int, quality_match.groups())
                    percentage = int((current / maximum) * 100)
                    self.logger.debug(f"WiFi signal from iwconfig quality: {percentage}%")
                    return percentage

                signal_match = re.search(r'Signal level=(-?\d+) dBm', result.stdout)
                if signal_match:
                    dbm = int(signal_match.group(1))
                    percentage = max(0, min(100, int((dbm + 85) * 100 / 35)))
                    self.logger.debug(f"WiFi signal from iwconfig dBm: {dbm} dBm = {percentage}%")
                    return percentage
        except Exception as e:
            self.logger.debug(f"iwconfig failed: {e}")

        return self._get_fallback_wifi_signal()

    def _get_wifi_signal_macos(self) -> int:
        """Get WiFi signal strength on macOS"""
        try:
            result = subprocess.run(['/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport', '-I'], 
                                  capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                # Look for agrCtlRSSI
                rssi_match = re.search(r'agrCtlRSSI: (-?\d+)', result.stdout)
                if rssi_match:
                    rssi = int(rssi_match.group(1))
                    percentage = max(0, min(100, int((rssi + 85) * 100 / 35)))
                    self.logger.debug(f"WiFi signal from airport: {percentage}%")
                    return percentage
        except Exception as e:
            self.logger.debug(f"macOS airport command failed: {e}")

        return self._get_fallback_wifi_signal()

    def _get_wifi_signal_windows(self) -> int:
        """Get WiFi signal strength on Windows"""
        try:
            result = subprocess.run(
                ['netsh', 'wlan', 'show', 'interfaces'],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                signal_match = re.search(r'Signal\s*:\s*(\d+)%', result.stdout)
                if signal_match:
                    percentage = int(signal_match.group(1))
                    self.logger.debug(f"WiFi signal from netsh: {percentage}%")
                    return percentage
        except Exception as e:
            self.logger.debug(f"netsh failed: {e}")

        return self._get_fallback_wifi_signal()

    def _get_fallback_wifi_signal(self) -> int:
        """Fallback WiFi signal when all platform detection methods fail"""
        return 0

    def format_wifi_status(self, wifi_percent: int) -> str:
        """Format WiFi status text with signal bars"""
        bars = self.get_signal_bars(wifi_percent)
        return f"{bars} {wifi_percent}%"

    def get_signal_bars(self, percentage: int) -> str:
        """Generate signal bar representation using ASCII characters"""
        if percentage >= 75:
            return "â–ˆâ–ˆâ–ˆâ–ˆ"  # 4 bars
        elif percentage >= 50:
            return "â–ˆâ–ˆâ–ˆâ–’"  # 3 bars
        elif percentage >= 25:
            return "â–ˆâ–ˆâ–’â–’"  # 2 bars
        elif percentage > 0:
            return "â–ˆâ–’â–’â–’"  # 1 bar
        else:
            return "â–’â–’â–’â–’"  # 0 bars

    def request_bandwidth_test(self):
        """Request bandwidth test on next monitoring cycle"""
        self.bandwidth_test_requested = True
        self.logger.info("Bandwidth test requested")

    def run_bandwidth_test(self):
        """Run bandwidth test to Raspberry Pi with both download and upload"""
        try:
            self.logger.info("Starting bandwidth test...")
            
            # Download test
            test_size_mb = 5
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
                download_mbps = (total_bytes * 8) / (download_time * 1000000)
                
                # Upload test
                upload_mbps = 0
                try:
                    upload_data = b'0' * (test_size_mb * 1024 * 1024)  # 5MB of data
                    upload_start = time.time()
                    
                    upload_response = requests.post(
                        f"http://{self.pi_ip}:8081/bandwidth_upload",
                        data=upload_data,
                        headers={'Content-Type': 'application/octet-stream'},
                        timeout=30
                    )
                    
                    if upload_response.status_code == 200:
                        upload_result = upload_response.json()
                        upload_mbps = upload_result.get("upload_mbps", 0)
                        self.logger.info(f"Upload test successful: {upload_mbps:.1f} Mbps")
                    else:
                        self.logger.warning(f"Upload test failed: HTTP {upload_response.status_code}")
                        
                except Exception as e:
                    self.logger.warning(f"Upload test error: {e}")
                    upload_mbps = 0
                
                # Report results
                status_text = f"Download: {download_mbps:.1f} Mbps"
                if upload_mbps > 0:
                    status_text += f", Upload: {upload_mbps:.1f} Mbps"
                else:
                    status_text += ", Upload: Not available"
                
                self.bandwidth_tested.emit(download_mbps, upload_mbps, status_text)
                self.logger.info(f"Bandwidth test complete: {status_text}")
                
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