"""Tests for PipelineCandidateRepo — pipeline_candidates table CRUD."""

import sqlite3
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bet.db.models import Fixture
from bet.db.repositories import (
    CompetitionRepo,
    FixtureRepo,
    PipelineCandidateRepo,
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
    conn.executescript(SCHEMA_PATH.read_text())
    yield conn
    conn.close()


@pytest.fixture
def seeded_db(db):
    """DB with fixtures for testing pipeline candidates."""
    sport_repo = SportRepo(db)
    sport_repo.seed_defaults()

    team_repo = TeamRepo(db)
    comp_repo = CompetitionRepo(db)
    fixture_repo = FixtureRepo(db)

    football = sport_repo.get_by_name("football")
    hockey = sport_repo.get_by_name("hockey")

    home1 = team_repo.find_or_create("Arsenal", football.id)
    away1 = team_repo.find_or_create("Chelsea", football.id)
    home2 = team_repo.find_or_create("Rangers", hockey.id)
    away2 = team_repo.find_or_create("Bruins", hockey.id)

    comp1 = comp_repo.find_or_create("Premier League", football.id)
    comp2 = comp_repo.find_or_create("NHL", hockey.id)

    f1_id = fixture_repo.upsert(Fixture(
        id=None, sport_id=football.id, competition_id=comp1,
        home_team_id=home1.id, away_team_id=away1.id,
        kickoff="2026-06-01T15:00:00", status="scheduled",
        source="test", fetched_at="2026-06-01T10:00:00",
    ))
    f2_id = fixture_repo.upsert(Fixture(
        id=None, sport_id=hockey.id, competition_id=comp2,
        home_team_id=home2.id, away_team_id=away2.id,
        kickoff="2026-06-01T19:00:00", status="scheduled",
        source="test", fetched_at="2026-06-01T10:00:00",
    ))

    db.commit()
    return {"conn": db, "f1_id": f1_id, "f2_id": f2_id}


class TestPipelineCandidateRepo:
    def test_save_and_get(self, seeded_db):
        repo = PipelineCandidateRepo(seeded_db["conn"])
        candidates = [
            {
                "fixture_id": seeded_db["f1_id"],
                "rank": 1,
                "score": 8.5,
                "sport": "football",
                "competition": "Premier League",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "kickoff": "2026-06-01T15:00:00",
                "data_tier": "FULL",
                "comp_score": 7,
                "n_odds_markets": 3,
                "n_safety_markets": 2,
                "odds_markets": ["h2h", "totals", "btts"],
                "safety_markets": ["corners", "fouls"],
            },
            {
                "fixture_id": seeded_db["f2_id"],
                "rank": 2,
                "score": 6.0,
                "sport": "hockey",
                "competition": "NHL",
                "home_team": "Rangers",
                "away_team": "Bruins",
                "kickoff": "2026-06-01T19:00:00",
                "data_tier": "PARTIAL",
                "comp_score": 5,
            },
        ]

        saved = repo.save_candidates("2026-06-01", candidates)
        assert saved == 2

        result = repo.get_by_date("2026-06-01")
        assert len(result) == 2
        assert result[0]["rank"] == 1
        assert result[0]["sport"] == "football"
        assert result[0]["score"] == 8.5
        assert result[0]["odds_markets"] == ["h2h", "totals", "btts"]
        assert result[1]["rank"] == 2
        assert result[1]["sport"] == "hockey"

    def test_get_by_sport(self, seeded_db):
        repo = PipelineCandidateRepo(seeded_db["conn"])
        candidates = [
            {"fixture_id": seeded_db["f1_id"], "rank": 1, "sport": "football",
             "home_team": "Arsenal", "away_team": "Chelsea"},
            {"fixture_id": seeded_db["f2_id"], "rank": 2, "sport": "hockey",
             "home_team": "Rangers", "away_team": "Bruins"},
        ]
        repo.save_candidates("2026-06-01", candidates)

        football_only = repo.get_by_date_and_sport("2026-06-01", "football")
        assert len(football_only) == 1
        assert football_only[0]["sport"] == "football"

    def test_enrich_tipster(self, seeded_db):
        repo = PipelineCandidateRepo(seeded_db["conn"])
        candidates = [
            {"fixture_id": seeded_db["f1_id"], "rank": 1, "sport": "football",
             "home_team": "Arsenal", "away_team": "Chelsea"},
        ]
        repo.save_candidates("2026-06-01", candidates)

        repo.enrich_tipster(seeded_db["f1_id"], "2026-06-01", 3,
                            {"sources": ["tipster-a", "tipster-b", "tipster-c"]})

        result = repo.get_by_date("2026-06-01")
        assert result[0]["tipster_count"] == 3
        assert result[0]["tipster_support"]["sources"] == ["tipster-a", "tipster-b", "tipster-c"]

    def test_get_count(self, seeded_db):
        repo = PipelineCandidateRepo(seeded_db["conn"])
        assert repo.get_count("2026-06-01") == 0

        candidates = [
            {"fixture_id": seeded_db["f1_id"], "rank": 1, "sport": "football",
             "home_team": "Arsenal", "away_team": "Chelsea"},
        ]
        repo.save_candidates("2026-06-01", candidates)
        assert repo.get_count("2026-06-01") == 1

    def test_delete_by_date(self, seeded_db):
        repo = PipelineCandidateRepo(seeded_db["conn"])
        candidates = [
            {"fixture_id": seeded_db["f1_id"], "rank": 1, "sport": "football",
             "home_team": "Arsenal", "away_team": "Chelsea"},
        ]
        repo.save_candidates("2026-06-01", candidates)
        assert repo.get_count("2026-06-01") == 1

        deleted = repo.delete_by_date("2026-06-01")
        assert deleted == 1
        assert repo.get_count("2026-06-01") == 0

    def test_save_replaces_existing(self, seeded_db):
        """save_candidates clears existing data for the date before inserting."""
        repo = PipelineCandidateRepo(seeded_db["conn"])
        candidates_v1 = [
            {"fixture_id": seeded_db["f1_id"], "rank": 1, "sport": "football",
             "home_team": "Arsenal", "away_team": "Chelsea", "score": 5.0},
        ]
        repo.save_candidates("2026-06-01", candidates_v1)
        assert repo.get_count("2026-06-01") == 1

        candidates_v2 = [
            {"fixture_id": seeded_db["f1_id"], "rank": 1, "sport": "football",
             "home_team": "Arsenal", "away_team": "Chelsea", "score": 9.0},
            {"fixture_id": seeded_db["f2_id"], "rank": 2, "sport": "hockey",
             "home_team": "Rangers", "away_team": "Bruins", "score": 7.0},
        ]
        repo.save_candidates("2026-06-01", candidates_v2)
        assert repo.get_count("2026-06-01") == 2

        result = repo.get_by_date("2026-06-01")
        assert result[0]["score"] == 9.0
