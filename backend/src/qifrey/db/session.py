"""Database engine and session management."""

from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from qifrey.config import get_settings
from qifrey.db.models import Base

logger = logging.getLogger(__name__)

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


def _migrate_columns(engine) -> None:
    """Lightweight SQLite migration to add missing columns to existing tables."""
    from sqlalchemy import text  # noqa: PLC0415

    migrations = [
        ("stories", "settings_json", "TEXT DEFAULT NULL"),
        ("chapters", "exclude_from_analysis", "BOOLEAN DEFAULT 0"),
        ("characters", "source", "VARCHAR(20) DEFAULT 'ai'"),
        ("characters", "locked", "BOOLEAN DEFAULT 0"),
        ("characters", "status", "VARCHAR(20) DEFAULT 'active'"),
        ("characters", "notes", "TEXT DEFAULT NULL"),
        ("characters", "color", "VARCHAR(50) DEFAULT NULL"),
        ("characters", "tags_json", "TEXT DEFAULT NULL"),
        ("aliases", "source", "VARCHAR(20) DEFAULT 'ai'"),
        ("facts", "source", "VARCHAR(20) DEFAULT 'ai'"),
        ("facts", "locked", "BOOLEAN DEFAULT 0"),
    ]

    with engine.connect() as conn:
        for table, column, col_def in migrations:
            try:
                # Check if column exists
                cols = [
                    row[1] for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                ]
                if cols and column not in cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"))
                    conn.commit()
            except Exception:
                pass

        # Make facts.chapter_id nullable if it was created with NOT NULL constraint
        try:
            table_info = conn.execute(text("PRAGMA table_info(facts)")).fetchall()
            chapter_col = next((row for row in table_info if row[1] == "chapter_id"), None)
            if chapter_col and chapter_col[3] == 1:
                conn.execute(text("PRAGMA foreign_keys=OFF;"))
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS facts_new (
                            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                            story_id INTEGER NOT NULL,
                            character_id INTEGER NOT NULL,
                            attribute VARCHAR(200) NOT NULL,
                            value TEXT NOT NULL,
                            chapter_id INTEGER,
                            quote TEXT,
                            confidence FLOAT NOT NULL,
                            source VARCHAR(20) DEFAULT 'ai',
                            locked BOOLEAN DEFAULT 0,
                            FOREIGN KEY(story_id) REFERENCES stories (id) ON DELETE CASCADE,
                            FOREIGN KEY(character_id) REFERENCES characters (id) ON DELETE CASCADE,
                            FOREIGN KEY(chapter_id) REFERENCES chapters (id) ON DELETE CASCADE
                        );
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO facts_new (
                            id, story_id, character_id, attribute, value,
                            chapter_id, quote, confidence, source, locked
                        )
                        SELECT id, story_id, character_id, attribute, value,
                               chapter_id, quote, confidence,
                               COALESCE(source, 'ai'), COALESCE(locked, 0)
                        FROM facts;
                        """
                    )
                )
                conn.execute(text("DROP TABLE facts;"))
                conn.execute(text("ALTER TABLE facts_new RENAME TO facts;"))
                conn.execute(text("PRAGMA foreign_keys=ON;"))
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("facts table nullable migration skipped: %s", exc)


def init_db() -> None:
    """Create all tables and perform lightweight schema migrations."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _migrate_columns(engine)


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
