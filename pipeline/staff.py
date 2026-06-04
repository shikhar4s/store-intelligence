from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional


@dataclass
class TrackStats:
    first_seen: datetime
    last_seen: datetime
    zone_ids: set[str] = field(default_factory=set)
    entry_exit_count: int = 0


@dataclass
class StaffHeuristic:
    min_duration_minutes: int = 12
    min_zone_count: int = 3
    repeated_entry_exit_count: int = 4
    stats: Dict[str, TrackStats] = field(default_factory=dict)

    def update(self, visitor_id: str, timestamp: datetime, zone_id: Optional[str], event_type: Optional[str]) -> tuple[bool, float, str]:
        item = self.stats.get(visitor_id)
        if item is None:
            item = TrackStats(first_seen=timestamp, last_seen=timestamp)
            self.stats[visitor_id] = item
        item.last_seen = timestamp
        if zone_id:
            item.zone_ids.add(zone_id)
        if event_type in {"ENTRY", "EXIT", "REENTRY"}:
            item.entry_exit_count += 1

        duration = item.last_seen - item.first_seen
        if duration >= timedelta(minutes=self.min_duration_minutes) and len(item.zone_ids) >= self.min_zone_count:
            return True, 0.72, "long_duration_multi_zone_presence"
        if item.entry_exit_count >= self.repeated_entry_exit_count:
            return True, 0.68, "repeated_entry_exit_pattern"
        return False, 0.35, "customer_like_short_track"
