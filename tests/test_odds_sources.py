"""Unit tests for odds_sources package — ABC, utilities, and all 5 source wrappers."""

from unittest.mock import MagicMock, patch

import pytest

from scripts.odds_sources import (
    OddsSource,
    normalize_team_name,
    events_match,
    merge_event_odds,
    make_event_id,
    SPORT_SOURCE_PRIORITY,
)


# ===========================================================================
# normalize_team_name
# ===========================================================================


class TestNormalizeTeamName:
    def test_strips_fc_prefix(self):
        assert normalize_team_name("FC Barcelona") == "barcelona"

    def test_strips_cf_suffix(self):
        assert normalize_team_name("Real Madrid CF") == "real madrid"

    def test_strips_sk_prefix(self):
        assert normalize_team_name("SK Slavia Praha") == "slavia praha"

    def test_removes_parenthetical(self):
        assert normalize_team_name("Lublin (W)") == "lublin"

    def test_collapses_whitespace(self):
        assert normalize_team_name("  Team   Name  ") == "team name"

    def test_unicode_normalization(self):
        result = normalize_team_name("Łódź")
        # NFKD + ascii ignore strips diacritics; Ł has no ASCII decomposition so is dropped
        assert result == "odz"

    def test_lowercases(self):
        assert normalize_team_name("BORUSSIA DORTMUND") == "borussia dortmund"

    def test_strips_multiple_suffixes(self):
        assert normalize_team_name("AFC United") == ""

    def test_empty_string(self):
        assert normalize_team_name("") == ""


# ===========================================================================
# events_match
# ===========================================================================


class TestEventsMatch:
    @staticmethod
    def _event(home, away, time):
        return {"home_team": home, "away_team": away, "commence_time": time}

    def test_same_teams_same_time(self):
        a = self._event("Barcelona", "Real Madrid", "2026-04-29T18:00:00Z")
        b = self._event("Barcelona", "Real Madrid", "2026-04-29T18:00:00Z")
        assert events_match(a, b) is True

    def test_same_teams_within_2h(self):
        a = self._event("Barcelona", "Real Madrid", "2026-04-29T18:00:00Z")
        b = self._event("Barcelona", "Real Madrid", "2026-04-29T19:30:00Z")
        assert events_match(a, b) is True

    def test_same_teams_3h_apart(self):
        a = self._event("Barcelona", "Real Madrid", "2026-04-29T18:00:00Z")
        b = self._event("Barcelona", "Real Madrid", "2026-04-29T21:00:00Z")
        assert events_match(a, b) is False

    def test_different_teams_same_time(self):
        a = self._event("Barcelona", "Real Madrid", "2026-04-29T18:00:00Z")
        b = self._event("Liverpool", "Arsenal", "2026-04-29T18:00:00Z")
        assert events_match(a, b) is False

    def test_team_name_variations(self):
        a = self._event("FC Barcelona", "Real Madrid CF", "2026-04-29T18:00:00Z")
        b = self._event("Barcelona", "Real Madrid", "2026-04-29T18:00:00Z")
        assert events_match(a, b) is True

    def test_completely_different_teams(self):
        a = self._event("Juventus", "Milan", "2026-04-29T18:00:00Z")
        b = self._event("Bayern", "Dortmund", "2026-04-29T18:00:00Z")
        assert events_match(a, b) is False

    def test_missing_time_still_matches_by_name(self):
        a = self._event("Barcelona", "Real Madrid", "")
        b = self._event("Barcelona", "Real Madrid", "")
        assert events_match(a, b) is True

    def test_custom_tolerance(self):
        a = self._event("Barcelona", "Real Madrid", "2026-04-29T18:00:00Z")
        b = self._event("Barcelona", "Real Madrid", "2026-04-29T21:00:00Z")
        assert events_match(a, b, time_tolerance_hours=4.0) is True


# ===========================================================================
# merge_event_odds
# ===========================================================================


class TestMergeEventOdds:
    def test_merge_different_bookmakers(self):
        existing = {
            "home_team": "A",
            "away_team": "B",
            "bookmakers": [{"key": "bet365", "title": "Bet365", "markets": []}],
        }
        new = {
            "home_team": "A",
            "away_team": "B",
            "bookmakers": [{"key": "pinnacle", "title": "Pinnacle", "markets": []}],
        }
        merged = merge_event_odds(existing, new)
        assert len(merged["bookmakers"]) == 2
        keys = {bm["key"] for bm in merged["bookmakers"]}
        assert keys == {"bet365", "pinnacle"}

    def test_merge_overlapping_bookmaker_no_duplicate(self):
        existing = {
            "bookmakers": [
                {"key": "bet365", "title": "Bet365", "markets": []},
                {"key": "pinnacle", "title": "Pinnacle", "markets": []},
            ],
        }
        new = {
            "bookmakers": [
                {"key": "bet365", "title": "Bet365", "markets": []},
                {"key": "unibet", "title": "Unibet", "markets": []},
            ],
        }
        merged = merge_event_odds(existing, new)
        assert len(merged["bookmakers"]) == 3
        keys = [bm["key"] for bm in merged["bookmakers"]]
        assert keys.count("bet365") == 1

    def test_merge_preserves_existing_fields(self):
        existing = {"home_team": "X", "bookmakers": [{"key": "a", "markets": []}]}
        new = {"home_team": "Y", "bookmakers": [{"key": "b", "markets": []}]}
        merged = merge_event_odds(existing, new)
        # Merged result keeps existing's top-level fields
        assert merged["home_team"] == "X"
        assert len(merged["bookmakers"]) == 2


# ===========================================================================
# make_event_id
# ===========================================================================


class TestMakeEventId:
    def test_basic(self):
        eid = make_event_id("oddsportal", "football", "FC Barcelona", "Real Madrid", "18:00")
        assert "oddsportal" in eid
        assert "football" in eid
        assert "barcelona" in eid
        assert "real_madrid" in eid

    def test_deterministic(self):
        a = make_event_id("src", "sport", "Home", "Away", "12:00")
        b = make_event_id("src", "sport", "Home", "Away", "12:00")
        assert a == b


# ===========================================================================
# Source: supported_sports
# ===========================================================================


class TestSupportedSports:
    """Verify each source advertises correct sport coverage."""

    def test_the_odds_api_covers_api_sports(self):
        with patch("scripts.odds_sources.the_odds_api.get_api_key", return_value="fake"), \
             patch("scripts.odds_sources.the_odds_api._fetch_odds", return_value=([], {})):
            from scripts.odds_sources.the_odds_api import TheOddsAPISource
            src = TheOddsAPISource()
        sports = src.supported_sports()
        for s in ["football", "tennis", "basketball", "hockey"]:
            assert s in sports
        # Volleyball has empty keys in SPORT_KEY_MAP → not supported
        assert "volleyball" not in sports

    def test_oddsportal_covers_5_sports(self):
        from scripts.odds_sources.oddsportal_source import OddsPortalSource
        src = OddsPortalSource()
        assert len(src.supported_sports()) == 5
        assert "football" in src.supported_sports()
        assert "volleyball" in src.supported_sports()

    def test_betexplorer_covers_5_sports(self):
        from scripts.odds_sources.betexplorer_source import BetExplorerSource
        src = BetExplorerSource()
        assert len(src.supported_sports()) == 5
        assert "volleyball" in src.supported_sports()

    def test_api_football_odds_football_only(self):
        with patch("scripts.odds_sources.api_football_odds.APIFootballOddsClient"):
            from scripts.odds_sources.api_football_odds import APIFootballOddsSource
            src = APIFootballOddsSource()
        assert src.supported_sports() == ["football"]


# ===========================================================================
# Source: fetch_odds (mocked)
# ===========================================================================


def _make_sample_event(home="Team A", away="Team B", source="test"):
    """Helper to build a sample event dict."""
    return {
        "id": f"{source}_1",
        "sport_key": "football_test",
        "sport_title": "Football",
        "commence_time": "2026-04-29T18:00:00Z",
        "home_team": home,
        "away_team": away,
        "bookmakers": [
            {
                "key": f"{source}-bm",
                "title": f"{source} Bookmaker",
                "markets": [{"key": "h2h", "outcomes": [
                    {"name": home, "price": 1.50},
                    {"name": "Draw", "price": 3.80},
                    {"name": away, "price": 5.00},
                ]}],
            }
        ],
    }


class TestTheOddsAPIFetch:
    def test_returns_events_with_source_tag(self):
        sample = [_make_sample_event(source="odds-api")]
        with patch("scripts.odds_sources.the_odds_api._fetch_odds", return_value=(sample, {})), \
             patch("scripts.odds_sources.the_odds_api.get_api_key", return_value="fake-key"):
            from scripts.odds_sources.the_odds_api import TheOddsAPISource
            src = TheOddsAPISource()
            result = src.fetch_odds("football", "2026-04-29", "2026-04-29")
        assert len(result) >= 1
        assert result[0]["_odds_source"] == "the-odds-api"

    def test_unsupported_sport_returns_empty(self):
        with patch("scripts.odds_sources.the_odds_api.get_api_key", return_value="fake-key"):
            from scripts.odds_sources.the_odds_api import TheOddsAPISource
            src = TheOddsAPISource()
            result = src.fetch_odds("volleyball", "2026-04-29", "2026-04-29")
        assert result == []

    def test_api_error_returns_empty_list(self):
        """When every sport key raises, fetch_odds returns [] (errors are caught per-key)."""
        with patch("scripts.odds_sources.the_odds_api._fetch_odds", side_effect=Exception("timeout")), \
             patch("scripts.odds_sources.the_odds_api.get_api_key", return_value="fake-key"):
            from scripts.odds_sources.the_odds_api import TheOddsAPISource
            src = TheOddsAPISource()
            # Use a sport with a single key to avoid partial successes
            result = src.fetch_odds("mma", "2026-04-29", "2026-04-29")
        assert result == []


class TestAPIFootballOddsFetch:
    def test_returns_events_with_source_tag(self):
        sample = [_make_sample_event(source="api-football")]
        mock_client = MagicMock()
        mock_client.fetch_odds_for_date.return_value = sample

        with patch("scripts.odds_sources.api_football_odds.APIFootballOddsClient", return_value=mock_client):
            from scripts.odds_sources.api_football_odds import APIFootballOddsSource
            src = APIFootballOddsSource()
            src._client = mock_client
            result = src.fetch_odds("football", "2026-04-29", "2026-04-29")

        assert len(result) == 1
        assert result[0]["_odds_source"] == "api-football-odds"

    def test_non_football_returns_empty(self):
        from scripts.odds_sources.api_football_odds import APIFootballOddsSource
        with patch("scripts.odds_sources.api_football_odds.APIFootballOddsClient"):
            src = APIFootballOddsSource()
        assert src.fetch_odds("tennis", "2026-04-29", "2026-04-29") == []

    def test_api_error_returns_empty(self):
        mock_client = MagicMock()
        mock_client.fetch_odds_for_date.side_effect = Exception("connection refused")

        with patch("scripts.odds_sources.api_football_odds.APIFootballOddsClient", return_value=mock_client):
            from scripts.odds_sources.api_football_odds import APIFootballOddsSource
            src = APIFootballOddsSource()
            src._client = mock_client
            result = src.fetch_odds("football", "2026-04-29", "2026-04-29")

        assert result == []


def _scraper_fetch_test(module_path, source_class_name, source_name, adapter_module):
    """Generic test helper for Playwright-based scrapers."""
    parsed_rows = [
        {"home": "Team A", "away": "Team B", "odds": ["1.50", "3.80", "5.00"], "time": "18:00"},
        {"home": "Team C", "away": "Team D", "odds": ["2.10", "3.30", "3.40"], "time": "20:00"},
    ]

    with patch(f"{module_path}.pw_fetch", return_value="<html>fake</html>") as mock_pw, \
         patch(f"{module_path}.{adapter_module}", return_value=parsed_rows):
        import importlib
        mod = importlib.import_module(f"scripts.odds_sources.{module_path.split('.')[-1]}")
        SourceCls = getattr(mod, source_class_name)
        src = SourceCls()
        result = src.fetch_odds("football", "2026-04-29", "2026-04-29")

    return result


class TestOddsPortalFetch:
    def test_returns_events_with_source_tag(self):
        from dataclasses import dataclass

        @dataclass
        class FakeFixture:
            external_id: str = "ext123"
            source: str = "oddsportal"
            sport: str = "football"
            competition_name: str = "Test League"
            home_team_name: str = "Team A"
            away_team_name: str = "Team B"
            kickoff: str = "2026-04-29T18:00:00Z"
            status: str = "scheduled"

        mock_client = MagicMock()
        mock_client.get_fixtures.return_value = [FakeFixture()]
        mock_client.get_listing_odds.return_value = {}

        from scripts.odds_sources.oddsportal_source import OddsPortalSource
        src = OddsPortalSource()
        src._client = mock_client

        result = src.fetch_odds("football", "2026-04-29", "2026-04-29")

        assert len(result) == 1
        assert result[0]["_source"] == "oddsportal"
        assert result[0]["home_team"] == "Team A"
        assert result[0]["away_team"] == "Team B"

    def test_unsupported_sport_returns_empty(self):
        from scripts.odds_sources.oddsportal_source import OddsPortalSource
        src = OddsPortalSource()
        # "curling" is not in SPORT_URLS
        assert src.fetch_odds("curling", "2026-04-29", "2026-04-29") == []

    def test_client_error_returns_empty(self):
        from scripts.odds_sources.oddsportal_source import OddsPortalSource
        src = OddsPortalSource()
        mock_client = MagicMock()
        mock_client.get_fixtures.side_effect = Exception("browser crash")
        src._client = mock_client
        result = src.fetch_odds("football", "2026-04-29", "2026-04-29")
        assert result == []


class TestBetExplorerFetch:
    def test_returns_events_with_source_tag(self):
        from dataclasses import dataclass

        @dataclass
        class FakeFixture:
            external_id: str = "ext456"
            source: str = "betexplorer"
            sport: str = "football"
            competition_name: str = "Test League"
            home_team_name: str = "Team X"
            away_team_name: str = "Team Y"
            kickoff: str = "2026-04-29T15:00:00Z"
            status: str = "scheduled"

        mock_client = MagicMock()
        mock_client.get_fixtures.return_value = [FakeFixture()]

        from scripts.odds_sources.betexplorer_source import BetExplorerSource
        src = BetExplorerSource()
        src._client = mock_client

        result = src.fetch_odds("football", "2026-04-29", "2026-04-29")

        assert len(result) == 1
        assert result[0]["_source"] == "betexplorer"
        assert result[0]["home_team"] == "Team X"

    def test_no_client_returns_empty(self):
        from scripts.odds_sources.betexplorer_source import BetExplorerSource
        src = BetExplorerSource()
        src._client = None
        # Force _get_client to fail
        with patch("scripts.odds_sources.betexplorer_source.BetExplorerSource._get_client", return_value=None):
            result = src.fetch_odds("football", "2026-04-29", "2026-04-29")
        assert result == []

    def test_client_error_returns_empty(self):
        from scripts.odds_sources.betexplorer_source import BetExplorerSource
        src = BetExplorerSource()
        mock_client = MagicMock()
        mock_client.get_fixtures.side_effect = Exception("timeout")
        src._client = mock_client
        result = src.fetch_odds("football", "2026-04-29", "2026-04-29")
        assert result == []


class TestBetclicFetch:
    """Betclic scraping is banned per R12 — no betclic_scraper module exists.
    These tests verify the absence of Betclic as a scraped source."""

    def test_betclic_scraper_module_does_not_exist(self):
        """R12: DO NOT scrape Betclic (403). Module should not exist."""
        import importlib
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("scripts.odds_sources.betclic_scraper")

    def test_betclic_not_in_source_priority(self):
        """R12: Betclic is the execution bookmaker, not a scraped source."""
        for sport, sources in SPORT_SOURCE_PRIORITY.items():
            assert "betclic" not in sources, f"betclic should not be in {sport} sources (R12)"


# ===========================================================================
# SPORT_SOURCE_PRIORITY
# ===========================================================================


class TestSportSourcePriority:
    def test_all_5_sports_have_priority(self):
        assert len(SPORT_SOURCE_PRIORITY) == 5

    def test_football_includes_working_sources(self):
        assert "the-odds-api" in SPORT_SOURCE_PRIORITY["football"]
        assert "api-football-odds" in SPORT_SOURCE_PRIORITY["football"]
        assert "odds-api-io" in SPORT_SOURCE_PRIORITY["football"]

    def test_volleyball_has_odds_api_io(self):
        assert "odds-api-io" in SPORT_SOURCE_PRIORITY["volleyball"]
        assert "the-odds-api" not in SPORT_SOURCE_PRIORITY["volleyball"]

    def test_every_sport_has_at_least_one_source(self):
        for sport, sources in SPORT_SOURCE_PRIORITY.items():
            assert len(sources) >= 1, f"{sport} has no sources"

    def test_no_broken_sources_in_priority(self):
        """SPORT_SOURCE_PRIORITY should not reference broken odds sources."""
        BROKEN = {"oddsportal", "betexplorer"}
        for sport, sources in SPORT_SOURCE_PRIORITY.items():
            for src in sources:
                assert src not in BROKEN, f"{sport} references broken source {src}"
