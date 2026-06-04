from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.layout_store import canonical_store_id, load_layout, store_layouts
from app.models import EventRecord, PosTransaction
from app.timeutils import isoformat_z


def list_stores(db: Session) -> dict:
    settings = get_settings()
    layout = load_layout()
    configured_stores = store_layouts(layout)
    names = {
        str(store.get("store_id")): str(store.get("store_name") or store.get("store_id"))
        for store in configured_stores
        if store.get("store_id")
    }

    event_rows = {
        row.store_id: {
            "event_count": row.event_count,
            "last_event_timestamp": row.last_event_timestamp,
        }
        for row in db.query(
            EventRecord.store_id.label("store_id"),
            func.count(EventRecord.id).label("event_count"),
            func.max(EventRecord.timestamp).label("last_event_timestamp"),
        )
        .group_by(EventRecord.store_id)
        .all()
    }
    pos_rows = {
        row.store_id: row.pos_count
        for row in db.query(
            PosTransaction.store_id.label("store_id"),
            func.count(PosTransaction.id).label("pos_count"),
        )
        .group_by(PosTransaction.store_id)
        .all()
    }
    configured_ids = {str(store.get("store_id")) for store in configured_stores if store.get("store_id")}
    store_ids = {settings.default_store_id, *configured_ids, *event_rows.keys(), *pos_rows.keys()}
    stores = []
    for store_id in sorted(store_ids):
        canonical_id = canonical_store_id(store_id)
        event_info = event_rows.get(store_id, {})
        stores.append(
            {
                "store_id": store_id,
                "display_name": names.get(canonical_id, names.get(store_id, store_id)),
                "event_count": int(event_info.get("event_count") or 0),
                "pos_transaction_count": int(pos_rows.get(store_id) or 0),
                "last_event_timestamp": isoformat_z(event_info.get("last_event_timestamp")),
                "is_default": store_id == settings.default_store_id,
            }
        )
    return {"stores": stores}
