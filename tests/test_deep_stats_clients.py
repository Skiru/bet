"""Tests for new deep-stats API clients: Sofascore Darts, Snooker Org, OpenDota, ITTF."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from scripts.api_clients.rate_limiter import RateLimiter
from scripts.api_clients.sofascore_darts import SofascoreDartsClient, STAT_KEY_MAP
from scripts.api_clients.snooker_org import SnookerOrgClient
from scripts.api_clients.opendota import OpenDotaClient
from scripts.api_clients.ittf_client import ITTFClient


@pytest.fixture
def rate_limiter(tmp_path):
    """Rate limiter with temp usage dir."""
    return RateLimiter(usage_dir=tmp_path / ".api_usage")


# ============================================================
# Sofascore Darts Tests
# ============================================================

class TestSofascoreDarts:
    """Tests for Sofascore Darts client."""

    def test_instantiation(self, rate_limiter):
        client = SofascoreDartsClient(rate_limiter=rate_limiter)
        assert client.is_available()
        assert client.api_key is None
        assert client.api_name == "sofascore-darts"

    def test_headers_no_auth(self, rate_limiter):
        client = SofascoreDartsClient(rate_limiter=rate_limiter)
        headers = client._build_headers()
        assert "User-Agent" in headers
        assert "x-apisports-key" not in headers

    def test_parse_fixtures(self, rate_limiter):
        """Test parsing of Sofascore scheduled events response."""
        client = SofascoreDartsClient(rate_limiter=rate_limiter)

        mock_response = {
            "events": [
                {
                    "id": 16103664,
                    "tournament": {
                        "name": "PDC WC Qual",
                        "uniqueTournament": {"name": "PDC World Championship"}
                    },
                    "homeTeam": {"id": 100, "name": "Michael van Gerwen"},
                    "awayTeam": {"id": 200, "name": "Luke Humphries"},
                    "startTimestamp": 1778100000,
                    "status": {"type": "finished"},
                }
            ]
        }

        with patch.object(client, "_request", return_value=mock_response):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    fixtures = client.get_fixtures("2026-05-07")

        assert len(fixtures) == 1
        f = fixtures[0]
        assert f.sport == "darts"
        assert f.home_team == "Michael van Gerwen"
        assert f.away_team == "Luke Humphries"
        assert f.competition == "PDC World Championship"
        assert f.source == "sofascore-darts"

    def test_parse_match_stats(self, rate_limiter):
        """Test parsing of per-event statistics response."""
        client = SofascoreDartsClient(rate_limiter=rate_limiter)

        mock_stats = {
            "statistics": [{
                "period": "ALL",
                "groups": [{
                    "groupName": "Attacking",
                    "statisticsItems": [
                        {"key": "Average3Darts", "homeValue": 95.5, "awayValue": 88.2},
                        {"key": "Thrown180", "homeValue": 5, "awayValue": 3},
                        {"key": "ThrownOver140", "homeValue": 8, "awayValue": 6},
                        {"key": "ThrownOver100", "homeValue": 15, "awayValue": 12},
                        {"key": "HighestCheckout", "homeValue": 164, "awayValue": 120},
                        {"key": "CheckoutsOver100", "homeValue": 2, "awayValue": 1},
                        {"key": "CheckoutsAccuracy", "homeValue": 12, "awayValue": 8,
                         "homeTotal": 30, "awayTotal": 25},
                    ]
                }]
            }]
        }

        with patch.object(client, "_request", return_value=mock_stats):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    stats = client.get_fixture_stats("16103664")

        assert stats["avg_score"] == {"home": 95.5, "away": 88.2}
        assert stats["one_eighties"] == {"home": 5, "away": 3}
        assert stats["thrown_over_140"] == {"home": 8, "away": 6}
        assert stats["highest_checkout"] == {"home": 164, "away": 120}
        assert stats["checkout_pct"]["home"] == 40.0  # 12/30 * 100
        assert stats["checkout_pct"]["away"] == 32.0  # 8/25 * 100

    def test_stat_key_map_complete(self):
        """All expected Sofascore stat keys are mapped."""
        expected = {"Average3Darts", "Thrown180", "ThrownOver140",
                    "ThrownOver100", "HighestCheckout", "CheckoutsOver100",
                    "CheckoutsAccuracy"}
        assert set(STAT_KEY_MAP.keys()) == expected

    def test_string_values_coercion(self, rate_limiter):
        """Test that string values from API are coerced to float."""
        client = SofascoreDartsClient(rate_limiter=rate_limiter)
        mock_stats = {
            "statistics": [{
                "period": "ALL",
                "groups": [{
                    "groupName": "Attacking",
                    "statisticsItems": [
                        {"key": "Average3Darts", "homeValue": "92.5", "awayValue": "87.3"},
                        {"key": "Thrown180", "homeValue": "3", "awayValue": "1"},
                    ]
                }]
            }]
        }
        with patch.object(client, "_request", return_value=mock_stats):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    stats = client.get_fixture_stats("123")

        assert stats["avg_score"] == {"home": 92.5, "away": 87.3}
        assert stats["one_eighties"] == {"home": 3.0, "away": 1.0}


# ============================================================
# Snooker Org Tests
# ============================================================

class TestSnookerOrg:
    """Tests for Snooker API client."""

    def test_instantiation(self, rate_limiter):
        client = SnookerOrgClient(rate_limiter=rate_limiter)
        # is_available() requires registered app name; without env/config it's False
        assert client.api_name == "snooker-org"

    def test_is_available_with_env(self, rate_limiter, monkeypatch):
        monkeypatch.setenv("SNOOKER_ORG_APP_NAME", "test-app")
        client = SnookerOrgClient(rate_limiter=rate_limiter)
        assert client.is_available()

    def test_headers_x_requested_by(self, rate_limiter):
        client = SnookerOrgClient(rate_limiter=rate_limiter)
        headers = client._build_headers()
        assert headers["X-Requested-By"] == "bet-pipeline"

    def test_parse_match(self, rate_limiter):
        """Test _parse_match with typical API response."""
        client = SnookerOrgClient(rate_limiter=rate_limiter)

        raw_match = {
            "ID": 12345,
            "EventName": "World Championship 2026",
            "Round": "Quarter-Final",
            "Player1ID": 1,
            "Player1Name": "Ronnie O'Sullivan",
            "Player2ID": 2,
            "Player2Name": "Judd Trump",
            "Score1": 13,
            "Score2": 10,
            "WinnerID": 1,
            "ScheduledDate": "2026-05-07",
            "Distance": 25,
        }

        parsed = client._parse_match(raw_match)
        assert parsed["match_id"] == "12345"
        assert parsed["player1_name"] == "Ronnie O'Sullivan"
        assert parsed["player2_name"] == "Judd Trump"
        assert parsed["score1"] == 13
        assert parsed["score2"] == 10
        assert parsed["total_frames"] == 23
        assert parsed["best_of"] == 25
        assert parsed["winner_id"] == "1"
        assert parsed["stats"]["frames_won"] == {"home": 13, "away": 10}

    def test_get_fixtures(self, rate_limiter):
        """Test upcoming fixtures fetch."""
        client = SnookerOrgClient(rate_limiter=rate_limiter)

        mock_data = [
            {
                "ID": 100,
                "EventName": "Shanghai Masters",
                "Player1ID": 1,
                "Player1Name": "Mark Selby",
                "Player2ID": 2,
                "Player2Name": "Neil Robertson",
                "ScheduledDate": "2026-05-08T14:00:00",
            }
        ]

        with patch.object(client, "_request", return_value=mock_data):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    fixtures = client.get_fixtures()

        assert len(fixtures) == 1
        assert fixtures[0].home_team == "Mark Selby"
        assert fixtures[0].sport == "snooker"

    def test_get_h2h(self, rate_limiter):
        """Test H2H fetch."""
        client = SnookerOrgClient(rate_limiter=rate_limiter)

        mock_data = [
            {
                "ID": 200,
                "EventName": "UK Championship",
                "Player1ID": 1,
                "Player1Name": "Trump",
                "Player2ID": 2,
                "Player2Name": "O'Sullivan",
                "Score1": 6,
                "Score2": 4,
                "WinnerID": 1,
                "ScheduledDate": "2025-12-10",
                "Distance": 11,
            }
        ]

        with patch.object(client, "_request", return_value=mock_data):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    h2h = client.get_h2h("1", "2")

        assert len(h2h) == 1
        assert h2h[0]["score1"] == 6


# ============================================================
# OpenDota Tests
# ============================================================

class TestOpenDota:
    """Tests for OpenDota (Dota 2) client."""

    def test_instantiation(self, rate_limiter):
        client = OpenDotaClient(rate_limiter=rate_limiter)
        assert client.is_available()
        assert client.api_name == "opendota"

    def test_parse_match_stats(self, rate_limiter):
        """Test aggregation of player stats into team stats."""
        client = OpenDotaClient(rate_limiter=rate_limiter)

        mock_match = {
            "match_id": 7777777,
            "duration": 2400,
            "radiant_win": True,
            "tower_status_radiant": 2047,
            "tower_status_dire": 0,
            "players": [
                # 5 Radiant players (slot < 128)
                {"player_slot": 0, "kills": 10, "deaths": 2, "assists": 15,
                 "gold_per_min": 600, "xp_per_min": 700, "hero_damage": 30000,
                 "tower_damage": 5000, "last_hits": 300, "denies": 20},
                {"player_slot": 1, "kills": 5, "deaths": 3, "assists": 20,
                 "gold_per_min": 400, "xp_per_min": 500, "hero_damage": 20000,
                 "tower_damage": 2000, "last_hits": 100, "denies": 5},
                {"player_slot": 2, "kills": 8, "deaths": 1, "assists": 12,
                 "gold_per_min": 550, "xp_per_min": 650, "hero_damage": 35000,
                 "tower_damage": 8000, "last_hits": 350, "denies": 15},
                {"player_slot": 3, "kills": 2, "deaths": 4, "assists": 25,
                 "gold_per_min": 300, "xp_per_min": 400, "hero_damage": 10000,
                 "tower_damage": 1000, "last_hits": 50, "denies": 3},
                {"player_slot": 4, "kills": 1, "deaths": 5, "assists": 28,
                 "gold_per_min": 250, "xp_per_min": 350, "hero_damage": 8000,
                 "tower_damage": 500, "last_hits": 30, "denies": 2},
                # 5 Dire players (slot >= 128)
                {"player_slot": 128, "kills": 6, "deaths": 8, "assists": 10,
                 "gold_per_min": 450, "xp_per_min": 500, "hero_damage": 25000,
                 "tower_damage": 3000, "last_hits": 200, "denies": 10},
                {"player_slot": 129, "kills": 4, "deaths": 7, "assists": 8,
                 "gold_per_min": 350, "xp_per_min": 400, "hero_damage": 18000,
                 "tower_damage": 1500, "last_hits": 150, "denies": 8},
                {"player_slot": 130, "kills": 3, "deaths": 6, "assists": 12,
                 "gold_per_min": 300, "xp_per_min": 380, "hero_damage": 15000,
                 "tower_damage": 1000, "last_hits": 120, "denies": 5},
                {"player_slot": 131, "kills": 1, "deaths": 5, "assists": 15,
                 "gold_per_min": 220, "xp_per_min": 300, "hero_damage": 8000,
                 "tower_damage": 500, "last_hits": 40, "denies": 2},
                {"player_slot": 132, "kills": 0, "deaths": 6, "assists": 18,
                 "gold_per_min": 200, "xp_per_min": 280, "hero_damage": 6000,
                 "tower_damage": 200, "last_hits": 20, "denies": 1},
            ]
        }

        with patch.object(client, "_request", return_value=mock_match):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    stats = client.get_fixture_stats("7777777")

        # Radiant: 10+5+8+2+1 = 26 kills
        assert stats["kills"]["home"] == 26
        # Dire: 6+4+3+1+0 = 14 kills
        assert stats["kills"]["away"] == 14
        # Radiant deaths: 2+3+1+4+5 = 15
        assert stats["deaths"]["home"] == 15
        # GPM average: (600+400+550+300+250)/5 = 420
        assert stats["gpm"]["home"] == 420
        # Duration: 2400s = 40 min
        assert stats["duration_minutes"]["home"] == 40.0
        # Radiant won
        assert stats["radiant_win"]["home"] == 1

    def test_get_fixtures(self, rate_limiter):
        """Test pro matches listing."""
        client = OpenDotaClient(rate_limiter=rate_limiter)

        mock_data = [
            {
                "match_id": 8000000,
                "start_time": 1778100000,
                "radiant_name": "Team Spirit",
                "dire_name": "OG",
                "radiant_team_id": 100,
                "dire_team_id": 200,
                "league_name": "The International 2026",
            }
        ]

        with patch.object(client, "_request", return_value=mock_data):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    fixtures = client.get_fixtures()

        assert len(fixtures) == 1
        assert fixtures[0].home_team == "Team Spirit"
        assert fixtures[0].away_team == "OG"
        assert fixtures[0].sport == "esports"

    def test_tower_kills_all_destroyed(self, rate_limiter):
        """Test tower_kills when all towers destroyed (status=0)."""
        client = OpenDotaClient(rate_limiter=rate_limiter)
        mock_match = {
            "match_id": 9999,
            "duration": 3000,
            "radiant_win": True,
            "tower_status_radiant": 2047,  # all 11 bits set = all standing
            "tower_status_dire": 0,        # all destroyed
            "players": [
                {"player_slot": i, "kills": 1, "deaths": 1, "assists": 1,
                 "gold_per_min": 400, "xp_per_min": 400, "hero_damage": 10000,
                 "tower_damage": 1000, "last_hits": 100, "denies": 5}
                for i in range(5)
            ] + [
                {"player_slot": 128 + i, "kills": 1, "deaths": 1, "assists": 1,
                 "gold_per_min": 400, "xp_per_min": 400, "hero_damage": 10000,
                 "tower_damage": 1000, "last_hits": 100, "denies": 5}
                for i in range(5)
            ],
        }
        with patch.object(client, "_request", return_value=mock_match):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    stats = client.get_fixture_stats("9999")

        # Radiant destroyed all dire towers: 11 - popcount(0) = 11
        assert stats["tower_kills"]["home"] == 11
        # Dire destroyed 0 radiant towers: 11 - popcount(2047) = 11 - 11 = 0
        assert stats["tower_kills"]["away"] == 0

    def test_tower_kills_partial(self, rate_limiter):
        """Test tower_kills with partial destruction."""
        client = OpenDotaClient(rate_limiter=rate_limiter)
        # 0b10000000111 = 1031 → 4 bits set → 7 destroyed
        mock_match = {
            "match_id": 8888,
            "duration": 2000,
            "radiant_win": False,
            "tower_status_radiant": 0b10000000111,  # 4 standing → 7 destroyed by dire
            "tower_status_dire": 0b11111111110,     # 10 standing → 1 destroyed by radiant
            "players": [
                {"player_slot": i, "kills": 1, "deaths": 1, "assists": 1,
                 "gold_per_min": 400, "xp_per_min": 400, "hero_damage": 10000,
                 "tower_damage": 1000, "last_hits": 100, "denies": 5}
                for i in range(5)
            ] + [
                {"player_slot": 128 + i, "kills": 1, "deaths": 1, "assists": 1,
                 "gold_per_min": 400, "xp_per_min": 400, "hero_damage": 10000,
                 "tower_damage": 1000, "last_hits": 100, "denies": 5}
                for i in range(5)
            ],
        }
        with patch.object(client, "_request", return_value=mock_match):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    stats = client.get_fixture_stats("8888")

        # Radiant killed 1 dire tower: 11 - 10 = 1
        assert stats["tower_kills"]["home"] == 1
        # Dire killed 7 radiant towers: 11 - 4 = 7
        assert stats["tower_kills"]["away"] == 7

    def test_skips_matches_without_start_time(self, rate_limiter):
        """Test that fixtures with start_time=0 are filtered out."""
        client = OpenDotaClient(rate_limiter=rate_limiter)
        mock_data = [
            {"match_id": 1, "start_time": 0, "radiant_name": "A", "dire_name": "B",
             "radiant_team_id": 1, "dire_team_id": 2, "league_name": "Test"},
            {"match_id": 2, "start_time": 1778100000, "radiant_name": "C", "dire_name": "D",
             "radiant_team_id": 3, "dire_team_id": 4, "league_name": "Test"},
        ]
        with patch.object(client, "_request", return_value=mock_data):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    fixtures = client.get_fixtures()

        assert len(fixtures) == 1
        assert fixtures[0].home_team == "C"


# ============================================================
# ITTF Table Tennis Tests
# ============================================================

class TestITTF:
    """Tests for ITTF Table Tennis client."""

    def test_instantiation(self, rate_limiter):
        client = ITTFClient(rate_limiter=rate_limiter)
        assert client.is_available()
        assert client.api_key is None

    def test_parse_set_scores(self, rate_limiter):
        """Test extraction of set scores from Sofascore event data."""
        client = ITTFClient(rate_limiter=rate_limiter)

        mock_event = {
            "event": {
                "homeTeam": {"name": "Ma Long"},
                "awayTeam": {"name": "Fan Zhendong"},
                "startTimestamp": 1778100000,
                "homeScore": {
                    "current": 4,
                    "period1": 11, "period2": 9, "period3": 11,
                    "period4": 11, "period5": 8, "period6": 11,
                },
                "awayScore": {
                    "current": 2,
                    "period1": 8, "period2": 11, "period3": 7,
                    "period4": 9, "period5": 11, "period6": 5,
                },
            }
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_event

        with patch("requests.get", return_value=mock_resp):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    stats = client.get_fixture_stats("12345")

        assert stats["sets_won"] == {"home": 4, "away": 2}
        assert stats["total_sets"] == {"home": 6, "away": 6}
        # Total points: (11+9+11+11+8+11) + (8+11+7+9+11+5) = 61+51 = 112
        assert stats["total_points"]["home"] == 112
        assert stats["points_scored"]["home"] == 61
        assert stats["points_scored"]["away"] == 51

    def test_fixtures_from_sofascore(self, rate_limiter):
        """Test fixture loading from Sofascore."""
        client = ITTFClient(rate_limiter=rate_limiter)

        mock_data = {
            "events": [
                {
                    "id": 99999,
                    "tournament": {
                        "name": "WTT Cup",
                        "uniqueTournament": {"name": "WTT Champions Macao"}
                    },
                    "homeTeam": {"id": 1, "name": "Wang Chuqin"},
                    "awayTeam": {"id": 2, "name": "Tomokazu Harimoto"},
                    "startTimestamp": 1778100000,
                    "status": {"type": "notstarted"},
                }
            ]
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_data

        with patch("requests.get", return_value=mock_resp):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    fixtures = client.get_fixtures("2026-05-07")

        assert len(fixtures) == 1
        assert fixtures[0].home_team == "Wang Chuqin"
        assert fixtures[0].sport == "table_tennis"
