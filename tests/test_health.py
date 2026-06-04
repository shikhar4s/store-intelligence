# PROMPT: Generate robust tests for health endpoint status, empty database behavior, and stale feed warnings.
# CHANGES MADE: Added stale historical event case and configured-store empty timestamp assertions.

from __future__ import annotations

from datetime import datetime, timezone

from tests.conftest import make_event


def test_health_without_events_is_ok(client):
    payload = client.get("/health").json()
    assert payload["status"] == "OK"
    assert payload["database"]["status"] == "OK"
    assert payload["last_event_timestamp_by_store"]["STORE_BLR_002"] is None
    assert payload["last_event_timestamp_by_store"]["STORE_MUM_1076"] is None


def test_health_stale_feed_warning(client):
    client.post("/events/ingest", json=[make_event("ENTRY", "VIS_OLD", datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc))])
    payload = client.get("/health").json()
    assert payload["status"] == "WARN"
    assert payload["warnings"][0]["type"] == "STALE_FEED"
    assert payload["last_event_timestamp_by_store"]["STORE_BLR_002"].startswith("2026-04-10T10:00:00")
