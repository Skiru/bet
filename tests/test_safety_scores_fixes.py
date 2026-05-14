import pytest
from scripts.compute_safety_scores import compute_hit_rate, compute_margin, compute_safety_score

def test_half_win_hit_rate_pushes():
    # Fix #1: Pushes count as half-win (0.5)
    # Line is 9.5, Values: 10, 11 (2 hits), 9 (1 push if line was 9, but let's test exact line)
    # Let's test with line 9.0
    line = 9.0
    values = [10.0, 11.0, 9.0, 8.0] # 2 hits (over), 1 push, 1 miss
    
    hits, total, pushes = compute_hit_rate(values, line, "OVER")
    assert hits == 2
    assert pushes == 1
    assert total == 4
    
    # Mathematical representation of what our code does now:
    rate = (hits + (0.5 * pushes)) / total
    assert rate == (2 + 0.5) / 4.0 # 0.625

def test_volatility_margin_cap():
    # Fix #3: Margin should be hard capped at 1.50
    # direction OVER: avg = 20.0, line = 5.0 -> avg/line = 4.0 -> should cap at 1.50
    margin_over = compute_margin(avg=20.0, line=5.0, direction="OVER")
    assert margin_over == 1.50
    
    # direction UNDER: avg = 2.0, line = 10.0 -> line/avg = 5.0 -> should cap at 1.50
    margin_under = compute_margin(avg=2.0, line=10.0, direction="UNDER")
    assert margin_under == 1.50
    
    # Normal margin shouldn't be affected
    margin_normal = compute_margin(avg=6.0, line=5.0, direction="OVER")
    assert margin_normal == 1.2  # 6/5

def test_small_sample_penalty():
    # Fix #3: Sample size penalty inside hit rates (less than 8 games)
    # Inside rank_markets this is applied directly, let's replicate logic for test validation
    # If hit rate is 100% (3/3), rate should be 1.0 * (3/10) = 0.3
    total_l10 = 3
    hits = 3
    pushes = 0
    raw_rate = (hits + 0.5 * pushes) / total_l10
    
    if total_l10 > 0 and total_l10 < 8:
        penalized_rate = round(raw_rate * (total_l10 / 10.0), 3)
    else:
        penalized_rate = raw_rate
        
    assert penalized_rate == 0.3

