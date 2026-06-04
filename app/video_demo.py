from __future__ import annotations

import html
import logging
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Generator, Optional

from fastapi import HTTPException

from app.layout_store import canonical_store_id, find_store_layout, store_layouts, store_name_for_id
from pipeline.model_loader import DetectorUnavailable, load_ultralytics_model
from pipeline.tracker import CentroidTracker


logger = logging.getLogger("store_intelligence.video_demo")
VIDEO_ROOT = Path("datasets/cctv_footage")
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}
MODEL_OPTIONS = [
    {
        "value": "yolov8n.pt",
        "label": "YOLOv8n - fastest live preview",
        "description": "Good for live CPU viewing; lower accuracy than large models.",
    },
    {
        "value": "yolov8n-seg.pt",
        "label": "YOLOv8n-seg - fast person masks",
        "description": "Fast local instance segmentation; better role evidence than boxes.",
    },
    {
        "value": "yolo11n.pt",
        "label": "YOLO11n - fast modern preview",
        "description": "Small modern YOLO option when weights are available.",
    },
    {
        "value": "yolov8x-seg.pt",
        "label": "YOLOv8x-seg - accurate person masks",
        "description": "Higher accuracy segmentation; recommended for RTX 4060 demos.",
    },
    {
        "value": "yolov8x.pt",
        "label": "YOLOv8x - high accuracy YOLO",
        "description": "Higher accuracy, slower; better on GPU.",
    },
    {
        "value": "rtdetr-x.pt",
        "label": "RT-DETR-X - highest checked AP",
        "description": "Highest official AP among checked options; slow on CPU.",
    },
]

LIVE_STATES: dict[str, dict] = {}
LIVE_STATES_LOCK = Lock()
DEFAULT_UNIFORM_BGR = "25,25,25;50,50,180;40,120,40"
UNIFORM_HIT_SCORE = 0.55
BLACK_UNIFORM_BRIGHTNESS_MAX = 45.0
BLACK_UNIFORM_REQUIRED_FRACTION = 0.60
REGULAR_UNIFORM_DISTANCE_MAX = 55.0
REGULAR_UNIFORM_REQUIRED_FRACTION = 0.18
DEFAULT_MIN_HUMAN_BOTTOM_Y = 0.45
DEFAULT_BLUR_STAFF_MAX_VARIANCE = 90.0
DEFAULT_STATIC_AFTER_FRAMES = 16
DEFAULT_STATIC_MOTION_THRESHOLD = 0.006
DEFAULT_STATIC_APPEARANCE_THRESHOLD = 0.025
DEFAULT_STAFF_UNIFORM_HITS = 4
PERSON_LIKE_HEIGHT_RATIO = 0.24
PERSON_LIKE_MASK_COVERAGE = 0.025
MOVING_CUSTOMER_MOTION_THRESHOLD = 0.008
MOVING_CUSTOMER_APPEARANCE_THRESHOLD = 0.09
DEFAULT_STAFF_AREA_X_MIN = 0.66
DEFAULT_STAFF_AREA_BOTTOM_Y_MAX = 0.92
MASK_REFINER_OPTIONS = [
    ("off", "Off - fastest box-only logic"),
    ("auto", "Auto - use native model masks"),
    ("mobile_sam.pt", "MobileSAM - optional SAM refinement"),
    ("FastSAM-s.pt", "FastSAM-s - optional fast refinement"),
    ("sam_b.pt", "SAM vit_b - optional accurate refinement"),
]


@dataclass
class LiveTrack:
    first_frame: int
    seen_frames: int = 0
    role: str = "customer_candidate"
    confidence: float = 0.0
    role_confidence: float = 0.35
    role_reason: str = "waiting_for_motion_or_uniform_evidence"
    centers: list[tuple[float, float]] = field(default_factory=list)
    areas: list[float] = field(default_factory=list)
    boxes: list[tuple[float, float, float, float]] = field(default_factory=list)
    bottom_ratios: list[float] = field(default_factory=list)
    center_x_ratios: list[float] = field(default_factory=list)
    height_ratios: list[float] = field(default_factory=list)
    mask_bottom_ratios: list[float] = field(default_factory=list)
    mask_coverages: list[float] = field(default_factory=list)
    appearance_changes: list[float] = field(default_factory=list)
    uniform_hits: int = 0
    uniform_score: float = 0.0
    dark_uniform_hits: int = 0
    dark_uniform_score: float = 0.0
    blur_score: float = 999.0
    last_crop_signature: object | None = None


def list_video_clips() -> list[dict]:
    if not VIDEO_ROOT.exists():
        return []
    clips = []
    for path in sorted(VIDEO_ROOT.rglob("*")):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            store_id = _store_id_for_clip(path)
            relative_id = path.relative_to(VIDEO_ROOT).as_posix()
            clips.append(
                {
                    "id": relative_id,
                    "name": path.name,
                    "relative_path": relative_id,
                    "store_id": store_id,
                    "store_name": store_name_for_id(store_id),
                    "camera_type": _camera_type_for_clip(path, store_id),
                    "size_mb": round(path.stat().st_size / 1_000_000, 2),
                }
            )
    return clips


def list_video_stores(clips: Optional[list[dict]] = None) -> list[dict]:
    configured = {
        str(store.get("store_id")): str(store.get("store_name") or store.get("store_id"))
        for store in store_layouts()
        if store.get("store_id")
    }
    for clip in clips if clips is not None else list_video_clips():
        configured.setdefault(clip["store_id"], clip["store_name"])
    return [
        {"store_id": store_id, "display_name": display_name}
        for store_id, display_name in sorted(configured.items(), key=lambda item: item[1])
    ]


def resolve_clip(clip_name: str) -> Path:
    root = VIDEO_ROOT.resolve()
    requested = Path(str(clip_name).replace("\\", "/"))
    candidate = (root / requested).resolve()
    try:
        candidate.relative_to(root)
        if candidate.is_file() and candidate.suffix.lower() in VIDEO_EXTENSIONS:
            return candidate
    except ValueError:
        pass

    safe_name = requested.name
    for path in root.rglob(safe_name):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            return path
    raise HTTPException(status_code=404, detail={"error": {"code": "CLIP_NOT_FOUND", "message": clip_name}})


def _norm_hint(value: object) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _store_id_for_clip(path: Path) -> str:
    for part in reversed(path.parts):
        candidate = canonical_store_id(part)
        if candidate != part or str(candidate).startswith("STORE_"):
            return candidate
    return canonical_store_id(path.parent.name)


def _camera_type_for_clip(path: Path, store_id: str) -> str:
    store_layout = find_store_layout(store_id)
    path_name = _norm_hint(path.name)
    for camera in store_layout.get("cameras") or []:
        hint = camera.get("source_hint")
        if hint and _norm_hint(hint) in path_name:
            return str(camera.get("camera_type") or "UNKNOWN")
    lower = path.stem.lower()
    if "entry" in lower:
        return "ENTRY"
    if "billing" in lower or "queue" in lower:
        return "BILLING"
    if "zone" in lower or "floor" in lower:
        return "MAIN_FLOOR"
    return "UNKNOWN"


def get_live_state(stream_id: str) -> dict:
    with LIVE_STATES_LOCK:
        return LIVE_STATES.get(
            stream_id,
            {
                "stream_id": stream_id,
                "running": False,
                "status": "not_started",
                "detections": [],
                "interactions": [],
                "frame_index": 0,
            },
        )


def stop_live_stream(stream_id: str) -> dict:
    with LIVE_STATES_LOCK:
        state = LIVE_STATES.setdefault(stream_id, {"stream_id": stream_id})
        state["running"] = False
        state["status"] = "stop_requested"
        return dict(state)


def live_stream_summaries() -> list[dict]:
    with LIVE_STATES_LOCK:
        return [
            {
                "stream_id": stream_id,
                "running": bool(state.get("running")),
                "status": state.get("status"),
                "clip": state.get("clip"),
                "store_id": state.get("store_id"),
                "model": state.get("model"),
                "frame_index": state.get("frame_index"),
                "tracker_backend": state.get("tracker_backend"),
                "tracking_warning": state.get("tracking_warning"),
            }
            for stream_id, state in LIVE_STATES.items()
        ]


def render_video_demo() -> str:
    model_options = "\n".join(
        f'<option value="{html.escape(item["value"])}"{" selected" if item["value"] == "yolo11n.pt" else ""}>{html.escape(item["label"])}</option>'
        for item in MODEL_OPTIONS
    )
    mask_refiner_options = "\n".join(
        f'<option value="{html.escape(value)}"{" selected" if value == "off" else ""}>{html.escape(label)}</option>' for value, label in MASK_REFINER_OPTIONS
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Live Detection Viewer</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, "Segoe UI", Arial, sans-serif;
      --page: #f7fafc;
      --panel: rgba(255, 255, 255, 0.92);
      --panel-solid: #ffffff;
      --ink: #0b1b34;
      --muted: #6d7890;
      --line: #e4ebf2;
      --teal: #079680;
      --teal-dark: #057367;
      --green: #21c998;
      --blue: #2f8df2;
      --purple: #9b6bff;
      --orange: #f4a236;
      --red: #d94d48;
      --shadow: 0 18px 40px rgba(38, 56, 83, 0.08);
      --shadow-soft: 0 12px 26px rgba(38, 56, 83, 0.06);
    }}
    * {{ box-sizing: border-box; }}
    html {{ min-height: 100%; background: var(--page); }}
    body {{
      min-height: 100vh;
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 88% 2%, rgba(173, 203, 255, 0.28), transparent 30%),
        linear-gradient(115deg, #ffffff 0%, #f9fbff 42%, #f4fbf8 100%);
    }}
    body::before {{
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image:
        linear-gradient(rgba(216, 226, 239, 0.22) 1px, transparent 1px),
        linear-gradient(90deg, rgba(216, 226, 239, 0.22) 1px, transparent 1px);
      background-size: 42px 42px;
      mask-image: linear-gradient(to bottom, rgba(0,0,0,0.42), transparent 62%);
    }}
    button, select, input, a {{ font: inherit; }}
    button {{ border: 0; cursor: pointer; }}
    h1, h2, h3, p {{ margin: 0; }}
    .icon {{ width: 22px; height: 22px; stroke: currentColor; stroke-width: 2; fill: none; stroke-linecap: round; stroke-linejoin: round; flex: 0 0 auto; }}
    .app-shell {{
      position: relative;
      display: grid;
      grid-template-columns: 222px minmax(0, 1fr);
      min-height: 100vh;
      padding: 24px 28px 28px 24px;
      gap: 26px;
      z-index: 1;
    }}
    .sidebar {{
      position: sticky;
      top: 24px;
      height: calc(100vh - 52px);
      display: grid;
      grid-template-rows: auto auto auto 1fr;
      gap: 24px;
    }}
    .rail-top {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; }}
    .logo-tile, .top-icon, .metric-icon {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 20px;
      background: rgba(255, 255, 255, 0.78);
      box-shadow: var(--shadow-soft);
      color: var(--teal);
    }}
    .logo-tile {{ width: 58px; height: 58px; }}
    .menu-button {{ width: 46px; height: 46px; border-radius: 16px; background: rgba(243, 247, 252, 0.92); color: #0e2943; display: inline-flex; align-items: center; justify-content: center; }}
    .store-card {{
      min-height: 102px;
      border-radius: 14px;
      padding: 20px;
      color: #ffffff;
      background: linear-gradient(135deg, rgba(152, 113, 255, 0.95), rgba(82, 206, 230, 0.95));
      box-shadow: 0 20px 36px rgba(99, 132, 220, 0.23);
      display: grid;
      align-content: center;
    }}
    .store-eyebrow {{ color: rgba(255, 255, 255, 0.78); font-size: 12px; font-weight: 800; }}
    .store-name {{ margin-top: 7px; font-size: 16px; font-weight: 900; }}
    .store-city {{ margin-top: 10px; display: inline-flex; align-items: center; gap: 8px; color: rgba(255, 255, 255, 0.76); font-size: 12px; font-weight: 700; }}
    .live-dot {{ width: 7px; height: 7px; border-radius: 50%; background: #21f2b6; box-shadow: 0 0 0 5px rgba(33, 242, 182, 0.12); }}
    .nav-list {{ display: grid; gap: 10px; align-content: start; }}
    .nav-button, a.nav-button {{
      width: 100%;
      min-height: 52px;
      display: flex;
      align-items: center;
      gap: 14px;
      padding: 0 20px;
      border-radius: 11px;
      color: #627089;
      background: transparent;
      font-size: 14px;
      font-weight: 850;
      text-decoration: none;
      text-align: left;
    }}
    .nav-button.active {{
      color: var(--teal);
      background: linear-gradient(90deg, rgba(225, 248, 242, 0.98), rgba(238, 250, 248, 0.74));
      box-shadow: inset 0 0 0 1px rgba(202, 239, 231, 0.78);
    }}
    .insight-card {{
      min-height: 180px;
      border-radius: 13px;
      padding: 22px;
      color: #ffffff;
      background: linear-gradient(155deg, rgba(177, 111, 255, 0.9), rgba(67, 156, 244, 0.96));
      box-shadow: 0 20px 34px rgba(73, 118, 239, 0.22);
      display: grid;
      align-content: center;
      gap: 12px;
    }}
    .insight-card strong {{ font-size: 17px; line-height: 1.35; }}
    .insight-card span {{ color: rgba(255,255,255,0.74); font-size: 13px; line-height: 1.55; }}
    .workspace {{ min-width: 0; }}
    .topbar {{
      min-height: 94px;
      display: grid;
      grid-template-columns: minmax(360px, 1fr) auto;
      gap: 24px;
      align-items: start;
      margin-bottom: 16px;
    }}
    .title-row {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
    h1 {{ font-size: 28px; line-height: 1.1; letter-spacing: 0; font-weight: 950; }}
    .live-pill {{ display: inline-flex; align-items: center; gap: 7px; padding: 7px 12px; border-radius: 999px; color: #0f9f79; background: #e9fbf3; font-size: 12px; font-weight: 900; box-shadow: inset 0 0 0 1px rgba(23, 202, 151, 0.16); }}
    .subtitle {{ margin-top: 20px; max-width: 760px; color: #30415e; font-size: 14px; line-height: 1.8; font-weight: 650; }}
    .utility-icons {{ display: flex; align-items: center; justify-content: flex-end; gap: 12px; }}
    .top-icon {{ width: 46px; height: 46px; border-radius: 16px; color: #102a43; background: rgba(242, 246, 255, 0.92); position: relative; }}
    .top-icon.alert::after {{
      content: "";
      position: absolute;
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: #f34747;
      border: 2px solid #ffffff;
      right: 10px;
      top: 9px;
    }}
    .notification-wrap {{ position: relative; }}
    .notification-count {{
      position: absolute;
      right: -4px;
      top: -5px;
      min-width: 19px;
      height: 19px;
      padding: 0 5px;
      border-radius: 999px;
      background: #f34747;
      color: #ffffff;
      border: 2px solid #ffffff;
      display: none;
      align-items: center;
      justify-content: center;
      font-size: 10px;
      font-weight: 950;
    }}
    .notification-panel {{
      position: absolute;
      right: 0;
      top: 58px;
      width: min(360px, calc(100vw - 32px));
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.98);
      border: 1px solid rgba(226, 232, 241, 0.96);
      box-shadow: 0 24px 48px rgba(33, 54, 81, 0.14);
      padding: 16px;
      display: none;
      z-index: 20;
    }}
    .notification-panel.open {{ display: block; }}
    .notification-panel h3 {{ font-size: 15px; font-weight: 950; margin: 0 0 12px; }}
    .notification-list {{ display: grid; gap: 10px; }}
    .notification-item {{
      display: grid;
      gap: 5px;
      padding: 11px 12px;
      border-radius: 10px;
      background: #f7fbfa;
      border: 1px solid #e7f1ef;
    }}
    .notification-item strong {{ color: #172943; font-size: 13px; }}
    .notification-item span {{ color: #64748b; font-size: 12px; line-height: 1.45; font-weight: 700; }}
    .notification-item.warn {{ background: #fff8e8; border-color: #fde7b6; }}
    .notification-item.critical {{ background: #fff0ef; border-color: #f8c7c4; }}
    .control-card {{
      border-radius: 13px;
      background: var(--panel);
      border: 1px solid rgba(226, 232, 241, 0.92);
      box-shadow: var(--shadow);
      padding: 24px;
      margin-bottom: 22px;
    }}
    .controls {{ display: grid; grid-template-columns: repeat(6, minmax(130px, 1fr)); gap: 14px; align-items: end; }}
    label {{ display: grid; gap: 8px; color: #748198; font-size: 12px; font-weight: 850; }}
    select, input {{
      width: 100%;
      min-width: 0;
      min-height: 48px;
      border: 1px solid var(--line);
      border-radius: 11px;
      outline: 0;
      background: rgba(255, 255, 255, 0.9);
      color: #30415e;
      padding: 0 14px;
      font-size: 13px;
      font-weight: 800;
      box-shadow: 0 12px 24px rgba(33, 54, 81, 0.045);
    }}
    button, a.button {{
      min-height: 48px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      border-radius: 11px;
      padding: 0 18px;
      background: linear-gradient(180deg, #078b80, #05736f);
      color: #fff;
      cursor: pointer;
      text-decoration: none;
      text-align: center;
      font-size: 13px;
      font-weight: 900;
      box-shadow: 0 12px 22px rgba(16, 125, 116, 0.11);
    }}
    button.stop {{ background: linear-gradient(180deg, #d85950, #b43832); box-shadow: 0 12px 22px rgba(185, 56, 50, 0.14); }}
    a.secondary {{ background: rgba(255, 255, 255, 0.85); color: #20324f; border: 1px solid #a9e0d9; box-shadow: none; }}
    .section-card {{
      position: relative;
      min-height: 128px;
      border-radius: 13px;
      background: var(--panel);
      border: 1px solid rgba(226, 232, 241, 0.92);
      box-shadow: var(--shadow);
      padding: 30px 34px;
      margin-bottom: 22px;
      overflow: hidden;
    }}
    .section-card h2 {{ font-size: 25px; letter-spacing: 0; line-height: 1.2; font-weight: 950; }}
    .section-card p {{ margin-top: 16px; color: #4b5870; font-size: 14px; line-height: 1.75; font-weight: 650; max-width: 880px; }}
    .viewer-grid {{ display: grid; grid-template-columns: minmax(0, 2fr) minmax(320px, 0.95fr); gap: 20px; }}
    .viewer {{
      background: #0d1517;
      border-radius: 13px;
      overflow: hidden;
      min-height: 460px;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: var(--shadow);
      border: 1px solid rgba(20, 33, 45, 0.25);
    }}
    .viewer img {{ width: 100%; height: auto; display: block; }}
    .status {{ margin-top: 12px; color: #526078; font-size: 14px; font-weight: 750; }}
    .side {{ display: grid; gap: 20px; align-content: start; }}
    .notes {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 22px; }}
    .panel {{
      background: var(--panel);
      border: 1px solid rgba(226, 232, 241, 0.92);
      border-radius: 13px;
      padding: 24px;
      box-shadow: var(--shadow-soft);
    }}
    h2 {{ font-size: 18px; margin: 0 0 12px; font-weight: 950; }}
    code {{ background: #edf8f5; color: #106f65; padding: 4px 7px; border-radius: 7px; font-size: 13px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #edf2f6; padding: 12px 8px; text-align: left; font-size: 13px; vertical-align: top; }}
    th {{ color: #7c889d; font-size: 11px; text-transform: uppercase; font-weight: 950; }}
    td {{ color: #273a56; font-weight: 700; }}
    .badge {{ display: inline-flex; border-radius: 999px; padding: 5px 9px; font-size: 12px; font-weight: 850; background: #e7f7f1; color: var(--teal-dark); }}
    .badge.staff {{ background: #fff0dc; color: #9a6110; }}
    .badge.customer {{ background: #dff8ef; color: #087569; }}
    .badge.customer_candidate {{ background: #eef3f7; color: #51615a; }}
    .badge.ignored_static_display {{ background: #e8ebf0; color: #4b5563; }}
    .feed {{ display: grid; gap: 10px; max-height: 260px; overflow: auto; }}
    .feed-item {{ border-left: 3px solid var(--orange); padding-left: 10px; color: #273a56; font-weight: 700; line-height: 1.4; }}
    .empty {{ color: #7a879a; font-weight: 700; }}
    @media (max-width: 1180px) {{
      .app-shell {{ grid-template-columns: 1fr; padding: 18px; }}
      .sidebar {{ position: static; height: auto; grid-template-columns: auto minmax(180px, 260px) 1fr; grid-template-rows: auto auto; align-items: start; }}
      .nav-list {{ grid-column: 1 / -1; grid-template-columns: repeat(3, minmax(0, 1fr)); }}
      .insight-card {{ display: none; }}
      .controls {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
      .viewer-grid {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 820px) {{
      .topbar, .notes {{ grid-template-columns: 1fr; }}
      .utility-icons {{ justify-content: flex-start; }}
      .sidebar {{ grid-template-columns: 1fr; }}
      .nav-list, .controls {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 560px) {{
      .app-shell {{ padding: 12px; }}
      .nav-list, .controls, .notes {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 24px; }}
    }}
  </style>
</head>
<body>
  <svg aria-hidden="true" style="position:absolute;width:0;height:0;overflow:hidden">
    <symbol id="i-bag" viewBox="0 0 24 24"><path d="M6 8h12l-1 12H7L6 8Z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/><path d="M10 13l2 2 4-5"/></symbol>
    <symbol id="i-menu" viewBox="0 0 24 24"><path d="M4 7h16"/><path d="M4 12h10"/><path d="M4 17h16"/></symbol>
    <symbol id="i-home" viewBox="0 0 24 24"><path d="m4 11 8-7 8 7"/><path d="M6 10v10h12V10"/><path d="M10 20v-6h4v6"/></symbol>
    <symbol id="i-camera" viewBox="0 0 24 24"><path d="M15 8h.01"/><path d="M4 7h4l2-3h4l2 3h4v13H4V7Z"/><circle cx="12" cy="14" r="4"/></symbol>
    <symbol id="i-code" viewBox="0 0 24 24"><path d="m8 9-4 3 4 3"/><path d="m16 9 4 3-4 3"/><path d="m14 5-4 14"/></symbol>
    <symbol id="i-users" viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2"/><circle cx="9.5" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9"/><path d="M16 3.1a4 4 0 0 1 0 7.8"/></symbol>
    <symbol id="i-bell" viewBox="0 0 24 24"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/></symbol>
    <symbol id="i-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></symbol>
    <symbol id="i-sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m4.9 4.9 1.4 1.4"/><path d="m17.7 17.7 1.4 1.4"/><path d="m4.9 19.1 1.4-1.4"/><path d="m17.7 6.3 1.4-1.4"/></symbol>
  </svg>
  <div class="app-shell">
    <aside class="sidebar" aria-label="Store Intelligence navigation">
      <div class="rail-top">
        <div class="logo-tile"><svg class="icon"><use href="#i-bag"></use></svg></div>
        <button class="menu-button" type="button" aria-label="Menu"><svg class="icon"><use href="#i-menu"></use></svg></button>
      </div>
      <div class="store-card">
        <div class="store-eyebrow">Connected Store</div>
        <div id="demoStoreName" class="store-name">Video source</div>
        <div class="store-city"><span class="live-dot"></span><span id="demoStoreCity">Live preview</span></div>
      </div>
      <nav class="nav-list" aria-label="Application navigation">
        <a class="nav-button" href="/dashboard"><svg class="icon"><use href="#i-home"></use></svg><span>Overview</span></a>
        <a class="nav-button active" href="/video-demo"><svg class="icon"><use href="#i-camera"></use></svg><span>Live detection</span></a>
        <a class="nav-button" href="/docs" target="_blank" rel="noreferrer"><svg class="icon"><use href="#i-code"></use></svg><span>API docs</span></a>
      </nav>
      <div class="insight-card"><strong>Smart detection.<br />Better validation.</strong><span>Watch model output, role evidence, and possible interactions live.</span></div>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <div class="title-row">
            <h1>Live Detection Viewer</h1>
            <span class="live-pill"><span class="live-dot"></span>Model Preview</span>
          </div>
          <p class="subtitle">Watch the selected model detect people on the CCTV clip. Boxes show person detections, confidence, track IDs, and a live staff/customer role heuristic. Since the footage has no audio, conversation is shown as a possible staff-customer interaction based on proximity over repeated frames.</p>
        </div>
        <div class="utility-icons">
          <button class="top-icon" type="button" aria-label="Search"><svg class="icon"><use href="#i-search"></use></svg></button>
          <div class="notification-wrap">
            <button id="notificationButton" class="top-icon" type="button" aria-label="Notifications" onclick="toggleNotifications()">
              <svg class="icon"><use href="#i-bell"></use></svg>
              <span id="notificationCount" class="notification-count">0</span>
            </button>
            <div id="notificationPanel" class="notification-panel" role="status" aria-live="polite">
              <h3>Notifications</h3>
              <div id="notificationList" class="notification-list"><div class="empty">No important notifications.</div></div>
            </div>
          </div>
          <button class="top-icon" type="button" aria-label="Theme"><svg class="icon"><use href="#i-sun"></use></svg></button>
        </div>
      </header>

      <section class="section-card">
        <h2>Detection controls</h2>
        <p>Select a store clip, choose the detector, optionally enable mask refinement, then start the live stream. Mask/SAM refinement remains off by default for speed.</p>
      </section>

      <section class="control-card">
        <div class="controls">
          <label>Store<select id="storeFilter"></select></label>
          <label>Clip<select id="clip"></select></label>
          <label>Model<select id="model">{model_options}</select></label>
          <label>Mask refinement<select id="maskRefiner">{mask_refiner_options}</select></label>
          <label>Confidence<input id="conf" type="number" min="0.05" max="0.9" step="0.05" value="0.25" /></label>
          <label>Image size<input id="imgsz" type="number" min="320" max="1280" step="32" value="960" /></label>
          <label>Frame stride<input id="stride" type="number" min="1" max="60" step="1" value="5" /></label>
          <label>Staff uniform BGR colors<input id="uniformBgr" type="text" value="{DEFAULT_UNIFORM_BGR}" placeholder="B,G,R;B,G,R" /></label>
          <label>Uniform hits for staff<input id="staffUniformHits" type="number" min="1" max="20" step="1" value="{DEFAULT_STAFF_UNIFORM_HITS}" /></label>
          <label>Static after frames<input id="staticAfter" type="number" min="3" max="120" step="1" value="{DEFAULT_STATIC_AFTER_FRAMES}" /></label>
          <label>Min human bottom Y<input id="minHumanBottom" type="number" min="0.2" max="0.95" step="0.01" value="{DEFAULT_MIN_HUMAN_BOTTOM_Y}" /></label>
          <label>Static motion threshold<input id="staticMotion" type="number" min="0.001" max="0.2" step="0.001" value="{DEFAULT_STATIC_MOTION_THRESHOLD}" /></label>
          <label>Static appearance max<input id="staticAppearance" type="number" min="0.005" max="0.3" step="0.005" value="{DEFAULT_STATIC_APPEARANCE_THRESHOLD}" /></label>
          <label>Blur staff cutoff<input id="blurStaffCutoff" type="number" min="0" max="500" step="5" value="{DEFAULT_BLUR_STAFF_MAX_VARIANCE}" /></label>
          <label>Staff area X min<input id="staffAreaXMin" type="number" min="0" max="1" step="0.01" value="{DEFAULT_STAFF_AREA_X_MIN}" /></label>
          <label>Staff area bottom Y max<input id="staffAreaBottomYMax" type="number" min="0.45" max="1" step="0.01" value="{DEFAULT_STAFF_AREA_BOTTOM_Y_MAX}" /></label>
          <label>Interaction distance<input id="interactionDistance" type="number" min="0.05" max="0.8" step="0.05" value="0.22" /></label>
          <label>Interaction frames<input id="interactionFrames" type="number" min="1" max="20" step="1" value="3" /></label>
          <button onclick="startStream()" type="button">Start live view</button>
          <button class="stop" onclick="stopStream()" type="button">Stop live preview</button>
        </div>
      </section>

      <section class="viewer-grid">
        <div>
          <div class="viewer">
            <img id="stream" alt="Annotated live detection stream will appear here" />
          </div>
          <div id="status" class="status">Choose a clip and press Start live view.</div>
        </div>
        <aside class="side">
          <div class="panel">
            <h2>Live detections</h2>
            <table>
              <thead><tr><th>ID</th><th>Role</th><th>Det/Role</th><th>Reason</th></tr></thead>
              <tbody id="detectionRows"><tr><td colspan="4" class="empty">No stream yet.</td></tr></tbody>
            </table>
          </div>
          <div class="panel">
            <h2>Possible interactions</h2>
            <div id="interactionFeed" class="feed"><div class="empty">No staff-customer proximity events yet.</div></div>
          </div>
        </aside>
      </section>
      <section class="notes">
        <div class="panel">
          <h2>Role labels</h2>
          <p>The live role label is conservative: tracks start as <code>customer_candidate</code>, optional masks can refine floor-contact and uniform evidence, blur is treated as customer evidence unless uniform and staff-area signals agree, and <code>staff</code> requires repeated uniform evidence. Everyone else defaults to <code>customer</code>.</p>
        </div>
        <div class="panel">
          <h2>Wall images and conversation</h2>
          <p>Static wall photos/posters are not counted in interaction logic after the static filter confirms near-zero motion. No audio exists in the clips, so conversation is a visual <code>possible interaction</code> signal from staff/customer proximity.</p>
        </div>
      </section>
    </main>
  </div>
  <script>
    let activeStreamId = null;
    let pollTimer = null;
    let clipCatalog = {{ clips: [], stores: [] }};

    function newStreamId() {{
      if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
      return `stream-${{Date.now()}}-${{Math.random().toString(16).slice(2)}}`;
    }}

    function escapeHtml(value) {{
      return String(value ?? '').replace(/[&<>"']/g, char => ({{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }}[char]));
    }}

    function toggleNotifications() {{
      document.getElementById('notificationPanel').classList.toggle('open');
    }}

    async function refreshNotifications() {{
      const payload = await fetch('/notifications').then(r => r.json()).catch(() => ({{ notifications: [] }}));
      const items = payload.notifications || [];
      const count = document.getElementById('notificationCount');
      count.textContent = String(items.length);
      count.style.display = items.length ? 'inline-flex' : 'none';
      document.getElementById('notificationButton').classList.toggle('alert', items.length > 0);
      document.getElementById('notificationList').innerHTML = items.map(item => {{
        const severity = String(item.severity || 'INFO').toLowerCase();
        const css = severity === 'critical' ? 'critical' : severity === 'warn' ? 'warn' : '';
        const store = item.store_id ? ` ${{escapeHtml(item.store_id)}}` : '';
        return `<div class="notification-item ${{css}}"><strong>${{escapeHtml(item.title || item.code)}}${{store}}</strong><span>${{escapeHtml(item.message || '')}}</span></div>`;
      }}).join('') || '<div class="empty">No important notifications.</div>';
    }}

    function cityForStore(storeId, displayName) {{
      const source = `${{storeId || ''}} ${{displayName || ''}}`.toLowerCase();
      if (source.includes('mum') || source.includes('mumbai')) return 'Mumbai';
      if (source.includes('blr') || source.includes('bangalore') || source.includes('brigade')) return 'Bangalore';
      return 'Live preview';
    }}

    function updateDemoStoreCard() {{
      const storeId = document.getElementById('storeFilter').value;
      const store = (clipCatalog.stores || []).find(item => item.store_id === storeId) || {{ store_id: storeId, display_name: storeId || 'All stores' }};
      document.getElementById('demoStoreName').textContent = store.display_name || store.store_id || 'All stores';
      document.getElementById('demoStoreCity').textContent = cityForStore(store.store_id, store.display_name);
    }}

    async function loadClips() {{
      const payload = await fetch('/video-demo/clips').then(r => r.json());
      clipCatalog = payload || {{ clips: [], stores: [] }};
      const storeSelect = document.getElementById('storeFilter');
      storeSelect.innerHTML = (clipCatalog.stores || []).map(store => `<option value="${{store.store_id}}">${{store.display_name}} (${{store.store_id}})</option>`).join('');
      if (!storeSelect.innerHTML) {{
        storeSelect.innerHTML = '<option value="">All stores</option>';
      }}
      storeSelect.addEventListener('change', () => {{
        updateDemoStoreCard();
        renderClipOptions();
      }});
      updateDemoStoreCard();
      renderClipOptions();
    }}

    function renderClipOptions() {{
      const storeId = document.getElementById('storeFilter').value;
      const select = document.getElementById('clip');
      const clips = (clipCatalog.clips || []).filter(clip => !storeId || clip.store_id === storeId);
      select.innerHTML = clips.map(clip => `<option value="${{clip.id}}">${{clip.name}} | ${{clip.camera_type}} | ${{clip.size_mb}} MB</option>`).join('');
      if (!select.innerHTML) {{
        select.innerHTML = '<option value="">No clips found</option>';
      }}
    }}

    function startStream() {{
      if (activeStreamId) stopStream(false);
      activeStreamId = newStreamId();
      const storeId = document.getElementById('storeFilter').value;
      const clip = document.getElementById('clip').value;
      if (!clip) {{
        document.getElementById('status').textContent = 'No clip is available for the selected store.';
        return;
      }}
      const model = document.getElementById('model').value;
      const maskRefiner = document.getElementById('maskRefiner').value;
      const conf = document.getElementById('conf').value;
      const imgsz = document.getElementById('imgsz').value;
      const stride = document.getElementById('stride').value;
      const uniformBgr = document.getElementById('uniformBgr').value;
      const staffUniformHits = document.getElementById('staffUniformHits').value;
      const staticAfter = document.getElementById('staticAfter').value;
      const minHumanBottom = document.getElementById('minHumanBottom').value;
      const staticMotion = document.getElementById('staticMotion').value;
      const staticAppearance = document.getElementById('staticAppearance').value;
      const blurStaffCutoff = document.getElementById('blurStaffCutoff').value;
      const staffAreaXMin = document.getElementById('staffAreaXMin').value;
      const staffAreaBottomYMax = document.getElementById('staffAreaBottomYMax').value;
      const interactionDistance = document.getElementById('interactionDistance').value;
      const interactionFrames = document.getElementById('interactionFrames').value;
      const url = `/video-demo/stream?clip=${{encodeURIComponent(clip)}}&store_id=${{encodeURIComponent(storeId)}}&model=${{encodeURIComponent(model)}}&mask_refiner=${{encodeURIComponent(maskRefiner)}}&conf=${{conf}}&imgsz=${{imgsz}}&stride=${{stride}}&stream_fps=4&stream_id=${{encodeURIComponent(activeStreamId)}}&uniform_bgr=${{encodeURIComponent(uniformBgr)}}&staff_uniform_hits=${{staffUniformHits}}&static_after_frames=${{staticAfter}}&min_human_bottom_y=${{minHumanBottom}}&static_motion_threshold=${{staticMotion}}&static_appearance_threshold=${{staticAppearance}}&blur_staff_max_variance=${{blurStaffCutoff}}&staff_area_x_min=${{staffAreaXMin}}&staff_area_bottom_y_max=${{staffAreaBottomYMax}}&interaction_distance=${{interactionDistance}}&interaction_frames=${{interactionFrames}}`;
      document.getElementById('stream').src = url + `&cache_bust=${{Date.now()}}`;
      document.getElementById('status').textContent = `Streaming ${{clip}} with ${{model}}. Staff/customer labels and possible interactions update live.`;
      pollTimer = setInterval(refreshState, 800);
      refreshState();
    }}

    async function stopStream(updateStatus = true) {{
      const streamId = activeStreamId;
      document.getElementById('stream').removeAttribute('src');
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = null;
      activeStreamId = null;
      if (streamId) {{
        await fetch(`/video-demo/stop/${{encodeURIComponent(streamId)}}`, {{ method: 'POST' }}).catch(() => null);
      }}
      if (updateStatus) {{
        document.getElementById('status').textContent = 'Live preview stopped.';
      }}
    }}

    async function refreshState() {{
      if (!activeStreamId) return;
      const state = await fetch(`/video-demo/state/${{encodeURIComponent(activeStreamId)}}`).then(r => r.json()).catch(() => null);
      if (!state) return;
      const detections = state.detections || [];
      document.getElementById('detectionRows').innerHTML = detections.map(item =>
        `<tr><td>#${{item.track_id}}</td><td><span class="badge ${{item.role}}">${{String(item.role || '').replaceAll('_', ' ')}}</span></td><td>${{Number(item.confidence || 0).toFixed(2)}} / ${{Number(item.role_confidence || 0).toFixed(2)}}</td><td>${{item.role_reason || ''}}<br><small>bottom=${{Number(item.bottom_y || 0).toFixed(2)}} mask=${{item.mask_available ? 'yes' : 'no'}} uniform=${{Number(item.uniform_score || 0).toFixed(2)}} dark=${{Number(item.dark_uniform_score || 0).toFixed(2)}} blur=${{Number(item.blur_score || 0).toFixed(0)}}</small></td></tr>`
      ).join('') || '<tr><td colspan="4" class="empty">No person detections in the latest frame.</td></tr>';
      const interactions = state.interactions || [];
      document.getElementById('interactionFeed').innerHTML = interactions.slice(-8).reverse().map(item =>
        `<div class="feed-item">Frame ${{item.frame_index}}: ${{item.message}}</div>`
      ).join('') || '<div class="empty">No staff-customer proximity events yet.</div>';
      document.getElementById('status').textContent = `${{state.status || 'streaming'}} | frame ${{state.frame_index || 0}} | detections ${{detections.length}}`;
    }}

    loadClips().then(refreshNotifications);
    setInterval(refreshNotifications, 2000);
  </script>
</body>
</html>"""


@lru_cache(maxsize=3)
def _cached_model(model_name: str):
    return load_ultralytics_model(model_name)


@lru_cache(maxsize=2)
def _cached_mask_refiner(model_name: str):
    if model_name in {"", "off", "auto"}:
        return None
    from pipeline.model_loader import DetectorUnavailable

    try:
        if model_name.lower().startswith("fastsam"):
            from ultralytics import FastSAM

            return FastSAM(model_name)
        from ultralytics import SAM

        return SAM(model_name)
    except Exception as exc:  # pragma: no cover - depends on optional model downloads
        raise DetectorUnavailable(f"could not load mask refiner {model_name}: {exc}") from exc


def _refine_masks_with_prompt(frame, boxes: list, mask_refiner: str, device: Optional[str]) -> list:
    if mask_refiner in {"", "off", "auto"} or not boxes:
        return []
    try:
        model = _cached_mask_refiner(mask_refiner)
        kwargs = {"source": frame, "bboxes": [[float(v) for v in box] for box in boxes], "verbose": False}
        if device:
            kwargs["device"] = device
        result = model.predict(**kwargs)[0]
        return _extract_result_masks(result, frame.shape[0], frame.shape[1])
    except Exception:
        return []


def _track_center(box) -> tuple[float, float]:
    x1, y1, x2, y2 = [float(v) for v in box]
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def _track_area(box) -> float:
    x1, y1, x2, y2 = [float(v) for v in box]
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _box_ratios(box, frame_width: int, frame_height: int) -> tuple[float, float]:
    _x1, y1, _x2, y2 = [float(v) for v in box]
    height = max(y2 - y1, 0.0)
    return y2 / max(float(frame_height), 1.0), height / max(float(frame_height), 1.0)


def _box_center_x_ratio(box, frame_width: int) -> float:
    x1, _y1, x2, _y2 = [float(v) for v in box]
    return ((x1 + x2) / 2.0) / max(float(frame_width), 1.0)


def _resize_mask(mask, frame_height: int, frame_width: int):
    if mask is None:
        return None
    import cv2
    import numpy as np

    array = np.asarray(mask)
    if array.ndim == 3:
        array = array[0]
    if array.shape[:2] != (frame_height, frame_width):
        array = cv2.resize(array.astype("float32"), (frame_width, frame_height), interpolation=cv2.INTER_LINEAR)
    return array > 0.5


def _extract_result_masks(result, frame_height: int, frame_width: int) -> list:
    masks = getattr(result, "masks", None)
    if masks is None or getattr(masks, "data", None) is None:
        return []
    try:
        arrays = masks.data.cpu().numpy()
    except Exception:
        return []
    return [_resize_mask(mask, frame_height, frame_width) for mask in arrays]


def _mask_bottom_ratio(mask, box, frame_height: int, frame_width: int) -> tuple[float, float]:
    resized = _resize_mask(mask, frame_height, frame_width)
    if resized is None or not resized.any():
        bottom_y, _height_ratio = _box_ratios(box, frame_width, frame_height)
        return bottom_y, 0.0
    import numpy as np

    ys = np.where(resized)[0]
    return float(ys.max() / max(frame_height - 1, 1)), float(resized.mean())


def _parse_uniform_bgr(value: str | None) -> list[tuple[int, int, int]]:
    colors: list[tuple[int, int, int]] = []
    if not value:
        return colors
    for item in value.replace("|", ";").split(";"):
        parts = [part.strip() for part in item.split(",") if part.strip()]
        if len(parts) != 3:
            continue
        try:
            b, g, r = [max(0, min(255, int(float(part)))) for part in parts]
        except ValueError:
            continue
        colors.append((b, g, r))
    return colors


def _remember_track_observation(
    track: LiveTrack,
    box,
    confidence: float,
    frame_width: int | None = None,
    frame_height: int | None = None,
    mask=None,
) -> None:
    track.seen_frames += 1
    track.confidence = float(confidence)
    track.centers.append(_track_center(box))
    track.areas.append(_track_area(box))
    track.boxes.append(tuple(float(v) for v in box))
    if frame_width is not None and frame_height is not None:
        bottom_y, height_ratio = _box_ratios(box, frame_width, frame_height)
        mask_bottom_y, mask_coverage = _mask_bottom_ratio(mask, box, frame_height, frame_width)
        track.bottom_ratios.append(bottom_y)
        track.center_x_ratios.append(_box_center_x_ratio(box, frame_width))
        track.height_ratios.append(height_ratio)
        track.mask_bottom_ratios.append(mask_bottom_y)
        track.mask_coverages.append(mask_coverage)
    del track.centers[:-30]
    del track.areas[:-30]
    del track.boxes[:-30]
    del track.bottom_ratios[:-30]
    del track.center_x_ratios[:-30]
    del track.height_ratios[:-30]
    del track.mask_bottom_ratios[:-30]
    del track.mask_coverages[:-30]


def _motion_ratio(track: LiveTrack, frame_width: int, frame_height: int) -> float:
    if len(track.centers) < 2:
        return 0.0
    xs = [point[0] for point in track.centers]
    ys = [point[1] for point in track.centers]
    span = ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2) ** 0.5
    diagonal = max((frame_width**2 + frame_height**2) ** 0.5, 1.0)
    return span / diagonal


def _area_change_ratio(track: LiveTrack) -> float:
    if len(track.areas) < 2:
        return 0.0
    mean_area = max(sum(track.areas) / len(track.areas), 1.0)
    return (max(track.areas) - min(track.areas)) / mean_area


def _uniform_match_scores(frame, box, uniform_colors: list[tuple[int, int, int]], mask=None) -> tuple[float, float]:
    if not uniform_colors:
        return 0.0, 0.0

    import numpy as np

    height, width = frame.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    box_width = max(1, x2 - x1)
    box_height = max(1, y2 - y1)
    torso_x1 = max(0, x1 + int(box_width * 0.15))
    torso_x2 = min(width, x2 - int(box_width * 0.15))
    torso_y1 = max(0, y1 + int(box_height * 0.20))
    torso_y2 = min(height, y1 + int(box_height * 0.68))
    if torso_x2 <= torso_x1 or torso_y2 <= torso_y1:
        return 0.0, 0.0

    crop = frame[torso_y1:torso_y2, torso_x1:torso_x2]
    if crop.size == 0:
        return 0.0, 0.0
    if mask is not None:
        resized = _resize_mask(mask, height, width)
        if resized is not None:
            mask_crop = resized[torso_y1:torso_y2, torso_x1:torso_x2]
            if mask_crop.any():
                pixels = crop[mask_crop].reshape(-1, 3).astype("float32")
            else:
                pixels = crop.reshape(-1, 3).astype("float32")
        else:
            pixels = crop.reshape(-1, 3).astype("float32")
    else:
            pixels = crop.reshape(-1, 3).astype("float32")
    if len(pixels) < 20:
        return 0.0, 0.0
    best_fraction = 0.0
    best_dark_fraction = 0.0
    brightness = pixels.mean(axis=1)
    for color in uniform_colors:
        target = np.array(color, dtype="float32")
        if float(target.mean()) <= 60.0:
            # Dark/black uniforms need a much stricter test than BGR distance.
            # A broad distance threshold makes grey blurred customers look like black uniforms.
            best_dark_fraction = max(best_dark_fraction, float((brightness <= BLACK_UNIFORM_BRIGHTNESS_MAX).mean()))
            continue
        distances = np.linalg.norm(pixels - target, axis=1)
        best_fraction = max(best_fraction, float((distances <= REGULAR_UNIFORM_DISTANCE_MAX).mean()))
    dark_score = min(1.0, best_dark_fraction / BLACK_UNIFORM_REQUIRED_FRACTION)
    regular_score = min(1.0, best_fraction / REGULAR_UNIFORM_REQUIRED_FRACTION)
    return max(regular_score, dark_score), dark_score


def _uniform_match_score(frame, box, uniform_colors: list[tuple[int, int, int]], mask=None) -> float:
    score, _dark_score = _uniform_match_scores(frame, box, uniform_colors, mask=mask)
    return score


def _face_blur_score(frame, box) -> float:
    import cv2

    height, width = frame.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    box_width = max(1, x2 - x1)
    box_height = max(1, y2 - y1)
    face_x1 = max(0, x1 + int(box_width * 0.18))
    face_x2 = min(width, x2 - int(box_width * 0.18))
    face_y1 = max(0, y1 + int(box_height * 0.04))
    face_y2 = min(height, y1 + int(box_height * 0.34))
    if face_x2 <= face_x1 or face_y2 <= face_y1:
        return 999.0
    crop = frame[face_y1:face_y2, face_x1:face_x2]
    if crop.size == 0:
        return 999.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _update_uniform_evidence(track: LiveTrack, score: float, dark_score: float = 0.0) -> None:
    track.uniform_score = max(track.uniform_score * 0.75, score)
    if score >= UNIFORM_HIT_SCORE:
        track.uniform_hits += 1
    track.dark_uniform_score = max(track.dark_uniform_score * 0.75, dark_score)
    if dark_score >= UNIFORM_HIT_SCORE:
        track.dark_uniform_hits += 1


def _classify_role(
    track: LiveTrack,
    *,
    frame_width: int,
    frame_height: int,
    static_after_frames: int,
    static_motion_threshold: float,
    static_appearance_threshold: float = DEFAULT_STATIC_APPEARANCE_THRESHOLD,
    min_human_bottom_y: float = DEFAULT_MIN_HUMAN_BOTTOM_Y,
    blur_staff_max_variance: float = DEFAULT_BLUR_STAFF_MAX_VARIANCE,
    staff_area_x_min: float = DEFAULT_STAFF_AREA_X_MIN,
    staff_area_bottom_y_max: float = DEFAULT_STAFF_AREA_BOTTOM_Y_MAX,
    staff_uniform_hits: int = DEFAULT_STAFF_UNIFORM_HITS,
) -> tuple[str, float, str]:
    motion = _motion_ratio(track, frame_width, frame_height)
    area_change = _area_change_ratio(track)
    static_after = max(3, static_after_frames)
    static_threshold = max(0.001, static_motion_threshold)
    appearance_threshold = max(0.001, static_appearance_threshold)
    staff_hits = max(2, staff_uniform_hits)
    box_bottom_y = track.bottom_ratios[-1] if track.bottom_ratios else 1.0
    mask_bottom_y = track.mask_bottom_ratios[-1] if track.mask_bottom_ratios else box_bottom_y
    bottom_y = max(mask_bottom_y, box_bottom_y if track.mask_coverages and track.mask_coverages[-1] == 0 else mask_bottom_y)
    height_ratio = track.height_ratios[-1] if track.height_ratios else 1.0
    mask_coverage = track.mask_coverages[-1] if track.mask_coverages else 0.0
    center_x = track.center_x_ratios[-1] if track.center_x_ratios else 0.5
    min_bottom = max(0.05, min(0.98, min_human_bottom_y))
    staff_area_min = max(0.0, min(1.0, staff_area_x_min))
    staff_bottom_max = max(min_bottom, min(1.0, staff_area_bottom_y_max))
    person_like_size = height_ratio >= PERSON_LIKE_HEIGHT_RATIO or mask_coverage >= PERSON_LIKE_MASK_COVERAGE
    blurred_real_person = track.blur_score <= max(0.0, blur_staff_max_variance) and height_ratio >= 0.12
    uniform_match = track.uniform_hits >= staff_hits
    dark_uniform_match = track.dark_uniform_hits >= staff_hits
    staff_area_match = staff_area_min <= 0 or center_x >= staff_area_min
    staff_depth_match = bottom_y <= staff_bottom_max

    if bottom_y < min_bottom and not person_like_size:
        return "ignored_static_display", 0.94, f"above_floor_band_wall_or_poster bottom_y={bottom_y:.2f}"

    small_wall_like = height_ratio < PERSON_LIKE_HEIGHT_RATIO and mask_coverage < PERSON_LIKE_MASK_COVERAGE
    near_wall_band = bottom_y < min_bottom + 0.08 or small_wall_like
    if (
        (small_wall_like or (bottom_y < min_bottom and not blurred_real_person))
        and near_wall_band
        and track.seen_frames >= static_after
        and motion <= static_threshold
        and area_change <= appearance_threshold
    ):
        return "ignored_static_display", 0.88, "static_bbox_wall_or_poster_candidate"

    if dark_uniform_match:
        area_note = " inside_staff_area" if staff_area_match and staff_depth_match else " calibrated_area_soft_override"
        role_confidence = min(0.97, 0.78 + 0.03 * min(track.dark_uniform_hits, 6))
        return (
            "staff",
            role_confidence,
            f"black_uniform_hits={track.dark_uniform_hits} dark_score={track.dark_uniform_score:.2f}{area_note}",
        )

    if uniform_match:
        if not staff_area_match:
            return "customer", 0.74, f"uniform_like_customer_outside_staff_area x={center_x:.2f}"
        if not staff_depth_match:
            return "customer", 0.77, f"uniform_like_foreground_customer bottom_y={bottom_y:.2f}"
        role_confidence = min(0.97, 0.74 + 0.035 * min(track.uniform_hits, 6) + (0.04 if blurred_real_person else 0.0))
        blur_note = f" blur_real_person={track.blur_score:.0f}" if blurred_real_person else ""
        return (
            "staff",
            role_confidence,
            f"uniform_color_match_hits={track.uniform_hits} staff_area_x={center_x:.2f} staff_bottom_y={bottom_y:.2f}{blur_note}",
        )

    if bottom_y < min_bottom and person_like_size:
        return "customer", 0.76, f"large_person_relaxed_floor_band bottom_y={bottom_y:.2f}"

    if blurred_real_person:
        return "customer", 0.84, f"blurred_real_person_without_staff_evidence blur={track.blur_score:.0f}"

    if motion >= max(static_threshold * 1.4, MOVING_CUSTOMER_MOTION_THRESHOLD) or area_change >= MOVING_CUSTOMER_APPEARANCE_THRESHOLD:
        return "customer", min(0.9, 0.58 + min(motion * 8.0, 0.25)), "validated_by_track_motion"

    if track.seen_frames >= 2:
        return "customer", 0.72, f"floor_contact_customer bottom_y={bottom_y:.2f}"

    return "customer_candidate", 0.42, "waiting_for_motion_or_uniform_evidence"


def _update_live_state(stream_id: str, patch: dict) -> None:
    with LIVE_STATES_LOCK:
        state = LIVE_STATES.setdefault(stream_id, {"stream_id": stream_id, "interactions": []})
        state.update(patch)


def _append_interactions(stream_id: str, interactions: list[dict]) -> None:
    if not interactions:
        return
    with LIVE_STATES_LOCK:
        state = LIVE_STATES.setdefault(stream_id, {"stream_id": stream_id, "interactions": []})
        state.setdefault("interactions", []).extend(interactions)
        state["interactions"] = state["interactions"][-40:]


def _draw_detection(frame, track_id: int, box, confidence: float, role: str, role_reason: str, mask=None) -> None:
    import cv2
    import numpy as np

    x1, y1, x2, y2 = [int(v) for v in box]
    colors = {
        "customer": (31, 119, 180),
        "staff": (0, 193, 255),
        "customer_candidate": (156, 163, 175),
        "ignored_static_display": (107, 114, 128),
    }
    labels = {
        "customer": "customer",
        "staff": "staff",
        "customer_candidate": "checking",
        "ignored_static_display": "ignored static display",
    }
    color = colors.get(role, (156, 163, 175))
    thickness = 1 if role == "ignored_static_display" else 2
    resized_mask = _resize_mask(mask, frame.shape[0], frame.shape[1])
    if resized_mask is not None and resized_mask.any():
        overlay = np.zeros_like(frame)
        overlay[resized_mask] = color
        frame[:] = cv2.addWeighted(frame, 1.0, overlay, 0.22, 0)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
    label = f"{labels.get(role, role)} #{track_id} {confidence:.2f}"
    text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.56, 2)[0]
    label_width = min(frame.shape[1] - x1, max(180, text_size[0] + 12))
    cv2.rectangle(frame, (x1, max(0, y1 - 28)), (min(frame.shape[1], x1 + label_width), y1), color, -1)
    cv2.putText(frame, label, (x1 + 4, max(16, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (20, 28, 25), 2)
    if role in {"customer_candidate", "ignored_static_display"}:
        reason = role_reason[:42]
        cv2.putText(frame, reason, (x1 + 4, min(frame.shape[0] - 8, y2 + 18)), cv2.FONT_HERSHEY_SIMPLEX, 0.44, color, 1)


def _detect_interactions(
    *,
    detections: list[dict],
    pair_counts: dict[tuple[int, int], int],
    frame_index: int,
    frame_width: int,
    frame_height: int,
    interaction_distance: float,
    interaction_frames: int,
) -> list[dict]:
    staff = [item for item in detections if item["role"] == "staff"]
    customers = [item for item in detections if item["role"] == "customer"]
    seen_pairs: set[tuple[int, int]] = set()
    interactions = []
    diagonal = max((frame_width**2 + frame_height**2) ** 0.5, 1.0)
    threshold = max(0.01, interaction_distance) * diagonal
    for staff_item in staff:
        sx, sy = staff_item["center"]
        for customer_item in customers:
            cx, cy = customer_item["center"]
            distance = ((sx - cx) ** 2 + (sy - cy) ** 2) ** 0.5
            pair = (staff_item["track_id"], customer_item["track_id"])
            if distance <= threshold:
                pair_counts[pair] = pair_counts.get(pair, 0) + 1
                seen_pairs.add(pair)
                if pair_counts[pair] == interaction_frames:
                    interactions.append(
                        {
                            "frame_index": frame_index,
                            "staff_track_id": staff_item["track_id"],
                            "customer_track_id": customer_item["track_id"],
                            "message": (
                                f"possible staff-customer interaction: staff #{staff_item['track_id']} "
                                f"near customer #{customer_item['track_id']} for {interaction_frames} sampled frames"
                            ),
                        }
                    )
    for pair in list(pair_counts):
        if pair not in seen_pairs:
            pair_counts[pair] = max(0, pair_counts[pair] - 1)
            if pair_counts[pair] == 0:
                del pair_counts[pair]
    return interactions


def mjpeg_detection_stream(
    *,
    clip_path: Path,
    store_id: Optional[str] = None,
    model_name: str = "yolo11n.pt",
    mask_refiner: str = "off",
    conf: float = 0.25,
    imgsz: int = 960,
    stride: int = 5,
    stream_fps: float = 4.0,
    device: Optional[str] = None,
    stream_id: str = "default",
    uniform_bgr: str = DEFAULT_UNIFORM_BGR,
    staff_uniform_hits: int = DEFAULT_STAFF_UNIFORM_HITS,
    static_after_frames: int = DEFAULT_STATIC_AFTER_FRAMES,
    static_motion_threshold: float = DEFAULT_STATIC_MOTION_THRESHOLD,
    static_appearance_threshold: float = DEFAULT_STATIC_APPEARANCE_THRESHOLD,
    min_human_bottom_y: float = DEFAULT_MIN_HUMAN_BOTTOM_Y,
    blur_staff_max_variance: float = DEFAULT_BLUR_STAFF_MAX_VARIANCE,
    staff_area_x_min: float = DEFAULT_STAFF_AREA_X_MIN,
    staff_area_bottom_y_max: float = DEFAULT_STAFF_AREA_BOTTOM_Y_MAX,
    interaction_distance: float = 0.22,
    interaction_frames: int = 3,
) -> Generator[bytes, None, None]:
    import cv2

    _update_live_state(
        stream_id,
        {
            "running": True,
            "status": "loading_model",
            "clip": clip_path.name,
            "store_id": store_id or _store_id_for_clip(clip_path),
            "model": model_name,
            "mask_refiner": mask_refiner,
            "tracker_backend": "loading",
            "tracking_warning": None,
            "detections": [],
            "interactions": [],
            "frame_index": 0,
        },
    )
    try:
        model = _cached_model(model_name)
    except DetectorUnavailable as exc:
        _update_live_state(stream_id, {"running": False, "status": f"model_unavailable: {exc}"})
        yield _error_frame(f"Model unavailable: {exc}")
        return
    uniform_colors = _parse_uniform_bgr(uniform_bgr)

    capture = cv2.VideoCapture(str(clip_path))
    if not capture.isOpened():
        _update_live_state(stream_id, {"running": False, "status": "clip_open_failed"})
        yield _error_frame(f"Could not open {clip_path.name}")
        return

    is_rtdetr = model.__class__.__name__.lower().startswith("rtdetr")
    tracker = CentroidTracker(max_distance=95.0, max_missed=10)
    role_tracks: dict[int, LiveTrack] = {}
    pair_counts: dict[tuple[int, int], int] = {}
    frame_index = 0
    output_width = 1080
    delay = 1.0 / max(stream_fps, 0.1)
    tracker_backend = "centroid" if is_rtdetr else "botsort"
    tracking_warning: str | None = None
    try:
        while get_live_state(stream_id).get("running", True):
            ok, frame = capture.read()
            if not ok:
                capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                frame_index = 0
                continue
            frame_index += 1
            if frame_index % max(stride, 1) != 0:
                continue

            scale = min(1.0, output_width / max(frame.shape[1], 1))
            if scale < 1.0:
                frame = cv2.resize(frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale)))

            common = {
                "source": frame,
                "classes": [0],
                "conf": max(0.01, min(float(conf), 0.99)),
                "imgsz": int(imgsz),
                "verbose": False,
            }
            if device:
                common["device"] = device

            detections = []
            if is_rtdetr:
                tracker_backend = "centroid"
                try:
                    result = model.predict(**common)[0]
                except Exception as exc:
                    logger.exception("video_demo_predict_failed")
                    _update_live_state(stream_id, {"running": False, "status": f"stream_error: {exc}"})
                    yield _error_frame(f"Live preview error: {exc}")
                    return
                boxes = getattr(result, "boxes", None)
                if boxes is not None:
                    xyxy = boxes.xyxy.cpu().numpy().tolist()
                    confs = boxes.conf.cpu().numpy().tolist()
                    tracks = tracker.update(zip(xyxy, confs))
                    prompt_masks = _refine_masks_with_prompt(frame, [track.box for track in tracks], mask_refiner, device)
                    track_items = [
                        (
                            track.track_id,
                            track.box,
                            track.confidence,
                            prompt_masks[index] if index < len(prompt_masks) else None,
                        )
                        for index, track in enumerate(tracks)
                    ]
                else:
                    track_items = []
            else:
                use_centroid_ids = False
                try:
                    result = model.track(persist=True, tracker="botsort.yaml", **common)[0]
                    tracker_backend = "botsort"
                except Exception as exc:
                    use_centroid_ids = True
                    tracker_backend = "centroid"
                    if tracking_warning is None:
                        tracking_warning = f"ultralytics_tracker_fallback: {exc}"
                        logger.warning("video_demo_tracker_fallback: %s", exc)
                    _update_live_state(
                        stream_id,
                        {
                            "status": "streaming_with_tracker_fallback",
                            "tracker_backend": tracker_backend,
                            "tracking_warning": tracking_warning,
                        },
                    )
                    try:
                        result = model.predict(**common)[0]
                    except Exception as predict_exc:
                        logger.exception("video_demo_fallback_predict_failed")
                        _update_live_state(stream_id, {"running": False, "status": f"stream_error: {predict_exc}"})
                        yield _error_frame(f"Live preview error: {predict_exc}")
                        return
                boxes = getattr(result, "boxes", None)
                if boxes is not None:
                    xyxy = boxes.xyxy.cpu().numpy().tolist()
                    confs = boxes.conf.cpu().numpy().tolist()
                    native_masks = _extract_result_masks(result, frame.shape[0], frame.shape[1])
                    prompt_masks = []
                    if mask_refiner not in {"", "auto", "off"}:
                        prompt_masks = _refine_masks_with_prompt(frame, xyxy, mask_refiner, device)
                    if mask_refiner == "off":
                        selected_masks = []
                    elif len(prompt_masks) == len(xyxy):
                        selected_masks = prompt_masks
                    else:
                        selected_masks = native_masks
                    if boxes.id is not None and not use_centroid_ids:
                        ids = boxes.id.cpu().numpy().astype(int).tolist()
                        track_items = [
                            (
                                int(track_id),
                                box,
                                confidence,
                                selected_masks[index] if index < len(selected_masks) else None,
                            )
                            for index, (track_id, box, confidence) in enumerate(zip(ids, xyxy, confs))
                        ]
                    else:
                        tracks = tracker.update(zip(xyxy, confs))
                        track_items = [
                            (
                                track.track_id,
                                track.box,
                                track.confidence,
                                selected_masks[index] if index < len(selected_masks) else None,
                            )
                            for index, track in enumerate(tracks)
                        ]
                else:
                    track_items = []

            for track_id, box, confidence, mask in track_items:
                live_track = role_tracks.setdefault(track_id, LiveTrack(first_frame=frame_index))
                _remember_track_observation(live_track, box, confidence, frame.shape[1], frame.shape[0], mask=mask)
                uniform_score, dark_uniform_score = _uniform_match_scores(frame, box, uniform_colors, mask=mask)
                live_track.blur_score = _face_blur_score(frame, box)
                _update_uniform_evidence(live_track, uniform_score, dark_uniform_score)
                role, role_confidence, role_reason = _classify_role(
                    live_track,
                    frame_width=frame.shape[1],
                    frame_height=frame.shape[0],
                    static_after_frames=static_after_frames,
                    static_motion_threshold=static_motion_threshold,
                    static_appearance_threshold=static_appearance_threshold,
                    min_human_bottom_y=min_human_bottom_y,
                    blur_staff_max_variance=blur_staff_max_variance,
                    staff_area_x_min=staff_area_x_min,
                    staff_area_bottom_y_max=staff_area_bottom_y_max,
                    staff_uniform_hits=staff_uniform_hits,
                )
                live_track.role = role
                live_track.role_confidence = role_confidence
                live_track.role_reason = role_reason
                center = _track_center(box)
                detection = {
                    "track_id": int(track_id),
                    "role": live_track.role,
                    "confidence": float(confidence),
                    "role_confidence": live_track.role_confidence,
                    "role_reason": live_track.role_reason,
                    "center": center,
                    "seen_frames": live_track.seen_frames,
                    "uniform_score": uniform_score,
                    "dark_uniform_score": dark_uniform_score,
                    "motion_ratio": _motion_ratio(live_track, frame.shape[1], frame.shape[0]),
                    "bottom_y": live_track.mask_bottom_ratios[-1] if live_track.mask_bottom_ratios else (live_track.bottom_ratios[-1] if live_track.bottom_ratios else None),
                    "box_bottom_y": live_track.bottom_ratios[-1] if live_track.bottom_ratios else None,
                    "center_x": live_track.center_x_ratios[-1] if live_track.center_x_ratios else None,
                    "mask_available": mask is not None,
                    "mask_coverage": live_track.mask_coverages[-1] if live_track.mask_coverages else 0.0,
                    "blur_score": live_track.blur_score,
                    "counted": live_track.role in {"customer", "staff"},
                }
                detections.append(detection)
                _draw_detection(frame, track_id, box, confidence, live_track.role, live_track.role_reason, mask=mask)

            interactions = _detect_interactions(
                detections=detections,
                pair_counts=pair_counts,
                frame_index=frame_index,
                frame_width=frame.shape[1],
                frame_height=frame.shape[0],
                interaction_distance=interaction_distance,
                interaction_frames=max(1, interaction_frames),
            )
            _append_interactions(stream_id, interactions)
            _update_live_state(
                stream_id,
                {
                    "running": True,
                    "status": "streaming_with_tracker_fallback" if tracking_warning else "streaming",
                    "tracker_backend": tracker_backend,
                    "tracking_warning": tracking_warning,
                    "frame_index": frame_index,
                    "detections": [
                        {
                            "track_id": item["track_id"],
                            "role": item["role"],
                            "confidence": round(item["confidence"], 4),
                            "role_confidence": round(item["role_confidence"], 4),
                            "role_reason": item["role_reason"],
                            "seen_frames": item["seen_frames"],
                            "uniform_score": round(item["uniform_score"], 4),
                            "dark_uniform_score": round(item["dark_uniform_score"], 4),
                            "motion_ratio": round(item["motion_ratio"], 5),
                            "bottom_y": round(item["bottom_y"], 4) if item["bottom_y"] is not None else None,
                            "box_bottom_y": round(item["box_bottom_y"], 4) if item["box_bottom_y"] is not None else None,
                            "center_x": round(item["center_x"], 4) if item["center_x"] is not None else None,
                            "mask_available": item["mask_available"],
                            "mask_coverage": round(item["mask_coverage"], 5),
                            "blur_score": round(item["blur_score"], 2),
                            "counted": item["counted"],
                        }
                        for item in detections
                    ],
                },
            )

            cv2.putText(frame, f"{clip_path.name} | {model_name} | masks {mask_refiner} | frame {frame_index}", (14, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(frame, "Masks refine floor/uniform evidence | staff needs uniform + calibrated area | no audio", (14, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 2)
            encoded_ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
            if encoded_ok:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + encoded.tobytes() + b"\r\n"
            time.sleep(delay)
    finally:
        capture.release()
        _update_live_state(stream_id, {"running": False, "status": "stopped"})


def _error_frame(message: str) -> bytes:
    import cv2
    import numpy as np

    frame = np.zeros((360, 900, 3), dtype=np.uint8)
    frame[:] = (22, 31, 29)
    cv2.putText(frame, message[:90], (24, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (245, 245, 245), 2)
    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    payload = encoded.tobytes() if ok else b""
    return b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + payload + b"\r\n"
