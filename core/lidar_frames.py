#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - Lidar Frame Decoding and Person Detection

Decodes the binary point frames streamed by the backend lidar receiver and
finds person-shaped clusters in them. Points are metres in the robot frame:
x right, y forward, z up, origin on the floor under the robot centre.
"""

import math
import struct
import zlib
from typing import Dict, List, Optional, Tuple

import numpy as np

FRAME_MAGIC = b"LDR1"
FRAME_HEADER = struct.Struct("<4sIdIH2x")   # magic, seq, stamp, point count, flags
FLAG_ZLIB = 1

CELL_M = 0.15
MIN_Z_M = 0.05
MAX_Z_M = 2.6
PERSON_MIN_HEIGHT_M = 1.0
PERSON_MAX_HEIGHT_M = 2.1
PERSON_MIN_WIDTH_M = 0.15
PERSON_MAX_WIDTH_M = 0.9
PERSON_MAX_FOOT_Z_M = 0.6
PERSON_MIN_POINTS = 6


def decode_frame(data: bytes) -> Optional[Tuple[int, float, np.ndarray]]:
    """(sequence, timestamp, points Nx3 in metres) from one binary frame, or None if it isn't one."""
    if len(data) < FRAME_HEADER.size:
        return None
    magic, seq, stamp, count, flags = FRAME_HEADER.unpack_from(data)
    if magic != FRAME_MAGIC:
        return None
    payload = data[FRAME_HEADER.size:]
    if flags & FLAG_ZLIB:
        payload = zlib.decompress(payload)
    pts = np.frombuffer(payload, dtype="<i2", count=count * 3).reshape(-1, 3).astype(np.float32) / 1000.0
    return seq, stamp, pts


def detect_people(points: np.ndarray, bearings_deg: Optional[List[float]] = None,
                  match_deg: float = 12.0) -> List[Dict]:
    """Person-shaped clusters: narrow, 1.0-2.1 m tall columns that reach the floor.

    Clusters are labelled PERSON when a camera person lies within match_deg of
    their bearing, otherwise UNKNOWN. A person standing against a wall merges
    with it and is not reported.
    """
    if points is None or len(points) == 0:
        return []
    pts = points[(points[:, 2] > MIN_Z_M) & (points[:, 2] < MAX_Z_M)]
    if len(pts) == 0:
        return []

    cells = np.floor(pts[:, :2] / CELL_M).astype(np.int64)
    keys, inverse, counts = np.unique(cells, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.reshape(-1)
    zmax = np.full(len(keys), -np.inf)
    zmin = np.full(len(keys), np.inf)
    np.maximum.at(zmax, inverse, pts[:, 2])
    np.minimum.at(zmin, inverse, pts[:, 2])

    index = {(int(k[0]), int(k[1])): i for i, k in enumerate(keys)}
    seen = np.zeros(len(keys), dtype=bool)
    detections = []
    for start in range(len(keys)):
        if seen[start]:
            continue
        component, stack = [], [start]
        seen[start] = True
        while stack:
            i = stack.pop()
            component.append(i)
            kx, ky = int(keys[i][0]), int(keys[i][1])
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    j = index.get((kx + dx, ky + dy))
                    if j is not None and not seen[j]:
                        seen[j] = True
                        stack.append(j)

        comp = np.array(component)
        cx0, cy0 = keys[comp, 0].min() * CELL_M, keys[comp, 1].min() * CELL_M
        cx1, cy1 = (keys[comp, 0].max() + 1) * CELL_M, (keys[comp, 1].max() + 1) * CELL_M
        width = max(cx1 - cx0, cy1 - cy0)
        top = float(zmax[comp].max())
        if not (PERSON_MIN_WIDTH_M <= width <= PERSON_MAX_WIDTH_M):
            continue
        if not (PERSON_MIN_HEIGHT_M <= top <= PERSON_MAX_HEIGHT_M):
            continue
        if zmin[comp].min() > PERSON_MAX_FOOT_Z_M or counts[comp].sum() < PERSON_MIN_POINTS:
            continue

        cx, cy = (cx0 + cx1) / 2, (cy0 + cy1) / 2
        label = "UNKNOWN"
        if bearings_deg:
            bearing = math.degrees(math.atan2(cx, cy))
            if min(abs(bearing - b) for b in bearings_deg) <= match_deg:
                label = "PERSON"
        detections.append({
            "box": (cx0, cy0, cx1, cy1, top),
            "distance": math.hypot(cx, cy),
            "label": label,
        })
    return detections
