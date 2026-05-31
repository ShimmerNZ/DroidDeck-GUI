#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bitsteam field inspector for DroidDeck — updated for actual API
Output saved to ~/DroidDeck/bitsteam_fields.txt

Run inside Distrobox:
    python3 ~/DroidDeck/inspect_bitsteam_fields.py
"""

import time
import sys

OUTPUT_FILE = "/home/deck/DroidDeck/bitsteam_fields.txt"

def log(msg=""):
    print(msg)
    with open(OUTPUT_FILE, 'a') as f:
        f.write(msg + "\n")

# Clear output file
open(OUTPUT_FILE, 'w').close()

log("=== bitsteam field inspector ===")
log()

try:
    from bitsteam import SteamDeck
except ImportError:
    log("ERROR: bitsteam not installed")
    log("Run: pip install bitsteam --break-system-packages")
    sys.exit(1)

log("Connecting...")
try:
    deck = SteamDeck()
    deck.start()
    log(f"Connected — device: {deck.device_path}")
except Exception as e:
    log(f"Connection failed: {e}")
    log("Check udev rule and /dev/hidraw* permissions")
    sys.exit(1)

# Let the reader thread settle
time.sleep(0.5)

log()
log("--- Analog values (sticks, triggers, trackpads) ---")
try:
    analog = deck.get_analog_values()
    log(f"Type: {type(analog)}")
    if hasattr(analog, '__dict__'):
        for k, v in vars(analog).items():
            log(f"  {k}: {v}")
    elif hasattr(analog, '_fields_'):
        for f in analog._fields_:
            log(f"  {f}: {getattr(analog, f)}")
    else:
        log(f"  raw: {analog}")
        try:
            for i, v in enumerate(analog):
                log(f"  [{i}]: {v}")
        except Exception:
            pass
except Exception as e:
    log(f"get_analog_values error: {e}")

log()
log("--- Button state ---")
try:
    buttons = deck.get_button_state()
    log(f"Type: {type(buttons)}")
    if hasattr(buttons, '__dict__'):
        for k, v in vars(buttons).items():
            log(f"  {k}: {v}")
    elif hasattr(buttons, '_fields_'):
        for f in buttons._fields_:
            log(f"  {f}: {getattr(buttons, f)}")
    else:
        log(f"  raw: {buttons}")
except Exception as e:
    log(f"get_button_state error: {e}")

log()
log("--- IMU rates (gyro/accelerometer) ---")
try:
    imu = deck.get_imu_rates()
    log(f"Type: {type(imu)}")
    if hasattr(imu, '__dict__'):
        for k, v in vars(imu).items():
            log(f"  {k}: {v}")
    elif hasattr(imu, '_fields_'):
        for f in imu._fields_:
            log(f"  {f}: {getattr(imu, f)}")
    else:
        log(f"  raw: {imu}")
        try:
            for i, v in enumerate(imu):
                log(f"  [{i}]: {v}")
        except Exception:
            pass
except Exception as e:
    log(f"get_imu_rates error: {e}")

log()
log("--- Raw attribute snapshots ---")
log(f"  deck.analog: {deck.analog}")
log(f"  deck.buttons: {deck.buttons}")
log(f"  deck.imu: {deck.imu}")

log()
log("--- Live check: press every button and tilt the Deck (15s) ---")
log("Watching for button changes and IMU movement...")

seen_buttons = set()
start = time.monotonic()
prev_buttons = deck.buttons

while time.monotonic() - start < 15:
    try:
        # Check for button changes
        curr = deck.buttons
        if curr != prev_buttons:
            log(f"  BUTTON CHANGE: {curr}")
            seen_buttons.add(str(curr))
            prev_buttons = curr

        # Check IMU
        imu = deck.get_imu_rates()
        if imu is not None:
            try:
                vals = list(imu) if hasattr(imu, '__iter__') else vars(imu).values()
                if any(abs(v) > 0.1 for v in vals if isinstance(v, (int, float))):
                    log(f"  IMU: {imu}")
            except Exception:
                pass

    except Exception as e:
        log(f"  read error: {e}")

    time.sleep(0.1)

deck.stop()

log()
log("--- Summary ---")
log(f"Button changes seen: {len(seen_buttons)}")
log("Done. Read this file at ~/DroidDeck/bitsteam_fields.txt")