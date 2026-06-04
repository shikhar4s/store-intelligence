from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.emit import EventEmitter, write_jsonl


def build_demo_events(store_id: str = "STORE_BLR_002") -> list[dict]:
    emitter = EventEmitter(store_id)
    start = datetime.now(timezone.utc) - timedelta(minutes=8)
    events = []
    for index in range(5):
        visitor_id = f"VIS_DEMO_{index:02d}"
        ts = start + timedelta(minutes=index)
        events.append(
            emitter.event(
                camera_id="CAM_ENTRY_01",
                visitor_id=visitor_id,
                event_type="ENTRY",
                timestamp=ts,
                confidence=0.74,
            )
        )
        events.append(
            emitter.event(
                camera_id="CAM_MAIN_01",
                visitor_id=visitor_id,
                event_type="ZONE_ENTER",
                timestamp=ts + timedelta(seconds=40),
                zone_id="SKINCARE",
                confidence=0.71,
                metadata={"sku_zone": "SKINCARE"},
            )
        )
        events.append(
            emitter.event(
                camera_id="CAM_MAIN_01",
                visitor_id=visitor_id,
                event_type="ZONE_DWELL",
                timestamp=ts + timedelta(seconds=70),
                zone_id="SKINCARE",
                dwell_ms=30000,
                confidence=0.69,
                metadata={"sku_zone": "SKINCARE"},
            )
        )
        if index >= 2:
            events.append(
                emitter.event(
                    camera_id="CAM_BILLING_01",
                    visitor_id=visitor_id,
                    event_type="BILLING_QUEUE_JOIN",
                    timestamp=ts + timedelta(seconds=120),
                    zone_id="BILLING",
                    confidence=0.67,
                    metadata={"queue_depth": index - 1, "sku_zone": "BILLING"},
                )
            )
    return events


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a small demo JSONL event file.")
    parser.add_argument("--output", default="outputs/demo_events.jsonl")
    parser.add_argument("--store-id", default="STORE_BLR_002")
    args = parser.parse_args()
    events = build_demo_events(args.store_id)
    write_jsonl(Path(args.output), events)
    print(json.dumps({"output": args.output, "events": len(events)}))


if __name__ == "__main__":
    main()
