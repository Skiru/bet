"""Basic tests for the DB layer using an in-memory SQLite DB."""

from __future__ import annotations

from datetime import datetime
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bet.db.models import Base
from bet.db.repository import upsert_fixture, insert_artifact, list_artifacts_for_day


@pytest.fixture(scope="function")
def init_db():
    # Use an in-memory SQLite DB for isolation
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_upsert_fixture_and_artifact(init_db):
    db = init_db
    f = upsert_fixture(db, external_id="ext-1", event_time=datetime.utcnow(), payload={"home": "A", "away": "B"})
    assert f.id is not None
    art = insert_artifact(db, artifact_type="normalized_fixtures", payload={"day": "2026-06-01"})
    assert art.uuid is not None
    # list artifacts for today
    start = datetime(2026, 6, 1)
    end = datetime(2026, 6, 2)
    arts = list_artifacts_for_day(db, start, end)
    assert isinstance(arts, list)
