"""Every arithmetic claim the pipeline makes, asserted as a property.

Written after the 2026-09-01 losses, sweeping the whole computation surface
rather than the one path that failed. The bugs it locks out were all found by
running these properties against real artifacts and seeing which came back
false -- the sheet had looked finished through all of them:

* ``_score_grid`` truncated the scoreline enumeration at 11 goals a side while
  its own comment claimed the omitted tail was ~1e-9. At the top of the fitted
  band it is 2.4e-3, so the grid summed to 0.9952 and ``fit_match_lambdas``
  charged every high-scoring fixture half a percent for being there.
* ``count_model_central``/``count_model_bound`` read Phi at the line itself,
  which on a whole-number line hands half the push mass to each side.
* ``_edge`` -- the ranking key for a whole group of singles, printed to the
  operator as "Przewaga" -- subtracted a devigged market probability from
  ``p_low``, a lower bound. Two different kinds of quantity.
* ``_cross_provider_agreement`` returned AGREE on one corroborated match out of
  twenty-three, and AGREE is what buys the CALL tier.
* ``_is_absent_not_zero`` passed a payload reporting six goals with zero shots
  on target, because not *all* of its values were zero.

The style throughout is to assert the property over a spread of inputs rather
than to pin one number, because a pinned number tells you the code changed and
a property tells you which claim it broke.
"""
from __future__ import annotations

import math
import statistics

import pytest

from bet.simple_stats.analyze import (
    MIN_CORROBORATED_MATCHES,
    _sample_dispersion,
    _winning_boundary,
    compute_hit_rate,
    corroborated_matches,
    count_model_bound,
    count_model_central,
    wilson_lower_bound,
)
from bet.simple_stats.contracts import ProviderValue
from bet.simple_stats.bet_builder_draft import TIER_MARGIN as COUPON_TIER_MARGIN
from bet.simple_stats.providers import _is_absent_not_zero
from bet.simple_stats.slip_audit import (
    _LAMBDA_MAX,
    _LAMBDA_MIN,
    _SCORE_CEILING,
    _score_grid,
    _truncated_pmf,
    fit_match_lambdas,
    half_lambdas,
    implied_probability,
    poisson_pmf,
    probability_team_scores,
    remove_vig,
)

# Real scoped samples from runs/2026-09-01/, plus degenerate shapes the
# generated grid does not reach on its own: a single observation, an all-zero
# sample, and a two-value sample with zero variance.
SAMPLES = [
    [2.0, 4.0, 3.0, 2.0, 3.0],                                # Sheffield corners
    [1.0, 1.0, 2.0, 3.0, 3.0],                                # Preston SOT
    [9.0, 8.0, 8.0, 10.0, 6.0],                               # Birmingham shots
    [6.0, 6.0, 6.0, 6.0, 7.0, 7.0],                           # Torino/Monza corners
    [8.0, 11.0, 9.0, 12.0, 8.0, 8.0, 8.0, 8.0, 10.0, 14.0],   # Lincoln SOT
    [24.0, 22.0, 26.0, 25.0, 21.0, 27.0, 23.0, 24.0],
    [1.0, 2.0, 0.0, 1.0, 2.0, 1.0, 1.0, 2.0],
    [0.0],
    [0.0, 0.0, 0.0],
    [5.0, 5.0],
    [1.0],
]
# Half lines, and whole lines so the push path is exercised on purpose.
LINES = [0.5, 1.5, 2.5, 3.5, 4.5, 7.5, 11.5, 15.5, 25.5, 1.0, 2.0, 3.0, 8.0, 21.0]


# --- compute_hit_rate -------------------------------------------------------


@pytest.mark.parametrize("values", SAMPLES)
@pytest.mark.parametrize("line", LINES)
def test_every_observation_is_a_hit_a_miss_or_a_push(values, line):
    """The accounting identity. If it fails, some observation was counted twice
    or dropped, and ``sample_size`` is what ``_confidence`` reads to award a
    tier."""
    over_hits, over_settled, over_pushes = compute_hit_rate(values, line, "OVER")
    under_hits, under_settled, under_pushes = compute_hit_rate(values, line, "UNDER")
    assert over_hits + under_hits + over_pushes == len(values)
    assert over_pushes == under_pushes
    assert over_settled == under_settled == len(values) - over_pushes
    # The two sides partition the settled sample exactly.
    assert over_hits + under_hits == over_settled


def test_a_push_is_a_hit_for_neither_side():
    assert compute_hit_rate([8.0, 10.0, 12.0], 10.0, "OVER") == (1, 2, 1)
    assert compute_hit_rate([8.0, 10.0, 12.0], 10.0, "UNDER") == (1, 2, 1)


# --- wilson_lower_bound -----------------------------------------------------


def test_wilson_is_a_bound_below_the_point_estimate_and_inside_the_unit_interval():
    for n in range(1, 40):
        previous = -1.0
        for hits in range(n + 1):
            bound = wilson_lower_bound(hits, n)
            assert 0.0 <= bound <= 1.0
            assert bound <= hits / n + 1e-12
            # Monotone in hits at fixed n: more successes can never lower it.
            assert bound >= previous - 1e-12
            previous = bound


def test_wilson_rewards_evidence_at_a_fixed_rate():
    assert wilson_lower_bound(3, 4) < wilson_lower_bound(9, 12) < wilson_lower_bound(75, 100)


def test_wilson_on_an_empty_sample_is_the_floor_not_a_missing_value():
    assert wilson_lower_bound(0, 0) == 0.0


# --- the count model --------------------------------------------------------


@pytest.mark.parametrize("values", SAMPLES)
@pytest.mark.parametrize("line", LINES)
def test_both_model_probabilities_stay_in_the_unit_interval(values, line):
    for direction in ("OVER", "UNDER"):
        assert 0.0 <= count_model_central(values, line, direction) <= 1.0
        assert 0.0 <= count_model_bound(values, line, direction) <= 1.0


@pytest.mark.parametrize("values", SAMPLES)
@pytest.mark.parametrize("line", LINES)
def test_the_bound_is_never_more_confident_than_the_centre(values, line):
    """``count_model_bound`` pushes the fitted mean against the bet, so it must
    come out at or below ``count_model_central`` on both sides. If it ever came
    out above, the "conservative" instrument would be the optimistic one."""
    for direction in ("OVER", "UNDER"):
        assert (
            count_model_bound(values, line, direction)
            <= count_model_central(values, line, direction) + 1e-12
        )


@pytest.mark.parametrize("values", SAMPLES)
@pytest.mark.parametrize("line", LINES)
def test_the_two_sides_of_a_line_never_sum_past_certainty(values, line):
    """On a half line the central probabilities partition the outcome exactly.
    On a whole line they must sum to *at most* one, the shortfall being the
    push mass -- which is only positive when the fitted distribution actually
    puts mass on the line. A sample of {0,0,0} against a line of 1.0 has none,
    so 1.0 is the right answer there and a strict inequality would be wrong.
    ``test_a_whole_line_excludes_the_push_from_both_sides`` makes the strict
    claim on a sample that straddles its line.

    Both bounds sum to at most one whatever the line, because each is
    separately pushed against its own bet.
    """
    central = sum(count_model_central(values, line, d) for d in ("OVER", "UNDER"))
    bounds = sum(count_model_bound(values, line, d) for d in ("OVER", "UNDER"))
    assert bounds <= 1.0 + 1e-12
    assert central <= 1.0 + 1e-12
    if not float(line).is_integer():
        assert central == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("values", SAMPLES)
def test_the_model_is_monotone_in_the_line(values):
    """The property Wilson cannot supply, and the whole reason this instrument
    exists: a further-out UNDER is safer and a further-out OVER is not."""
    ordered = sorted(LINES)
    under = [count_model_bound(values, line, "UNDER") for line in ordered]
    over = [count_model_bound(values, line, "OVER") for line in ordered]
    assert under == sorted(under)
    assert over == sorted(over, reverse=True)


@pytest.mark.parametrize("values", SAMPLES)
@pytest.mark.parametrize("line", LINES)
def test_combining_the_two_instruments_can_only_lower_confidence(values, line):
    """``p_low = min(wilson, model)``. Asserted as a property because it is the
    safety guarantee of the whole change: replaying the frozen 2026-08-31
    fixture moved 251 rows and every one of them down."""
    for direction in ("OVER", "UNDER"):
        hits, settled, _ = compute_hit_rate(values, line, direction)
        if settled == 0:
            continue
        empirical = wilson_lower_bound(hits, settled)
        combined = min(empirical, count_model_bound(values, line, direction))
        assert combined <= empirical + 1e-12


@pytest.mark.parametrize("values", SAMPLES)
def test_dispersion_never_falls_below_the_poisson_floor(values):
    """A count process has variance at least its mean. A sample tighter than
    that is a short sample, not a tame market -- Torino/Monza's six corner
    observations had variance 0.27 against a mean of 6.33 and the match
    returned 16."""
    assert _sample_dispersion(values) >= statistics.fmean(values) - 1e-12
    if len(values) > 1:
        assert _sample_dispersion(values) >= statistics.variance(values) - 1e-12


# --- the continuity correction ----------------------------------------------


@pytest.mark.parametrize("line", LINES)
def test_the_winning_boundary_agrees_with_the_push_rule(line):
    """``_winning_boundary`` and ``compute_hit_rate`` must classify the same
    integers as wins, or the model is pricing a different bet than the sample
    is counting.

    This is the cross-check that makes the boundary arithmetic trustworthy: it
    is derived from the settlement rule rather than asserted alongside it.
    """
    for direction in ("OVER", "UNDER"):
        boundary = _winning_boundary(line, direction)
        for value in range(0, 40):
            hits, _, pushes = compute_hit_rate([float(value)], line, direction)
            settles_as_win = hits == 1
            assert pushes == (1 if float(value) == line else 0)
            model_says_win = (
                value < boundary if direction == "UNDER" else value > boundary
            )
            assert settles_as_win == model_says_win, (
                f"line {line} {direction}: value {value} settles as "
                f"{'win' if settles_as_win else 'not a win'} but the boundary "
                f"{boundary} says otherwise"
            )


def test_a_half_line_leaves_the_boundary_where_it_was():
    """The correction must be inert on the lines this pipeline mostly prices,
    or it would silently reprice every football row."""
    for line in (0.5, 4.5, 9.5, 12.5):
        assert _winning_boundary(line, "OVER") == line
        assert _winning_boundary(line, "UNDER") == line


def test_a_whole_line_excludes_the_push_from_both_sides():
    """UNDER 21 wins on 20 or fewer; OVER 21 wins on 22 or more. Reading Phi at
    21 itself would give half of P(exactly 21) to each side."""
    assert _winning_boundary(21.0, "UNDER") == 20.5
    assert _winning_boundary(21.0, "OVER") == 21.5
    values = [18.0, 20.0, 21.0, 22.0, 24.0, 21.0, 19.0, 23.0]
    total = sum(count_model_central(values, 21.0, d) for d in ("OVER", "UNDER"))
    # The gap is the push mass the two sides must not claim between them.
    assert 0.0 < 1.0 - total < 0.5


# --- slip_audit: the market's own arithmetic --------------------------------


@pytest.mark.parametrize("lam", [0.15, 0.5, 1.0, 1.5, 2.5, 3.5, 4.5])
def test_the_poisson_pmf_is_a_distribution(lam):
    assert sum(poisson_pmf(k, lam) for k in range(200)) == pytest.approx(1.0, abs=1e-12)


def test_a_zero_rate_puts_all_its_mass_on_zero():
    assert poisson_pmf(0, 0.0) == 1.0
    assert poisson_pmf(3, 0.0) == 0.0


@pytest.mark.parametrize("lam", [_LAMBDA_MIN, 1.2, 2.5, _LAMBDA_MAX])
def test_the_truncated_pmf_keeps_essentially_all_of_the_mass(lam):
    """Truncation is what the ceiling is *for*, so the omitted mass is asserted
    directly rather than trusted to a constant. The old ceiling of 11 goals
    omitted 2.4e-3 at lambda 4.5 while claiming 1e-9."""
    pmf = _truncated_pmf(lam)
    assert sum(pmf) == pytest.approx(1.0, abs=1e-12)
    assert len(pmf) <= _SCORE_CEILING + 1


@pytest.mark.parametrize(
    "lam_home, lam_away",
    [(0.15, 0.15), (1.5, 1.2), (2.5, 2.5), (4.5, 0.15), (4.5, 4.5)],
)
def test_the_scoreline_grid_is_a_distribution_at_every_fitted_rate(lam_home, lam_away):
    """Including at the top of the band, which is where it used to fail. The
    1X2 terms of ``fit_match_lambdas``'s error are compared against devigged
    targets that sum to exactly one, so a grid summing to 0.9952 charged the
    fit half a percent for nothing."""
    home, draw, away, totals = _score_grid(lam_home, lam_away)
    assert home + draw + away == pytest.approx(1.0, abs=1e-9)
    assert sum(totals) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize(
    "lam_home, lam_away",
    [(0.15, 0.15), (1.5, 1.2), (2.5, 2.5), (4.5, 0.15), (4.5, 4.5)],
)
def test_the_totals_distribution_has_the_mean_it_should(lam_home, lam_away):
    """The sum of two independent Poissons is Poisson with the summed rate, so
    the grid's own mean is a closed-form check on the convolution."""
    _, _, _, totals = _score_grid(lam_home, lam_away)
    mean = sum(index * p for index, p in enumerate(totals))
    assert mean == pytest.approx(lam_home + lam_away, abs=1e-6)


def test_the_grid_never_indexes_past_its_totals_array():
    """The array is sized from the two truncation lengths, so a mismatch would
    be an IndexError rather than a wrong number. Exercised at the extremes."""
    for lam_home in (_LAMBDA_MIN, _LAMBDA_MAX):
        for lam_away in (_LAMBDA_MIN, _LAMBDA_MAX):
            _score_grid(lam_home, lam_away)


@pytest.mark.parametrize(
    "lam_home, lam_away",
    [(1.6, 1.1), (1.0, 1.0), (2.2, 0.8), (0.6, 0.5), (3.0, 2.0)],
)
def test_the_lambda_fit_recovers_the_rates_it_was_built_from(lam_home, lam_away):
    """Round-trip: turn known rates into consensus prices, then refit. This is
    the only end-to-end check on ``fit_match_lambdas``, and it is what would
    have caught the truncation bias as a systematic pull toward lower rates."""
    home, draw, away, totals = _score_grid(lam_home, lam_away)
    over = 1.0 - (totals[0] + totals[1] + totals[2])
    vig = 1.05
    fitted_home, fitted_away = fit_match_lambdas(
        home_win=vig / home,
        draw=vig / draw,
        away_win=vig / away,
        over_25=vig / over,
        under_25=vig / (1.0 - over),
    )
    assert fitted_home == pytest.approx(lam_home, abs=0.05)
    assert fitted_away == pytest.approx(lam_away, abs=0.05)


def test_the_fit_stays_inside_its_own_declared_band():
    """Clamping is honest where extrapolating is not, so a fixture priced far
    outside the band must come back clamped rather than wild."""
    for prices in ((1.01, 40.0, 60.0), (60.0, 40.0, 1.01)):
        home, draw, away = prices
        for lam in fit_match_lambdas(home_win=home, draw=draw, away_win=away):
            assert _LAMBDA_MIN <= lam <= _LAMBDA_MAX


@pytest.mark.parametrize(
    "prices", [(2.0, 2.0), (1.5, 3.0), (2.5, 3.4, 2.9), (1.05, 30.0), (1.9, 1.9)]
)
def test_devigging_returns_a_distribution_strictly_under_the_raw_prices(prices):
    devigged = remove_vig(*prices)
    assert sum(devigged) == pytest.approx(1.0, abs=1e-12)
    # Every devigged probability sits at or below the raw 1/price it came from,
    # because the overround being removed is non-negative. Reading 1/price as a
    # probability flatters every bet, which is the asymmetry remove_vig exists
    # to remove.
    if sum(implied_probability(p) for p in prices) >= 1.0:
        for price, probability in zip(prices, devigged):
            assert probability <= implied_probability(price) + 1e-12


def test_devigging_one_price_is_refused_rather_than_guessed():
    with pytest.raises(ValueError):
        remove_vig(1.90)


def test_a_price_at_or_below_evens_is_refused():
    for price in (1.0, 0.5, 0.0, -2.0):
        with pytest.raises(ValueError):
            implied_probability(price)


def test_the_half_split_conserves_the_match_rate_and_favours_the_second_half():
    """Measured over 7,516 fixtures: second halves score more. An even split
    would misprice every first-half market."""
    for total in (0.5, 1.5, 3.0, 4.5):
        first, second = half_lambdas(total)
        assert first + second == pytest.approx(total, abs=1e-12)
        assert second > first


def test_a_team_scoring_probability_is_a_probability():
    previous = -1.0
    for lam in (0.15, 0.5, 1.0, 2.0, 4.5):
        p = probability_team_scores(lam)
        assert 0.0 < p < 1.0
        assert p > previous
        previous = p


# --- corroboration ----------------------------------------------------------


def _pv(provider: str, value: float, *, day: str = "2026-08-22", match_id: str = "m") -> ProviderValue:
    return ProviderValue(
        provider=provider, match_id=match_id, match_date=day,
        opponent="Real Betis", value=value, observed_at="2026-08-25T00:00:00+00:00",
    )


def test_corroboration_counts_matches_and_not_observations():
    """Three providers on one match is one corroborated match. The question the
    threshold answers is how much of the sample a second source has verified,
    and one match out of ten is a tenth of it however many providers cover it.
    """
    one_match = [
        _pv("bzzoiro", 9.0, match_id="a"),
        _pv("espn-football", 9.0, match_id="b"),
        _pv("highlightly", 9.0, match_id="c"),
    ]
    assert corroborated_matches("corners_total", one_match) == 1


def test_a_lone_corroborated_match_does_not_corroborate_a_sample():
    """The 2026-09-01 hole. Nineteen samples took AGREE on exactly one
    corroborated match, sixteen of them tennis ``total_games`` where two
    providers overlapped on 1 match out of 23 -- and AGREE is what
    ``tier_for_row`` reads to hand out CALL, the tier with the thinner price
    margin."""
    from bet.simple_stats.analyze import _cross_provider_agreement

    sample = [_pv("bzzoiro", 9.0, day=f"2026-08-{d:02d}", match_id=f"a{d}") for d in range(1, 12)]
    sample.append(_pv("espn-football", 9.0, day="2026-08-01", match_id="e1"))
    assert corroborated_matches("corners_total", sample) == 1
    assert _cross_provider_agreement("corners_total", sample) == "SINGLE_SOURCE"


def test_enough_corroborated_matches_still_reach_agree():
    """The gate must not become a ban on corroboration ever counting."""
    from bet.simple_stats.analyze import _cross_provider_agreement

    sample: list[ProviderValue] = []
    for day in range(1, 1 + MIN_CORROBORATED_MATCHES):
        sample.append(_pv("bzzoiro", 9.0, day=f"2026-08-{day:02d}", match_id=f"a{day}"))
        sample.append(_pv("espn-football", 9.0, day=f"2026-08-{day:02d}", match_id=f"e{day}"))
    assert corroborated_matches("corners_total", sample) == MIN_CORROBORATED_MATCHES
    assert _cross_provider_agreement("corners_total", sample) == "AGREE"


def test_one_conflicting_match_is_still_enough_for_disagree():
    """The asymmetry is deliberate and must stay: a single provider conflict is
    a reason to distrust a sample, while a single provider agreement is not a
    reason to trust it. Only the permissive direction needed a floor."""
    from bet.simple_stats.analyze import _cross_provider_agreement

    sample = [
        _pv("bzzoiro", 9.0, day="2026-08-01", match_id="a1"),
        _pv("espn-football", 4.0, day="2026-08-01", match_id="e1"),
    ]
    assert corroborated_matches("corners_total", sample) == 1
    assert _cross_provider_agreement("corners_total", sample) == "DISAGREE"


# --- provider payload sanity ------------------------------------------------


def test_a_payload_that_scored_without_shooting_is_refused():
    """The real one: highlightly on match 1328313068 in the 2026-09-01 dossier,
    six goals with zero shots and zero shots on target. It passed every gate
    there was -- not all its values were zero (goals and cards were not), and
    it carried no fouls key for ``_ZERO_IMPOSSIBLE_MARKETS``. bzzoiro produced
    one of the same shape on 2026-08-31."""
    assert _is_absent_not_zero(
        {
            "goals_total": 6.0,
            "shots_on_target_total": 0.0,
            "shots_total": 0.0,
            "corners_total": 0.0,
            "cards_total": 2.0,
            "possession": 100.0,
        },
        "highlightly",
    )


def test_an_own_goal_is_not_treated_as_an_impossible_payload():
    """Some feeds do not attribute an own goal to the scoring side as a shot on
    target, so goals may legitimately exceed shots on target by one. The gate
    has to tolerate the accounting convention and refuse the impossibility."""
    assert not _is_absent_not_zero(
        {"goals_for": 1.0, "shots_on_target_for": 0.0, "shots_for": 8.0}, "bzzoiro"
    )
    assert _is_absent_not_zero(
        {"goals_for": 2.0, "shots_on_target_for": 0.0, "shots_for": 8.0}, "bzzoiro"
    )


def test_a_goalless_draw_with_absent_shot_data_is_refused_even_with_a_card():
    """The all-values-zero test passed this the moment anything non-zero was in
    the payload, which a single yellow card supplies. Restricting the test to
    counted-play metrics is what closes it -- and goals and cards stay out of
    that set, because zero of either is an ordinary result."""
    assert _is_absent_not_zero(
        {"goals_total": 0.0, "cards_total": 3.0, "corners_total": 0.0, "shots_total": 0.0},
        "espn-football",
    )


def test_a_real_match_with_no_corners_is_not_refused():
    """0 corners happens. The gate must key on impossibility, not on rarity, or
    it starts deleting the data it is there to protect."""
    assert not _is_absent_not_zero(
        {"corners_total": 0.0, "shots_total": 11.0, "fouls_total": 14.0}, "bzzoiro"
    )


def test_an_empty_payload_is_not_an_impossible_one():
    """Nothing to judge is not evidence of a fault, and returning True here
    would drop every provider that served no stats at all into the same bucket
    as one that served nonsense."""
    assert not _is_absent_not_zero({}, "bzzoiro")


# --- the price arithmetic the operator reads --------------------------------


def test_the_required_price_is_the_reciprocal_of_the_floor_times_the_tier_margin():
    """``min_acceptable_odds`` is the only number in the file the operator acts
    on directly. Asserted as the identity rather than trusted, because a tier
    whose margin drifted would be undetectable from the artifact."""
    for p_low in (0.50, 0.55, 0.61, 0.72, 0.80, 0.95):
        fair = 1.0 / p_low
        for tier, margin in COUPON_TIER_MARGIN.items():
            minimum = round(fair * margin, 4)
            assert minimum > fair or margin == 1.0
            # Taking exactly the minimum price returns the margin over fair.
            assert minimum * p_low == pytest.approx(margin, abs=1e-3)
            assert tier in ("CALL", "LEAN")


def test_a_stronger_row_demands_a_shorter_price():
    """Monotonicity of the threshold in the evidence. If this inverted, the
    sheet would be asking for more money on the rows it believed most."""
    previous = float("inf")
    for p_low in (0.50, 0.60, 0.70, 0.80, 0.90):
        minimum = (1.0 / p_low) * COUPON_TIER_MARGIN["LEAN"]
        assert minimum < previous
        previous = minimum


def test_devigging_a_two_sided_pair_is_the_same_arithmetic_everywhere():
    """Three places devig a pair of prices: ``market_context``'s
    same-bookmaker probability, ``coupons``' ``superbet_implied``, and the
    ladder read. They are separate implementations over different input shapes,
    so the *arithmetic* is pinned here in one place -- if one of them drifts,
    this is the number it drifted from."""
    for under, over in ((2.70, 1.40), (1.90, 1.90), (1.32, 3.05), (2.50, 1.55)):
        overround = 1.0 / under + 1.0 / over
        implied_under = (1.0 / under) / overround
        implied_over = (1.0 / over) / overround
        assert implied_under + implied_over == pytest.approx(1.0, abs=1e-12)
        assert remove_vig(under, over) == pytest.approx(
            (implied_under, implied_over), abs=1e-12
        )
        # The overround these markets carry is 2-10%; outside that band the
        # pair is not a real two-way market and the devig means nothing.
        assert 1.0 < overround < 1.15


def test_the_standard_normal_cdf_matches_its_own_tails():
    """``count_model_central`` is Phi, and Phi has properties worth checking
    rather than assuming: symmetry about zero, and the 95% point that has to
    line up with the 1.96 both instruments use."""
    from bet.simple_stats.analyze import _standard_normal_cdf as phi

    assert phi(0.0) == pytest.approx(0.5, abs=1e-12)
    for z in (0.25, 1.0, 1.96, 3.0):
        assert phi(z) + phi(-z) == pytest.approx(1.0, abs=1e-12)
    assert phi(1.96) == pytest.approx(0.975, abs=5e-4)
    assert phi(-1.96) == pytest.approx(0.025, abs=5e-4)


# --- a specification gap, pinned rather than silently resolved --------------


def test_a_thin_uncorroborated_sample_is_weak_not_lean():
    """The gap in ``bet-analyst.md``'s tier table, closed 2026-09-02.

    The table reads: CALL for ``n>=8`` AGREE; LEAN for ``n>=8`` single-source
    **or** ``n>=5`` AGREE; WEAK for ``n`` 3-4; DROP below that. An ``n`` of 5-7
    that nothing corroborates matched none of those conditions -- above WEAK's
    stated range and below both of LEAN's -- and ``tier_for_row`` resolved it
    the permissive way, toward LEAN, which reaches the coupon while WEAK does
    not. That is what admitted the three largest losses of 2026-09-01:
    Sheffield United corners, Preston shots on target and Birmingham shots were
    all n=5 SINGLE_SOURCE.

    It resolves to WEAK now, and both the code's docstring and the agent
    doc's table say so. This test is the reason it cannot drift back: the
    permissive reading is the one a reader re-deriving the table from ``n``
    alone would naturally write.
    """
    from bet.simple_stats.bet_builder_draft import tier_for_row
    from bet.simple_stats.contracts import StatsSheetRow

    def row(sample_size: int, agreement: str) -> StatsSheetRow:
        return StatsSheetRow(
            event_id="e", sport="football", market="corners_for", line=4.5,
            direction="UNDER", team_name="Sheffield United", hits=sample_size,
            sample_size=sample_size, hit_rate=1.0, p_low=0.5655, mean=2.8,
            median=3.0, dispersion=2.8 ** 0.5, cross_provider_agreement=agreement,
            confidence="MEDIUM", data_quality="READY",
        )

    # The gap, and the reading the code now takes.
    for n in (5, 6, 7):
        assert tier_for_row(row(n, "SINGLE_SOURCE")) == "WEAK"
        assert tier_for_row(row(n, "DISAGREE")) == "WEAK"
        # Corroboration is what buys LEAN at this depth -- not the sample size,
        # which is identical in all three of these.
        assert tier_for_row(row(n, "AGREE")) == "LEAN"
    # The parts of the table that are unambiguous, so a change to the gap
    # cannot quietly move these too.
    assert tier_for_row(row(4, "SINGLE_SOURCE")) == "WEAK"
    assert tier_for_row(row(4, "AGREE")) == "WEAK"
    assert tier_for_row(row(2, "AGREE")) == "DROP"
    assert tier_for_row(row(12, "AGREE")) == "CALL"
    assert tier_for_row(row(12, "SINGLE_SOURCE")) == "LEAN"
    assert tier_for_row(row(12, "DISAGREE")) == "LEAN"


# --- one policy constant, not six copies ------------------------------------


def test_the_tier_margins_have_exactly_one_definition():
    """They were written out in six places: ``bet_builder_draft.TIER_MARGIN``,
    ``superbet_offer.TIER_MARGINS``, and three inline literals inside
    ``build_coupons`` -- the ``require_superbet_value`` probe, the body that
    fills ``min_acceptable_odds``, and ``_superbet_surplus`` for the ranking.

    All six agreed, which was luck. Changing CALL's 1.05 would have left the
    coupon file internally inconsistent: the price printed on a single, the
    price its VALUE verdict was decided against, and the price its ranking used
    would each have come from a different copy.
    """
    from bet.simple_stats import bet_builder_draft, superbet_offer

    assert superbet_offer.TIER_MARGINS is bet_builder_draft.TIER_MARGIN
    assert bet_builder_draft.TIER_MARGIN == {"CALL": 1.05, "LEAN": 1.10}


def test_the_three_coupon_price_sites_cannot_diverge():
    """``required_price`` is the single implementation the three former inline
    copies now share, and it has to agree with the one in ``superbet_offer``
    that the sheet's own column is built from."""
    from bet.simple_stats.contracts import StatsSheetRow
    from bet.simple_stats.coupons import required_price
    from bet.simple_stats.superbet_offer import min_acceptable_odds

    for p_low in (0.50, 0.61, 0.72, 0.85):
        row = StatsSheetRow(
            event_id="e", sport="football", market="corners_total", line=9.5,
            direction="UNDER", hits=9, sample_size=12, hit_rate=0.75, p_low=p_low,
            mean=9.1, median=9.0, cross_provider_agreement="AGREE",
            confidence="HIGH", data_quality="READY",
        )
        for tier in ("CALL", "LEAN"):
            assert required_price(row, tier) == min_acceptable_odds(row, tier)


# --- the context flags read the same sample the statistics do ---------------


def test_the_xg_flag_reads_a_scoped_and_deduplicated_sample():
    """It used to read the raw dossier bucket, so pre-season friendlies,
    previous-season matches and multi-provider duplicates all fed the
    "actual goals per game" it compares against season xG.

    The fixture below is the failure in miniature: one league match at 0 goals
    and three July friendlies at 3 apiece. Raw, that averages 2.25/game and
    clears the 0.75 gap against a 1.00/game season xGF, firing
    ARGUES_AGAINST and stepping the row's tier down. Scoped, it averages 0.00
    and the flag must stay silent.
    """
    from bet.simple_stats.context_flags import context_flags_for_row
    from bet.simple_stats.contracts import (
        EventDossierV1,
        MetricObservation,
        StatsSheetRow,
        TeamSeasonForm,
    )

    # 2026-07-19 is pinned as a friendly in config/observation_scope.json via
    # its competition id; anything scope_values drops would do here.
    league = ProviderValue(
        provider="bzzoiro", match_id="L1", match_date="2026-08-29",
        opponent="Cardiff City", value=0.0,
        observed_at="2026-09-01T00:00:00+00:00",
        competition_id="league-1", season_id="2026",
    )
    stale = [
        ProviderValue(
            provider="bzzoiro", match_id=f"S{i}", match_date=f"2025-07-{10 + i:02d}",
            opponent=f"Friendly {i}", value=3.0,
            observed_at="2026-09-01T00:00:00+00:00",
            competition_id="league-1", season_id="2025",
        )
        for i in range(3)
    ]
    dossier = EventDossierV1(
        event_id="e", sport="football", readiness="READY",
        team_a_name="Sheffield United", team_b_name="Bolton Wanderers",
        metrics={
            "goals_for": MetricObservation(
                canonical_name="goals_for", team_a_l10=[league, *stale],
            )
        },
        season_form=[TeamSeasonForm(side="home", provider_team_id="t1", xgf=5.0, xg_games=5)],
    )
    row = StatsSheetRow(
        event_id="e", sport="football", market="goals_for", line=0.5,
        direction="OVER", team_name="Sheffield United", hits=1, sample_size=1,
        hit_rate=1.0, p_low=0.2, mean=0.0, median=0.0,
        cross_provider_agreement="SINGLE_SOURCE", confidence="LOW",
        data_quality="READY",
    )
    # Raw, the bucket would average 2.25/game against a 1.00/game xGF -- a gap
    # of 1.25, well past the 0.75 threshold.
    assert statistics.fmean(pv.value for pv in [league, *stale]) == pytest.approx(2.25)
    # Scoped, the previous-season matches are gone and there is nothing to flag.
    assert not [
        flag for flag in context_flags_for_row(row, dossier)
        if flag.source == "season_form"
    ]


def test_the_xg_flag_still_fires_on_a_sample_that_survives_scoping():
    """The positive control for the test above. Without it that one passes
    whether the flag was fixed or simply broken, and a flag that never fires
    would look identical to a flag that fires correctly."""
    from bet.simple_stats.context_flags import context_flags_for_row
    from bet.simple_stats.contracts import (
        EventDossierV1,
        MetricObservation,
        StatsSheetRow,
        TeamSeasonForm,
    )

    # Same shape as the scoped-out fixture, but every match is in the current
    # season of the same competition, so scope_values keeps all four and the
    # mean really is 2.25/game against a 1.00/game xGF.
    bucket = [
        ProviderValue(
            provider="bzzoiro", match_id=f"L{i}", match_date=f"2026-08-{10 + i:02d}",
            opponent=f"Opponent {i}", value=value,
            observed_at="2026-09-01T00:00:00+00:00",
            competition_id="league-1", season_id="2026",
        )
        for i, value in enumerate((0.0, 3.0, 3.0, 3.0))
    ]
    dossier = EventDossierV1(
        event_id="e", sport="football", readiness="READY",
        team_a_name="Sheffield United", team_b_name="Bolton Wanderers",
        metrics={
            "goals_for": MetricObservation(canonical_name="goals_for", team_a_l10=bucket)
        },
        season_form=[
            TeamSeasonForm(side="home", provider_team_id="t1", xgf=5.0, xg_games=5)
        ],
    )
    row = StatsSheetRow(
        event_id="e", sport="football", market="goals_for", line=0.5,
        direction="OVER", team_name="Sheffield United", hits=3, sample_size=4,
        hit_rate=0.75, p_low=0.3, mean=2.25, median=3.0,
        cross_provider_agreement="SINGLE_SOURCE", confidence="LOW",
        data_quality="READY",
    )
    flags = [
        flag for flag in context_flags_for_row(row, dossier)
        if flag.source == "season_form"
    ]
    assert len(flags) == 1
    assert flags[0].direction == "ARGUES_AGAINST"
    assert flags[0].magnitude == pytest.approx(1.25, abs=0.01)


def test_provider_duplicates_do_not_move_the_xg_flags_average():
    """The second half of the same fault: a match three providers report is one
    match. Before ``_one_per_day`` ran here it was three observations, so a
    well-covered fixture pulled the average toward whichever value the
    duplicated match carried."""
    from bet.simple_stats.context_flags import context_flags_for_row
    from bet.simple_stats.contracts import (
        EventDossierV1,
        MetricObservation,
        StatsSheetRow,
        TeamSeasonForm,
    )

    def pv(provider: str, match_id: str, day: str, value: float) -> ProviderValue:
        return ProviderValue(
            provider=provider, match_id=match_id, match_date=day,
            opponent="Opponent", value=value,
            observed_at="2026-09-01T00:00:00+00:00",
            competition_id="league-1", season_id="2026",
        )

    # One 3-goal match reported by three providers, plus three 0-goal matches.
    # Collapsed: mean 0.75, gap 0.75 - 1.00 < 0 and nothing fires. Uncollapsed
    # it would be 1.50 over six "matches".
    bucket = [
        pv("bzzoiro", "b1", "2026-08-29", 3.0),
        pv("espn-football", "e1", "2026-08-29", 3.0),
        pv("highlightly", "h1", "2026-08-29", 3.0),
        pv("bzzoiro", "b2", "2026-08-22", 0.0),
        pv("bzzoiro", "b3", "2026-08-15", 0.0),
        pv("bzzoiro", "b4", "2026-08-08", 0.0),
    ]
    dossier = EventDossierV1(
        event_id="e", sport="football", readiness="READY",
        team_a_name="Sheffield United", team_b_name="Bolton Wanderers",
        metrics={
            "goals_for": MetricObservation(canonical_name="goals_for", team_a_l10=bucket)
        },
        season_form=[
            TeamSeasonForm(side="home", provider_team_id="t1", xgf=5.0, xg_games=5)
        ],
    )
    row = StatsSheetRow(
        event_id="e", sport="football", market="goals_for", line=0.5,
        direction="OVER", team_name="Sheffield United", hits=1, sample_size=4,
        hit_rate=0.25, p_low=0.1, mean=0.75, median=0.0,
        cross_provider_agreement="AGREE", confidence="LOW", data_quality="READY",
    )
    assert statistics.fmean(pv_.value for pv_ in bucket) == pytest.approx(1.5)
    assert not [
        flag for flag in context_flags_for_row(row, dossier)
        if flag.source == "season_form"
    ]


# --- empirical-Bayes shrinkage ----------------------------------------------


def test_shrinkage_pulls_a_thin_sample_toward_its_market_and_leaves_a_fat_one():
    """``n/(n+k)``: the whole point is that the weight is a function of how much
    evidence there is, so a five-match sample moves a long way and a
    fifty-match sample barely moves at all."""
    from bet.simple_stats.analyze import SHRINKAGE_K, market_priors, shrunk_centre

    prior = market_priors()["corners_for"]
    thin = shrunk_centre([2.0] * 5, "corners_for")
    fat = shrunk_centre([2.0] * 50, "corners_for")
    assert 2.0 < thin < prior
    assert 2.0 < fat < thin
    # The weight is exactly n/(n+k), asserted rather than approximated.
    for n in (1, 5, 12, 40):
        weight = n / (n + SHRINKAGE_K)
        assert shrunk_centre([2.0] * n, "corners_for") == pytest.approx(
            weight * 2.0 + (1 - weight) * prior, abs=1e-9
        )


def test_shrinkage_never_moves_a_sample_past_its_prior_or_the_wrong_way():
    """It is a weighted average of two numbers, so the result has to lie
    between them. A shrunk centre outside that interval would mean the sign of
    the weight had gone wrong somewhere."""
    from bet.simple_stats.analyze import market_priors, shrunk_centre

    for market, prior in list(market_priors().items())[:12]:
        for mean in (0.0, prior * 0.25, prior, prior * 3):
            for n in (1, 3, 8, 30):
                centre = shrunk_centre([mean] * n, market)
                assert min(mean, prior) - 1e-9 <= centre <= max(mean, prior) + 1e-9


def test_a_market_with_no_pinned_prior_is_left_exactly_alone():
    """Absent is not degraded. A metric missing from config/market_priors.json
    keeps the behaviour it had before priors existed, which is also what makes
    the file safe to extend one market at a time."""
    from bet.simple_stats.analyze import market_priors, shrunk_centre

    assert "a_market_nobody_has_measured" not in market_priors()
    assert shrunk_centre([1.0, 2.0, 3.0], "a_market_nobody_has_measured") == 2.0


def test_shrinkage_reaches_p_low_but_not_the_empirical_count():
    """Where the line is drawn, and it is the important part of the design.

    ``count_model_bound`` prices from the shrunk centre; ``wilson_lower_bound``
    and ``hits``/``sample_size`` do not move at all, because those count what
    happened and an empirical count is not a quantity you shrink. ``p_low`` is
    the ``min`` of the two, so it can move either way -- but never above the
    trials it ran.
    """
    values = [2.0, 4.0, 3.0, 2.0, 3.0]          # Sheffield United's corners
    from bet.simple_stats.analyze import shrunk_centre

    centre = shrunk_centre(values, "corners_for")
    hits, settled, _ = compute_hit_rate(values, 4.5, "UNDER")
    empirical = wilson_lower_bound(hits, settled)
    # The count is untouched by shrinkage: 5 of 5 either way.
    assert (hits, settled) == (5, 5)
    plain = min(empirical, count_model_bound(values, 4.5, "UNDER"))
    shrunk = min(empirical, count_model_bound(values, 4.5, "UNDER", centre))
    assert shrunk < plain          # 2.80 -> 4.09 against a 4.5 line
    assert shrunk <= empirical     # and the count is still the ceiling


def test_the_ladder_gate_reads_the_raw_mean_and_not_the_shrunk_one():
    """The circularity this avoids, and the reason ``row.mean`` stays raw.

    Shrinkage moves our estimate toward the market by construction, so a gate
    that compared the *shrunk* centre to the book's ladder would quietly stop
    firing on exactly the samples it exists to catch. Measured on the
    2026-09-01 rows: Sheffield United's ladder sigma goes from -1.77 to -1.00
    and Preston's from -1.33 to -0.28, both inside the 1.25 threshold.

    So the two answer different questions and read different numbers.
    ``p_low``/``p_central`` price from the shrunk centre; ``ladder_sigma`` asks
    whether the *evidence* describes this fixture, and reads the sample's own.
    """
    from bet.simple_stats.analyze import shrunk_centre
    from bet.simple_stats.contracts import EventDossierV1, MetricObservation

    values = [2.0, 4.0, 3.0, 2.0, 3.0]
    raw = statistics.fmean(values)
    # Sheffield United is team_a and therefore tonight's home side, so the
    # price shrinks toward the *home* corners prior (5.25) rather than the
    # pooled one (4.74). The gate below still reads row.mean, and that is
    # exactly the claim under test -- moving the shrinkage target must not
    # move the diagnostic.
    centre = shrunk_centre(values, "corners_for", "home")
    ladder_median, spread = 5.76, _sample_dispersion(values) ** 0.5
    assert abs((raw - ladder_median) / spread) > 1.25       # the raw mean is caught
    assert abs((centre - ladder_median) / spread) < 1.25    # the shrunk one is not

    # And the row that ANALYZE writes carries both, so the artifact can be
    # audited without re-deriving either.
    dossier = EventDossierV1(
        event_id="e", sport="football", readiness="READY",
        team_a_name="Sheffield United", team_b_name="Bolton Wanderers",
        metrics={
            "corners_for": MetricObservation(
                canonical_name="corners_for",
                team_a_l10=[
                    ProviderValue(
                        provider="bzzoiro", match_id=f"m{i}",
                        match_date=f"2026-08-{10 + i:02d}", opponent=f"Opp {i}",
                        value=v, observed_at="2026-09-01T00:00:00+00:00",
                    )
                    for i, v in enumerate(values)
                ],
            )
        },
    )
    from bet.simple_stats.analyze import analyze_dossier

    rows = [
        r for r in analyze_dossier(dossier)
        if r.market == "corners_for" and r.team_name == "Sheffield United"
    ]
    assert rows, "no corners_for row was produced"
    row = rows[0]
    assert row.mean == pytest.approx(raw)                 # evidence, unshrunk
    assert row.shrunk_mean == pytest.approx(centre)       # what the price used
    assert row.shrunk_mean > row.mean


def test_every_pinned_prior_is_a_positive_number_with_its_evidence_recorded():
    """The config is policy, so it has to carry the same audit trail
    observation_scope.json does: how many observations, over which window."""
    import json
    from pathlib import Path

    doc = json.loads(
        (Path(__file__).resolve().parents[2] / "config" / "market_priors.json")
        .read_text(encoding="utf-8")
    )
    assert doc["_measured_over"] and doc["_measured_at"]
    assert doc["priors"], "an empty priors block would silently disable shrinkage"
    for market, block in doc["priors"].items():
        assert not market.startswith("_")
        assert block["mean"] > 0, market
        # 120 is the floor the measurement script applies; below it the prior is
        # itself a thin sample and shrinking toward it borrows nothing.
        assert block["observations"] >= 120, market
    # A percentage has no count distribution to fit, so it must never appear.
    from bet.simple_stats.contracts import PERCENTAGE_METRICS

    assert not (set(doc["priors"]) & PERCENTAGE_METRICS)
