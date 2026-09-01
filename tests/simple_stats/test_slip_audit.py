"""Pricing a slip against the market, and the 2026-08-30/31 ledger it came from.

The regression at the bottom is the point of this file. Twenty bets were placed
off the operator's screen across those two days; thirteen can be priced against
bzzoiro's consensus. ``test_ledger_separates_priced_bets_from_the_rest`` asserts
that the audit takes exactly two of them -- and that both winners it refuses
stay refused. A test that only checked the losers would pass on a rule that
simply says "no", which is the failure mode this whole module exists to avoid.
"""
import math

import pytest

from bet.simple_stats.slip_audit import (
    FIRST_HALF_GOAL_SHARE,
    MINIMUM_EDGE,
    RANGE_MARKETS,
    audit_leg,
    expected_value,
    fit_match_lambdas,
    half_lambdas,
    implied_probability,
    poisson_pmf,
    probability_team_scores,
    range_market_ceiling,
    redundant_legs,
    remove_vig,
    slip_price_floor,
)

# --- the arithmetic ---------------------------------------------------------


def test_implied_probability_is_the_raw_price_not_a_devigged_one():
    assert implied_probability(2.0) == pytest.approx(0.5)
    assert implied_probability(1.42) == pytest.approx(0.7042, abs=1e-4)


@pytest.mark.parametrize("price", [1.0, 0.9, -2.0])
def test_a_price_at_or_below_evens_is_not_odds(price):
    with pytest.raises(ValueError):
        implied_probability(price)


def test_devigging_needs_the_whole_market():
    with pytest.raises(ValueError, match="complete market"):
        remove_vig(1.85)


def test_remove_vig_normalises_to_one():
    probabilities = remove_vig(2.21, 3.58, 3.05)
    assert sum(probabilities) == pytest.approx(1.0)
    # Monaco were favourites; devigging must not reorder the market.
    assert probabilities[0] > probabilities[2] > probabilities[1]


def test_devigged_probability_is_always_below_the_raw_price_implied_one():
    """The asymmetry that makes comparing a raw implied number to a modelled one
    flatter every bet. Asserted rather than described because the whole ledger
    below turns on it."""
    prices = (2.21, 3.58, 3.05)
    for devigged, price in zip(remove_vig(*prices), prices):
        assert devigged < implied_probability(price)


def test_poisson_pmf_sums_to_one_over_the_grid():
    assert sum(poisson_pmf(k, 1.35) for k in range(30)) == pytest.approx(1.0)


def test_second_half_carries_more_goals_than_the_first():
    """Measured, not assumed -- and an even split would misprice every
    first-half market in the range table."""
    assert 0.40 < FIRST_HALF_GOAL_SHARE < 0.50
    first, second = half_lambdas(3.0)
    assert first < second
    assert first + second == pytest.approx(3.0)


# --- fitting the market -----------------------------------------------------

# bzzoiro consensus for Lecce - AS Roma, event 210073, taken 2026-08-31T16:08Z.
LECCE_ROMA_ODDS = dict(
    home_win=7.47, draw=4.23, away_win=1.45, over_25=2.01, under_25=1.81
)


def test_fit_recovers_a_lopsided_match():
    lam_home, lam_away = fit_match_lambdas(**LECCE_ROMA_ODDS)
    assert lam_away > lam_home  # Roma at 1.45 were not the quiet side
    assert lam_home + lam_away == pytest.approx(2.56, abs=0.10)


def test_fit_reproduces_the_prices_it_was_given():
    lam_home, lam_away = fit_match_lambdas(**LECCE_ROMA_ODDS)
    target = remove_vig(
        LECCE_ROMA_ODDS["home_win"],
        LECCE_ROMA_ODDS["draw"],
        LECCE_ROMA_ODDS["away_win"],
    )
    home = draw = 0.0
    for i in range(12):
        for j in range(12):
            p = poisson_pmf(i, lam_home) * poisson_pmf(j, lam_away)
            if i > j:
                home += p
            elif i == j:
                draw += p
    assert home == pytest.approx(target[0], abs=0.05)
    assert draw == pytest.approx(target[1], abs=0.05)


def test_totals_line_is_optional_but_moves_the_match_rate():
    without = sum(fit_match_lambdas(home_win=2.21, draw=3.58, away_win=3.05))
    with_totals = sum(
        fit_match_lambdas(
            home_win=2.21, draw=3.58, away_win=3.05, over_25=1.59, under_25=2.37
        )
    )
    assert without != pytest.approx(with_totals, abs=0.01)


def test_probability_team_scores_is_monotone_in_the_rate():
    assert probability_team_scores(0.9) < probability_team_scores(1.4)
    assert probability_team_scores(1.22) == pytest.approx(0.705, abs=0.005)


# --- the range markets and their ceilings -----------------------------------


def test_each_half_one_to_three_cannot_beat_fifty_two_percent():
    """The most reusable number here: no fixture makes this market a favourite,
    so a price under its floor is refusable before any team is named."""
    ceiling, at_lambda, floor = range_market_ceiling("each_half_1_3")
    assert ceiling == pytest.approx(0.520, abs=0.005)
    assert at_lambda == pytest.approx(3.6, abs=0.15)
    assert floor == pytest.approx(1.92, abs=0.02)


def test_the_first_half_range_builder_has_the_same_shape():
    ceiling, _, floor = range_market_ceiling("1h_over_0_5_under_2_5_and_2h_over_0_5")
    assert ceiling == pytest.approx(0.505, abs=0.005)
    assert floor == pytest.approx(1.98, abs=0.02)


@pytest.mark.parametrize("key", sorted(RANGE_MARKETS))
def test_range_markets_fall_away_on_both_sides_of_their_peak(key):
    """Two-sided is what makes them different from an over: a dull match fails
    the lower bound and a wild one fails the upper, so 'the goals will flow' is
    not an argument for taking one."""
    market = RANGE_MARKETS[key]
    _, peak, _ = range_market_ceiling(key)
    assert market.probability(peak * 0.4) < market.probability(peak)
    assert market.probability(peak * 2.2) < market.probability(peak)


def test_one_to_three_in_each_half_makes_a_two_to_six_total_leg_redundant():
    assert redundant_legs(["each_half_1_3", "total_2_6"]) == [
        ("each_half_1_3", "total_2_6")
    ]


def test_redundancy_spotter_is_quiet_on_legs_it_knows_nothing_about():
    assert redundant_legs(["each_half_1_3", "corners_total_over_8_5"]) == []


# --- the slip floor ---------------------------------------------------------


def test_slip_price_floor_is_the_weakest_leg():
    assert slip_price_floor([0.67, 0.85, 0.80]) == pytest.approx(1.493, abs=0.001)


def test_a_slip_priced_at_its_floor_carries_its_other_legs_for_nothing():
    """The 2026-08-31 Lecce three-leg builder, exactly. Coulibaly to commit a
    foul was 20 of his last 30 starts; the builder paid 1.50 against a floor of
    1.49, so the Malen and Falcone legs were worth one Polish grosz between
    them."""
    coulibaly = 20 / 30
    assert slip_price_floor([coulibaly, 0.86, 0.78]) == pytest.approx(1.50, abs=0.01)


def test_slip_floor_rejects_an_empty_slip():
    with pytest.raises(ValueError):
        slip_price_floor([])


# --- audit_leg --------------------------------------------------------------


def test_expected_value_is_zero_at_fair_odds():
    assert expected_value(2.0, 0.5) == pytest.approx(0.0)


def test_audit_takes_a_price_above_fair():
    verdict = audit_leg(label="x", price=1.73, fair_probability=0.676)
    assert verdict.verdict == "TAKE"
    assert verdict.edge > MINIMUM_EDGE
    assert verdict.fair_odds == pytest.approx(1.479, abs=0.005)


def test_audit_calls_a_hair_of_edge_marginal_rather_than_a_bet():
    verdict = audit_leg(label="x", price=1.42, fair_probability=0.71)
    assert verdict.verdict == "MARGINAL"
    assert "noise" in verdict.reason


def test_audit_rejects_a_price_below_fair_and_says_both_numbers():
    verdict = audit_leg(label="x", price=1.42, fair_probability=0.643)
    assert verdict.verdict == "REJECT"
    assert "70.4%" in verdict.reason and "64.3%" in verdict.reason


# --- the ledger -------------------------------------------------------------

# Every football bet placed on 2026-08-30/31 that bzzoiro can price, with the
# fair probability derived from its consensus block (team-to-score legs and
# range builders) or from a Wilson lower bound on a real sample (the two
# counting-stat legs, whose markets the odds feed does not carry).
#
# (label, price, fair_probability, settled)
LEDGER = [
    ("Napoli-Como: SOT>6.5 + goals>1.5 + corners>7.5", 2.75, 0.3857, "WIN"),
    ("Osasuna-Getafe: Getafe fouls >12.5", 1.73, 0.676, "WIN"),
    ("Inter Turku-KuPS: KuPS to score", 1.42, 0.703, "LOSS"),
    ("Widzew-Lech: goals >2.5 + X2", 2.67, 0.366, "WIN"),
    ("Kobenhavn-Sonderjyske: Sonderjyske to score", 1.60, 0.605, "WIN"),
    ("Djurgarden-Mjallby: Mjallby to score", 1.48, 0.647, "LOSS"),
    ("Osasuna-Getafe: Osasuna to score", 1.40, 0.680, "WIN"),
    ("GAIS-Brommapojkarna: Brommapojkarna to score", 1.43, 0.643, "LOSS"),
    ("Rakow-Jagiellonia: Jagiellonia score + corners >3.5", 2.42, 0.386, "WIN"),
    ("Lecce-Roma: 1H o0.5 + 1H u2.5 + 2H o0.5", 2.05, 0.434, "LOSS"),
    ("Besiktas-Corum: Besiktas corners >4.5", 1.42, 0.436, "WIN"),
    ("Lecce-Roma: Malen SOT + Coulibaly foul + Falcone saves", 1.50, 0.450, "LOSS"),
    ("Monaco-Marseille: both teams corners >3.5 + BTTS", 3.45, 0.185, "LOSS"),
]

TAKEN = {
    "Napoli-Como: SOT>6.5 + goals>1.5 + corners>7.5",
    "Osasuna-Getafe: Getafe fouls >12.5",
}


@pytest.mark.parametrize("label,price,fair,settled", LEDGER)
def test_ledger_verdicts(label, price, fair, settled):
    verdict = audit_leg(label=label, price=price, fair_probability=fair)
    assert (verdict.verdict == "TAKE") is (label in TAKEN), (
        f"{label}: {verdict.verdict} at edge {verdict.edge:+.1%} (settled {settled})"
    )


def test_ledger_separates_priced_bets_from_the_rest():
    verdicts = {
        label: audit_leg(label=label, price=price, fair_probability=fair)
        for label, price, fair, _ in LEDGER
    }
    taken = {label for label, v in verdicts.items() if v.verdict == "TAKE"}
    assert taken == TAKEN

    settled = {label: result for label, _, _, result in LEDGER}
    # Both bets worth taking won. That is the encouraging half.
    assert all(settled[label] == "WIN" for label in taken)
    # Five of the refused bets also won, and refusing them is still correct --
    # this is the assertion that stops the rule collapsing into hindsight.
    refused_winners = [
        label
        for label, v in verdicts.items()
        if v.verdict != "TAKE" and settled[label] == "WIN"
    ]
    assert len(refused_winners) == 5


def test_every_team_to_score_leg_on_the_ledger_was_priced_at_or_below_fair():
    """The concentration that cost the day: five bets in one market, none of
    them paying more than the consensus said they were worth."""
    legs = [row for row in LEDGER if "to score" in row[0]]
    assert len(legs) == 5
    for label, price, fair, _ in legs:
        verdict = audit_leg(label=label, price=price, fair_probability=fair)
        assert verdict.edge < MINIMUM_EDGE


def test_the_range_builders_were_below_their_own_market_ceiling_floor():
    """Both were refusable on the ceiling alone, before the fixture was read."""
    _, _, floor = range_market_ceiling("1h_over_0_5_under_2_5_and_2h_over_0_5")
    lecce_price = 2.05
    assert lecce_price > floor  # it clears the crude floor ...
    fair = next(fair for label, _, fair, _ in LEDGER if "1H o0.5" in label)
    assert 1.0 / fair > lecce_price  # ... and still is not worth its price
    assert math.isclose(1.0 / fair, 2.30, abs_tol=0.02)
