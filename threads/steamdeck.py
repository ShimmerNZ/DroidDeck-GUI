#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SteamDeckControllerThread — HID-based input handler for DroidDeck

Reads analog, IMU and button data directly from the Steam Deck's
raw HID interface (/dev/hidraw3), bypassing the Steam Input layer.

Analog and IMU are parsed from raw HID reports using verified byte offsets.
Button state is read from bitsteam which handles the bitmask parsing.
Both readers open the device independently — Linux hidraw allows concurrent
readers, each receiving their own copy of every report.

Byte offsets verified by hardware orientation sweep testing:
  Triggers:    44 (L), 46 (R)  — uint16, 0-32767
  Left stick:  48 (X), 50 (Y)  — int16,  ±32767
  Right stick: 52 (X), 54 (Y)  — int16,  ±32767
  Accel roll:  24               — int16,  ±17000 (left=+, right=-)
  Accel pitch: 26               — int16,  ±17000 (back=+, forward=-)
"""

import json
import struct
import time
from typing import Dict, Any, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from core.logger import get_logger
from core.config_manager import config_manager
from core.utils import error_boundary


# HID device path for the Steam Deck built-in controller
HIDRAW_PATH     = b'/dev/hidraw3'
HIDRAW_PATH_STR = '/dev/hidraw3'

# Firmware command to enable IMU output in the HID report
# Sourced from the hid-steam Linux kernel driver protocol
IMU_ENABLE_CMD = bytes([
    0x00, 0x87, 0x15, 0x32, 0x84,
    0x03, 0x18, 0x00, 0x00, 0x31,
    0x02, 0x00, 0x08, 0x07, 0x00,
    0x00, 0x31, 0x02, 0x00, 0x00,
    0x00,
]) + bytes(43)

# Raw HID report byte offsets (verified by hardware testing)
OFF_LEFT_TRIGGER  = 44   # uint16  0–32767
OFF_RIGHT_TRIGGER = 46   # uint16  0–32767
OFF_LEFT_STICK_X  = 48   # int16   ±32767
OFF_LEFT_STICK_Y  = 50   # int16   ±32767
OFF_RIGHT_STICK_X = 52   # int16   ±32767
OFF_RIGHT_STICK_Y = 54   # int16   ±32767
OFF_ACCEL_X       = 24   # int16   ±17000  roll  (left=+, right=−)
OFF_ACCEL_Y       = 26   # int16   ±17000  pitch (back=+, forward=−)

STICK_MAX   = 32767
TRIGGER_MAX = 32767
IMU_MAX     = 17000

STICK_DEADZONE   = 0.05
TRIGGER_DEADZONE = 0.02
IMU_DEADZONE     = 0.04

# bitsteam field name → DroidDeck control name
BUTTON_MAP = {
    'a':                'button_a',
    'b':                'button_b',
    'x':                'button_x',
    'y':                'button_y',
    'l1':               'shoulder_left',
    'r1':               'shoulder_right',
    'l2_click':         'left_trigger_btn',
    'r2_click':         'right_trigger_btn',
    'dpad_up':          'dpad_up',
    'dpad_down':        'dpad_down',
    'dpad_left':        'dpad_left',
    'dpad_right':       'dpad_right',
    'select':           'button_back',
    'start':            'button_menu',
    'steam':            'button_guide',
    'quick_access':     'button_quick_access',
    'l_stick_press':    'stick_left_click',
    'r_stick_press':    'stick_right_click',
    'l_lower_grip':     'grip_left_lower',
    'r_lower_grip':     'grip_right_lower',
    'l_upper_grip':     'grip_left_upper',
    'r_upper_grip':     'grip_right_upper',
    'l_trackpad_press': 'button_left_pad',
    'r_trackpad_press': 'button_right_pad',
}


class ControllerInputData:
    """Container for one frame of controller input"""
    def __init__(self, axes: Dict[str, float], buttons: Dict[str, bool],
                 timestamp: float, sequence: int):
        self.axes      = axes
        self.buttons   = buttons
        self.timestamp = timestamp
        self.sequence  = sequence
        self.source    = "steamdeck"


class SteamDeckControllerThread(QThread):
    """50 Hz controller input thread — HID-based, no Steam Input dependency"""

    controller_input        = pyqtSignal(ControllerInputData)
    controller_connected    = pyqtSignal(str, str)
    controller_disconnected = pyqtSignal(str)
    heartbeat_signal        = pyqtSignal(float)
    stats_updated           = pyqtSignal(dict)
    send_websocket_message  = pyqtSignal(dict)

    def __init__(self, websocket_manager=None):
        super().__init__()
        self.logger            = get_logger("controller")
        self.websocket_manager = websocket_manager

        self.running           = False
        self.controller_active = False

        self.poll_rate_hz  = 50
        self.poll_interval = 1.0 / self.poll_rate_hz
        self.sequence_number = 0
        self.last_input_sent = 0

        # IMU state
        self.imu_enabled       = False
        self.imu_zero_ax       = 0
        self.imu_zero_ay       = 0
        self._prev_buttons     = {}
        self.imu_toggle_buttons: set = set()

        # HID handles
        self._hid_device    = None
        self._bitsteam_deck = None

        self.stats = {
            "inputs_processed": 0,
            "inputs_sent":      0,
            "start_time":       0,
            "last_input_time":  0,
            "disconnections":   0,
        }

        # Listen for controller_config_data messages so imu_toggle_button updates
        # automatically when the user refreshes config from backend on a different device.
        if websocket_manager:
            try:
                websocket_manager.textMessageReceived.connect(self._on_websocket_message)
            except Exception:
                pass

        self.logger.info("SteamDeck controller thread initialised")

    def _scan_config_for_imu_toggle(self, config: dict):
        """Scan a controller config dict and populate imu_toggle_buttons."""
        if not isinstance(config, dict):
            return
        found = set()
        for control_name, entries in config.items():
            if isinstance(entries, dict):
                entries = [entries]
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict) and entry.get("behavior") == "imu_toggle":
                    found.add(control_name)
        self.imu_toggle_buttons = found
        if found:
            self.logger.info(f"IMU toggle buttons: {', '.join(sorted(found))}")
        else:
            self.logger.warning("No imu_toggle behavior found in controller config")

    def _load_controller_config(self):
        """Read controller config from disk and update imu_toggle_buttons."""
        try:
            with open("resources/configs/controller_config.json", "r") as f:
                config = json.load(f)
            self._scan_config_for_imu_toggle(config)
        except Exception as e:
            self.logger.error(f"Could not load controller config: {e}")

    def _on_websocket_message(self, text: str):
        """Reload controller config when a save completes."""
        try:
            data = json.loads(text)
            if data.get("type") == "controller_config_saved" and data.get("success"):
                self._load_controller_config()
        except Exception:
            pass

    def start_monitoring(self):
        if not self.running:
            self._load_controller_config()
            self.running = True
            self.stats["start_time"] = time.time()
            self.start()
            self.logger.info("SteamDeck controller monitoring started")
    def stop_monitoring(self):
        """Signal the poll loop to stop and wait for the thread to exit cleanly."""
        self.running = False

        # Disconnect websocket signals before the thread tears down so there
        # are no dangling references to this object after cleanup.
        if self.websocket_manager:
            try:
                self.websocket_manager.textMessageReceived.disconnect(self._on_websocket_message)
            except Exception:
                pass

        if self.isRunning():
            # No self.quit() here — run() uses a plain while loop, not a Qt
            # event loop, so quit() is a no-op. Setting self.running = False is
            # sufficient to break the loop. Give it 5 s to flush cleanup.
            self.wait(5000)

        self.logger.info("SteamDeck controller monitoring stopped")

    def run(self):
        """Main 50 Hz polling loop"""
        self._init_hid()

        while self.running:
            current_time = time.monotonic()

            if self.controller_active:
                try:
                    self._read_and_send(current_time)
                except Exception as e:
                    self.logger.error(f"Input read error: {e}")

            if int(current_time) % 5 == 0:
                self._update_stats()

            elapsed = time.monotonic() - current_time
            sleep_time = self.poll_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        self._cleanup_hid()

    def _init_hid(self):
        """Open the raw HID device using direct file I/O for sticks/buttons,
        and bitsteam for IMU data (requires Steam gyro disabled in Desktop Config)."""
        import os
        retry_delay = 2.0
        while self.running and not self.controller_active:
            try:
                # Open hidraw directly — hidapi open_path fails inside the
                # Distrobox container due to ACL/userns mapping.
                fd = os.open(HIDRAW_PATH_STR, os.O_RDWR | os.O_NONBLOCK)
                self._hid_device = fd

                # Enable IMU output in firmware
                os.write(fd, IMU_ENABLE_CMD)
                time.sleep(0.3)

                # bitsteam is used solely for IMU (pitch/yaw/roll) data.
                # Buttons and sticks are parsed from raw bytes in _drain_hid.
                # Requires Steam gyro set to None in Desktop Configuration.
                from bitsteam import SteamDeck as BitSteamDeck
                self._bitsteam_deck = BitSteamDeck()
                self._bitsteam_deck.start()
                time.sleep(0.2)

                self.controller_active = True
                self.logger.info(f"HID controller opened: {HIDRAW_PATH_STR}")
                self.controller_connected.emit("Steam Deck", "steamdeck_hid")

            except Exception as e:
                self.logger.warning(f"HID init failed: {e} — retrying in {retry_delay}s")
                deadline = time.monotonic() + retry_delay
                while self.running and time.monotonic() < deadline:
                    time.sleep(0.1)

    def _cleanup_hid(self):
        """Release HID resources cleanly."""
        try:
            if self._bitsteam_deck:
                # stop() joins the bitsteam background thread — give it 2s before giving up
                import threading
                t = threading.Thread(target=self._bitsteam_deck.stop, daemon=True)
                t.start()
                t.join(timeout=2.0)
                if t.is_alive():
                    self.logger.warning("bitsteam stop() timed out — continuing shutdown")
                self._bitsteam_deck = None
        except Exception as e:
            self.logger.debug(f"bitsteam stop error: {e}")

        try:
            if self._hid_device is not None:
                import os
                os.close(self._hid_device)
                self._hid_device = None
        except Exception as e:
            self.logger.debug(f"HID close error: {e}")

        # Only signal disconnect if we actually connected — avoids a spurious
        # "disconnected" event on startup failure or repeated stop() calls.
        if self.controller_active:
            self.controller_active = False
            self.controller_disconnected.emit("HID device closed")

    def _drain_hid(self) -> Optional[bytes]:
        """Read all pending HID reports and return only the most recent.

        The Steam Deck sends reports at ~250Hz but we poll at 50Hz. Without
        draining, the kernel FIFO builds up and reads become stale by seconds.
        """
        import os
        import select
        latest = None
        while True:
            r, _, _ = select.select([self._hid_device], [], [], 0)
            if not r:
                break
            try:
                data = os.read(self._hid_device, 64)
                if data:
                    latest = data
            except BlockingIOError:
                break
        return latest

    def _read_and_send(self, current_time: float):
        """Read one HID frame, parse all inputs, and emit the websocket message"""
        raw = self._drain_hid()
        if not raw or len(raw) < 56:
            return
        axes    = self._parse_analog(raw)
        buttons = self._parse_buttons(raw)

        # Toggle IMU on button press edge; add axes if enabled
        self._check_imu_toggle(buttons, raw)
        if self.imu_enabled:
            axes.update(self._parse_imu(raw))

        input_data = ControllerInputData(
            axes=axes,
            buttons=buttons,
            timestamp=current_time,
            sequence=self.sequence_number,
        )
        self.sequence_number += 1

        self.controller_input.emit(input_data)
        self._send_controller_websocket(input_data)
        self.stats["inputs_processed"] += 1
        self.stats["last_input_time"]   = current_time
        self.last_input_sent            = current_time

    def _parse_analog(self, raw: bytes) -> Dict[str, float]:
        """Parse sticks and triggers from raw HID bytes, apply deadzone"""
        lt = struct.unpack_from('<H', raw, OFF_LEFT_TRIGGER)[0]
        rt = struct.unpack_from('<H', raw, OFF_RIGHT_TRIGGER)[0]
        lx = struct.unpack_from('<h', raw, OFF_LEFT_STICK_X)[0]
        ly = struct.unpack_from('<h', raw, OFF_LEFT_STICK_Y)[0]
        rx = struct.unpack_from('<h', raw, OFF_RIGHT_STICK_X)[0]
        ry = struct.unpack_from('<h', raw, OFF_RIGHT_STICK_Y)[0]

        return {
            'left_trigger':  self._norm_trigger(lt),
            'right_trigger': self._norm_trigger(rt),
            'left_stick_x':  self._norm_stick(lx),
            'left_stick_y':  self._norm_stick(ly),
            'right_stick_x': self._norm_stick(rx),
            'right_stick_y': self._norm_stick(ry),
        }

    def _parse_imu(self, raw: bytes) -> Dict[str, float]:
        """Read IMU tilt from bitsteam which handles the firmware activation.
        Returns normalised roll and pitch in ±1.0 range with deadzone applied.
        Requires Steam gyro set to None in Desktop Configuration.
        """
        if not self._bitsteam_deck:
            return {'imu_roll': 0.0, 'imu_pitch': 0.0}
        try:
            imu = self._bitsteam_deck.imu
            roll  = self._norm_imu_rate(imu.get('roll',  0.0))
            pitch = self._norm_imu_rate(imu.get('pitch', 0.0))
            return {
                'imu_roll':  roll,
                'imu_pitch': pitch,
            }
        except Exception:
            return {'imu_roll': 0.0, 'imu_pitch': 0.0}

    def _parse_buttons(self, raw: bytes) -> Dict[str, bool]:
        """Parse button state directly from the raw HID report bytes.
        Byte/bit mapping verified against the bitsteam library source.
        """
        b8  = raw[8]
        b9  = raw[9]
        b10 = raw[10]
        b11 = raw[11]
        b13 = raw[13]
        b14 = raw[14]
        return {
            'button_a':            bool(b8  & 0x80),
            'button_b':            bool(b8  & 0x20),
            'button_x':            bool(b8  & 0x40),
            'button_y':            bool(b8  & 0x10),
            'shoulder_left':       bool(b8  & 0x08),
            'shoulder_right':      bool(b8  & 0x04),
            'left_trigger_btn':    bool(b8  & 0x02),
            'right_trigger_btn':   bool(b8  & 0x01),
            'dpad_up':             bool(b9  & 0x01),
            'dpad_down':           bool(b9  & 0x08),
            'dpad_left':           bool(b9  & 0x04),
            'dpad_right':          bool(b9  & 0x02),
            'button_back':         bool(b9  & 0x10),
            'button_guide':        bool(b9  & 0x20),
            'button_menu':         bool(b9  & 0x40),
            'grip_left_lower':     bool(b9  & 0x80),
            'grip_right_lower':    bool(b10 & 0x01),
            'stick_left_click':    bool(b10 & 0x40),
            'button_left_pad':     (b10 & 0x0a) == 0x0a,
            'button_right_pad':    (b10 & 0x14) == 0x14,
            'stick_right_click':   bool(b11 & 0x04),
            'grip_left_upper':     bool(b13 & 0x02),
            'grip_right_upper':    bool(b13 & 0x04),
            'button_quick_access': bool(b14 & 0x04),
        }

    def _check_imu_toggle(self, buttons: Dict[str, bool], raw: bytes):
        """Detect a press edge on any configured IMU toggle button.
        All buttons are checked before deciding to toggle — no early exit."""
        triggered = False
        for btn in self.imu_toggle_buttons:
            current = buttons.get(btn, False)
            prev    = self._prev_buttons.get(btn, False)
            if current and not prev:
                triggered = True
        if triggered:
            self._toggle_imu(raw)
        self._prev_buttons = buttons

    def _toggle_imu(self, raw: bytes):
        """Enable or disable IMU tilt control via bitsteam."""
        if not self.imu_enabled:
            self.imu_enabled = True
            self.logger.info("IMU tilt enabled via bitsteam")
        else:
            self.imu_enabled = False
            self.logger.info("IMU tilt disabled")

    def _norm_stick(self, raw_int16: int) -> float:
        """Normalise int16 stick value to ±1.0 with deadzone"""
        v = raw_int16 / STICK_MAX
        return 0.0 if abs(v) < STICK_DEADZONE else max(-1.0, min(1.0, v))

    def _norm_trigger(self, raw_uint16: int) -> float:
        """Normalise a trigger to -1.0 (released) → +1.0 (fully pressed).

        The old pygame axis range was -1 to +1 so multi_servo's center-based
        formula (center ± pulse_range) sweeps the full servo min→max.
        Mapping 0→1 instead would only use the upper half of the range.
        """
        return max(-1.0, min(1.0, (raw_uint16 / TRIGGER_MAX) * 2.0 - 1.0))

    def _norm_imu(self, delta: int) -> float:
        """Normalise IMU delta value to ±1.0 with deadzone"""
        v = delta / IMU_MAX
        return 0.0 if abs(v) < IMU_DEADZONE else max(-1.0, min(1.0, v))

    def _norm_imu_rate(self, rate: float) -> float:
        """Normalise bitsteam IMU rate (degrees/sec) to ±1.0 with deadzone.
        Clamps at ±90 deg/sec as the practical tilt range for servo control.
        """
        v = rate / 90.0
        return 0.0 if abs(v) < IMU_DEADZONE else max(-1.0, min(1.0, v))

    def _send_controller_websocket(self, input_data: ControllerInputData):
        """Emit controller data as a thread-safe Qt signal for the websocket"""
        try:
            message = {
                "type":      "steamdeck_controller",
                "axes":      input_data.axes,
                "buttons":   input_data.buttons,
                "timestamp": input_data.timestamp,
                "sequence":  input_data.sequence,
                "source":    "steamdeck",
            }
            self.send_websocket_message.emit(message)
            self.stats["inputs_sent"] += 1

            if self.stats["inputs_sent"] == 1:
                self.logger.info("First controller message sent")
            elif self.stats["inputs_sent"] % 500 == 0:
                self.logger.debug(f"Controller messages sent: {self.stats['inputs_sent']}")

        except Exception as e:
            self.logger.error(f"Failed to queue controller data: {e}", exc_info=True)

    def _update_stats(self):
        current_time = time.time()
        uptime = current_time - self.stats["start_time"] if self.stats["start_time"] > 0 else 0
        self.stats_updated.emit({
            **self.stats,
            "uptime":            uptime,
            "controller_active": self.controller_active,
            "controller_name":   "Steam Deck (HID)",
            "imu_enabled":       self.imu_enabled,
            "input_rate":        self.stats["inputs_processed"] / uptime if uptime > 0 else 0,
        })

    @error_boundary
    def get_controller_info(self) -> Dict[str, Any]:
        return {
            "connected":       self.controller_active,
            "controller_name": "Steam Deck (HID)",
            "controller_id":   "steamdeck_hid",
            "imu_enabled":     self.imu_enabled,
            "imu_toggle":      sorted(self.imu_toggle_buttons),
            "sequence_number": self.sequence_number,
            "poll_rate":       self.poll_rate_hz,
        }

    def set_poll_rate(self, hz: int):
        if 10 <= hz <= 120:
            self.poll_rate_hz  = hz
            self.poll_interval = 1.0 / hz
            self.logger.info(f"Controller poll rate set to {hz} Hz")

    def enable_safety_monitoring(self, enabled: bool):
        self.logger.info(f"Safety monitoring {'enabled' if enabled else 'disabled'}")