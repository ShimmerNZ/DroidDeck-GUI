#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - Simulated 3D Lidar Scene

Raycasts a convention-hall corner the way a forward-facing Unitree L2 sees it,
then thins the points to one per 5 cm cube as the backend does before
streaming, so the Lidar screen can be developed and demonstrated without
hardware and looks the same as it will with the real sensor.
Coordinates are metres in the robot frame: x right, y forward, z up.
"""

import math
from typing import Dict, List, Tuple

import numpy as np

SENSOR_POS = np.array([0.0, 0.5, 0.22])
MAX_RANGE = 15.0
DOME_HALF_ANGLE_DEG = 96.0
CAMERA_HALF_FOV_DEG = 35.0
CAMERA_MAX_RANGE = 9.0
THIN_VOXEL_M = 0.05

STATIC_BOXES = [
    ((-7.2, -4.0, 0.0), (-7.0, 10.0, 3.0)),
    ((7.0, -4.0, 0.0), (7.2, 10.0, 3.0)),
    ((-7.2, 10.0, 0.0), (7.2, 10.2, 3.0)),
    ((2.5, 3.0, 0.0), (4.5, 4.0, 1.0)),
    ((-5.0, 6.0, 0.0), (-3.5, 7.5, 2.0)),
    ((-2.5, 2.0, 0.72), (-1.0, 2.8, 0.76)),
    ((1.0, 1.4, 0.0), (1.4, 1.7, 0.25)),
]
STATIC_CYLINDERS = [
    (4.0, 7.5, 0.3, 0.0, 3.0),
    (-2.45, 2.05, 0.03, 0.0, 0.72),
    (-1.05, 2.05, 0.03, 0.0, 0.72),
    (-2.45, 2.75, 0.03, 0.0, 0.72),
    (-1.05, 2.75, 0.03, 0.0, 0.72),
    (-1.6, -2.2, 0.25, 0.0, 0.9),
]
PATHS = [
    {"a": (-4.0, 8.5), "b": (3.0, 8.5), "v": 0.8},
    {"a": (-0.6, 4.0), "b": (-0.6, 9.4), "v": 0.6},
    {"a": (5.6, 0.5), "b": (5.6, 6.2), "v": 0.7},
    {"a": (-6.0, 2.5), "b": (-3.0, -3.0), "v": 0.5},
    {"c": (1.6, 5.6), "r": 1.3, "v": 0.5},
]


def _ray_boxes(o, d, boxes):
    """Distance along each ray to the nearest of the boxes (inf if none)."""
    best = np.full(len(d), np.inf)
    with np.errstate(divide="ignore", invalid="ignore"):
        inv = 1.0 / d
    for mn, mx in boxes:
        mn, mx = np.asarray(mn), np.asarray(mx)
        with np.errstate(invalid="ignore"):
            t1 = (mn - o) * inv
            t2 = (mx - o) * inv
        parallel = d == 0
        inside = (o >= mn) & (o <= mx)
        t1 = np.where(parallel, np.where(inside, -np.inf, np.inf), t1)
        t2 = np.where(parallel, np.where(inside, np.inf, -np.inf), t2)
        tmin = np.minimum(t1, t2).max(axis=1)
        tmax = np.maximum(t1, t2).min(axis=1)
        hit = (tmax >= tmin) & (tmin > 1e-4)
        best = np.where(hit & (tmin < best), tmin, best)
    return best


def _ray_cylinders(o, d, cylinders):
    """Distance along each ray to the nearest vertical cylinder (side or top cap)."""
    best = np.full(len(d), np.inf)
    a = d[:, 0] ** 2 + d[:, 1] ** 2
    for cx, cy, r, z0, z1 in cylinders:
        ox, oy = o[0] - cx, o[1] - cy
        b = 2 * (ox * d[:, 0] + oy * d[:, 1])
        c = ox * ox + oy * oy - r * r
        disc = b * b - 4 * a * c
        with np.errstate(invalid="ignore", divide="ignore"):
            t = (-b - np.sqrt(np.maximum(disc, 0))) / (2 * a)
        z = o[2] + t * d[:, 2]
        side = (disc >= 0) & (a > 1e-12) & (t > 1e-4) & (z >= z0) & (z <= z1)
        best = np.where(side & (t < best), t, best)
        with np.errstate(divide="ignore", invalid="ignore"):
            tc = (z1 - o[2]) / d[:, 2]
        px, py = ox + tc * d[:, 0], oy + tc * d[:, 1]
        cap = (tc > 1e-4) & (px * px + py * py <= r * r)
        best = np.where(cap & (tc < best), tc, best)
    return best


class LidarSimulator:
    """Generates point cloud scans and person detections for the test scene."""

    def __init__(self):
        self._jitter = 0.0

    def _people(self, t: float) -> List[Dict]:
        people = []
        for i, p in enumerate(PATHS):
            if "c" in p:
                ang = t * p["v"] / p["r"] + i
                pos = (p["c"][0] + math.cos(ang) * p["r"], p["c"][1] + math.sin(ang) * p["r"])
                hd = (-math.sin(ang), math.cos(ang))
                s = t * p["v"]
            else:
                dx, dy = p["b"][0] - p["a"][0], p["b"][1] - p["a"][1]
                length = math.hypot(dx, dy)
                s = (t * p["v"] + i * 1.7) % (2 * length)
                f = s / length if s < length else 2 - s / length
                pos = (p["a"][0] + dx * f, p["a"][1] + dy * f)
                hd = (dx / length, dy / length) if s < length else (-dx / length, -dy / length)
            pp = (-hd[1], hd[0])
            g = 0.15 * math.sin(s * 6)
            people.append({
                "pos": pos,
                "cylinders": [
                    (pos[0] + pp[0] * 0.1 + hd[0] * g, pos[1] + pp[1] * 0.1 + hd[1] * g, 0.07, 0.0, 0.88),
                    (pos[0] - pp[0] * 0.1 - hd[0] * g, pos[1] - pp[1] * 0.1 - hd[1] * g, 0.07, 0.0, 0.88),
                    (pos[0], pos[1], 0.2, 0.88, 1.5),
                    (pos[0], pos[1], 0.11, 1.5, 1.75),
                ],
            })
        return people

    def _rays(self) -> np.ndarray:
        self._jitter = (self._jitter + 0.37) % 1.0
        min_y = math.cos(math.radians(DOME_HALF_ANGLE_DEG))
        dirs = []
        for e in range(52):
            el = math.radians(-88 + (e + self._jitter) * (176 / 52))
            ce, se = math.cos(el), math.sin(el)
            n_az = max(12, round(240 * ce))
            az = -math.pi + (np.arange(n_az) + self._jitter) * 2 * math.pi / n_az
            row = np.stack([np.sin(az) * ce, np.cos(az) * ce, np.full(n_az, se)], axis=1)
            dirs.append(row[row[:, 1] >= min_y])
        return np.concatenate(dirs)

    def scan(self, t: float) -> Tuple[np.ndarray, List[Dict]]:
        """Return (points Nx3, detections) for time t in seconds."""
        d = self._rays()
        o = SENSOR_POS
        people = self._people(t)

        best = np.minimum(_ray_boxes(o, d, STATIC_BOXES), _ray_cylinders(o, d, STATIC_CYLINDERS))
        owner = np.full(len(d), -1)
        for i, person in enumerate(people):
            tp = _ray_cylinders(o, d, person["cylinders"])
            closer = tp < best
            best = np.where(closer, tp, best)
            owner = np.where(closer, i, owner)
        with np.errstate(divide="ignore", invalid="ignore"):
            tf = np.where(d[:, 2] < -1e-6, -o[2] / d[:, 2], np.inf)
        floor_closer = tf < best
        best = np.where(floor_closer, tf, best)
        owner = np.where(floor_closer, -1, owner)

        keep = (best < MAX_RANGE) & (best > 0.05)
        points = o + d[keep] * best[keep, None]
        owner = owner[keep]
        if len(points):
            _, first = np.unique(np.floor(points / THIN_VOXEL_M).astype(np.int32), axis=0, return_index=True)
            first = np.sort(first)
            points, owner = points[first], owner[first]

        detections = []
        half_fov = math.radians(CAMERA_HALF_FOV_DEG)
        for i in range(len(people)):
            pts = points[owner == i]
            if len(pts) < 6:
                continue
            x0, y0 = pts[:, 0].min() - 0.08, pts[:, 1].min() - 0.08
            x1, y1 = pts[:, 0].max() + 0.08, pts[:, 1].max() + 0.08
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            dist = math.hypot(cx, cy)
            in_camera = abs(math.atan2(cx, cy)) < half_fov and dist < CAMERA_MAX_RANGE
            detections.append({
                "box": (x0, y0, x1, y1, float(pts[:, 2].max())),
                "distance": dist,
                "label": "PERSON" if in_camera else "UNKNOWN",
            })
        return points.astype(np.float32), detections
