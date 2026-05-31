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

import struct
import time
from typing import Dict, Any, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from core.logger import get_logger
from core.config_manager import config_manager
from core.utils import error_boundary


# HID device path for the Steam Deck built-in controller
HIDRAW_PATH = b'/dev/hidraw3'

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
    'start':            'button_start',
    'steam':            'button_guide',
    'quick_access':     'button_quick_access',
    'l_stick_press':    'button_l3',
    'r_stick_press':    'button_r3',
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
        self.imu_enabled      = False
        self.imu_zero_ax      = 0
        self.imu_zero_ay      = 0
        self._prev_buttons    = {}
        self.imu_toggle_button = self._load_imu_toggle_button()

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

        self.logger.info("SteamDeck controller thread initialised")

    def _load_imu_toggle_button(self) -> str:
        """Read the IMU toggle button name from config, default to button_r3"""
        try:
            cfg = config_manager.get_config("resources/configs/steamdeck_config.json")
            return cfg.get("current", {}).get("imu_toggle_button", "button_r3")
        except Exception:
            return "button_r3"

    def start_monitoring(self):
        if not self.running:
            self.running = True
            self.stats["start_time"] = time.time()
            self.start()
            self.logger.info("SteamDeck controller monitoring started")

    def stop_monitoring(self):
        self.running = False
        if self.isRunning():
            self.quit()
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
        """Open the raw HID device and start the bitsteam button reader"""
        retry_delay = 2.0
        while self.running and not self.controller_active:
            try:
                import hid
                self._hid_device = hid.Device(path=HIDRAW_PATH)
                self._hid_device.nonblocking = True

                # Enable IMU output in firmware
                self._hid_device.write(IMU_ENABLE_CMD)
                time.sleep(0.3)

                # bitsteam reads buttons from the same hidraw device independently
                from bitsteam import SteamDeck as BitSteamDeck
                self._bitsteam_deck = BitSteamDeck()
                self._bitsteam_deck.start()
                time.sleep(0.2)

                self.controller_active = True
                self.logger.info(f"HID controller opened: {HIDRAW_PATH}")
                self.controller_connected.emit("Steam Deck", "steamdeck_hid")

            except Exception as e:
                self.logger.warning(f"HID init failed: {e} — retrying in {retry_delay}s")
                time.sleep(retry_delay)

    def _cleanup_hid(self):
        """Release HID resources"""
        try:
            if self._bitsteam_deck:
                self._bitsteam_deck.stop()
                self._bitsteam_deck = None
        except Exception as e:
            self.logger.debug(f"bitsteam stop error: {e}")

        try:
            if self._hid_device:
                self._hid_device.close()
                self._hid_device = None
        except Exception as e:
            self.logger.debug(f"HID close error: {e}")

        if self.controller_active:
            self.controller_active = False
            self.controller_disconnected.emit("HID device closed")

    def _drain_hid(self) -> Optional[bytes]:
        """Read all pending HID reports and return only the most recent.

        The Steam Deck sends reports at ~250Hz but we poll at 50Hz. Without
        draining, the kernel FIFO builds up and reads become stale by seconds.
        """
        latest = None
        while True:
            data = self._hid_device.read(64)
            if not data:
                break
            latest = bytes(data)
        return latest

    def _read_and_send(self, current_time: float):
        """Read one HID frame, parse all inputs, and emit the websocket message"""
        raw = self._drain_hid()
        if not raw or len(raw) < 56:
            return
        axes    = self._parse_analog(raw)
        buttons = self._parse_buttons()

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
        """Parse accelerometer tilt axes relative to the calibration zero point"""
        ax = struct.unpack_from('<h', raw, OFF_ACCEL_X)[0] - self.imu_zero_ax
        ay = struct.unpack_from('<h', raw, OFF_ACCEL_Y)[0] - self.imu_zero_ay

        roll  = self._norm_imu(ax)
        pitch = self._norm_imu(ay)

        return {
            'imu_roll':  roll,
            'imu_pitch': pitch,
        }

    def _parse_buttons(self) -> Dict[str, bool]:
        """Read button state from bitsteam and remap to DroidDeck control names"""
        if not self._bitsteam_deck:
            return {}
        raw = self._bitsteam_deck.buttons
        return {
            our_name: bool(raw.get(bs_name, False))
            for bs_name, our_name in BUTTON_MAP.items()
        }

    def _check_imu_toggle(self, buttons: Dict[str, bool], raw: bytes):
        """Detect a press edge on the IMU toggle button and switch IMU state"""
        current = buttons.get(self.imu_toggle_button, False)
        prev    = self._prev_buttons.get(self.imu_toggle_button, False)

        if current and not prev:
            self._toggle_imu(raw)

        self._prev_buttons = buttons

    def _toggle_imu(self, raw: bytes):
        """Enable or disable IMU tilt control, calibrating zero on enable"""
        if not self.imu_enabled:
            # Capture current accelerometer values as the neutral reference
            try:
                self.imu_zero_ax = struct.unpack_from('<h', raw, OFF_ACCEL_X)[0]
                self.imu_zero_ay = struct.unpack_from('<h', raw, OFF_ACCEL_Y)[0]
            except Exception:
                self.imu_zero_ax = 0
                self.imu_zero_ay = 0
            self.imu_enabled = True
            self.logger.info(
                f"IMU tilt enabled — zero ref: "
                f"roll={self.imu_zero_ax} pitch={self.imu_zero_ay}"
            )
        else:
            self.imu_enabled = False
            self.logger.info("IMU tilt disabled")

    def _norm_stick(self, raw_int16: int) -> float:
        """Normalise int16 stick value to ±1.0 with deadzone"""
        v = raw_int16 / STICK_MAX
        return 0.0 if abs(v) < STICK_DEADZONE else max(-1.0, min(1.0, v))

    def _norm_trigger(self, raw_uint16: int) -> float:
        """Normalise uint16 trigger value to 0.0–1.0 with deadzone"""
        v = raw_uint16 / TRIGGER_MAX
        return 0.0 if v < TRIGGER_DEADZONE else min(1.0, v)

    def _norm_imu(self, delta: int) -> float:
        """Normalise IMU delta value to ±1.0 with deadzone"""
        v = delta / IMU_MAX
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
            "imu_toggle":      self.imu_toggle_button,
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