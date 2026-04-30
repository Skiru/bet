"""Integration tests for deep_analysis_pool.py."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from scripts.deep_analysis_pool import (
    analyze_fixture,
    generate_analysis_pool,
    load_fixtures,
    load_odds_snapshot,
    write_pool_json,
    write_pool_markdown,
)
from scripts import normalize_stats as _ns_mod


def _make_cache_data(team: str, sport: str = "football",
                     corners_home: int = 6, corners_away: int = 4,
                     fouls_home: int = 13, fouls_away: int = 11) -> dict:
    """Build a fake stats cache file for a team."""
    matches = []
    for i in range(10):
        matches.append({
            "fixture_id": f"cache-{team}-{i}",
            "date": f"2026-04-{20 - i:02d}",
            "opponent": f"Opponent-{i}",
            "stats": {
                "corners": {"home": corners_home + (i % 3), "away": corners_away + (i % 2)},
                "fouls": {"home": fouls_home, "away": fouls_away},
                "yellow_cards": {"home": 2, "away": 1},
                "shots": {"home": 14, "away": 10},
                "shots_on_target": {"home": 5, "away": 3},
                "goals": {"home": 1, "away": 1},
            },
        })
    return {
        "team": team,
        "sport": sport,
        "form": {"l10_matches": matches},
        "h2h": {},
    }


def _write_cache(cache_dir: Path, sport: str, team_slug: str, data: dict):
    """Write a cache file for a team."""
    sport_dir = cache_dir / sport
    sport_dir.mkdir(parents=True, exist_ok=True)
    cache_file = sport_dir / f"{team_slug}.json"
    cache_file.write_text(json.dumps(data), encoding="utf-8")


def _make_fixtures(fixtures: list[dict]) -> dict:
    """Wrap fixtures in the expected file format."""
    return {"fixtures": fixtures}


class TestLoadFixtures(unittest.TestCase):
    def test_load_existing_fixtures(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            fixtures = _make_fixtures([
                {"home_team": "Liverpool", "away_team": "Arsenal", "sport": "football"},
            ])
            (data_dir / "fixtures_2026-04-28.json").write_text(json.dumps(fixtures))
            with patch("scripts.deep_analysis_pool.DATA_DIR", data_dir):
                result = load_fixtures("2026-04-28")
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["home_team"], "Liverpool")

    def test_load_missing_fixtures_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("scripts.deep_analysis_pool.DATA_DIR", Path(tmpdir)):
                result = load_fixtures("2099-01-01")
            self.assertEqual(result, [])


class TestLoadOddsSnapshot(unittest.TestCase):
    def test_load_dict_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            odds = {
                "football": [
                    {"home_team": "Liverpool", "away_team": "Arsenal", "odds": {"h2h": [1.8, 3.5, 4.2]}},
                ]
            }
            (data_dir / "odds_api_snapshot.json").write_text(json.dumps(odds))
            with patch("scripts.deep_analysis_pool.DATA_DIR", data_dir):
                result = load_odds_snapshot()
            self.assertIn("liverpool|arsenal", result)

    def test_load_missing_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("scripts.deep_analysis_pool.DATA_DIR", Path(tmpdir)):
                result = load_odds_snapshot()
            self.assertEqual(result, {})


class TestAnalyzeFixture(unittest.TestCase):
    def test_returns_none_for_missing_teams(self):
        result = analyze_fixture({"sport": "football"}, {})
        self.assertIsNone(result)

    def test_returns_minimal_dict_for_cache_miss(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "stats_cache"
            cache_dir.mkdir()
            with patch.object(_ns_mod, "CACHE_DIR", cache_dir):
                result = analyze_fixture(
                    {"home_team": "NoTeam", "away_team": "NoTeam2", "sport": "football"},
                    {},
                )
            self.assertIsNotNone(result)
            self.assertEqual(result["data_quality"], "NO_CACHE")
            self.assertTrue(result["cache_miss"])

    def test_successful_analysis(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "stats_cache"
            _write_cache(cache_dir, "football", "liverpool", _make_cache_data("Liverpool"))
            _write_cache(cache_dir, "football", "arsenal", _make_cache_data("Arsenal", corners_home=5, corners_away=3))

            with patch.object(_ns_mod, "CACHE_DIR", cache_dir):
                result = analyze_fixture(
                    {
                        "home_team": "Liverpool",
                        "away_team": "Arsenal",
                        "sport": "football",
                        "competition": "Premier League",
                        "kickoff": "2026-04-28T15:00:00Z",
                        "fixture_id": "12345",
                    },
                    {},
                )

            self.assertIsNotNone(result)
            self.assertEqual(result["home_team"], "Liverpool")
            self.assertEqual(result["away_team"], "Arsenal")
            self.assertEqual(result["sport"], "football")
            self.assertIn("best_market", result)
            self.assertIsNotNone(result["best_market"])
            self.assertIn("safety_score", result["best_market"])
            self.assertGreater(len(result["all_markets"]), 0)
            self.assertIn("markdown_table", result)


class TestGenerateAnalysisPool(unittest.TestCase):
    def _setup_pool(self, tmpdir: str, fixtures: list[dict]) -> Path:
        """Set up data dir with fixtures and cache, return data_dir."""
        data_dir = Path(tmpdir) / "data"
        data_dir.mkdir()
        cache_dir = Path(tmpdir) / "stats_cache"

        (data_dir / "fixtures_2026-04-28.json").write_text(
            json.dumps(_make_fixtures(fixtures))
        )

        for f in fixtures:
            home_slug = f["home_team"].lower().replace(" ", "-")
            away_slug = f["away_team"].lower().replace(" ", "-")
            _write_cache(cache_dir, f.get("sport", "football"), home_slug, _make_cache_data(f["home_team"]))
            _write_cache(cache_dir, f.get("sport", "football"), away_slug, _make_cache_data(f["away_team"]))

        return data_dir, cache_dir

    def test_empty_fixtures(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            (data_dir / "fixtures_2026-04-28.json").write_text(
                json.dumps({"fixtures": []})
            )
            with patch("scripts.deep_analysis_pool.DATA_DIR", data_dir):
                pool = generate_analysis_pool("2026-04-28")
            self.assertEqual(pool["total_events_in_pool"], 0)
            self.assertEqual(pool["events"], [])

    def test_no_fixtures_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("scripts.deep_analysis_pool.DATA_DIR", Path(tmpdir)):
                pool = generate_analysis_pool("2099-01-01")
            self.assertEqual(pool["total_events_in_pool"], 0)

    def test_pool_with_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fixtures = [
                {"home_team": "Liverpool", "away_team": "Arsenal", "sport": "football", "competition": "PL"},
                {"home_team": "Chelsea", "away_team": "Everton", "sport": "football", "competition": "PL"},
            ]
            data_dir, cache_dir = self._setup_pool(tmpdir, fixtures)

            with patch("scripts.deep_analysis_pool.DATA_DIR", data_dir), \
                 patch.object(_ns_mod, "CACHE_DIR", cache_dir):
                pool = generate_analysis_pool("2026-04-28")

            self.assertEqual(pool["date"], "2026-04-28")
            self.assertGreaterEqual(pool["total_events_in_pool"], 1)
            self.assertIn("generated_at", pool)

            # Events should be ranked by safety score desc
            events = pool["events"]
            if len(events) >= 2:
                s1 = events[0].get("best_market", {}).get("safety_score", 0)
                s2 = events[1].get("best_market", {}).get("safety_score", 0)
                self.assertGreaterEqual(s1, s2)

            # Each event should have rank
            for ev in events:
                self.assertIn("rank", ev)

    def test_sport_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fixtures = [
                {"home_team": "Liverpool", "away_team": "Arsenal", "sport": "football", "competition": "PL"},
                {"home_team": "Lakers", "away_team": "Celtics", "sport": "basketball", "competition": "NBA"},
            ]
            data_dir, cache_dir = self._setup_pool(tmpdir, fixtures)

            with patch("scripts.deep_analysis_pool.DATA_DIR", data_dir), \
                 patch.object(_ns_mod, "CACHE_DIR", cache_dir):
                pool = generate_analysis_pool("2026-04-28", sports=["basketball"])

            # Only basketball events should pass through (may still be 0 if no basketball markets)
            for ev in pool["events"]:
                self.assertEqual(ev["sport"], "basketball")


class TestWritePoolJson(unittest.TestCase):
    def test_writes_valid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            pool = {
                "date": "2026-04-28",
                "generated_at": "2026-04-28T12:00:00Z",
                "api_usage": {},
                "total_fixtures_discovered": 5,
                "total_fixtures_with_data": 3,
                "total_events_in_pool": 3,
                "events": [
                    {
                        "rank": 1,
                        "home_team": "Liverpool",
                        "away_team": "Arsenal",
                        "sport": "football",
                        "best_market": {"name": "Corners O/U 9.5", "safety_score": 0.85},
                        "all_markets": [],
                        "data_quality": "PARTIAL",
                    }
                ],
            }

            with patch("scripts.deep_analysis_pool.DATA_DIR", data_dir):
                path = write_pool_json(pool, "2026-04-28")

            self.assertTrue(path.exists())
            loaded = json.loads(path.read_text())
            self.assertEqual(loaded["date"], "2026-04-28")
            self.assertEqual(loaded["total_events_in_pool"], 3)
            self.assertEqual(len(loaded["events"]), 1)


class TestWritePoolMarkdown(unittest.TestCase):
    def test_writes_markdown_with_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            pool = {
                "date": "2026-04-28",
                "generated_at": "2026-04-28T12:00:00Z",
                "api_usage": {},
                "total_fixtures_discovered": 5,
                "total_fixtures_with_data": 2,
                "total_events_in_pool": 2,
                "events": [
                    {
                        "rank": 1,
                        "home_team": "Liverpool",
                        "away_team": "Arsenal",
                        "sport": "football",
                        "competition": "Premier League",
                        "kickoff": "15:00",
                        "data_quality": "PARTIAL",
                        "best_market": {
                            "name": "Corners O/U 9.5",
                            "direction": "OVER",
                            "safety_score": 0.85,
                            "l10_avg": 11.2,
                            "h2h_avg": 10.8,
                            "three_way": "3/3 SUPPORT",
                            "margin": 1.179,
                        },
                        "all_markets": [
                            {
                                "rank": 1,
                                "name": "Corners O/U 9.5",
                                "direction": "OVER",
                                "safety": 0.85,
                                "l10_avg": 11.2,
                                "h2h_avg": 10.8,
                                "hit_l10": "8/10",
                                "hit_h2h": "6/7",
                                "margin": 1.179,
                            },
                        ],
                        "ev": None,
                    },
                    {
                        "rank": 2,
                        "home_team": "Chelsea",
                        "away_team": "Everton",
                        "sport": "football",
                        "competition": "Premier League",
                        "kickoff": "17:30",
                        "data_quality": "THIN",
                        "best_market": {
                            "name": "Fouls O/U 22.5",
                            "direction": "OVER",
                            "safety_score": 0.70,
                            "l10_avg": 24.1,
                            "h2h_avg": None,
                            "three_way": "2/2 SUPPORT",
                            "margin": 1.071,
                        },
                        "all_markets": [],
                        "ev": None,
                    },
                ],
            }

            with patch("scripts.deep_analysis_pool.DATA_DIR", data_dir):
                path = write_pool_markdown(pool, "2026-04-28")

            self.assertTrue(path.exists())
            content = path.read_text()

            # Header
            self.assertIn("# Analysis Pool — 2026-04-28", content)
            # Events
            self.assertIn("Liverpool vs Arsenal", content)
            self.assertIn("Chelsea vs Everton", content)
            # Table headers
            self.assertIn("| # | Market | Dir |", content)
            # Market row
            self.assertIn("Corners O/U 9.5", content)
            self.assertIn("0.85", content)
            # Summary
            self.assertIn("## Summary", content)
            self.assertIn("Total events analyzed: 2", content)

    def test_empty_pool_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            pool = {
                "date": "2026-04-28",
                "generated_at": "2026-04-28T12:00:00Z",
                "api_usage": {},
                "total_fixtures_discovered": 0,
                "total_fixtures_with_data": 0,
                "total_events_in_pool": 0,
                "events": [],
            }

            with patch("scripts.deep_analysis_pool.DATA_DIR", data_dir):
                path = write_pool_markdown(pool, "2026-04-28")

            content = path.read_text()
            self.assertIn("# Analysis Pool — 2026-04-28", content)
            self.assertIn("Total events analyzed: 0", content)


if __name__ == "__main__":
    unittest.main()
