"""Telling "missed the bar" apart from "could not have cleared it" (F52).

The operator asked why eight short-priced legs that all won were not on the
2026-09-18 coupon. Every one of them was in the sheet, correctly sampled,
correctly priced, and marked BELOW_BAR — the same word the sheet uses for a row
that missed by two per cent. Four of the eight could not have qualified at any
sample size, because `p_bar` is a blend with our estimate capped at P_CEILING
and the price sat under `margin / (best possible p_bar)`.

That is not a threshold to loosen. At 1.07 a 10% expected-value margin needs an
edge larger than the bookmaker's own margin on a favourite, which is arithmetic,
not evidence. It is a fact the artifact has to state.
"""

import pytest

from bet.sofa.engine import (
    K_PRICE,
    P_CEILING,
    bar_is_unreachable,
    bar_probability,
    get_required_odds,
)


def test_a_short_price_on_a_strong_favourite_is_unreachable():
    """Wisla Krakow corners OVER 2.5 at 1.07, market_p 0.9148, n=9."""
    assert bar_is_unreachable(1.07, 0.9148, 9)


def test_a_price_that_merely_missed_is_not_flagged():
    """Elche goals OVER 0.5 at 1.45 needed 1.64: a real miss, on evidence."""
    assert not bar_is_unreachable(1.45, 0.6628, 10)


def test_a_long_shot_is_never_unreachable():
    assert not bar_is_unreachable(8.5, 0.10, 10)


def test_unreachable_means_what_it_says_no_sample_can_qualify_it():
    """The claim is universal, so check it against the whole range of p."""
    offered, market_p, n = 1.07, 0.9148, 9
    assert bar_is_unreachable(offered, market_p, n)
    for i in range(1, 100):
        p_central = i / 100.0
        p_bar, _ = bar_probability(
            p_central=min(p_central, P_CEILING),
            hits=0,
            n=n,
            p_low_val=1.0,
            market_p=market_p,
        )
        assert get_required_odds(p_bar) > offered


def test_a_reachable_row_has_some_sample_that_qualifies_it():
    offered, market_p, n = 1.45, 0.6628, 10
    assert not bar_is_unreachable(offered, market_p, n)
    qualifies = [
        i
        for i in range(1, 100)
        if get_required_odds(
            bar_probability(
                p_central=min(i / 100.0, P_CEILING),
                hits=0,
                n=n,
                p_low_val=1.0,
                market_p=market_p,
            )[0]
        )
        <= offered
    ]
    assert qualifies, "not unreachable, so some p_central must clear it"


def test_the_bound_moves_with_the_sample_weight():
    """More weight on our own estimate raises the ceiling on p_bar."""
    offered, market_p = 1.20, 0.90
    assert bar_is_unreachable(offered, market_p, n=2, k_price=K_PRICE)
    assert not bar_is_unreachable(offered, market_p, n=200, k_price=K_PRICE)


@pytest.mark.parametrize(
    ("offered", "market_p", "n"),
    [(None, 0.9, 10), (1.07, None, 10), (1.07, 0.9, 0)],
)
def test_a_row_missing_a_term_is_not_claimed_unreachable(offered, market_p, n):
    assert not bar_is_unreachable(offered, market_p, n)
