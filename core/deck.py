import hid
import threading
import struct
import time
from scipy.spatial.transform import Rotation as R

# Steam Deck controller feature-report protocol (from Linux hid-steam.c).
# In game mode, Steam strips accelerometer/gyro out of the HID report unless
# the gyro is configured to a used mode. Sending this settings command tells
# the controller firmware to keep raw accel and raw gyro in every report,
# regardless of the Steam controller-layout gyro setting.
_ID_SET_SETTINGS_VALUES = 0x87
_SETTING_GYRO_MODE = 48
_GYRO_MODE_SEND_RAW_ACCEL = 0x08
_GYRO_MODE_SEND_RAW_GYRO = 0x10
# Combined bitmask: keep both raw accelerometer and raw gyroscope in the report.
_GYRO_MODE_VALUE = _GYRO_MODE_SEND_RAW_ACCEL | _GYRO_MODE_SEND_RAW_GYRO
# Steam re-disables the sensors periodically, so the enable command must be
# re-sent. SDL re-sends roughly every 800ms; matching that interval.
_GYRO_REENABLE_INTERVAL = 0.8


class SteamDeck:
    """
    A library to read and process input from a Steam Deck controller.
    """

    def __init__(self, device_path=None):
        """
        Initializes the Steam Deck controller.

        :param device_path: The HID device path for the Steam Deck. Pass None to auto-discover.
        """
        if device_path is None:
            try:
                device_path = self._discover_device_path()
            except Exception:
                # Fallback to a sensible default for systems where discovery
                # fails (keeps backward compatibility).
                device_path = b"/dev/hidraw2"

        self.device_path = device_path
        self.is_running = False
        self._thread = None
        self._lock = threading.Lock()

        # Initialize state dictionaries
        self.buttons = {
            'a': False, 'b': False, 'x': False, 'y': False,
            'l1': False, 'r1': False, 'l2_click': False, 'r2_click': False,
            'dpad_up': False, 'dpad_down': False, 'dpad_left': False, 'dpad_right': False,
            'select': False, 'start': False, 'steam': False, 'quick_access': False,
            'l_lower_grip': False, 'r_lower_grip': False,
            'l_upper_grip': False, 'r_upper_grip': False,
            'l_stick_press': False, 'r_stick_press': False,
            'l_stick_touch': False, 'r_stick_touch': False,
            'l_trackpad_touch': False, 'l_trackpad_press': False,
            'r_trackpad_touch': False, 'r_trackpad_press': False
        }
        self.analog = {
            'left_trigger': 0, 'right_trigger': 0,
            'left_stick_x': 0, 'left_stick_y': 0,
            'right_stick_x': 0, 'right_stick_y': 0,
            'left_trackpad_x': 0, 'left_trackpad_y': 0,
            'right_trackpad_x': 0, 'right_trackpad_y': 0,
            'left_trackpad_pressure': 0, 'right_trackpad_pressure': 0
        }
        self.imu = {
            'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0
        }

        # Raw accelerometer and gyroscope values (int16 from HID report)
        self.motion = {
            'accel_x': 0, 'accel_y': 0, 'accel_z': 0,
            'gyro_x': 0, 'gyro_y': 0, 'gyro_z': 0
        }

        self.previous_device_orientation = R.identity()
        self.is_first_imu_frame = True
        self._last_imu_time = None

        # Byte offsets (named constants make maintenance easier)
        self.OFF_BTN_BYTE8 = 8
        self.OFF_BTN_BYTE9 = 9
        self.OFF_BTN_BYTE10 = 10
        self.OFF_BTN_BYTE11 = 11
        self.OFF_BTN_BYTE13 = 13
        self.OFF_BTN_BYTE14 = 14
        self.OFF_LEFT_TRACK_X = 16
        self.OFF_LEFT_TRACK_Y = 18
        self.OFF_RIGHT_TRACK_X = 20
        self.OFF_RIGHT_TRACK_Y = 22
        self.OFF_LEFT_TRIGGER = 44
        self.OFF_RIGHT_TRIGGER = 46
        self.OFF_LEFT_STICK_X = 48
        self.OFF_LEFT_STICK_Y = 50
        self.OFF_RIGHT_STICK_X = 52
        self.OFF_RIGHT_STICK_Y = 54
        self.OFF_LEFT_TRACKPAD_PRESSURE = 56
        self.OFF_RIGHT_TRACKPAD_PRESSURE = 58
        self.OFF_IMU_START = 36

        # Raw accelerometer offsets (int16 little-endian)
        self.OFF_ACCEL_X = 24
        self.OFF_ACCEL_Y = 26
        self.OFF_ACCEL_Z = 28
        # Raw gyroscope offsets (int16 little-endian)
        self.OFF_GYRO_X = 30
        self.OFF_GYRO_Y = 32
        self.OFF_GYRO_Z = 34

    def _discover_device_path(self):
        """
        Finds the Steam Deck hidraw path by inspecting enumerated HID devices.
        """
        for device in hid.enumerate():
            vendor_id = device.get('vendor_id')
            product_id = device.get('product_id')
            interface_number = device.get('interface_number')

            if vendor_id == 0x28DE and product_id == 0x1205 and interface_number == 2:
                return device.get('path')

        raise RuntimeError('Could not auto-discover the Steam Deck HID device.')

    def _enable_motion_sensors(self, device):
        """
        Tell the controller firmware to include raw accel/gyro in every HID
        report. Required in Steam game mode where the sensors are otherwise
        stripped from the report. Safe to call repeatedly.
        """
        # Packet: [0x87, len, reg, val_lo, val_hi] padded to 64 bytes.
        # A report ID of 0x00 is prepended for the feature report.
        cmd = bytearray(64)
        cmd[0] = _ID_SET_SETTINGS_VALUES
        cmd[1] = 0x03
        cmd[2] = _SETTING_GYRO_MODE
        cmd[3] = _GYRO_MODE_VALUE & 0xFF
        cmd[4] = (_GYRO_MODE_VALUE >> 8) & 0xFF
        try:
            device.send_feature_report(b'\x00' + bytes(cmd))
        except Exception as e:
            print(f"Failed to send motion-enable feature report: {e}")

    def _read_and_parse_thread(self):
        """
        Continuously reads and parses data from the HID device in a separate thread.
        """
        try:
            with hid.Device(path=self.device_path) as device:
                self.is_running = True
                print("Steam Deck reader thread started.")
                self._enable_motion_sensors(device)
                last_reenable = time.monotonic()
                while self.is_running:
                    data = device.read(64, timeout=200)
                    if data:
                        self._parse_input(data)
                    now = time.monotonic()
                    if now - last_reenable >= _GYRO_REENABLE_INTERVAL:
                        self._enable_motion_sensors(device)
                        last_reenable = now
        except Exception as e:
            print(f"Error reading from HID device: {e}")
        finally:
            self.is_running = False
            print("Steam Deck reader thread stopped.")

    def _parse_input(self, data):
        """
        Parses the 64-byte raw input data from the Steam Deck.
        """
        # Parse into local variables (keep lock scope short)
        byte8 = data[self.OFF_BTN_BYTE8]
        a_btn = bool(byte8 & 0x80)
        b_btn = bool(byte8 & 0x20)
        x_btn = bool(byte8 & 0x40)
        y_btn = bool(byte8 & 0x10)
        l1_btn = bool(byte8 & 0x08)
        r1_btn = bool(byte8 & 0x04)
        l2_click = bool(byte8 & 0x02)
        r2_click = bool(byte8 & 0x01)

        byte9 = data[self.OFF_BTN_BYTE9]
        dpad_up = bool(byte9 & 0x01)
        # Dashboard mapping: down and right are swapped compared to earlier guesses
        dpad_down = bool(byte9 & 0x08)
        dpad_left = bool(byte9 & 0x04)
        dpad_right = bool(byte9 & 0x02)
        select_btn = bool(byte9 & 0x10)
        steam_btn = bool(byte9 & 0x20)
        start_btn = bool(byte9 & 0x40)
        quick_access = False

        # Apply dashboard-verified mappings for lower grips and stick touches

        byte10 = data[self.OFF_BTN_BYTE10]
        l_stick_press = bool(byte10 & 0x40)
        l_trackpad_touch = bool(byte10 & 0x08)
        l_trackpad_press = (byte10 & 0x0a) == 0x0a
        r_trackpad_touch = bool(byte10 & 0x10)
        r_trackpad_press = (byte10 & 0x14) == 0x14
        # Dashboard: right lower grip is in byte10 bit 0
        r_lower_grip = bool(byte10 & 0x01)

        byte11 = data[self.OFF_BTN_BYTE11]
        r_stick_press = bool(byte11 & 0x04)

        byte13 = data[self.OFF_BTN_BYTE13]
        l_upper_grip = bool(byte13 & 0x02)
        r_upper_grip = bool(byte13 & 0x04)
        # Stick touch sensors (verified)
        l_stick_touch = bool(byte13 & 0x40)
        r_stick_touch = bool(byte13 & 0x80)

        # Read byte14 for quick access
        byte14 = data[self.OFF_BTN_BYTE14]
        quick_access = bool(byte14 & 0x04)

        # --- Analog Sticks ---
        left_stick_x = struct.unpack('<h', data[self.OFF_LEFT_STICK_X:self.OFF_LEFT_STICK_X+2])[0]
        left_stick_y = struct.unpack('<h', data[self.OFF_LEFT_STICK_Y:self.OFF_LEFT_STICK_Y+2])[0]
        right_stick_x = struct.unpack('<h', data[self.OFF_RIGHT_STICK_X:self.OFF_RIGHT_STICK_X+2])[0]
        right_stick_y = struct.unpack('<h', data[self.OFF_RIGHT_STICK_Y:self.OFF_RIGHT_STICK_Y+2])[0]

        # --- Triggers ---
        left_trigger = struct.unpack('<H', data[self.OFF_LEFT_TRIGGER:self.OFF_LEFT_TRIGGER+2])[0]
        right_trigger = struct.unpack('<H', data[self.OFF_RIGHT_TRIGGER:self.OFF_RIGHT_TRIGGER+2])[0]

        # --- Touchpads ---
        left_track_x = struct.unpack('<h', data[self.OFF_LEFT_TRACK_X:self.OFF_LEFT_TRACK_X+2])[0]
        left_track_y = struct.unpack('<h', data[self.OFF_LEFT_TRACK_Y:self.OFF_LEFT_TRACK_Y+2])[0]
        right_track_x = struct.unpack('<h', data[self.OFF_RIGHT_TRACK_X:self.OFF_RIGHT_TRACK_X+2])[0]
        right_track_y = struct.unpack('<h', data[self.OFF_RIGHT_TRACK_Y:self.OFF_RIGHT_TRACK_Y+2])[0]
        left_track_pressure = struct.unpack('<H', data[self.OFF_LEFT_TRACKPAD_PRESSURE:self.OFF_LEFT_TRACKPAD_PRESSURE+2])[0]
        right_track_pressure = struct.unpack('<H', data[self.OFF_RIGHT_TRACKPAD_PRESSURE:self.OFF_RIGHT_TRACKPAD_PRESSURE+2])[0]

        # --- Raw Accelerometer / Gyroscope (int16 little-endian) ---
        accel_x = struct.unpack('<h', data[self.OFF_ACCEL_X:self.OFF_ACCEL_X+2])[0]
        accel_y = struct.unpack('<h', data[self.OFF_ACCEL_Y:self.OFF_ACCEL_Y+2])[0]
        accel_z = struct.unpack('<h', data[self.OFF_ACCEL_Z:self.OFF_ACCEL_Z+2])[0]
        gyro_x = struct.unpack('<h', data[self.OFF_GYRO_X:self.OFF_GYRO_X+2])[0]
        gyro_y = struct.unpack('<h', data[self.OFF_GYRO_Y:self.OFF_GYRO_Y+2])[0]
        gyro_z = struct.unpack('<h', data[self.OFF_GYRO_Z:self.OFF_GYRO_Z+2])[0]

        # Update shared state under lock
        with self._lock:
            self.buttons['a'] = a_btn
            self.buttons['b'] = b_btn
            self.buttons['x'] = x_btn
            self.buttons['y'] = y_btn
            self.buttons['l1'] = l1_btn
            self.buttons['r1'] = r1_btn
            self.buttons['l2_click'] = l2_click
            self.buttons['r2_click'] = r2_click

            self.buttons['dpad_up'] = dpad_up
            self.buttons['dpad_down'] = dpad_down
            self.buttons['dpad_left'] = dpad_left
            self.buttons['dpad_right'] = dpad_right
            self.buttons['select'] = select_btn
            self.buttons['start'] = start_btn
            self.buttons['steam'] = steam_btn
            self.buttons['quick_access'] = quick_access

            # Dashboard mapping for lower grips
            self.buttons['l_lower_grip'] = bool(byte9 & 0x80)
            self.buttons['r_lower_grip'] = r_lower_grip

            self.buttons['l_upper_grip'] = l_upper_grip
            self.buttons['r_upper_grip'] = r_upper_grip
            self.buttons['l_stick_press'] = l_stick_press
            self.buttons['l_stick_touch'] = l_stick_touch
            self.buttons['r_stick_touch'] = r_stick_touch
            self.buttons['l_trackpad_touch'] = l_trackpad_touch
            self.buttons['l_trackpad_press'] = l_trackpad_press
            self.buttons['r_trackpad_touch'] = r_trackpad_touch
            self.buttons['r_trackpad_press'] = r_trackpad_press
            self.buttons['r_stick_press'] = r_stick_press

            self.analog['left_stick_x'] = left_stick_x
            self.analog['left_stick_y'] = left_stick_y
            self.analog['right_stick_x'] = right_stick_x
            self.analog['right_stick_y'] = right_stick_y

            self.analog['left_trigger'] = left_trigger
            self.analog['right_trigger'] = right_trigger

            self.analog['left_trackpad_x'] = left_track_x
            self.analog['left_trackpad_y'] = left_track_y
            self.analog['right_trackpad_x'] = right_track_x
            self.analog['right_trackpad_y'] = right_track_y
            self.analog['left_trackpad_pressure'] = left_track_pressure
            self.analog['right_trackpad_pressure'] = right_track_pressure

            self.motion['accel_x'] = accel_x
            self.motion['accel_y'] = accel_y
            self.motion['accel_z'] = accel_z
            self.motion['gyro_x'] = gyro_x
            self.motion['gyro_y'] = gyro_y
            self.motion['gyro_z'] = gyro_z

        # --- IMU (Gyro) ---
        self._parse_imu(data)

    def _parse_imu(self, data):
        """
        Parses the IMU data to calculate pitch, yaw, and roll rates.
        """
        # Read raw quaternion-like values (2-byte signed each)
        raw_vals = [struct.unpack('<h', bytes(data[i:i+2]))[0] for i in range(self.OFF_IMU_START, self.OFF_IMU_START+8, 2)]
        scaling_factor = 16384.0
        q_x, q_y, q_z, q_w = [v / scaling_factor for v in raw_vals]

        try:
            # Map input to (x, y, z, w) as expected by scipy
            input_quat_map = [q_z, q_y, q_x, q_w]
            current_device_orientation = R.from_quat(input_quat_map)

            now = time.perf_counter()
            if self.is_first_imu_frame or self._last_imu_time is None:
                # First valid frame: initialize reference
                self.previous_device_orientation = current_device_orientation
                self.is_first_imu_frame = False
                self._last_imu_time = now
                return

            dt = now - self._last_imu_time
            if dt <= 0:
                # Unreliable dt; reset timestamp and flag
                self.is_first_imu_frame = True
                self._last_imu_time = now
                return

            # Compute local rotation from previous to current
            delta_local = self.previous_device_orientation.inv() * current_device_orientation
            # Euler angles (zyx) in degrees
            delta_angles = delta_local.as_euler('zyx', degrees=True)

            # Convert delta angles (degrees per frame) -> rates (degrees/sec)
            rates = [angle / dt for angle in delta_angles]

            # Store as roll, yaw, pitch (matching previous layout)
            self._lock.acquire()
            try:
                self.imu['roll'], self.imu['yaw'], self.imu['pitch'] = rates
            finally:
                self._lock.release()

            # Update reference and time
            self.previous_device_orientation = current_device_orientation
            self._last_imu_time = now

        except Exception:
            # On parse errors, reset IMU state so next valid frame re-initializes
            self.is_first_imu_frame = True
            self._last_imu_time = None

    def start(self):
        """
        Starts the thread that reads from the Steam Deck.
        """
        if not self.is_running:
            self._thread = threading.Thread(target=self._read_and_parse_thread, daemon=True)
            self._thread.start()

    def stop(self):
        """
        Stops the thread that reads from the Steam Deck.
        """
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join()

    def get_button_state(self, button_name):
        """
        Gets the state of a specific button.

        :param button_name: The name of the button.
        :return: True if pressed, False otherwise.
        """
        with self._lock:
            return self.buttons.get(button_name, False)

    def get_analog_values(self):
        """
        Gets the current values of all analog inputs.

        :return: A dictionary with the analog input values.
        """
        with self._lock:
            return self.analog.copy()

    def get_imu_rates(self):
        """
        Gets the current IMU rotation rates.

        :return: A dictionary with the pitch, yaw, and roll rates.
        """
        with self._lock:
            return self.imu.copy()

    def get_motion_values(self):
        """
        Gets the current raw accelerometer and gyroscope values.

        :return: A dictionary with accel_x/y/z and gyro_x/y/z as int16 values.
        """
        with self._lock:
            return self.motion.copy()