#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Droid battery profile shared across the GUI.

The backend owns the battery settings (hardware_config.json on the Pi) and
derives the alert thresholds and voltage range from them. The GUI asks for
the profile when the connection comes up and after a save; until then the
defaults below (a 4S lithium pack) are used.
"""

from PyQt6.QtCore import QObject, pyqtSignal

DEFAULT_PROFILE = {
    "chemistry": "lithium",
    "series": 4,
    "full_voltage": 16.8,
    "nominal_voltage": 14.8,
    "low_voltage": 14.0,
    "critical_voltage": 13.2,
    "empty_voltage": 12.0,
    "sensor_max_voltage": 16.8,
    "over_sensor_range": False,
}


class BatteryProfile(QObject):
    """Current pack thresholds; emits changed when the backend sends new ones"""

    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._profile = dict(DEFAULT_PROFILE)

    @property
    def low_voltage(self) -> float:
        return self._profile["low_voltage"]

    @property
    def critical_voltage(self) -> float:
        return self._profile["critical_voltage"]

    @property
    def full_voltage(self) -> float:
        return self._profile["full_voltage"]

    @property
    def empty_voltage(self) -> float:
        return self._profile["empty_voltage"]

    def apply(self, profile) -> bool:
        """Take a profile from the backend; returns True if anything changed"""
        if not isinstance(profile, dict):
            return False
        updated = dict(self._profile)
        for key in DEFAULT_PROFILE:
            if key in profile and profile[key] is not None:
                updated[key] = profile[key]
        if updated == self._profile:
            return False
        self._profile = updated
        self.changed.emit()
        return True


battery_profile = BatteryProfile()
