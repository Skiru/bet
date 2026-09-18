"""F41 — a count metric may not spend probability on negative counts.

The 2026-09-18 coupon's top row was "Ruch Chorzow under 0.5 corners" at 30.00,
on a sample of [5,7,7,5,2,7,3,16,3,3]. The model claimed 0.1294, of which
0.1062 was the normal distribution's mass below *zero* corners. These tests
pin the arithmetic, the complementarity it must not break, and the fact that
every stage which scores a rung conditions on the same support — the sheet,
the settler and the two calibration scripts, which are only comparable if
they price the same model.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from bet.sofa.engine import (
    NON_COUNT_METRICS,
    calc_p_central,
    calc_p_central_raw,
    calculate_p_low,
    normal_cdf,
    outside_model_resolution,
    predictive_sd,
    support_floor_for,
    winning_boundary,
)

REPO = Path(__file__).resolve().parents[2]

# The row, exactly as the sheet recorded it.
RUCH_SAMPLE = [5.0, 7.0, 7.0, 5.0, 2.0, 7.0, 3.0, 16.0, 3.0, 3.0]
RUCH_CENTRE = 5.2955
RUCH_SD = 4.0497
RUCH_N = 10
RUCH_OFFERED = 30.0


def test_support_floor_is_minus_half_for_counts_and_absent_for_the_rest() -> None:
    """-0.5, not 0.0: a count of zero occupies [-0.5, 0.5).

    Clamping at 0.0 was measured against 516,883 settled rows and came out
    *worse than no floor at all* — in the p < 0.10 band the coupon selects,
    realised/predicted went 0.93 (no floor) -> 1.46 (floor 0.0) -> 0.99
    (floor -0.5). Deleting the mass below zero also deletes what was standing
    in for the atom at zero on a low-mean count.
    """
    for market in ("corners_for", "goals_total", "cards_points_for", "games_won_for"):
        assert support_floor_for(market) == -0.5
    for market in sorted(NON_COUNT_METRICS):
        assert support_floor_for(market) is None


def test_the_floor_keeps_the_zero_atom_that_clamping_at_zero_deletes() -> None:
    """A low-mean count must not lose "exactly zero" to the truncation."""
    centre, sd = 0.70, 1.64  # a team averaging 0.7 second-half goals
    b = winning_boundary(0.5, "UNDER")
    at_zero = calc_p_central_raw(centre, sd, b, "UNDER", 0.0)
    at_minus_half = calc_p_central_raw(centre, sd, b, "UNDER", -0.5)
    poisson_zero = math.exp(-centre)
    assert at_zero < 0.20
    assert at_minus_half > at_zero
    # Neither reaches Poisson, but the continuity-corrected floor must not be
    # further from it than the naive one.
    assert abs(at_minus_half - poisson_zero) < abs(at_zero - poisson_zero)


def test_the_claimed_probability_was_mostly_mass_below_zero() -> None:
    """The measurement that motivated the fix, pinned so it cannot drift."""
    pred_sd = predictive_sd(RUCH_SD**2, RUCH_CENTRE, RUCH_N)
    boundary = winning_boundary(0.5, "UNDER")

    unconditioned = calc_p_central_raw(RUCH_CENTRE, pred_sd, boundary, "UNDER")
    below_zero = normal_cdf((0.0 - RUCH_CENTRE) / pred_sd)

    assert unconditioned == pytest.approx(0.1294, abs=5e-4)
    assert below_zero == pytest.approx(0.1062, abs=5e-4)
    # Four fifths of the model's opinion sat on an impossible outcome.
    assert below_zero / unconditioned > 0.8

    below_floor = normal_cdf((-0.5 - RUCH_CENTRE) / pred_sd)
    conditioned = calc_p_central_raw(
        RUCH_CENTRE, pred_sd, boundary, "UNDER", support_floor_for("corners_for")
    )
    assert conditioned == pytest.approx(
        (unconditioned - below_floor) / (1.0 - below_floor), rel=1e-9
    )
    assert conditioned < unconditioned / 2


def test_the_row_no_longer_reaches_a_sheet_at_all() -> None:
    """The point of the fix: this rung must stop winning the top coupon slot.

    It does not merely fail its price — it falls under P_FLOOR, so
    outside_model_resolution refuses to price it, which is the same answer the
    sample gives: the event never happened in ten matches.
    """
    pred_sd = predictive_sd(RUCH_SD**2, RUCH_CENTRE, RUCH_N)
    boundary = winning_boundary(0.5, "UNDER")
    assert sum(1 for v in RUCH_SAMPLE if v < boundary) == 0

    p = calc_p_central_raw(
        RUCH_CENTRE, pred_sd, boundary, "UNDER", support_floor_for("corners_for")
    )
    # p = 0.0473, under P_FLOOR, so the rung is never priced. It is not that
    # the row fails its price — 1.10/0.0473 is 23.3 and the offer was 30.00,
    # so on price alone it would still look like value. The refusal is the
    # model declining to have an opinion, which is the correct answer.
    assert outside_model_resolution(p)
    assert 1.10 / p < RUCH_OFFERED


def test_conditioning_keeps_over_and_under_complementary() -> None:
    """A rung's two sides must still be two descriptions of one belief."""
    for centre, sd in ((5.3, 4.2), (1.8, 1.4), (0.4, 1.9), (22.0, 6.0)):
        for line in (0.5, 1.5, 2.5, 9.5, 21.5):
            over = calc_p_central_raw(
                centre, sd, winning_boundary(line, "OVER"), "OVER", -0.5
            )
            under = calc_p_central_raw(
                centre, sd, winning_boundary(line, "UNDER"), "UNDER", -0.5
            )
            assert over + under == pytest.approx(1.0, abs=1e-9)
            assert 0.0 <= over <= 1.0
            assert 0.0 <= under <= 1.0


def test_conditioning_only_bites_where_the_impossible_mass_is_material() -> None:
    """A well-separated rung must be left where it was, or this is a rewrite."""
    centre, sd = 11.0, 3.0  # mass below zero ~ 1e-4
    for line in (7.5, 9.5, 11.5, 13.5):
        for direction in ("OVER", "UNDER"):
            b = winning_boundary(line, direction)
            plain = calc_p_central_raw(centre, sd, b, direction)
            floored = calc_p_central_raw(centre, sd, b, direction, -0.5)
            assert floored == pytest.approx(plain, abs=1e-3)


def test_conditioning_moves_probability_towards_the_possible_side() -> None:
    centre, sd = 3.0, 3.5
    b_under = winning_boundary(0.5, "UNDER")
    b_over = winning_boundary(0.5, "OVER")
    assert calc_p_central_raw(centre, sd, b_under, "UNDER", -0.5) < calc_p_central_raw(
        centre, sd, b_under, "UNDER"
    )
    assert calc_p_central_raw(centre, sd, b_over, "OVER", -0.5) > calc_p_central_raw(
        centre, sd, b_over, "OVER"
    )


def test_a_model_entirely_below_its_support_is_refused_not_renormalised() -> None:
    """Degenerate input must reach outside_model_resolution, not a divide."""
    p = calc_p_central_raw(-40.0, 1.0, 0.5, "UNDER", -0.5)
    assert p == 0.0
    assert outside_model_resolution(p)


def test_p_low_is_not_given_a_support_floor_in_production() -> None:
    """Conditioning the *shifted* centre backfires, so the sheet must not.

    calculate_p_low shifts the centre 1.96 SE against the bet. That shifted
    centre is an artificial device, not a mean the quantity could have, and
    when the shift lands below the support, renormalising inflates the tail it
    was supposed to bound: at centre 0.3, sd 2.5, n = 5 the OVER estimate goes
    from 0.191 to 0.626. p_low only ever caps p downward, so the unfloored
    value is the strictly more protective one — and it keeps run_sheet
    agreeing with settle.py, which never passed a floor here either.
    """
    plain = calculate_p_low(0.3, 2.5, 5, winning_boundary(0.5, "OVER"), "OVER")
    floored = calculate_p_low(0.3, 2.5, 5, winning_boundary(0.5, "OVER"), "OVER", -0.5)
    assert plain == pytest.approx(0.1913, abs=5e-4)
    assert floored > 3 * plain, "the floored variant is the anti-conservative one"

    sheet = (REPO / "scripts/sofa/run_sheet.py").read_text(encoding="utf-8")
    settle = (REPO / "src/bet/sofa/settle.py").read_text(encoding="utf-8")
    for name, source in (("run_sheet", sheet), ("settle", settle)):
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "calculate_p_low"
            ):
                assert len(node.args) <= 5, (
                    f"{name}:{node.lineno} passes a support floor to "
                    "calculate_p_low"
                )


def test_clamped_and_p_low_variants_accept_the_same_floor() -> None:
    pred_sd = predictive_sd(RUCH_SD**2, RUCH_CENTRE, RUCH_N)
    b = winning_boundary(0.5, "UNDER")
    assert calc_p_central(RUCH_CENTRE, pred_sd, b, "UNDER", -0.5) == pytest.approx(
        max(0.05, calc_p_central_raw(RUCH_CENTRE, pred_sd, b, "UNDER", -0.5))
    )
    # calculate_p_low clamps to [0.05, 0.95], and on the Ruch row both
    # variants land on the floor, so the effect is only visible where the
    # conservative shift leaves the result inside the band.
    floored = calculate_p_low(2.4, 2.2, 10, b, "UNDER", -0.5)
    plain = calculate_p_low(2.4, 2.2, 10, b, "UNDER")
    assert floored < plain
    assert calculate_p_low(RUCH_CENTRE, RUCH_SD, RUCH_N, b, "UNDER", -0.5) <= (
        calculate_p_low(RUCH_CENTRE, RUCH_SD, RUCH_N, b, "UNDER")
    )


def test_degenerate_zero_sd_is_unchanged_by_the_floor() -> None:
    for direction, expected in (("OVER", 1.0), ("UNDER", 0.0)):
        assert calc_p_central_raw(5.0, 0.0, 2.5, direction, -0.5) == expected


@pytest.mark.parametrize(
    "path,call",
    [
        ("scripts/sofa/run_sheet.py", "calc_p_central_raw"),
        ("src/bet/sofa/settle.py", "calc_p_central_raw"),
        ("scripts/sofa/calibrate_from_cache.py", "calc_p_central_raw"),
        ("scripts/sofa/fit_constants.py", "calc_p_central"),
    ],
)
def test_every_stage_that_scores_a_rung_passes_a_support_floor(
    path: str, call: str
) -> None:
    """The sheet prices a model; the calibration measures one. If they are not
    the same model the correction curve is fitted to something that never
    ships — the failure `calibrate_from_cache` was written to avoid."""
    tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == call
    ]
    assert calls, f"{path} no longer calls {call}"
    for node in calls:
        assert len(node.args) >= 5, (
            f"{path}:{node.lineno} calls {call} without a support floor"
        )
        arg = node.args[4]
        assert isinstance(arg, ast.Call) and arg.func.id == "support_floor_for", (
            f"{path}:{node.lineno} passes a literal floor instead of "
            "support_floor_for(market)"
        )


def test_no_zero_rung_that_gets_priced_can_claim_impossible_mass() -> None:
    """The invariant that matters: nothing absurd is ever *priced*.

    The normal remains the wrong shape for the zero atom of a skewed count,
    and with a wide enough sd it still overstates P(exactly zero) — at centre
    8.0 with sd 7.0 it says 0.033 against a Poisson 0.00034. The floor does
    not repair that and this test does not pretend it does. What it pins is
    that every such rung lands under P_FLOOR, so outside_model_resolution
    refuses it, and every rung that *is* priced sits within a factor of 15 of
    Poisson. Before the floor, the live Ruch row was priced at 26x.
    """
    checked = 0
    for centre in (0.6, 1.5, 3.0, 5.3, 8.0, 11.0):
        for sd in (1.0, 2.5, 4.3, 7.0):
            p = calc_p_central_raw(
                centre, sd, winning_boundary(0.5, "UNDER"), "UNDER", -0.5
            )
            if outside_model_resolution(p):
                continue
            checked += 1
            assert p <= 15.0 * math.exp(-centre), (centre, sd, p)
    assert checked > 0, "the sweep priced nothing, so it asserted nothing"
