"""The devig, and the bias the proportional one carried (F51).

Measured on 2026-09-18: of that day's rungs that were both priced by Superbet
and settled from Sofascore (2,354 of them), the proportional devig said 0.158
for the band that won 0.087, and 0.842 for the band that won 0.913. Seven
points of overstatement on the long shot, seven of understatement on the
favourite.

That number is `market_p`, and `market_p` is both what `bar_probability`
shrinks the sample toward and what `edge` is measured against — so the bias
pushed every long shot's bar down and every favourite's bar up. On that day's
sheet the effect was total: 654 VALUE rows, not one of them above market_p
0.635, and 1,752 priced rows at market_p >= 0.70 that could not qualify under
any price.
"""

import pytest

from bet.sofa.engine import devig


def test_a_devigged_pair_is_a_distribution():
    for over, under in ((1.33, 3.10), (1.90, 1.90), (15.0, 1.02), (1.07, 6.5)):
        p_over, p_under = devig(over, under)
        assert p_over + p_under == pytest.approx(1.0, abs=1e-9)
        assert 0.0 < p_over < 1.0
        assert 0.0 < p_under < 1.0


def test_devigging_never_raises_a_probability_above_its_own_price():
    """The margin comes out; it is never added to a side."""
    for over, under in ((1.33, 3.10), (15.0, 1.02), (1.07, 6.5), (2.10, 1.80)):
        p_over, p_under = devig(over, under)
        assert p_over <= 1.0 / over + 1e-12
        assert p_under <= 1.0 / under + 1e-12


def test_a_symmetric_price_devigs_to_a_half_whatever_the_margin():
    for price in (1.90, 1.95, 2.00, 1.50):
        assert devig(price, price)[0] == pytest.approx(0.5, abs=1e-9)


def test_devigging_keeps_the_market_order():
    p_over, p_under = devig(1.33, 3.10)
    assert p_over > p_under


def test_the_power_devig_takes_more_margin_off_the_long_shot():
    """The whole point of the change, stated as an inequality.

    Proportional devigging removes the same *relative* share from both sides.
    Bookmakers load the margin onto the long shot, so the correct devig has to
    remove more of it there — which is to say the long shot's probability must
    come out lower than proportional says, and the favourite's higher.
    """
    long_shot_price, favourite_price = 15.0, 1.02
    power_long, power_fav = devig(long_shot_price, favourite_price)
    prop_long, prop_fav = devig(long_shot_price, favourite_price, method="proportional")

    assert power_long < prop_long
    assert power_fav > prop_fav
    # And not by a rounding amount: on this rung proportional claims the long
    # shot is more than twice as likely as it is.
    assert prop_long / power_long > 2.0


def test_the_correction_grows_with_how_lopsided_the_price_is():
    """Holding the margin fixed, a more lopsided rung is corrected harder.

    The overround has to be held constant to see this. Real rungs vary in both
    at once — 1.02/15.00 is more lopsided than 1.07/6.50 but carries a smaller
    margin (1.047 against 1.088), so its absolute correction is smaller. That
    is the margin talking, not the shape.
    """
    overround = 1.06
    gaps = []
    for q_over in (0.53, 0.65, 0.80, 0.92):
        q_under = overround - q_over
        power, _ = devig(1.0 / q_over, 1.0 / q_under)
        prop, _ = devig(1.0 / q_over, 1.0 / q_under, method="proportional")
        gaps.append(round(power - prop, 12))
    assert gaps == sorted(gaps), "a more lopsided rung must be corrected harder"
    assert gaps[0] >= 0.0


def test_an_even_money_rung_is_left_alone_by_both_methods():
    assert devig(1.90, 1.90) == pytest.approx(
        devig(1.90, 1.90, method="proportional"), abs=1e-9
    )


@pytest.mark.parametrize(
    ("over", "under"),
    [(1.9, None), (None, 1.9), (None, None), (1.0, 3.0), (0.5, 3.0), (3.0, 1.0)],
)
def test_an_impossible_or_incomplete_price_is_refused_not_guessed(over, under):
    assert devig(over, under) is None


# --- markets wider than two -----------------------------------------------


def test_a_three_way_market_devigs_to_a_distribution():
    from bet.sofa.engine import devig_many

    probs = devig_many([1 / 2.10, 1 / 3.40, 1 / 3.60])
    assert probs is not None
    assert sum(probs) == pytest.approx(1.0, abs=1e-9)
    assert probs == sorted(probs, reverse=True), "order must survive"


def test_the_three_way_devig_is_the_same_estimator_as_the_two_way():
    """A "most corners" market is not a different kind of price.

    Devigging it proportionally while devigging over/under by power would
    leave the bias in the one family that has no ladder check behind it.
    """
    from bet.sofa.engine import devig_many

    pair = devig(1.33, 3.10)
    wide = devig_many([1 / 1.33, 1 / 3.10])
    assert wide == pytest.approx(list(pair), abs=1e-12)


def test_the_three_way_long_shot_comes_out_below_proportional():
    from bet.sofa.engine import devig_many

    implied = [1 / 1.20, 1 / 9.00, 1 / 15.00]
    power = devig_many(implied)
    proportional = devig_many(implied, method="proportional")
    assert power[0] > proportional[0]
    assert power[1] < proportional[1]
    assert power[2] < proportional[2]


@pytest.mark.parametrize(
    "implied", [[0.5], [], [1.5, 0.2], [0.4, 0.0], [0.4, -0.1], [1.0, 0.2]]
)
def test_an_incomplete_or_impossible_wide_market_is_refused(implied):
    from bet.sofa.engine import devig_many

    assert devig_many(implied) is None


def test_the_solver_brackets_every_realistic_market():
    """The bisection runs on a fixed [0.05, 20] bracket; check it is enough.

    Swept over margins from none to 30% and shapes from even to 200:1, on
    markets two to four wide. A bracket that failed to contain the root would
    return a set that does not sum to one, and the renormalisation at the end
    would hide it — so the check is on the exponent's effect, not only the sum.
    """
    import random

    from bet.sofa.engine import devig_many

    rng = random.Random(20260918)
    for _ in range(2000):
        width = rng.choice([2, 2, 2, 3, 4])
        shares = [rng.uniform(0.005, 1.0) for _ in range(width)]
        total = sum(shares)
        margin = rng.uniform(0.0, 0.30)
        implied = [s / total * (1.0 + margin) for s in shares]
        if any(q <= 0.0 or q >= 1.0 for q in implied):
            continue
        probs = devig_many(implied)
        assert probs is not None
        assert sum(probs) == pytest.approx(1.0, abs=1e-9)
        # Order preserved, and every probability strictly under its raw price.
        assert [i for i, _ in sorted(enumerate(probs), key=lambda t: -t[1])] == [
            i for i, _ in sorted(enumerate(implied), key=lambda t: -t[1])
        ]
        if margin > 1e-6:
            assert all(p < q + 1e-9 for p, q in zip(probs, implied, strict=True))
