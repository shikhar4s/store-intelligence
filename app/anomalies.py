from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.funnel import compute_funnel
from app.heatmap import compute_heatmap
from app.layout_store import canonical_store_id, known_zones
from app.metrics import compute_metrics, events_in_window, non_staff, resolve_window
from app.timeutils import ensure_utc, isoformat_z, utc_now


def _anomaly(kind: str, severity: str, message: str, evidence: dict, suggested_action: str, detected_at) -> dict:
    return {
        "type": kind,
        "severity": severity,
        "message": message,
        "evidence": evidence,
        "suggested_action": suggested_action,
        "detected_at": isoformat_z(detected_at),
    }


def _conversion_history(db: Session, store_id: str, current_start, current_end) -> list[float]:
    rates = []
    for days_back in range(1, 8):
        start = current_start - timedelta(days=days_back)
        end = current_end - timedelta(days=days_back)
        metrics = compute_metrics(db, store_id, start=start.isoformat(), end=end.isoformat())
        if metrics["unique_visitors"] > 0:
            rates.append(metrics["conversion_rate"])
    return rates


def compute_anomalies(
    db: Session,
    store_id: str,
    date: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> dict:
    store_id = canonical_store_id(store_id)
    window_start, window_end = resolve_window(db, store_id, date=date, start=start, end=end)
    all_events = events_in_window(db, store_id, window_start, window_end)
    events = non_staff(all_events)
    detected_at = max((ensure_utc(event.timestamp) for event in all_events), default=utc_now())
    metrics = compute_metrics(db, store_id, start=window_start.isoformat(), end=window_end.isoformat())
    anomalies = []

    queue_depths = [
        int((event.event_metadata or {}).get("queue_depth"))
        for event in events
        if isinstance((event.event_metadata or {}).get("queue_depth"), int)
    ]
    current_depth = metrics["current_queue_depth"]
    baseline = statistics.median(queue_depths) if queue_depths else 0
    if current_depth >= 3 and current_depth >= max(3, baseline + 2):
        anomalies.append(
            _anomaly(
                "BILLING_QUEUE_SPIKE",
                "CRITICAL" if current_depth >= 6 else "WARN",
                "Billing queue depth is above the recent baseline.",
                {"current_queue_depth": current_depth, "rolling_median_queue_depth": baseline},
                "Open another billing counter or move floor staff to checkout support.",
                detected_at,
            )
        )

    history = _conversion_history(db, store_id, window_start, window_end)
    current_conversion = metrics["conversion_rate"]
    if len(history) < 2:
        anomalies.append(
            _anomaly(
                "CONVERSION_DROP",
                "INFO",
                "Insufficient 7-day history to assert a conversion drop.",
                {"current_conversion_rate": current_conversion, "history_days": len(history)},
                "Continue collecting events and POS data before acting on conversion trend.",
                detected_at,
            )
        )
    else:
        baseline_conversion = statistics.mean(history)
        if current_conversion < baseline_conversion * 0.6:
            anomalies.append(
                _anomaly(
                    "CONVERSION_DROP",
                    "CRITICAL" if current_conversion < baseline_conversion * 0.4 else "WARN",
                    "Current conversion rate is materially below the 7-day baseline.",
                    {
                        "current_conversion_rate": current_conversion,
                        "baseline_7_day_conversion_rate": round(baseline_conversion, 4),
                    },
                    "Inspect staffing, queue depth, and stock availability for the affected window.",
                    detected_at,
                )
            )

    recent_cutoff = detected_at - timedelta(minutes=30)
    zone_recent_visits: dict[str, int] = defaultdict(int)
    for event in events:
        if event.zone_id and event.event_type in {"ZONE_ENTER", "ZONE_DWELL"} and ensure_utc(event.timestamp) >= recent_cutoff:
            zone_recent_visits[event.zone_id] += 1
    for zone in known_zones(store_id):
        zone_id = str(zone["zone_id"])
        if zone_id.upper().startswith("ENTRY"):
            continue
        if zone_recent_visits.get(zone_id, 0) == 0 and events:
            anomalies.append(
                _anomaly(
                    "DEAD_ZONE",
                    "WARN",
                    f"No recent customer activity detected in zone {zone_id}.",
                    {"zone_id": zone_id, "lookback_minutes": 30},
                    "Check camera coverage, merchandising visibility, and whether the zone is blocked.",
                    detected_at,
                )
            )

    return {
        "store_id": store_id,
        "window_start": isoformat_z(window_start),
        "window_end": isoformat_z(window_end),
        "anomalies": anomalies,
        "data_confidence": metrics["data_confidence"],
    }
