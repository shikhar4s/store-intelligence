# PROMPT: Generate shared pytest fixtures for a FastAPI store intelligence API with isolated SQLite state.
# CHANGES MADE: Added deterministic event helpers, POS helper, and per-test database reset to avoid hidden coupling.

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.database import configure_database, init_db
from app.main import create_app


@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "test.db"
    configure_database(f"sqlite:///{db_path.as_posix()}")
    init_db()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_event(
    event_type: str = "ENTRY",
    visitor_id: str = "VIS_001",
    ts: datetime | None = None,
    zone_id: str | None = None,
    store_id: str = "STORE_BLR_002",
    is_staff: bool = False,
    confidence: float = 0.8,
    dwell_ms: int = 0,
    queue_depth: int | None = None,
):
    timestamp = ts or datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc)
    return {
        "event_id": str(uuid4()),
        "store_id": store_id,
        "camera_id": "CAM_ENTRY_01" if event_type in {"ENTRY", "EXIT", "REENTRY"} else "CAM_MAIN_01",
        "visitor_id": visitor_id,
        "event_type": event_type,
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "zone_id": zone_id,
        "dwell_ms": dwell_ms,
        "is_staff": is_staff,
        "confidence": confidence,
        "metadata": {"queue_depth": queue_depth, "sku_zone": zone_id, "session_seq": 1},
    }


def make_pos(transaction_id: str, ts: datetime, amount: float = 100.0, store_id: str = "STORE_BLR_002"):
    return {
        "store_id": store_id,
        "transaction_id": transaction_id,
        "timestamp": ts.isoformat().replace("+00:00", "Z"),
        "amount": amount,
    }
