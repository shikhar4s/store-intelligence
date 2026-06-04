from __future__ import annotations

from typing import Any, List

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.errors import ServiceUnavailableError, structured_error
from app.models import PosTransaction
from app.schemas import PosTransactionIn


def ingest_pos_payload(db: Session, payload: Any) -> dict:
    raw_transactions = payload.get("transactions") if isinstance(payload, dict) else payload
    if not isinstance(raw_transactions, list):
        raise HTTPException(
            status_code=400,
            detail=structured_error("INVALID_PAYLOAD", "Expected a list or {'transactions': [...]}"),
        )

    accepted = 0
    duplicates = 0
    errors: List[dict] = []
    seen: set[tuple[str, str]] = set()

    for index, raw in enumerate(raw_transactions):
        try:
            item = PosTransactionIn.model_validate(raw)
        except ValidationError as exc:
            errors.append({"index": index, "code": "VALIDATION_ERROR", "message": str(exc)})
            continue
        key = (item.store_id, item.transaction_id)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        exists = (
            db.query(PosTransaction.id)
            .filter(
                PosTransaction.store_id == item.store_id,
                PosTransaction.transaction_id == item.transaction_id,
            )
            .first()
        )
        if exists:
            duplicates += 1
            continue
        db.add(
            PosTransaction(
                store_id=item.store_id,
                transaction_id=item.transaction_id,
                timestamp=item.timestamp,
                amount=item.amount,
                raw=dict(raw),
            )
        )
        accepted += 1

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ServiceUnavailableError("POS transaction write conflict") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise ServiceUnavailableError("POS transaction write failed") from exc

    return {
        "accepted_count": accepted,
        "duplicate_count": duplicates,
        "rejected_count": len(errors),
        "errors": errors,
    }
