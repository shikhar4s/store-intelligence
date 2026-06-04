# PROMPT: Generate robust tests for event ingestion validation, idempotency, partial success, batch limits, and storage outages.
# CHANGES MADE: Added malformed-event partial success assertions and structured 503 verification for unavailable DB dependencies.

from __future__ import annotations

from datetime import datetime, timezone

from app.errors import ServiceUnavailableError
from app.main import get_db
from tests.conftest import make_event


def test_ingest_happy_path(client):
    event = make_event()
    response = client.post("/events/ingest", json={"events": [event]})
    assert response.status_code == 200
    assert response.json()["accepted_count"] == 1
    assert response.json()["rejected_count"] == 0


def test_ingest_duplicate_event_id_is_idempotent(client):
    event = make_event()
    first = client.post("/events/ingest", json=[event])
    second = client.post("/events/ingest", json=[event])
    assert first.json()["accepted_count"] == 1
    assert second.json()["accepted_count"] == 0
    assert second.json()["duplicate_count"] == 1


def test_ingest_partial_success_with_malformed_event(client):
    good = make_event()
    bad = {"event_id": "not-a-uuid", "store_id": "STORE_BLR_002"}
    response = client.post("/events/ingest", json={"events": [good, bad]})
    payload = response.json()
    assert response.status_code == 200
    assert payload["accepted_count"] == 1
    assert payload["rejected_count"] == 1
    assert payload["errors"][0]["index"] == 1
    assert payload["errors"][0]["code"] == "VALIDATION_ERROR"


def test_ingest_rejects_batch_over_500(client):
    events = [make_event(visitor_id=f"VIS_{idx:03d}") for idx in range(501)]
    response = client.post("/events/ingest", json={"events": events})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "BATCH_TOO_LARGE"


def test_db_unavailable_returns_503_structured_body(client):
    def broken_db():
        raise ServiceUnavailableError("database down for test")

    client.app.dependency_overrides[get_db] = broken_db
    response = client.post("/events/ingest", json=[make_event()])
    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "DATABASE_UNAVAILABLE", "message": "database down for test"}
    }
