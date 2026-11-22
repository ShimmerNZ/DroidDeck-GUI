#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - 3D Lidar Surroundings Screen

Shows the point cloud from the forward-facing Unitree L2 as a 3D scene with
WALL-E in the middle. Static returns are drawn as glowing blocks, the floor as
points, and tracked people as walking figures with trails and labels. TEST
DATA feeds the view from a simulated scene so it can be checked without the
robot.
"""

import math
import os
import time
from collections import deque
from typing import Dict, List, Optional

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QBrush, QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                         QMatrix4x4, QPolygonF, QRadialGradient, QVector2D, QVector3D)
from PyQt6.QtOpenGL import (QOpenGLBuffer, QOpenGLFramebufferObject, QOpenGLShader, QOpenGLShaderProgram, QOpenGLVersionFunctionsFactory,
                            QOpenGLVersionProfile, QOpenGLVertexArrayObject)
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.logger import get_logger
from core.lidar_frames import FRAME_MAGIC, decode_frame, detect_people
from core.lidar_sim import DOME_HALF_ANGLE_DEG, SENSOR_POS, LidarSimulator
from core.theme_manager import theme_manager
from widgets.base_screen import BaseScreen
from widgets.camera_screen import CARD_OBJECT_NAME, button_style, card_style, px_font

CARD_WIDTH = 1061
CARD_HEIGHT = 516
CARD_PADDING = 6
HEADER_HEIGHT = 30
HEADER_INSET = 8

MODEL_PATH = "resources/models/robot.obj"
MODEL_UP_AXIS = "z"
MODEL_YAW_DEG = 180.0
MODEL_MAX_TRIANGLES = 3000
MODEL_MAX_TRIANGLES_GL = 200000
MODEL_DEFAULT_COLOUR = (0.78, 0.67, 0.43)
USE_OPENGL = True

FRAME_INTERVAL_MS = 16
SCAN_INTERVAL_S = 0.1
SCAN_HISTORY = 3
DEFAULT_DISTANCE = 9.6
DEFAULT_PITCH = 0.49
FIELD_OF_VIEW_DEG = 60.0
DRIFT_AMPLITUDE = 0.55
DRIFT_SPEED = 0.18
CAMERA_EASE = 0.08
VIEW_PRESETS = {
    "chase": {"target": (0.0, 3.2, 0.7), "pitch": 0.49, "distance": 9.6},
    "top": {"target": (0.0, 3.5, 0.0), "pitch": 1.3, "distance": 13.0},
    "eye": {"pitch": 0.12},
}
VIEW_ORDER = ("chase", "top", "eye")
HEAD_POS = np.array([0.0, 0.15, 0.82])
CAMERA_HFOV_DEG = 66.0
ATTENTION_MATCH_DEG = 12.0
ATTENTION_TIMEOUT_S = 1.5
PROXIMITY_RANGE_M = 1.2
PROXIMITY_DANGER_M = 0.5
PROXIMITY_SECTORS = 48
ROBOT_RADIUS_M = 0.55
LIVE_TIMEOUT_S = 3.0
LIVE_DETECT_FRAMES = 3

FLOOR_HEIGHT = 0.06
VOXEL_SIZE = 0.2
VOXEL_LIFETIME_S = 1.5
FOG_NEAR_M = 2.5
FOG_RANGE_M = 13.0
FOG_FLOOR = 0.28
TRACK_MATCH_M = 0.8
TRACK_TIMEOUT_S = 1.0
TRAIL_SECONDS = 3.0
POP_SECONDS = 0.8
GLOW_DOWNSAMPLE = 4
GLOW_STRENGTH = 0.15
TIMING_LOG_INTERVAL_S = 3.0

PALETTES = {
    "cyan": {
        "ramp": [(40, 70, 90), (60, 140, 190), (95, 211, 255), (190, 235, 255), (255, 255, 255)],
        "block": (120, 200, 255), "person": (73, 209, 122), "unknown": (242, 178, 51),
        "accent": (140, 220, 255), "fog": (5, 9, 12), "bg": ("#081016", "#030507"),
        "grid": QColor(90, 160, 190, 23),
    },
    "amber": {
        "ramp": [(70, 45, 20), (150, 90, 30), (225, 160, 20), (245, 200, 90), (255, 230, 160)],
        "block": (225, 160, 20), "person": (110, 230, 200), "unknown": (255, 140, 60),
        "accent": (255, 190, 80), "fog": (12, 9, 5), "bg": ("#0d0a06", "#050403"),
        "grid": QColor(225, 160, 20, 20),
    },
}
PALETTE = PALETTES["cyan"]
BLIND_COL = (232, 64, 42)


def _read_mtl_colours(path: str) -> Dict[str, tuple]:
    """Material name -> diffuse colour (Kd, 0-1) from an MTL file."""
    colours, name = {}, None
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            parts = line.strip().split(None, 1)
            if not parts:
                continue
            if parts[0] == "newmtl" and len(parts) > 1:
                name = parts[1].strip()
            elif parts[0] == "Kd" and name is not None and len(parts) > 1:
                colours[name] = tuple(float(x) for x in parts[1].split()[:3])
    return colours


def load_obj_mesh(path: str, max_triangles: int = MODEL_MAX_TRIANGLES) -> Optional[Dict]:
    """Load an OBJ with its material colours, convert to the robot frame, scale to metres and simplify."""
    if not os.path.exists(path):
        return None
    verts, faces, face_mtl, names = [], [], [], [None]
    current, mtllib = 0, None
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("v "):
                parts = line.split()
                verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
            elif line.startswith("f "):
                idx = []
                for tok in line.split()[1:]:
                    i = int(tok.split("/")[0])
                    idx.append(i - 1 if i > 0 else len(verts) + i)
                for k in range(1, len(idx) - 1):
                    faces.append((idx[0], idx[k], idx[k + 1]))
                    face_mtl.append(current)
            elif line.startswith("usemtl"):
                name = line[6:].strip()
                if name not in names:
                    names.append(name)
                current = names.index(name)
            elif line.startswith("mtllib") and mtllib is None:
                mtllib = line[6:].strip()
    if not verts or not faces:
        return None

    table = {}
    for candidate in ([os.path.join(os.path.dirname(path), mtllib)] if mtllib else []) + [os.path.splitext(path)[0] + ".mtl"]:
        if os.path.exists(candidate):
            table = _read_mtl_colours(candidate)
            break
    palette = np.array([table.get(n, MODEL_DEFAULT_COLOUR) if n else MODEL_DEFAULT_COLOUR for n in names])
    colours = palette[np.array(face_mtl, dtype=np.int64)]

    v = np.array(verts, dtype=np.float64)
    if MODEL_UP_AXIS == "y":
        v = np.stack([v[:, 0], -v[:, 2], v[:, 1]], axis=1)
    yaw = math.radians(MODEL_YAW_DEG)
    c, s = math.cos(yaw), math.sin(yaw)
    v = np.stack([v[:, 0] * c - v[:, 1] * s, v[:, 0] * s + v[:, 1] * c, v[:, 2]], axis=1)

    height = v[:, 2].max() - v[:, 2].min()
    if 0.4 < height < 3:
        scale = 1.0
    elif 40 <= height < 300:
        scale = 0.01
    elif 400 <= height < 3000:
        scale = 0.001
    else:
        scale = 1.1 / height
    centre = (v.min(axis=0) + v.max(axis=0)) / 2
    v = (v - np.array([centre[0], centre[1], v[:, 2].min()])) * scale

    f = np.array(faces, dtype=np.int64)
    cell = (height * scale) / 60
    for _ in range(10):
        if len(f) <= max_triangles:
            break
        keys = np.round(v / cell).astype(np.int64)
        _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
        inverse = inverse.reshape(-1)
        nf = inverse[f]
        ok = (nf[:, 0] != nf[:, 1]) & (nf[:, 1] != nf[:, 2]) & (nf[:, 0] != nf[:, 2])
        nf, nc = nf[ok], colours[ok]
        _, rows = np.unique(np.sort(nf, axis=1), axis=0, return_index=True)
        rows = np.sort(rows)
        v, f, colours = v[first], nf[rows], nc[rows]
        cell *= 1.4

    a, b, cc = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    n = np.cross(b - a, cc - a)
    norm = np.linalg.norm(n, axis=1)
    valid = norm > 1e-12
    light = np.array([0.4, -0.6, 0.8]) / np.linalg.norm([0.4, -0.6, 0.8])
    shade = 0.35 + 0.65 * np.abs((n[valid] / norm[valid, None]) @ light)
    return {"vertices": v, "faces": f[valid], "shade": shade, "colours": colours[valid]}


def _rgb(c, alpha: int = 255) -> QColor:
    return QColor(int(c[0]), int(c[1]), int(c[2]), int(max(0, min(255, alpha))))


def _fog(xy: np.ndarray) -> np.ndarray:
    """Brightness factor by horizontal distance from the sensor: 1 close by, fading with range."""
    d = np.hypot(xy[..., 0] - SENSOR_POS[0], xy[..., 1] - SENSOR_POS[1])
    return np.clip(1 - (d - FOG_NEAR_M) / FOG_RANGE_M, FOG_FLOOR, 1.0)


def _mix_fog(rgb: np.ndarray, k: np.ndarray) -> np.ndarray:
    fog = np.array(PALETTE["fog"], dtype=np.float64)
    return fog + (rgb - fog) * k[..., None]


def _ramp(z: np.ndarray) -> np.ndarray:
    """Colour by height from the palette ramp (0 to 2 m)."""
    ramp = np.array(PALETTE["ramp"], dtype=np.float64)
    t = np.clip(z / 2.0, 0, 0.999) * (len(ramp) - 1)
    i = t.astype(int)
    f = (t - i)[:, None]
    return ramp[i] + (ramp[i + 1] - ramp[i]) * f


def _splat(buf: np.ndarray, flat_index: np.ndarray, rgb: np.ndarray):
    """Add colours into an (H, W, 3) buffer at flattened pixel indices."""
    if len(flat_index) == 0:
        return
    size = buf.shape[0] * buf.shape[1]
    view = buf.reshape(-1, 3)
    for ch in range(3):
        view[:, ch] += np.bincount(flat_index, weights=rgb[:, ch], minlength=size).astype(np.float32)


class PersonTrack:
    """A tracked mover: smoothed heading, walking speed, gait phase and trail."""

    def __init__(self, track_id: int, centre, now: float):
        self.id = track_id
        self.centre = np.array(centre, dtype=np.float64)
        self.heading = np.array([0.0, 1.0])
        self.speed = 0.0
        self.phase = 0.0
        self.first_seen = now
        self.last_seen = now
        self.trail: deque = deque()
        self.detection: Dict = {}

    def update(self, detection: Dict, now: float):
        x0, y0, x1, y1, _ = detection["box"]
        self.centre = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
        self.detection = detection
        self.last_seen = now
        self.trail.append((self.centre[0], self.centre[1], now))
        while self.trail and now - self.trail[0][2] > TRAIL_SECONDS:
            self.trail.popleft()
        if len(self.trail) > 2:
            a, b = self.trail[max(0, len(self.trail) - 5)], self.trail[-1]
            dx, dy = b[0] - a[0], b[1] - a[1]
            dist = math.hypot(dx, dy)
            dt = max(0.05, b[2] - a[2])
            self.speed += (dist / dt - self.speed) * 0.2
            if dist > 0.03:
                h = self.heading * 0.8 + np.array([dx, dy]) / dist * 0.2
                self.heading = h / max(1e-6, np.linalg.norm(h))


class LidarSceneMixin:
    """Scan data, tracking, camera and the QPainter overlay shared by both lidar views."""

    def _init_scene(self, model_triangles: int = MODEL_MAX_TRIANGLES):
        self.scans: deque = deque(maxlen=SCAN_HISTORY)
        self.voxels: Dict[tuple, float] = {}
        self.tracks: Dict[int, PersonTrack] = {}
        self._next_track = 0
        self.simulated = False
        self.last_scan_time = -10.0
        self.preset = "chase"
        self.target = np.array(VIEW_PRESETS["chase"]["target"])
        self.yaw_offset = 0.0
        self.pitch = DEFAULT_PITCH
        self.distance = DEFAULT_DISTANCE
        self.auto_sway = True
        self._yaw = 0.0
        self._drag_pos: Optional[QPointF] = None
        self.focus_track: Optional[int] = None
        self.proximity = np.full(PROXIMITY_SECTORS, np.inf)
        self._start = time.monotonic()
        self._last_frame = self._start
        self._layer_cache = None
        self.logger = get_logger("lidar_view")
        self._timings: Dict[str, float] = {}
        self._timed_frames = 0
        self._last_timing_log = self._start
        self.frame_times: deque = deque(maxlen=30)
        self.model = None
        try:
            self.model = load_obj_mesh(MODEL_PATH, model_triangles)
        except Exception:
            self.model = None

    # ---------- data ----------

    def set_scan(self, points: np.ndarray, detections: List[Dict], simulated: bool = False):
        now = time.monotonic()
        self.simulated = simulated
        self.last_scan_time = now
        pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)

        in_person = np.zeros(len(pts), dtype=bool)
        for det in detections:
            x0, y0, x1, y1, top = det["box"]
            in_person |= ((pts[:, 0] >= x0) & (pts[:, 0] <= x1) & (pts[:, 1] >= y0) & (pts[:, 1] <= y1)
                          & (pts[:, 2] <= top + 0.1))
        floor = (pts[:, 2] < FLOOR_HEIGHT) & ~in_person
        static = ~floor & ~in_person
        self.scans.append({"floor": pts[floor], "person": pts[in_person]})

        self.proximity = np.full(PROXIMITY_SECTORS, np.inf)
        near = pts[static]
        if len(near):
            dist = np.hypot(near[:, 0], near[:, 1])
            close = dist < ROBOT_RADIUS_M + PROXIMITY_RANGE_M
            if close.any():
                ang = np.arctan2(near[close, 0], near[close, 1])
                sector = ((ang + math.pi) / (2 * math.pi) * PROXIMITY_SECTORS).astype(int) % PROXIMITY_SECTORS
                np.minimum.at(self.proximity, sector, dist[close] - ROBOT_RADIUS_M)

        if static.any():
            keys = np.unique(np.floor(pts[static] / VOXEL_SIZE).astype(np.int32), axis=0)
            for k in map(tuple, keys):
                self.voxels[k] = now
        self.voxels = {k: t for k, t in self.voxels.items() if now - t <= VOXEL_LIFETIME_S}

        self._update_tracks(detections, now)

    def _update_tracks(self, detections: List[Dict], now: float):
        unmatched = set(self.tracks)
        for det in detections:
            x0, y0, x1, y1, _ = det["box"]
            centre = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
            best, best_d = None, TRACK_MATCH_M
            for tid in unmatched:
                d = float(np.linalg.norm(self.tracks[tid].centre - centre))
                if d < best_d:
                    best, best_d = tid, d
            if best is None:
                best = self._next_track
                self._next_track += 1
                self.tracks[best] = PersonTrack(best, centre, now)
            else:
                unmatched.discard(best)
            self.tracks[best].update(det, now)
        for tid in list(self.tracks):
            if now - self.tracks[tid].last_seen > TRACK_TIMEOUT_S:
                del self.tracks[tid]

    def clear(self):
        self.scans.clear()
        self.voxels.clear()
        self.tracks.clear()
        self.simulated = False
        self.update()

    def tracked_count(self) -> int:
        return len(self.tracks)

    # ---------- camera ----------

    def reset_view(self):
        preset = VIEW_PRESETS[self.preset]
        self.yaw_offset = 0.0
        self.pitch = preset["pitch"]
        if self.preset != "eye":
            self.distance = preset["distance"]
            self.target = np.array(preset["target"])
        self.auto_sway = True
        self.update()

    def next_view(self) -> str:
        self.preset = VIEW_ORDER[(VIEW_ORDER.index(self.preset) + 1) % len(VIEW_ORDER)]
        self.reset_view()
        return self.preset

    def _point_kinds(self):
        """Floor returns form rings around the sensor that look like ripples from the eye view, so hide them there."""
        return ("person",) if self.preset == "eye" else ("floor", "person")

    def set_focus(self, track_id: Optional[int]):
        self.focus_track = track_id

    def mousePressEvent(self, event):
        self._drag_pos = event.position()
        self.auto_sway = False

    def mouseMoveEvent(self, event):
        if self._drag_pos is None:
            return
        delta = event.position() - self._drag_pos
        self._drag_pos = event.position()
        self.yaw_offset += delta.x() * 0.006
        if self.preset == "eye":
            self.pitch = min(0.6, max(-0.3, self.pitch + delta.y() * 0.003))
        else:
            self.pitch = min(1.35, max(0.12, self.pitch + delta.y() * 0.004))
        self.update()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        self.reset_view()

    def wheelEvent(self, event):
        if self.preset == "eye":
            return
        step = 0.9 if event.angleDelta().y() > 0 else 1.1
        self.distance = min(20.0, max(3.5, self.distance * step))
        self.auto_sway = False
        self.update()

    def _camera(self, t: float):
        sway = DRIFT_AMPLITUDE * math.sin(t * DRIFT_SPEED) if self.auto_sway else 0.0
        if self.preset == "eye":
            sway *= 0.4
        goal = self.yaw_offset + sway
        self._yaw += (goal - self._yaw) * CAMERA_EASE
        if self.preset == "eye":
            pos = HEAD_POS.astype(np.float64)
            fwd = np.array([math.sin(self._yaw) * math.cos(self.pitch), math.cos(self._yaw) * math.cos(self.pitch),
                            -math.sin(self.pitch)])
        else:
            horizontal = self.distance * math.cos(self.pitch)
            pos = self.target + np.array([math.sin(self._yaw) * horizontal, -math.cos(self._yaw) * horizontal,
                                          self.distance * math.sin(self.pitch)])
            fwd = self.target - pos
        fwd = fwd / np.linalg.norm(fwd)
        right = np.cross(fwd, [0.0, 0.0, 1.0])
        right /= np.linalg.norm(right)
        up = np.cross(right, fwd)
        focal = (self.height() / 2) / math.tan(math.radians(FIELD_OF_VIEW_DEG) / 2)
        return pos, fwd, right, up, focal

    def _project(self, cam, pts: np.ndarray):
        """Screen x, y, depth, pixels-per-metre and validity for an (N, 3) array."""
        pos, fwd, right, up, focal = cam
        v = pts - pos
        z = v @ fwd
        valid = z > 0.2
        zs = np.where(valid, z, 1.0)
        sx = self.width() / 2 + (v @ right) / zs * focal
        sy = self.height() / 2 - (v @ up) / zs * focal
        return sx, sy, z, focal / zs, valid

    def _p1(self, cam, p):
        sx, sy, z, scale, valid = self._project(cam, np.array([p], dtype=np.float64))
        return (sx[0], sy[0], z[0], scale[0]) if valid[0] else None

    # ---------- drawing helpers ----------

    def _polyline(self, painter: QPainter, cam, pts: np.ndarray):
        sx, sy, _, _, valid = self._project(cam, pts)
        path = QPainterPath()
        pen_down = False
        for x, y, ok in zip(sx, sy, valid):
            if not ok:
                pen_down = False
                continue
            if pen_down:
                path.lineTo(x, y)
            else:
                path.moveTo(x, y)
                pen_down = True
        painter.drawPath(path)

    def _floor_polygon(self, painter: QPainter, cam, pts: np.ndarray, fill: Optional[QColor], edge: QColor,
                       width: float = 1.0):
        sx, sy, _, _, valid = self._project(cam, pts)
        if not valid.all():
            return
        painter.setPen(QPen(edge, width))
        painter.setBrush(fill if fill is not None else Qt.BrushStyle.NoBrush)
        painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in zip(sx, sy)]))
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_box(self, painter: QPainter, cam, mn, mx, top_fill: QColor, side_fill: QColor, edge: QColor):
        corners = np.array([[mn[0], mn[1], mn[2]], [mx[0], mn[1], mn[2]], [mx[0], mx[1], mn[2]], [mn[0], mx[1], mn[2]],
                            [mn[0], mn[1], mx[2]], [mx[0], mn[1], mx[2]], [mx[0], mx[1], mx[2]], [mn[0], mx[1], mx[2]]])
        sx, sy, z, _, valid = self._project(cam, corners)
        if not valid.all():
            return
        faces = [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)]
        painter.setPen(QPen(edge, 1))
        for face in sorted(faces, key=lambda fc: -sum(z[i] for i in fc)):
            painter.setBrush(top_fill if face[0] == 4 else side_fill)
            painter.drawPolygon(QPolygonF([QPointF(sx[i], sy[i]) for i in face]))
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _label(self, painter: QPainter, x: float, y: float, text: str, colour: QColor, leader: bool = False):
        if leader:
            line = QColor(colour)
            line.setAlpha(150)
            painter.setPen(QPen(line, 1))
            painter.drawLine(QPointF(x, y), QPointF(x, y - 18))
            y -= 18
        font = QFont("Arial")
        font.setPixelSize(13)
        font.setBold(True)
        painter.setFont(font)
        w = painter.fontMetrics().horizontalAdvance(text) + 14
        rect = QRectF(x - w / 2, y - 22, w, 20)
        painter.setPen(QPen(colour, 1.5))
        painter.setBrush(QColor(10, 12, 13, 217))
        painter.drawRoundedRect(rect, 5, 5)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    # ---------- layers ----------

    def _cached_layers(self):
        """Background gradient and vignette, rendered once per widget size."""
        size = (self.width(), self.height())
        if self._layer_cache is None or self._layer_cache[0] != size:
            w, h = size
            bg = QPixmap(w, h)
            p = QPainter(bg)
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0, QColor(PALETTE["bg"][0]))
            grad.setColorAt(1, QColor(PALETTE["bg"][1]))
            p.fillRect(0, 0, w, h, QBrush(grad))
            p.end()
            vig = QPixmap(w, h)
            vig.fill(Qt.GlobalColor.transparent)
            p = QPainter(vig)
            rad = QRadialGradient(w / 2, h / 2, w * 0.62)
            rad.setColorAt(0.0, QColor(0, 0, 0, 0))
            rad.setColorAt(min(0.95, h * 0.35 / (w * 0.62)), QColor(0, 0, 0, 0))
            rad.setColorAt(1.0, QColor(0, 0, 0, 178))
            p.fillRect(0, 0, w, h, QBrush(rad))
            p.end()
            self._layer_cache = (size, bg, vig)
        return self._layer_cache[1], self._layer_cache[2]

    def _draw_trails_and_rings(self, painter: QPainter, cam, now: float):
        for tr in self.tracks.values():
            rgb = PALETTE["person"] if tr.detection.get("label") == "PERSON" else PALETTE["unknown"]
            pts = list(tr.trail)
            for i in range(1, len(pts)):
                a = self._p1(cam, (pts[i - 1][0], pts[i - 1][1], 0))
                b = self._p1(cam, (pts[i][0], pts[i][1], 0))
                if a and b:
                    painter.setPen(QPen(_rgb(rgb, 255 * 0.6 * i / len(pts)), 2.5))
                    painter.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))
            ang = np.linspace(0, 2 * math.pi, 41)
            ring = np.stack([tr.centre[0] + np.cos(ang) * 0.38, tr.centre[1] + np.sin(ang) * 0.38, np.zeros(41)], axis=1)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            self._floor_polygon(painter, cam, ring, _rgb(rgb, 30), _rgb(rgb, 230), 2)
            pulse = now - tr.first_seen
            if pulse < POP_SECONDS:
                r = 0.38 + pulse * 1.2
                ring = np.stack([tr.centre[0] + np.cos(ang) * r, tr.centre[1] + np.sin(ang) * r, np.zeros(41)], axis=1)
                self._floor_polygon(painter, cam, ring, None, _rgb(rgb, 205 * (1 - pulse / POP_SECONDS)), 2)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    def _draw_figure(self, painter: QPainter, cam, tr: PersonTrack, dt: float):
        tr.phase += dt * tr.speed * 5.5
        rgb = PALETTE["person"] if tr.detection.get("label") == "PERSON" else PALETTE["unknown"]
        f = tr.heading
        side = np.array([f[1], -f[0]])
        c = tr.centre
        stride = min(1.0, tr.speed / 0.4)
        swing = stride * 0.5 * math.sin(tr.phase)
        bob = abs(math.sin(tr.phase)) * 0.03 * stride
        hip_z, sh_z = 0.9 + bob, 1.38 + bob

        def at(sd, fw, z):
            return (c[0] + side[0] * sd + f[0] * fw, c[1] + side[1] * sd + f[1] * fw, z)

        parts = []
        for s in (-1, 1):
            a = swing * s
            hip = at(0.1 * s, 0, hip_z)
            knee = at(0.1 * s, math.sin(a) * 0.45, hip_z - math.cos(a) * 0.45)
            foot = at(0.1 * s, math.sin(a) * 0.45 + math.sin(a * 0.4) * 0.42, 0.04)
            parts += [(hip, knee, 0.075), (knee, foot, 0.065)]
            b = -swing * s * 0.9
            shoulder = at(0.21 * s, 0, sh_z)
            elbow = at(0.25 * s, math.sin(b) * 0.28, sh_z - math.cos(b) * 0.28)
            hand = at(0.26 * s, math.sin(b) * 0.28 + math.sin(b + 0.35) * 0.27,
                      sh_z - 0.28 - math.cos(b + 0.35) * 0.27)
            parts += [(shoulder, elbow, 0.055), (elbow, hand, 0.05)]
        parts.append((at(0, 0, hip_z - 0.02), at(0, 0.02, sh_z), 0.17))
        head = at(0, 0.03, sh_z + 0.27)
        parts.append((head, head, 0.155))

        projected = []
        for a, b, r in parts:
            pa, pb = self._p1(cam, a), self._p1(cam, b)
            if pa and pb:
                projected.append(((pa[2] + pb[2]) / 2, pa, pb, r))
        projected.sort(key=lambda item: -item[0])

        dark = tuple(int(v * 0.55) for v in rgb)
        light = tuple(min(255, v + 40) for v in rgb)
        for _, pa, pb, r in projected:
            w = max(2.0, (pa[3] + pb[3]) / 2 * r * 2)
            a_pt, b_pt = QPointF(pa[0], pa[1]), QPointF(pb[0] + 0.01, pb[1])
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            pen = QPen(_rgb(rgb, 46), w + 6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(a_pt, b_pt)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            pen = QPen(_rgb(dark, 242), w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(a_pt, b_pt)
            off = w * 0.12
            pen = QPen(_rgb(light, 217), max(1.0, w * 0.45))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(pa[0] - off, pa[1] - off), QPointF(pb[0] - off + 0.01, pb[1] - off))

        top = self._p1(cam, (c[0], c[1], 1.78))
        if top:
            det = tr.detection
            label = "PERSON" if det.get("label") == "PERSON" else "UNKNOWN"
            self._label(painter, top[0], top[1] - 4, f"{label} {det.get('distance', 0):.1f} m", _rgb(rgb), leader=True)

    def _draw_overlay(self, painter: QPainter):
        painter.drawPixmap(0, 0, self._cached_layers()[1])

        font = QFont("Arial")
        font.setPixelSize(12)
        painter.setFont(font)
        legend = [(_rgb(PALETTE["person"]), "Person (camera confirmed)"), (_rgb(PALETTE["unknown"]), "Unknown mover"),
                  (_rgb(BLIND_COL), "Behind sensor")]
        box = QRectF(10, self.height() - 74, 200, 64)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(10, 12, 13, 204))
        painter.drawRoundedRect(box, 8, 8)
        for i, (colour, text) in enumerate(legend):
            y = box.top() + 16 + i * 18
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            painter.drawEllipse(QPointF(box.left() + 14, y), 5, 5)
            painter.setPen(QColor(216, 212, 200))
            painter.drawText(QPointF(box.left() + 26, y + 4), text)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if self.simulated and self.scans:
            self._label(painter, self.width() / 2, HEADER_INSET + HEADER_HEIGHT + 30, "SIMULATED DATA", _rgb(PALETTE["unknown"]))

        if not self.scans:
            title = QFont("Arial")
            title.setPixelSize(28)
            title.setBold(True)
            painter.setFont(title)
            painter.setPen(QColor(theme_manager.get("primary_color")))
            painter.drawText(QRectF(0, self.height() / 2 - 40, self.width(), 36),
                             Qt.AlignmentFlag.AlignCenter, "NO LIDAR CONNECTED")
            sub = QFont("Arial")
            sub.setPixelSize(16)
            painter.setFont(sub)
            painter.setPen(QColor(theme_manager.get("grey_light")))
            painter.drawText(QRectF(0, self.height() / 2 + 2, self.width(), 24),
                             Qt.AlignmentFlag.AlignCenter, "Press TEST DATA to preview the view with a simulated scene")

    def fps(self) -> float:
        if len(self.frame_times) < 2:
            return 0.0
        span = self.frame_times[-1] - self.frame_times[0]
        return (len(self.frame_times) - 1) / span if span > 0 else 0.0

    def _timed(self, name: str, fn, *args):
        t0 = time.perf_counter()
        fn(*args)
        self._timings[name] = self._timings.get(name, 0.0) + (time.perf_counter() - t0)

    def _draw_focus_beam(self, painter: QPainter, cam, now: float):
        tr = self.tracks.get(self.focus_track) if self.focus_track is not None else None
        if tr is None or self.preset == "eye":
            return
        head = self._p1(cam, tuple(HEAD_POS))
        target = self._p1(cam, (tr.centre[0], tr.centre[1], 1.45))
        accent = PALETTE["accent"]
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        if head and target:
            for width, alpha in ((14, 26), (7, 60), (2.5, 210)):
                pen = QPen(_rgb(accent, alpha), width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(QPointF(head[0], head[1]), QPointF(target[0], target[1]))
        pulse = 0.5 + 0.08 * math.sin(now * 6)
        ang = np.linspace(0, 2 * math.pi, 41)
        ring = np.stack([tr.centre[0] + np.cos(ang) * pulse, tr.centre[1] + np.sin(ang) * pulse, np.zeros(41)], axis=1)
        self._floor_polygon(painter, cam, ring, _rgb(accent, 22), _rgb(accent, 220), 2.5)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    def _draw_figures(self, painter: QPainter, cam, dt: float):
        for tr in sorted(self.tracks.values(), key=lambda t: -float(np.linalg.norm(t.centre - cam[0][:2]))):
            self._draw_figure(painter, cam, tr, dt)

    def _draw_sensor_pulse(self, painter: QPainter, cam, now: float):
        age = now - self.last_scan_time
        s = self._p1(cam, tuple(SENSOR_POS))
        if s and age < SCAN_INTERVAL_S and self.scans:
            grad = QRadialGradient(s[0], s[1], 26)
            grad.setColorAt(0, _rgb(PALETTE["accent"], 204 * (1 - age / SCAN_INTERVAL_S)))
            grad.setColorAt(1, _rgb(PALETTE["accent"], 0))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            painter.fillRect(QRectF(s[0] - 26, s[1] - 26, 52, 52), QBrush(grad))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    def _log_timings(self, now: float):
        if now - self._last_timing_log < TIMING_LOG_INTERVAL_S or not self.scans or not self._timed_frames:
            return
        per = {k: 1000 * v / self._timed_frames for k, v in self._timings.items()}
        parts = ", ".join(f"{k} {v:.1f}" for k, v in per.items() if k != "total")
        self.logger.debug("Lidar frame ms (%s): total %.1f (%s), %d blocks, %.0f fps",
                          self.RENDERER, per.get("total", 0), parts, len(self.voxels), self.fps())
        self._timings.clear()
        self._timed_frames = 0
        self._last_timing_log = now


class LidarView(LidarSceneMixin, QWidget):
    """QPainter renderer, used when OpenGL is unavailable."""

    RENDERER = "qpainter"

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self._init_scene()

    def _draw_background(self, painter: QPainter, cam):
        painter.drawPixmap(0, 0, self._cached_layers()[0])

        painter.setPen(QPen(PALETTE["grid"], 1))
        for x in range(-7, 8):
            self._polyline(painter, cam, np.stack([np.full(15, x), np.linspace(-4, 10, 15), np.zeros(15)], axis=1))
        for y in range(-4, 11):
            self._polyline(painter, cam, np.stack([np.linspace(-7, 7, 15), np.full(15, y), np.zeros(15)], axis=1))

        half = math.radians(DOME_HALF_ANGLE_DEG)
        ang = np.linspace(half, 2 * math.pi - half, 40)
        outer = np.stack([SENSOR_POS[0] + np.sin(ang) * 4.5, SENSOR_POS[1] + np.cos(ang) * 4.5, np.zeros(40)], axis=1)
        inner = np.stack([SENSOR_POS[0] + np.sin(ang[::-1]) * 0.3, SENSOR_POS[1] + np.cos(ang[::-1]) * 0.3,
                          np.zeros(40)], axis=1)
        self._floor_polygon(painter, cam, np.concatenate([outer, inner]), _rgb(BLIND_COL, 26), _rgb(BLIND_COL, 90))

    def _draw_blocks(self, painter: QPainter, cam, now: float):
        if not self.voxels:
            return
        keys = np.array(list(self.voxels.keys()), dtype=np.float64)
        ages = now - np.array(list(self.voxels.values()))
        life = np.clip(1 - ages / VOXEL_LIFETIME_S, 0, 1)
        o = keys * VOXEL_SIZE
        s = VOXEL_SIZE - 0.02
        k = _fog(o[:, :2] + s / 2)
        cam_pos = cam[0]

        x0, y0, z0 = o[:, 0], o[:, 1], o[:, 2]
        x1, y1, z1 = x0 + s, y0 + s, z0 + s

        ik = keys.astype(np.int64) + 512
        code = (ik[:, 0] << 20) | (ik[:, 1] << 10) | ik[:, 2]

        def free(dx: int, dy: int, dz: int) -> np.ndarray:
            return ~np.isin(code + (dx << 20) + (dy << 10) + dz, code)

        faces = [
            ("top", free(0, 0, 1), [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]),
            ("side", (cam_pos[0] > x1) & free(1, 0, 0), [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]),
            ("side", (cam_pos[0] < x0) & free(-1, 0, 0), [(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)]),
            ("side", (cam_pos[1] > y1) & free(0, 1, 0), [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)]),
            ("side", (cam_pos[1] < y0) & free(0, -1, 0), [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)]),
        ]
        strength = np.clip(life * (0.45 + 0.85 * k), 0, 1.3)
        bucket = np.clip((strength * 4).astype(int), 0, 5)
        tone = 0.5 + 0.5 * k

        fills: Dict[tuple, QPainterPath] = {}
        edges: Dict[int, QPainterPath] = {}
        tones: Dict[int, List[float]] = {}
        for kind, mask, quad in faces:
            idx = np.nonzero(mask)[0]
            if len(idx) == 0:
                continue
            pts = np.stack([np.stack([c[0][idx], c[1][idx], c[2][idx]], axis=1) for c in quad], axis=1)
            sx, sy, _, _, valid = self._project(cam, pts.reshape(-1, 3))
            sx, sy, valid = sx.reshape(-1, 4), sy.reshape(-1, 4), valid.reshape(-1, 4).all(axis=1)
            for j in np.nonzero(valid)[0]:
                b = int(bucket[idx[j]])
                poly = QPolygonF([QPointF(sx[j, 0], sy[j, 0]), QPointF(sx[j, 1], sy[j, 1]),
                                  QPointF(sx[j, 2], sy[j, 2]), QPointF(sx[j, 3], sy[j, 3])])
                fills.setdefault((kind, b), QPainterPath()).addPolygon(poly)
                edges.setdefault(b, QPainterPath()).addPolygon(poly)
                tones.setdefault(b, []).append(tone[idx[j]])

        base = np.array(PALETTE["block"], dtype=np.float64)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for (kind, b), path in fills.items():
            path.setFillRule(Qt.FillRule.WindingFill)
            col = _mix_fog(base, np.array(np.mean(tones[b])))
            level = (b + 0.5) / 4
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_rgb(col, 255 * min(0.6, (0.34 if kind == "top" else 0.16) * level)))
            painter.drawPath(path)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for b, path in edges.items():
            col = _mix_fog(base, np.array(np.mean(tones[b])))
            painter.setPen(QPen(_rgb(col, 255 * min(0.75, 0.35 * (b + 0.5) / 4)), 1))
            painter.drawPath(path)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    def _draw_points(self, painter: QPainter, cam):
        """Splat floor and person points into an image with additive glow, then draw it in one call."""
        w, h = self.width(), self.height()
        if w < 8 or h < 8 or not self.scans:
            return
        buf = np.zeros((h, w, 3), dtype=np.float32)
        gw, gh = (w + GLOW_DOWNSAMPLE - 1) // GLOW_DOWNSAMPLE, (h + GLOW_DOWNSAMPLE - 1) // GLOW_DOWNSAMPLE
        glow = np.zeros((gh, gw, 3), dtype=np.float32)
        person = np.array(PALETTE["person"], dtype=np.float64) * 0.6 + 100
        n = len(self.scans)
        age_alpha = [0.3, 0.55, 0.95]
        flat_all, cols_all, glow_flat, glow_cols = [], [], [], []

        for idx, scan in enumerate(self.scans):
            alpha_base = age_alpha[idx + SCAN_HISTORY - n]
            for kind in self._point_kinds():
                pts = scan[kind]
                if len(pts) == 0:
                    continue
                sx, sy, _, scale, valid = self._project(cam, pts)
                k = _fog(pts[:, :2])
                rgb = np.tile(person, (len(pts), 1)) if kind == "person" else _ramp(pts[:, 2])
                rgb = _mix_fog(rgb, 0.45 + 0.55 * k) * np.clip(alpha_base * (0.4 + 0.75 * k), 0, 1)[:, None]
                ix, iy = np.round(sx).astype(np.int64), np.round(sy).astype(np.int64)
                size = np.clip(np.round(scale * 0.025), 1, 3).astype(np.int64)
                ok = valid & (ix >= 0) & (ix < w - 3) & (iy >= 0) & (iy < h - 3)
                flat = [iy[ok] * w + ix[ok]]
                cols = [rgb[ok]]
                for s_px in (2, 3):
                    sel = ok & (size >= s_px)
                    if sel.any():
                        d = s_px - 1
                        base = iy[sel] * w + ix[sel]
                        flat += [base + d * w, base + d, base + d * w + d]
                        cols += [rgb[sel]] * 3
                flat_all += flat
                cols_all += cols
                if idx == n - 1:
                    sel = ok & (k > 0.6)
                    glow_flat.append((iy[sel] // GLOW_DOWNSAMPLE) * gw + ix[sel] // GLOW_DOWNSAMPLE)
                    glow_cols.append(rgb[sel] * GLOW_STRENGTH)

        if flat_all:
            _splat(buf, np.concatenate(flat_all), np.concatenate(cols_all))
        if glow_flat:
            _splat(glow, np.concatenate(glow_flat), np.concatenate(glow_cols))

        for axis in (0, 1):
            for _ in range(2):
                glow = (glow + np.roll(glow, 1, axis) + np.roll(glow, -1, axis)) / 3.0

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(QRectF(0, 0, w, h), self._to_image(glow))
        painter.drawImage(QRectF(0, 0, w, h), self._to_image(buf))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    @staticmethod
    def _to_image(rgb: np.ndarray) -> QImage:
        """Additive colour buffer to a premultiplied RGBA image."""
        h, w = rgb.shape[:2]
        out = np.empty((h, w, 4), dtype=np.uint8)
        np.clip(rgb, 0, 255, out=rgb)
        out[..., :3] = rgb
        np.maximum(np.maximum(out[..., 0], out[..., 1]), out[..., 2], out=out[..., 3])
        return QImage(out.tobytes(), w, h, 4 * w, QImage.Format.Format_RGBA8888_Premultiplied).copy()

    def _draw_robot(self, painter: QPainter, cam, now: float):
        centre = self._p1(cam, (0, 0, 0))
        edge = self._p1(cam, (0.9, 0, 0))
        if centre and edge:
            rx = max(10.0, abs(edge[0] - centre[0]) + 0.9 * centre[3] * 0.3)
            grad = QRadialGradient(centre[0], centre[1], rx)
            grad.setColorAt(0, QColor(0, 0, 0, 190))
            grad.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(QPointF(centre[0], centre[1]), rx, rx * 0.5)
            painter.setBrush(Qt.BrushStyle.NoBrush)

        rim = _rgb(PALETTE["accent"], 230)
        if self.model is None:
            self._draw_box(painter, cam, (-0.42, -0.4, 0), (-0.24, 0.4, 0.3), QColor(80, 80, 78, 250), QColor(48, 48, 46, 250), rim)
            self._draw_box(painter, cam, (0.24, -0.4, 0), (0.42, 0.4, 0.3), QColor(80, 80, 78, 250), QColor(48, 48, 46, 250), rim)
            self._draw_box(painter, cam, (-0.24, -0.32, 0.12), (0.24, 0.32, 0.62),
                           QColor(225, 175, 70, 250), QColor(196, 140, 40, 250), rim)
        else:
            v, f, shade = self.model["vertices"], self.model["faces"], self.model["shade"]
            colours = self.model["colours"] * 255
            sx, sy, z, _, valid = self._project(cam, v)
            tri_ok = valid[f].all(axis=1)
            order = np.argsort(-z[f].mean(axis=1))
            painter.setPen(Qt.PenStyle.NoPen)
            for i in order:
                if not tri_ok[i]:
                    continue
                a, b, c = f[i]
                s = shade[i]
                r, g, bl = colours[i] * s
                painter.setBrush(QColor(int(r), int(g), int(bl)))
                painter.drawPolygon(QPolygonF([QPointF(sx[a], sy[a]), QPointF(sx[b], sy[b]), QPointF(sx[c], sy[c])]))
            painter.setBrush(Qt.BrushStyle.NoBrush)

        sp = SENSOR_POS
        self._draw_box(painter, cam, (sp[0] - 0.05, sp[1] - 0.05, sp[2] - 0.06), (sp[0] + 0.05, sp[1] + 0.05, sp[2] + 0.06),
                       QColor(20, 20, 22), QColor(20, 20, 22), QColor(95, 211, 255, 230))
        self._draw_sensor_pulse(painter, cam, now)

    def paintEvent(self, event):
        now = time.monotonic()
        dt = min(0.1, now - self._last_frame)
        self._last_frame = now
        self.frame_times.append(now)
        t_start = time.perf_counter()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cam = self._camera(now - self._start)

        self._timed("background", self._draw_background, painter, cam)
        self._timed("trails", self._draw_trails_and_rings, painter, cam, now)
        self._timed("blocks", self._draw_blocks, painter, cam, now)
        self._timed("points", self._draw_points, painter, cam)
        self._timed("beam", self._draw_focus_beam, painter, cam, now)
        self._timed("figures", self._draw_figures, painter, cam, dt)
        if self.preset != "eye":
            self._timed("robot", self._draw_robot, painter, cam, now)
        self._timed("overlay", self._draw_overlay, painter)
        painter.end()
        self._timings["total"] = self._timings.get("total", 0.0) + (time.perf_counter() - t_start)
        self._timed_frames += 1

        self._log_timings(now)


GL_POINTS, GL_LINES, GL_TRIANGLES = 0x0000, 0x0001, 0x0004
GL_BLEND, GL_DEPTH_TEST, GL_PROGRAM_POINT_SIZE = 0x0BE2, 0x0B71, 0x8642
GL_ONE, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA = 0x0001, 0x0302, 0x0303
GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT = 0x4000, 0x0100
GL_FLOAT, GL_LEQUAL = 0x1406, 0x0203
GL_POINT_SPRITE = 0x8861
GL_TEXTURE0, GL_TEXTURE_2D = 0x84C0, 0x0DE1
VERTEX_STRIDE = 32
MESH_STRIDE = 40

BLOOM = True
BLOOM_STRENGTH = 0.5
FLOOR_REFLECTION = True
REFLECTION_DIM = 0.22
CAMERA_CONE_LENGTH_M = 6.5

VERTEX_SHADER = """
#version 120
attribute vec3 a_pos;
attribute vec4 a_col;
attribute float a_size;
uniform mat4 u_mvp;
uniform float u_focal;
uniform float u_min_size;
uniform float u_max_size;
uniform float u_dim;
varying vec4 v_col;
void main() {
    gl_Position = u_mvp * vec4(a_pos, 1.0);
    v_col = vec4(a_col.rgb, a_col.a * u_dim);
    gl_PointSize = clamp(a_size * u_focal / max(gl_Position.w, 0.1), u_min_size, u_max_size);
}
"""

FRAGMENT_SHADER = """
#version 120
varying vec4 v_col;
uniform int u_round;
void main() {
    float a = 1.0;
    if (u_round == 1) {
        vec2 d = gl_PointCoord * 2.0 - 1.0;
        float r = dot(d, d);
        if (r > 1.0) discard;
        a = (1.0 - r) * (1.0 - r);
    }
    gl_FragColor = vec4(v_col.rgb, v_col.a * a);
}
"""

MESH_VERTEX_SHADER = """
#version 120
attribute vec3 a_pos;
attribute vec3 a_nrm;
attribute vec4 a_col;
uniform mat4 u_mvp;
varying vec3 v_nrm;
varying vec3 v_pos;
varying vec4 v_col;
void main() {
    gl_Position = u_mvp * vec4(a_pos, 1.0);
    v_nrm = a_nrm;
    v_pos = a_pos;
    v_col = a_col;
}
"""

MESH_FRAGMENT_SHADER = """
#version 120
varying vec3 v_nrm;
varying vec3 v_pos;
varying vec4 v_col;
uniform vec3 u_light;
uniform vec3 u_eye;
uniform vec3 u_rim;
uniform float u_dim;
void main() {
    vec3 n = normalize(v_nrm);
    vec3 v = normalize(u_eye - v_pos);
    if (dot(n, v) < 0.0) n = -n;
    float diff = 0.3 + 0.7 * max(dot(n, u_light), 0.0);
    float spec = pow(max(dot(reflect(-u_light, n), v), 0.0), 24.0) * 0.35;
    float rim = pow(1.0 - max(dot(n, v), 0.0), 2.5) * 0.9;
    vec3 c = v_col.rgb * diff + vec3(spec) + rim * u_rim;
    gl_FragColor = vec4(c * u_dim, v_col.a * u_dim);
}
"""

POST_VERTEX_SHADER = """
#version 120
attribute vec3 a_pos;
varying vec2 v_uv;
void main() {
    gl_Position = vec4(a_pos.xy, 0.0, 1.0);
    v_uv = a_pos.xy * 0.5 + 0.5;
}
"""

POST_FRAGMENT_SHADER = """
#version 120
varying vec2 v_uv;
uniform sampler2D u_tex;
uniform vec2 u_step;
uniform float u_strength;
void main() {
    vec4 c = texture2D(u_tex, v_uv) * 0.227027;
    c += (texture2D(u_tex, v_uv + u_step * 1.384615) + texture2D(u_tex, v_uv - u_step * 1.384615)) * 0.316216;
    c += (texture2D(u_tex, v_uv + u_step * 3.230769) + texture2D(u_tex, v_uv - u_step * 3.230769)) * 0.070270;
    gl_FragColor = vec4(c.rgb * u_strength, 1.0);
}
"""

SCREEN_QUAD = np.array([[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, -1, 0], [1, 1, 0], [-1, 1, 0]], dtype=np.float32)


def _verts(pos: np.ndarray, rgba: np.ndarray, size: float = 0.0) -> np.ndarray:
    """Interleaved float32 vertices: x, y, z, r, g, b, a, size."""
    pos = np.asarray(pos, dtype=np.float32).reshape(-1, 3)
    rgba = np.broadcast_to(np.asarray(rgba, dtype=np.float32), (len(pos), 4))
    out = np.empty((len(pos), 8), dtype=np.float32)
    out[:, :3] = pos
    out[:, 3:7] = rgba
    out[:, 7] = size
    return out


def _mesh_verts(pos: np.ndarray, nrm: np.ndarray, rgba) -> np.ndarray:
    """Interleaved float32 mesh vertices: x, y, z, nx, ny, nz, r, g, b, a."""
    pos = np.asarray(pos, dtype=np.float32).reshape(-1, 3)
    out = np.empty((len(pos), 10), dtype=np.float32)
    out[:, :3] = pos
    out[:, 3:6] = np.asarray(nrm, dtype=np.float32).reshape(-1, 3)
    out[:, 6:10] = np.broadcast_to(np.asarray(rgba, dtype=np.float32), (len(pos), 4))
    return out


def _quads_to_tris(c0, c1, c2, c3) -> np.ndarray:
    return np.stack([c0, c1, c2, c0, c2, c3], axis=1).reshape(-1, 3)


def _quads_to_lines(c0, c1, c2, c3) -> np.ndarray:
    return np.stack([c0, c1, c1, c2, c2, c3, c3, c0], axis=1).reshape(-1, 3)


def _box_mesh(mn, mx, rgba, edge_rgba):
    """Lit triangles and edge lines for an axis-aligned box without a bottom face."""
    (x0, y0, z0), (x1, y1, z1) = mn, mx
    quads = [
        ((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), (0, 0, 1)),
        ((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1), (0, -1, 0)),
        ((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1), (1, 0, 0)),
        ((x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (0, 1, 0)),
        ((x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (-1, 0, 0)),
    ]
    tris, lines = [], []
    for q in quads:
        corners = [np.array([c]) for c in q[:4]]
        tri = _quads_to_tris(*corners)
        tris.append(_mesh_verts(tri, np.tile(q[4], (len(tri), 1)), rgba))
        lines.append(_verts(_quads_to_lines(*corners), edge_rgba))
    return np.concatenate(tris), np.concatenate(lines)


class LidarGLView(LidarSceneMixin, QOpenGLWidget):
    """OpenGL 2.1 renderer: blocks, points, glow, reflections and the lit robot on the GPU;
    trails, figures and labels drawn on top with QPainter."""

    RENDERER = "opengl"
    gl_failed = pyqtSignal()

    def __init__(self, parent=None):
        QOpenGLWidget.__init__(self, parent)
        self._init_scene(MODEL_MAX_TRIANGLES_GL)
        self.gl = None
        self.program = None
        self.mesh_program = None
        self.post_program = None
        self.vao = None
        self.vbo = None
        self.mesh_vbo = None
        self.mesh_count = 0
        self.failed = False
        self.bloom_ok = BLOOM
        self._bloom_fbos = None
        self._static = {}
        self._fbo_scale = 1.0

    # ---------- setup ----------

    def _make_program(self, vertex: str, fragment: str, attributes) -> QOpenGLShaderProgram:
        program = QOpenGLShaderProgram(self)
        if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, vertex):
            raise RuntimeError("Vertex shader: " + program.log())
        if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, fragment):
            raise RuntimeError("Fragment shader: " + program.log())
        for loc, name in enumerate(attributes):
            program.bindAttributeLocation(name, loc)
        if not program.link():
            raise RuntimeError("Shader link: " + program.log())
        return program

    def initializeGL(self):
        try:
            profile = QOpenGLVersionProfile()
            profile.setVersion(2, 1)
            self.gl = QOpenGLVersionFunctionsFactory.get(profile, self.context())
            if self.gl is None or not self.gl.initializeOpenGLFunctions():
                raise RuntimeError("OpenGL 2.1 functions unavailable")
            self.program = self._make_program(VERTEX_SHADER, FRAGMENT_SHADER, ("a_pos", "a_col", "a_size"))
            self.mesh_program = self._make_program(MESH_VERTEX_SHADER, MESH_FRAGMENT_SHADER, ("a_pos", "a_nrm", "a_col"))
            self.vao = QOpenGLVertexArrayObject(self)
            if not self.vao.create():
                self.vao = None
            self.vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            self.vbo.create()
            self.vbo.setUsagePattern(QOpenGLBuffer.UsagePattern.StreamDraw)
            self.mesh_vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            self.mesh_vbo.create()
            self.mesh_vbo.setUsagePattern(QOpenGLBuffer.UsagePattern.StaticDraw)
            self._build_static()
            self.logger.info("Lidar view using OpenGL")
        except Exception as e:
            self.failed = True
            self.logger.warning(f"OpenGL lidar view unavailable, using QPainter: {e}")
            QTimer.singleShot(0, self.gl_failed.emit)
            return
        if self.bloom_ok:
            try:
                self.post_program = self._make_program(POST_VERTEX_SHADER, POST_FRAGMENT_SHADER, ("a_pos",))
            except Exception as e:
                self.bloom_ok = False
                self.logger.warning(f"Lidar bloom disabled: {e}")

    def _build_static(self):
        grid = []
        for x in range(-7, 8):
            grid += [(x, -4, 0.001), (x, 10, 0.001)]
        for y in range(-4, 11):
            grid += [(-7, y, 0.001), (7, y, 0.001)]
        g = PALETTE["grid"]
        self._static["grid"] = _verts(np.array(grid), (g.redF(), g.greenF(), g.blueF(), g.alphaF()))

        half = math.radians(DOME_HALF_ANGLE_DEG)
        ang = np.linspace(half, 2 * math.pi - half, 41)
        outer = np.stack([SENSOR_POS[0] + np.sin(ang) * 4.5, SENSOR_POS[1] + np.cos(ang) * 4.5, np.full(41, 0.002)], axis=1)
        inner = np.stack([SENSOR_POS[0] + np.sin(ang) * 0.3, SENSOR_POS[1] + np.cos(ang) * 0.3, np.full(41, 0.002)], axis=1)
        red = np.array(BLIND_COL) / 255.0
        self._static["blind"] = _verts(_quads_to_tris(inner[:-1], outer[:-1], outer[1:], inner[1:]), (*red, 0.10))
        edge = np.concatenate([np.stack([outer[:-1], outer[1:]], axis=1).reshape(-1, 3),
                               np.stack([inner[:-1], inner[1:]], axis=1).reshape(-1, 3),
                               np.array([inner[0], outer[0], inner[-1], outer[-1]])])
        self._static["blind_edge"] = _verts(edge, (*red, 0.35))

        cone_half = math.radians(CAMERA_HFOV_DEG / 2)
        ang = np.linspace(-cone_half, cone_half, 25)
        near = np.stack([SENSOR_POS[0] + np.sin(ang) * 0.4, SENSOR_POS[1] + np.cos(ang) * 0.4, np.full(25, 0.0025)], axis=1)
        far = np.stack([SENSOR_POS[0] + np.sin(ang) * CAMERA_CONE_LENGTH_M, SENSOR_POS[1] + np.cos(ang) * CAMERA_CONE_LENGTH_M,
                        np.full(25, 0.0025)], axis=1)
        green = np.array(PALETTE["person"]) / 255.0
        tris = _quads_to_tris(near[:-1], far[:-1], far[1:], near[1:])
        alpha = np.tile([0.10, 0.0, 0.0, 0.10, 0.0, 0.10], 24)
        self._static["cone"] = _verts(tris, np.concatenate([np.tile(green, (len(tris), 1)), alpha[:, None]], axis=1))
        self._static["cone_edge"] = _verts(np.array([near[0], far[0], near[-1], far[-1]]), (*green, 0.25))

        ring = np.linspace(0, 2 * math.pi, 49)
        rim_pts = np.stack([np.cos(ring) * 0.9, np.sin(ring) * 0.9, np.full(49, 0.003)], axis=1)
        centre = np.zeros((48, 3)) + [0, 0, 0.003]
        shadow = np.stack([centre, rim_pts[:-1], rim_pts[1:]], axis=1).reshape(-1, 3)
        cols = np.tile(np.array([[0, 0, 0, 0.75], [0, 0, 0, 0], [0, 0, 0, 0]], dtype=np.float32), (48, 1))
        self._static["shadow"] = _verts(shadow, cols)

        rim = (*(np.array(PALETTE["accent"]) / 255.0), 0.9)
        meshes, edges = [], []
        if self.model is None:
            dark = (0.24, 0.24, 0.23, 1.0)
            for mn, mx, col in (((-0.42, -0.4, 0), (-0.24, 0.4, 0.3), dark), ((0.24, -0.4, 0), (0.42, 0.4, 0.3), dark),
                                ((-0.24, -0.32, 0.12), (0.24, 0.32, 0.62), (0.82, 0.6, 0.2, 1.0))):
                m, e = _box_mesh(mn, mx, col, rim)
                meshes.append(m)
                edges.append(e)
        else:
            v, f = self.model["vertices"], self.model["faces"]
            fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
            vn = np.zeros_like(v)
            for i in range(3):
                np.add.at(vn, f[:, i], fn)
            vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-9)
            rgba = np.concatenate([self.model["colours"], np.ones((len(f), 1))], axis=1)
            meshes.append(_mesh_verts(v[f].reshape(-1, 3), vn[f].reshape(-1, 3), np.repeat(rgba, 3, axis=0)))
        sp = SENSOR_POS
        m, e = _box_mesh((sp[0] - 0.05, sp[1] - 0.05, sp[2] - 0.06), (sp[0] + 0.05, sp[1] + 0.05, sp[2] + 0.06),
                         (0.08, 0.08, 0.09, 1.0), (95 / 255, 211 / 255, 1.0, 0.9))
        meshes.append(m)
        edges.append(e)
        mesh = np.concatenate(meshes)
        self._static["robot_edge"] = np.concatenate(edges) if edges else None
        raw = np.ascontiguousarray(mesh, dtype=np.float32).tobytes()
        self.mesh_vbo.bind()
        self.mesh_vbo.allocate(raw, len(raw))
        self.mesh_vbo.release()
        self.mesh_count = len(mesh)

        top, bottom = QColor(PALETTE["bg"][0]), QColor(PALETTE["bg"][1])
        b = [bottom.redF(), bottom.greenF(), bottom.blueF(), 1]
        t = [top.redF(), top.greenF(), top.blueF(), 1]
        self._static["background"] = _verts(SCREEN_QUAD, np.array([b, b, t, b, t, t]))

    # ---------- per-frame geometry ----------

    def _block_geometry(self, cam, now: float):
        if not self.voxels:
            return None, None
        keys = np.array(list(self.voxels.keys()), dtype=np.float64)
        ages = now - np.array(list(self.voxels.values()))
        life = np.clip(1 - ages / VOXEL_LIFETIME_S, 0, 1)
        o = keys * VOXEL_SIZE
        s = VOXEL_SIZE - 0.02
        k = _fog(o[:, :2] + s / 2)
        cam_pos = cam[0]
        ik = keys.astype(np.int64) + 512
        code = (ik[:, 0] << 20) | (ik[:, 1] << 10) | ik[:, 2]

        def free(dx: int, dy: int, dz: int) -> np.ndarray:
            return ~np.isin(code + (dx << 20) + (dy << 10) + dz, code)

        x0, y0, z0 = o[:, 0], o[:, 1], o[:, 2]
        x1, y1, z1 = x0 + s, y0 + s, z0 + s
        faces = [
            (0.34, free(0, 0, 1), [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]),
            (0.16, (cam_pos[0] > x1) & free(1, 0, 0), [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]),
            (0.16, (cam_pos[0] < x0) & free(-1, 0, 0), [(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)]),
            (0.16, (cam_pos[1] > y1) & free(0, 1, 0), [(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)]),
            (0.16, (cam_pos[1] < y0) & free(0, -1, 0), [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)]),
        ]
        strength = np.clip(life * (0.45 + 0.85 * k), 0, 1.3)
        col = _mix_fog(np.array(PALETTE["block"], dtype=np.float64), 0.5 + 0.5 * k) / 255.0
        tris, lines = [], []
        for base_alpha, mask, quad in faces:
            idx = np.nonzero(mask)[0]
            if len(idx) == 0:
                continue
            c = [np.stack([q[0][idx], q[1][idx], q[2][idx]], axis=1) for q in quad]
            fill = np.concatenate([col[idx], np.minimum(0.6, base_alpha * strength[idx])[:, None]], axis=1)
            edge = np.concatenate([col[idx], np.minimum(0.75, 0.35 * strength[idx])[:, None]], axis=1)
            tris.append(_verts(_quads_to_tris(*c), np.repeat(fill, 6, axis=0)))
            lines.append(_verts(_quads_to_lines(*c), np.repeat(edge, 8, axis=0)))
        if not tris:
            return None, None
        return np.concatenate(tris), np.concatenate(lines)

    def _point_geometry(self):
        person = np.array(PALETTE["person"], dtype=np.float64) * 0.6 + 100
        n = len(self.scans)
        age_alpha = [0.3, 0.55, 0.95]
        cores, glows = [], []
        for idx, scan in enumerate(self.scans):
            alpha_base = age_alpha[idx + SCAN_HISTORY - n]
            for kind in self._point_kinds():
                pts = scan[kind]
                if len(pts) == 0:
                    continue
                k = _fog(pts[:, :2])
                rgb = np.tile(person, (len(pts), 1)) if kind == "person" else _ramp(pts[:, 2])
                rgb = _mix_fog(rgb, 0.45 + 0.55 * k) / 255.0
                alpha = np.clip(alpha_base * (0.4 + 0.75 * k), 0, 1)
                cores.append(_verts(pts, np.concatenate([rgb, alpha[:, None]], axis=1), 0.025))
                if idx == n - 1:
                    sel = k > 0.6
                    glows.append(_verts(pts[sel], np.concatenate([rgb[sel], (alpha[sel] * GLOW_STRENGTH)[:, None]], axis=1), 0.12))
        core = np.concatenate(cores) if cores else None
        glow = np.concatenate(glows) if glows else None
        return core, glow

    def _proximity_geometry(self):
        """Floor wedges between the robot and anything closer than PROXIMITY_RANGE_M."""
        sectors = np.nonzero(np.isfinite(self.proximity) & (self.proximity < PROXIMITY_RANGE_M))[0]
        if len(sectors) == 0:
            return None
        step = 2 * math.pi / PROXIMITY_SECTORS
        a0 = -math.pi + sectors * step
        a1 = a0 + step
        d = np.maximum(self.proximity[sectors], 0.05)
        r0, r1 = np.full(len(sectors), ROBOT_RADIUS_M), ROBOT_RADIUS_M + d

        def pt(r, a):
            return np.stack([np.sin(a) * r, np.cos(a) * r, np.full(len(a), 0.004)], axis=1)

        tris = _quads_to_tris(pt(r0, a0), pt(r1, a0), pt(r1, a1), pt(r0, a1))
        danger = np.clip((PROXIMITY_RANGE_M - d) / (PROXIMITY_RANGE_M - PROXIMITY_DANGER_M), 0, 1)
        amber, red = np.array([1.0, 0.7, 0.15]), np.array([1.0, 0.2, 0.12])
        rgb = amber + (red - amber) * danger[:, None]
        inner = np.concatenate([rgb, (0.15 + 0.45 * danger)[:, None]], axis=1)
        outer = np.concatenate([rgb, np.zeros((len(d), 1))], axis=1)
        cols = np.stack([inner, outer, outer, inner, outer, inner], axis=1).reshape(-1, 4)
        return _verts(tris, cols)

    def _matrices(self, cam):
        pos, fwd, right, up, _ = cam
        view = np.eye(4)
        view[0, :3], view[1, :3], view[2, :3] = right, up, -fwd
        view[:3, 3] = [-np.dot(right, pos), -np.dot(up, pos), np.dot(fwd, pos)]
        f1 = 1.0 / math.tan(math.radians(FIELD_OF_VIEW_DEG) / 2)
        aspect = max(1.0, self.width()) / max(1.0, self.height())
        near, far = 0.1, 100.0
        proj = np.array([[f1 / aspect, 0, 0, 0], [0, f1, 0, 0],
                         [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)], [0, 0, -1, 0]])
        return proj @ view

    # ---------- drawing ----------

    @staticmethod
    def _qmat(m: np.ndarray) -> QMatrix4x4:
        return QMatrix4x4(*[float(v) for v in m.flatten()])

    def _attributes(self, program, layout, stride: int):
        for loc, offset, size in layout:
            program.setAttributeBuffer(loc, GL_FLOAT, offset, size, stride)
            program.enableAttributeArray(loc)

    def _release_attributes(self, program, count: int):
        for loc in range(count):
            program.disableAttributeArray(loc)

    def _draw(self, mode: int, data: Optional[np.ndarray], mvp: QMatrix4x4, round_points: bool = False,
              min_size: float = 1.0, max_size: float = 4.0, dim: float = 1.0):
        if data is None or len(data) == 0:
            return
        dpr = self.devicePixelRatioF()
        focal = (self.height() / 2) / math.tan(math.radians(FIELD_OF_VIEW_DEG) / 2) * dpr * self._fbo_scale
        p = self.program
        p.setUniformValue("u_mvp", mvp)
        p.setUniformValue("u_focal", float(focal))
        p.setUniformValue("u_min_size", float(min_size * dpr * self._fbo_scale))
        p.setUniformValue("u_max_size", float(max_size * dpr * self._fbo_scale))
        p.setUniformValue("u_round", 1 if round_points else 0)
        p.setUniformValue("u_dim", float(dim))
        raw = np.ascontiguousarray(data, dtype=np.float32).tobytes()
        self.vbo.bind()
        self.vbo.allocate(raw, len(raw))
        self._attributes(p, ((0, 0, 3), (1, 12, 4), (2, 28, 1)), VERTEX_STRIDE)
        self.gl.glDrawArrays(mode, 0, len(data))
        self._release_attributes(p, 3)
        self.vbo.release()

    def _draw_mesh(self, mvp: QMatrix4x4, cam, dim: float = 1.0):
        if not self.mesh_count:
            return
        mp = self.mesh_program
        mp.bind()
        light = np.array([0.4, -0.6, 0.8]) / np.linalg.norm([0.4, -0.6, 0.8])
        mp.setUniformValue("u_mvp", mvp)
        mp.setUniformValue("u_light", QVector3D(*[float(v) for v in light]))
        mp.setUniformValue("u_eye", QVector3D(*[float(v) for v in cam[0]]))
        mp.setUniformValue("u_rim", QVector3D(*[c / 255.0 for c in PALETTE["accent"]]))
        mp.setUniformValue("u_dim", float(dim))
        self.mesh_vbo.bind()
        self._attributes(mp, ((0, 0, 3), (1, 12, 3), (2, 24, 4)), MESH_STRIDE)
        self.gl.glDrawArrays(GL_TRIANGLES, 0, self.mesh_count)
        self._release_attributes(mp, 3)
        self.mesh_vbo.release()
        self.program.bind()

    def _bloom_targets(self, w: int, h: int):
        size = (max(1, w // 2), max(1, h // 2))
        if self._bloom_fbos is None or self._bloom_fbos[0] != size:
            self._bloom_fbos = (size, QOpenGLFramebufferObject(*size), QOpenGLFramebufferObject(*size))
        return self._bloom_fbos[1], self._bloom_fbos[2]

    def _blur_pass(self, source, target, step):
        target.bind()
        pp = self.post_program
        pp.bind()
        self.gl.glActiveTexture(GL_TEXTURE0)
        self.gl.glBindTexture(GL_TEXTURE_2D, source.texture())
        pp.setUniformValue("u_tex", 0)
        pp.setUniformValue("u_step", QVector2D(*step))
        pp.setUniformValue("u_strength", 1.0)
        self._draw_quad(pp)

    def _draw_quad(self, program):
        raw = SCREEN_QUAD.tobytes()
        self.vbo.bind()
        self.vbo.allocate(raw, len(raw))
        program.setAttributeBuffer(0, GL_FLOAT, 0, 3, 12)
        program.enableAttributeArray(0)
        self.gl.glDrawArrays(GL_TRIANGLES, 0, 6)
        program.disableAttributeArray(0)
        self.vbo.release()

    def _render_bloom(self, glow_layers, mvp, now: float):
        gl = self.gl
        dpr = self.devicePixelRatioF()
        w, h = int(self.width() * dpr), int(self.height() * dpr)
        a, b = self._bloom_targets(w, h)
        a.bind()
        gl.glViewport(0, 0, a.width(), a.height())
        gl.glClearColor(0.0, 0.0, 0.0, 1.0)
        gl.glClear(GL_COLOR_BUFFER_BIT)
        gl.glDisable(GL_DEPTH_TEST)
        gl.glEnable(GL_BLEND)
        gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        self._fbo_scale = 0.5
        self.program.bind()
        for mode, data, kwargs in glow_layers:
            self._draw(mode, data, mvp, **kwargs)
        self._fbo_scale = 1.0
        gl.glDisable(GL_BLEND)
        for _ in range(2):
            self._blur_pass(a, b, (1.0 / a.width(), 0.0))
            self._blur_pass(b, a, (0.0, 1.0 / a.height()))
        QOpenGLFramebufferObject.bindDefault()
        gl.glViewport(0, 0, w, h)
        gl.glEnable(GL_BLEND)
        gl.glBlendFunc(GL_ONE, GL_ONE)
        pp = self.post_program
        pp.bind()
        gl.glActiveTexture(GL_TEXTURE0)
        gl.glBindTexture(GL_TEXTURE_2D, a.texture())
        pp.setUniformValue("u_tex", 0)
        pp.setUniformValue("u_step", QVector2D(0.0, 0.0))
        pp.setUniformValue("u_strength", float(BLOOM_STRENGTH))
        self._draw_quad(pp)
        gl.glBindTexture(GL_TEXTURE_2D, 0)
        pp.release()

    def _render_gl(self, cam, now: float):
        gl = self.gl
        dpr = self.devicePixelRatioF()
        self._fbo_scale = 1.0
        gl.glViewport(0, 0, int(self.width() * dpr), int(self.height() * dpr))
        gl.glClearColor(0.0, 0.0, 0.0, 1.0)
        gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        gl.glEnable(GL_PROGRAM_POINT_SIZE)
        gl.glEnable(GL_POINT_SPRITE)

        t0 = time.perf_counter()
        blocks, block_edges = self._block_geometry(cam, now)
        core, glow = self._point_geometry()
        proximity = self._proximity_geometry()
        self._timings["geometry"] = self._timings.get("geometry", 0.0) + (time.perf_counter() - t0)

        m = self._matrices(cam)
        mvp = self._qmat(m)
        mirror = self._qmat(m @ np.diag([1.0, 1.0, -1.0, 1.0]))
        show_robot = self.preset != "eye"

        if self.vao is not None:
            self.vao.bind()
        self.program.bind()

        gl.glDisable(GL_DEPTH_TEST)
        gl.glDisable(GL_BLEND)
        self._draw(GL_TRIANGLES, self._static["background"], QMatrix4x4())

        gl.glEnable(GL_BLEND)
        if FLOOR_REFLECTION and self.preset != "eye":
            gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE)
            self._draw(GL_TRIANGLES, blocks, mirror, dim=REFLECTION_DIM)
            self._draw(GL_POINTS, core, mirror, min_size=1.3, max_size=4.0, dim=REFLECTION_DIM)
            if show_robot:
                gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
                self._draw_mesh(mirror, cam, dim=REFLECTION_DIM)

        gl.glEnable(GL_DEPTH_TEST)
        gl.glDepthFunc(GL_LEQUAL)
        gl.glDepthMask(True)
        gl.glDisable(GL_BLEND)
        if show_robot:
            self._draw_mesh(mvp, cam)

        gl.glDepthMask(False)
        gl.glEnable(GL_BLEND)
        gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        if show_robot:
            self._draw(GL_TRIANGLES, self._static["shadow"], mvp)
        self._draw(GL_TRIANGLES, self._static["blind"], mvp)
        self._draw(GL_LINES, self._static["blind_edge"], mvp)
        self._draw(GL_TRIANGLES, self._static["cone"], mvp)
        self._draw(GL_LINES, self._static["cone_edge"], mvp)
        self._draw(GL_LINES, self._static["grid"], mvp)
        self._draw(GL_TRIANGLES, proximity, mvp)
        if show_robot:
            self._draw(GL_LINES, self._static["robot_edge"], mvp)

        gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        self._draw(GL_TRIANGLES, blocks, mvp)
        self._draw(GL_LINES, block_edges, mvp)
        self._draw(GL_POINTS, glow, mvp, round_points=True, min_size=4.0, max_size=26.0)
        self._draw(GL_POINTS, core, mvp, round_points=False, min_size=1.3, max_size=4.0)

        gl.glDepthMask(True)
        gl.glDisable(GL_DEPTH_TEST)

        if self.bloom_ok and self.post_program is not None and self.scans:
            t1 = time.perf_counter()
            try:
                self._render_bloom([
                    (GL_TRIANGLES, blocks, {"dim": 0.8}),
                    (GL_LINES, block_edges, {}),
                    (GL_POINTS, glow, {"round_points": True, "min_size": 4.0, "max_size": 26.0}),
                    (GL_POINTS, core, {"min_size": 1.3, "max_size": 4.0}),
                ], mvp, now)
            except Exception as e:
                self.bloom_ok = False
                QOpenGLFramebufferObject.bindDefault()
                self.logger.warning(f"Lidar bloom disabled: {e}")
            self._timings["bloom"] = self._timings.get("bloom", 0.0) + (time.perf_counter() - t1)

        gl.glDisable(GL_BLEND)
        if self.vao is not None:
            self.vao.release()
        self.program.release()

    def paintGL(self):
        now = time.monotonic()
        dt = min(0.1, now - self._last_frame)
        self._last_frame = now
        self.frame_times.append(now)
        t_start = time.perf_counter()
        cam = self._camera(now - self._start)

        painter = QPainter(self)
        if not self.failed:
            painter.beginNativePainting()
            t0 = time.perf_counter()
            try:
                self._render_gl(cam, now)
            except Exception as e:
                self.failed = True
                self.logger.warning(f"OpenGL lidar view failed, using QPainter: {e}")
                QTimer.singleShot(0, self.gl_failed.emit)
            self._timings["gl"] = self._timings.get("gl", 0.0) + (time.perf_counter() - t0)
            painter.endNativePainting()

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._timed("trails", self._draw_trails_and_rings, painter, cam, now)
        self._timed("beam", self._draw_focus_beam, painter, cam, now)
        self._timed("figures", self._draw_figures, painter, cam, dt)
        self._timed("pulse", self._draw_sensor_pulse, painter, cam, now)
        self._timed("overlay", self._draw_overlay, painter)
        painter.end()
        self._timings["total"] = self._timings.get("total", 0.0) + (time.perf_counter() - t_start)
        self._timed_frames += 1
        self._log_timings(now)


class LidarScreen(BaseScreen):
    """3D view of WALL-E's surroundings built from the Unitree L2 point cloud."""

    def _setup_screen(self):
        self.setStyleSheet("background: transparent;")
        self.simulator = LidarSimulator()
        self.camera_source = None
        self._attention = {"state": None, "focus_id": None, "time": 0.0}
        self.subscribe("attention_state", self._on_attention_state)
        self.subscribe("lidar_status", self._on_lidar_status)
        self._live_frames: deque = deque(maxlen=LIVE_DETECT_FRAMES)
        self._last_live = 0.0
        self._lidar_status: Dict = {}
        self._streaming = False
        if self.websocket is not None:
            if hasattr(self.websocket, "register_binary_handler"):
                self.websocket.register_binary_handler(FRAME_MAGIC, self._on_lidar_frame)
            self.websocket.connected.connect(self._on_reconnected)
        self._sim_start = time.monotonic()
        self._last_scan = 0.0
        self._scan_times: deque = deque(maxlen=20)

        self.card = QFrame()
        self.card.setObjectName(CARD_OBJECT_NAME)
        self.card.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.card.setStyleSheet(card_style())

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        card_layout.setSpacing(CARD_PADDING)
        self.card_layout = card_layout

        header = QHBoxLayout()
        header.setContentsMargins(4, 0, 0, 0)
        header.setSpacing(10)
        self.title_label = QLabel("SURROUNDINGS  ·  3D")
        self.title_label.setFont(px_font(14, bold=True, spacing=1.5))
        self.stats_label = QLabel("Lidar: waiting for backend")
        self.stats_label.setFont(px_font(13))
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.test_button = QPushButton("TEST DATA")
        self.test_button.setCheckable(True)
        self.test_button.setFixedSize(110, 26)
        self.test_button.setFont(px_font(12, bold=True))
        self.test_button.toggled.connect(self._on_test_toggled)

        self.view_button = QPushButton("VIEW: CHASE")
        self.view_button.setFixedSize(110, 26)
        self.view_button.setFont(px_font(12, bold=True))

        self.reset_button = QPushButton("RESET VIEW")
        self.reset_button.setFixedSize(110, 26)
        self.reset_button.setFont(px_font(12, bold=True))

        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.stats_label)
        header.addWidget(self.test_button)
        header.addWidget(self.view_button)
        header.addWidget(self.reset_button)
        self.view = self._make_view()
        self.reset_button.clicked.connect(lambda: self.view.reset_view())
        self.view_button.clicked.connect(self._next_view)
        card_layout.addWidget(self.view, 1)

        self.header_widget = QWidget(self.card)
        self.header_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.header_widget.setStyleSheet("background: transparent;")
        self.header_widget.setLayout(header)
        self.header_widget.setGeometry(CARD_PADDING + HEADER_INSET, CARD_PADDING + HEADER_INSET,
                                       CARD_WIDTH - 2 * (CARD_PADDING + HEADER_INSET), HEADER_HEIGHT)
        self.header_widget.raise_()

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(105, 27, 12, 6)
        main_layout.addWidget(self.card, 0, Qt.AlignmentFlag.AlignTop)
        main_layout.addStretch()

        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self._tick)

        self._apply_styles()
        theme_manager.register_callback(self._apply_styles)

    def set_camera_source(self, camera_screen):
        """Camera screen whose tracked people give the bearing of WALL-E's attention focus."""
        self.camera_source = camera_screen

    def _on_attention_state(self, message: Dict):
        self._attention = {"state": message.get("state"), "focus_id": message.get("focus_id"),
                           "time": time.monotonic()}

    def _next_view(self):
        self.view_button.setText(f"VIEW: {self.view.next_view().upper()}")

    def _focus_track(self, now: float) -> Optional[int]:
        """Lidar track WALL-E is paying attention to, matched by bearing from the camera."""
        tracks = self.view.tracks
        if not tracks:
            return None
        if self.test_button.isChecked():
            people = [t for t in tracks.values() if t.detection.get("label") == "PERSON"]
            return min(people, key=lambda t: float(np.linalg.norm(t.centre)), default=None).id if people else None
        att = self._attention
        state = (att["state"] or "").upper()
        if att["focus_id"] is None or state in ("", "OFF") or now - att["time"] > ATTENTION_TIMEOUT_S:
            return None
        cam = self.camera_source
        people = getattr(cam, "_last_people", None) if cam is not None else None
        person = next((p for p in (people or []) if p.get("id") == att["focus_id"]), None)
        if person is None:
            return None
        bearing = math.radians((person["cx"] - 0.5) * CAMERA_HFOV_DEG)
        best, best_diff = None, math.radians(ATTENTION_MATCH_DEG)
        for t in tracks.values():
            diff = abs(math.atan2(t.centre[0] - SENSOR_POS[0], t.centre[1] - SENSOR_POS[1]) - bearing)
            if diff < best_diff:
                best, best_diff = t.id, diff
        return best

    def _make_view(self):
        if USE_OPENGL:
            view = LidarGLView()
            view.gl_failed.connect(self._fall_back_to_painter)
            return view
        return LidarView()

    def _fall_back_to_painter(self):
        """Swap the OpenGL view for the QPainter one, keeping scans, tracks and camera."""
        old = self.view
        if isinstance(old, LidarView):
            return
        new = LidarView()
        for attr in ("scans", "voxels", "tracks", "_next_track", "simulated", "last_scan_time", "preset", "target",
                     "yaw_offset", "pitch", "distance", "auto_sway", "_yaw", "focus_track", "proximity"):
            setattr(new, attr, getattr(old, attr))
        self.card_layout.replaceWidget(old, new)
        old.hide()
        old.deleteLater()
        self.view = new
        self.header_widget.raise_()

    def _apply_styles(self, *_):
        primary = theme_manager.get("primary_color")
        self.card.setStyleSheet(card_style())
        self.title_label.setStyleSheet(f"color: {primary}; border: none; background: transparent;")
        self.stats_label.setStyleSheet("color: #9e9e9e; border: none; background: transparent;")
        self.test_button.setStyleSheet(button_style(checked_fill=primary))
        self.reset_button.setStyleSheet(button_style())
        self.view_button.setStyleSheet(button_style())

    def _on_test_toggled(self, checked: bool):
        self._scan_times.clear()
        self._live_frames.clear()
        self.view.clear()
        if checked:
            self._sim_start = time.monotonic()
            self._last_scan = 0.0
        else:
            self._show_lidar_status()
        self._set_stream(self.isVisible() and not checked)

    # ---------- live lidar ----------

    def _set_stream(self, enable: bool, force: bool = False):
        """Ask the backend to start or stop the binary point stream for this Deck."""
        if enable == self._streaming and not force:
            return
        if self.websocket is None or not self.websocket.is_connected():
            self._streaming = False
            return
        if self.send_websocket_message("lidar_stream", enable=enable):
            self._streaming = enable

    def _on_reconnected(self):
        self._streaming = False
        self._set_stream(self.isVisible() and not self.test_button.isChecked(), force=True)

    def _on_lidar_status(self, message: Dict):
        self._lidar_status = message
        if not self.test_button.isChecked() and time.monotonic() - self._last_live > LIVE_TIMEOUT_S:
            self._show_lidar_status()

    def _show_lidar_status(self):
        st = self._lidar_status
        if not st:
            self.stats_label.setText("Lidar: waiting for backend")
        elif not st.get("enabled", True):
            self.stats_label.setText("Lidar disabled in backend config")
        elif st.get("connected"):
            self.stats_label.setText(f"Lidar {st.get('lidar_ip', '')}  ·  {st.get('points_per_s', 0):,} pts/s")
        else:
            self.stats_label.setText("Lidar not connected")

    def _camera_bearings(self) -> Optional[List[float]]:
        cam = self.camera_source
        if cam is None or not getattr(cam, "tracking_enabled", False):
            return None
        return [(p["cx"] - 0.5) * CAMERA_HFOV_DEG for p in (getattr(cam, "_last_people", None) or []) if "cx" in p]

    def _on_lidar_frame(self, data: bytes):
        if self.test_button.isChecked() or not self.isVisible():
            return
        try:
            decoded = decode_frame(data)
        except Exception as e:
            self.logger.warning(f"Bad lidar frame: {e}")
            return
        if decoded is None:
            return
        _, _, points = decoded
        now = time.monotonic()
        self._last_live = now
        self._live_frames.append(points)
        detections = detect_people(np.concatenate(self._live_frames), self._camera_bearings())
        self.view.set_scan(points, detections, simulated=False)
        self._scan_times.append(now)
        self._update_stats(len(points), self.view.tracked_count())

    def _tick(self):
        now = time.monotonic()
        if self.test_button.isChecked() and now - self._last_scan >= SCAN_INTERVAL_S:
            self._last_scan = now
            points, detections = self.simulator.scan(now - self._sim_start)
            self.view.set_scan(points, detections, simulated=True)
            self._scan_times.append(now)
            self._update_stats(len(points), self.view.tracked_count())
        elif self._last_live and now - self._last_live > LIVE_TIMEOUT_S:
            self._last_live = 0.0
            self._live_frames.clear()
            self._scan_times.clear()
            self.view.clear()
            self._show_lidar_status()
        self.view.set_focus(self._focus_track(now))
        self.view.update()

    def _update_stats(self, n_points: int, n_people: int):
        rate = 0.0
        if len(self._scan_times) > 1:
            span = self._scan_times[-1] - self._scan_times[0]
            rate = (len(self._scan_times) - 1) / span if span > 0 else 0.0
        source = "TEST" if self.test_button.isChecked() else f"LIVE {self._lidar_status.get('lidar_ip', '')}".strip()
        self.stats_label.setText(f"{source}  ·  {n_points:,} points  ·  {rate:.0f} Hz  ·  {n_people} tracked  ·  "
                                 f"{self.view.fps():.0f} fps")

    def showEvent(self, event):
        super().showEvent(event)
        self.frame_timer.start(FRAME_INTERVAL_MS)
        if not self.test_button.isChecked():
            self._show_lidar_status()
            self._set_stream(True)

    def hideEvent(self, event):
        self.frame_timer.stop()
        self._set_stream(False)
        super().hideEvent(event)

    def cleanup(self):
        self.frame_timer.stop()
        self._set_stream(False)
        if self.websocket is not None and hasattr(self.websocket, "unregister_binary_handler"):
            self.websocket.unregister_binary_handler(FRAME_MAGIC, self._on_lidar_frame)
        try:
            theme_manager.unregister_callback(self._apply_styles)
        except Exception:
            pass
