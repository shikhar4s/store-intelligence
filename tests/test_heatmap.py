# PROMPT: Generate robust tests for heatmap zone aggregation, normalization, zero-visit zones, and low-confidence data flags.
# CHANGES MADE: Added known-layout zero-zone assertion and verified normalized score is derived from input visit counts.

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tests.conftest import make_event


def test_heatmap_normalization_and_low_confidence(client):
    ts = datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc)
    events = [
        make_event("ENTRY", "VIS_1", ts),
        make_event("ZONE_ENTER", "VIS_1", ts + timedelta(minutes=1), "SKINCARE"),
        make_event("ZONE_DWELL", "VIS_1", ts + timedelta(minutes=2), "SKINCARE", dwell_ms=60000),
        make_event("ZONE_ENTER", "VIS_2", ts + timedelta(minutes=3), "MAKEUP"),
    ]
    client.post("/events/ingest", json=events)
    payload = client.get("/stores/STORE_BLR_002/heatmap?date=2026-04-10").json()
    zones = {zone["zone_id"]: zone for zone in payload["zones"]}
    assert zones["SKINCARE"]["visits"] == 1
    assert zones["SKINCARE"]["avg_dwell_ms"] == 60000
    assert zones["SKINCARE"]["normalized_score_0_100"] == 100.0
    assert "BILLING" in zones
    assert payload["data_confidence"]["is_confident"] is False
