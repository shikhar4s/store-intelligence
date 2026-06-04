from __future__ import annotations

from sqlalchemy.orm import Session

from app.health import health_status
from app.stores import list_stores
from app.timeutils import utc_now
from app.video_demo import live_stream_summaries


def _notification(
    *,
    code: str,
    severity: str,
    title: str,
    message: str,
    source: str,
    store_id: str | None = None,
) -> dict:
    return {
        "code": code,
        "severity": severity,
        "title": title,
        "message": message,
        "source": source,
        "store_id": store_id,
        "created_at": utc_now().isoformat().replace("+00:00", "Z"),
    }


def list_notifications(db: Session, limit: int = 6) -> dict:
    """Return only operationally useful notifications for the UI bell."""

    notifications: list[dict] = []
    for stream in live_stream_summaries():
        status = str(stream.get("status") or "unknown")
        if stream.get("tracking_warning"):
            notifications.append(
                _notification(
                    code="LIVE_TRACKER_FALLBACK",
                    severity="WARN",
                    title="Live tracker is using fallback",
                    message=(
                        f"{stream.get('clip') or 'Selected clip'} is still processing, but "
                        f"tracker backend switched to {stream.get('tracker_backend') or 'centroid'}."
                    ),
                    source="video-demo",
                    store_id=stream.get("store_id"),
                )
            )
        if stream.get("running"):
            notifications.append(
                _notification(
                    code="LIVE_DETECTION_RUNNING",
                    severity="INFO",
                    title="Live detection is running",
                    message=(
                        f"{stream.get('clip') or 'Selected clip'} is processing with "
                        f"{stream.get('model') or 'the selected model'} at frame {stream.get('frame_index') or 0}."
                    ),
                    source="video-demo",
                    store_id=stream.get("store_id"),
                )
            )
        elif "unavailable" in status or "failed" in status or "error" in status:
            notifications.append(
                _notification(
                    code="LIVE_DETECTION_ATTENTION",
                    severity="WARN",
                    title="Live detection needs attention",
                    message=f"{stream.get('clip') or 'A clip'} stopped with status: {status}.",
                    source="video-demo",
                    store_id=stream.get("store_id"),
                )
            )

    health = health_status(db)
    if health.get("database", {}).get("status") != "OK":
        notifications.append(
            _notification(
                code="DATABASE_UNAVAILABLE",
                severity="CRITICAL",
                title="Database is unavailable",
                message="Metrics cannot load until SQLite/Postgres is reachable.",
                source="health",
            )
        )

    for warning in health.get("warnings") or []:
        notifications.append(
            _notification(
                code=str(warning.get("type") or "HEALTH_WARNING"),
                severity="WARN",
                title="Feed may be stale",
                message=str(warning.get("message") or "A store feed has not received recent events."),
                source="health",
                store_id=warning.get("store_id"),
            )
        )

    stores = list_stores(db).get("stores", [])
    for store in stores:
        if int(store.get("event_count") or 0) == 0:
            notifications.append(
                _notification(
                    code="NO_EVENTS_FOR_STORE",
                    severity="INFO",
                    title="Store has no events yet",
                    message=f"{store.get('display_name') or store.get('store_id')} has no ingested events. Run replay or wait for processing to finish.",
                    source="stores",
                    store_id=store.get("store_id"),
                )
            )

    priority = {"CRITICAL": 0, "WARN": 1, "INFO": 2}
    notifications.sort(key=lambda item: (priority.get(str(item.get("severity")), 9), item.get("code") or ""))
    capped = notifications[: max(1, min(limit, 6))]
    return {
        "notifications": capped,
        "count": len(capped),
        "has_more": len(notifications) > len(capped),
        "generated_at": utc_now().isoformat().replace("+00:00", "Z"),
    }
