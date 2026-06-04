# PROMPT: Generate robust tests for pipeline operational helpers, replay utilities, POS parsing, trackers, ReID, and demo event generation.
# CHANGES MADE: Used temporary files/directories to avoid touching challenge CCTV assets and tightened schema validation of generated events.

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.schemas import EventIn
from pipeline.detect import TrackMotionState, _should_skip_unvalidated_track, _update_motion_state, build_parser, discover_videos, run_detection
from pipeline.layout_loader import discover_layout_file, load_layout, write_generated_layout
from pipeline.model_loader import DetectorUnavailable, load_ultralytics_model, video_fps
from pipeline.pos_loader import discover_pos_file, infer_clip_start, parse_pos_csv
from pipeline.reid import ReIdGallery, stable_visitor_id
from pipeline.replay import load_events
from pipeline.staff import StaffHeuristic
from pipeline.tracker import CentroidTracker
from scripts.seed_demo import build_demo_events
from scripts.smoke_test import event as smoke_event


def test_run_detection_force_fallback_writes_valid_jsonl(tmp_path: Path, monkeypatch):
    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    (video_dir / "CAM 1.mp4").write_bytes(b"0" * 2048)
    layout_path = tmp_path / "store_layout.json"
    layout = {
        "store_id": "STORE_TEST_001",
        "zones": [{"zone_id": "BILLING", "sku_zone": "BILLING", "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]]}],
        "cameras": [{"camera_id": "CAM_ENTRY_01", "camera_type": "ENTRY"}],
    }
    layout_path.write_text(json.dumps(layout), encoding="utf-8")
    output = tmp_path / "events.jsonl"
    monkeypatch.chdir(tmp_path)
    args = build_parser().parse_args(
        [
            "--input",
            str(video_dir),
            "--output",
            str(output),
            "--layout",
            str(layout_path),
            "--force-fallback",
        ]
    )
    events = run_detection(args)
    assert discover_videos(video_dir) == [video_dir / "CAM 1.mp4"]
    assert output.exists()
    assert events
    assert EventIn.model_validate(events[0]).store_id == "STORE_TEST_001"


def test_detection_defaults_are_accuracy_biased():
    args = build_parser().parse_args(["--input", "datasets/cctv_footage"])
    assert args.model == "rtdetr-x.pt"
    assert args.tracker == "botsort.yaml"
    assert args.confidence == 0.10
    assert args.imgsz == 960
    assert args.static_after_frames == 8
    assert args.static_motion_threshold == 0.012
    assert args.min_human_bottom_y == 0.62


def test_pipeline_static_wall_display_tracks_are_filtered_before_events():
    state = TrackMotionState()
    for _ in range(8):
        _update_motion_state(state, (0.5, 0.5), [100, 100, 180, 300], 640, 480)

    assert _should_skip_unvalidated_track(state, static_after_frames=8, static_motion_threshold=0.012, min_human_bottom_y=0.62) is True
    assert state.ignored_static_display is True

    moving = TrackMotionState()
    _update_motion_state(moving, (0.2, 0.2), [100, 100, 180, 300], 640, 480)
    _update_motion_state(moving, (0.25, 0.25), [116, 116, 196, 316], 640, 480)
    assert _should_skip_unvalidated_track(moving, static_after_frames=8, static_motion_threshold=0.012, min_human_bottom_y=0.2) is False
    assert moving.validated is True


def test_layout_and_pos_discovery_and_parsing(tmp_path: Path):
    layout_path = tmp_path / "sample_layout.json"
    layout_path.write_text(json.dumps({"store_id": "STORE_X", "zones": []}), encoding="utf-8")
    pos_path = tmp_path / "pos_transactions.csv"
    pos_path.write_text(
        "invoice_number,order_date,order_time,total_amount\nINV1,10-04-2026,16:55:36,123.45\nINV1,10-04-2026,16:55:36,10.00\n",
        encoding="utf-8",
    )
    assert discover_layout_file(tmp_path) == layout_path
    assert discover_pos_file(tmp_path) == pos_path
    layout = load_layout(layout_path)
    generated = tmp_path / "generated.json"
    write_generated_layout(generated, layout)
    assert json.loads(generated.read_text(encoding="utf-8"))["store_id"] == "STORE_X"
    transactions = parse_pos_csv(pos_path, store_id="STORE_X")
    assert len(transactions) == 1
    assert transactions[0]["amount"] == 133.45
    assert infer_clip_start(pos_path, datetime(2026, 1, 1, tzinfo=timezone.utc)).year == 2026


def test_tracker_staff_and_reid_helpers():
    tracker = CentroidTracker(max_distance=20)
    tracks = tracker.update([((0, 0, 10, 10), 0.8)])
    assert tracks[0].track_id == 1
    tracks = tracker.update([((2, 2, 12, 12), 0.7)])
    assert tracks[0].track_id == 1

    staff = StaffHeuristic(min_duration_minutes=1, min_zone_count=2)
    start = datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc)
    assert staff.update("VIS_A", start, "A", "ZONE_ENTER")[0] is False
    is_staff, confidence, reason = staff.update("VIS_A", start + timedelta(minutes=2), "B", "ZONE_ENTER")
    assert is_staff is True
    assert confidence > 0.5
    assert "duration" in reason

    gallery = ReIdGallery(ttl=timedelta(minutes=5))
    assert stable_visitor_id("CAM", 1).startswith("VIS_")
    feature = gallery.feature_hash(fallback="same-shirt")
    gallery.remember_exit("VIS_A", start, feature)
    assert gallery.match_reentry(start + timedelta(minutes=2), feature) == "VIS_A"


def test_replay_seed_demo_smoke_event_and_video_fps(tmp_path: Path):
    events = build_demo_events("STORE_TEST_002")
    output = tmp_path / "demo.jsonl"
    output.write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")
    loaded = load_events(output)
    assert len(loaded) == len(events)
    assert EventIn.model_validate(loaded[0]).store_id == "STORE_TEST_002"

    smoke = smoke_event("ENTRY", "VIS_SMOKE", datetime(2026, 4, 10, tzinfo=timezone.utc))
    assert EventIn.model_validate(smoke).event_type == "ENTRY"
    assert video_fps(tmp_path / "missing.mp4") == 15.0

    try:
        load_ultralytics_model("__missing_model__.pt")
    except DetectorUnavailable as exc:
        assert "ultralytics" in str(exc) or "could not load" in str(exc)
