"""Unit tests for normalize_stats.py."""

import unittest

from scripts.normalize_stats import (
    NormalizedFixture,
    NormalizedMatchStats,
    SPORT_STAT_KEYS,
    SPORT_MARKETS,
    build_safety_score_input,
    _round_to_half,
    _extract_stat_values,
)


def _make_match(fixture_id: str, home: str, away: str, date: str, stats: dict) -> NormalizedMatchStats:
    """Helper to create a NormalizedMatchStats instance."""
    return NormalizedMatchStats(
        fixture_id=fixture_id,
        source="test",
        sport="football",
        home_team=home,
        away_team=away,
        date=date,
        stats=stats,
    )


def _make_football_matches(team: str, n: int = 10, corners_home: int = 5, corners_away: int = 3,
                           fouls_home: int = 12, fouls_away: int = 10) -> list[NormalizedMatchStats]:
    """Create N football matches with consistent stats."""
    matches = []
    for i in range(n):
        matches.append(_make_match(
            fixture_id=f"match-{team}-{i}",
            home=team,
            away=f"Opponent-{i}",
            date=f"2026-04-{20 - i:02d}",
            stats={
                "corners": {"home": corners_home + (i % 3), "away": corners_away + (i % 2)},
                "fouls": {"home": fouls_home, "away": fouls_away},
                "yellow_cards": {"home": 2, "away": 1},
                "shots": {"home": 14, "away": 10},
                "shots_on_target": {"home": 5, "away": 3},
                "goals": {"home": 1, "away": 1},
            },
        ))
    return matches


class TestNormalizedMatchStats(unittest.TestCase):
    """Test NormalizedMatchStats creation."""

    def test_creation(self):
        match = _make_match("f1", "Liverpool", "Arsenal", "2026-04-20", {"corners": {"home": 5, "away": 3}})
        self.assertEqual(match.fixture_id, "f1")
        self.assertEqual(match.source, "test")
        self.assertEqual(match.sport, "football")
        self.assertEqual(match.home_team, "Liverpool")
        self.assertEqual(match.stats["corners"]["home"], 5)

    def test_default_stats(self):
        match = NormalizedMatchStats(
            fixture_id="f1", source="test", sport="football",
            home_team="A", away_team="B", date="2026-04-20",
        )
        self.assertEqual(match.stats, {})


class TestNormalizedFixture(unittest.TestCase):
    """Test NormalizedFixture creation."""

    def test_creation(self):
        fixture = NormalizedFixture(
            fixture_id="f1", source="api-football", sport="football",
            competition="Premier League", home_team="Liverpool", away_team="Arsenal",
        )
        self.assertEqual(fixture.status, "scheduled")
        self.assertEqual(fixture.kickoff, "")


class TestRoundToHalf(unittest.TestCase):
    """Test line rounding."""

    def test_exact_half(self):
        self.assertEqual(_round_to_half(9.5), 9.5)

    def test_round_down(self):
        self.assertEqual(_round_to_half(9.2), 9.0)

    def test_round_up(self):
        self.assertEqual(_round_to_half(9.8), 10.0)

    def test_round_to_nearest_half(self):
        self.assertEqual(_round_to_half(9.3), 9.5)
        self.assertEqual(_round_to_half(9.7), 9.5)

    def test_integer(self):
        self.assertEqual(_round_to_half(10.0), 10.0)


class TestExtractStatValues(unittest.TestCase):
    """Test stat extraction from match lists."""

    def test_extract_home_corners(self):
        matches = _make_football_matches("TeamA", n=10, corners_home=5)
        values = _extract_stat_values(matches, "corners", "TeamA", last_n=10)
        self.assertEqual(len(values), 10)
        self.assertTrue(all(isinstance(v, float) for v in values))

    def test_extract_limited(self):
        matches = _make_football_matches("TeamA", n=10)
        values = _extract_stat_values(matches, "corners", "TeamA", last_n=5)
        self.assertEqual(len(values), 5)

    def test_missing_stat(self):
        matches = _make_football_matches("TeamA", n=5)
        values = _extract_stat_values(matches, "nonexistent", "TeamA")
        self.assertEqual(values, [])


class TestBuildSafetyScoreInput(unittest.TestCase):
    """Test build_safety_score_input output format."""

    def test_basic_output_format(self):
        team_a_matches = _make_football_matches("Liverpool", n=10, corners_home=6, corners_away=4)
        team_b_matches = _make_football_matches("Arsenal", n=10, corners_home=5, corners_away=3)
        h2h_matches = _make_football_matches("Liverpool", n=5, corners_home=7, corners_away=4)

        result = build_safety_score_input(
            sport="football",
            team_a="Liverpool",
            team_b="Arsenal",
            competition="Premier League",
            team_a_matches=team_a_matches,
            team_b_matches=team_b_matches,
            h2h_matches=h2h_matches,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["sport"], "football")
        self.assertEqual(result["team_a"], "Liverpool")
        self.assertEqual(result["team_b"], "Arsenal")
        self.assertEqual(result["competition"], "Premier League")
        self.assertIsInstance(result["markets"], list)
        self.assertTrue(len(result["markets"]) > 0)

    def test_market_structure(self):
        """Each market should have the fields compute_safety_scores.py expects."""
        team_a_matches = _make_football_matches("Liverpool", n=10)
        team_b_matches = _make_football_matches("Arsenal", n=10)

        result = build_safety_score_input(
            sport="football",
            team_a="Liverpool",
            team_b="Arsenal",
            competition="Premier League",
            team_a_matches=team_a_matches,
            team_b_matches=team_b_matches,
            h2h_matches=[],
        )

        self.assertIsNotNone(result)
        market = result["markets"][0]

        required_keys = ["name", "line", "team_a_l10", "team_b_l10",
                         "h2h_values", "team_a_l5", "team_b_l5",
                         "is_combined", "source"]
        for key in required_keys:
            self.assertIn(key, market, f"Missing key: {key}")

        self.assertIsInstance(market["line"], float)
        self.assertIsInstance(market["team_a_l10"], list)
        self.assertIsInstance(market["team_b_l10"], list)
        self.assertIsInstance(market["is_combined"], bool)

    def test_insufficient_team_a(self):
        """Should return None if team A has < 5 matches."""
        team_a_matches = _make_football_matches("Liverpool", n=3)
        team_b_matches = _make_football_matches("Arsenal", n=10)

        result = build_safety_score_input(
            sport="football",
            team_a="Liverpool",
            team_b="Arsenal",
            competition="PL",
            team_a_matches=team_a_matches,
            team_b_matches=team_b_matches,
            h2h_matches=[],
        )
        self.assertIsNone(result)

    def test_insufficient_team_b(self):
        """Should return None if team B has < 5 matches."""
        team_a_matches = _make_football_matches("Liverpool", n=10)
        team_b_matches = _make_football_matches("Arsenal", n=4)

        result = build_safety_score_input(
            sport="football",
            team_a="Liverpool",
            team_b="Arsenal",
            competition="PL",
            team_a_matches=team_a_matches,
            team_b_matches=team_b_matches,
            h2h_matches=[],
        )
        self.assertIsNone(result)

    def test_l5_is_subset_of_l10(self):
        """L5 should be the first 5 entries of L10."""
        team_a_matches = _make_football_matches("Liverpool", n=10)
        team_b_matches = _make_football_matches("Arsenal", n=10)

        result = build_safety_score_input(
            sport="football",
            team_a="Liverpool",
            team_b="Arsenal",
            competition="PL",
            team_a_matches=team_a_matches,
            team_b_matches=team_b_matches,
            h2h_matches=[],
        )

        self.assertIsNotNone(result)
        for market in result["markets"]:
            if market["team_a_l10"]:
                self.assertEqual(market["team_a_l5"], market["team_a_l10"][:5])
            if market["team_b_l10"]:
                self.assertEqual(market["team_b_l5"], market["team_b_l10"][:5])

    def test_line_auto_determination(self):
        """Line should be rounded to nearest 0.5 from L10 average."""
        # All matches have corners home=6, away=4 → combined avg ~10
        team_a_matches = _make_football_matches("Liverpool", n=10, corners_home=6, corners_away=0)
        team_b_matches = _make_football_matches("Arsenal", n=10, corners_home=0, corners_away=4)

        result = build_safety_score_input(
            sport="football",
            team_a="Liverpool",
            team_b="Arsenal",
            competition="PL",
            team_a_matches=team_a_matches,
            team_b_matches=team_b_matches,
            h2h_matches=[],
        )

        self.assertIsNotNone(result)
        # Find corners total market
        corners_market = next(m for m in result["markets"] if m["name"] == "Corners Total O/U")
        # Line should be a multiple of 0.5
        self.assertEqual(corners_market["line"] % 0.5, 0.0)

    def test_unknown_sport(self):
        """Unknown sport with no market definitions should return None."""
        team_a_matches = _make_football_matches("TeamA", n=10)
        team_b_matches = _make_football_matches("TeamB", n=10)

        result = build_safety_score_input(
            sport="curling",
            team_a="TeamA",
            team_b="TeamB",
            competition="WC",
            team_a_matches=team_a_matches,
            team_b_matches=team_b_matches,
            h2h_matches=[],
        )
        self.assertIsNone(result)

    def test_basketball_markets(self):
        """Basketball should produce point/rebound/assist markets."""
        matches_a = []
        matches_b = []
        for i in range(10):
            matches_a.append(_make_match(
                f"bball-a-{i}", "Lakers", f"Opp-{i}", f"2026-04-{20 - i:02d}",
                {"points": {"home": 110, "away": 105}, "rebounds": {"home": 45, "away": 40},
                 "assists": {"home": 25, "away": 22}},
            ))
            matches_b.append(_make_match(
                f"bball-b-{i}", f"Opp-{i}", "Celtics", f"2026-04-{20 - i:02d}",
                {"points": {"home": 108, "away": 103}, "rebounds": {"home": 42, "away": 38},
                 "assists": {"home": 23, "away": 20}},
            ))

        result = build_safety_score_input(
            sport="basketball",
            team_a="Lakers",
            team_b="Celtics",
            competition="NBA",
            team_a_matches=matches_a,
            team_b_matches=matches_b,
            h2h_matches=[],
        )

        self.assertIsNotNone(result)
        market_names = [m["name"] for m in result["markets"]]
        self.assertIn("Total Points O/U", market_names)


class TestSportMarketDefinitions(unittest.TestCase):
    """Test that market definitions cover key sports."""

    def test_football_has_stat_markets(self):
        names = [m["name"] for m in SPORT_MARKETS["football"]]
        self.assertIn("Corners Total O/U", names)
        self.assertIn("Fouls Total O/U", names)
        self.assertIn("Cards Total O/U", names)
        self.assertIn("Shots Total O/U", names)

    def test_basketball_has_stat_markets(self):
        names = [m["name"] for m in SPORT_MARKETS["basketball"]]
        self.assertIn("Total Points O/U", names)
        self.assertIn("Total Rebounds O/U", names)

    def test_hockey_has_stat_markets(self):
        names = [m["name"] for m in SPORT_MARKETS["hockey"]]
        self.assertIn("Total Goals O/U", names)
        self.assertIn("Total Shots O/U", names)


if __name__ == "__main__":
    unittest.main()
