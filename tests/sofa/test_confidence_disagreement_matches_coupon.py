"""CONFIDENCE's disagreement gate reads the quantity MAX_DISAGREEMENT was
measured on - p_central minus the devigged price - the way COUPON does.

2026-09-23: it compared the calibrated lower bound with 1/odds, and 159 of 216
printed singles sat more than 0.10 above their devigged price.
"""

import inspect

from bet.sofa.confidence import MAX_DISAGREEMENT, disagrees_with_price


def test_a_row_far_above_its_devigged_price_is_refused():
    # Fernandez set 1 OVER 5.5 as printed: p 0.908, market 0.727, conf 0.831,
    # odds 1.32 - the old test read 0.831 - 0.758 = 0.073 and let it through.
    assert disagrees_with_price(0.908, 0.727, 0.831, 1.32)
    assert 0.831 - 1 / 1.32 <= MAX_DISAGREEMENT


def test_a_row_near_its_price_passes():
    assert not disagrees_with_price(0.78, 0.70, 0.76, 1.35)


def test_a_one_sided_rung_keeps_the_odds_comparison():
    assert disagrees_with_price(0.95, None, 0.90, 1.60)
    assert not disagrees_with_price(0.95, None, 0.70, 1.60)


def test_the_stage_uses_it():
    import scripts.sofa.run_confidence as conf

    src = inspect.getsource(conf)
    assert "disagrees_with_price(" in src
    assert "realised_lo - 1.0 / odds > MAX_DISAGREEMENT" not in src
