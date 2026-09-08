"""Second pass of 2026-09-08: a row must describe one sample, and a rung must
be one the draw can settle.

Found by probing invariants against every recorded slate in ``runs/`` rather
than by reading code. Three of them held; the ones that did not:

* ``corroborated_matches > sample_size`` on 62 rows -- the coupon printed
  "19/18 matches seen by a second provider".
* the two sides of a half-integer rung not summing to 1 with no push and no
  clamp, on 213 rows the conflict flags did not explain.
* a non-integer ``mean`` whose denominator did not divide ``sample_size``, on
  ~900 rows, and **always** by exactly one.

All three were the same defect. A provider conflict that straddles the line
settles nothing, so ``count_hits`` drops it from ``sample_size`` -- and it was
still in the list the count model prices from, still in the corroboration
count, and still in ``mean``. Plus one real match sitting in three buckets
(team A's last ten, team B's, the h2h) counted three times against a priced
sample that folds it once.
"""
from __future__ import annotations

import pytest

from bet.simple_stats.analyze import (
    _adverse_values,
    _cross_provider_agreement,
    _independent_match_sample,
    _set_lines_for_format,
    corroborated_matches,
    count_hits,
    count_model_central,
)
from bet.simple_stats.contracts import ProviderValue


def _pv(
    provider: str,
    value: float,
    *,
    day: str,
    opponent: str = "Real Betis",
    low: float | None = None,
    high: float | None = None,
) -> ProviderValue:
    return ProviderValue(
        provider=provider,
        match_id=f"{provider}-{day}-{opponent}",
        match_date=day,
        opponent=opponent,
        value=value,
        observed_at="2026-09-08T00:00:00+00:00",
        conflict_low=low,
        conflict_high=high,
    )


# --- the straddling conflict must leave every number, not just sample_size ---


def _sample_with_a_straddler() -> list[ProviderValue]:
    """Nine clean observations plus one the two providers put either side of 6.5."""
    sample = [
        _pv("bzzoiro", 4.0, day=f"2026-08-{day:02d}", opponent=f"Team {day}")
        for day in range(1, 10)
    ]
    sample.append(
        _pv("bzzoiro", 6.0, day="2026-08-20", opponent="Disputed FC", low=6.0, high=7.0)
    )
    return sample


def test_the_count_model_prices_the_sample_the_hit_count_settled():
    sample = _sample_with_a_straddler()
    counted = count_hits(sample, 6.5, "UNDER")
    assert counted.conflicts_on_line == 1
    assert counted.sample_size == 9

    priced = _adverse_values(sample, "UNDER", 6.5)
    assert len(priced) == counted.sample_size
    # Without the line the straddler is still there, at the adverse end, in the
    # list ``count_model_central`` reads -- which is what made a row report
    # n=9 above a centre computed from ten observations.
    unfiltered = _adverse_values(sample, "UNDER")
    assert len(unfiltered) == 10
    assert 7.0 in unfiltered and 7.0 not in priced


def test_a_clean_rung_sums_to_one_across_its_two_sides():
    """The invariant that found it. With the straddler gone from both sides the
    OVER and the UNDER are computed from one sample and must sum exactly."""
    sample = _sample_with_a_straddler()
    over = count_model_central(_adverse_values(sample, "OVER", 6.5), 6.5, "OVER")
    under = count_model_central(_adverse_values(sample, "UNDER", 6.5), 6.5, "UNDER")
    assert over + under == pytest.approx(1.0, abs=1e-9)


def test_a_push_stays_in_the_model_sample():
    """A value on the line settles no bet and is still a measurement of the
    level; ``_winning_boundary`` is what keeps its mass off both sides."""
    sample = [
        _pv("bzzoiro", 7.0, day=f"2026-08-{day:02d}", opponent=f"Team {day}")
        for day in range(1, 5)
    ]
    counted = count_hits(sample, 7.0, "UNDER")
    assert counted.pushes == 4 and counted.sample_size == 0
    assert len(_adverse_values(sample, "UNDER", 7.0)) == 4


def test_corroboration_never_exceeds_the_sample_it_describes():
    """The coupon prints ``corroborated_matches``/``sample_size`` verbatim."""
    sample: list[ProviderValue] = []
    for day in range(1, 6):
        sample.append(_pv("bzzoiro", 4.0, day=f"2026-08-{day:02d}", opponent=f"Team {day}"))
        sample.append(_pv("espn-football", 4.0, day=f"2026-08-{day:02d}", opponent=f"Team {day}"))
    # one more match the two providers put either side of 6.5
    sample.append(_pv("bzzoiro", 6.0, day="2026-08-20", opponent="Disputed FC"))
    sample.append(_pv("espn-football", 7.0, day="2026-08-20", opponent="Disputed FC"))

    independent = [
        _pv("bzzoiro", 4.0, day=f"2026-08-{day:02d}", opponent=f"Team {day}")
        for day in range(1, 6)
    ] + [_pv("bzzoiro", 6.0, day="2026-08-20", opponent="Disputed FC", low=6.0, high=7.0)]
    counted = count_hits(independent, 6.5, "UNDER")
    assert counted.sample_size == 5

    assert corroborated_matches("corners_total", sample) == 6
    assert corroborated_matches("corners_total", sample, "football", None, 6.5) == 5
    assert corroborated_matches("corners_total", sample, "football", None, 6.5) <= counted.sample_size


def test_one_match_in_three_buckets_is_one_corroborated_match():
    """Gotham - Portland, 2026-08-29. The 2026-07-25 meeting is in team A's last
    ten, team B's last ten and the h2h, and each copy was counted -- 19
    corroborated matches against a priced sample of 18. 13 of 32,027 samples
    took AGREE on the inflated numerator, and AGREE is what ``tier_for_row``
    reads to hand out CALL."""
    day = "2026-07-25"
    a_side = [
        _pv("bzzoiro", 11.0, day=day, opponent="Portland Thorns FC"),
        _pv("espn-football", 11.0, day=day, opponent="Portland Thorns FC"),
    ]
    b_side = [
        _pv("bzzoiro", 11.0, day=day, opponent="NJ/NY Gotham FC"),
        _pv("espn-football", 11.0, day=day, opponent="Gotham FC"),
    ]
    h2h = [
        _pv("bzzoiro", 11.0, day=day, opponent="Portland Thorns FC"),
        _pv("espn-football", 11.0, day=day, opponent="Portland Thorns FC"),
    ]
    pooled = a_side + b_side + h2h
    parts = [a_side, b_side, h2h]

    # Three buckets, three multi-provider clusters -- one match.
    assert corroborated_matches("corners_total", pooled, "football", parts) == 3
    assert (
        corroborated_matches(
            "corners_total", pooled, "football", parts, None, {day}
        )
        == 1
    )
    # And the share the label divides by uses the same count.
    assert _cross_provider_agreement(
        "corners_total", pooled, 1, "football", parts, {day}
    ) in ("PARTIAL_AGREE", "SINGLE_SOURCE", "AGREE")


def test_the_fold_matches_what_the_priced_sample_does():
    """``_independent_match_sample`` folds the shared match to one observation;
    the corroboration count has to fold it the same way or the numerator and
    the denominator are counting different things."""
    day = "2026-07-25"

    class Obs:
        team_a_l10 = [
            _pv("bzzoiro", 11.0, day=day, opponent="Portland Thorns FC"),
            _pv("bzzoiro", 8.0, day="2026-08-02", opponent="Chicago Red Stars"),
        ]
        team_b_l10 = [
            _pv("bzzoiro", 11.0, day=day, opponent="NJ/NY Gotham FC"),
            _pv("bzzoiro", 9.0, day="2026-08-05", opponent="Orlando Pride"),
        ]
        h2h = [_pv("bzzoiro", 11.0, day=day, opponent="Portland Thorns FC")]

    independent = _independent_match_sample(
        Obs(), "NJ/NY Gotham FC", "Portland Thorns FC", "football"
    )
    # Three real matches: the shared one plus one from each side.
    assert len(independent) == 3


# --- a rung the draw cannot settle is not a rung -----------------------------


def test_a_best_of_five_never_prices_the_set_line_only_a_best_of_three_has():
    """``total_sets 2.5`` on a men's slam tie. Shelton - Shapovalov read 14/14
    with a sample minimum of 3 sets and the model returned 0.6028 for the OVER
    and **0.3972 for the UNDER** -- four tenths on an outcome the draw does not
    allow without a retirement, and none of these samples contains one."""
    assert _set_lines_for_format([2.5], "BO5") == []
    assert _set_lines_for_format([2.5, 3.5, 4.5], "BO5") == [3.5, 4.5]
    assert _set_lines_for_format([5.5], "BO5") == []


def test_a_best_of_three_never_prices_a_line_above_three_sets():
    assert _set_lines_for_format([2.5, 3.5, 4.5], "BO3") == [2.5]
    assert _set_lines_for_format([1.5], "BO3") == []


def test_an_unpinned_competition_is_left_exactly_as_it_was():
    """The standing rule -- an unpinned fixture scopes nothing and suppresses
    nothing rather than being guessed at -- and the trap the first version of
    this fix fell into: widening the shared static grid gave 3.5 and 4.5 to
    unpinned fixtures, where this filter is inert, and produced
    ``UNDER 4.5`` at 20/20 off a sample whose maximum is 3."""
    assert _set_lines_for_format([2.5], None) == [2.5]
    assert _set_lines_for_format([2.5, 3.5, 4.5], None) == [2.5, 3.5, 4.5]
    assert _set_lines_for_format([2.5], "BO7") == [2.5]


# --- an impossible half-time score must not become a negative goal ----------


def test_a_half_time_score_above_full_time_is_refused():
    """bzzoiro match 221408, Penafiel - Leganes 2026-07-24: half time 1, full
    time 0. ``goals_2h_for = ft - ht`` produced **-1.0** and nothing noticed --
    one observation in 10,173, and every UNDER built on that sample was better
    for it. The split is dropped rather than clamped: both figures cannot be
    right and nothing in the ingest says which."""
    from bet.simple_stats.providers import half_time_is_possible

    assert half_time_is_possible(0, 1, 1, 2) is True
    assert half_time_is_possible(0, 0, 0, 0) is True
    assert half_time_is_possible(2, 1, 2, 1) is True     # a goalless second half
    # the real case, and the mirror of it
    assert half_time_is_possible(1, 0, 0, 2) is False
    assert half_time_is_possible(0, 3, 1, 2) is False
    # a missing half-time score is not a defect, just no split available
    assert half_time_is_possible(None, 0, 1, 2) is False
    assert half_time_is_possible(0, None, 1, 2) is False


def test_the_derivation_it_guards_would_otherwise_go_negative():
    """Stated as arithmetic so the guard cannot be removed as decoration."""
    from bet.simple_stats.providers import half_time_is_possible

    home_goals, away_goals, home_ht, away_ht = 0, 2, 1, 0
    assert not half_time_is_possible(home_ht, away_ht, home_goals, away_goals)
    # what the ingest would have emitted for the home side
    assert float(home_goals) - float(home_ht) == -1.0
