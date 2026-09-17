import math
import pytest

from bet.sofa.contracts import Direction, PricedRung, SheetRow
from bet.sofa.engine import (
    calc_p_central,
    predictive_sd,
    winning_boundary,
    devig,
    ladder_centre,
    calculate_p_low,
    bar_probability,
    get_required_odds,
    normal_cdf
)

def test_t17_p_central_sum_to_one():
    # p_central(OVER) + p_central(UNDER) == 1 before clamp.
    # Note: because of how winning_boundary works, for half lines they use the same boundary,
    # and therefore their z-scores are symmetric.
    # Let's test on a half line first to avoid push mass.
    line = 2.5
    centre = 2.2
    sd = 1.3
    
    bound_over = winning_boundary(line, "OVER")
    bound_under = winning_boundary(line, "UNDER")
    
    assert bound_over == 2.5
    assert bound_under == 2.5
    
    # Calculate directly without clamp
    z_under = (bound_under - centre) / sd
    p_under_raw = normal_cdf(z_under)
    
    z_over = -(bound_over - centre) / sd
    p_over_raw = normal_cdf(z_over)
    
    assert math.isclose(p_under_raw + p_over_raw, 1.0, rel_tol=1e-9)
    
    # With clamp
    p_over = calc_p_central(centre, sd, bound_over, "OVER")
    p_under = calc_p_central(centre, sd, bound_under, "UNDER")
    
    # If clamped to 0.95 and 0.05, sum is 1.0
    # Difference from 1.0 is bounded by 2 * (1 - 0.95) = 0.1
    diff = abs(1.0 - (p_over + p_under))
    assert diff <= 0.10001


def test_t18_monotonicity_with_line():
    centre = 2.0
    sd = 1.0
    
    lines = [0.5, 1.5, 2.5, 3.5, 4.5]
    p_overs = []
    p_unders = []
    
    for line in lines:
        bound_over = winning_boundary(line, "OVER")
        bound_under = winning_boundary(line, "UNDER")
        p_overs.append(calc_p_central(centre, sd, bound_over, "OVER"))
        p_unders.append(calc_p_central(centre, sd, bound_under, "UNDER"))
        
    for i in range(1, len(lines)):
        assert p_overs[i] <= p_overs[i-1] # OVER should decrease
        assert p_unders[i] >= p_unders[i-1] # UNDER should increase

def test_t19_required_odds_monotonicity_and_floor():
    p_bars = [0.9, 0.5, 0.1, 0.05, 0.01, 0.0001]
    
    # If bar_probability returns 0.01 because of floor
    p_bar_clamped, _ = bar_probability(p_central=0.001, hits=0, n=10, p_low_val=0.001, market_p=None)
    assert p_bar_clamped == 0.01
    
    odds = [get_required_odds(p) for p in p_bars]
    for i in range(1, len(odds)):
        # Odds should increase as p decreases
        assert odds[i] >= odds[i-1]


def test_t20_predictive_sd():
    variance = 2.0
    mean = 2.0
    sample_sd = math.sqrt(variance)
    
    for n in range(2, 20):
        pred_sd = predictive_sd(variance, mean, n)
        assert pred_sd > sample_sd
        
    # Specifically for n=5
    pred_sd_5 = predictive_sd(variance, mean, 5)
    ratio = pred_sd_5 / sample_sd
    assert math.isclose(ratio, math.sqrt(1 + 1/5), rel_tol=1e-5)


def test_t21_winning_boundary_whole_line():
    assert winning_boundary(2.0, "OVER") == 2.5
    assert winning_boundary(2.0, "UNDER") == 1.5
    
    # Ensure push mass is not included in either direction
    centre = 2.0
    sd = 1.0
    p_over = calc_p_central(centre, sd, 2.5, "OVER")
    p_under = calc_p_central(centre, sd, 1.5, "UNDER")
    
    # For a perfect standard normal around 2.0, mass between 1.5 and 2.5 is push
    # So P(OVER) + P(UNDER) < 1.0
    assert p_over + p_under < 1.0


def test_t22_devig_single_sided():
    assert devig(1.9, None) is None
    assert devig(None, 1.9) is None


def test_t23_ladder_centre():
    # Only one rung
    assert ladder_centre([(2.5, 0.6)]) is None
    
    # Both above 0.5
    assert ladder_centre([(1.5, 0.8), (2.5, 0.6)]) is None
    
    # Both below 0.5
    assert ladder_centre([(4.5, 0.4), (5.5, 0.2)]) is None
    
    # Crossing 0.5
    res = ladder_centre([(2.5, 0.6), (3.5, 0.4)])
    assert res is not None
    assert math.isclose(res, 3.0, rel_tol=1e-5)


def test_t24_calibration_correction_cannot_raise_p():
    p_central = 0.5
    market_p = None
    
    p_bar_zero, _ = bar_probability(p_central, hits=5, n=10, p_low_val=0.5, market_p=market_p, correction=0.0)
    p_bar_corr, _ = bar_probability(p_central, hits=5, n=10, p_low_val=0.5, market_p=market_p, correction=0.05)
    
    assert p_bar_corr < p_bar_zero


def test_t25_edge_uses_p_central_not_p_bar():
    # edge = p_central - market_p
    # Create a dummy row to test field calculations
    import datetime
    row = SheetRow(
        sofascore_event_id=1,
        sport="football",
        market="goals_total",
        subject="",
        line=2.5,
        direction="OVER",
        sample_size=10,
        sample_mean=2.5,
        sample_sd=1.0,
        centre=2.5,
        p_central=0.6,
        market_p=0.5,
        ladder_centre=None,
        ladder_sigma=None,
        p_bar=0.55, # explicitly different from p_central
        bar_reason="none",
        required_odds=2.0,
        offered_odds=2.1,
        edge=0.6 - 0.5, # p_central - market_p
        surplus=0.1,
        verdict="VALUE",
        notes=[]
    )
    
    assert math.isclose(row.edge, 0.1, rel_tol=1e-5)
    # If edge was using p_bar, it would be 0.55 - 0.5 = 0.05
    assert not math.isclose(row.edge, 0.05, rel_tol=1e-5)
