from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ingestion import ingest_payload
from app.models import EventRecord, PosTransaction
from app.pos import ingest_pos_payload
from pipeline.emit import EventEmitter


logger = logging.getLogger("store_intelligence.bootstrap")


def _demo_events_for_store(store_id: str, *, start: datetime, zone_id: str, billing_zone_id: str) -> list[dict]:
    emitter = EventEmitter(store_id)
    events: list[dict] = []
    for index in range(24):
        visitor_id = f"VIS_DEMO_{store_id[-4:]}_{index:02d}"
        ts = start + timedelta(seconds=index * 25)
        events.append(
            emitter.event(
                camera_id=f"{store_id}_CAM_ENTRY_01",
                visitor_id=visitor_id,
                event_type="ENTRY",
                timestamp=ts,
                confidence=0.78,
                metadata={"source": "vercel_demo_seed"},
            )
        )
        events.append(
            emitter.event(
                camera_id=f"{store_id}_CAM_MAIN_01",
                visitor_id=visitor_id,
                event_type="ZONE_ENTER",
                timestamp=ts + timedelta(seconds=18),
                zone_id=zone_id,
                confidence=0.74,
                metadata={"sku_zone": "SKINCARE", "source": "vercel_demo_seed"},
            )
        )
        events.append(
            emitter.event(
                camera_id=f"{store_id}_CAM_MAIN_01",
                visitor_id=visitor_id,
                event_type="ZONE_DWELL",
                timestamp=ts + timedelta(seconds=48),
                zone_id=zone_id,
                dwell_ms=30000,
                confidence=0.71,
                metadata={"sku_zone": "SKINCARE", "source": "vercel_demo_seed"},
            )
        )
        if index % 3 == 0:
            queue_depth = 1 + (index % 6)
            events.append(
                emitter.event(
                    camera_id=f"{store_id}_CAM_BILLING_01",
                    visitor_id=visitor_id,
                    event_type="BILLING_QUEUE_JOIN",
                    timestamp=ts + timedelta(seconds=70),
                    zone_id=billing_zone_id,
                    confidence=0.69,
                    metadata={"queue_depth": queue_depth, "sku_zone": "BILLING", "source": "vercel_demo_seed"},
                )
            )
    return events


def _demo_pos_for_store(store_id: str, events: list[dict]) -> list[dict]:
    transactions = []
    billing_events = [event for event in events if event["store_id"] == store_id and event["event_type"] == "BILLING_QUEUE_JOIN"]
    for index, event in enumerate(billing_events[:5]):
        event_ts = datetime.fromisoformat(str(event["timestamp"]).replace("Z", "+00:00"))
        transactions.append(
            {
                "store_id": store_id,
                "transaction_id": f"VERCEL_DEMO_{store_id}_{index:02d}",
                "timestamp": (event_ts + timedelta(seconds=75)).isoformat().replace("+00:00", "Z"),
                "amount": 999.0 + index * 125.0,
                "source": "vercel_demo_seed",
            }
        )
    return transactions


def seed_demo_data_if_needed(db: Session) -> None:
    existing_count = db.query(func.count(EventRecord.id)).scalar() or 0
    if int(existing_count) > 0:
        return

    start = datetime.now(timezone.utc) - timedelta(minutes=12)
    events = []
    events.extend(
        _demo_events_for_store(
            "STORE_BLR_002",
            start=start,
            zone_id="SKINCARE",
            billing_zone_id="BILLING",
        )
    )
    events.extend(
        _demo_events_for_store(
            "STORE_MUM_1076",
            start=start + timedelta(minutes=1),
            zone_id="PURPLLE_MUM_1076_Z01",
            billing_zone_id="PURPLLE_MUM_1076_Z_BILLING_01",
        )
    )
    response = ingest_payload(db, {"events": events}, trace_id="bootstrap_demo")
    transactions = _demo_pos_for_store("STORE_BLR_002", events) + _demo_pos_for_store("STORE_MUM_1076", events)
    ingest_pos_payload(db, {"transactions": transactions})
    logger.info(
        "seeded_demo_data",
        extra={
            "accepted_events": response.accepted_count,
            "pos_transactions": len(transactions),
        },
    )
