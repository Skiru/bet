"""The 2026-09-03 rank-one single, from the coupon file back to the estimand.

That day's coupon opened with a tennis row that looked like the best bet of the
slate and was an artifact of measuring the wrong quantity:

    #1 Oliynykova/Eala aces_total 1.5 OVER   p_low 0.7050  min 1.5603  @2.42

Superbet's price was genuine and correctly joined -- ``Liczba asow`` /
``Powyzej 1.5``, match scope, and the book's per-player and match-total
quotes on that fixture devig to within 1.1pp of each other. The wrong number
was ours, from two independent errors stacked in the same direction:

1. ``providers`` defines a tennis ``*_total`` observation as
   ``own + opponent``, and ``_independent_match_sample`` pools both
   participants' last-ten buckets. So the sample measured these two players
   *plus a draw of third parties*. Its mean was 5.23; the two players' own
   hard-court rates are 1.00 and 1.25, so the quantity Superbet was pricing
   was 2.25. The sample's right tail -- a 12 and an 18 -- was Alycia Parks's
   and Qinwen Zheng's serving, and neither was on court.
2. ``market_priors`` pins one ``aces_total`` mean, 8.066, measured over two
   ATP-heavy slates. On this run ATP averaged 13.42 a match and WTA 5.74, so
   shrinkage pulled a WTA best-of-three centre *up* to 6.4635 -- above the
   sample's own mean, which is the tell that the target was wrong.

The sheet already contradicted itself: the same fixture's own ``aces_for``
rows read p_low 0.353 (Oliynykova, mean 1.00) and 0.306 (Eala, mean 1.25) and
never became candidates. Framed per player it was a pass; pooled it led the
file.

Neither demotion gate could catch it. ``off_ladder`` needs two devigged rungs
and Superbet posted one, so ``ladder_sigma`` was None -- and had it fired it
would have passed anyway, because the same contamination that inflated the
mean inflated ``dispersion`` to 4.59. ``MAX_MARKET_DISAGREEMENT`` saw the gap
(0.481, against a 0.25 threshold) but only annotates since 2026-09-02.

The fix is ``_framed_tennis_total_centre``: price a tennis match total from the
sum of the two participants' own rates, which are already on the sheet as
per-player rows. It needs no new prior and no new gate -- at the framed centre
the count model bound falls below ``MIN_SINGLE_P_LOW`` and the row leaves the
coupon through the floor that was always there.
"""
from __future__ import annotations

import pytest

from bet.simple_stats import analyze
from bet.simple_stats.contracts import EventDossierV1, MetricObservation, ProviderValue

# Oliynykova/Eala, WTA US Open, 2026-09-03, hard court, as the dossier held it.
# Clay observations are listed because the surface filter has to remove them --
# including the only real meeting of these two, 2026-05-17.
_A_OWN = [  # aces_for, Oliynykova
    (1.0, "Diane Parry", "2026-08-23", "Hard"),
    (1.0, "Mayar Sherif", "2026-08-23", "Hard"),
    (0.0, "Mirra Andreeva", "2026-08-13", "Hard"),
    (2.0, "Elvina Kalieva", "2026-08-13", "Hard"),
    (1.0, "Karolina Pliskova", "2026-08-02", "Hard"),
    (0.0, "Leyre Romero Gormaz", "2026-07-20", "Clay"),
    (2.0, "Nastasja Schunk", "2026-07-20", "Clay"),
]
_B_OWN = [  # aces_for, Eala
    (0.0, "Amanda Anisimova", "2026-08-13", "Hard"),
    (1.0, "Belinda Bencic", "2026-08-02", "Hard"),
    (2.0, "Caty Mcnally", "2026-08-02", "Hard"),
    (2.0, "Alycia Parks", "2026-08-02", "Hard"),
    (0.0, "Jessica Pegula", "2026-07-27", "Hard"),
    (1.0, "Elina Svitolina", "2026-07-27", "Hard"),
    (0.0, "Leylah Fernandez", "2026-07-27", "Hard"),
    (4.0, "Qinwen Zheng", "2026-07-27", "Hard"),
]
# aces_total for the same matches: own + opponent. The 12 is Parks, the 18 Zheng.
_A_TOTAL = [
    (3.0, "Diane Parry", "2026-08-23", "Hard"),
    (3.0, "Mayar Sherif", "2026-08-23", "Hard"),
    (3.0, "Mirra Andreeva", "2026-08-13", "Hard"),
    (3.0, "Elvina Kalieva", "2026-08-13", "Hard"),
    (5.0, "Karolina Pliskova", "2026-08-02", "Hard"),
    (1.0, "Leyre Romero Gormaz", "2026-07-20", "Clay"),
    (3.0, "Nastasja Schunk", "2026-07-20", "Clay"),
]
_B_TOTAL = [
    (3.0, "Amanda Anisimova", "2026-08-13", "Hard"),
    (2.0, "Belinda Bencic", "2026-08-02", "Hard"),
    (3.0, "Caty Mcnally", "2026-08-02", "Hard"),
    (12.0, "Alycia Parks", "2026-08-02", "Hard"),
    (4.0, "Jessica Pegula", "2026-07-27", "Hard"),
    (5.0, "Elina Svitolina", "2026-07-27", "Hard"),
    (4.0, "Leylah Fernandez", "2026-07-27", "Hard"),
    (18.0, "Qinwen Zheng", "2026-07-27", "Hard"),
]

# The 13 hard-court pooled values the shipped row was built from.
POOLED_HARD = [3.0, 3.0, 3.0, 3.0, 5.0, 3.0, 2.0, 3.0, 12.0, 4.0, 5.0, 4.0, 18.0]


def _values(rows, provider="tennis-abstract"):
    return [
        ProviderValue(
            provider=provider,
            match_id=f"{provider}-{day}-{opponent}",
            value=value,
            opponent=opponent,
            match_date=f"{day}T12:00:00+00:00",
            observed_at="2026-09-03T04:20:00+00:00",
            surface=surface,
        )
        for value, opponent, day, surface in rows
    ]


def _dossier(sport="tennis"):
    return EventDossierV1(
        event_id="c9161b2a225d3803d41b49f8e21f882233d133fc75e0be8371036052726acc6c",
        sport=sport,
        readiness="PARTIAL",
        team_a_name="Oleksandra Oliynykova",
        team_b_name="Alexandra Eala",
        metrics={
            "aces_total": MetricObservation(
                canonical_name="aces_total",
                team_a_l10=_values(_A_TOTAL),
                team_b_l10=_values(_B_TOTAL),
                h2h=_values([(2.0, "Alexandra Eala", "2026-05-17", "Clay")]),
            ),
            "aces_for": MetricObservation(
                canonical_name="aces_for",
                team_a_l10=_values(_A_OWN),
                team_b_l10=_values(_B_OWN),
                h2h=_values([(2.0, "Alexandra Eala", "2026-05-17", "Clay")]),
            ),
        },
    )


def test_framed_centre_is_the_two_players_own_rates_summed():
    """1.00 + 1.25 = 2.25, not the pooled 5.23."""
    centre, suppress = analyze._framed_tennis_total_centre(
        _dossier(), "aces_total", "Hard"
    )
    assert centre == pytest.approx(2.25)
    assert suppress is False


def test_pooled_sample_mean_is_the_number_that_shipped():
    """Guards the premise: 5.2308 is what the pooled sample really said, so the
    test above is measuring a frame error and not an arithmetic slip."""
    assert sum(POOLED_HARD) / len(POOLED_HARD) == pytest.approx(5.2308, abs=1e-4)


def test_the_shipped_prior_pulled_a_wta_centre_above_its_own_sample():
    """The second, independent error. A shrinkage target above the sample mean
    is the signature of a prior measured on the other tour."""
    shrunk = analyze.shrunk_centre(POOLED_HARD, "aces_total")
    assert shrunk == pytest.approx(6.4635, abs=1e-3)
    assert shrunk > sum(POOLED_HARD) / len(POOLED_HARD)


def test_framed_centre_drops_the_row_below_the_coupon_floor():
    """The whole point: no new gate. At the framed centre the count model bound
    falls under MIN_SINGLE_P_LOW, so the row stops being a candidate."""
    from bet.simple_stats.coupons import MIN_SINGLE_P_LOW

    shipped = min(
        analyze.wilson_lower_bound(13, 13),
        analyze.count_model_bound(POOLED_HARD, 1.5, "OVER", 6.4635),
    )
    framed = min(
        analyze.wilson_lower_bound(13, 13),
        analyze.count_model_bound(POOLED_HARD, 1.5, "OVER", 2.25),
    )
    assert shipped == pytest.approx(0.7050, abs=1e-3)
    assert shipped >= MIN_SINGLE_P_LOW
    assert framed < MIN_SINGLE_P_LOW


def test_wilson_alone_cannot_see_the_frame_error():
    """Why the bound had to move and not the trial count. 13/13 is 13/13
    whichever quantity the 13 measured, so Wilson is identical either way and
    ``min`` can only help if the count model's centre is right."""
    assert analyze.wilson_lower_bound(13, 13) == pytest.approx(0.7719, abs=1e-3)


def test_football_totals_are_untouched():
    """Pooling is close to correct in football -- a team's opponents average
    roughly the league mean -- and this fix must not reach it."""
    assert analyze._framed_tennis_total_centre(
        _dossier(sport="football"), "corners_total", None
    ) == (None, False)


def test_total_sets_has_no_component_and_keeps_the_pooled_centre():
    """Named in ``_TENNIS_TOTAL_COMPONENT``'s docstring as still exposed, so
    that it is a known gap rather than a silent one."""
    assert analyze._framed_tennis_total_centre(
        _dossier(), "total_sets", "Hard"
    ) == (None, False)


def test_a_one_sided_sample_suppresses_the_market_and_never_falls_back():
    """The residual the first version of this fix left behind.

    One participant with no scoped observation must **suppress** the market,
    not fall back to the pooled centre -- the pooled sample is at its most
    wrong exactly there, because it is then entirely the other player and her
    opponents. This is Badosa-Gauff ``double_faults_total``: the surface filter
    removed all nine of Badosa's clay matches and the surviving n=9 was Gauff
    alone, yet the row still described a two-player total.
    """
    dossier = EventDossierV1(
        event_id="one-sided",
        sport="tennis",
        readiness="PARTIAL",
        team_a_name="Oleksandra Oliynykova",
        team_b_name="Alexandra Eala",
        metrics={
            "aces_for": MetricObservation(
                canonical_name="aces_for",
                team_a_l10=_values(_A_OWN),
                team_b_l10=[],
                h2h=[],
            ),
        },
    )
    assert analyze._framed_tennis_total_centre(dossier, "aces_total", "Hard") == (
        None,
        True,
    )


def test_surface_filter_applies_to_the_component_too():
    """The component is scoped, not read raw -- otherwise a clay sample would
    price a hard-court row.

    Asserted through a surface neither player has a full sample on rather than
    by comparing means: Oliynykova's two clay observations are 0 and 2, which
    average to the same 1.00 as her hard court, so on *this* fixture the
    filtered and unfiltered centres coincide at 2.25 by accident. Eala has no
    clay match at all, so asking for clay must fall back to None -- which can
    only happen if the filter reached the component.
    """
    # Eala has no clay match, so clay is one-sided -> suppress, not fall back.
    assert analyze._framed_tennis_total_centre(_dossier(), "aces_total", "Clay") == (
        None,
        True,
    )
    centre, suppress = analyze._framed_tennis_total_centre(
        _dossier(), "aces_total", "Hard"
    )
    assert centre == pytest.approx(2.25)
    assert suppress is False
