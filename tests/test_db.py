"""Basic tests for the DB layer using an in-memory SQLite DB."""

from __future__ import annotations

from datetime import datetime
import pytest

from bet.db.connection import get_engine, get_db
from bet.db.models import Base
from bet.db.repository import upsert_fixture, insert_artifact, list_artifacts_for_day


@pytest.fixture(scope="function")
def init_db(tmp_path):
    # Use a temporary SQLite file for isolation
    db_file = tmp_path / "test.db"
    engine = get_engine()
    # create tables in the engine's database
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_upsert_fixture_and_artifact(init_db):
    with get_db() as db:
        f = upsert_fixture(db, external_id="ext-1", event_time=datetime.utcnow(), payload={"home": "A", "away": "B"})
        assert f.id is not None
        art = insert_artifact(db, artifact_type="normalized_fixtures", payload={"day": "2026-06-01"})
        assert art.uuid is not None
        # list artifacts for today
        start = datetime(2026, 6, 1)
        end = datetime(2026, 6, 2)
        arts = list_artifacts_for_day(db, start, end)
        assert isinstance(arts, list)
