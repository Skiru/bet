"""Tests for _try_api_fetch() enrichment budget — checks DB before calling API.

Verifies:
- Fixtures already in match_stats table are NOT re-fetched via get_fixture_stats()
- Fixtures NOT in DB are fetched via get_fixture_stats()
"""

import sqlite3
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from bet.db.models import Team
from bet.db.schema import init_db
from bet.stats.enrichment import _try_api_fetch


@pytest.fixture
def db():
    """In-memory SQLite database with schema initialized."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn


@pytest.fixture
def db_with_fixtures(db):
    """DB with a sport, team, and some fixtures pre-inserted."""
    # Insert sport
    db.execute(
        "INSERT INTO sports (id, name, tier, stat_keys) VALUES (?, ?, ?, ?)",
        (1, "football", 1, '["corners", "fouls", "shots"]'),
    )
    # Insert teams
    db.execute(
        "INSERT INTO teams (id, sport_id, name, aliases) VALUES (?, ?, ?, ?)",
        (1, 1, "Liverpool", '["LFC"]'),
    )
    db.execute(
        "INSERT INTO teams (id, sport_id, name, aliases) VALUES (?, ?, ?, ?)",
        (2, 1, "Arsenal", '["ARS"]'),
    )
    # Insert fixtures with known external_ids (simulating previously fetched data)
    for i in range(1, 6):
        db.execute(
            "INSERT INTO fixtures (id, external_id, sport_id, home_team_id, away_team_id, "
            "kickoff, status, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (i, str(1000 + i), 1, 1, 2, f"2025-04-{i:02d}T15:00:00", "finished", "api-football", "2025-04-01T00:00:00"),
        )

    # Pre-insert match_stats for fixtures 1001, 1002, 1003 (external_ids) → fixture DB ids 1,2,3
    for fix_db_id in [1, 2, 3]:
        for stat_key in ["corners", "fouls", "shots"]:
            db.execute(
                "INSERT INTO match_stats (fixture_id, team_id, stat_key, stat_value, source, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (fix_db_id, 1, stat_key, 8.0, "api-football", "2025-04-01T00:00:00"),
            )

    db.commit()
    return db


@dataclass
class MockMatchStats:
    """Minimal match stats mock."""
    external_id: str
    source: str
    sport: str
    home_team_name: str
    away_team_name: str
    stats: dict


class TestEnrichmentBudget:
    def test_skips_api_for_cached_fixtures(self, db_with_fixtures):
        """Fixtures already in match_stats should NOT trigger get_fixture_stats()."""
        team = Team(id=1, sport_id=1, name="Liverpool")

        # Mock API client
        mock_client = MagicMock()
        mock_client.is_available.return_value = True
        mock_client.resolve_team_id.return_value = "40"
        # Return 5 fixtures: 1001-1005 (first 3 already in DB)
        mock_client.get_team_last_fixtures.return_value = [
            {"id": 1001}, {"id": 1002}, {"id": 1003}, {"id": 1004}, {"id": 1005},
        ]
        # get_fixture_stats returns mock data for new fixtures
        mock_client.get_fixture_stats.return_value = [
            MockMatchStats(
                external_id="1004",
                source="api-football",
                sport="football",
                home_team_name="Liverpool",
                away_team_name="Arsenal",
                stats={"corners": {"home": 7.0, "away": 5.0}, "fouls": {"home": 12.0, "away": 9.0}, "shots": {"home": 15.0, "away": 8.0}},
            )
        ]

        with patch("bet.api_clients.get_client", return_value=mock_client):
            result = _try_api_fetch(team, "football", ["corners", "fouls", "shots"], db_with_fixtures)

        assert result is True

        # get_fixture_stats should only be called for fixtures NOT in DB (1004, 1005)
        calls = mock_client.get_fixture_stats.call_args_list
        called_ids = [str(c[0][0]) for c in calls]
        # 1001, 1002, 1003 should NOT appear
        assert "1001" not in called_ids
        assert "1002" not in called_ids
        assert "1003" not in called_ids
        # 1004 and 1005 SHOULD appear
        assert "1004" in called_ids
        assert "1005" in called_ids

    def test_fetches_api_for_uncached_fixtures(self, db_with_fixtures):
        """Fixtures NOT in match_stats SHOULD trigger get_fixture_stats()."""
        team = Team(id=1, sport_id=1, name="Liverpool")

        mock_client = MagicMock()
        mock_client.is_available.return_value = True
        mock_client.resolve_team_id.return_value = "40"
        # Return only fixtures NOT in DB
        mock_client.get_team_last_fixtures.return_value = [
            {"id": 2001}, {"id": 2002}, {"id": 2003},
        ]
        mock_client.get_fixture_stats.return_value = [
            MockMatchStats(
                external_id="2001",
                source="api-football",
                sport="football",
                home_team_name="Liverpool",
                away_team_name="Arsenal",
                stats={"corners": {"home": 9.0, "away": 4.0}, "fouls": {"home": 11.0, "away": 10.0}},
            )
        ]

        with patch("bet.api_clients.get_client", return_value=mock_client):
            result = _try_api_fetch(team, "football", ["corners", "fouls", "shots"], db_with_fixtures)

        assert result is True
        # All 3 uncached fixtures should trigger API calls
        assert mock_client.get_fixture_stats.call_count == 3

    def test_no_api_calls_when_all_cached(self, db_with_fixtures):
        """If ALL fixtures are already in DB, get_fixture_stats() should never be called."""
        team = Team(id=1, sport_id=1, name="Liverpool")

        mock_client = MagicMock()
        mock_client.is_available.return_value = True
        mock_client.resolve_team_id.return_value = "40"
        # Return only fixtures that ARE in DB
        mock_client.get_team_last_fixtures.return_value = [
            {"id": 1001}, {"id": 1002}, {"id": 1003},
        ]

        with patch("bet.api_clients.get_client", return_value=mock_client):
            result = _try_api_fetch(team, "football", ["corners", "fouls", "shots"], db_with_fixtures)

        assert result is True
        # No API stat calls needed — all data was in DB
        mock_client.get_fixture_stats.assert_not_called()
