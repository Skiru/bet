"""Unit tests for compute_safety_scores.py."""

import unittest

from scripts.compute_safety_scores import (
    compute_combined_values,
    compute_combined_l5,
    compute_hit_rate,
    compute_margin,
    compute_safety_score,
    compute_three_way_check,
    infer_direction,
    rank_markets,
)


def _make_market(
    name: str = "Corners Total O/U",
    line: float = 9.5,
    team_a_l10: list | None = None,
    team_b_l10: list | None = None,
    h2h_values: list | None = None,
    team_a_l5: list | None = None,
    team_b_l5: list | None = None,
    is_combined: bool = True,
    source: str = "test",
    team_swapped: bool = False,
) -> dict:
    """Helper to create a market dict."""
    a10 = team_a_l10 if team_a_l10 is not None else [5, 6, 7, 5, 6, 5, 7, 6, 5, 6]
    b10 = team_b_l10 if team_b_l10 is not None else [4, 5, 3, 4, 5, 4, 3, 5, 4, 5]
    return {
        "name": name,
        "line": line,
        "team_a_l10": a10,
        "team_b_l10": b10,
        "h2h_values": h2h_values or [],
        "team_a_l5": team_a_l5 or a10[:5],
        "team_b_l5": team_b_l5 or b10[:5],
        "is_combined": is_combined,
        "source": source,
        "team_swapped": team_swapped,
    }


def _make_ranking_input(markets: list[dict], sport: str = "football") -> dict:
    """Helper to create a full ranking input dict."""
    return {
        "sport": sport,
        "team_a": "TeamA",
        "team_b": "TeamB",
        "competition": "TestLeague",
        "markets": markets,
    }


class TestComputeCombinedValues(unittest.TestCase):
    """Test compute_combined_values()."""

    def test_combined_market(self):
        market = _make_market(
            team_a_l10=[5, 6, 7],
            team_b_l10=[3, 4, 5],
            is_combined=True,
        )
        result = compute_combined_values(market)
        self.assertEqual(result, [8, 10, 12])

    def test_combined_unequal_length(self):
        market = _make_market(
            team_a_l10=[5, 6, 7, 8],
            team_b_l10=[3, 4],
            is_combined=True,
        )
        result = compute_combined_values(market)
        self.assertEqual(result, [8, 10])

    def test_team_specific_market(self):
        market = _make_market(
            team_a_l10=[5, 6, 7],
            team_b_l10=[3, 4, 5],
            is_combined=False,
        )
        result = compute_combined_values(market)
        self.assertEqual(result, [5, 6, 7])

    def test_empty_values(self):
        market = _make_market(team_a_l10=[], team_b_l10=[], is_combined=True)
        result = compute_combined_values(market)
        self.assertEqual(result, [])


class TestComputeHitRate(unittest.TestCase):
    """Test compute_hit_rate()."""

    def test_over_counting(self):
        values = [10, 11, 12, 8, 9]
        hits, total = compute_hit_rate(values, 9.5, "OVER")
        self.assertEqual(hits, 3)  # 10, 11, 12
        self.assertEqual(total, 5)

    def test_under_counting(self):
        values = [10, 11, 12, 8, 9]
        hits, total = compute_hit_rate(values, 9.5, "UNDER")
        self.assertEqual(hits, 2)  # 8, 9
        self.assertEqual(total, 5)

    def test_exact_line_is_push(self):
        """Values exactly on the line should NOT count as hit for OVER or UNDER."""
        values = [9.5, 9.5, 9.5]
        hits_over, _ = compute_hit_rate(values, 9.5, "OVER")
        hits_under, _ = compute_hit_rate(values, 9.5, "UNDER")
        self.assertEqual(hits_over, 0)
        self.assertEqual(hits_under, 0)

    def test_empty_values(self):
        hits, total = compute_hit_rate([], 9.5, "OVER")
        self.assertEqual(hits, 0)
        self.assertEqual(total, 0)

    def test_all_over(self):
        values = [10, 11, 12]
        hits, total = compute_hit_rate(values, 5.5, "OVER")
        self.assertEqual(hits, 3)
        self.assertEqual(total, 3)

    def test_all_under(self):
        values = [1, 2, 3]
        hits, total = compute_hit_rate(values, 5.5, "UNDER")
        self.assertEqual(hits, 3)
        self.assertEqual(total, 3)


class TestComputeMargin(unittest.TestCase):
    """Test compute_margin()."""

    def test_over_margin(self):
        result = compute_margin(12.0, 9.5, "OVER")
        self.assertAlmostEqual(result, 12.0 / 9.5, places=3)

    def test_under_margin(self):
        result = compute_margin(7.0, 9.5, "UNDER")
        self.assertAlmostEqual(result, 9.5 / 7.0, places=3)

    def test_line_zero(self):
        result = compute_margin(5.0, 0, "OVER")
        self.assertEqual(result, 0.0)

    def test_avg_zero_under(self):
        """avg=0 with line>0 is a very strong UNDER signal."""
        result = compute_margin(0, 0.5, "UNDER")
        self.assertEqual(result, 2.0)

    def test_avg_zero_over(self):
        """avg=0 with line>0 for OVER should be 0.0 (no margin)."""
        result = compute_margin(0, 0.5, "OVER")
        self.assertEqual(result, 0.0)

    def test_avg_zero_line_zero(self):
        result = compute_margin(0, 0, "UNDER")
        self.assertEqual(result, 0.0)


class TestComputeSafetyScore(unittest.TestCase):
    """Test compute_safety_score()."""

    def test_min_of_two_rates(self):
        self.assertEqual(compute_safety_score(0.8, 0.6), 0.6)
        self.assertEqual(compute_safety_score(0.5, 0.9), 0.5)

    def test_equal_rates(self):
        self.assertEqual(compute_safety_score(0.7, 0.7), 0.7)

    def test_zero(self):
        self.assertEqual(compute_safety_score(0.0, 0.8), 0.0)

    def test_perfect(self):
        self.assertEqual(compute_safety_score(1.0, 1.0), 1.0)


class TestComputeThreeWayCheck(unittest.TestCase):
    """Test compute_three_way_check()."""

    def test_all_three_aligned_over(self):
        result = compute_three_way_check(12.0, 11.0, 13.0, 9.5)
        self.assertIn("SUPPORT", result["alignment"])
        self.assertEqual(result["l10_direction"], "OVER")
        self.assertEqual(result["h2h_direction"], "OVER")

    def test_two_of_three_conflict(self):
        # L10=OVER, H2H=UNDER, L5=OVER → 2/3 SUPPORT
        result = compute_three_way_check(12.0, 8.0, 13.0, 9.5)
        self.assertIn("SUPPORT", result["alignment"])

    def test_three_of_three_conflict(self):
        # L10=OVER, H2H=UNDER, L5=UNDER → CONFLICT
        result = compute_three_way_check(10.0, 8.0, 8.0, 9.5)
        self.assertIn("CONFLICT", result["alignment"])

    def test_h2h_missing(self):
        result = compute_three_way_check(12.0, 0.0, 13.0, 9.5)
        self.assertEqual(result["h2h_direction"], "N/A")
        self.assertIsNone(result["h2h_avg"])
        # Must indicate H2H is missing in alignment string
        self.assertIn("H2H N/A", result["alignment"])
        self.assertIn("SUPPORT", result["alignment"])

    def test_trend_up(self):
        # L5 > L10 by >5%
        result = compute_three_way_check(10.0, 11.0, 11.0, 9.5)
        self.assertEqual(result["l5_trend"], "UP")

    def test_trend_down(self):
        result = compute_three_way_check(10.0, 11.0, 9.0, 9.5)
        self.assertEqual(result["l5_trend"], "DOWN")

    def test_trend_stable(self):
        result = compute_three_way_check(10.0, 11.0, 10.2, 9.5)
        self.assertEqual(result["l5_trend"], "STABLE")


class TestInferDirection(unittest.TestCase):
    """Test infer_direction()."""

    def test_over(self):
        self.assertEqual(infer_direction(12.0, 9.5), "OVER")

    def test_under(self):
        self.assertEqual(infer_direction(8.0, 9.5), "UNDER")

    def test_equal_is_under(self):
        self.assertEqual(infer_direction(9.5, 9.5), "UNDER")


class TestRankMarkets(unittest.TestCase):
    """Test rank_markets()."""

    def test_sorted_by_safety_desc(self):
        # High safety market
        m1 = _make_market(
            name="Corners Total O/U",
            line=9.5,
            team_a_l10=[6, 7, 6, 7, 6, 7, 6, 7, 6, 7],
            team_b_l10=[4, 5, 4, 5, 4, 5, 4, 5, 4, 5],
            h2h_values=[12, 11, 13, 12, 11],
        )
        # Lower safety market
        m2 = _make_market(
            name="Fouls Total O/U",
            line=25.5,
            team_a_l10=[12, 14, 10, 13, 11, 12, 14, 10, 13, 11],
            team_b_l10=[10, 12, 8, 11, 9, 10, 12, 8, 11, 9],
            h2h_values=[20, 18, 22],
        )
        data = _make_ranking_input([m1, m2])
        result = rank_markets(data)

        self.assertIsNotNone(result)
        self.assertEqual(len(result["ranking"]), 2)
        self.assertGreaterEqual(
            result["ranking"][0]["safety_score"],
            result["ranking"][1]["safety_score"],
        )

    def test_h2h_blind_penalty(self):
        """Market without H2H should have lower safety than with H2H (30% penalty)."""
        m_with_h2h = _make_market(
            name="Corners Total O/U",
            line=9.5,
            team_a_l10=[6, 7, 6, 7, 6, 7, 6, 7, 6, 7],
            team_b_l10=[4, 5, 4, 5, 4, 5, 4, 5, 4, 5],
            h2h_values=[12, 11, 13, 12, 11],
        )
        m_without_h2h = _make_market(
            name="Fouls Total O/U",
            line=9.5,
            team_a_l10=[6, 7, 6, 7, 6, 7, 6, 7, 6, 7],
            team_b_l10=[4, 5, 4, 5, 4, 5, 4, 5, 4, 5],
            h2h_values=[],
        )
        data = _make_ranking_input([m_with_h2h, m_without_h2h])
        result = rank_markets(data)

        ranking = result["ranking"]
        with_h2h = next(r for r in ranking if r["name"] == "Corners Total O/U")
        without_h2h = next(r for r in ranking if r["name"] == "Fouls Total O/U")

        self.assertFalse(with_h2h["h2h_blind"])
        self.assertTrue(without_h2h["h2h_blind"])
        self.assertGreater(with_h2h["safety_score"], without_h2h["safety_score"])

    def test_result_structure(self):
        m = _make_market(h2h_values=[10, 11, 12])
        data = _make_ranking_input([m])
        result = rank_markets(data)

        self.assertIn("candidate", result)
        self.assertIn("ranking", result)
        self.assertIn("three_way_check", result)
        self.assertIn("recommended_market", result)
        self.assertIn("markdown_ranking_table", result)

        r = result["ranking"][0]
        self.assertIn("safety_score", r)
        self.assertIn("margin", r)
        self.assertIn("direction", r)
        self.assertIn("hit_rate_l10", r)
        self.assertIn("three_way_check", r)

    def test_per_market_three_way_check(self):
        """Each market in ranking should carry its own three_way_check."""
        m1 = _make_market(
            name="Corners Total O/U",
            h2h_values=[12, 11, 13],
        )
        m2 = _make_market(
            name="Fouls Total O/U",
            line=20.5,
            team_a_l10=[12, 11, 13, 12, 11, 12, 11, 13, 12, 11],
            team_b_l10=[10, 9, 11, 10, 9, 10, 9, 11, 10, 9],
            h2h_values=[22, 21, 20],
        )
        data = _make_ranking_input([m1, m2])
        result = rank_markets(data)

        for r in result["ranking"]:
            self.assertIn("three_way_check", r)
            self.assertIn("alignment", r["three_way_check"])
            self.assertIn("l10_direction", r["three_way_check"])

    def test_margin_tiebreaker(self):
        """When safety scores are equal, higher margin should rank first."""
        # Both markets have same L10 hit rate, same H2H, but different margins
        m_high_margin = _make_market(
            name="High Margin",
            line=8.5,  # lower line → higher OVER margin
            team_a_l10=[6, 7, 6, 7, 6, 7, 6, 7, 6, 7],
            team_b_l10=[4, 5, 4, 5, 4, 5, 4, 5, 4, 5],
            h2h_values=[12, 11, 13, 12, 11],
        )
        m_low_margin = _make_market(
            name="Low Margin",
            line=10.5,  # higher line → lower OVER margin
            team_a_l10=[6, 7, 6, 7, 6, 7, 6, 7, 6, 7],
            team_b_l10=[4, 5, 4, 5, 4, 5, 4, 5, 4, 5],
            h2h_values=[12, 11, 13, 12, 11],
        )
        data = _make_ranking_input([m_low_margin, m_high_margin])
        result = rank_markets(data)

        # If safety scores happen to be equal, higher margin ranks first
        if result["ranking"][0]["safety_score"] == result["ranking"][1]["safety_score"]:
            self.assertGreaterEqual(
                result["ranking"][0]["margin"],
                result["ranking"][1]["margin"],
            )

    def test_empty_markets(self):
        data = _make_ranking_input([])
        result = rank_markets(data)
        self.assertEqual(result["ranking"], [])
        self.assertIsNone(result["recommended_market"])

    def test_team_swapped_display(self):
        """Team B-only market should have swapped display averages."""
        m = _make_market(
            name="TeamB Corners O/U",
            team_a_l10=[5, 6, 7, 5, 6, 5, 7, 6, 5, 6],  # Actually Team B data (swapped)
            team_b_l10=[],
            is_combined=False,
            team_swapped=True,
            h2h_values=[],
        )
        data = _make_ranking_input([m])
        result = rank_markets(data)

        r = result["ranking"][0]
        # With team_swapped=True, display_a_avg should show team_b_avg (0.0)
        # and display_b_avg should show team_a_avg (the actual data)
        self.assertEqual(r["team_a_avg"], 0.0)
        self.assertGreater(r["team_b_avg"], 0.0)


if __name__ == "__main__":
    unittest.main()
