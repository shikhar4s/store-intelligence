from __future__ import annotations

from typing import Any, Iterable, List

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.event_normalizer import normalize_event_batch
from app.errors import ServiceUnavailableError, structured_error
from app.models import EventRecord, IngestionAudit
from app.schemas import EventIn, IngestError, IngestResponse, extract_events_payload, validation_message


def _event_to_record(event: EventIn) -> EventRecord:
    return EventRecord(
        event_id=event.event_id,
        store_id=event.store_id,
        camera_id=event.camera_id,
        visitor_id=event.visitor_id,
        event_type=event.event_type.value,
        timestamp=event.timestamp,
        zone_id=event.zone_id,
        dwell_ms=event.dwell_ms,
        is_staff=event.is_staff,
        confidence=event.confidence,
        event_metadata=event.metadata.model_dump(),
    )


def ingest_payload(db: Session, payload: Any, trace_id: str | None = None) -> IngestResponse:
    settings = get_settings()
    try:
        raw_events = extract_events_payload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=structured_error("INVALID_PAYLOAD", str(exc))) from exc

    raw_events = normalize_event_batch(raw_events)

    if len(raw_events) > settings.ingest_batch_limit:
        raise HTTPException(
            status_code=413,
            detail=structured_error(
                "BATCH_TOO_LARGE",
                f"Batch contains {len(raw_events)} events; limit is {settings.ingest_batch_limit}",
            ),
        )

    valid: List[tuple[int, EventIn]] = []
    errors: List[IngestError] = []
    seen_in_batch: set[str] = set()
    duplicate_count = 0

    for index, raw in enumerate(raw_events):
        raw_event_id = raw.get("event_id") if isinstance(raw, dict) else None
        try:
            event = EventIn.model_validate(raw)
        except (ValidationError, ValueError) as exc:
            message = validation_message(exc) if isinstance(exc, ValidationError) else str(exc)
            errors.append(
                IngestError(index=index, event_id=raw_event_id, code="VALIDATION_ERROR", message=message)
            )
            continue
        if event.event_id in seen_in_batch:
            duplicate_count += 1
            continue
        seen_in_batch.add(event.event_id)
        valid.append((index, event))

    existing_ids: set[str] = set()
    if valid:
        ids = [event.event_id for _, event in valid]
        try:
            existing_ids = {
                row[0]
                for row in db.query(EventRecord.event_id)
                .filter(EventRecord.event_id.in_(ids))
                .all()
            }
        except SQLAlchemyError as exc:
            raise ServiceUnavailableError("Database lookup failed") from exc

    accepted_count = 0
    for _, event in valid:
        if event.event_id in existing_ids:
            duplicate_count += 1
            continue
        db.add(_event_to_record(event))
        accepted_count += 1

    db.add(
        IngestionAudit(
            trace_id=trace_id,
            accepted_count=accepted_count,
            duplicate_count=duplicate_count,
            rejected_count=len(errors),
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ServiceUnavailableError("Database write conflict while ingesting events") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise ServiceUnavailableError("Database write failed") from exc

    return IngestResponse(
        accepted_count=accepted_count,
        duplicate_count=duplicate_count,
        rejected_count=len(errors),
        errors=errors,
    )


def count_events_payload(payload: Any) -> int:
    try:
        return len(extract_events_payload(payload))
    except ValueError:
        return 0
