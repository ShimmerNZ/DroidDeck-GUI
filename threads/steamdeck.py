#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SteamDeckControllerThread — HID-based input handler for DroidDeck

Reads analog, IMU and button data directly from the Steam Deck's
raw HID interface (/dev/hidraw3), bypassing the Steam Input layer.

All input is read via the local SteamDeckExtended class in deck.py.
No external bitsteam package required.

Byte offsets verified by hardware sweep testing (test_motion_standalone.py):
  Triggers:    44 (L), 46 (R)  — uint16, 0-32767
  Left stick:  48 (X), 50 (Y)  — int16,  ±32767
  Right stick: 52 (X), 54 (Y)  — int16,  ±32767
  Accel X:     24               — int16,  ±16384 (roll,  left=+, right=-)
  Accel Y:     26               — int16,  ±16384 (pitch, back=+, forward=-)
  Accel Z:     28               — int16,  ±16384 (vertical)
  Gyro X/Y/Z:  30/32/34        — int16,  raw gyroscope rates
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

# Normalisation constants
STICK_MAX   = 32767
TRIGGER_MAX = 32767

# Accelerometer full-scale range — 1g = 16384 LSB (verified by hardware sweep).
ACCEL_MAX = 16384

STICK_DEADZONE   = 0.05
TRIGGER_DEADZONE = 0.02
IMU_DEADZONE     = 0.04

# SteamDeckExtended field name → DroidDeck control name
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
        self.imu_enabled      = False
        self._accel_zero_x    = 0
        self._accel_zero_y    = 0
        self._prev_buttons    = {}
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
        """Start the bitsteam controller thread — handles all inputs including IMU."""
        retry_delay = 2.0
        while self.running and not self.controller_active:
            try:
                from core.deck import SteamDeckExtended
                self._bitsteam_deck = SteamDeckExtended()
                self._bitsteam_deck.start()
                time.sleep(0.5)

                if not self._bitsteam_deck.is_running:
                    raise RuntimeError("SteamDeckExtended thread failed to start")

                self.controller_active = True
                self.logger.info("SteamDeckExtended controller started")
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

        # raw HID device not used — bitsteam manages the device

        # Only signal disconnect if we actually connected — avoids a spurious
        # "disconnected" event on startup failure or repeated stop() calls.
        if self.controller_active:
            self.controller_active = False
            self.controller_disconnected.emit("HID device closed")

    def _drain_hid(self) -> Optional[bytes]:
        """Not used — all data comes from bitsteam. Returns a sentinel value."""
        return b'\x00' * 64

    def _read_and_send(self, current_time: float):
        """Read all inputs from bitsteam and emit the websocket message."""
        if not self._bitsteam_deck or not self._bitsteam_deck.is_running:
            return
        axes    = self._parse_analog()
        buttons = self._parse_buttons()

        # Toggle IMU on button press edge; add gyro axes if enabled
        self._check_imu_toggle(buttons)
        if self.imu_enabled:
            axes.update(self._parse_imu())

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

    def _parse_analog(self) -> Dict[str, float]:
        """Read sticks and triggers from bitsteam and apply deadzone."""
        a = self._bitsteam_deck.get_analog_values()
        return {
            'left_trigger':  self._norm_trigger(a.get('left_trigger',  0)),
            'right_trigger': self._norm_trigger(a.get('right_trigger', 0)),
            'left_stick_x':  self._norm_stick(a.get('left_stick_x',   0)),
            'left_stick_y':  self._norm_stick(a.get('left_stick_y',   0)),
            'right_stick_x': self._norm_stick(a.get('right_stick_x',  0)),
            'right_stick_y': self._norm_stick(a.get('right_stick_y',  0)),
        }

    def _parse_imu(self) -> Dict[str, float]:
        """Read absolute tilt from the raw accelerometer.

        Accelerometer values are gravity-relative — tilting the Deck changes
        how much of 1g projects onto each axis. This gives stable absolute
        tilt with no drift, no integration needed.
        The zero reference is captured when IMU is toggled on.
        """
        m = self._bitsteam_deck.get_motion_values()
        ax = m.get('accel_x', 0) - self._accel_zero_x
        ay = m.get('accel_y', 0) - self._accel_zero_y

        roll  = self._norm_imu_accel(ax)
        pitch = self._norm_imu_accel(ay)

        return {
            'imu_roll':  roll,
            'imu_pitch': pitch,
        }

    def _parse_buttons(self) -> Dict[str, bool]:
        """Read button state from bitsteam and remap to DroidDeck control names."""
        raw = self._bitsteam_deck.buttons
        return {
            our_name: bool(raw.get(bs_name, False))
            for bs_name, our_name in BUTTON_MAP.items()
        }

    def _check_imu_toggle(self, buttons: Dict[str, bool]):
        """Detect a press edge on any configured IMU toggle button.
        All buttons are checked before deciding to toggle — no early exit."""
        triggered = False
        for btn in self.imu_toggle_buttons:
            current = buttons.get(btn, False)
            prev    = self._prev_buttons.get(btn, False)
            if current and not prev:
                triggered = True
        if triggered:
            self._toggle_imu()
        self._prev_buttons = buttons

    def _toggle_imu(self):
        """Enable or disable IMU tilt. Captures accelerometer zero ref on enable."""
        if not self.imu_enabled:
            if self._bitsteam_deck:
                m = self._bitsteam_deck.get_motion_values()
                self._accel_zero_x = m.get('accel_x', 0)
                self._accel_zero_y = m.get('accel_y', 0)
            else:
                self._accel_zero_x = 0
                self._accel_zero_y = 0
            self.imu_enabled = True
            self.logger.info(
                f"IMU tilt enabled — accel zero: x={self._accel_zero_x} y={self._accel_zero_y}"
            )
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

    def _norm_imu_accel(self, counts: int) -> float:
        """Normalise raw accelerometer counts to ±1.0 with deadzone.
        ACCEL_MAX counts (1g) maps to ±1.0 full servo travel.
        """
        v = counts / ACCEL_MAX
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