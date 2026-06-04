# PROMPT: Generate robust tests for real-time metrics including empty stores, staff exclusion, zero purchases, POS conversion, and abandonment.
# CHANGES MADE: Tightened session-level expectations and added explicit POS timestamp correlation inside the five-minute window.

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tests.conftest import make_event, make_pos


def test_empty_store_metrics_do_not_crash(client):
    response = client.get("/stores/EMPTY/metrics")
    payload = response.json()
    assert response.status_code == 200
    assert payload["unique_visitors"] == 0
    assert payload["conversion_rate"] == 0.0
    assert payload["avg_dwell_ms_by_zone"] == {}
    assert payload["data_confidence"]["is_confident"] is False


def test_metrics_alias_uses_default_store_for_evaluator_shorthand(client):
    ts = datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc)
    client.post("/events/ingest", json=[make_event("ENTRY", "VIS_ALIAS", ts)])
    payload = client.get("/metrics?date=2026-04-10").json()
    assert payload["store_id"] == "STORE_BLR_002"
    assert payload["unique_visitors"] == 1


def test_all_staff_events_are_excluded(client):
    ts = datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc)
    events = [
        make_event("ENTRY", "VIS_STAFF", ts, is_staff=True),
        make_event("ZONE_DWELL", "VIS_STAFF", ts + timedelta(seconds=30), "SKINCARE", is_staff=True, dwell_ms=30000),
    ]
    client.post("/events/ingest", json=events)
    payload = client.get("/stores/STORE_BLR_002/metrics?date=2026-04-10").json()
    assert payload["unique_visitors"] == 0
    assert payload["entry_count"] == 0
    assert payload["avg_dwell_ms_by_zone"] == {}


def test_zero_purchases_conversion_rate_is_zero(client):
    client.post("/events/ingest", json=[make_event("ENTRY", "VIS_1")])
    payload = client.get("/stores/STORE_BLR_002/metrics?date=2026-04-10").json()
    assert payload["unique_visitors"] == 1
    assert payload["conversion_rate"] == 0.0


def test_billing_pos_conversion_correlation(client):
    ts = datetime(2026, 4, 10, 11, 0, tzinfo=timezone.utc)
    events = [
        make_event("ENTRY", "VIS_BUYER", ts),
        make_event("BILLING_QUEUE_JOIN", "VIS_BUYER", ts + timedelta(minutes=3), "BILLING", queue_depth=2),
    ]
    client.post("/events/ingest", json=events)
    client.post("/pos/ingest", json={"transactions": [make_pos("TXN_1", ts + timedelta(minutes=7))]})
    payload = client.get("/stores/STORE_BLR_002/metrics?date=2026-04-10").json()
    assert payload["conversion_rate"] == 1.0
    assert payload["current_queue_depth"] == 2


def test_queue_abandonment_rate(client):
    ts = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)
    events = [
        make_event("ENTRY", "VIS_A", ts),
        make_event("BILLING_QUEUE_JOIN", "VIS_A", ts + timedelta(minutes=1), "BILLING", queue_depth=1),
        make_event("BILLING_QUEUE_ABANDON", "VIS_A", ts + timedelta(minutes=8), "BILLING", queue_depth=0),
    ]
    client.post("/events/ingest", json=events)
    payload = client.get("/stores/STORE_BLR_002/metrics?date=2026-04-10").json()
    assert payload["abandonment_rate"] == 1.0
    assert payload["current_queue_depth"] == 0
