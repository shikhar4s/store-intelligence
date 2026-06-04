# PROMPT: Generate robust tests for operational notifications that explain stalled background processing without flooding the UI.
# CHANGES MADE: Added active live-stream, stale-feed, empty-store, and last-six notification assertions.

from __future__ import annotations

from datetime import datetime, timezone

from app.video_demo import LIVE_STATES, LIVE_STATES_LOCK
from tests.conftest import make_event


def test_notifications_are_capped_and_include_empty_stores(client):
    payload = client.get("/notifications").json()
    assert payload["count"] <= 6
    assert len(payload["notifications"]) <= 6
    assert any(item["code"] == "NO_EVENTS_FOR_STORE" for item in payload["notifications"])


def test_notifications_include_stale_feed_warning(client):
    client.post(
        "/events/ingest",
        json=[make_event("ENTRY", "VIS_STALE", datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc))],
    )
    payload = client.get("/notifications").json()
    assert any(item["code"] == "STALE_FEED" and item["severity"] == "WARN" for item in payload["notifications"])


def test_notifications_include_active_live_detection(client):
    with LIVE_STATES_LOCK:
        LIVE_STATES["test-active-stream"] = {
            "running": True,
            "status": "streaming",
            "clip": "sample.mp4",
            "store_id": "STORE_BLR_002",
            "model": "yolo11n.pt",
            "frame_index": 42,
        }
    try:
        payload = client.get("/notifications").json()
        assert any(item["code"] == "LIVE_DETECTION_RUNNING" for item in payload["notifications"])
    finally:
        with LIVE_STATES_LOCK:
            LIVE_STATES.pop("test-active-stream", None)


def test_notifications_include_tracker_fallback_warning(client):
    with LIVE_STATES_LOCK:
        LIVE_STATES["test-fallback-stream"] = {
            "running": True,
            "status": "streaming_with_tracker_fallback",
            "clip": "sample.mp4",
            "store_id": "STORE_BLR_002",
            "model": "yolo11n.pt",
            "frame_index": 12,
            "tracker_backend": "centroid",
            "tracking_warning": "ultralytics_tracker_fallback: missing lap",
        }
    try:
        payload = client.get("/notifications").json()
        assert any(item["code"] == "LIVE_TRACKER_FALLBACK" and item["severity"] == "WARN" for item in payload["notifications"])
    finally:
        with LIVE_STATES_LOCK:
            LIVE_STATES.pop("test-fallback-stream", None)
