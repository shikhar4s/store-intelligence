from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.layout_store import canonical_store_id
from app.models import EventRecord, PosTransaction
from app.timeutils import day_window, ensure_utc, isoformat_z, parse_optional_datetime, utc_now


def resolve_window(
    db: Session,
    store_id: str,
    date: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Tuple[datetime, datetime]:
    store_id = canonical_store_id(store_id)
    parsed_start = parse_optional_datetime(start)
    parsed_end = parse_optional_datetime(end)
    if parsed_start and parsed_end:
        return parsed_start, parsed_end
    if date:
        return day_window(date_type.fromisoformat(date))

    latest = (
        db.query(func.max(EventRecord.timestamp))
        .filter(EventRecord.store_id == store_id)
        .scalar()
    )
    now = utc_now()
    if latest is not None:
        latest = ensure_utc(latest)
        if latest.date() < now.date() or latest.date() > now.date():
            return day_window(latest.date())
    return day_window(now.date())


def events_in_window(db: Session, store_id: str, start: datetime, end: datetime) -> List[EventRecord]:
    store_id = canonical_store_id(store_id)
    return (
        db.query(EventRecord)
        .filter(
            EventRecord.store_id == store_id,
            EventRecord.timestamp >= start,
            EventRecord.timestamp <= end,
        )
        .order_by(EventRecord.timestamp.asc(), EventRecord.id.asc())
        .all()
    )


def pos_in_window(
    db: Session,
    store_id: str,
    start: datetime,
    end: datetime,
    include_lookback: bool = False,
) -> List[PosTransaction]:
    store_id = canonical_store_id(store_id)
    begin = start - timedelta(minutes=get_settings().pos_correlation_minutes) if include_lookback else start
    return (
        db.query(PosTransaction)
        .filter(
            PosTransaction.store_id == store_id,
            PosTransaction.timestamp >= begin,
            PosTransaction.timestamp <= end,
        )
        .order_by(PosTransaction.timestamp.asc())
        .all()
    )


def is_billing_event(event: EventRecord) -> bool:
    zone = (event.zone_id or "").upper()
    return event.event_type in {"BILLING_QUEUE_JOIN", "BILLING_QUEUE_ABANDON"} or "BILLING" in zone or "QUEUE" in zone


def non_staff(events: Iterable[EventRecord]) -> List[EventRecord]:
    return [event for event in events if not event.is_staff]


def converted_visitor_ids(
    db: Session,
    store_id: str,
    start: datetime,
    end: datetime,
    events: Optional[Sequence[EventRecord]] = None,
) -> set[str]:
    store_id = canonical_store_id(store_id)
    settings = get_settings()
    business_events = list(events) if events is not None else non_staff(events_in_window(db, store_id, start, end))
    billing_touches = [
        (event.visitor_id, ensure_utc(event.timestamp))
        for event in business_events
        if is_billing_event(event) and event.event_type != "BILLING_QUEUE_ABANDON"
    ]
    if not billing_touches:
        return set()

    converted: set[str] = set()
    transactions = pos_in_window(db, store_id, start, end, include_lookback=False)
    window = timedelta(minutes=settings.pos_correlation_minutes)
    for txn in transactions:
        txn_ts = ensure_utc(txn.timestamp)
        candidates = [
            (visitor_id, ts)
            for visitor_id, ts in billing_touches
            if visitor_id not in converted and txn_ts - window <= ts <= txn_ts
        ]
        if not candidates:
            continue
        candidates.sort(key=lambda item: abs((txn_ts - item[1]).total_seconds()))
        converted.add(candidates[0][0])
    return converted


def current_queue_depth(events: Sequence[EventRecord]) -> int:
    active: set[str] = set()
    latest_depth: Optional[int] = None
    latest_depth_ts: Optional[datetime] = None
    for event in events:
        metadata = event.event_metadata or {}
        source_event_type = str(metadata.get("source_event_type") or "").lower()
        terminal_queue_sample = source_event_type in {"queue_completed", "queue_abandoned"} or bool(metadata.get("queue_exit_ts"))
        if isinstance(metadata.get("queue_depth"), int) and not terminal_queue_sample:
            latest_depth = max(0, metadata["queue_depth"])
            latest_depth_ts = ensure_utc(event.timestamp)
        if event.event_type == "BILLING_QUEUE_JOIN" or (
            event.event_type == "ZONE_ENTER" and is_billing_event(event)
        ):
            active.add(event.visitor_id)
            if terminal_queue_sample:
                active.discard(event.visitor_id)
        if event.event_type in {"BILLING_QUEUE_ABANDON", "ZONE_EXIT", "EXIT"} and is_billing_event(event):
            active.discard(event.visitor_id)
    if latest_depth is not None and latest_depth_ts is not None:
        return max(latest_depth, len(active))
    return len(active)


def avg_dwell_by_zone(events: Sequence[EventRecord]) -> dict[str, float]:
    values: dict[str, list[int]] = defaultdict(list)
    for event in events:
        if event.event_type == "ZONE_DWELL" and event.zone_id:
            values[event.zone_id].append(event.dwell_ms)
    return {zone_id: round(sum(dwell) / len(dwell), 2) for zone_id, dwell in values.items() if dwell}


def data_confidence(events: Sequence[EventRecord], unique_visitors: int) -> dict:
    if not events:
        return {"is_confident": False, "reason": "no_events_for_window"}
    if unique_visitors < 20:
        return {"is_confident": False, "reason": "fewer_than_20_sessions"}
    avg_confidence = statistics.mean(event.confidence for event in events)
    if avg_confidence < 0.35:
        return {"is_confident": False, "reason": "low_average_detection_confidence"}
    return {"is_confident": True, "reason": "sufficient_session_count_and_confidence"}


def compute_metrics(
    db: Session,
    store_id: str,
    date: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> dict:
    store_id = canonical_store_id(store_id)
    window_start, window_end = resolve_window(db, store_id, date=date, start=start, end=end)
    all_events = events_in_window(db, store_id, window_start, window_end)
    business_events = non_staff(all_events)
    visitors = {event.visitor_id for event in business_events}
    converted = converted_visitor_ids(db, store_id, window_start, window_end, business_events)
    billing_visitors = {event.visitor_id for event in business_events if is_billing_event(event)}
    abandon_visitors = {
        event.visitor_id for event in business_events if event.event_type == "BILLING_QUEUE_ABANDON"
    }
    last_event = max((ensure_utc(event.timestamp) for event in all_events), default=None)
    unique_count = len(visitors)
    conversion_rate = (len(converted) / unique_count) if unique_count else 0.0
    abandonment_rate = (len(abandon_visitors) / len(billing_visitors)) if billing_visitors else 0.0

    return {
        "store_id": store_id,
        "window_start": isoformat_z(window_start),
        "window_end": isoformat_z(window_end),
        "unique_visitors": unique_count,
        "entry_count": sum(1 for event in business_events if event.event_type == "ENTRY"),
        "exit_count": sum(1 for event in business_events if event.event_type == "EXIT"),
        "conversion_rate": round(conversion_rate, 4),
        "avg_dwell_ms_by_zone": avg_dwell_by_zone(business_events),
        "current_queue_depth": current_queue_depth(business_events),
        "abandonment_rate": round(abandonment_rate, 4),
        "last_event_timestamp": isoformat_z(last_event),
        "data_confidence": data_confidence(business_events, unique_count),
    }
