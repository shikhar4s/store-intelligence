from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from app.layout_store import canonical_store_id


LEGACY_EVENT_TYPES = {
    "entry": "ENTRY",
    "exit": "EXIT",
    "zone_entered": "ZONE_ENTER",
    "zone_exited": "ZONE_EXIT",
    "zone_dwell": "ZONE_DWELL",
    "queue_joined": "BILLING_QUEUE_JOIN",
    "queue_completed": "BILLING_QUEUE_JOIN",
    "queue_abandoned": "BILLING_QUEUE_ABANDON",
    "reentry": "REENTRY",
}


def normalize_event_batch(raw_events: Iterable[Any]) -> list[Any]:
    events = list(raw_events)
    visitor_map = _build_legacy_visitor_map(events)
    return [_normalize_event(event, visitor_map) for event in events]


def _normalize_event(raw: Any, visitor_map: dict[tuple[str, str, str, str], str]) -> Any:
    if not isinstance(raw, dict) or "event_id" in raw:
        return raw

    raw_type = str(raw.get("event_type") or "").strip()
    event_type = LEGACY_EVENT_TYPES.get(raw_type.lower())
    if not event_type:
        return raw

    store_id = canonical_store_id(raw.get("store_id") or raw.get("store_code"))
    visitor_id = _visitor_id(raw, store_id, visitor_map)
    timestamp = _timestamp_for(raw, event_type)
    zone_id = raw.get("zone_id")
    queue_depth = _safe_int(raw.get("queue_depth"))
    if queue_depth is None and event_type == "BILLING_QUEUE_JOIN":
        queue_depth = _safe_int(raw.get("queue_position_at_join"))

    metadata: Dict[str, Any] = {
        "queue_depth": queue_depth,
        "sku_zone": raw.get("sku_zone") or raw.get("zone_type"),
        "session_seq": _safe_int(raw.get("session_seq")) or 1,
        "source_schema": "challenge_sample_events_v2",
        "source_event_type": raw_type,
        "raw_store_id": raw.get("store_id") or raw.get("store_code"),
    }
    for key in (
        "id_token",
        "track_id",
        "group_id",
        "group_size",
        "gender_pred",
        "gender",
        "age_pred",
        "age",
        "age_bucket",
        "is_face_hidden",
        "zone_name",
        "zone_type",
        "is_revenue_zone",
        "zone_hotspot_x",
        "zone_hotspot_y",
        "queue_event_id",
        "queue_join_ts",
        "queue_served_ts",
        "queue_exit_ts",
        "wait_seconds",
        "queue_position_at_join",
        "abandoned",
    ):
        if key in raw:
            metadata[key] = raw[key]

    return {
        "event_id": _stable_uuid_v4(raw),
        "store_id": store_id,
        "camera_id": _camera_id(raw.get("camera_id"), store_id),
        "visitor_id": visitor_id,
        "event_type": event_type,
        "timestamp": timestamp,
        "zone_id": str(zone_id) if zone_id not in (None, "") else None,
        "dwell_ms": _dwell_ms(raw, event_type),
        "is_staff": _safe_bool(raw.get("is_staff", False)),
        "confidence": _confidence_for(raw, event_type),
        "metadata": metadata,
    }


def _build_legacy_visitor_map(events: list[Any]) -> dict[tuple[str, str, str, str], str]:
    exact: dict[tuple[str, str, str, str], str] = {}
    bucket_candidates: dict[tuple[str, str, str, str], set[str]] = {}
    for raw in events:
        if not isinstance(raw, dict) or not raw.get("id_token"):
            continue
        store_id = canonical_store_id(raw.get("store_id") or raw.get("store_code"))
        visitor_id = _clean_identifier(raw.get("id_token"), "VIS")
        gender = _norm(raw.get("gender_pred") or raw.get("gender"))
        age = str(raw.get("age_pred") or raw.get("age") or "")
        bucket = _norm(raw.get("age_bucket"))
        if gender or age or bucket:
            exact[(store_id, gender, age, bucket)] = visitor_id
            bucket_candidates.setdefault((store_id, gender, "", bucket), set()).add(visitor_id)

    for key, candidates in bucket_candidates.items():
        if len(candidates) == 1:
            exact.setdefault(key, next(iter(candidates)))
    return exact


def _visitor_id(raw: dict[str, Any], store_id: str, visitor_map: dict[tuple[str, str, str, str], str]) -> str:
    if raw.get("id_token"):
        return _clean_identifier(raw.get("id_token"), "VIS")
    gender = _norm(raw.get("gender_pred") or raw.get("gender"))
    age = str(raw.get("age_pred") or raw.get("age") or "")
    bucket = _norm(raw.get("age_bucket"))
    mapped = visitor_map.get((store_id, gender, age, bucket)) or visitor_map.get((store_id, gender, "", bucket))
    if mapped:
        return mapped
    track_id = raw.get("track_id") or raw.get("id") or raw.get("queue_event_id")
    return _clean_identifier(f"VIS_{track_id}" if track_id is not None else f"VIS_{store_id}", "VIS")


def _timestamp_for(raw: dict[str, Any], event_type: str) -> str:
    if event_type == "BILLING_QUEUE_ABANDON":
        raw_ts = raw.get("queue_exit_ts") or raw.get("event_time") or raw.get("event_timestamp")
    elif event_type == "BILLING_QUEUE_JOIN":
        raw_ts = raw.get("queue_join_ts") or raw.get("event_time") or raw.get("event_timestamp")
    else:
        raw_ts = raw.get("event_timestamp") or raw.get("event_time") or raw.get("timestamp")
    return _parse_timestamp(raw_ts).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return datetime.now(timezone.utc)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            else:
                return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    return parsed.astimezone(timezone.utc)


def _dwell_ms(raw: dict[str, Any], event_type: str) -> int:
    if raw.get("dwell_ms") is not None:
        return max(0, _safe_int(raw.get("dwell_ms")) or 0)
    if event_type in {"ZONE_DWELL", "BILLING_QUEUE_ABANDON"} and raw.get("wait_seconds") is not None:
        return max(0, (_safe_int(raw.get("wait_seconds")) or 0) * 1000)
    return 0


def _confidence_for(raw: dict[str, Any], event_type: str) -> float:
    explicit = raw.get("confidence") or raw.get("det_confidence")
    if explicit is not None:
        try:
            return max(0.0, min(float(explicit), 1.0))
        except (TypeError, ValueError):
            pass
    if event_type in {"ENTRY", "EXIT", "REENTRY"}:
        return 0.86
    if event_type.startswith("ZONE_"):
        return 0.80
    return 0.78


def _camera_id(value: Any, store_id: str) -> str:
    raw = str(value or "CAM_UNKNOWN").strip()
    cleaned = _clean_identifier(raw.upper(), "CAM")
    if store_id == "STORE_MUM_1076" and cleaned.startswith("CAM"):
        return f"PURPLLE_MUM_1076_{cleaned}"
    return cleaned


def _stable_uuid_v4(raw: dict[str, Any]) -> str:
    stable_source = json.dumps(raw, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    digest = hashlib.md5(stable_source).digest()
    return str(UUID(bytes=digest, version=4))


def _clean_identifier(value: Any, fallback_prefix: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_:-]+", "_", str(value or "").strip()).strip("_")
    return cleaned[:96] if cleaned else f"{fallback_prefix}_UNKNOWN"


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _safe_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "staff"}
