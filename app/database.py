from __future__ import annotations

from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import get_settings
from app.errors import ServiceUnavailableError


Base = declarative_base()

_engine: Optional[Engine] = None
SessionLocal: Optional[sessionmaker[Session]] = None


def _sqlite_connect_args(url: str) -> dict:
    return {"check_same_thread": False} if url.startswith("sqlite") else {}


def _ensure_sqlite_parent(url: str) -> None:
    if not url.startswith("sqlite:///"):
        return
    raw_path = url.replace("sqlite:///", "", 1)
    if raw_path and raw_path != ":memory:":
        Path(raw_path).parent.mkdir(parents=True, exist_ok=True)


def configure_database(url: Optional[str] = None) -> Engine:
    global _engine, SessionLocal
    database_url = url or get_settings().database_url
    _ensure_sqlite_parent(database_url)
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(
        database_url,
        connect_args=_sqlite_connect_args(database_url),
        pool_pre_ping=True,
        future=True,
    )
    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        return configure_database()
    return _engine


def init_db() -> None:
    from app import models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    if str(engine.url).startswith("sqlite"):
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.commit()


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        configure_database()
    assert SessionLocal is not None
    try:
        db = SessionLocal()
    except SQLAlchemyError as exc:
        raise ServiceUnavailableError("Database session could not be opened") from exc
    try:
        yield db
    except SQLAlchemyError as exc:
        db.rollback()
        raise ServiceUnavailableError("Database operation failed") from exc
    finally:
        db.close()


def ping_database() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False
