from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4


EVENT_TYPES = {
    "ENTRY",
    "EXIT",
    "ZONE_ENTER",
    "ZONE_EXIT",
    "ZONE_DWELL",
    "BILLING_QUEUE_JOIN",
    "BILLING_QUEUE_ABANDON",
    "REENTRY",
}


class EventEmitter:
    def __init__(self, store_id: str):
        self.store_id = store_id
        self._seq_by_visitor: dict[str, int] = {}

    def event(
        self,
        *,
        camera_id: str,
        visitor_id: str,
        event_type: str,
        timestamp: datetime,
        zone_id: Optional[str] = None,
        dwell_ms: int = 0,
        is_staff: bool = False,
        confidence: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Unsupported event_type {event_type}")
        timestamp = timestamp.astimezone(timezone.utc) if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
        seq = self._seq_by_visitor.get(visitor_id, 0) + 1
        self._seq_by_visitor[visitor_id] = seq
        payload_metadata = {"queue_depth": None, "sku_zone": None, "session_seq": seq}
        payload_metadata.update(metadata or {})
        return {
            "event_id": str(uuid4()),
            "store_id": self.store_id,
            "camera_id": camera_id,
            "visitor_id": visitor_id,
            "event_type": event_type,
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "zone_id": zone_id,
            "dwell_ms": int(max(dwell_ms, 0)),
            "is_staff": bool(is_staff),
            "confidence": round(float(max(0.0, min(1.0, confidence))), 4),
            "metadata": payload_metadata,
        }


def write_jsonl(path: str | Path, events: list[dict]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
