# PROMPT: Generate robust tests for queue spike, dead zone, and conversion drop anomaly behavior.
# CHANGES MADE: Built deterministic current and historical windows so anomalies come from computation rather than fixtures.

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tests.conftest import make_event, make_pos


def test_queue_spike_and_dead_zone_anomalies(client):
    ts = datetime(2026, 4, 10, 17, 0, tzinfo=timezone.utc)
    events = [
        make_event("ENTRY", "VIS_Q1", ts),
        make_event("ZONE_ENTER", "VIS_Q1", ts + timedelta(minutes=1), "SKINCARE"),
        make_event("BILLING_QUEUE_JOIN", "VIS_Q1", ts + timedelta(minutes=2), "BILLING", queue_depth=1),
        make_event("BILLING_QUEUE_JOIN", "VIS_Q2", ts + timedelta(minutes=3), "BILLING", queue_depth=6),
    ]
    client.post("/events/ingest", json=events)
    payload = client.get("/stores/STORE_BLR_002/anomalies?date=2026-04-10").json()
    kinds = {item["type"] for item in payload["anomalies"]}
    assert "BILLING_QUEUE_SPIKE" in kinds
    assert "DEAD_ZONE" in kinds


def test_conversion_drop_against_history(client):
    current = datetime(2026, 4, 10, 11, 0, tzinfo=timezone.utc)
    for days_back in (1, 2):
        ts = current - timedelta(days=days_back)
        visitor = f"VIS_HIST_{days_back}"
        client.post(
            "/events/ingest",
            json=[
                make_event("ENTRY", visitor, ts),
                make_event("BILLING_QUEUE_JOIN", visitor, ts + timedelta(minutes=1), "BILLING", queue_depth=1),
            ],
        )
        client.post("/pos/ingest", json=[make_pos(f"TXN_HIST_{days_back}", ts + timedelta(minutes=3))])
    client.post(
        "/events/ingest",
        json=[
            make_event("ENTRY", "VIS_CURRENT", current),
            make_event("BILLING_QUEUE_JOIN", "VIS_CURRENT", current + timedelta(minutes=1), "BILLING", queue_depth=1),
        ],
    )
    payload = client.get("/stores/STORE_BLR_002/anomalies?date=2026-04-10").json()
    conversion = [item for item in payload["anomalies"] if item["type"] == "CONVERSION_DROP"]
    assert conversion
    assert conversion[0]["severity"] in {"WARN", "CRITICAL"}
