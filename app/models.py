from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from app.database import Base


def utc_created_at() -> datetime:
    return datetime.now(timezone.utc)


class EventRecord(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    event_id = Column(String(64), nullable=False, unique=True, index=True)
    store_id = Column(String(64), nullable=False, index=True)
    camera_id = Column(String(64), nullable=False, index=True)
    visitor_id = Column(String(96), nullable=False, index=True)
    event_type = Column(String(32), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    zone_id = Column(String(96), nullable=True, index=True)
    dwell_ms = Column(Integer, nullable=False, default=0)
    is_staff = Column(Boolean, nullable=False, default=False, index=True)
    confidence = Column(Float, nullable=False, default=0.0)
    event_metadata = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_created_at)

    __table_args__ = (
        Index("ix_events_store_timestamp", "store_id", "timestamp"),
        Index("ix_events_store_visitor", "store_id", "visitor_id"),
    )


class PosTransaction(Base):
    __tablename__ = "pos_transactions"

    id = Column(Integer, primary_key=True)
    store_id = Column(String(64), nullable=False, index=True)
    transaction_id = Column(String(96), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    amount = Column(Float, nullable=False, default=0.0)
    source_file = Column(Text, nullable=True)
    raw = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_created_at)

    __table_args__ = (
        UniqueConstraint("store_id", "transaction_id", name="uq_pos_store_transaction"),
        Index("ix_pos_store_timestamp", "store_id", "timestamp"),
    )


class IngestionAudit(Base):
    __tablename__ = "ingestion_audit"

    id = Column(Integer, primary_key=True)
    trace_id = Column(String(64), nullable=True, index=True)
    accepted_count = Column(Integer, nullable=False, default=0)
    duplicate_count = Column(Integer, nullable=False, default=0)
    rejected_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_created_at)
