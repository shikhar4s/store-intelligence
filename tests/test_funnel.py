# PROMPT: Generate robust tests for session-based funnel computation, reentry deduplication, and purchase stage correlation.
# CHANGES MADE: Used one visitor_id across ENTRY and REENTRY to prove the funnel counts sessions, not raw event rows.

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tests.conftest import make_event, make_pos


def test_reentry_not_double_counted_in_funnel(client):
    ts = datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc)
    events = [
        make_event("ENTRY", "VIS_REPEAT", ts),
        make_event("EXIT", "VIS_REPEAT", ts + timedelta(minutes=5)),
        make_event("REENTRY", "VIS_REPEAT", ts + timedelta(minutes=8)),
        make_event("ZONE_ENTER", "VIS_REPEAT", ts + timedelta(minutes=9), "MAKEUP"),
    ]
    client.post("/events/ingest", json=events)
    payload = client.get("/stores/STORE_BLR_002/funnel?date=2026-04-10").json()
    stages = {stage["stage"]: stage["count"] for stage in payload["stages"]}
    assert payload["total_sessions"] == 1
    assert stages["Entry"] == 1
    assert stages["Zone Visit"] == 1


def test_funnel_alias_uses_default_store_for_evaluator_shorthand(client):
    ts = datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc)
    client.post(
        "/events/ingest",
        json=[
            make_event("ENTRY", "VIS_ALIAS_FUNNEL", ts),
            make_event("ZONE_ENTER", "VIS_ALIAS_FUNNEL", ts + timedelta(minutes=1), "MAKEUP"),
        ],
    )
    payload = client.get("/funnel?date=2026-04-10").json()
    assert payload["store_id"] == "STORE_BLR_002"
    assert payload["total_sessions"] == 1


def test_purchase_stage_uses_pos_session_correlation(client):
    ts = datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc)
    client.post(
        "/events/ingest",
        json=[
            make_event("ENTRY", "VIS_PURCHASE", ts),
            make_event("ZONE_ENTER", "VIS_PURCHASE", ts + timedelta(minutes=1), "SKINCARE"),
            make_event("BILLING_QUEUE_JOIN", "VIS_PURCHASE", ts + timedelta(minutes=5), "BILLING", queue_depth=1),
        ],
    )
    client.post("/pos/ingest", json=[make_pos("TXN_PURCHASE", ts + timedelta(minutes=8))])
    payload = client.get("/stores/STORE_BLR_002/funnel?date=2026-04-10").json()
    stages = {stage["stage"]: stage["count"] for stage in payload["stages"]}
    assert stages == {"Entry": 1, "Zone Visit": 1, "Billing Queue": 1, "Purchase": 1}
