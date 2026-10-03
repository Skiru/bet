"""scripts/sofa/measure_sport_admission.py - the coupon rule replayed on a
measured sport's graded lines.

The curve must come only from earlier dates, a leg must clear the floor,
confidence x odds, MAX_DISAGREEMENT and the margin cap exactly as CONFIDENCE
reads them, and the ROI interval must resample games.
"""

from scripts.sofa.measure_sport_admission import (
    RULES,
    admitted,
    bucket_of,
    fit_curve,
    replay,
    roi_interval,
    wilson_lo,
)


def _row(date, game, p_model, p_price, y, odds, over=0.08, family="total", line=5.5):
    return {"date": date, "game": game, "family": family, "period": 0,
            "line": line, "side": "OVER", "p_model": p_model,
            "p_price": p_price, "y": y, "odds": odds, "overround": over}


def test_the_curve_is_the_wilson_lower_bound_of_its_bucket():
    rows = [_row("d1", f"g{i}", 0.78, 0.7, 1.0 if i < 160 else 0.0, 1.4)
            for i in range(200)]
    curve = fit_curve(rows, "model", min_bucket=200)
    b = bucket_of(0.78)
    assert curve[b][1] == 200
    assert abs(curve[b][0] - wilson_lo(160, 200)) < 1e-12
    assert fit_curve(rows, "model", min_bucket=201) == {}


def test_a_leg_needs_floor_price_disagreement_and_margin():
    curve = {bucket_of(0.78): (0.74, 500)}
    std = RULES["standard"]
    assert admitted(_row("d", "g", 0.78, 0.72, 1, 1.40), curve, "model", std) == 0.74
    # 0.74 x 1.35 = 0.999: below the price
    assert admitted(_row("d", "g", 0.78, 0.72, 1, 1.35), curve, "model", std) is None
    # the model 0.11 above the devigged price: MAX_DISAGREEMENT
    assert admitted(_row("d", "g", 0.78, 0.67, 1, 1.40), curve, "model", std) is None
    # a ladder margin above the singles' cap
    assert admitted(_row("d", "g", 0.78, 0.72, 1, 1.40, over=0.12), curve,
                    "model", std) is None
    # under the floor
    low = {bucket_of(0.78): (0.69, 500)}
    assert admitted(_row("d", "g", 0.78, 0.72, 1, 1.50), low, "model", std) is None
    # the variant: 0.65 floor, x >= 0.90, margin up to 15%
    var = RULES["wariant"]
    assert admitted(_row("d", "g", 0.78, 0.72, 1, 1.35, over=0.12), curve,
                    "model", var) == 0.74


def test_the_first_date_is_never_tested_and_later_dates_read_only_the_past():
    train = [_row("d1", f"a{i}", 0.78, 0.72, 1.0, 1.40) for i in range(300)]
    test = [_row("d2", "b1", 0.78, 0.72, 0.0, 1.40)]
    future = [_row("d3", f"c{i}", 0.78, 0.72, 0.0, 1.40) for i in range(300)]
    legs = replay(train + test + future, "model", RULES["standard"], 200)
    dates = {leg["date"] for leg in legs}
    assert "d1" not in dates and "d2" in dates
    # d3 reads d1+d2 (301 rows, 300 hits): still printed; d2 never read d3
    d2 = [leg for leg in legs if leg["date"] == "d2"]
    assert len(d2) == 1 and d2[0]["confidence"] == wilson_lo(300, 300)


def test_the_roi_interval_resamples_games():
    legs = [dict(_row("d", "g1", 0.8, 0.7, 1.0, 1.5), confidence=0.75),
            dict(_row("d", "g1", 0.8, 0.7, 1.0, 1.5), confidence=0.75),
            dict(_row("d", "g2", 0.8, 0.7, 0.0, 1.5), confidence=0.75)]
    roi = roi_interval(legs, n=500)
    assert roi is not None
    assert abs(roi[0] - (0.5 + 0.5 - 1.0) / 3) < 1e-12
    # resampling games: the only possible means are 0.5 (g1 twice), -1 and 0
    assert roi[1] >= -1.0 and roi[2] <= 0.5
    assert roi_interval([]) is None
