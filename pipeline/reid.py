from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Sequence


def stable_visitor_id(camera_id: str, track_id: int) -> str:
    digest = hashlib.sha1(f"{camera_id}:{track_id}".encode("utf-8")).hexdigest()[:8]
    return f"VIS_{digest}"


@dataclass
class RecentExit:
    visitor_id: str
    timestamp: datetime
    feature_hash: str


@dataclass
class ReIdGallery:
    ttl: timedelta = timedelta(minutes=30)
    recent_exits: list[RecentExit] = field(default_factory=list)

    def feature_hash(self, crop: Any = None, fallback: str = "") -> str:
        if crop is None:
            return hashlib.sha1(fallback.encode("utf-8")).hexdigest()[:10]
        try:
            return hashlib.sha1(bytes(crop)).hexdigest()[:10]
        except Exception:
            return hashlib.sha1(repr(crop).encode("utf-8")).hexdigest()[:10]

    def remember_exit(self, visitor_id: str, timestamp: datetime, feature_hash: str) -> None:
        self.recent_exits.append(RecentExit(visitor_id, timestamp, feature_hash))
        self.recent_exits = [item for item in self.recent_exits if timestamp - item.timestamp <= self.ttl]

    def match_reentry(self, timestamp: datetime, feature_hash: str) -> Optional[str]:
        candidates = [
            item
            for item in self.recent_exits
            if 0 <= (timestamp - item.timestamp).total_seconds() <= self.ttl.total_seconds()
        ]
        for candidate in sorted(candidates, key=lambda item: timestamp - item.timestamp):
            if candidate.feature_hash[:4] == feature_hash[:4]:
                return candidate.visitor_id
        return None
