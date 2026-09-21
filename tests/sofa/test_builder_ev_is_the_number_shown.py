"""Two defects that both said "EV" and meant something else.

Neither was visible in the artifact. `08_confidence.json` carried the right
numbers in both cases; what was wrong was which of them the builder *chose*
and which one the PDF *printed*. A reader comparing the JSON against the PDF
would have found them; nobody does that, which is why they lasted.
"""

import pytest

from bet.sofa.confidence import (
    BUILDER_CORRELATION_HAIRCUT,
    best_leg_per_quantity,
    displayed_ev,
    quantity_family,
)


def _leg(market: str, leg_ev: float, confidence: float) -> dict:
    return {"market": market, "leg_ev": leg_ev, "confidence": confidence,
            "line": 2.5, "direction": "OVER", "offered_odds": 1.5}


class TestTheFamilyRepresentative:
    """A builder takes one leg per quantity, so this choice bounds the ranking.

    Ranking the pool by EV is worth nothing if the pool was assembled by
    price. Fixing only the cross-family sort left the defect alive one level
    down, which is where it had always done the damage.
    """

    def test_the_representative_is_the_ev_positive_leg_not_the_short_one(self):
        """The exact inversion: highest confidence, lowest EV.

        `goals_total` at 0.91 confidence is the shorter price and the worse
        bet. Choosing by confidence took it and discarded a leg worth eight
        times as much.
        """
        best = best_leg_per_quantity([
            _leg("goals_total", leg_ev=0.01, confidence=0.91),
            _leg("goals_for", leg_ev=0.08, confidence=0.82),
        ])
        assert list(best) == ["goals"]
        assert best["goals"]["market"] == "goals_for"

    def test_a_negative_ev_leg_never_represents_a_family_that_has_a_positive_one(self):
        best = best_leg_per_quantity([
            _leg("corners_total", leg_ev=-0.04, confidence=0.93),
            _leg("corners_1h_total", leg_ev=0.02, confidence=0.81),
        ])
        assert best["corners"]["leg_ev"] == pytest.approx(0.02)

    def test_families_stay_separate(self):
        """One representative per quantity, and quantities do not merge.

        `goals_for` and `goals_total` are one quantity counted twice (measured
        lambda 2.165); goals and corners are not (0.95-1.02).
        """
        best = best_leg_per_quantity([
            _leg("goals_total", 0.05, 0.85),
            _leg("goals_for", 0.03, 0.88),
            _leg("corners_total", 0.02, 0.84),
            _leg("cards_points_total", 0.01, 0.83),
        ])
        assert set(best) == {"goals", "corners", "cards"}
        assert best["goals"]["market"] == "goals_total"

    def test_games_sets_and_handicap_games_are_one_tennis_family(self):
        """A short tennis match settles every UNDER at once."""
        assert quantity_family("games_total") == quantity_family("sets_total")
        assert quantity_family("handicap_games") == quantity_family("games_total")
        best = best_leg_per_quantity([
            _leg("games_total", 0.01, 0.90),
            _leg("sets_total", 0.06, 0.83),
            _leg("handicap_games", 0.02, 0.87),
        ])
        assert list(best) == ["games"]
        assert best["games"]["market"] == "sets_total"

    def test_an_empty_group_produces_no_representative(self):
        assert best_leg_per_quantity([]) == {}


class TestTheNumberThePdfPrints:
    """The PDF page says "EV liczone jest od tej ceny" — the post-haircut one.

    It printed the product EV instead, because the variable holding the key
    was named `key` and a per-leg loop rebound `key` to a tuple. A loop
    variable outlives its loop, so `b.get(key, b.get("ev_if_product_priced"))`
    missed on a tuple and took the fallback every time.
    """

    def test_the_haircut_ev_wins_whenever_it_exists(self):
        """+0.02 is a thin slip worth taking; +0.159 is a different claim."""
        assert displayed_ev(
            {"ev_after_haircut": 0.02, "ev_if_product_priced": 0.159}
        ) == pytest.approx(0.02)

    def test_a_negative_haircut_ev_is_not_treated_as_missing(self):
        """The case that matters most: the haircut turned the slip negative.

        `0.0` and a negative value are both falsy-adjacent traps for a
        `or`-style fallback. A slip the haircut killed must print as killed.
        """
        assert displayed_ev(
            {"ev_after_haircut": -0.0916, "ev_if_product_priced": 0.0322}
        ) == pytest.approx(-0.0916)
        assert displayed_ev(
            {"ev_after_haircut": 0.0, "ev_if_product_priced": 0.0322}
        ) == pytest.approx(0.0)

    def test_an_artifact_predating_the_haircut_falls_back(self):
        """The fallback is legitimate, and it is why the bug was invisible."""
        assert displayed_ev({"ev_if_product_priced": 0.0322}) == pytest.approx(0.0322)

    def test_the_printed_ev_matches_the_haircut_arithmetic(self):
        """Ties the displayed number to the price the operator can get.

        p * (product * (1 - haircut)) - 1, not p * product - 1.
        """
        p, product = 0.7331, 1.41
        after = product * (1.0 - BUILDER_CORRELATION_HAIRCUT)
        builder = {
            "combined_probability": p,
            "odds_if_product": product,
            "ev_if_product_priced": round(p * product - 1.0, 4),
            "ev_after_haircut": round(p * after - 1.0, 4),
        }
        assert displayed_ev(builder) == pytest.approx(p * after - 1.0, abs=1e-4)
        assert displayed_ev(builder) < builder["ev_if_product_priced"]
