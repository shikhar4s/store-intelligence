from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.video_demo import (
    DEFAULT_BLUR_STAFF_MAX_VARIANCE,
    DEFAULT_MIN_HUMAN_BOTTOM_Y,
    DEFAULT_STAFF_AREA_BOTTOM_Y_MAX,
    DEFAULT_STAFF_AREA_X_MIN,
    DEFAULT_STAFF_UNIFORM_HITS,
    DEFAULT_STATIC_AFTER_FRAMES,
    DEFAULT_STATIC_APPEARANCE_THRESHOLD,
    DEFAULT_STATIC_MOTION_THRESHOLD,
    DEFAULT_UNIFORM_BGR,
    LiveTrack,
    _classify_role,
    _face_blur_score,
    _parse_uniform_bgr,
    _remember_track_observation,
    _store_id_for_clip,
    _uniform_match_scores,
    _update_uniform_evidence,
)
from pipeline.model_loader import load_ultralytics_model

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}


def _discover_videos(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS)


def _sample_indices(frame_count: int, frames_per_clip: int) -> list[int]:
    if frame_count <= 1:
        return [0]
    ratios = [0.15, 0.5, 0.85]
    if frames_per_clip <= 1:
        ratios = [0.5]
    elif frames_per_clip == 2:
        ratios = [0.25, 0.75]
    return [max(0, min(frame_count - 1, int(frame_count * ratio))) for ratio in ratios[:frames_per_clip]]


def _role_for_detection(frame: Any, box: list[float], confidence: float, uniform_colors: list[tuple[int, int, int]]) -> dict:
    track = LiveTrack(first_frame=0)
    height, width = frame.shape[:2]
    for _ in range(max(2, DEFAULT_STAFF_UNIFORM_HITS)):
        _remember_track_observation(track, box, confidence, width, height)
        uniform_score, dark_uniform_score = _uniform_match_scores(frame, box, uniform_colors)
        track.blur_score = _face_blur_score(frame, box)
        _update_uniform_evidence(track, uniform_score, dark_uniform_score)
    role, role_confidence, role_reason = _classify_role(
        track,
        frame_width=width,
        frame_height=height,
        static_after_frames=DEFAULT_STATIC_AFTER_FRAMES,
        static_motion_threshold=DEFAULT_STATIC_MOTION_THRESHOLD,
        static_appearance_threshold=DEFAULT_STATIC_APPEARANCE_THRESHOLD,
        min_human_bottom_y=DEFAULT_MIN_HUMAN_BOTTOM_Y,
        blur_staff_max_variance=DEFAULT_BLUR_STAFF_MAX_VARIANCE,
        staff_area_x_min=DEFAULT_STAFF_AREA_X_MIN,
        staff_area_bottom_y_max=DEFAULT_STAFF_AREA_BOTTOM_Y_MAX,
        staff_uniform_hits=DEFAULT_STAFF_UNIFORM_HITS,
    )
    return {
        "role": role,
        "role_confidence": round(role_confidence, 4),
        "reason": role_reason,
        "det_confidence": round(float(confidence), 4),
    }


def verify(args: argparse.Namespace) -> dict:
    import cv2

    videos = _discover_videos(args.input)
    if not videos:
        raise RuntimeError(f"No video clips found under {args.input}")

    by_store: dict[str, list[Path]] = defaultdict(list)
    for video in videos:
        by_store[_store_id_for_clip(video)].append(video)

    model = load_ultralytics_model(args.model)
    uniform_colors = _parse_uniform_bgr(args.uniform_bgr)
    stores = []
    total_samples = 0
    total_detections = 0
    tracker_checked = False
    is_rtdetr = model.__class__.__name__.lower().startswith("rtdetr")

    for store_id, store_videos in sorted(by_store.items()):
        store_summary = {"store_id": store_id, "clips": []}
        for clip_path in store_videos[: args.max_clips_per_store]:
            capture = cv2.VideoCapture(str(clip_path))
            if not capture.isOpened():
                raise RuntimeError(f"Could not open video clip: {clip_path}")
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            clip_summary = {"clip": str(clip_path), "frame_count": frame_count, "samples": []}
            for frame_index in _sample_indices(frame_count, args.frames_per_clip):
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = capture.read()
                if not ok or frame is None:
                    raise RuntimeError(f"Could not read frame {frame_index} from {clip_path}")
                if not args.skip_tracker_check and not tracker_checked and not is_rtdetr:
                    try:
                        model.track(
                            source=frame,
                            classes=[0],
                            conf=args.conf,
                            imgsz=args.imgsz,
                            tracker=args.tracker,
                            persist=False,
                            verbose=False,
                        )
                    except Exception as exc:
                        raise RuntimeError(
                            "Ultralytics tracker check failed. Rebuild with INSTALL_CV=true "
                            "so requirements-cv.txt installs lap and other tracker dependencies. "
                            f"Original error: {exc}"
                        ) from exc
                    tracker_checked = True
                result = model.predict(source=frame, classes=[0], conf=args.conf, imgsz=args.imgsz, verbose=False)[0]
                boxes = getattr(result, "boxes", None)
                detections = []
                if boxes is not None:
                    xyxy = boxes.xyxy.cpu().numpy().tolist()
                    confs = boxes.conf.cpu().numpy().tolist()
                    detections = [
                        _role_for_detection(frame, box, confidence, uniform_colors)
                        for box, confidence in zip(xyxy, confs)
                    ]
                role_counts: dict[str, int] = defaultdict(int)
                for detection in detections:
                    role_counts[detection["role"]] += 1
                total_samples += 1
                total_detections += len(detections)
                clip_summary["samples"].append(
                    {
                        "frame_index": frame_index,
                        "detections": len(detections),
                        "role_counts": dict(sorted(role_counts.items())),
                        "examples": detections[: min(len(detections), 5)],
                    }
                )
            capture.release()
            store_summary["clips"].append(clip_summary)
        stores.append(store_summary)

    return {
        "ok": True,
        "model": args.model,
        "stores_checked": len(stores),
        "clips_found": len(videos),
        "samples_checked": total_samples,
        "detections_seen": total_detections,
        "tracker_checked": tracker_checked,
        "stores": stores,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify that the video-demo model path can open clips and produce sampled detections.")
    parser.add_argument("--input", type=Path, default=Path("datasets/cctv_footage"))
    parser.add_argument("--model", default="yolo11n.pt")
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--tracker", default="botsort.yaml")
    parser.add_argument("--skip-tracker-check", action="store_true")
    parser.add_argument("--uniform-bgr", default=DEFAULT_UNIFORM_BGR)
    parser.add_argument("--max-clips-per-store", type=int, default=2)
    parser.add_argument("--frames-per-clip", type=int, default=3)
    parser.add_argument("--compact", action="store_true", help="Only print top-level summary.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = verify(args)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    if args.compact:
        payload = {
            "ok": payload["ok"],
            "model": payload["model"],
            "stores_checked": payload["stores_checked"],
            "clips_found": payload["clips_found"],
            "samples_checked": payload["samples_checked"],
            "detections_seen": payload["detections_seen"],
            "tracker_checked": payload["tracker_checked"],
        }
    print(json.dumps(payload, indent=None if args.compact else 2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
