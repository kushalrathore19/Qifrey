"""Database engine and session management."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from qifrey.config import get_settings
from qifrey.db.models import Base

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        if settings.db_path == ":memory:":
            _engine = create_engine(
                "sqlite://",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
                echo=False,
            )
        else:
            _engine = create_engine(
                f"sqlite:///{settings.db_path}",
                connect_args={"check_same_thread": False},
                echo=False,
            )
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal


def init_db() -> None:
    """Create all tables."""
    Base.metadata.create_all(bind=get_engine())


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session."""
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


def reset_engine() -> None:
    """For testing: reset global engine/session so a new DB path takes effect."""
    global _engine, _SessionLocal
    if _engine:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
