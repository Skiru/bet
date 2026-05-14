import sqlite3
import pytest
from bet.db.schema import init_db
from bet.db.connection import get_db
from bet.discovery.repository import FixtureSourceRepo
from bet.db.repositories import FixtureRepo, TeamRepo, SportRepo
from bet.db.models import Fixture, Team, Sport
from datetime import datetime

@pytest.fixture
def repo(db: sqlite3.Connection):
    return FixtureSourceRepo(db)

def test_fixture_source_upsert(db, repo):
    # setup
    db.execute("INSERT INTO sports (name, tier) VALUES ('football', 1)")
    db.execute("INSERT INTO teams (sport_id, name) VALUES (1, 'Team A')")
    db.execute("INSERT INTO teams (sport_id, name) VALUES (1, 'Team B')")
    db.execute(
        "INSERT INTO fixtures (sport_id, home_team_id, away_team_id, kickoff, fetched_at) VALUES (1, 1, 2, '2026-05-14T10:00:00Z', '2026-05-14')"
    )
    
    # create
    id1 = repo.upsert(1, "sofascore", "ext_123", confidence=0.9, raw_data={"a": 1})
    assert id1 > 0
    row = db.execute("SELECT * FROM fixture_sources WHERE id = ?", (id1,)).fetchone()
    assert row["source"] == "sofascore"
    assert row["external_id"] == "ext_123"
    
    # update
    id2 = repo.upsert(1, "sofascore", "ext_123", confidence=0.95, raw_data={"a": 2})
    assert id2 == id1
    row = db.execute("SELECT * FROM fixture_sources WHERE id = ?", (id1,)).fetchone()
    assert row["confidence"] == 0.95
    assert "2" in row["raw_data"]

def test_fixture_source_get_by_fixture(db, repo):
    db.execute("INSERT INTO sports (name, tier) VALUES ('football', 1)")
    db.execute("INSERT INTO teams (sport_id, name) VALUES (1, 'TA')")
    db.execute("INSERT INTO teams (sport_id, name) VALUES (1, 'TB')")
    db.execute("INSERT INTO fixtures (sport_id, home_team_id, away_team_id, kickoff, fetched_at) VALUES (1, 1, 2, 'kick', 'now')")
    
    repo.upsert(1, "odds-api", "oa_1")
    repo.upsert(1, "api-football", "af_1")
    
    records = repo.get_by_fixture(1)
    assert len(records) == 2
    sources = [r["source"] for r in records]
    assert "odds-api" in sources
    assert "api-football" in sources

def test_fixture_source_get_by_source_id(db, repo):
    db.execute("INSERT INTO sports (name, tier) VALUES ('football', 1)")
    db.execute("INSERT INTO teams (sport_id, name) VALUES (1, 'TA')")
    db.execute("INSERT INTO teams (sport_id, name) VALUES (1, 'TB')")
    db.execute("INSERT INTO fixtures (sport_id, home_team_id, away_team_id, kickoff, fetched_at) VALUES (1, 1, 2, 'kick', 'now')")
    
    repo.upsert(1, "odds-api", "unique_id_x")
    record = repo.get_by_source_id("odds-api", "unique_id_x")
    assert record is not None
    assert record["fixture_id"] == 1
    assert record["external_id"] == "unique_id_x"
    
    assert repo.get_by_source_id("odds-api", "not_exist") is None

def test_fixture_source_bulk_upsert(db, repo):
    db.execute("INSERT INTO sports (name, tier) VALUES ('football', 1)")
    db.execute("INSERT INTO teams (sport_id, name) VALUES (1, 'TA')")
    db.execute("INSERT INTO teams (sport_id, name) VALUES (1, 'TB')")
    db.execute("INSERT INTO fixtures (sport_id, home_team_id, away_team_id, kickoff, fetched_at) VALUES (1, 1, 2, 'kick', 'now')")
    
    records = [
        (1, "source_1", "ext_1", 1.0, {"key": "val1"}),
        (1, "source_2", "ext_2", 0.8, None)
    ]
    
    count = repo.bulk_upsert(records)
    assert count == 2
    
    db_recs = db.execute("SELECT * FROM fixture_sources").fetchall()
    assert len(db_recs) == 2

def test_fixture_source_fk_constraint(db, repo):
    with pytest.raises(sqlite3.IntegrityError):
        repo.upsert(999, "sofascore", "ext_123")
