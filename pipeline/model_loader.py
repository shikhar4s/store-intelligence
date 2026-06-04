from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

from pipeline.tracker import CentroidTracker


@dataclass
class Detection:
    track_id: int
    box_xyxy: tuple[float, float, float, float]
    confidence: float
    frame_index: int
    width: int
    height: int


class DetectorUnavailable(RuntimeError):
    pass


def load_ultralytics_model(model_name: str = "rtdetr-x.pt"):  # pragma: no cover - optional dependency path
    config_dir = Path(os.getenv("YOLO_CONFIG_DIR", Path.cwd() / ".ultralytics"))
    config_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(config_dir))
    os.environ.setdefault("MPLCONFIGDIR", str(config_dir / "matplotlib"))
    try:
        from ultralytics import RTDETR, YOLO
    except Exception as exc:
        raise DetectorUnavailable("ultralytics is not installed") from exc
    try:
        if model_name.lower().startswith("rtdetr"):
            return RTDETR(model_name)
        return YOLO(model_name)
    except Exception as exc:
        raise DetectorUnavailable(f"could not load {model_name}: {exc}") from exc


def video_fps(path: Path, default: float = 15.0) -> float:
    try:
        import cv2

        capture = cv2.VideoCapture(str(path))
        fps = capture.get(cv2.CAP_PROP_FPS) or default
        capture.release()
        return float(fps or default)
    except Exception:
        return default


def iter_ultralytics_tracks(  # pragma: no cover - optional dependency path
    model,
    video_path: Path,
    sample_fps: float,
    confidence: float,
    tracker: str,
    imgsz: int,
    device: Optional[str] = None,
) -> Iterator[Detection]:
    fps = video_fps(video_path)
    stride = max(1, int(round(fps / max(sample_fps, 0.1))))
    common_args = {
        "source": str(video_path),
        "stream": True,
        "classes": [0],
        "conf": confidence,
        "vid_stride": stride,
        "imgsz": imgsz,
        "verbose": False,
    }
    if device:
        common_args["device"] = device
    is_rtdetr = model.__class__.__name__.lower().startswith("rtdetr")
    centroid_tracker = CentroidTracker(max_distance=95.0, max_missed=10)

    def emit_from_results(results, *, use_centroid_ids: bool) -> Iterator[Detection]:
        for result_index, result in enumerate(results):
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            width, height = int(result.orig_shape[1]), int(result.orig_shape[0])
            xyxy = boxes.xyxy.cpu().numpy().tolist()
            confs = boxes.conf.cpu().numpy().tolist()
            if use_centroid_ids or boxes.id is None:
                tracks = centroid_tracker.update(zip(xyxy, confs))
                track_items = [(track.track_id, track.box, track.confidence) for track in tracks]
            else:
                ids = boxes.id.cpu().numpy().astype(int).tolist()
                track_items = list(zip(ids, xyxy, confs))
            for track_id, box, conf in track_items:
                yield Detection(
                    track_id=int(track_id),
                    box_xyxy=tuple(float(v) for v in box[:4]),
                    confidence=float(conf),
                    frame_index=result_index * stride,
                    width=width,
                    height=height,
                )

    if is_rtdetr:
        yield from emit_from_results(model.predict(**common_args), use_centroid_ids=True)
        return

    try:
        yield from emit_from_results(model.track(persist=True, tracker=tracker, **common_args), use_centroid_ids=False)
    except Exception:
        # BoT-SORT/ByteTrack depends on optional native packages such as lap.
        # Keep event generation alive with detector boxes plus centroid IDs.
        yield from emit_from_results(model.predict(**common_args), use_centroid_ids=True)
