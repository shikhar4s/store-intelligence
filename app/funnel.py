from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.layout_store import canonical_store_id
from app.metrics import converted_visitor_ids, events_in_window, is_billing_event, non_staff, resolve_window


def _stage(name: str, count: int, previous_count: int | None) -> dict:
    if previous_count is None or previous_count == 0:
        drop = 0.0
    else:
        drop = round(max(previous_count - count, 0) / previous_count * 100, 2)
    return {"stage": name, "count": count, "drop_off_pct_from_previous": drop}


def compute_funnel(
    db: Session,
    store_id: str,
    date: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> dict:
    store_id = canonical_store_id(store_id)
    window_start, window_end = resolve_window(db, store_id, date=date, start=start, end=end)
    events = non_staff(events_in_window(db, store_id, window_start, window_end))

    entry = {event.visitor_id for event in events if event.event_type in {"ENTRY", "REENTRY"}}
    any_session = {event.visitor_id for event in events}
    if not entry and any_session:
        entry = any_session
    zone_visit = {
        event.visitor_id
        for event in events
        if event.event_type in {"ZONE_ENTER", "ZONE_DWELL", "ZONE_EXIT"} and not is_billing_event(event)
    }
    billing = {event.visitor_id for event in events if is_billing_event(event)}
    purchase = converted_visitor_ids(db, store_id, window_start, window_end, events)

    stages = [
        _stage("Entry", len(entry), None),
        _stage("Zone Visit", len(zone_visit), len(entry)),
        _stage("Billing Queue", len(billing), len(zone_visit)),
        _stage("Purchase", len(purchase), len(billing)),
    ]
    total_sessions = len(entry)
    return {
        "store_id": store_id,
        "window_start": window_start.isoformat().replace("+00:00", "Z"),
        "window_end": window_end.isoformat().replace("+00:00", "Z"),
        "total_sessions": total_sessions,
        "stages": stages,
        "data_confidence": {
            "is_confident": total_sessions >= 20,
            "reason": "sufficient_sessions" if total_sessions >= 20 else "fewer_than_20_sessions",
        },
    }
