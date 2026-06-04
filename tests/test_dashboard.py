# PROMPT: Generate robust tests for dashboard discoverability, store listing, and user-facing navigation text.
# CHANGES MADE: Added assertions that users can select stores and understand sections without memorizing endpoint URLs.

from __future__ import annotations

from datetime import datetime, timezone

from tests.conftest import make_event


def test_stores_endpoint_lists_default_store(client):
    payload = client.get("/stores").json()
    stores = {store["store_id"]: store for store in payload["stores"]}
    assert "STORE_BLR_002" in stores
    assert stores["STORE_BLR_002"]["is_default"] is True


def test_stores_endpoint_reflects_ingested_events(client):
    client.post(
        "/events/ingest",
        json=[make_event("ENTRY", "VIS_STORE", datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc))],
    )
    payload = client.get("/stores").json()
    store = next(item for item in payload["stores"] if item["store_id"] == "STORE_BLR_002")
    assert store["event_count"] == 1
    assert store["last_event_timestamp"].startswith("2026-04-10T10:00:00")


def test_dashboard_has_store_menu_navigation_and_explanations(client):
    response = client.get("/dashboard")
    html = response.text
    assert response.status_code == 200
    assert 'id="storeSelect"' in html
    assert "Overview" in html
    assert "Funnel" in html
    assert "Heatmap" in html
    assert "Anomalies" in html
    assert "How it works" in html
    assert "Turns CCTV-derived events and POS transactions" in html
    assert "Non-staff visitor sessions" in html
    assert 'id="notificationButton"' in html
    assert 'id="notificationList"' in html
