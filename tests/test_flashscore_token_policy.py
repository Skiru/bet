"""Regression tests for the Flashscore token-remediation policy."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import flashscore_bulk_enrich
import flashscore_enricher
import settle_on_finish
import data_enrichment_agent
from bet.api_clients import unified as unified_module
from bet.api_clients.unified import UnifiedAPIClient
from bet.api_clients.volleyball_data import VolleyballDataClient
from bet.db.models import Fixture
from bet.db.repositories import CompetitionRepo, FixtureRepo, SportRepo, StatsRepo, TeamRepo
from bet.stats.fallback_chains import FALLBACK_CHAINS

SCHEMA_PATH = ROOT / "src" / "bet" / "db" / "schema.sql"


@pytest.fixture
def settlement_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text())

    sport_repo = SportRepo(conn)
    sport_repo.seed_defaults()
    football = sport_repo.get_by_name("football")
    assert football is not None

    team_repo = TeamRepo(conn)
    competition_repo = CompetitionRepo(conn)
    fixture_repo = FixtureRepo(conn)
    stats_repo = StatsRepo(conn)

    home = team_repo.find_or_create("Real Madrid", football.id)
    away = team_repo.find_or_create("Alaves", football.id)
    competition_id = competition_repo.find_or_create("LaLiga", football.id)

    fixture = Fixture(
        id=None,
        sport_id=football.id,
        competition_id=competition_id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff="2026-04-21T21:00:00",
        status="finished",
        score_home=2,
        score_away=0,
        source="test",
        fetched_at="2026-04-21T23:00:00",
    )
    fixture_id = fixture_repo.upsert(fixture)

    stats_repo.bulk_save_match_stats([
        (fixture_id, home.id, "corners", 7.0, "api-football"),
        (fixture_id, away.id, "corners", 3.0, "api-football"),
        (fixture_id, home.id, "yellow_cards", 2.0, "api-football"),
        (fixture_id, away.id, "yellow_cards", 4.0, "api-football"),
    ])
    conn.commit()

    yield {
        "conn": conn,
        "football": football,
        "home": home,
        "away": away,
        "fixture_id": fixture_id,
    }
    conn.close()


class TestTokenizedFeedRetirement:
    def test_flashscore_enricher_source_has_no_tokenized_feed_url(self):
        source = (ROOT / "scripts" / "flashscore_enricher.py").read_text()
        assert "d.flashscore.com/x/feed/d_st_" not in source

    def test_retired_helper_returns_no_stats(self):
        assert flashscore_enricher._fetch_match_statistics(["abc12345"], "football") == {}

    def test_bulk_enrich_source_has_no_tokenized_helper_reference(self):
        source = (ROOT / "scripts" / "flashscore_bulk_enrich.py").read_text()
        assert "_fetch_match_statistics" not in source


class TestUnifiedRoutingPolicy:
    def test_flashscore_not_in_canonical_match_stats_chain(self):
        assert "flashscore" not in unified_module.STATS_PRIORITY["football"]

    def test_unified_prefers_canonical_non_flashscore_provider(self):
        client = UnifiedAPIClient()
        visited: list[str] = []

        def fake_get_client(name: str):
            visited.append(name)
            if name == "espn-football":
                provider = MagicMock()
                provider.get_fixture_stats.return_value = [{"source": name}]
                return provider
            return None

        client._get_client = fake_get_client  # type: ignore[method-assign]

        result = client.get_fixture_stats("fixture-1", sport="football")

        assert result == [{"source": "espn-football"}]
        assert visited[0] == "espn-football"
        assert "flashscore" not in visited

    def test_unified_deep_data_no_longer_calls_flashscore_stats(self):
        client = UnifiedAPIClient()
        flashscore = MagicMock()
        flashscore.get_match_preview.return_value = {
            "form_home": ["W"],
            "form_away": ["L"],
            "h2h": [{"id": "1"}],
        }
        flashscore.get_fixture_stats.return_value = [{"unexpected": True}]
        client._get_client = MagicMock(return_value=flashscore)

        result = client.get_deep_data("fixture-1", status="finished")

        flashscore.get_fixture_stats.assert_not_called()
        assert result["stats"] == []


class TestSettlementStatMarkets:
    def test_settlement_source_can_be_db_backed(self):
        pick = {
            "market": "Corners Total O/U",
            "selection": "OVER 9.5",
            "bookmaker_odds": "1.90",
            "stake_pln": "10.00",
        }
        match_stats = {"corners": {"home": 6, "away": 5}}

        settled = settle_on_finish.settle_stat_market(
            pick,
            match_stats,
            "Home",
            "Away",
        )

        assert settled is True
        assert pick["status"] == "win"
        assert pick["settlement_source"] == "db_match_stats_settlement"

    def test_manual_settlement_source_is_marked_for_pending_stat_markets(self):
        pick = {
            "market": "Corners Total O/U",
            "selection": "OVER 9.5",
            "status": "pending",
        }

        marked = settle_on_finish._mark_manual_settlement_source([pick])

        assert marked == [pick]
        assert pick["settlement_source"] == "manual_verification_required"

    def test_settlement_script_uses_db_match_stats_helper_in_main_path(self):
        source = (ROOT / "scripts" / "settle_on_finish.py").read_text()
        assert "_fetch_settlement_db_match_stats(" in source
        assert "search_sofascore(" not in source

    @patch("bet.db.connection.get_db")
    def test_db_match_stats_helper_resolves_fixture_stats(self, mock_get_db, settlement_db):
        ctx = MagicMock()
        ctx.__enter__.return_value = settlement_db["conn"]
        ctx.__exit__.return_value = False
        mock_get_db.return_value = ctx

        result = settle_on_finish._fetch_settlement_db_match_stats(
            "Real Madrid",
            "Alaves",
            sport="football",
            betting_day="2026-04-21",
        )

        assert result == {
            "corners": {"home": 7.0, "away": 3.0},
            "yellow_cards": {"home": 2.0, "away": 4.0},
        }

    @patch("bet.db.connection.get_db")
    def test_db_match_stats_helper_handles_missing_coverage(self, mock_get_db, settlement_db):
        ctx = MagicMock()
        ctx.__enter__.return_value = settlement_db["conn"]
        ctx.__exit__.return_value = False
        mock_get_db.return_value = ctx

        result = settle_on_finish._fetch_settlement_db_match_stats(
            "Real Madrid",
            "Alaves",
            sport="football",
            betting_day="2026-04-19",
        )

        assert result is None

    @patch("settle_on_finish.requests.get")
    def test_settlement_search_helper_quotes_flashscore_query(self, mock_get):
        response = MagicMock()
        response.status_code = 200
        response.text = ""
        mock_get.return_value = response

        settle_on_finish.search_flashscore("A&B", "Łódź", sport="football")

        called_urls = [call.args[0] for call in mock_get.call_args_list]
        assert "https://www.flashscore.com/search/?q=A%26B%20%C5%81%C3%B3d%C5%BA" in called_urls

    @patch("bet.db.connection.get_db")
    def test_db_match_stats_helper_tries_neighboring_dates(self, mock_get_db, settlement_db):
        ctx = MagicMock()
        ctx.__enter__.return_value = settlement_db["conn"]
        ctx.__exit__.return_value = False
        mock_get_db.return_value = ctx

        result = settle_on_finish._fetch_settlement_db_match_stats(
            "Real Madrid",
            "Alaves",
            sport="football",
            betting_day="2026-04-22",
        )

        assert result == {
            "corners": {"home": 7.0, "away": 3.0},
            "yellow_cards": {"home": 2.0, "away": 4.0},
        }

    @patch("settle_on_finish._append_learning_log")
    @patch("settle_on_finish._sync_settlement_to_db")
    @patch("settle_on_finish.write_csv")
    @patch("settle_on_finish.log")
    @patch("settle_on_finish._fetch_settlement_db_match_stats")
    @patch("settle_on_finish.search_flashscore_playwright")
    @patch("settle_on_finish.search_flashscore")
    @patch("settle_on_finish.search_cached_html")
    @patch("settle_on_finish.search_odds_api_snapshot")
    def test_main_prefers_db_stats_over_flashscore_html_for_football_stat_markets(
        self,
        mock_snapshot,
        mock_cached_html,
        mock_flashscore,
        mock_playwright,
        mock_db_stats,
        _mock_log,
        _mock_write_csv,
        _mock_sync_db,
        _mock_learning_log,
    ):
        pick = {
            "pick_id": "PK-TEST-1",
            "event": "Crystal Palace vs Shakhtar Donetsk",
            "sport": "football",
            "market": "corners_total",
            "selection": "OVER 5.5",
            "status": "pending",
            "bookmaker_odds": "1.80",
            "stake_pln": "10.00",
            "betting_day": "2026-05-07",
        }

        mock_snapshot.return_value = None
        mock_cached_html.return_value = None
        mock_flashscore.return_value = None
        mock_playwright.return_value = (2, 1)
        mock_db_stats.return_value = {"corners": {"home": 1.0, "away": 5.0}}

        with patch("settle_on_finish.read_csv", side_effect=[[pick], []]), patch.object(
            sys,
            "argv",
            ["settle_on_finish.py", "--no-poll"],
        ):
            settle_on_finish.main()

        mock_db_stats.assert_called_once()
        assert pick["status"] == "win"
        assert pick["settlement_source"] == "db_match_stats_settlement"


class TestVolleyballCanonicalFallback:
    def test_shared_volleyball_fallback_chain(self):
        assert FALLBACK_CHAINS["volleyball"] == [
            "espn-volleyball",
            "api-volleyball",
            "flashscore-volleyball",
            "sofascore",
            "google-sports",
            "serpapi",
        ]

    @patch("bet.api_clients.get_client")
    def test_volleyball_match_stats_returns_none_for_payload_without_stats(self, mock_get_client):
        provider = MagicMock()
        provider.get_fixture_stats.return_value = {"unexpected": True}
        mock_get_client.return_value = provider

        client = object.__new__(VolleyballDataClient)

        result = client.fetch_match_stats("fixture-1")

        assert result is None

    @patch("bet.api_clients.get_client")
    def test_volleyball_match_stats_extracts_stats_from_list_payload(self, mock_get_client):
        provider = MagicMock()
        provider.get_fixture_stats.return_value = [MagicMock(stats={"aces": {"home": 5, "away": 2}})]
        mock_get_client.return_value = provider

        client = object.__new__(VolleyballDataClient)

        result = client.fetch_match_stats("fixture-1")

        assert result == {"aces": {"home": 5, "away": 2}}

    @patch("bet.api_clients.get_client")
    def test_volleyball_match_stats_uses_only_canonical_default_providers(self, mock_get_client):
        espn_provider = MagicMock()
        espn_provider.get_fixture_stats.return_value = None
        api_provider = MagicMock()
        api_provider.get_fixture_stats.return_value = [MagicMock(stats={"aces": {"home": 4, "away": 1}})]

        providers = {
            "espn-volleyball": espn_provider,
            "api-volleyball": api_provider,
        }
        called_names: list[str] = []

        def fake_get_client(name):
            called_names.append(name)
            return providers.get(name)

        mock_get_client.side_effect = fake_get_client

        client = object.__new__(VolleyballDataClient)

        result = client.fetch_match_stats("fixture-1")

        assert result == {"aces": {"home": 4, "away": 1}}
        assert called_names == ["api-volleyball"]

    def test_volleyball_enrichment_never_calls_flashscore_last_resort(self, monkeypatch):
        client = MagicMock()
        client.api_name = "google-sports"
        client.is_available.return_value = True

        monkeypatch.setattr(data_enrichment_agent, "FALLBACK_CHAINS", {"volleyball": ["google-sports"]})
        monkeypatch.setattr(data_enrichment_agent, "get_client", lambda *args, **kwargs: client)
        monkeypatch.setattr(data_enrichment_agent, "fetch_team_stats", lambda *args, **kwargs: [])
        monkeypatch.setattr(data_enrichment_agent, "_source_is_down", lambda *_: False)
        monkeypatch.setattr(
            data_enrichment_agent,
            "complete_volleyball_rich_stats",
            lambda *args, **kwargs: {
                "team": "Poland",
                "sport": "volleyball",
                "source": "api-volleyball",
                "status": "failed",
                "fixtures_scanned": 0,
                "matches_persisted": 0,
                "rich_keys_found": [],
                "missing_rich_keys": ["aces", "blocks", "hitting_pct", "points"],
                "error": "No rich volleyball stats found",
                "failure_reason": "stats_missing",
            },
        )
        flashscore_mock = MagicMock(return_value=({"points": [75]}, None))
        monkeypatch.setattr(data_enrichment_agent, "_try_flashscore", flashscore_mock)

        result = data_enrichment_agent.enrich_team("Poland", "volleyball")

        flashscore_mock.assert_not_called()
        assert result["source"] is None
        assert result["status"] == "failed"