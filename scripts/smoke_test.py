from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from uuid import uuid4


def request_json(method: str, url: str, body=None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = response.read().decode("utf-8")
        return json.loads(payload) if payload else {}


def event(event_type: str, visitor_id: str, timestamp, zone_id=None, metadata=None, is_staff=False):
    return {
        "event_id": str(uuid4()),
        "store_id": "STORE_BLR_002",
        "camera_id": "CAM_ENTRY_01" if event_type in {"ENTRY", "EXIT", "REENTRY"} else "CAM_MAIN_01",
        "visitor_id": visitor_id,
        "event_type": event_type,
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "zone_id": zone_id,
        "dwell_ms": 30000 if event_type == "ZONE_DWELL" else 0,
        "is_staff": is_staff,
        "confidence": 0.72,
        "metadata": {"queue_depth": None, "sku_zone": zone_id, "session_seq": 1, **(metadata or {})},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Exercise the running API end to end.")
    parser.add_argument("--url", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    now = datetime.now(timezone.utc) - timedelta(minutes=2)
    events = [
        event("ENTRY", "VIS_SMOKE_01", now),
        event("ZONE_ENTER", "VIS_SMOKE_01", now + timedelta(seconds=20), "SKINCARE"),
        event("ZONE_DWELL", "VIS_SMOKE_01", now + timedelta(seconds=50), "SKINCARE"),
        event("BILLING_QUEUE_JOIN", "VIS_SMOKE_01", now + timedelta(seconds=80), "BILLING", {"queue_depth": 1}),
        event("ENTRY", "VIS_STAFF_01", now, is_staff=True),
    ]
    try:
        health = request_json("GET", f"{base}/health")
        ingest = request_json("POST", f"{base}/events/ingest", {"events": events})
        metrics = request_json("GET", f"{base}/stores/STORE_BLR_002/metrics")
        funnel = request_json("GET", f"{base}/stores/STORE_BLR_002/funnel")
        heatmap = request_json("GET", f"{base}/stores/STORE_BLR_002/heatmap")
        anomalies = request_json("GET", f"{base}/stores/STORE_BLR_002/anomalies")
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)

    checks = [
        health.get("status") in {"OK", "WARN"},
        ingest.get("accepted_count", 0) >= 4 or ingest.get("duplicate_count", 0) >= 4,
        metrics.get("unique_visitors", 0) >= 1,
        funnel.get("stages") is not None,
        heatmap.get("zones") is not None,
        anomalies.get("anomalies") is not None,
    ]
    result = {
        "ok": all(checks),
        "health": health.get("status"),
        "ingest": ingest,
        "metrics_unique_visitors": metrics.get("unique_visitors"),
        "anomaly_count": len(anomalies.get("anomalies", [])),
    }
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if all(checks) else 1)


if __name__ == "__main__":
    main()
