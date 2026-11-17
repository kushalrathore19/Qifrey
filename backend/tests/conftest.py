"""Pytest configuration and fixtures for Qifrey backend tests."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

# Set test DB path BEFORE importing app modules
os.environ["QIFREY_DB_PATH"] = ":memory:"

from qifrey.config import get_settings
from qifrey.db.models import Base
from qifrey.db.session import get_db, get_engine, reset_engine
from qifrey.main import app
from qifrey.pipeline.rate_limiter import reset_rate_limiter


@pytest.fixture(autouse=True)
def _reset_db():
    """Create a fresh in-memory DB for every test."""
    reset_engine()
    reset_rate_limiter(max_rpm=1000)
    get_settings.cache_clear()
    # Override db_path for tests
    os.environ["QIFREY_DB_PATH"] = ":memory:"

    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    test_session_local = sessionmaker(bind=engine)

    def override_get_db():
        db = test_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db_session():
    from sqlalchemy.orm import Session

    engine = get_engine()
    with Session(engine) as session:
        yield session
