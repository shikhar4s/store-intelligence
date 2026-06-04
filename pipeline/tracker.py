from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Sequence, Tuple


def _centroid(box: Sequence[float]) -> Tuple[float, float]:
    x1, y1, x2, y2 = box[:4]
    return (float(x1 + x2) / 2.0, float(y1 + y2) / 2.0)


@dataclass
class Track:
    track_id: int
    box: Sequence[float]
    confidence: float
    missed: int = 0
    age: int = 1


@dataclass
class CentroidTracker:
    max_distance: float = 80.0
    max_missed: int = 8
    _next_id: int = 1
    tracks: Dict[int, Track] = field(default_factory=dict)

    def update(self, detections: Iterable[tuple[Sequence[float], float]]) -> List[Track]:
        detections = list(detections)
        unmatched_tracks = set(self.tracks)
        assigned: set[int] = set()
        updated: Dict[int, Track] = {}

        for box, confidence in detections:
            cx, cy = _centroid(box)
            best_id = None
            best_distance = self.max_distance
            for track_id in list(unmatched_tracks):
                tcx, tcy = _centroid(self.tracks[track_id].box)
                distance = ((cx - tcx) ** 2 + (cy - tcy) ** 2) ** 0.5
                if distance < best_distance:
                    best_id = track_id
                    best_distance = distance
            if best_id is None:
                best_id = self._next_id
                self._next_id += 1
                age = 1
            else:
                unmatched_tracks.discard(best_id)
                age = self.tracks[best_id].age + 1
            updated[best_id] = Track(best_id, box, confidence, missed=0, age=age)
            assigned.add(best_id)

        for track_id in unmatched_tracks:
            old = self.tracks[track_id]
            if old.missed + 1 <= self.max_missed:
                updated[track_id] = Track(track_id, old.box, old.confidence, missed=old.missed + 1, age=old.age + 1)

        self.tracks = updated
        return [track for track in self.tracks.values() if track.track_id in assigned]
