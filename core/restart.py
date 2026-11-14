#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - Application restart
When launch.sh runs the app it sets DROIDDECK_SUPERVISED and relaunches
main.py whenever the app exits with RESTART_EXIT_CODE. The relaunch then
happens inside the process Steam started, so Steam keeps treating DroidDeck
as running. Started any other way, the app re-executes itself on exit.
"""

import atexit
import os
import sys

RESTART_EXIT_CODE = 75
SUPERVISOR_ENV = "DROIDDECK_SUPERVISED"

_restart_requested = False


def is_supervised() -> bool:
    return os.environ.get(SUPERVISOR_ENV) == "1"


def prepare_restart():
    """Mark the app for restart; the caller then closes the main window as normal"""
    global _restart_requested
    if _restart_requested:
        return
    _restart_requested = True
    if not is_supervised():
        argv = [sys.executable] + list(getattr(sys, "orig_argv", [sys.executable] + sys.argv)[1:])
        atexit.register(_exec_relaunch, argv)


def restart_exit_code(code: int) -> int:
    """Exit code main.py should return: the restart code when launch.sh will relaunch the app"""
    if _restart_requested and is_supervised():
        return RESTART_EXIT_CODE
    return code


def _exec_relaunch(argv):
    try:
        os.execv(sys.executable, argv)
    except Exception as e:
        print(f"Restart failed, please start DroidDeck manually: {e}")
