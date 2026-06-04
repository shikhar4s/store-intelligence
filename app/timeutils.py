from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Optional, Tuple


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def isoformat_z(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return ensure_utc(value).isoformat().replace("+00:00", "Z")


def day_window(day: date) -> Tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=timezone.utc)
    return start, end


def parse_optional_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    return ensure_utc(datetime.fromisoformat(cleaned))
