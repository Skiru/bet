"""Tests for MarketMatrixRepo."""

import json
import sqlite3

import pytest

from bet.db.repositories import MarketMatrixRepo


@pytest.fixture
def conn():
    """In-memory DB with market_matrix tables."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("""
        CREATE TABLE IF NOT EXISTS fixtures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sport TEXT, home_team TEXT, away_team TEXT, kickoff TEXT, betting_date TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS market_matrix_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
            betting_date TEXT NOT NULL,
            sport TEXT NOT NULL,
            competition TEXT,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            kickoff TEXT,
            data_tier TEXT NOT NULL DEFAULT 'FIXTURE_ONLY',
            fixture_source TEXT,
            odds_markets_json TEXT NOT NULL DEFAULT '[]',
            safety_markets_json TEXT NOT NULL DEFAULT '[]',
            suggested_json TEXT,
            total_markets_available INTEGER NOT NULL DEFAULT 0,
            scores24_h2h_json TEXT,
            scores24_form_json TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(fixture_id, betting_date)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS market_matrix_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            betting_date TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            total_fixtures INTEGER NOT NULL DEFAULT 0,
            total_events_in_matrix INTEGER NOT NULL DEFAULT 0,
            events_with_odds INTEGER NOT NULL DEFAULT 0,
            events_with_safety_data INTEGER NOT NULL DEFAULT 0,
            sport_breakdown_json TEXT NOT NULL DEFAULT '{}',
            market_type_counts_json TEXT NOT NULL DEFAULT '{}',
            data_tier_breakdown_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(betting_date)
        )
    """)
    # Insert fixture for FK
    c.execute("INSERT INTO fixtures (id, sport, home_team, away_team, kickoff, betting_date) VALUES (1, 'football', 'TeamA', 'TeamB', '20:00', '2099-06-01')")
    c.execute("INSERT INTO fixtures (id, sport, home_team, away_team, kickoff, betting_date) VALUES (2, 'tennis', 'PlayerX', 'PlayerY', '14:00', '2099-06-01')")
    c.commit()
    return c


@pytest.fixture
def repo(conn):
    return MarketMatrixRepo(conn)


def _make_event(fixture_id=1, sport="football", home="TeamA", away="TeamB", tier="FULL"):
    return {
        "fixture_id": fixture_id,
        "sport": sport,
        "competition": "Premier League",
        "home_team": home,
        "away_team": away,
        "kickoff": "20:00",
        "data_tier": tier,
        "fixture_source": "odds_api",
        "odds_markets": [{"market": "1X2", "odds": {"1": 1.5, "X": 3.8, "2": 6.0}}],
        "safety_markets": [{"market": "corners_ou", "line": 9.5}],
        "suggested": [{"market": "over_2.5", "safety_score": 7.2}],
        "total_markets_available": 15,
        "scores24_h2h": {"matches": 5, "home_wins": 3},
        "scores24_form": {"home_l5": "WWDLW"},
    }


class TestMarketMatrixRepoSaveAndGet:
    def test_save_events_and_get(self, repo):
        events = [_make_event(1), _make_event(2, sport="tennis", home="PlayerX", away="PlayerY")]
        saved = repo.save_events("2099-06-01", events)
        assert saved == 2

        result = repo.get_events_by_date("2099-06-01")
        assert len(result) == 2
        assert result[0]["sport"] == "football"
        assert result[0]["odds_markets"][0]["market"] == "1X2"
        assert result[1]["sport"] == "tennis"

    def test_save_replaces_existing(self, repo):
        repo.save_events("2099-06-01", [_make_event(1)])
        assert repo.get_count("2099-06-01") == 1

        repo.save_events("2099-06-01", [_make_event(1, tier="PARTIAL"), _make_event(2, sport="tennis", home="PlayerX", away="PlayerY")])
        assert repo.get_count("2099-06-01") == 2
        result = repo.get_events_by_date("2099-06-01")
        assert result[0]["data_tier"] == "PARTIAL"

    def test_get_events_by_tier(self, repo):
        events = [
            _make_event(1, tier="FULL"),
            _make_event(2, sport="tennis", home="PlayerX", away="PlayerY", tier="PARTIAL"),
        ]
        repo.save_events("2099-06-01", events)

        full = repo.get_events_by_tier("2099-06-01", "FULL")
        assert len(full) == 1
        assert full[0]["data_tier"] == "FULL"

    def test_get_count(self, repo):
        assert repo.get_count("2099-06-01") == 0
        repo.save_events("2099-06-01", [_make_event(1)])
        assert repo.get_count("2099-06-01") == 1

    def test_delete_by_date(self, repo):
        repo.save_events("2099-06-01", [_make_event(1)])
        deleted = repo.delete_by_date("2099-06-01")
        assert deleted == 1
        assert repo.get_count("2099-06-01") == 0

    def test_event_to_dict_fields(self, repo):
        repo.save_events("2099-06-01", [_make_event(1)])
        result = repo.get_events_by_date("2099-06-01")[0]
        assert result["fixture_id"] == 1
        assert result["competition"] == "Premier League"
        assert result["scores24_h2h"] == {"matches": 5, "home_wins": 3}
        assert result["scores24_form"] == {"home_l5": "WWDLW"}
        assert result["suggested"] == [{"market": "over_2.5", "safety_score": 7.2}]


class TestMarketMatrixRunMetadata:
    def test_save_and_get_run(self, repo):
        metadata = {
            "total_fixtures": 100,
            "total_events_in_matrix": 80,
            "events_with_odds": 65,
            "events_with_safety_data": 45,
            "sport_breakdown": {"football": 40, "tennis": 20, "basketball": 20},
            "market_type_counts": {"1X2": 60, "totals": 50},
            "data_tier_breakdown": {"FULL": 30, "PARTIAL": 30, "FIXTURE_ONLY": 20},
        }
        run_id = repo.save_run("2099-06-01", metadata)
        assert run_id > 0

        result = repo.get_run_metadata("2099-06-01")
        assert result is not None
        assert result["total_fixtures"] == 100
        assert result["events_with_odds"] == 65
        assert result["sport_breakdown"]["football"] == 40

    def test_get_run_metadata_empty(self, repo):
        assert repo.get_run_metadata("2099-01-01") is None

    def test_save_run_replaces(self, repo):
        repo.save_run("2099-06-01", {"total_fixtures": 50})
        repo.save_run("2099-06-01", {"total_fixtures": 100})
        result = repo.get_run_metadata("2099-06-01")
        assert result["total_fixtures"] == 100
