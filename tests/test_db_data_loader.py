"""Tests for db_data_loader — verifying DB-only paths work correctly."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from bet.db.models import Fixture, OddsRecord
from bet.db.repositories import (
    CompetitionRepo,
    FixtureRepo,
    OddsRepo,
    SportRepo,
    TeamRepo,
)

SCHEMA_PATH = Path(__file__).parent.parent / "src" / "bet" / "db" / "schema.sql"


@pytest.fixture
def db():
    """In-memory SQLite database with schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    schema = SCHEMA_PATH.read_text()
    conn.executescript(schema)
    yield conn
    conn.close()


@contextmanager
def _mock_get_db(conn):
    """Context manager that yields the provided connection (mimics get_db)."""
    yield conn


@pytest.fixture
def seeded_db(db):
    """DB with sports, teams, fixtures, and odds seeded."""
    sport_repo = SportRepo(db)
    sport_repo.seed_defaults()

    team_repo = TeamRepo(db)
    comp_repo = CompetitionRepo(db)
    fixture_repo = FixtureRepo(db)
    odds_repo = OddsRepo(db)

    football = sport_repo.get_by_name("football")
    assert football is not None

    home = team_repo.find_or_create("Arsenal", football.id)
    away = team_repo.find_or_create("Chelsea", football.id)

    comp_id = comp_repo.find_or_create("Premier League", football.id, country="England")

    f1 = Fixture(
        id=None,
        sport_id=football.id,
        competition_id=comp_id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff="2026-06-01T15:00:00",
        status="scheduled",
        source="api",
        fetched_at="2026-06-01T10:00:00",
    )
    f1_id = fixture_repo.upsert(f1)

    # Add odds records
    odds_repo.save(OddsRecord(
        id=None,
        fixture_id=f1_id,
        bookmaker="betclic",
        market="h2h",
        selection="Arsenal",
        odds=1.85,
        line=None,
        fetched_at="2026-06-01T10:00:00",
    ))
    odds_repo.save(OddsRecord(
        id=None,
        fixture_id=f1_id,
        bookmaker="betclic",
        market="h2h",
        selection="Chelsea",
        odds=4.20,
        line=None,
        fetched_at="2026-06-01T10:00:00",
    ))
    odds_repo.save(OddsRecord(
        id=None,
        fixture_id=f1_id,
        bookmaker="betclic",
        market="totals",
        selection="Over",
        odds=1.90,
        line=2.5,
        fetched_at="2026-06-01T10:00:00",
    ))
    odds_repo.save(OddsRecord(
        id=None,
        fixture_id=f1_id,
        bookmaker="betclic",
        market="totals",
        selection="Under",
        odds=1.95,
        line=2.5,
        fetched_at="2026-06-01T10:00:00",
    ))

    db.commit()
    return {
        "conn": db,
        "football": football,
        "home": home,
        "away": away,
        "f1_id": f1_id,
    }


class TestLoadFixturesFromDb:
    """Tests for load_fixtures_from_db — DB-only path."""

    def test_returns_fixtures_from_db(self, seeded_db):
        """load_fixtures_from_db returns fixtures when DB has data."""
        with patch("bet.db.connection.get_db", return_value=_mock_get_db(seeded_db["conn"])):
            from db_data_loader import load_fixtures_from_db
            result = load_fixtures_from_db("2026-06-01")
            assert len(result) >= 1
            assert any("Arsenal" in str(r.get("home_team", "")) for r in result)

    def test_returns_empty_when_db_empty(self, db):
        """load_fixtures_from_db returns [] when no fixtures in DB (no JSON fallback)."""
        SportRepo(db).seed_defaults()
        db.commit()

        with patch("bet.db.connection.get_db", return_value=_mock_get_db(db)):
            from db_data_loader import load_fixtures_from_db
            result = load_fixtures_from_db("2099-01-01")
            assert result == []


class TestLoadOddsFromDb:
    """Tests for load_odds_from_db — verify field parity with old JSON format."""

    def test_odds_have_required_fields(self, seeded_db):
        """load_odds_from_db returns events with bookmaker/market/odds structure."""
        with patch("bet.db.connection.get_db", return_value=_mock_get_db(seeded_db["conn"])):
            from db_data_loader import load_odds_from_db
            result = load_odds_from_db("2026-06-01")

            assert "events" in result
            assert "total_events" in result
            assert result["total_events"] >= 1

            event = result["events"][0]
            # Required fields matching old JSON format
            assert "home_team" in event
            assert "away_team" in event
            assert "sport" in event
            assert "bookmakers" in event

            # Bookmakers structure
            bm = event["bookmakers"][0]
            assert "key" in bm
            assert "title" in bm
            assert "markets" in bm

            # Markets structure
            mkt = bm["markets"][0]
            assert "key" in mkt
            assert "outcomes" in mkt

            # Outcomes structure
            outcome = mkt["outcomes"][0]
            assert "name" in outcome
            assert "price" in outcome

    def test_totals_have_point_field(self, seeded_db):
        """Totals markets include 'point' field in outcomes."""
        with patch("bet.db.connection.get_db", return_value=_mock_get_db(seeded_db["conn"])):
            from db_data_loader import load_odds_from_db
            result = load_odds_from_db("2026-06-01")

            event = result["events"][0]
            found_totals = False
            for bm in event["bookmakers"]:
                for mkt in bm["markets"]:
                    if mkt["key"] == "totals":
                        found_totals = True
                        for outcome in mkt["outcomes"]:
                            assert "point" in outcome
                            assert outcome["point"] == 2.5
            assert found_totals, "Expected to find 'totals' market"

    def test_returns_empty_when_no_odds(self, db):
        """load_odds_from_db returns empty structure when no odds (no JSON fallback)."""
        SportRepo(db).seed_defaults()
        db.commit()

        with patch("bet.db.connection.get_db", return_value=_mock_get_db(db)):
            from db_data_loader import load_odds_from_db
            result = load_odds_from_db("2099-01-01")
            assert result["events"] == []
            assert result["total_events"] == 0
