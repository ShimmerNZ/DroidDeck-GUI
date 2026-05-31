#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bitsteam field inspector for DroidDeck
Connects to /dev/hidraw2, reads a few frames, and prints every
field name and its current value so we can map them precisely
into steamdeck.py and controller_config.json.

Run inside Distrobox:
    python3 inspect_bitsteam_fields.py
"""

import time
from bitsteam import SteamDeck


def inspect(state):
    """Print every non-private attribute and its value"""
    fields = {
        k: getattr(state, k)
        for k in dir(state)
        if not k.startswith('_') and not callable(getattr(state, k))
    }
    return fields


def main():
    print("Connecting to Steam Deck HID device...")
    try:
        deck = SteamDeck()
    except Exception as e:
        print(f"Connection failed: {e}")
        print("Make sure the udev rule is applied and /dev/hidraw2 is readable.")
        return

    print("Connected. Reading 3 frames to capture field names...\n")

    # Grab a few frames so any lazy-initialised fields are populated
    state = None
    for _ in range(10):
        s = deck.get_state()
        if s is not None:
            state = s
        time.sleep(0.05)

    if state is None:
        print("No state received. Is the controller active?")
        deck.close()
        return

    fields = inspect(state)

    # Group by likely category for readability
    sticks    = {k: v for k, v in fields.items() if 'stick' in k or 'joystick' in k}
    triggers  = {k: v for k, v in fields.items() if 'trigger' in k}
    imu       = {k: v for k, v in fields.items() if any(x in k for x in
                 ('pitch', 'yaw', 'roll', 'accel', 'gyro', 'imu', 'angular', 'gravity'))}
    buttons   = {k: v for k, v in fields.items() if 'btn' in k or 'button' in k or 'press' in k}
    pads      = {k: v for k, v in fields.items() if 'pad' in k or 'touch' in k}
    other     = {k: v for k, v in fields.items()
                 if k not in sticks and k not in triggers and k not in imu
                 and k not in buttons and k not in pads}

    def show(label, d):
        if not d:
            return
        print(f"--- {label} ---")
        for k, v in sorted(d.items()):
            print(f"  {k:<30} = {v!r}")
        print()

    show("Sticks", sticks)
    show("Triggers", triggers)
    show("IMU (gyro / accelerometer)", imu)
    show("Buttons", buttons)
    show("Trackpads", pads)
    show("Other", other)

    # Now hold for 10 seconds and report any button presses or large IMU readings
    print("--- Live check: press every button and tilt the Deck (10s) ---\n")
    seen_buttons = set()
    start = time.monotonic()
    while time.monotonic() - start < 10:
        s = deck.get_state()
        if s is None:
            time.sleep(0.02)
            continue

        live = inspect(s)

        # Report buttons that just became True
        for k, v in live.items():
            if ('btn' in k or 'button' in k) and v and k not in seen_buttons:
                print(f"  BUTTON PRESSED: {k}")
                seen_buttons.add(k)

        # Report significant IMU movement
        for k in ('pitch', 'yaw', 'roll'):
            if k in live and abs(live[k]) > 5:
                print(f"  IMU {k}: {live[k]:.2f}")

        time.sleep(0.02)

    deck.close()
    print(f"\nButtons observed during live check: {sorted(seen_buttons)}")
    print("\nCopy these field names — they're what goes into the steamdeck.py migration.")


if __name__ == '__main__':
    main()
