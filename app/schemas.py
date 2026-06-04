from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.layout_store import canonical_store_id
from app.timeutils import ensure_utc


class EventType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    ZONE_ENTER = "ZONE_ENTER"
    ZONE_EXIT = "ZONE_EXIT"
    ZONE_DWELL = "ZONE_DWELL"
    BILLING_QUEUE_JOIN = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_ABANDON = "BILLING_QUEUE_ABANDON"
    REENTRY = "REENTRY"


class EventMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    queue_depth: Optional[int] = None
    sku_zone: Optional[str] = None
    session_seq: int = Field(default=1, ge=1)

    @field_validator("queue_depth")
    @classmethod
    def queue_depth_non_negative(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 0:
            raise ValueError("queue_depth must be non-negative")
        return value


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    store_id: str = Field(min_length=1, max_length=64)
    camera_id: str = Field(min_length=1, max_length=64)
    visitor_id: str = Field(min_length=1, max_length=96)
    event_type: EventType
    timestamp: datetime
    zone_id: Optional[str] = None
    dwell_ms: int = Field(default=0, ge=0)
    is_staff: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: EventMetadata = Field(default_factory=EventMetadata)

    @field_validator("event_id")
    @classmethod
    def event_id_is_uuid(cls, value: str) -> str:
        UUID(str(value), version=4)
        return str(value)

    @field_validator("store_id")
    @classmethod
    def canonicalize_store(cls, value: str) -> str:
        return canonical_store_id(value)

    @field_validator("timestamp")
    @classmethod
    def timestamp_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class IngestError(BaseModel):
    index: int
    event_id: Optional[str] = None
    code: str
    message: str


class IngestResponse(BaseModel):
    accepted_count: int
    duplicate_count: int
    rejected_count: int
    errors: List[IngestError]


class PosTransactionIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    store_id: str
    transaction_id: str
    timestamp: datetime
    amount: float = Field(default=0.0, ge=0.0)

    @field_validator("timestamp")
    @classmethod
    def pos_timestamp_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("store_id")
    @classmethod
    def pos_store_id_canonical(cls, value: str) -> str:
        return canonical_store_id(value)


def extract_events_payload(payload: Any) -> List[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return payload["events"]
    raise ValueError("Expected a JSON array of events or an object with an 'events' array")


def validation_message(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []))
        parts.append(f"{loc}: {err.get('msg')}")
    return "; ".join(parts) or "Invalid event"
