# PROMPT: Generate robust tests for updated challenge resources, two-store aliases, POS store discovery, and store-scoped video demo clips.
# CHANGES MADE: Added compatibility coverage for sample_eventsbe42122.jsonl, ST1008/ST1076 aliasing, and nested CCTV clip discovery.

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import video_demo
from app.event_normalizer import normalize_event_batch
from app.layout_store import canonical_store_id, known_zones
from app.schemas import EventIn
from pipeline.detect import infer_camera, infer_store_id_for_video
from pipeline.layout_loader import load_layout
from pipeline.pos_loader import parse_pos_csv


def test_store_aliases_and_known_zones_cover_two_stores():
    assert canonical_store_id("ST1008") == "STORE_BLR_002"
    assert canonical_store_id("Store 1") == "STORE_BLR_002"
    assert canonical_store_id("ST1076") == "STORE_MUM_1076"
    assert canonical_store_id("store_1076") == "STORE_MUM_1076"
    assert any(zone["zone_id"] == "PURPLLE_MUM_1076_Z_BILLING_01" for zone in known_zones("ST1076"))


def test_store_catalog_lists_configured_stores_before_events(client):
    response = client.get("/stores")
    payload = response.json()
    store_ids = {store["store_id"] for store in payload["stores"]}
    assert response.status_code == 200
    assert {"STORE_BLR_002", "STORE_MUM_1076"}.issubset(store_ids)


def test_sample_eventsbe42122_jsonl_normalizes_and_ingests(client):
    path = Path("resources/sample_eventsbe42122.jsonl")
    if not path.exists():
        pytest.skip("challenge sample_eventsbe42122.jsonl not present")

    raw_events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    normalized = normalize_event_batch(raw_events)
    assert len(normalized) == 13
    assert {event["store_id"] for event in normalized} == {"STORE_MUM_1076"}
    assert {EventIn.model_validate(event).visitor_id for event in normalized} == {"ID_60001", "ID_60002", "ID_60003"}

    response = client.post("/events/ingest", json={"events": raw_events})
    assert response.status_code == 200
    assert response.json()["accepted_count"] == 13
    metrics = client.get("/stores/ST1076/metrics?date=2026-03-08").json()
    funnel = client.get("/stores/store_1076/funnel?date=2026-03-08").json()
    heatmap = client.get("/stores/STORE_MUM_1076/heatmap?date=2026-03-08").json()

    assert metrics["store_id"] == "STORE_MUM_1076"
    assert metrics["unique_visitors"] == 3
    assert metrics["current_queue_depth"] == 0
    assert metrics["abandonment_rate"] == pytest.approx(1 / 3, rel=0.001)
    assert funnel["total_sessions"] == 3
    assert heatmap["zones"]
    assert any(zone["zone_id"] == "PURPLLE_MUM_1076_Z01" and zone["visits"] == 1 for zone in heatmap["zones"])


def test_new_pos_sample_uses_csv_store_id_when_no_override():
    path = Path("resources/POS - sample transactions.csv")
    if not path.exists():
        pytest.skip("challenge POS sample not present")

    transactions = parse_pos_csv(path)
    assert transactions
    assert {transaction["store_id"] for transaction in transactions} == {"STORE_BLR_002"}
    assert len(transactions) == 101


def test_nested_cctv_clip_catalog_is_store_scoped(tmp_path: Path, monkeypatch):
    root = tmp_path / "cctv_footage"
    store_1 = root / "Store 1"
    store_2 = root / "Store 2"
    store_1.mkdir(parents=True)
    store_2.mkdir(parents=True)
    (store_1 / "CAM 3 - entry.mp4").write_bytes(b"video")
    (store_2 / "billing_area.mp4").write_bytes(b"video")

    monkeypatch.setattr(video_demo, "VIDEO_ROOT", root)
    clips = video_demo.list_video_clips()

    assert {clip["store_id"] for clip in clips} == {"STORE_BLR_002", "STORE_MUM_1076"}
    assert any(clip["id"] == "Store 1/CAM 3 - entry.mp4" and clip["camera_type"] == "ENTRY" for clip in clips)
    assert any(clip["id"] == "Store 2/billing_area.mp4" and clip["camera_type"] == "BILLING" for clip in clips)
    assert video_demo.resolve_clip("Store 2/billing_area.mp4") == store_2 / "billing_area.mp4"


def test_detection_infers_store_and_camera_from_updated_paths():
    layout = load_layout(Path("configs/store_layout.generated.json"))
    store_1_video = Path("datasets/cctv_footage/Store 1/CAM 3 - entry.mp4")
    store_2_video = Path("datasets/cctv_footage/Store 2/billing_area.mp4")

    assert infer_store_id_for_video(store_1_video, layout) == "STORE_BLR_002"
    assert infer_store_id_for_video(store_2_video, layout) == "STORE_MUM_1076"
    assert infer_camera(store_1_video, layout["stores"][0], 0)["camera_type"] == "ENTRY"
    assert infer_camera(store_2_video, layout["stores"][1], 1)["camera_type"] == "BILLING"
