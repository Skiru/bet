"""Tests for fetch_api_stats.py — pipeline orchestration and cache integration."""

import json
import sys
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from normalize_stats import NormalizedFixture, NormalizedMatchStats
from bet.api_clients.rate_limiter import RateLimiter
from bet.api_clients.base_client import APIRateLimitError, APIError
from build_stats_cache import slugify


# ---------------------------------------------------------------------------
# Helpers: mock data builders
# ---------------------------------------------------------------------------

def _make_fixture(fixture_id="100", sport="football", home="Liverpool", away="Arsenal",
                  competition="Premier League", kickoff="2026-04-28T20:00:00Z"):
    return NormalizedFixture(
        fixture_id=fixture_id, source="api-football", sport=sport,
        competition=competition, home_team=home, away_team=away,
        home_team_id="40", away_team_id="42", kickoff=kickoff, status="FT",
    )


def _make_match_stats(fixture_id="100", home="Liverpool", away="Arsenal",
                      sport="football", date="2026-04-20",
                      corners=(7, 5), fouls=(12, 9)):
    return NormalizedMatchStats(
        fixture_id=fixture_id, source="api-football", sport=sport,
        home_team=home, away_team=away, date=date,
        stats={
            "corners": {"home": corners[0], "away": corners[1]},
            "fouls": {"home": fouls[0], "away": fouls[1]},
            "yellow_cards": {"home": 2, "away": 3},
            "shots": {"home": 14, "away": 10},
            "shots_on_target": {"home": 6, "away": 4},
        },
    )


def _make_n_match_stats(n=10, home="Liverpool", sport="football"):
    """Generate N match stats with varying data."""
    matches = []
    for i in range(n):
        matches.append(_make_match_stats(
            fixture_id=str(200 + i),
            home=home,
            away=f"Opponent {i}",
            date=f"2026-04-{20 - i:02d}",
            corners=(6 + i % 3, 4 + i % 2),
            fouls=(11 + i % 4, 8 + i % 3),
        ))
    return matches


def _mock_client(team_fixtures=None, fixture_stats_map=None,
                 h2h_fixtures=None, resolve_ids=None):
    """Create a mock API client with configurable responses."""
    client = MagicMock()
    client.api_key = "test-key"
    client.api_name = "api-football"
    client.is_available.return_value = True

    resolve_ids = resolve_ids or {"liverpool": "40", "arsenal": "42"}
    client.resolve_team_id.side_effect = lambda name: resolve_ids.get(name.lower().strip())

    client.get_team_last_fixtures.return_value = team_fixtures or []

    fixture_stats_map = fixture_stats_map or {}
    client.get_fixture_stats.side_effect = lambda fid: fixture_stats_map.get(fid)

    client.get_h2h.return_value = h2h_fixtures or []

    return client


# ---------------------------------------------------------------------------
# Tests: fetch_team_stats
# ---------------------------------------------------------------------------

class TestFetchTeamStats:
    def test_returns_stats_for_each_fixture(self):
        from fetch_api_stats import fetch_team_stats

        fixtures = [_make_fixture(f"{i}") for i in range(3)]
        stats_map = {
            "0": _make_match_stats("0", date="2026-04-20"),
            "1": _make_match_stats("1", date="2026-04-18"),
            "2": _make_match_stats("2", date="2026-04-16"),
        }
        client = _mock_client(
            team_fixtures=fixtures,
            fixture_stats_map=stats_map,
            resolve_ids={"liverpool": "40"},
        )

        result = fetch_team_stats(client, "Liverpool", "football")
        assert len(result) == 3
        assert all(isinstance(m, NormalizedMatchStats) for m in result)

    def test_returns_empty_if_team_not_resolved(self):
        from fetch_api_stats import fetch_team_stats

        client = _mock_client(resolve_ids={})
        result = fetch_team_stats(client, "Unknown FC", "football")
        assert result == []

    def test_returns_empty_if_no_fixtures(self):
        from fetch_api_stats import fetch_team_stats

        client = _mock_client(
            team_fixtures=[],
            resolve_ids={"testteam": "99"},
        )
        result = fetch_team_stats(client, "TestTeam", "football")
        assert result == []

    def test_partial_on_rate_limit(self):
        from fetch_api_stats import fetch_team_stats

        fixtures = [_make_fixture(f"{i}") for i in range(5)]
        call_count = 0

        def get_stats_with_limit(fid):
            nonlocal call_count
            call_count += 1
            if call_count > 2:
                raise APIRateLimitError("Rate limited")
            return _make_match_stats(fid)

        client = _mock_client(
            team_fixtures=fixtures,
            resolve_ids={"liverpool": "40"},
        )
        client.get_fixture_stats.side_effect = get_stats_with_limit

        result = fetch_team_stats(client, "Liverpool", "football")
        # Should return 2 results (stopped before rate limit would affect 3rd)
        assert len(result) == 2

    def test_fills_date_from_fixture_kickoff(self):
        from fetch_api_stats import fetch_team_stats

        fixtures = [_make_fixture("500", kickoff="2026-04-25T18:00:00Z")]
        stats_no_date = _make_match_stats("500", date="")
        client = _mock_client(
            team_fixtures=fixtures,
            fixture_stats_map={"500": stats_no_date},
            resolve_ids={"liverpool": "40"},
        )

        result = fetch_team_stats(client, "Liverpool", "football")
        assert len(result) == 1
        assert result[0].date == "2026-04-25"

    def test_handles_dict_fixtures_and_list_stat_payloads(self):
        from fetch_api_stats import fetch_team_stats

        fixtures = [{"id": "500", "kickoff": "2026-04-25T18:00:00Z"}]
        stats_payload = [{
            "external_id": "500",
            "source": "api-football",
            "sport": "football",
            "home_team_name": "Liverpool",
            "away_team_name": "Arsenal",
            "stats": {
                "corners": {"home": 7, "away": 5},
                "fouls": {"home": 12, "away": 9},
            },
        }]
        client = _mock_client(
            team_fixtures=fixtures,
            fixture_stats_map={"500": stats_payload},
            resolve_ids={"liverpool": "40"},
        )

        result = fetch_team_stats(client, "Liverpool", "football")

        assert len(result) == 1
        assert result[0].fixture_id == "500"
        assert result[0].home_team == "Liverpool"
        assert result[0].away_team == "Arsenal"
        assert result[0].date == "2026-04-25"


class TestFetchH2HStats:
    def test_handles_dict_h2h_fixtures_and_list_stat_payloads(self):
        from fetch_api_stats import fetch_h2h_stats

        client = _mock_client(
            h2h_fixtures=[{"id": "600", "kickoff": "2026-04-21T20:00:00Z"}],
            fixture_stats_map={
                "600": [{
                    "external_id": "600",
                    "source": "api-football",
                    "sport": "football",
                    "home_team_name": "Liverpool",
                    "away_team_name": "Arsenal",
                    "stats": {
                        "corners": {"home": 8, "away": 4},
                    },
                }]
            },
            resolve_ids={"liverpool": "40", "arsenal": "42"},
        )

        result = fetch_h2h_stats(client, "Liverpool", "Arsenal", "football")

        assert len(result) == 1
        assert result[0].fixture_id == "600"
        assert result[0].date == "2026-04-21"
        assert result[0].stats["corners"]["home"] == 8


# ---------------------------------------------------------------------------
# Tests: enrich_fixture
# ---------------------------------------------------------------------------

class TestEnrichFixture:
    def test_enriched_with_full_data(self, tmp_path):
        from fetch_api_stats import enrich_fixture

        rate_limiter = RateLimiter(usage_dir=tmp_path / ".usage")

        fixture = {
            "fixture_id": "100",
            "sport": "football",
            "home_team": "Liverpool",
            "away_team": "Arsenal",
            "competition": "Premier League",
        }

        team_a_stats = _make_n_match_stats(10, "Liverpool")
        team_b_stats = _make_n_match_stats(10, "Arsenal")
        h2h_stats = _make_n_match_stats(5, "Liverpool")

        mock_client = _mock_client(resolve_ids={"liverpool": "40", "arsenal": "42"})

        # Simulate: resolve_team_id, get_team_last_fixtures, get_fixture_stats, get_h2h
        with patch("fetch_api_stats.get_client", return_value=mock_client), \
             patch("fetch_api_stats.fetch_team_stats") as mock_fetch_team, \
             patch("fetch_api_stats.fetch_h2h_stats") as mock_fetch_h2h, \
             patch("fetch_api_stats._store_in_cache"):

            mock_fetch_team.side_effect = [team_a_stats, team_b_stats]
            mock_fetch_h2h.return_value = h2h_stats

            result = enrich_fixture(fixture, rate_limiter)

        assert result["status"] == "enriched"
        assert result["api_source"] == "espn-football"
        assert result["team_a_matches"] == 10
        assert result["team_b_matches"] == 10
        assert result["h2h_matches"] == 5
        assert result["safety_input_built"] is True

    def test_skipped_for_unsupported_sport(self, tmp_path):
        from fetch_api_stats import enrich_fixture

        rate_limiter = RateLimiter(usage_dir=tmp_path / ".usage")
        fixture = {
            "fixture_id": "200",
            "sport": "curling",
            "home_team": "Team A",
            "away_team": "Team B",
            "competition": "World Cup",
        }

        result = enrich_fixture(fixture, rate_limiter)
        assert result["status"] == "skipped"

    def test_failed_with_missing_teams(self, tmp_path):
        from fetch_api_stats import enrich_fixture

        rate_limiter = RateLimiter(usage_dir=tmp_path / ".usage")
        fixture = {
            "fixture_id": "300",
            "sport": "football",
            "home_team": "",
            "away_team": "Arsenal",
            "competition": "PL",
        }

        result = enrich_fixture(fixture, rate_limiter)
        assert result["status"] == "failed"


# ---------------------------------------------------------------------------
# Tests: fallback chain
# ---------------------------------------------------------------------------

class TestFallbackChain:
    def test_falls_to_second_api_on_rate_limit(self, tmp_path):
        from fetch_api_stats import enrich_fixture

        rate_limiter = RateLimiter(usage_dir=tmp_path / ".usage")

        fixture = {
            "fixture_id": "400",
            "sport": "football",
            "home_team": "Liverpool",
            "away_team": "Arsenal",
            "competition": "Premier League",
        }

        # First two clients have no API key, third works
        mock_client_unavail = MagicMock()
        mock_client_unavail.api_key = None  # No key → skip
        mock_client_unavail.is_available.return_value = False

        mock_client_ok = MagicMock()
        mock_client_ok.api_key = "test-key"
        mock_client_ok.api_name = "football-data-org"
        mock_client_ok.is_available.return_value = True

        team_stats = _make_n_match_stats(6, "Liverpool")
        h2h_stats = []

        call_count = [0]

        def factory(api_name, rl):
            call_count[0] += 1
            if api_name in ("espn-football", "api-football"):
                return mock_client_unavail
            return mock_client_ok

        with patch("fetch_api_stats.get_client", side_effect=factory), \
             patch("fetch_api_stats.fetch_team_stats") as mock_fetch_team, \
             patch("fetch_api_stats.fetch_h2h_stats", return_value=h2h_stats), \
             patch("fetch_api_stats._store_in_cache"):

            mock_fetch_team.return_value = team_stats

            result = enrich_fixture(fixture, rate_limiter)

        # Should have tried espn-football + api-football (both unavailable) and used football-data-org
        assert result["api_source"] == "football-data-org"


# ---------------------------------------------------------------------------
# Tests: cache storage via update_from_api
# ---------------------------------------------------------------------------

class TestCacheStorage:
    def test_update_from_api_stores_l10(self, tmp_path):
        from build_stats_cache import update_from_api, read_cache, CACHE_DIR

        # Patch CACHE_DIR to tmp
        with patch("build_stats_cache.CACHE_DIR", tmp_path):
            matches = _make_n_match_stats(8, "Liverpool")
            path = update_from_api(
                sport="football",
                team="Liverpool",
                normalized_matches=matches,
                api_source="api-football",
            )

            assert path.exists()
            data = json.loads(path.read_text())
            assert data["api_source"] == "api-football"
            assert len(data["form"]["l10_matches"]) == 8
            assert "l10_avg" in data["form"]
            assert "l5_avg" in data["form"]
            assert "api-football" in data["sources"]

    def test_update_from_api_stores_h2h(self, tmp_path):
        from build_stats_cache import update_from_api

        with patch("build_stats_cache.CACHE_DIR", tmp_path):
            team_matches = _make_n_match_stats(6, "Liverpool")
            h2h_matches = _make_n_match_stats(3, "Liverpool")

            path = update_from_api(
                sport="football",
                team="Liverpool",
                normalized_matches=team_matches,
                api_source="api-football",
                opponent="Arsenal",
                h2h_matches=h2h_matches,
            )

            data = json.loads(path.read_text())
            assert "arsenal" in data["h2h"]
            assert len(data["h2h"]["arsenal"]["matches"]) == 3
            assert "avg" in data["h2h"]["arsenal"]

    def test_update_from_api_preserves_existing_h2h(self, tmp_path):
        from build_stats_cache import update_from_api, update_cache, create_team_cache_entry

        with patch("build_stats_cache.CACHE_DIR", tmp_path):
            # Pre-populate cache with H2H for Chelsea
            existing = create_team_cache_entry(
                team="Liverpool", sport="football",
                h2h_data={
                    "chelsea": {
                        "last_updated": "2026-04-27T10:00:00+00:00",
                        "matches": [{"date": "2026-03-01", "fixture_id": "old-1", "stats": {}}],
                        "avg": {},
                    }
                },
            )
            update_cache("football", "Liverpool", existing)

            # Now update with Arsenal H2H
            team_matches = _make_n_match_stats(6, "Liverpool")
            h2h_matches = _make_n_match_stats(2, "Liverpool")

            path = update_from_api(
                sport="football",
                team="Liverpool",
                normalized_matches=team_matches,
                api_source="api-football",
                opponent="Arsenal",
                h2h_matches=h2h_matches,
            )

            data = json.loads(path.read_text())
            # Both H2H entries should exist
            assert "arsenal" in data["h2h"]
            assert "chelsea" in data["h2h"]


# ---------------------------------------------------------------------------
# Tests: fetch_stats_for_date
# ---------------------------------------------------------------------------

class TestFetchStatsForDate:
    def test_loads_fixtures_and_enriches(self, tmp_path):
        from fetch_api_stats import fetch_stats_for_date

        # Create fixtures file
        data_dir = tmp_path / "betting" / "data"
        data_dir.mkdir(parents=True)
        fixtures = {
            "date": "2026-04-28",
            "fixtures": [
                {
                    "fixture_id": "1",
                    "sport": "football",
                    "home_team": "Liverpool",
                    "away_team": "Arsenal",
                    "competition": "Premier League",
                },
                {
                    "fixture_id": "2",
                    "sport": "basketball",
                    "home_team": "Lakers",
                    "away_team": "Celtics",
                    "competition": "NBA",
                },
            ],
            "count": 2,
        }
        fixtures_file = data_dir / "fixtures_2026-04-28.json"
        fixtures_file.write_text(json.dumps(fixtures))

        rate_limiter = RateLimiter(usage_dir=tmp_path / ".usage")

        with patch("fetch_api_stats.DATA_DIR", data_dir), \
             patch("fetch_api_stats.enrich_fixture") as mock_enrich:

            mock_enrich.return_value = {
                "fixture_id": "1",
                "status": "enriched",
                "api_source": "api-football",
                "team_a_matches": 10,
                "team_b_matches": 10,
                "h2h_matches": 5,
                "safety_input_built": True,
            }

            result = fetch_stats_for_date("2026-04-28", rate_limiter=rate_limiter)

        assert result["total_fixtures"] == 2
        assert mock_enrich.call_count == 2

    def test_filters_by_sport(self, tmp_path):
        from fetch_api_stats import fetch_stats_for_date

        data_dir = tmp_path / "betting" / "data"
        data_dir.mkdir(parents=True)
        fixtures = {
            "date": "2026-04-28",
            "fixtures": [
                {"fixture_id": "1", "sport": "football", "home_team": "A", "away_team": "B", "competition": "X"},
                {"fixture_id": "2", "sport": "basketball", "home_team": "C", "away_team": "D", "competition": "Y"},
                {"fixture_id": "3", "sport": "hockey", "home_team": "E", "away_team": "F", "competition": "Z"},
            ],
            "count": 3,
        }
        (data_dir / "fixtures_2026-04-28.json").write_text(json.dumps(fixtures))

        rate_limiter = RateLimiter(usage_dir=tmp_path / ".usage")

        with patch("fetch_api_stats.DATA_DIR", data_dir), \
             patch("fetch_api_stats.enrich_fixture") as mock_enrich:

            mock_enrich.return_value = {"fixture_id": "1", "status": "skipped"}
            result = fetch_stats_for_date(
                "2026-04-28", sports=["football"], rate_limiter=rate_limiter,
            )

        # Only football fixture should be enriched
        assert result["total_fixtures"] == 1
        # Two-phase enrichment: Phase 1 (ESPN) + Phase 2 (rate-limited) for missed
        assert mock_enrich.call_count == 2


# ---------------------------------------------------------------------------
# Tests: build_safety_input_from_cache with extended format
# ---------------------------------------------------------------------------

class TestBuildSafetyInputFromCache:
    def test_reads_extended_cache_format(self, tmp_path):
        from normalize_stats import build_safety_input_from_cache

        sport_dir = tmp_path / "football"
        sport_dir.mkdir()

        # Create cache with l10_matches format
        for team, slug in [("Liverpool", "liverpool"), ("Arsenal", "arsenal")]:
            cache = {
                "team": team,
                "sport": "football",
                "slug": slug,
                "last_updated": "2026-04-28T10:00:00+00:00",
                "ttl_hours": 24,
                "api_source": "api-football",
                "form": {
                    "l10_matches": [
                        {
                            "date": f"2026-04-{20 - i:02d}",
                            "opponent": "SomeTeam",
                            "fixture_id": str(i),
                            "stats": {
                                "corners": {"home": 6 + i, "away": 4 + i},
                                "fouls": {"home": 11 + i, "away": 8 + i},
                                "yellow_cards": {"home": 2, "away": 3},
                                "shots": {"home": 14, "away": 10},
                                "shots_on_target": {"home": 6, "away": 4},
                            },
                        }
                        for i in range(8)
                    ],
                    "l10_avg": {"corners_home": 9.5, "fouls_home": 14.5},
                    "l5_avg": {"corners_home": 10.0, "fouls_home": 15.0},
                },
                "h2h": {
                    "arsenal" if team == "Liverpool" else "liverpool": {
                        "last_updated": "2026-04-28T10:00:00+00:00",
                        "matches": [
                            {
                                "date": f"2026-03-{15 - i:02d}",
                                "fixture_id": f"h2h-{i}",
                                "stats": {
                                    "corners": {"home": 5 + i, "away": 4 + i},
                                    "fouls": {"home": 10 + i, "away": 9 + i},
                                    "yellow_cards": {"home": 3, "away": 2},
                                    "shots": {"home": 13, "away": 11},
                                    "shots_on_target": {"home": 5, "away": 4},
                                },
                            }
                            for i in range(4)
                        ],
                        "avg": {"corners_total": 11.0},
                    }
                },
                "sources": ["api-football"],
            }
            (sport_dir / f"{slug}.json").write_text(json.dumps(cache))

        result = build_safety_input_from_cache(
            "football", "Liverpool", "Arsenal", "Premier League",
            cache_dir=tmp_path,
        )

        assert result is not None
        assert result["sport"] == "football"
        assert result["team_a"] == "Liverpool"
        assert result["team_b"] == "Arsenal"
        assert len(result["markets"]) > 0


# ---------------------------------------------------------------------------
# Tests: per-match source provenance in shared persistence (M2 regression)
# ---------------------------------------------------------------------------

class TestPerMatchSourceProvenance:
    """Regression tests for M2: mixed-source batches must attribute each stat
    row/team_form row to its actual match source, not the batch api_source."""

    def _make_mixed_source_matches(self):
        """Two matches with different sources and non-overlapping stat keys."""
        m1 = NormalizedMatchStats(
            fixture_id="501",
            source="tennis-abstract",
            sport="tennis",
            home_team="Iga Swiatek",
            away_team="Aryna Sabalenka",
            date="2026-05-18",
            stats={"aces": 8.0, "double_faults": 2.0},
        )
        m2 = NormalizedMatchStats(
            fixture_id="502",
            source="sackmann",
            sport="tennis",
            home_team="Iga Swiatek",
            away_team="Elena Rybakina",
            date="2026-05-16",
            stats={"aces": 6.0, "hold_pct": 83.3},
        )
        return m1, m2

    def test_save_per_match_stat_arrays_uses_per_match_source(self):
        import fetch_api_stats
        from types import SimpleNamespace
        from unittest.mock import patch

        team_form_saves = []

        class FakeSportObj:
            id = 1

        class FakeTeamObj:
            id = 101

        class FakeStatsRepo:
            def __init__(self, conn=None):
                pass
            def save_team_form(self, form):
                team_form_saves.append(form)

        class FakeTeamRepo:
            def __init__(self, conn=None):
                pass
            def find_or_create(self, name, sport_id):
                return FakeTeamObj()

        class FakeSportRepo:
            def __init__(self, conn=None):
                pass
            def get_by_name(self, name):
                return FakeSportObj()

        class FakeConn:
            def commit(self):
                pass

        class FakeDB:
            def __enter__(self):
                return FakeConn()
            def __exit__(self, *_):
                return False

        m1, m2 = self._make_mixed_source_matches()

        with patch.object(fetch_api_stats, "_HAS_DB", True), \
             patch.object(fetch_api_stats, "get_db", return_value=FakeDB()), \
             patch.object(fetch_api_stats, "SportRepo", FakeSportRepo), \
             patch.object(fetch_api_stats, "TeamRepo", FakeTeamRepo), \
             patch.object(fetch_api_stats, "StatsRepo", FakeStatsRepo):
            fetch_api_stats._save_per_match_stat_arrays(
                "tennis", "Iga Swiatek", [m1, m2], "tennis-abstract"
            )

        forms = {f.stat_key: f for f in team_form_saves}

        # "aces" first appears in m1 (tennis-abstract) — even though m2 also
        # has "aces", the first-contributing source wins.
        assert forms["aces"].source == "tennis-abstract"
        # "double_faults" only in m1 → tennis-abstract
        assert forms["double_faults"].source == "tennis-abstract"
        # "hold_pct" only in m2 (sackmann) → sackmann, not the batch api_source
        assert forms["hold_pct"].source == "sackmann"

    def test_persist_match_stats_to_db_uses_per_match_source(self):
        import fetch_api_stats
        from types import SimpleNamespace
        from unittest.mock import patch

        saved_rows = []

        class FakeSportObj:
            id = 1

        class FakeTeamObj:
            id = 101

        class FakeFixtureObj:
            id = 501

        class FakeStatsRepo:
            def __init__(self, conn=None):
                pass
            def bulk_save_match_stats(self, rows):
                saved_rows.extend(rows)

        class FakeTeamRepo:
            def __init__(self, conn=None):
                pass
            def find_or_create(self, name, sport_id):
                return FakeTeamObj()

        class FakeSportRepo:
            def __init__(self, conn=None):
                pass
            def get_by_name(self, name):
                return FakeSportObj()

        class FakeFixtureRepo:
            def __init__(self, conn=None):
                pass
            def get_by_teams_and_date(self, home, away, date, sport_id):
                return FakeFixtureObj()

        class FakeConn:
            pass

        class FakeDB:
            def __enter__(self):
                return FakeConn()
            def __exit__(self, *_):
                return False

        m1, m2 = self._make_mixed_source_matches()

        with patch.object(fetch_api_stats, "_HAS_DB", True), \
             patch.object(fetch_api_stats, "get_db", return_value=FakeDB()), \
             patch.object(fetch_api_stats, "SportRepo", FakeSportRepo), \
             patch.object(fetch_api_stats, "TeamRepo", FakeTeamRepo), \
             patch.object(fetch_api_stats, "StatsRepo", FakeStatsRepo), \
             patch.object(fetch_api_stats, "FixtureRepo", FakeFixtureRepo):
            fetch_api_stats._persist_match_stats_to_db(
                "tennis", "Iga Swiatek", [m1, m2], "tennis-abstract"
            )

        # Each row is (fixture_id, team_id, stat_key, value, source)
        ta_rows = [row for row in saved_rows if row[4] == "tennis-abstract"]
        sack_rows = [row for row in saved_rows if row[4] == "sackmann"]

        # m1 (tennis-abstract) contributes aces and double_faults
        assert any(row[2] == "aces" for row in ta_rows), \
            "aces from m1 (tennis-abstract) must carry tennis-abstract source"
        assert any(row[2] == "double_faults" for row in ta_rows), \
            "double_faults only in m1 must carry tennis-abstract source"

        # m2 (sackmann) contributes aces and hold_pct with sackmann source
        assert any(row[2] == "aces" for row in sack_rows), \
            "aces from m2 (sackmann) must carry sackmann source"
        assert any(row[2] == "hold_pct" for row in sack_rows), \
            "hold_pct only in m2 (sackmann) must carry sackmann source, not the batch api_source"
