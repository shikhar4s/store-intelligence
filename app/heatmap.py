from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session

from app.layout_store import canonical_store_id, known_zones
from app.metrics import events_in_window, non_staff, resolve_window
from app.timeutils import isoformat_z


def compute_heatmap(
    db: Session,
    store_id: str,
    date: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> dict:
    store_id = canonical_store_id(store_id)
    window_start, window_end = resolve_window(db, store_id, date=date, start=start, end=end)
    events = non_staff(events_in_window(db, store_id, window_start, window_end))
    sessions = {event.visitor_id for event in events}
    visit_counts: dict[str, int] = defaultdict(int)
    dwell_values: dict[str, list[int]] = defaultdict(list)
    sku_by_zone: dict[str, str | None] = {}

    for zone in known_zones(store_id):
        zone_id = str(zone["zone_id"])
        visit_counts.setdefault(zone_id, 0)
        sku_by_zone[zone_id] = zone.get("sku_zone")

    for event in events:
        if not event.zone_id:
            continue
        metadata = event.event_metadata or {}
        sku_by_zone.setdefault(event.zone_id, metadata.get("sku_zone"))
        if event.event_type == "ZONE_ENTER":
            visit_counts[event.zone_id] += 1
        elif event.event_type == "ZONE_DWELL":
            dwell_values[event.zone_id].append(event.dwell_ms)

    max_visits = max(visit_counts.values(), default=0)
    zones = []
    for zone_id in sorted(visit_counts):
        visits = visit_counts[zone_id]
        dwell = dwell_values.get(zone_id, [])
        avg_dwell = round(sum(dwell) / len(dwell), 2) if dwell else 0.0
        score = round((visits / max_visits * 100), 2) if max_visits else 0.0
        zones.append(
            {
                "zone_id": zone_id,
                "sku_zone": sku_by_zone.get(zone_id),
                "visits": visits,
                "avg_dwell_ms": avg_dwell,
                "normalized_score_0_100": score,
            }
        )

    return {
        "store_id": store_id,
        "window_start": isoformat_z(window_start),
        "window_end": isoformat_z(window_end),
        "zones": zones,
        "data_confidence": {
            "is_confident": len(sessions) >= 20,
            "reason": "sufficient_sessions" if len(sessions) >= 20 else "fewer_than_20_sessions",
        },
    }
