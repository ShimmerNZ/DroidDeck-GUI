#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lightweight multi-person tracker.

Assigns stable integer IDs to face detections across frames by greedily
matching each detection to the nearest existing track, measured in units of
the average box size so that fast movers and blurred frames still match.
Pure Python, no dependencies, safe to run inside the image processing thread.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

# (centre x, centre y, width, height, confidence), all normalised 0..1
Detection = Tuple[float, float, float, float, float]


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
    hits: int = 1

    def as_dict(self) -> Dict[str, float]:
        return {
            "id": self.track_id,
            "cx": round(self.cx, 4),
            "cy": round(self.cy, 4),
            "w": round(self.w, 4),
            "h": round(self.h, 4),
            "score": round(self.score, 3),
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
        briefly keeps the same ID
    """

    def __init__(self, max_missed: float = 1.5, report_grace: float = 0.4,
                 min_hits: int = 2, max_match_distance: float = 1.0):
        self.max_missed = max_missed
        self.report_grace = report_grace
        self.min_hits = min_hits
        self.max_match_distance = max_match_distance
        self._tracks: Dict[int, TrackedPerson] = {}
        self._next_id = 1

    def reset(self) -> None:
        self._tracks.clear()

    def update(self, detections: List[Detection], now: float) -> List[Dict[str, float]]:
        """Match detections to tracks and return the confirmed, recently seen people."""
        pairs = self._candidate_pairs(detections)
        pairs.sort(key=lambda p: p[0])

        used_tracks = set()
        used_detections = set()
        for distance, track_id, det_idx in pairs:
            if track_id in used_tracks or det_idx in used_detections:
                continue
            used_tracks.add(track_id)
            used_detections.add(det_idx)
            self._apply(self._tracks[track_id], detections[det_idx], now)

        for det_idx, det in enumerate(detections):
            if det_idx in used_detections:
                continue
            track = TrackedPerson(
                track_id=self._next_id, cx=det[0], cy=det[1], w=det[2], h=det[3],
                score=det[4], first_seen=now, last_seen=now,
            )
            self._tracks[track.track_id] = track
            self._next_id += 1

        for track_id in [t.track_id for t in self._tracks.values()
                         if now - t.last_seen > self.max_missed]:
            del self._tracks[track_id]

        visible = [
            t for t in self._tracks.values()
            if t.hits >= self.min_hits and now - t.last_seen <= self.report_grace
        ]
        visible.sort(key=lambda t: t.track_id)
        return [t.as_dict() for t in visible]

    def _candidate_pairs(self, detections: List[Detection]) -> List[Tuple[float, int, int]]:
        pairs = []
        for track in self._tracks.values():
            for det_idx, det in enumerate(detections):
                scale = max(0.5 * (track.w + det[2]), 0.5 * (track.h + det[3]), 1e-6)
                distance = math.hypot(track.cx - det[0], track.cy - det[1]) / scale
                if distance <= self.max_match_distance:
                    pairs.append((distance, track.track_id, det_idx))
        return pairs

    @staticmethod
    def _apply(track: TrackedPerson, det: Detection, now: float) -> None:
        track.cx, track.cy, track.w, track.h, track.score = det
        track.last_seen = now
        track.hits += 1
