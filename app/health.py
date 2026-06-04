from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.database import ping_database
from app.layout_store import store_layouts
from app.models import EventRecord
from app.timeutils import ensure_utc, isoformat_z, utc_now

STARTED_AT = utc_now()


def health_status(db: Session) -> dict:
    settings = get_settings()
    database_ok = ping_database()
    now = utc_now()
    rows = (
        db.query(EventRecord.store_id, func.max(EventRecord.timestamp))
        .group_by(EventRecord.store_id)
        .all()
        if database_ok
        else []
    )
    last_event_by_store = {
        str(store.get("store_id")): None for store in store_layouts() if store.get("store_id")
    }
    stale_warnings = []
    for store_id, last_ts in rows:
        last_ts = ensure_utc(last_ts)
        last_event_by_store[store_id] = isoformat_z(last_ts)
        lag_minutes = (now - last_ts).total_seconds() / 60
        if lag_minutes > settings.stale_feed_minutes:
            stale_warnings.append(
                {
                    "store_id": store_id,
                    "type": "STALE_FEED",
                    "lag_minutes": round(lag_minutes, 2),
                    "message": f"No events for more than {settings.stale_feed_minutes} minutes.",
                }
            )

    if not database_ok:
        status = "ERROR"
    elif stale_warnings:
        status = "WARN"
    else:
        status = "OK"
    return {
        "status": status,
        "database": {"status": "OK" if database_ok else "ERROR"},
        "last_event_timestamp_by_store": last_event_by_store,
        "warnings": stale_warnings,
        "version": __version__,
        "build": {"environment": settings.environment},
        "uptime_seconds": round((now - STARTED_AT).total_seconds(), 2),
    }
