from __future__ import annotations

import argparse
import json
import math
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from app.layout_store import canonical_store_id, find_store_layout, store_layouts
from pipeline.emit import EventEmitter, write_jsonl
from pipeline.layout_loader import discover_layout_file, load_layout, write_generated_layout
from pipeline.model_loader import DetectorUnavailable, iter_ultralytics_tracks, load_ultralytics_model, video_fps
from pipeline.pos_loader import discover_pos_file, infer_clip_start
from pipeline.reid import ReIdGallery, stable_visitor_id
from pipeline.staff import StaffHeuristic
from pipeline.zones import crossed_line, footpoint_xyxy, locate_zone, normalize_point


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}


def discover_videos(input_path: Path) -> List[Path]:
    if input_path.is_file():
        return [input_path]
    return sorted(path for path in input_path.rglob("*") if path.suffix.lower() in VIDEO_EXTENSIONS)


def _norm_hint(value: object) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def infer_camera(path: Path, layout: dict, ordinal: int) -> dict:
    cameras = list(layout.get("cameras") or [])
    path_name = _norm_hint(path.name)
    path_stem = _norm_hint(path.stem)
    for camera in cameras:
        hint = camera.get("source_hint")
        if not hint:
            continue
        hint_name = _norm_hint(hint)
        if hint_name and (hint_name == path_name or hint_name == path_stem or hint_name in path_name):
            return dict(camera)

    stem_lower = path.stem.lower()
    store_prefix = str(layout.get("store_id") or "STORE").replace("-", "_").upper()
    if "entry" in stem_lower:
        return {
            "camera_id": f"{store_prefix}_CAM_ENTRY_{ordinal + 1:02d}",
            "camera_type": "ENTRY",
            "entry_line": [[0.08, 0.55], [0.92, 0.55]],
            "inbound_side": "above_to_below",
        }
    if "billing" in stem_lower or "queue" in stem_lower:
        return {"camera_id": f"{store_prefix}_CAM_BILLING_{ordinal + 1:02d}", "camera_type": "BILLING"}
    if "zone" in stem_lower or "floor" in stem_lower:
        return {"camera_id": f"{store_prefix}_CAM_ZONE_{ordinal + 1:02d}", "camera_type": "MAIN_FLOOR"}

    digits = "".join(ch for ch in path.stem if ch.isdigit())
    index = int(digits) if digits else ordinal + 1
    if index == 1:
        return {"camera_id": f"{store_prefix}_CAM_ENTRY_01", "camera_type": "ENTRY", "entry_line": [[0.08, 0.55], [0.92, 0.55]], "inbound_side": "above_to_below"}
    if index in {3, 5}:
        return {"camera_id": f"{store_prefix}_CAM_BILLING_{1 if index == 3 else 2:02d}", "camera_type": "BILLING"}
    return {"camera_id": f"{store_prefix}_CAM_MAIN_{1 if index == 2 else index:02d}", "camera_type": "MAIN_FLOOR"}


def infer_store_id_for_video(path: Path, layout: dict, override_store_id: Optional[str] = None) -> str:
    if override_store_id:
        return canonical_store_id(override_store_id)
    records = store_layouts(layout)
    path_parts = {_norm_hint(part) for part in path.parts}
    for store in records:
        candidates = [
            store.get("store_id"),
            store.get("store_name"),
            store.get("source_folder"),
            *(store.get("aliases") or []),
        ]
        if any(_norm_hint(candidate) in path_parts for candidate in candidates if candidate):
            return str(store.get("store_id"))
    if len(records) == 1 and records[0].get("store_id"):
        return str(records[0].get("store_id"))
    return canonical_store_id(path.parent.name)


def _visitor(index: int) -> str:
    return f"VIS_{index:06d}"


@dataclass
class TrackMotionState:
    points: list[tuple[float, float]] = field(default_factory=list)
    areas: list[float] = field(default_factory=list)
    validated: bool = False
    ignored_static_display: bool = False


def _normalized_area(box_xyxy, width: int, height: int) -> float:
    x1, y1, x2, y2 = [float(value) for value in box_xyxy]
    area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return area / max(float(width * height), 1.0)


def _update_motion_state(state: TrackMotionState, point: tuple[float, float], box_xyxy, width: int, height: int) -> None:
    state.points.append(point)
    state.areas.append(_normalized_area(box_xyxy, width, height))
    del state.points[:-30]
    del state.areas[:-30]


def _motion_span(state: TrackMotionState) -> float:
    if len(state.points) < 2:
        return 0.0
    xs = [point[0] for point in state.points]
    ys = [point[1] for point in state.points]
    return ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2) ** 0.5


def _area_change_span(state: TrackMotionState) -> float:
    if len(state.areas) < 2:
        return 0.0
    mean_area = max(sum(state.areas) / len(state.areas), 0.0001)
    return (max(state.areas) - min(state.areas)) / mean_area


def _should_skip_unvalidated_track(
    state: TrackMotionState,
    *,
    static_after_frames: int,
    static_motion_threshold: float,
    min_human_bottom_y: Optional[float] = None,
) -> bool:
    if state.ignored_static_display:
        return True
    if state.validated:
        return False

    latest_bottom_y = state.points[-1][1] if state.points else 1.0
    if min_human_bottom_y is not None and latest_bottom_y < min_human_bottom_y:
        state.ignored_static_display = True
        return True

    motion = _motion_span(state)
    area_change = _area_change_span(state)
    if motion >= max(static_motion_threshold * 1.8, 0.018) or area_change >= 0.06:
        state.validated = True
        return False

    if len(state.points) >= max(3, static_after_frames) and motion <= static_motion_threshold and area_change <= 0.035:
        state.ignored_static_display = True
        return True

    return True


def fallback_events_for_video(
    *,
    video_path: Path,
    camera: dict,
    layout: dict,
    emitter: EventEmitter,
    start_ts: datetime,
    ordinal: int,
) -> List[dict]:
    size_mb = max(video_path.stat().st_size / 1_000_000, 1)
    person_count = max(3, min(9, int(math.sqrt(size_mb))))
    zones = [zone for zone in layout.get("zones", []) if not str(zone.get("zone_id", "")).startswith("ENTRY")]
    if not zones:
        zones = [{"zone_id": "SKINCARE", "sku_zone": "SKINCARE"}, {"zone_id": "BILLING", "sku_zone": "BILLING"}]

    events: List[dict] = []
    camera_type = camera.get("camera_type")
    camera_id = camera.get("camera_id")
    base_offset = timedelta(minutes=ordinal * 2)

    for idx in range(person_count):
        visitor_id = _visitor(idx + 1)
        is_staff = idx == 0 and ordinal % 2 == 0
        confidence = 0.38 + min(0.45, (size_mb % 50) / 100) - (0.08 if is_staff else 0)
        timestamp = start_ts + base_offset + timedelta(minutes=idx * 3)
        staff_metadata = {"staff_heuristic": "fallback_pattern" if is_staff else None}

        if camera_type == "ENTRY":
            events.append(
                emitter.event(
                    camera_id=camera_id,
                    visitor_id=visitor_id,
                    event_type="ENTRY",
                    timestamp=timestamp,
                    is_staff=is_staff,
                    confidence=confidence,
                    metadata=staff_metadata,
                )
            )
            if idx == 1:
                events.append(
                    emitter.event(
                        camera_id=camera_id,
                        visitor_id=visitor_id,
                        event_type="EXIT",
                        timestamp=timestamp + timedelta(minutes=8),
                        is_staff=is_staff,
                        confidence=confidence * 0.92,
                        metadata=staff_metadata,
                    )
                )
                events.append(
                    emitter.event(
                        camera_id=camera_id,
                        visitor_id=visitor_id,
                        event_type="REENTRY",
                        timestamp=timestamp + timedelta(minutes=11),
                        is_staff=is_staff,
                        confidence=confidence * 0.86,
                        metadata={"reid_method": "fallback_time_appearance", **staff_metadata},
                    )
                )
            elif idx % 3 == 0:
                events.append(
                    emitter.event(
                        camera_id=camera_id,
                        visitor_id=visitor_id,
                        event_type="EXIT",
                        timestamp=timestamp + timedelta(minutes=22),
                        is_staff=is_staff,
                        confidence=confidence * 0.9,
                        metadata=staff_metadata,
                    )
                )
        elif camera_type == "BILLING":
            zone = next((z for z in zones if "BILLING" in str(z.get("zone_id", "")).upper()), zones[-1])
            queue_depth = min(6, idx + 1)
            events.append(
                emitter.event(
                    camera_id=camera_id,
                    visitor_id=visitor_id,
                    event_type="BILLING_QUEUE_JOIN",
                    timestamp=timestamp + timedelta(minutes=20),
                    zone_id=str(zone.get("zone_id")),
                    is_staff=is_staff,
                    confidence=confidence,
                    metadata={"queue_depth": queue_depth, "sku_zone": zone.get("sku_zone"), **staff_metadata},
                )
            )
            if idx % 4 == 3:
                events.append(
                    emitter.event(
                        camera_id=camera_id,
                        visitor_id=visitor_id,
                        event_type="BILLING_QUEUE_ABANDON",
                        timestamp=timestamp + timedelta(minutes=26),
                        zone_id=str(zone.get("zone_id")),
                        is_staff=is_staff,
                        confidence=confidence * 0.75,
                        metadata={"queue_depth": max(queue_depth - 1, 0), "sku_zone": zone.get("sku_zone"), **staff_metadata},
                    )
                )
        else:
            zone = zones[idx % len(zones)]
            zone_id = str(zone.get("zone_id"))
            sku_zone = zone.get("sku_zone")
            events.append(
                emitter.event(
                    camera_id=camera_id,
                    visitor_id=visitor_id,
                    event_type="ZONE_ENTER",
                    timestamp=timestamp + timedelta(minutes=5),
                    zone_id=zone_id,
                    is_staff=is_staff,
                    confidence=confidence,
                    metadata={"sku_zone": sku_zone, **staff_metadata},
                )
            )
            events.append(
                emitter.event(
                    camera_id=camera_id,
                    visitor_id=visitor_id,
                    event_type="ZONE_DWELL",
                    timestamp=timestamp + timedelta(minutes=5, seconds=30),
                    zone_id=zone_id,
                    dwell_ms=30_000 + idx * 5_000,
                    is_staff=is_staff,
                    confidence=confidence * 0.94,
                    metadata={"sku_zone": sku_zone, **staff_metadata},
                )
            )
            events.append(
                emitter.event(
                    camera_id=camera_id,
                    visitor_id=visitor_id,
                    event_type="ZONE_EXIT",
                    timestamp=timestamp + timedelta(minutes=7),
                    zone_id=zone_id,
                    is_staff=is_staff,
                    confidence=confidence * 0.9,
                    metadata={"sku_zone": sku_zone, **staff_metadata},
                )
            )
    return events


def yolo_events_for_video(  # pragma: no cover - exercised only when optional CV/model stack is installed
    *,
    model,
    video_path: Path,
    camera: dict,
    layout: dict,
    emitter: EventEmitter,
    start_ts: datetime,
    sample_fps: float,
    confidence: float,
    tracker_config: str,
    imgsz: int,
    device: Optional[str],
    static_after_frames: int = 8,
    static_motion_threshold: float = 0.012,
    min_human_bottom_y: float = 0.62,
) -> List[dict]:
    events: List[dict] = []
    fps = video_fps(video_path)
    zones = list(layout.get("zones") or [])
    staff = StaffHeuristic()
    gallery = ReIdGallery()
    previous_points: Dict[int, tuple[float, float]] = {}
    motion_states: Dict[int, TrackMotionState] = {}
    current_zone: Dict[int, Optional[str]] = {}
    zone_entered_at: Dict[tuple[int, str], datetime] = {}
    dwell_mark: Dict[tuple[int, str], int] = {}
    active_billing: set[int] = set()
    entry_line = camera.get("entry_line") or [[0.08, 0.55], [0.92, 0.55]]
    inbound_side = camera.get("inbound_side", "above_to_below")
    model_label = str(getattr(model, "ckpt_path", "") or getattr(model, "model_name", "") or model.__class__.__name__)

    for detection in iter_ultralytics_tracks(model, video_path, sample_fps, confidence, tracker_config, imgsz, device):
        timestamp = start_ts + timedelta(seconds=detection.frame_index / max(fps, 1.0))
        foot = footpoint_xyxy(detection.box_xyxy)
        point = normalize_point(foot[0], foot[1], detection.width, detection.height)
        visitor_id = stable_visitor_id(camera["camera_id"], detection.track_id)
        track_key = detection.track_id
        motion_state = motion_states.setdefault(track_key, TrackMotionState())
        _update_motion_state(motion_state, point, detection.box_xyxy, detection.width, detection.height)
        if camera.get("camera_type") != "ENTRY" and _should_skip_unvalidated_track(
            motion_state,
            static_after_frames=static_after_frames,
            static_motion_threshold=static_motion_threshold,
            min_human_bottom_y=min_human_bottom_y,
        ):
            previous_points[track_key] = point
            continue
        is_staff, staff_conf, staff_reason = staff.update(visitor_id, timestamp, None, None)
        event_conf = min(detection.confidence, staff_conf if is_staff else 1.0)

        if camera.get("camera_type") == "ENTRY":
            direction = crossed_line(previous_points.get(track_key), point, entry_line)
            if direction:
                event_type = "ENTRY" if direction == inbound_side else "EXIT"
                feature_hash = gallery.feature_hash(fallback=f"{visitor_id}:{round(point[0],2)}:{round(point[1],2)}")
                if event_type == "ENTRY":
                    reentry_id = gallery.match_reentry(timestamp, feature_hash)
                    if reentry_id:
                        visitor_id = reentry_id
                        event_type = "REENTRY"
                else:
                    gallery.remember_exit(visitor_id, timestamp, feature_hash)
                events.append(
                    emitter.event(
                        camera_id=camera["camera_id"],
                        visitor_id=visitor_id,
                        event_type=event_type,
                        timestamp=timestamp,
                        is_staff=is_staff,
                        confidence=event_conf,
                            metadata={"staff_reason": staff_reason, "detector": "ultralytics", "model": model_label},
                    )
                )
        else:
            zone = locate_zone(point, zones)
            zone_id = str(zone.get("zone_id")) if zone else None
            previous_zone = current_zone.get(track_key)
            if zone_id != previous_zone:
                if previous_zone:
                    entered = zone_entered_at.get((track_key, previous_zone), timestamp)
                    events.append(
                        emitter.event(
                            camera_id=camera["camera_id"],
                            visitor_id=visitor_id,
                            event_type="ZONE_EXIT",
                            timestamp=timestamp,
                            zone_id=previous_zone,
                            dwell_ms=int((timestamp - entered).total_seconds() * 1000),
                            is_staff=is_staff,
                            confidence=event_conf,
                            metadata={"detector": "ultralytics", "model": model_label},
                        )
                    )
                    if "BILLING" in previous_zone.upper() and track_key in active_billing:
                        active_billing.discard(track_key)
                        events.append(
                            emitter.event(
                                camera_id=camera["camera_id"],
                                visitor_id=visitor_id,
                                event_type="BILLING_QUEUE_ABANDON",
                                timestamp=timestamp,
                                zone_id=previous_zone,
                                is_staff=is_staff,
                                confidence=event_conf * 0.7,
                                metadata={"queue_depth": len(active_billing), "detector": "ultralytics_pending_pos", "model": model_label},
                            )
                        )
                if zone_id:
                    zone_entered_at[(track_key, zone_id)] = timestamp
                    dwell_mark[(track_key, zone_id)] = 0
                    current_zone[track_key] = zone_id
                    event_type = "ZONE_ENTER"
                    metadata = {"sku_zone": zone.get("sku_zone") if zone else None, "detector": "ultralytics", "model": model_label}
                    if "BILLING" in zone_id.upper():
                        active_billing.add(track_key)
                        event_type = "BILLING_QUEUE_JOIN"
                        metadata["queue_depth"] = len(active_billing)
                    events.append(
                        emitter.event(
                            camera_id=camera["camera_id"],
                            visitor_id=visitor_id,
                            event_type=event_type,
                            timestamp=timestamp,
                            zone_id=zone_id,
                            is_staff=is_staff,
                            confidence=event_conf,
                            metadata=metadata,
                        )
                    )
                else:
                    current_zone[track_key] = None
            elif zone_id:
                entered = zone_entered_at.get((track_key, zone_id), timestamp)
                dwell_seconds = int((timestamp - entered).total_seconds())
                emitted_marks = dwell_mark.get((track_key, zone_id), 0)
                if dwell_seconds >= (emitted_marks + 1) * 30:
                    dwell_mark[(track_key, zone_id)] = emitted_marks + 1
                    events.append(
                        emitter.event(
                            camera_id=camera["camera_id"],
                            visitor_id=visitor_id,
                            event_type="ZONE_DWELL",
                            timestamp=timestamp,
                            zone_id=zone_id,
                            dwell_ms=dwell_seconds * 1000,
                            is_staff=is_staff,
                            confidence=event_conf,
                            metadata={"sku_zone": zone.get("sku_zone") if zone else None, "detector": "ultralytics", "model": model_label},
                        )
                    )
        previous_points[track_key] = point
    return events


def post_events(url: str, events: List[dict]) -> None:
    data = json.dumps({"events": events}).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status >= 300:
            raise RuntimeError(f"ingest failed with HTTP {response.status}")


def run_detection(args: argparse.Namespace) -> List[dict]:
    layout_file = Path(args.layout) if args.layout else discover_layout_file(Path("."))
    layout = load_layout(layout_file)
    if args.store_id and not layout.get("stores"):
        layout["store_id"] = args.store_id
    generated_layout_path = Path("configs/store_layout.generated.json")
    try:
        write_generated_layout(generated_layout_path, layout)
    except OSError:
        pass

    pos_file = Path(args.pos) if args.pos else discover_pos_file(Path("."))
    start_ts = infer_clip_start(pos_file, datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc))
    videos = discover_videos(Path(args.input))
    events: List[dict] = []

    model = None
    model_reason = "forced fallback"
    if not args.force_fallback:
        try:
            model = load_ultralytics_model(args.model)
            model_reason = "ultralytics"
        except DetectorUnavailable as exc:
            model_reason = str(exc)

    for ordinal, video_path in enumerate(videos):
        video_store_id = infer_store_id_for_video(video_path, layout, args.store_id)
        store_layout = find_store_layout(video_store_id, layout)
        camera = infer_camera(video_path, store_layout, ordinal)
        emitter = EventEmitter(store_id=video_store_id)
        if model is not None:
            try:
                video_events = yolo_events_for_video(
                    model=model,
                    video_path=video_path,
                    camera=camera,
                    layout=store_layout,
                    emitter=emitter,
                    start_ts=start_ts + timedelta(minutes=ordinal * 20),
                    sample_fps=args.sample_fps,
                    confidence=args.confidence,
                    tracker_config=args.tracker,
                    imgsz=args.imgsz,
                    device=args.device,
                    static_after_frames=args.static_after_frames,
                    static_motion_threshold=args.static_motion_threshold,
                    min_human_bottom_y=args.min_human_bottom_y,
                )
            except Exception as exc:
                video_events = fallback_events_for_video(
                    video_path=video_path,
                    camera=camera,
                    layout=store_layout,
                    emitter=emitter,
                    start_ts=start_ts + timedelta(minutes=ordinal * 20),
                    ordinal=ordinal,
                )
                for event in video_events:
                    event["metadata"]["fallback_reason"] = f"ultralytics_error: {exc}"
        else:
            video_events = fallback_events_for_video(
                video_path=video_path,
                camera=camera,
                layout=store_layout,
                emitter=emitter,
                start_ts=start_ts + timedelta(minutes=ordinal * 20),
                ordinal=ordinal,
            )
            for event in video_events:
                event["metadata"]["fallback_reason"] = model_reason
        events.extend(video_events)

    events.sort(key=lambda event: event["timestamp"])
    if args.output:
        write_jsonl(args.output, events)
    if args.emit_url:
        if args.realtime:
            previous_ts: Optional[datetime] = None
            for event in events:
                current_ts = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
                if previous_ts is not None:
                    delay = max(0.0, (current_ts - previous_ts).total_seconds() / max(args.speed, 0.1))
                    time.sleep(min(delay, 10.0))
                post_events(args.emit_url, [event])
                previous_ts = current_ts
        else:
            for index in range(0, len(events), 100):
                post_events(args.emit_url, events[index : index + 100])
    return events


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Process CCTV clips into structured store events.")
    parser.add_argument("--input", required=True, help="Video file or directory containing CCTV clips.")
    parser.add_argument("--output", default="outputs/events.jsonl", help="JSONL output path.")
    parser.add_argument("--emit-url", help="Optional API ingest URL.")
    parser.add_argument("--realtime", action="store_true", help="Replay emitted events according to event timestamps.")
    parser.add_argument("--speed", type=float, default=5.0, help="Realtime replay speed multiplier.")
    parser.add_argument("--sample-fps", type=float, default=5.0, help="Frame sampling rate for model-backed detection.")
    parser.add_argument("--confidence", type=float, default=0.10, help="Detector confidence threshold; low default preserves weak CCTV detections.")
    parser.add_argument("--imgsz", type=int, default=960, help="Inference image size. Higher values improve small-person recall at higher memory cost.")
    parser.add_argument("--model", default="rtdetr-x.pt", help="Ultralytics model name/path. Default is high-accuracy RT-DETR-X.")
    parser.add_argument("--tracker", default="botsort.yaml", help="Ultralytics tracker config for YOLO models; RT-DETR uses an internal centroid association fallback.")
    parser.add_argument("--device", help="Optional Ultralytics device, e.g. 0 for GPU or cpu.")
    parser.add_argument("--static-after-frames", type=int, default=8, help="Ignore an unvalidated track as a wall/poster display after this many static sampled detections.")
    parser.add_argument("--static-motion-threshold", type=float, default=0.012, help="Normalized motion span below this threshold is treated as static until the track is validated.")
    parser.add_argument("--min-human-bottom-y", type=float, default=0.62, help="Minimum normalized detection box bottom for floor-standing humans on floor/billing cameras; higher filters more wall posters.")
    parser.add_argument("--layout", help="Layout JSON/XLSX path. Auto-discovered when omitted.")
    parser.add_argument("--pos", help="POS CSV path used to infer clip start. Auto-discovered when omitted.")
    parser.add_argument("--store-id", help="Override canonical store id.")
    parser.add_argument("--force-fallback", action="store_true", help="Skip model loading and emit deterministic fallback events.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    events = run_detection(args)
    print(json.dumps({"videos_processed": len(discover_videos(Path(args.input))), "events_emitted": len(events), "output": args.output}))


if __name__ == "__main__":
    main()
