"""Integration tests for fetch_odds_multi.py — multi-source aggregator."""

import csv
import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.fetch_odds_multi import (
    run_multi_scan,
    extract_best_odds,
    _load_source,
    load_configured_sports,
)


# ===========================================================================
# Fixtures & helpers
# ===========================================================================

def _make_event(eid, home, away, time, source, sport="football", bookmakers=None):
    """Build a minimal event dict."""
    if bookmakers is None:
        bookmakers = [{
            "key": f"{source}-bm",
            "title": f"{source} Bookmaker",
            "markets": [{
                "key": "h2h",
                "outcomes": [
                    {"name": home, "price": 1.50},
                    {"name": "Draw", "price": 3.80},
                    {"name": away, "price": 5.00},
                ],
            }],
        }]
    return {
        "id": eid,
        "sport_key": f"{sport}_{source}",
        "sport_title": sport.title(),
        "commence_time": time,
        "home_team": home,
        "away_team": away,
        "bookmakers": bookmakers,
        "_our_sport": sport,
        "_odds_source": source,
        "_sport_key": f"{sport}_{source}",
    }


def _build_mock_source(name, sports, events):
    """Build a MagicMock source implementing OddsSource interface."""
    src = MagicMock()
    src.name = name
    src.supported_sports.return_value = sports
    src.fetch_odds.return_value = events
    return src


@pytest.fixture
def mock_data_dir(tmp_path, monkeypatch):
    """Redirect DATA_DIR to tmp_path so output files don't pollute the workspace."""
    monkeypatch.setattr("scripts.fetch_odds_multi.DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def mock_config(tmp_path, monkeypatch):
    """Provide a minimal betting_config.json."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "betting_config.json"
    config_file.write_text(json.dumps({
        "sports": ["football", "tennis", "volleyball"],
    }))
    monkeypatch.setattr("scripts.fetch_odds_multi.CONFIG_DIR", config_dir)
    return config_dir


# ===========================================================================
# extract_best_odds
# ===========================================================================


class TestExtractBestOdds:
    def test_extracts_h2h(self):
        event = _make_event("e1", "Home", "Away", "2026-04-29T18:00:00Z", "test")
        best = extract_best_odds(event)
        assert best["home_team"] == "Home"
        assert "h2h" in best["markets"]
        assert best["markets"]["h2h"]["Home"]["price"] == 1.50

    def test_no_bookmakers(self):
        event = _make_event("e2", "H", "A", "2026-04-29T18:00:00Z", "test", bookmakers=[])
        best = extract_best_odds(event)
        assert best["markets"] == {}


# ===========================================================================
# load_configured_sports
# ===========================================================================


class TestLoadConfiguredSports:
    def test_loads_from_config(self, mock_config):
        sports = load_configured_sports()
        assert sports == ["football", "tennis", "volleyball"]

    def test_fallback_when_no_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr("scripts.fetch_odds_multi.CONFIG_DIR", tmp_path / "nonexistent")
        sports = load_configured_sports()
        # Should return defaults from SPORT_SOURCE_PRIORITY
        assert len(sports) == 5


# ===========================================================================
# _load_source
# ===========================================================================


class TestLoadSource:
    def test_unknown_source_returns_none(self):
        assert _load_source("nonexistent-source") is None

    def test_broken_source_returns_none(self):
        with patch("importlib.import_module", side_effect=ImportError("broken")):
            result = _load_source("the-odds-api")
        assert result is None


# ===========================================================================
# run_multi_scan — merge correctness
# ===========================================================================


class TestMultiScanMerge:
    """Events from multiple sources are merged via fuzzy matching."""

    def test_same_event_from_two_sources_merged(self, mock_data_dir, mock_config):
        """Same match from two sources → single event with combined bookmakers."""
        ev_odds_api = _make_event(
            "oa1", "Barcelona", "Real Madrid", "2026-04-29T20:00:00Z", "the-odds-api",
            bookmakers=[{"key": "pinnacle", "title": "Pinnacle", "markets": []}],
        )
        ev_odds_io = _make_event(
            "io1", "FC Barcelona", "Real Madrid CF", "2026-04-29T20:00:00Z", "odds-api-io",
            bookmakers=[{"key": "betclic-pl", "title": "Betclic PL", "markets": []}],
        )

        src_api = _build_mock_source("the-odds-api", ["football"], [ev_odds_api])
        src_io = _build_mock_source("odds-api-io", ["football"], [ev_odds_io])

        with patch("scripts.fetch_odds_multi._load_source") as mock_load, \
             patch("scripts.fetch_odds_multi.load_configured_sports", return_value=["football"]):
            mock_load.side_effect = lambda n: {"the-odds-api": src_api, "odds-api-io": src_io}.get(n)
            events = run_multi_scan(sport_filter=["football"])

        assert len(events) == 1
        bm_keys = {bm["key"] for bm in events[0]["bookmakers"]}
        assert "pinnacle" in bm_keys
        assert "betclic-pl" in bm_keys

    def test_different_events_not_merged(self, mock_data_dir, mock_config):
        """Different matches from same source remain separate."""
        ev1 = _make_event("e1", "Barcelona", "Real Madrid", "2026-04-29T18:00:00Z", "the-odds-api")
        ev2 = _make_event("e2", "Liverpool", "Arsenal", "2026-04-29T20:00:00Z", "the-odds-api")

        src = _build_mock_source("the-odds-api", ["football"], [ev1, ev2])

        with patch("scripts.fetch_odds_multi._load_source", return_value=src), \
             patch("scripts.fetch_odds_multi.load_configured_sports", return_value=["football"]):
            events = run_multi_scan(sport_filter=["football"])

        assert len(events) == 2


# ===========================================================================
# run_multi_scan — output files
# ===========================================================================


class TestMultiScanOutputs:
    """Verify output file schema and content."""

    def _run_with_events(self, mock_data_dir, events, sports=None):
        if sports is None:
            sports = ["football"]
        src = _build_mock_source("the-odds-api", sports, events)
        with patch("scripts.fetch_odds_multi._load_source", return_value=src), \
             patch("scripts.fetch_odds_multi.load_configured_sports", return_value=sports):
            run_multi_scan(sport_filter=sports)
        return mock_data_dir

    def test_snapshot_json_schema(self, mock_data_dir, mock_config):
        ev = _make_event("e1", "A", "B", "2026-04-29T18:00:00Z", "the-odds-api")
        data_dir = self._run_with_events(mock_data_dir, [ev])
        snapshot = json.loads((data_dir / "odds_api_snapshot.json").read_text())
        assert "timestamp" in snapshot
        assert "total_events" in snapshot
        assert snapshot["total_events"] == 1
        assert "events" in snapshot
        assert isinstance(snapshot["events"], list)

    def test_summary_csv_columns(self, mock_data_dir, mock_config):
        ev = _make_event("e1", "Home", "Away", "2026-04-29T18:00:00Z", "the-odds-api")
        data_dir = self._run_with_events(mock_data_dir, [ev])
        with open(data_dir / "odds_api_summary.csv") as f:
            reader = csv.reader(f)
            header = next(reader)
        expected = [
            "sport", "sport_key", "home", "away", "commence_time",
            "h2h_home", "h2h_away", "total_line", "over_price",
            "over_book", "under_price", "under_book",
        ]
        assert header == expected

    def test_summary_csv_has_data_rows(self, mock_data_dir, mock_config):
        ev = _make_event("e1", "Home", "Away", "2026-04-29T18:00:00Z", "the-odds-api")
        data_dir = self._run_with_events(mock_data_dir, [ev])
        with open(data_dir / "odds_api_summary.csv") as f:
            rows = list(csv.reader(f))
        assert len(rows) == 2  # header + 1 data row

    def test_provenance_json_tracks_sources(self, mock_data_dir, mock_config):
        ev = _make_event("e1", "A", "B", "2026-04-29T18:00:00Z", "the-odds-api")
        data_dir = self._run_with_events(mock_data_dir, [ev])
        prov = json.loads((data_dir / "odds_multi_sources.json").read_text())
        assert "timestamp" in prov
        assert "sources_used" in prov
        assert "per_sport" in prov
        assert "total_events" in prov
        assert prov["total_events"] == 1
        assert "the-odds-api" in prov["sources_used"]


# ===========================================================================
# run_multi_scan — sports filter
# ===========================================================================


class TestMultiScanSportsFilter:
    def test_filter_limits_sports(self, mock_data_dir, mock_config):
        """--sports volleyball should only scan volleyball."""
        src = _build_mock_source("oddsportal", ["football", "volleyball"], [])
        with patch("scripts.fetch_odds_multi._load_source", return_value=src), \
             patch("scripts.fetch_odds_multi.load_configured_sports",
                   return_value=["football", "volleyball"]):
            events = run_multi_scan(sport_filter=["volleyball"])

        # fetch_odds should only have been called with volleyball
        calls = [c for c in src.fetch_odds.call_args_list]
        sport_args = [c[0][0] for c in calls]
        assert "volleyball" in sport_args
        assert "football" not in sport_args


# ===========================================================================
# run_multi_scan — dry run
# ===========================================================================


class TestMultiScanDryRun:
    def test_dry_run_no_api_calls(self, mock_data_dir, mock_config):
        """--dry-run should not call any source.fetch_odds."""
        src = _build_mock_source("the-odds-api", ["football"], [])
        with patch("scripts.fetch_odds_multi._load_source", return_value=src), \
             patch("scripts.fetch_odds_multi.load_configured_sports", return_value=["football"]):
            result = run_multi_scan(dry_run=True)

        src.fetch_odds.assert_not_called()
        assert result is None  # dry_run returns early


# ===========================================================================
# run_multi_scan — missing source for sport
# ===========================================================================


class TestMultiScanMissingSources:
    def test_no_source_produces_empty_not_error(self, mock_data_dir, mock_config):
        """Sport with no loadable source → empty results, no crash."""
        with patch("scripts.fetch_odds_multi._load_source", return_value=None), \
             patch("scripts.fetch_odds_multi.load_configured_sports", return_value=["volleyball"]):
            events = run_multi_scan(sport_filter=["volleyball"])

        assert events == []

    def test_source_error_captured_gracefully(self, mock_data_dir, mock_config):
        """Source that raises during fetch → errors recorded, not propagated."""
        src = _build_mock_source("oddsportal", ["volleyball"], [])
        src.fetch_odds.side_effect = Exception("scraper blew up")

        # _load_source returns the same failing mock for every source name
        # volleyball has 3 sources in priority: oddsportal, betexplorer, betclic
        with patch("scripts.fetch_odds_multi._load_source", return_value=src), \
             patch("scripts.fetch_odds_multi.load_configured_sports", return_value=["volleyball"]):
            events = run_multi_scan(sport_filter=["volleyball"])

        assert events == []
        prov = json.loads((mock_data_dir / "odds_multi_sources.json").read_text())
        assert "errors" in prov
        assert len(prov["errors"]) >= 1
        assert all(e["sport"] == "volleyball" for e in prov["errors"])
