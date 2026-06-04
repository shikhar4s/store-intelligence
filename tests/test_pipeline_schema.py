# PROMPT: Generate robust tests for detection pipeline event schema validation with synthetic track/event generation.
# CHANGES MADE: Avoided real CCTV dependency by using fallback video-file metadata and validating the emitted JSONL schema.

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.schemas import EventIn
from pipeline.detect import fallback_events_for_video, infer_camera
from pipeline.emit import EventEmitter, write_jsonl
from pipeline.layout_loader import load_layout
from pipeline.validate_events import validate_file
from pipeline.zones import crossed_line, point_in_polygon


def test_pipeline_fallback_events_validate_schema(tmp_path: Path):
    fake_video = tmp_path / "CAM 1.mp4"
    fake_video.write_bytes(b"0" * 1024 * 1024)
    layout = load_layout()
    camera = infer_camera(fake_video, layout, 0)
    emitter = EventEmitter("STORE_BLR_002")
    events = fallback_events_for_video(
        video_path=fake_video,
        camera=camera,
        layout=layout,
        emitter=emitter,
        start_ts=datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc),
        ordinal=0,
    )
    assert events
    for event in events:
        assert EventIn.model_validate(event).store_id == "STORE_BLR_002"
    output = tmp_path / "events.jsonl"
    write_jsonl(output, events)
    ok, failed = validate_file(output)
    assert ok == len(events)
    assert failed == 0


def test_zone_geometry_helpers():
    square = [[0, 0], [1, 0], [1, 1], [0, 1]]
    assert point_in_polygon((0.5, 0.5), square)
    assert not point_in_polygon((1.5, 0.5), square)
    assert crossed_line((0.5, 0.4), (0.5, 0.6), [[0, 0.5], [1, 0.5]]) == "above_to_below"
