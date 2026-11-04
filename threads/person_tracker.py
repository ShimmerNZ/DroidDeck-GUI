#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lightweight multi-person tracker.

Assigns stable integer IDs to body detections across frames. Each track
predicts where its person will be from their recent movement, and a detection
only matches a track if it is near that prediction and a similar size, so two
people crossing keep their own IDs. Positions are lightly smoothed to take
the frame-to-frame jitter out of the head aim.

IDs are reused: a new person takes the lowest ID that is free, as long as it
has not belonged to anyone for reuse_delay seconds, so the numbers stay small
without a newcomer being mistaken for someone who only just left.

Pure Python, no dependencies, safe to run inside the image processing thread.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Detection:
    """One body found in a frame; positions and sizes are normalised 0..1"""
    cx: float
    cy: float
    w: float
    h: float
    score: float
    shoulder_width: float = 0.0
    gesture: Optional[str] = None
    points: List[Tuple[float, float]] = field(default_factory=list)


@dataclass
class TrackedPerson:
    track_id: int
    cx: float
    cy: float
    w: float
    h: float
    score: float
    first_seen: float
    last_seen: float
    shoulder_width: float = 0.0
    gesture: Optional[str] = None
    points: List[Tuple[float, float]] = field(default_factory=list)
    vx: float = 0.0
    vy: float = 0.0
    hits: int = 1

    def predicted(self, now: float) -> Tuple[float, float]:
        dt = min(max(now - self.last_seen, 0.0), 0.5)
        return self.cx + self.vx * dt, self.cy + self.vy * dt

    def as_dict(self) -> Dict[str, object]:
        return {
            "id": self.track_id,
            "cx": round(self.cx, 4),
            "cy": round(self.cy, 4),
            "w": round(self.w, 4),
            "h": round(self.h, 4),
            "sw": round(self.shoulder_width, 4),
            "score": round(self.score, 3),
            "gesture": self.gesture,
        }


class PersonTracker:
    """
    Track lifecycle:
      - a new detection creates a track that is reported once it has been
        matched in min_hits frames
      - a track that goes unmatched is still reported for report_grace seconds
        at its last known position, so a single missed detection does not make
        the person appear to vanish
      - a track is kept for max_missed seconds so a person who reappears
        briefly keeps the same ID. This is longer than the backend's
        lost_grace (2.0s), so someone who reappears before the backend gives
        up on them is still recognised as the same person
    """

    def __init__(self, max_missed: float = 2.5, report_grace: float = 0.4,
                 min_hits: int = 2, max_match_distance: float = 1.0,
                 max_size_ratio: float = 2.0, smoothing: float = 0.6,
                 reuse_delay: float = 20.0):
        self.max_missed = max_missed
        self.report_grace = report_grace
        self.min_hits = min_hits
        self.max_match_distance = max_match_distance
        self.max_size_ratio = max_size_ratio
        self.smoothing = smoothing
        self.reuse_delay = reuse_delay
        self._tracks: Dict[int, TrackedPerson] = {}
        self._released: Dict[int, float] = {}

    def reset(self) -> None:
        self._tracks.clear()
        self._released.clear()

    def update(self, detections: List[Detection], now: float) -> List[TrackedPerson]:
        """Match detections to tracks and return the confirmed, recently seen people."""
        pairs = self._candidate_pairs(detections, now)
        pairs.sort(key=lambda p: p[0])

        used_tracks = set()
        used_detections = set()
        for _, track_id, det_idx in pairs:
            if track_id in used_tracks or det_idx in used_detections:
                continue
            used_tracks.add(track_id)
            used_detections.add(det_idx)
            self._apply(self._tracks[track_id], detections[det_idx], now)

        for track in self._tracks.values():
            if track.track_id not in used_tracks:
                track.gesture = None

        for det_idx, det in enumerate(detections):
            if det_idx in used_detections:
                continue
            track = TrackedPerson(
                track_id=self._new_id(now), cx=det.cx, cy=det.cy, w=det.w, h=det.h,
                score=det.score, first_seen=now, last_seen=now,
                shoulder_width=det.shoulder_width, gesture=det.gesture, points=det.points,
            )
            self._tracks[track.track_id] = track

        for track_id in [t.track_id for t in self._tracks.values()
                         if now - t.last_seen > self.max_missed]:
            del self._tracks[track_id]
            self._released[track_id] = now

        visible = [
            t for t in self._tracks.values()
            if t.hits >= self.min_hits and now - t.last_seen <= self.report_grace
        ]
        visible.sort(key=lambda t: t.track_id)
        return visible

    def _new_id(self, now: float) -> int:
        """Lowest ID not in use and not released within reuse_delay"""
        for track_id in [i for i, t in self._released.items() if now - t > self.reuse_delay]:
            del self._released[track_id]
        candidate = 1
        while candidate in self._tracks or candidate in self._released:
            candidate += 1
        return candidate

    def _candidate_pairs(self, detections: List[Detection], now: float) -> List[Tuple[float, int, int]]:
        pairs = []
        for track in self._tracks.values():
            px, py = track.predicted(now)
            for det_idx, det in enumerate(detections):
                if not self._similar_size(track.w, det.w):
                    continue
                scale = max(0.5 * (track.w + det.w), 0.5 * (track.h + det.h), 1e-6)
                distance = math.hypot(px - det.cx, py - det.cy) / scale
                if distance <= self.max_match_distance:
                    pairs.append((distance, track.track_id, det_idx))
        return pairs

    def _similar_size(self, a: float, b: float) -> bool:
        if a <= 0 or b <= 0:
            return True
        ratio = a / b if a > b else b / a
        return ratio <= self.max_size_ratio

    def _apply(self, track: TrackedPerson, det: Detection, now: float) -> None:
        dt = now - track.last_seen
        k = self.smoothing
        cx = track.cx + k * (det.cx - track.cx)
        cy = track.cy + k * (det.cy - track.cy)
        if 0.0 < dt <= 0.5:
            track.vx = 0.5 * track.vx + 0.5 * (cx - track.cx) / dt
            track.vy = 0.5 * track.vy + 0.5 * (cy - track.cy) / dt
        else:
            track.vx = track.vy = 0.0
        track.cx, track.cy = cx, cy
        track.w += k * (det.w - track.w)
        track.h += k * (det.h - track.h)
        if det.shoulder_width > 0:
            if track.shoulder_width > 0:
                track.shoulder_width += k * (det.shoulder_width - track.shoulder_width)
            else:
                track.shoulder_width = det.shoulder_width
        track.score = det.score
        track.gesture = det.gesture
        track.points = det.points
        track.last_seen = now
        track.hits += 1
