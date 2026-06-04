from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import get_settings


BRIGADE_ZONES = [
    {
        "zone_id": "ENTRY_THRESHOLD",
        "sku_zone": None,
        "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 0.25], [0.0, 0.25]],
    },
    {
        "zone_id": "SKINCARE",
        "sku_zone": "SKINCARE",
        "polygon": [[0.05, 0.28], [0.48, 0.28], [0.48, 0.70], [0.05, 0.70]],
    },
    {
        "zone_id": "MAKEUP",
        "sku_zone": "MAKEUP",
        "polygon": [[0.52, 0.28], [0.96, 0.28], [0.96, 0.70], [0.52, 0.70]],
    },
    {
        "zone_id": "BILLING",
        "sku_zone": "BILLING",
        "polygon": [[0.55, 0.72], [0.98, 0.72], [0.98, 0.98], [0.55, 0.98]],
    },
]

MUMBAI_ZONES = [
    {
        "zone_id": "PURPLLE_MUM_1076_ENTRY",
        "sku_zone": None,
        "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 0.22], [0.0, 0.22]],
    },
    {
        "zone_id": "PURPLLE_MUM_1076_Z01",
        "sku_zone": "SKINCARE",
        "polygon": [[0.04, 0.24], [0.48, 0.24], [0.48, 0.68], [0.04, 0.68]],
    },
    {
        "zone_id": "PURPLLE_MUM_1076_Z02",
        "sku_zone": "MAKEUP",
        "polygon": [[0.50, 0.24], [0.96, 0.24], [0.96, 0.68], [0.50, 0.68]],
    },
    {
        "zone_id": "PURPLLE_MUM_1076_Z03",
        "sku_zone": "FRAGRANCE",
        "polygon": [[0.05, 0.69], [0.48, 0.69], [0.48, 0.96], [0.05, 0.96]],
    },
    {
        "zone_id": "PURPLLE_MUM_1076_Z_BILLING_01",
        "sku_zone": "BILLING",
        "polygon": [[0.52, 0.70], [0.98, 0.70], [0.98, 0.98], [0.52, 0.98]],
    },
]

DEFAULT_STORE_LAYOUTS = [
    {
        "store_id": "STORE_BLR_002",
        "store_name": "Brigade Road",
        "aliases": ["ST1008", "Brigade_Bangalore", "Store 1", "store_1"],
        "source_folder": "Store 1",
        "open_hours": {"start": "10:00", "end": "22:00", "timezone": "Asia/Kolkata"},
        "zones": BRIGADE_ZONES,
        "cameras": [
            {
                "camera_id": "STORE_BLR_002_CAM_ZONE_01",
                "camera_type": "MAIN_FLOOR",
                "source_hint": "CAM 1 - zone.mp4",
            },
            {
                "camera_id": "STORE_BLR_002_CAM_ZONE_02",
                "camera_type": "MAIN_FLOOR",
                "source_hint": "CAM 2 - zone.mp4",
            },
            {
                "camera_id": "STORE_BLR_002_CAM_ENTRY_01",
                "camera_type": "ENTRY",
                "entry_line": [[0.08, 0.55], [0.92, 0.55]],
                "inbound_side": "above_to_below",
                "source_hint": "CAM 3 - entry.mp4",
            },
            {
                "camera_id": "STORE_BLR_002_CAM_BILLING_01",
                "camera_type": "BILLING",
                "source_hint": "CAM 5 - billing.mp4",
            },
        ],
    },
    {
        "store_id": "STORE_MUM_1076",
        "store_name": "Mumbai Store 1076",
        "aliases": ["ST1076", "store_1076", "PURPLLE_MUM_1076", "Store 2", "store_2"],
        "source_folder": "Store 2",
        "open_hours": {"start": "10:00", "end": "22:00", "timezone": "Asia/Kolkata"},
        "zones": MUMBAI_ZONES,
        "cameras": [
            {
                "camera_id": "PURPLLE_MUM_1076_CAM_ENTRY_01",
                "camera_type": "ENTRY",
                "entry_line": [[0.08, 0.56], [0.92, 0.56]],
                "inbound_side": "above_to_below",
                "source_hint": "entry 1.mp4",
            },
            {
                "camera_id": "PURPLLE_MUM_1076_CAM_ENTRY_02",
                "camera_type": "ENTRY",
                "entry_line": [[0.10, 0.56], [0.90, 0.56]],
                "inbound_side": "above_to_below",
                "source_hint": "entry 2.mp4",
            },
            {
                "camera_id": "PURPLLE_MUM_1076_CAM_ZONE_01",
                "camera_type": "MAIN_FLOOR",
                "source_hint": "zone.mp4",
            },
            {
                "camera_id": "PURPLLE_MUM_1076_CAM_BILLING_01",
                "camera_type": "BILLING",
                "source_hint": "billing_area.mp4",
            },
        ],
    },
]

DEFAULT_LAYOUT = {
    "store_id": "STORE_BLR_002",
    "store_name": "Brigade Road",
    "aliases": ["ST1008", "Brigade_Bangalore", "Store 1", "store_1"],
    "open_hours": {"start": "10:00", "end": "22:00", "timezone": "Asia/Kolkata"},
    "zones": BRIGADE_ZONES,
    "cameras": DEFAULT_STORE_LAYOUTS[0]["cameras"],
    "stores": DEFAULT_STORE_LAYOUTS,
}


@lru_cache(maxsize=4)
def load_layout(path: Optional[str] = None) -> Dict[str, Any]:
    settings = get_settings()
    layout_path = Path(path) if path else settings.layout_config_path
    if layout_path.exists():
        try:
            return json.loads(layout_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return DEFAULT_LAYOUT
    return DEFAULT_LAYOUT


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def store_layouts(layout: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    raw = layout or load_layout()
    stores = raw.get("stores")
    if isinstance(stores, list) and stores:
        records = [dict(store) for store in stores if isinstance(store, dict)]
    else:
        records = [dict(raw)]
    if not records:
        records = [dict(DEFAULT_STORE_LAYOUTS[0])]
    for record in records:
        record.setdefault("open_hours", raw.get("open_hours") or DEFAULT_LAYOUT["open_hours"])
        record.setdefault("zones", DEFAULT_LAYOUT["zones"])
        record.setdefault("cameras", [])
        record.setdefault("aliases", [])
    return records


def find_store_layout(raw_store_id: Optional[str] = None, layout: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    records = store_layouts(layout)
    if raw_store_id:
        target = _norm(raw_store_id)
        for record in records:
            candidates = [
                record.get("store_id"),
                record.get("store_name"),
                record.get("source_folder"),
                *(record.get("aliases") or []),
            ]
            if target in {_norm(candidate) for candidate in candidates if candidate}:
                return record
    default_id = get_settings().default_store_id
    for record in records:
        if record.get("store_id") == default_id:
            return record
    return records[0]


def store_name_for_id(store_id: str) -> str:
    record = find_store_layout(store_id)
    return str(record.get("store_name") or store_id)


def known_zones(store_id: str) -> List[Dict[str, Any]]:
    layout = find_store_layout(store_id)
    return list(layout.get("zones") or DEFAULT_LAYOUT["zones"])


def canonical_store_id(raw_store_id: Optional[str] = None) -> str:
    if raw_store_id is None or str(raw_store_id).strip() == "":
        return get_settings().default_store_id
    cleaned = str(raw_store_id).strip()
    target = _norm(cleaned)
    for record in store_layouts():
        candidates = [
            record.get("store_id"),
            record.get("store_name"),
            record.get("source_folder"),
            *(record.get("aliases") or []),
        ]
        if target in {_norm(candidate) for candidate in candidates if candidate}:
            return str(record.get("store_id"))
    return cleaned
