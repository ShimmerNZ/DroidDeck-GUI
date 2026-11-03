#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - GUI version information
The installed branch and commit come from version_info.json, written by the
in-app updater, or from the git checkout when running from a clone.
"""

import json
from pathlib import Path

GUI_VERSION = "1.0"
VERSION_INFO_FILE = "version_info.json"

APP_ROOT = Path(__file__).resolve().parent.parent


def _read_version_file() -> dict:
    try:
        with open(APP_ROOT / VERSION_INFO_FILE, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _read_git_checkout() -> dict:
    """Branch and commit from a .git folder, without running git"""
    git_dir = APP_ROOT / ".git"
    try:
        head = (git_dir / "HEAD").read_text().strip()
    except OSError:
        return {}
    if not head.startswith("ref:"):
        return {"branch": "detached", "commit": head}
    ref = head.split(":", 1)[1].strip()
    branch = ref.rsplit("/", 1)[-1]
    try:
        return {"branch": branch, "commit": (git_dir / ref).read_text().strip()}
    except OSError:
        pass
    try:
        for line in (git_dir / "packed-refs").read_text().splitlines():
            parts = line.strip().split(" ")
            if len(parts) == 2 and parts[1] == ref:
                return {"branch": branch, "commit": parts[0]}
    except OSError:
        pass
    return {"branch": branch}


def get_build_info() -> dict:
    """{'version', 'branch', 'commit'} for the running GUI"""
    info = _read_version_file() or _read_git_checkout()
    return {
        "version": GUI_VERSION,
        "branch": info.get("branch", ""),
        "commit": (info.get("commit") or "")[:7],
    }


def get_build_label() -> str:
    """'main @ 1b7db32', or 'unknown build' before the first in-app update"""
    info = get_build_info()
    if info["branch"] and info["commit"]:
        return f"{info['branch']} @ {info['commit']}"
    if info["commit"]:
        return info["commit"]
    return "unknown build"


def save_build_info(app_root: Path, branch: str, commit: str):
    """Record the branch and commit an update installed"""
    import time
    data = {"branch": branch, "commit": commit, "updated": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(Path(app_root) / VERSION_INFO_FILE, "w") as f:
        json.dump(data, f, indent=2)
