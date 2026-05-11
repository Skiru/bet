"""Tests for ESPN API client."""

from unittest.mock import patch, MagicMock

import pytest

from bet.api_clients.espn import (
    ESPNClient,
    ESPN_SPORT_MAP,
    ESPN_LEAGUES,
    SOCCER_STAT_MAP,
    NBA_STAT_MAP,
    NHL_STAT_MAP,
    COMPETITION_TO_ESPN_LEAGUE,
    get_espn_league_for_competition,
    _is_game_finished,
)
from bet.api_clients.rate_limiter import RateLimiter
from bet.api_clients.api_football import APIFixture, APIMatchStats


@pytest.fixture
def rate_limiter():
    return RateLimiter()


@pytest.fixture
def soccer_client(rate_limiter):
    return ESPNClient(sport="football", league="eng.1", rate_limiter=rate_limiter)


@pytest.fixture
def nba_client(rate_limiter):
    return ESPNClient(sport="basketball", league="nba", rate_limiter=rate_limiter)


@pytest.fixture
def nhl_client(rate_limiter):
    return ESPNClient(sport="hockey", league="nhl", rate_limiter=rate_limiter)



class TestESPNClientInit:
    """Test ESPN client initialization."""

    def test_no_api_key_needed(self, soccer_client):
        assert soccer_client.api_key == "espn-no-key"

    def test_is_available(self, soccer_client):
        assert soccer_client.is_available() is True

    def test_sport_mapping(self, soccer_client):
        assert soccer_client._espn_sport == "soccer"
        assert soccer_client.sport == "football"

    def test_base_url(self, soccer_client):
        assert "soccer/eng.1" in soccer_client.base_url

    def test_nba_base_url(self, nba_client):
        assert "basketball/nba" in nba_client.base_url

    def test_headers_no_api_key(self, soccer_client):
        headers = soccer_client._build_headers()
        assert "x-apisports-key" not in headers
        assert headers["Accept"] == "application/json"

    def test_api_name(self, soccer_client):
        assert soccer_client.api_name == "espn-football"

    def test_nba_api_name(self, nba_client):
        assert nba_client.api_name == "espn-basketball"


class TestStatMappings:
    """Test stat mapping correctness per sport."""

    def test_soccer_stat_map_has_key_stats(self):
        assert "wonCorners" in SOCCER_STAT_MAP
        assert SOCCER_STAT_MAP["wonCorners"] == "corners"
        assert SOCCER_STAT_MAP["foulsCommitted"] == "fouls"
        assert SOCCER_STAT_MAP["yellowCards"] == "yellow_cards"
        assert SOCCER_STAT_MAP["totalShots"] == "shots"
        assert SOCCER_STAT_MAP["possessionPct"] == "possession"

    def test_nba_stat_map_has_key_stats(self):
        assert NBA_STAT_MAP["totalRebounds"] == "rebounds"
        assert NBA_STAT_MAP["assists"] == "assists"
        assert NBA_STAT_MAP["steals"] == "steals"
        assert NBA_STAT_MAP["fieldGoalPct"] == "fg_pct"
        assert NBA_STAT_MAP["threePointFieldGoalPct"] == "three_pct"

    def test_nhl_stat_map_has_key_stats(self):
        assert NHL_STAT_MAP["hits"] == "hits"
        assert NHL_STAT_MAP["blockedShots"] == "blocks"
        assert NHL_STAT_MAP["shotsTotal"] == "shots"
        assert NHL_STAT_MAP["powerPlayPct"] == "power_play_pct"

    def test_soccer_stat_map_size(self):
        assert len(SOCCER_STAT_MAP) == 28

    def test_nba_stat_map_size(self):
        assert len(NBA_STAT_MAP) == 17

    def test_nhl_stat_map_size(self):
        assert len(NHL_STAT_MAP) == 14


class TestLeagueMapping:
    """Test competition name to ESPN league mapping."""

    def test_premier_league(self):
        assert get_espn_league_for_competition("Premier League") == "eng.1"

    def test_la_liga(self):
        assert get_espn_league_for_competition("La Liga") == "esp.1"

    def test_bundesliga(self):
        assert get_espn_league_for_competition("Bundesliga") == "ger.1"

    def test_ekstraklasa(self):
        assert get_espn_league_for_competition("Ekstraklasa") == "pol.1"

    def test_unknown_competition(self):
        assert get_espn_league_for_competition("Unknown League 42") is None

    def test_empty_competition(self):
        assert get_espn_league_for_competition("") is None


class TestIsGameFinished:
    """Test the _is_game_finished helper."""

    def test_explicit_status_full_time(self):
        event = {
            "date": "2025-01-01T15:00Z",
            "status": {"type": {"name": "STATUS_FULL_TIME", "state": "post"}},
            "competitions": [{"competitors": [{"score": "2"}]}],
        }
        assert _is_game_finished(event) is True

    def test_explicit_status_final(self):
        event = {
            "date": "2025-01-01T15:00Z",
            "status": {"type": {"name": "STATUS_FINAL", "state": "post"}},
            "competitions": [{"competitors": [{"score": "3"}]}],
        }
        assert _is_game_finished(event) is True

    def test_future_game_not_finished(self):
        event = {
            "date": "2099-01-01T15:00Z",
            "status": {"type": {"name": "", "state": "pre"}},
            "competitions": [{"competitors": [{"score": "0"}]}],
        }
        assert _is_game_finished(event) is False

    def test_past_game_with_score_is_finished(self):
        event = {
            "date": "2020-01-01T15:00Z",
            "status": {"type": {"name": "", "state": ""}},
            "competitions": [{"competitors": [{"score": "2"}, {"score": "1"}]}],
        }
        assert _is_game_finished(event) is True

    def test_past_game_zero_zero_is_finished(self):
        """A 0-0 game in the past with score fields present IS finished."""
        event = {
            "date": "2020-01-01T15:00Z",
            "status": {"type": {"name": "", "state": ""}},
            "competitions": [{"competitors": [{"score": "0"}, {"score": "0"}]}],
        }
        assert _is_game_finished(event) is True

    def test_past_game_no_score_field_not_finished(self):
        """A past game without any score field is NOT finished."""
        event = {
            "date": "2020-01-01T15:00Z",
            "status": {"type": {"name": "", "state": ""}},
            "competitions": [{"competitors": [{}, {}]}],
        }
        assert _is_game_finished(event) is False


class TestGetFixtures:
    """Test get_fixtures with mocked responses."""

    @patch("bet.api_clients.espn.ESPNClient._check_cache", return_value=None)
    @patch("bet.api_clients.espn.ESPNClient._save_cache")
    @patch("bet.api_clients.espn.ESPNClient._request")
    def test_get_fixtures_returns_api_fixtures(self, mock_request, mock_save, mock_cache, soccer_client):
        mock_request.return_value = {
            "events": [
                {
                    "id": "12345",
                    "date": "2025-05-03T15:00Z",
                    "season": {"type": {"name": "Regular Season"}},
                    "status": {"type": {"name": "STATUS_FULL_TIME", "state": "post"}},
                    "competitions": [
                        {
                            "competitors": [
                                {"homeAway": "home", "team": {"displayName": "Arsenal"}},
                                {"homeAway": "away", "team": {"displayName": "Chelsea"}},
                            ]
                        }
                    ],
                }
            ]
        }

        fixtures = soccer_client.get_fixtures("2025-05-03")
        assert len(fixtures) == 1
        assert isinstance(fixtures[0], APIFixture)
        assert fixtures[0].home_team_name == "Arsenal"
        assert fixtures[0].away_team_name == "Chelsea"
        assert fixtures[0].external_id == "12345"
        assert fixtures[0].sport == "football"


class TestGetFixtureStats:
    """Test get_fixture_stats with mocked responses."""

    @patch("bet.api_clients.espn.ESPNClient._check_cache", return_value=None)
    @patch("bet.api_clients.espn.ESPNClient._save_cache")
    @patch("bet.api_clients.espn.ESPNClient._request")
    def test_soccer_stats_parsed(self, mock_request, mock_save, mock_cache, soccer_client):
        mock_request.return_value = {
            "boxscore": {
                "teams": [
                    {
                        "team": {"displayName": "Arsenal"},
                        "homeAway": "home",
                        "statistics": [
                            {"name": "wonCorners", "displayValue": "7"},
                            {"name": "foulsCommitted", "displayValue": "12"},
                            {"name": "totalShots", "displayValue": "15"},
                            {"name": "possessionPct", "displayValue": "62.5"},
                        ],
                    },
                    {
                        "team": {"displayName": "Chelsea"},
                        "homeAway": "away",
                        "statistics": [
                            {"name": "wonCorners", "displayValue": "4"},
                            {"name": "foulsCommitted", "displayValue": "9"},
                            {"name": "totalShots", "displayValue": "8"},
                            {"name": "possessionPct", "displayValue": "37.5"},
                        ],
                    },
                ]
            }
        }

        stats = soccer_client.get_fixture_stats("12345")
        assert len(stats) == 1
        ms = stats[0]
        assert isinstance(ms, APIMatchStats)
        assert ms.home_team_name == "Arsenal"
        assert ms.away_team_name == "Chelsea"
        assert ms.stats["corners"]["home"] == 7.0
        assert ms.stats["corners"]["away"] == 4.0
        assert ms.stats["fouls"]["home"] == 12.0
        assert ms.stats["shots"]["home"] == 15.0
        assert ms.stats["possession"]["home"] == 62.5

    @patch("bet.api_clients.espn.ESPNClient._check_cache", return_value=None)
    @patch("bet.api_clients.espn.ESPNClient._save_cache")
    @patch("bet.api_clients.espn.ESPNClient._request")
    def test_nba_stats_parsed(self, mock_request, mock_save, mock_cache, nba_client):
        mock_request.return_value = {
            "boxscore": {
                "teams": [
                    {
                        "team": {"displayName": "Los Angeles Lakers"},
                        "homeAway": "home",
                        "statistics": [
                            {"name": "totalRebounds", "displayValue": "45"},
                            {"name": "assists", "displayValue": "28"},
                            {"name": "fieldGoalPct", "displayValue": "48.5"},
                        ],
                    },
                    {
                        "team": {"displayName": "Boston Celtics"},
                        "homeAway": "away",
                        "statistics": [
                            {"name": "totalRebounds", "displayValue": "38"},
                            {"name": "assists", "displayValue": "25"},
                            {"name": "fieldGoalPct", "displayValue": "45.2"},
                        ],
                    },
                ]
            }
        }

        stats = nba_client.get_fixture_stats("67890")
        assert len(stats) == 1
        ms = stats[0]
        assert ms.stats["rebounds"]["home"] == 45.0
        assert ms.stats["assists"]["away"] == 25.0
        assert ms.stats["fg_pct"]["home"] == 48.5

    @patch("bet.api_clients.espn.ESPNClient._check_cache", return_value=None)
    @patch("bet.api_clients.espn.ESPNClient._save_cache")
    @patch("bet.api_clients.espn.ESPNClient._request")
    def test_nhl_stats_parsed(self, mock_request, mock_save, mock_cache, nhl_client):
        mock_request.return_value = {
            "boxscore": {
                "teams": [
                    {
                        "team": {"displayName": "Toronto Maple Leafs"},
                        "homeAway": "home",
                        "statistics": [
                            {"name": "hits", "displayValue": "25"},
                            {"name": "blockedShots", "displayValue": "18"},
                            {"name": "shotsTotal", "displayValue": "32"},
                            {"name": "faceoffPercent", "displayValue": "52.3"},
                        ],
                    },
                    {
                        "team": {"displayName": "Montreal Canadiens"},
                        "homeAway": "away",
                        "statistics": [
                            {"name": "hits", "displayValue": "22"},
                            {"name": "blockedShots", "displayValue": "15"},
                            {"name": "shotsTotal", "displayValue": "28"},
                            {"name": "faceoffPercent", "displayValue": "47.7"},
                        ],
                    },
                ]
            }
        }

        stats = nhl_client.get_fixture_stats("55555")
        assert len(stats) == 1
        ms = stats[0]
        assert ms.stats["hits"]["home"] == 25.0
        assert ms.stats["blocks"]["away"] == 15.0
        assert ms.stats["shots"]["home"] == 32.0


class TestResolveTeamId:
    """Test team ID resolution with mocked responses."""

    @patch("bet.api_clients.espn.ESPNClient._check_cache", return_value=None)
    @patch("bet.api_clients.espn.ESPNClient._save_cache")
    @patch("bet.api_clients.espn.ESPNClient._request")
    def test_exact_match(self, mock_request, mock_save, mock_cache, soccer_client):
        mock_request.return_value = {
            "sports": [
                {
                    "leagues": [
                        {
                            "teams": [
                                {"team": {"id": "359", "displayName": "Arsenal", "shortDisplayName": "Arsenal", "abbreviation": "ARS", "location": "Arsenal"}},
                                {"team": {"id": "363", "displayName": "Chelsea", "shortDisplayName": "Chelsea", "abbreviation": "CHE", "location": "Chelsea"}},
                            ]
                        }
                    ]
                }
            ]
        }

        tid = soccer_client.resolve_team_id("Arsenal")
        assert tid == "359"

    @patch("bet.api_clients.espn.ESPNClient._check_cache", return_value=None)
    @patch("bet.api_clients.espn.ESPNClient._save_cache")
    @patch("bet.api_clients.espn.ESPNClient._request")
    def test_partial_match(self, mock_request, mock_save, mock_cache, soccer_client):
        mock_request.return_value = {
            "sports": [
                {
                    "leagues": [
                        {
                            "teams": [
                                {"team": {"id": "364", "displayName": "Tottenham Hotspur", "shortDisplayName": "Tottenham", "abbreviation": "TOT", "location": "Tottenham"}},
                            ]
                        }
                    ]
                }
            ]
        }

        tid = soccer_client.resolve_team_id("Tottenham")
        assert tid == "364"

    @patch("bet.api_clients.espn.ESPNClient._check_cache", return_value=None)
    @patch("bet.api_clients.espn.ESPNClient._save_cache")
    @patch("bet.api_clients.espn.ESPNClient._request")
    def test_no_match_returns_none(self, mock_request, mock_save, mock_cache, soccer_client):
        mock_request.return_value = {
            "sports": [
                {
                    "leagues": [
                        {
                            "teams": [
                                {"team": {"id": "1", "displayName": "Some Team", "shortDisplayName": "Some", "abbreviation": "ST", "location": "Somewhere"}},
                            ]
                        }
                    ]
                }
            ]
        }

        tid = soccer_client.resolve_team_id("Nonexistent FC")
        assert tid is None

    @patch("bet.api_clients.espn.ESPNClient._check_cache")
    def test_uses_cache(self, mock_cache, soccer_client):
        mock_cache.return_value = {"team_id": "999"}
        tid = soccer_client.resolve_team_id("Cached Team")
        assert tid == "999"


class TestGetTeamLastFixtures:
    """Test team fixture retrieval and filtering."""

    @patch("bet.api_clients.espn.ESPNClient._check_cache", return_value=None)
    @patch("bet.api_clients.espn.ESPNClient._save_cache")
    @patch("bet.api_clients.espn.ESPNClient._request")
    def test_filters_completed_games(self, mock_request, mock_save, mock_cache, soccer_client):
        mock_request.return_value = {
            "events": [
                {
                    "id": "1",
                    "date": "2025-04-01T15:00Z",
                    "status": {"type": {"name": "STATUS_FULL_TIME", "state": "post"}},
                    "competitions": [
                        {
                            "competitors": [
                                {"homeAway": "home", "team": {"displayName": "Arsenal"}, "score": "2"},
                                {"homeAway": "away", "team": {"displayName": "Chelsea"}, "score": "1"},
                            ]
                        }
                    ],
                },
                {
                    "id": "2",
                    "date": "2099-06-01T15:00Z",
                    "status": {"type": {"name": "STATUS_SCHEDULED", "state": "pre"}},
                    "competitions": [
                        {
                            "competitors": [
                                {"homeAway": "home", "team": {"displayName": "Arsenal"}, "score": "0"},
                                {"homeAway": "away", "team": {"displayName": "Liverpool"}, "score": "0"},
                            ]
                        }
                    ],
                },
            ]
        }

        fixtures = soccer_client.get_team_last_fixtures("359", last_n=10)
        assert len(fixtures) == 1
        assert fixtures[0]["id"] == "1"
        assert fixtures[0]["home_team"] == "Arsenal"

    @patch("bet.api_clients.espn.ESPNClient._check_cache", return_value=None)
    @patch("bet.api_clients.espn.ESPNClient._save_cache")
    @patch("bet.api_clients.espn.ESPNClient._request")
    def test_limits_to_last_n(self, mock_request, mock_save, mock_cache, soccer_client):
        # Create 15 completed events
        events = []
        for i in range(15):
            events.append({
                "id": str(i),
                "date": f"2025-01-{15-i:02d}T15:00Z",
                "status": {"type": {"name": "STATUS_FULL_TIME", "state": "post"}},
                "competitions": [
                    {
                        "competitors": [
                            {"homeAway": "home", "team": {"displayName": "Arsenal"}, "score": "1"},
                            {"homeAway": "away", "team": {"displayName": f"Team {i}"}, "score": "0"},
                        ]
                    }
                ],
            })
        mock_request.return_value = {"events": events}

        fixtures = soccer_client.get_team_last_fixtures("359", last_n=5)
        assert len(fixtures) == 5


class TestESPNClientRegistry:
    """Test ESPN client registration in CLIENT_REGISTRY."""

    def test_espn_football_registered(self):
        from bet.api_clients import CLIENT_REGISTRY
        assert "espn-football" in CLIENT_REGISTRY

    def test_espn_basketball_registered(self):
        from bet.api_clients import CLIENT_REGISTRY
        assert "espn-basketball" in CLIENT_REGISTRY

    def test_espn_hockey_registered(self):
        from bet.api_clients import CLIENT_REGISTRY
        assert "espn-hockey" in CLIENT_REGISTRY

    def test_get_client_factory(self):
        from bet.api_clients import get_client
        client = get_client("espn-football")
        assert isinstance(client, ESPNClient)
        assert client.sport == "football"
        assert client.league == "eng.1"
