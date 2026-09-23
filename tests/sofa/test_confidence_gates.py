"""The gates added after the 2026-09-20 coupon review.

Every case here is a leg that actually reached a built coupon. The review
found them one at a time; the point of the tests is that they cannot come
back one at a time either.
"""

import pytest

from bet.sofa.confidence import (
    CONFIDENCE_CEILING,
    MIN_ODDS_FOR_CEILING,
    builder_legs_are_coherent,
    leg_is_ev_positive,
    line_is_beyond_sample,
    mode_loses,
    overround,
    single_is_fairly_priced,
)


def test_the_odds_floor_is_the_curves_own_resolution_limit():
    """A leg priced below 1/ceiling cannot win under this calibration.

    Not a judgement about any fixture: the curve tops out at 0.9202, so
    0.9202 * odds > 1 requires odds > 1.0867. The old floor was 1.01.
    """
    assert MIN_ODDS_FOR_CEILING == pytest.approx(1.0 / CONFIDENCE_CEILING)
    assert MIN_ODDS_FOR_CEILING == pytest.approx(1.0867, abs=0.0001)
    assert not leg_is_ev_positive(CONFIDENCE_CEILING, 1.08)
    assert leg_is_ev_positive(CONFIDENCE_CEILING, 1.09)


def test_the_eight_legs_that_dragged_the_2026_09_20_slips():
    """Londrina's was the worst: @1.01 against a confidence of 0.906.

    It multiplied the slip odds by 1.01 and its probability by 0.906 — an EV
    multiplier of 0.915. The slip fell from +0.097 to +0.004.
    """
    assert not leg_is_ev_positive(0.906, 1.01)
    assert not leg_is_ev_positive(0.916, 1.08)  # AC Milan goals UNDER 5.5
    assert not leg_is_ev_positive(0.884, 1.06)  # CSYD Liniers goals_for UNDER 2.5
    assert leg_is_ev_positive(0.848, 1.20)      # Dinamo corners UNDER 13.5 survives


def test_a_line_the_sample_has_never_reached_is_an_extrapolation():
    """AC Milan `goals_total UNDER 5.5` on a sample whose maximum was 5.

    The sample reported 20 hits from 20 observations and could not have
    reported anything else. That is not evidence about the tail.
    """
    milan = [0, 0, 1, 1, 1, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 5, 5, 5]
    assert line_is_beyond_sample(5.5, "UNDER", milan)
    assert not line_is_beyond_sample(4.5, "UNDER", milan)
    # symmetric on the other side
    assert line_is_beyond_sample(0.5, "OVER", [1, 2, 3])
    assert not line_is_beyond_sample(1.5, "OVER", [1, 2, 3])


def test_an_empty_sample_does_not_trip_the_shape_gates():
    """No observations is a different refusal (THIN_SAMPLE); these must not
    claim to have measured a shape they never saw."""
    assert not line_is_beyond_sample(5.5, "UNDER", [])
    assert not mode_loses(0.5, "OVER", [])


def test_the_modal_outcome_must_not_lose_the_bet():
    """Chaco For Ever `goals_total OVER 0.5` with a modal sample value of 0.

    The single most frequent thing this sample has seen settles the leg as a
    loss. A mean above the line does not rescue that.
    """
    chaco = [0.0, 0.0, 0.0, 1.0, 1.0, 2.0, 3.0]
    assert mode_loses(0.5, "OVER", chaco)
    # Farul `corners_2h_for OVER 0.5`, mode 0 on nine observations
    assert mode_loses(0.5, "OVER", [0, 0, 0, 0, 1, 1, 2, 2, 3])
    # A mode on the winning side is fine, even sitting right by the line:
    # AC Milan cards OVER 1.5 with a mode of 2 wins on its modal outcome.
    assert not mode_loses(1.5, "OVER", [1, 2, 2, 2, 4, 4, 5, 6])


def test_mode_loses_is_not_merely_proximity_to_the_line():
    """The earlier crude check flagged `abs(mode - line) <= 0.5`, which fires
    on safe legs. Only the losing side counts."""
    assert not mode_loses(1.5, "OVER", [2, 2, 2, 3])   # mode 2 wins OVER 1.5
    assert mode_loses(2.5, "OVER", [2, 2, 2, 3])       # mode 2 loses OVER 2.5
    assert not mode_loses(2.5, "UNDER", [2, 2, 2, 3])  # mode 2 wins UNDER 2.5
    assert mode_loses(1.5, "UNDER", [2, 2, 2, 3])      # mode 2 loses UNDER 1.5


def _leg(market, direction):
    return {"market": market, "direction": direction}


def test_a_builder_may_not_disagree_with_itself_about_tempo():
    """`combined_probability` multiplies, which assumes independence.

    goals UNDER with corners OVER is negatively correlated, so the product
    overstates the joint and the reported EV is too high. Three of the
    fourteen slips on 2026-09-20 were built this way.
    """
    assert not builder_legs_are_coherent(
        [_leg("goals_total", "UNDER"), _leg("corners_total", "OVER")]
    )
    assert builder_legs_are_coherent(
        [_leg("goals_total", "UNDER"), _leg("corners_1h_total", "UNDER")]
    )
    assert builder_legs_are_coherent(
        [_leg("goals_total", "OVER"), _leg("shots_total", "OVER")]
    )


def test_cards_do_not_constrain_tempo_coherence():
    """Cards are not a tempo quantity — a cards OVER beside a goals UNDER is
    the ordinary 'tight, niggly match' read, and lambda across quantities sits
    at 0.95-1.02. Only goals/corners/shots are checked against each other."""
    assert builder_legs_are_coherent(
        [_leg("goals_total", "UNDER"), _leg("cards_points_total", "OVER")]
    )
    # the real AC Milan slip, minus the leg the EV gate removes
    assert builder_legs_are_coherent(
        [
            _leg("corners_1h_total", "UNDER"),
            _leg("cards_points_total", "OVER"),
            _leg("shots_on_target_for", "UNDER"),
        ]
    )


def test_the_sample_age_guard_sits_where_the_measurement_put_it():
    """180 days, not the 120 that reasoning about transfer windows suggested.

    Measured on 5,220 settled legs from 2026-09-19: the 121-180 day band
    realises 0.874 against a declared 0.856 and returns -3.8%, indistinguishable
    from the freshest band (0.878, -3.0%). Only past 180 days does it fall
    away (0.817, -9.7%, n=104). A 120-day cut would have removed 60 of that
    day's 83 coupon legs to catch 6 of its 9 losses — a worse loss rate than
    the coupon's own 11.2%.
    """
    from bet.sofa.confidence import MAX_BUILDER_SAMPLE_AGE_DAYS

    assert MAX_BUILDER_SAMPLE_AGE_DAYS == 180


def test_a_leg_can_win_nine_times_in_ten_and_still_lose_money():
    """Why ODDS_TOO_LOW is judged on return, not on hit rate.

    The 2,492 settled legs priced below 1.0867 on 2026-09-19 won **92.5%** of
    the time and returned **-3.5%** (-87.7 units). Any audit that scores a
    gate by the hit rate of what it removes will call that gate a mistake.
    """
    hit_rate, odds = 0.925, 1.06
    assert hit_rate > 0.9
    assert hit_rate * odds < 1.0
    assert not leg_is_ev_positive(hit_rate, odds)


def test_builder_odds_discounts_the_product_when_no_screen_price():
    """Superbet never quotes the product. Selecting on it selects on fiction."""
    from bet.sofa.confidence import BUILDER_CORRELATION_HAIRCUT, builder_odds

    assert builder_odds(2.0) == pytest.approx(2.0 * (1 - BUILDER_CORRELATION_HAIRCUT))
    # A measured price beats the estimate outright, in both directions.
    assert builder_odds(2.364, screen_odds=1.90) == 1.90
    assert builder_odds(1.754, screen_odds=1.99) == 1.99


def test_haircut_matches_the_measured_range():
    """12% is the middle of 8.8-19.6%, the three prices read off the screen."""
    from bet.sofa.confidence import BUILDER_CORRELATION_HAIRCUT

    assert 0.088 <= BUILDER_CORRELATION_HAIRCUT <= 0.196


def test_empirical_joint_counts_the_same_match_not_the_same_team():
    """Legs must hold together in one match for the slip to have held."""
    from bet.sofa.confidence import empirical_joint

    goals = {1: 2.0, 2: 6.0, 3: 1.0}
    corners = {1: 5.0, 2: 9.0, 3: 2.0}
    # goals UNDER 4.5 and corners OVER 3.5 hold together only in match 1:
    # match 2 has the corners but not the goals, match 3 the reverse.
    assert empirical_joint([goals, corners], [(4.5, "UNDER"), (3.5, "OVER")]) == (1, 3)


def test_empirical_joint_only_judges_shared_matches():
    """A match one leg never saw cannot testify about the joint."""
    from bet.sofa.confidence import empirical_joint

    a = {1: 1.0, 2: 1.0, 3: 1.0}
    b = {1: 1.0}
    assert empirical_joint([a, b], [(2.5, "UNDER"), (2.5, "UNDER")]) == (1, 1)
    assert empirical_joint([a, {}], [(2.5, "UNDER"), (2.5, "UNDER")]) == (0, 0)


def test_joint_probability_demotes_but_never_promotes():
    """The observed joint may veto the product; it may not inflate it.

    The Flamengo slip of 2026-09-20 is the case that matters: the product said
    0.583 and the legs held together in 4 of the team's last 10 matches.
    """
    from bet.sofa.confidence import joint_probability

    assert joint_probability(0.583, 4, 10) < 0.583
    # Nested legs make the product too LOW; the sample must not promote them.
    assert joint_probability(0.649, 9, 10) == 0.649
    # Too few shared matches to say anything: the product stands.
    assert joint_probability(0.583, 0, 3) == 0.583


def test_joint_probability_never_asserts_certainty():
    """10 for 10 is not 100%. Laplace keeps the slip honest."""
    from bet.sofa.confidence import joint_probability

    assert joint_probability(0.999, 10, 10) < 1.0


def test_a_builder_with_negative_ev_after_the_haircut_is_not_stakeable():
    """The 2026-09-21 contradiction: CONFIDENCE said 3, the PDF staked 0.

    All three of that day's builders were `best_for_fixture` and all three
    had negative EV once Superbet's measured correlation markup was applied.
    The summary counted only the first condition, so it announced three bets
    on a day with none. Both readers now share one predicate.
    """
    from bet.sofa.confidence import is_stakeable

    day_2026_09_21 = [
        {"best_for_fixture": True, "ev_after_haircut": -0.0496},
        {"best_for_fixture": True, "ev_after_haircut": -0.0538},
        {"best_for_fixture": True, "ev_after_haircut": -0.0916},
    ]
    assert sum(1 for b in day_2026_09_21 if is_stakeable(b)) == 0


def test_stakeable_needs_both_conditions_not_either():
    from bet.sofa.confidence import is_stakeable

    assert is_stakeable({"best_for_fixture": True, "ev_after_haircut": 0.02})
    # Positive EV is not enough: a subset builder on a fixture already staked
    # is the same opinion sold twice.
    assert not is_stakeable({"best_for_fixture": False, "ev_after_haircut": 0.40})
    # Nor is being the best builder on a fixture, if it loses money.
    assert not is_stakeable({"best_for_fixture": True, "ev_after_haircut": -0.001})


def test_an_artifact_predating_the_haircut_falls_back_to_product_ev():
    """Older 08_confidence.json carries only `ev_if_product_priced`."""
    from bet.sofa.confidence import is_stakeable

    assert is_stakeable({"best_for_fixture": True, "ev_if_product_priced": 0.05})
    assert not is_stakeable({"best_for_fixture": True, "ev_if_product_priced": -0.05})


def test_a_market_may_not_borrow_the_pool_above_its_own_measured_range():
    """The failure that made banning tennis look reasonable.

    `games_won_for` has 9,286 settled rows and no bucket above 0.825; its best
    measured bucket realises 0.756. The global pool — 74,574 rows, almost all
    football counting markets — says 0.905 at p=0.90. Falling through put 12
    tennis legs on the 2026-09-21 list at a confidence this market has never
    once been observed to deliver.
    """
    from bet.sofa.confidence import Calibration

    cal = Calibration(
        pooled={"0.900-0.925": {"realised_lo95": 0.905, "n": 74574}},
        by_market={
            "games_won_for": {"0.800-0.825": {"realised_lo95": 0.7159, "n": 480}}
        },
    )
    # Inside its own range: served from its own curve.
    got = cal.realised("games_won_for", 0.81)
    assert got is not None and got[1] == "market:games_won_for"
    # Above the top of its measured range: refused, not borrowed.
    assert cal.realised("games_won_for", 0.90) is None
    # A market with no curve at all still falls back.
    assert cal.realised("something_else", 0.90) == (0.905, "pooled", 74574)


def test_tennis_falls_back_to_tennis_not_to_football():
    """The global pool is ~95% football counts. Tennis has 56,581 rows of its
    own and is measurably less reliable at the top — 0.851 against the pool's
    0.907 in the 0.900-0.925 bucket."""
    from bet.sofa.confidence import Calibration

    cal = Calibration(
        pooled={"0.900-0.925": {"realised_lo95": 0.9052, "n": 74574}},
        by_market={},
        pooled_by_sport={
            "tennis": {"0.900-0.925": {"realised_lo95": 0.8310, "n": 1330}}
        },
    )
    # A count market (NB): sets_total was used here until 2026-09-23, when an
    # empirical market with no curve of its own stopped borrowing the pool
    # above the measured empirical ceiling - see
    # test_tennis_set_totals_and_tiebreaks::test_an_unmeasured_market_is_capped.
    assert cal.realised("aces_total", 0.91, "tennis") == (0.8310, "pooled:tennis", 1330)
    # No sport given, or a sport with no pool: the global one, as before.
    assert cal.realised("aces_total", 0.91) == (0.9052, "pooled", 74574)
    assert cal.realised("aces_total", 0.91, "handball") == (0.9052, "pooled", 74574)


def test_an_empirical_frequency_market_is_calibratable_not_banned():
    """`uses_empirical_frequency` markets were refused outright, which removed
    the largest tennis market from the path that builds the coupon while the
    VALUE path was made of it."""
    from bet.sofa.engine import uses_empirical_frequency, uses_poisson_floor

    assert uses_empirical_frequency("games_won_for")
    # The surviving gate in run_confidence refuses only markets with no model
    # at all — neither a count nor an empirical frequency.
    assert not (
        not uses_poisson_floor("games_won_for")
        and not uses_empirical_frequency("games_won_for")
    )


def test_both_paths_share_one_sample_freshness_rule():
    """How far back a sample reaches and whether it is still current are two
    questions. Until 2026-09-21 CONFIDENCE asked only the first (180 days of
    reach) and the coupon only the second (60 days of staleness), so the PDF —
    the artifact actually staked — was the more permissive of the two."""
    import scripts.sofa.run_confidence as rc
    from bet.sofa.confidence import MAX_BUILDER_SAMPLE_AGE_DAYS
    from bet.sofa.coupon import MAX_SAMPLE_AGE_DAYS

    # One constant, imported, not a second copy of the number.
    assert rc.MAX_SAMPLE_AGE_DAYS is MAX_SAMPLE_AGE_DAYS
    # And they measure different things, so both still exist.
    assert MAX_SAMPLE_AGE_DAYS < MAX_BUILDER_SAMPLE_AGE_DAYS


class TestOverroundAndSingles:
    """Singles exist because the PDF could not render one.

    `build_coupon_pdf.py` staked only Bet Builders, which need two legs of
    DIFFERENT quantity families in the SAME match. On 2026-09-22 the day held
    37 qualifying legs and produced 0 builders, so the operator got a blank
    page. They are ranked by confidence rather than by `leg_ev` because that
    ordering is measured to be inverted — see MAX_OVERROUND.
    """

    def test_overround_is_the_two_sided_margin(self) -> None:
        # A perfectly fair two-way market prices both sides at 2.00.
        assert overround(2.0, 2.0) == pytest.approx(0.0, abs=1e-9)
        # Superbet's typical corners ladder sits near 8.6%.
        assert overround(1.28, 3.25) == pytest.approx(0.08894, abs=1e-4)

    def test_a_one_sided_rung_cannot_be_measured(self) -> None:
        """The missing side is exactly where the margin would show, so it is
        refused rather than assumed fair."""
        assert overround(1.28, None) is None
        assert overround(None, 3.25) is None
        assert overround(1.28, 1.0) is None
        assert not single_is_fairly_priced(overround(1.28, None))

    def test_the_threshold_is_the_one_place_outcomes_separate(self) -> None:
        assert single_is_fairly_priced(0.086) is True
        assert single_is_fairly_priced(0.105) is True
        assert single_is_fairly_priced(0.106) is False
        # Superbet's goals ladders run to 11.8% and are meant to fall out.
        assert single_is_fairly_priced(0.118) is False

    def test_singles_are_not_ranked_by_leg_ev(self) -> None:
        """The regression this whole section exists for.

        `confidence` is a step function, so within one calibration bucket
        `leg_ev = confidence * odds - 1` is a strictly increasing function of
        the price. Ranking by it puts the longest price first, and the
        longest-priced third of a bucket is measured to hit LESS often. The
        two legs below share a bucket; EV prefers the 1.30, confidence and the
        tie-break prefer the 1.10.
        """
        cheap = {"confidence": 0.90, "offered_odds": 1.10, "overround": 0.085}
        dear = {"confidence": 0.90, "offered_odds": 1.30, "overround": 0.085}
        cheap["leg_ev"] = cheap["confidence"] * cheap["offered_odds"] - 1
        dear["leg_ev"] = dear["confidence"] * dear["offered_odds"] - 1
        assert dear["leg_ev"] > cheap["leg_ev"]

        by_ev = sorted([cheap, dear], key=lambda r: -r["leg_ev"])
        by_singles = sorted(
            [cheap, dear], key=lambda r: (-r["confidence"], r["offered_odds"])
        )
        assert by_ev[0] is dear
        assert by_singles[0] is cheap, "singles must not inherit the EV ordering"
