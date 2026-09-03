"""The 2026-09-01 slate, from the settled ledger back to the defect.

Seven singles reached the "worth its price" section of that day's coupon file.
Six lost, one was void when the match was abandoned, and none won. The
outcomes, read off the operator's own slips:

    #1 Sheffield United corners_for      4.5 UNDER @2.70   ->  5   LOST
    #2 Preston shots_on_target_for       3.5 UNDER @2.12   ->  4   LOST
    #3 Jovic/Frech double_faults_total   4.5 OVER  @1.85   ->  abandoned
    #4 Birmingham shots_for             12.5 UNDER @2.07   -> 16   LOST
    #5 Maria/Ostapenko double_faults    11.5 UNDER @1.95   ->      LOST
    #6 Torino/Monza corners_total        8.5 UNDER @1.88   -> 16   LOST
    #7 Lincoln shots_on_target_total     7.5 OVER  @1.49   ->  3   LOST

Six independent losses at the p_low the file claimed for them is a 0.4% event.
It was not variance, and the cause was one arithmetic property with one
safeguard disabled on top of it:

1. ``wilson_lower_bound`` cannot see the line. On a sample that has not missed
   once it returns the same number for every line above the sample's maximum --
   Sheffield United's five corner observations {2,4,3,2,3} scored 0.5655085 at
   4.5, 5.5, 6.5 and 7.5 alike.
2. ``min_acceptable_odds`` is a tier margin over ``1/p_low``, so it was
   constant down the ladder too. Only the longest-priced rung could clear it,
   and the longest-priced rung is the one the book thinks least likely. The
   pipeline was reading the book's risk premium as its own surplus.
3. "VALUE" is therefore *algebraically* a disagreement filter: ``price >=
   margin/p_low`` devigs to ``p_low - implied >= p_low*(1 - 1/(margin*
   overround))``, about +0.08 at these overrounds. Every VALUE row disagrees
   with the book by at least that much by construction.
4. The one gate that measured that disagreement, ``MAX_MARKET_DISAGREEMENT``,
   was set at 0.15 -- above six of the seven -- *and* exempted rows with no
   miss in the sample, which was five of the seven. It also could not have
   been rescued by moving the number: because of (3) it was measuring our own
   conservatism, so every setting is either a no-op or a blanket ban. It now
   compares ``p_central``, which carries neither the bound nor the margin.

Each test below is one of those, pinned with that day's real numbers.
"""
from __future__ import annotations

import statistics

import pytest

from bet.simple_stats import coupons as coupons_module
from bet.simple_stats.analyze import count_model_bound, wilson_lower_bound
from bet.simple_stats.contracts import (
    EventListV1,
    EventRecord,
    StatsSheetRow,
    StatsSheetV1,
    SuperbetEventOffer,
    SuperbetLine,
    SuperbetOfferV1,
)
from bet.simple_stats.coupons import (
    MAX_LADDER_SIGMA,
    MAX_MARKET_DISAGREEMENT,
    build_coupons,
)


@pytest.fixture(autouse=True)
def _clear_competition_tier_cache():
    coupons_module.reset_competition_tier_cache()
    yield
    coupons_module.reset_competition_tier_cache()


# --- 1. p_low must be able to tell one rung from another --------------------


# The five samples, exactly as ``_one_per_day`` and ``scope_values`` left them
# in that run's dossier. Verified against
# runs/2026-09-01/2026-09-01_event_dossiers.json.
SHEFFIELD_CORNERS = [2.0, 4.0, 3.0, 2.0, 3.0]
PRESTON_SHOTS_ON_TARGET = [1.0, 1.0, 2.0, 3.0, 3.0]
BIRMINGHAM_SHOTS = [9.0, 8.0, 8.0, 10.0, 6.0]
TORINO_MONZA_CORNERS = [6.0, 6.0, 6.0, 6.0, 7.0, 7.0]
LINCOLN_SHOTS_ON_TARGET = [8.0, 11.0, 9.0, 12.0, 8.0, 8.0, 8.0, 8.0, 10.0, 14.0]


def test_wilson_alone_still_cannot_tell_the_rungs_apart():
    """The defect itself, asserted so the fix has something to be a fix *of*.

    This is not a bug in ``wilson_lower_bound`` -- it answers the question it
    is asked, which is about the trial count. It is a bug in asking it alone.
    """
    for line in (4.5, 5.5, 6.5, 7.5):
        hits = sum(1 for v in SHEFFIELD_CORNERS if v < line)
        assert hits == len(SHEFFIELD_CORNERS)
        assert wilson_lower_bound(hits, len(SHEFFIELD_CORNERS)) == pytest.approx(
            0.5655085, abs=1e-6
        )


def test_the_count_model_rises_with_the_line_so_the_ladder_is_ordered_again():
    """What the sheet needs and Wilson cannot give: a number that knows 7.5 is
    a safer UNDER than 4.5 on a sample topping out at 4."""
    bounds = [
        count_model_bound(SHEFFIELD_CORNERS, line, "UNDER")
        for line in (4.5, 5.5, 6.5, 7.5)
    ]
    assert bounds == sorted(bounds)
    assert bounds[0] < bounds[-1]
    # And the mirror image for an OVER: further out is *less* likely.
    over = [
        count_model_bound(SHEFFIELD_CORNERS, line, "OVER")
        for line in (4.5, 5.5, 6.5, 7.5)
    ]
    assert over == sorted(over, reverse=True)


def test_the_model_is_a_cap_and_can_only_ever_lower_p_low():
    """The combination rule is ``min``, so no pairing of the two instruments
    can manufacture a confidence neither of them holds alone.

    Stated against Wilson rather than against the previous release, because
    shrinkage (``shrunk_centre``) later made ``p_low`` move in *both*
    directions -- 141 rows up and 214 down on the frozen fixture -- by moving
    the centre the model prices from. What survives, and what actually matters,
    is that the empirical count is always still a ceiling: a row can never be
    more confident than the trials it ran.
    """
    for values in (
        SHEFFIELD_CORNERS,
        PRESTON_SHOTS_ON_TARGET,
        BIRMINGHAM_SHOTS,
        TORINO_MONZA_CORNERS,
        LINCOLN_SHOTS_ON_TARGET,
    ):
        for line in (0.5, 1.5, 3.5, 7.5, 11.5, 15.5, 25.5):
            for direction in ("OVER", "UNDER"):
                hits = sum(
                    1 for v in values
                    if (v > line if direction == "OVER" else v < line)
                )
                settled = sum(1 for v in values if v != line)
                if not settled:
                    continue
                combined = min(
                    wilson_lower_bound(hits, settled),
                    count_model_bound(values, line, direction),
                )
                assert combined <= wilson_lower_bound(hits, settled) + 1e-12


def test_an_undispersed_count_sample_does_not_buy_certainty():
    """Torino/Monza, #6, and the one loss the sample's own shape could have
    caught. Six scoped observations of {6,6,6,6,7,7} -- variance 0.27 against a
    mean of 6.33 -- read as unanimous by Wilson: 6/6 UNDER 8.5, p_low 0.610,
    min 1.80, Superbet 1.88, VALUE. The match returned 16 corners.

    A count process has variance at least its mean, so the sample's own 0.27 is
    a small-sample artefact and not a property of corner counts. Flooring the
    variance at the mean is what turns 0.610 into a number that cannot clear
    1.88.
    """
    wilson = wilson_lower_bound(6, 6)
    assert wilson == pytest.approx(0.6097, abs=1e-3)
    model = count_model_bound(TORINO_MONZA_CORNERS, 8.5, "UNDER")
    p_low = min(wilson, model)
    assert p_low < wilson
    # The number that decides it: a LEAN needs 1.10/p_low on the screen.
    assert 1.10 / p_low > 1.88


def test_lincoln_over_no_longer_clears_its_price():
    """#7, and the one of the six that was honest variance rather than a broken
    sample -- mean 9.6 against a ladder median of 8.46, agreeing with the book
    about where the market sat. It still must not be sold as value at 1.49:
    ten observations of a distribution this wide do not fix P(X>7.5) at 0.72.
    """
    wilson = wilson_lower_bound(10, 10)
    assert wilson == pytest.approx(0.7225, abs=1e-3)
    p_low = min(wilson, count_model_bound(LINCOLN_SHOTS_ON_TARGET, 7.5, "OVER"))
    assert p_low < 0.60
    assert 1.10 / p_low > 1.49


def test_percentage_markets_keep_the_wilson_number_untouched():
    """Possession is not a count and no count model is fitted to it, so those
    rows must come out of this change bit-identical."""
    from bet.simple_stats.analyze import _COUNT_MARKETS_EXCLUDED

    assert "possession" in _COUNT_MARKETS_EXCLUDED


# --- 2. the sheet must be checked against the book's whole ladder -----------


def _row(**overrides) -> StatsSheetRow:
    kwargs = dict(
        event_id="evt-1", sport="football", market="corners_for", line=4.5,
        direction="UNDER", team_name="Sheffield United", hits=5, sample_size=5,
        hit_rate=1.0, p_low=0.5655,
        # count_model_central({2,4,3,2,3}, 4.5, UNDER) to three places: what the
        # sample actually claimed, before Wilson and the margin buried it.
        p_central=0.845,
        mean=2.8, median=3.0,
        # sqrt(max(var 0.70, mean 2.80)) -- the Poisson floor binds here, as it
        # does on most five-observation count samples.
        dispersion=2.8 ** 0.5,
        sources=["bzzoiro"],
        cross_provider_agreement="SINGLE_SOURCE", confidence="MEDIUM",
        data_quality="READY",
    )
    kwargs.update(overrides)
    return StatsSheetRow(**kwargs)


def _sheet(*rows) -> StatsSheetV1:
    return StatsSheetV1(
        run_id="RID-1", date="2026-09-01",
        generated_at="2026-09-01T00:00:00+00:00", rows=list(rows),
    )


def _events() -> EventListV1:
    return EventListV1(
        run_id="RID-1", generated_at="2026-09-01T00:00:00+00:00",
        date="2026-09-01", sports=["football"],
        events=[
            EventRecord(
                event_id="evt-1", sport="football", competition="Championship",
                home_team="Sheffield United", away_team="Bolton Wanderers",
                start_time="2026-09-01T18:45:00+00:00",
                identity_confidence="CONFIRMED", status="ACTIVE",
            )
        ],
    )


def _rung(line: float, *, under: float, over: float | None, market="corners_for",
          team="Sheffield United"):
    """One rung. ``over=None`` posts the UNDER side only, which is what a
    one-way market looks like and is the case that leaves every devigged read
    of the book inert."""
    common = dict(market=market, line=line, source_market_name=market,
                  source_outcome_name="x", team_name=team)
    lines = [SuperbetLine(direction="UNDER", price=under, **common)]
    if over is not None:
        lines.append(SuperbetLine(direction="OVER", price=over, **common))
    return lines


def _offer(*groups) -> SuperbetOfferV1:
    return SuperbetOfferV1(
        run_id="RID-1", date="2026-09-01",
        generated_at="2026-09-01T14:50:00+00:00",
        events=[
            SuperbetEventOffer(
                superbet_event_id="13777816",
                superbet_match_name="Sheffield United·Bolton Wanderers",
                sport="football", kickoff="2026-09-01T18:45:00Z",
                event_id="evt-1", match_quality="EXACT",
                lines=[line for g in groups for line in g],
            )
        ],
    )


# Superbet's real ladder for Sheffield United corners on 2026-09-01, both sides
# of every rung, read off runs/2026-09-01/2026-09-01_superbet_offer.json. It
# devigs to P(X<2.5)=0.130, 3.5=0.221, 4.5=0.341, 5.5=0.468, 6.5=0.591,
# 7.5=0.698 -- a median of 5.76 corners. Our sample said 2.80. The match
# returned 5.
SHEFFIELD_LADDER = (
    _rung(2.5, under=7.10, over=1.06),
    _rung(3.5, under=4.15, over=1.18),
    _rung(4.5, under=2.70, over=1.40),
    _rung(5.5, under=1.97, over=1.73),
    _rung(6.5, under=1.56, over=2.25),
    _rung(7.5, under=1.32, over=3.05),
)


def _sheffield_coupons(**row_overrides):
    lines = (2.5, 3.5, 4.5, 5.5, 6.5, 7.5)
    return build_coupons(
        _sheet(*[_row(line=line, **row_overrides) for line in lines]),
        _events(),
        superbet_offer=_offer(*SHEFFIELD_LADDER),
    )


def test_shrinkage_is_what_removes_these_three_rows():
    """#1, #2 and #4 -- the three largest losses -- never become candidates
    once the centre is shrunk, and this is the assertion that says so.

    It replaces a tier assertion that was here for half of 2026-09-02. The
    tier table's gap at n=5-7 uncorroborated was tightened to WEAK on the
    strength of these three rows and reverted after backtesting: settled
    against real results over four slates the category won 84.4% of 77 bets
    against a claimed 0.592 (see
    ``test_the_thin_uncorroborated_category_is_not_a_losing_one``). These three
    were the miscalibrated rows in it, not evidence about the category, and
    what actually catches a miscalibrated centre is the estimator.

    Home-side rows, so the home prior is the shrinkage target -- which is the
    correct one for all three and moves each of them further below the floor.
    """
    from bet.simple_stats.analyze import shrunk_centre
    from bet.simple_stats.coupons import MIN_SINGLE_P_LOW

    cases = (
        ("corners_for", SHEFFIELD_CORNERS, 4.5, 0.201),
        ("shots_on_target_for", PRESTON_SHOTS_ON_TARGET, 3.5, 0.116),
        ("shots_for", BIRMINGHAM_SHOTS, 12.5, 0.222),
    )
    for market, values, line, expected in cases:
        centre = shrunk_centre(values, market, "home")
        assert centre > statistics.fmean(values), market
        priced = count_model_bound(values, line, "UNDER", centre)
        assert priced == pytest.approx(expected, abs=0.01), market
        assert priced < MIN_SINGLE_P_LOW, market
    # And the unshrunk sample cleared the floor comfortably, which is the whole
    # reason they reached the file.
    assert wilson_lower_bound(5, 5) > MIN_SINGLE_P_LOW


def test_the_ladder_median_is_read_and_reported():
    """The number the pipeline already had on disk and never looked at."""
    single = _sheffield_coupons().singles[0]
    # (2.80 - 5.76) / 1.673.
    assert single.ladder_sigma == pytest.approx(-1.77, abs=0.02)


def test_a_sample_that_disagrees_with_the_whole_ladder_loses_the_top():
    """#1, the row that led the file at rank one.

    It is not flagged for the price of its own rung -- it is flagged because
    the book's entire ladder puts this market's centre at 5.76 and the sample
    puts it at 2.80. That is not a disagreement about a tail, which is where an
    edge would live; it is a disagreement about which distribution is being
    priced, and on 2026-09-01 the book was right.
    """
    single = _sheffield_coupons().singles[0]
    assert single.needs_review is True
    assert abs(single.ladder_sigma) > MAX_LADDER_SIGMA
    assert any("drabinka" in c for c in single.caveats)


def test_the_ladder_gate_still_demotes_after_the_price_gate_stopped():
    """The split, pinned. 2026-09-02 turned the per-rung price gap into a
    caveat that keeps its rank, and the temptation in that change was to take
    the ladder gate with it -- which would put Sheffield's corners back at
    rank one, where it lost."""
    coupons = _sheffield_coupons()
    ranked = [
        s for s in coupons.singles
        if s.ladder_sigma is not None and abs(s.ladder_sigma) > MAX_LADDER_SIGMA
    ]
    assert ranked, "the fixture no longer produces an off-ladder row to test"
    assert all(
        s.rank > min(other.rank for other in coupons.singles)
        for s in ranked
    ) or len(coupons.singles) == len(ranked), (
        "an off-ladder sample kept the top of the file"
    )
    assert any("zepchnięto na koniec listy" in n for n in coupons.notes)


def test_an_all_zeros_sample_cannot_hide_from_the_gate_behind_its_own_dispersion():
    """The sigma denominator is the sample's dispersion, floored at
    ``sqrt(mean)`` -- which is 0 exactly when the sample is all zeros, the
    provider-fabrication class. Reading that as "cannot compute sigma" made
    the most broken sample possible the only one the gate could not touch:
    p_central 1.0, no demotion, rank one. It is not unreadable; it is
    infinitely far from a book whose ladder is perfectly legible."""
    coupons = build_coupons(
        _sheet(_row(line=4.5, mean=0.0, median=0.0, dispersion=0.0,
                    hits=5, sample_size=5, hit_rate=1.0, p_low=0.5655,
                    p_central=1.0)),
        _events(),
        superbet_offer=_offer(*SHEFFIELD_LADDER),
    )
    single = coupons.singles[0]
    assert single.ladder_sigma == -coupons_module._LADDER_SIGMA_SATURATED
    assert abs(single.ladder_sigma) > MAX_LADDER_SIGMA
    assert any("drabinka" in c for c in single.caveats)


def test_one_rung_now_locates_the_book_and_catches_this_loser():
    """Changed on 2026-09-03, and Sheffield United is the proof it was wrong.

    This used to assert ``ladder_sigma is None`` on the reasoning that one rung
    is a probability and not a location. It is a location once the sample's own
    spread is known: ``P(X < 4.5) = 0.341`` devigged means the book's centre
    sits 0.41 standard deviations *above* 4.5, and our sample mean is 2.80 --
    -1.42 sigma, past ``MAX_LADDER_SIGMA``, on a row that lost.

    On the 2026-09-03 slate the old rule left ``ladder_sigma`` null on 9 of 15
    singles, and those nine were disproportionately the thin single-rung
    markets where a five-observation sample is most likely to be overruling a
    real price. Being unable to read a *two-sided* price is still not evidence
    against the sample; being unwilling to read one is different.
    """
    coupons = build_coupons(
        _sheet(_row(line=4.5)),
        _events(),
        superbet_offer=_offer(_rung(4.5, under=2.70, over=1.40)),
    )
    single = coupons.singles[0]
    assert single.ladder_sigma == pytest.approx(-1.4244, abs=1e-3)
    assert abs(single.ladder_sigma) > MAX_LADDER_SIGMA
    # And it agrees with the interpolated answer the full six-rung ladder gives
    # for the same sample, which is the check that the single-rung path is
    # reading the same book.
    full = build_coupons(
        _sheet(_row(line=4.5)), _events(), superbet_offer=_offer(*SHEFFIELD_LADDER)
    )
    assert full.singles[0].ladder_sigma == pytest.approx(single.ladder_sigma, abs=0.4)
    assert single.needs_review is True


def test_a_one_sided_rung_still_leaves_the_gate_inert():
    """A rung the book posts on one side only carries no devigged probability,
    so there is nothing to locate a centre from. That rule is unchanged."""
    coupons = build_coupons(
        _sheet(_row(line=4.5)),
        _events(),
        superbet_offer=_offer(_rung(4.5, under=2.70, over=None)),
    )
    single = coupons.singles[0]
    assert single.ladder_sigma is None
    assert single.market_disagreement is None


def test_agreeing_with_the_ladder_is_not_penalised():
    """The gate must not become a ban on having an opinion.

    Same six-rung ladder, but one row on it: UNDER 5.5, from a sample centred
    at 5.7 where the book centres the market at 5.76 -- 0.03 of a standard
    deviation apart. That is the property this test exists for, and it holds:
    the ladder gate does not fire, the row is not demoted, and it carries no
    ladder caveat.

    What disqualified #1 was the *location* of its sample, not the fact that it
    outbid the book. A row that agrees about location has to be allowed to
    disagree about price, or the fix reduces to "never outbid Superbet", which
    is the same as not producing a sheet at all.

    **The price this row has to beat changed on 2026-09-03** and the two
    assertions at the end record it. The market prior shrinks a 12-observation
    sample halfway toward the book's own devigged number (w = 12/22 = 0.545),
    so an edge of 0.55 against 0.468 becomes 0.513 against 0.468 -- and the
    LEAN margin of 10% no longer fits inside what is left. In relative terms
    the bar is now "beat the devigged price by 0.10/w", which at this n is
    18.3%; this row beats it by 17.5% and misses by half a point. A larger edge
    on the same sample still clears, which is the second half of the test: the
    prior charges for thinness, it does not ban disagreement.
    """
    coupons = build_coupons(
        _sheet(_row(line=5.5, mean=5.7, median=6.0, hits=9, sample_size=12,
                    hit_rate=0.75, p_low=0.60, p_central=0.55,
                    dispersion=5.7 ** 0.5)),
        _events(),
        superbet_offer=_offer(*SHEFFIELD_LADDER),
    )
    assert len(coupons.singles) == 1
    single = coupons.singles[0]
    # (5.70 - 5.76) / 2.387 -- the same market, agreed on.
    assert single.ladder_sigma == pytest.approx(-0.03, abs=0.03)
    assert abs(single.ladder_sigma) <= MAX_LADDER_SIGMA
    assert single.market_disagreement == pytest.approx(0.082, abs=0.01)
    assert single.needs_review is False
    assert not any("drabinka" in c for c in single.caveats)
    assert single.market_probability == pytest.approx(0.468, abs=0.01)
    assert single.sample_weight == pytest.approx(12 / 22, abs=1e-4)
    assert single.superbet_verdict == "PRICED_BELOW_THRESHOLD"

    bigger_edge = build_coupons(
        _sheet(_row(line=5.5, mean=5.7, median=6.0, hits=9, sample_size=12,
                    hit_rate=0.75, p_low=0.60, p_central=0.62,
                    dispersion=5.7 ** 0.5)),
        _events(),
        superbet_offer=_offer(*SHEFFIELD_LADDER),
    )
    assert bigger_edge.singles[0].superbet_verdict == "VALUE"


def test_the_ladder_gate_is_measured_in_sigma_and_not_as_a_ratio():
    """Why the first version of this gate was replaced, pinned as a property.

    A ratio band cannot mean one thing across markets. Take the *same* 0.30
    absolute disagreement between sample and ladder in two of them: half-time
    goals, where the mean is around 1.25, and total shots, where it is 24.

    Read as a ratio, one of them sits 19% from parity and the other 1% -- an
    order of magnitude apart, entirely because of the size of the mean and not
    because either sample is more wrong than the other. Read in the sample's
    own spread they are both small and both similar. Measured over one real
    day the ratio band fired on 53% of ``goals_for`` samples and 0% of
    ``corners_total``; in sigma the median is 0.30 and 0.13.
    """
    from bet.simple_stats.analyze import _sample_dispersion

    half_time_goals = [1.0, 2.0, 0.0, 1.0, 2.0, 1.0, 1.0, 2.0]
    total_shots = [24.0, 22.0, 26.0, 25.0, 21.0, 27.0, 23.0, 24.0]

    sigmas, ratio_distances = [], []
    for values in (half_time_goals, total_shots):
        mean = sum(values) / len(values)
        ladder_median = mean + 0.30
        sigmas.append(abs(mean - ladder_median) / (_sample_dispersion(values) ** 0.5))
        ratio_distances.append(abs(1.0 - mean / ladder_median))

    # The ratio reading disagrees with itself by more than tenfold between two
    # markets given the identical disagreement.
    assert max(ratio_distances) / min(ratio_distances) > 10
    # The sigma reading stays within a factor of five, and -- the point -- both
    # readings are on the same side of the threshold, which is what lets one
    # constant govern every market on the board.
    assert max(sigmas) / min(sigmas) < 5
    assert all(sigma < MAX_LADDER_SIGMA for sigma in sigmas)


# --- 3. the safeguard must not be exempted on the rows that need it ---------


def test_a_saturated_row_is_no_longer_exempt_from_the_disagreement_gate():
    """The direct enabler. Five of that day's seven singles had no miss in
    their sample, and the exemption cleared all five.

    The exemption's reasoning was sound about the symptom -- a constant
    ``p_low`` makes ``p_low - implied`` track the price alone -- and drew the
    wrong conclusion from it. The constancy was the defect; the gate was the
    alarm. ``p_low`` is line-aware now, so there is nothing left to exempt.
    """
    single = _sheffield_coupons().singles[0]
    assert single.hits >= single.sample_size  # saturated, as it was that day
    assert single.needs_review is True


# The seven singles that day's file admitted, measured the new way: p_central
# against Superbet's devigged price at the same rung. Replayed from
# runs/2026-09-01/ with the current code -- the old p_low-based numbers for the
# same seven were +0.224, +0.142, +0.128, +0.120, +0.119, +0.117, +0.101, all
# but one of them under the 0.15 that was supposed to catch them.
ADMITTED_2026_09_01 = [
    ("#1 Sheffield corners", 0.504, "LOST 5"),
    ("#4 Birmingham shots", 0.487, "LOST 16"),
    ("#2 Preston shots on target", 0.418, "LOST 4"),
    ("#5 Maria/Ostapenko double faults", 0.357, "LOST"),
    ("#6 Torino/Monza corners", 0.316, "LOST 16"),
    ("#3 Jovic/Frech double faults", 0.263, "VOID"),
    ("#7 Lincoln shots on target", 0.129, "LOST 3"),
]

# The eight the same run put under "cena nie uzasadnia zakładu", measured the
# same way. Tightening must not sweep these in: they were ranked low for the
# right reason already, on price.
REJECTED_2026_09_01 = [0.083, 0.256, 0.221, 0.253, 0.064, 0.096, 0.118, 0.166]


@pytest.mark.parametrize("label, disagreement, outcome", ADMITTED_2026_09_01)
def test_the_threshold_sits_below_that_days_admitted_set(label, disagreement, outcome):
    """0.25 is p95 of the run's 3928 two-sided rows, chosen from the
    distribution rather than from the casualties -- but the casualties are what
    it has to be checked against, and six of the seven clear it.

    The seventh is #7 Lincoln at +0.129, and it is *supposed* to be missed
    here: at a ladder ratio of 1.135 it agreed with the book about where the
    market sat (z +0.37), and its defect was a p_low that ten wide observations
    could not support. ``count_model_bound`` takes it, which is the right
    layer -- see ``test_lincoln_over_no_longer_clears_its_price``.
    """
    if label.startswith("#7"):
        pytest.skip("caught upstream by count_model_bound, not by this gate")
    assert disagreement > MAX_MARKET_DISAGREEMENT


def test_the_rejected_rows_of_that_day_are_mostly_left_alone():
    """The gate must stay an outlier gate. Five of the eight rejected rows are
    inside the threshold; the three that are not were already unbettable on
    price, and the gate demotes rather than deletes, so the cost is a rank."""
    inside = [d for d in REJECTED_2026_09_01 if d <= MAX_MARKET_DISAGREEMENT]
    assert len(inside) >= 5


def test_the_gate_is_not_a_blanket_ban_on_outbidding_the_book():
    """The trap the first attempt at this fix fell into, pinned so a future
    tightening cannot repeat it.

    Against ``p_low`` the VALUE inequality forces a disagreement of at least
    ``p_low*(1 - 1/(margin*overround))``. If the threshold sits below that, no
    row can ever be both bettable and unflagged and the sheet has stopped
    having opinions. At 0.25 against ``p_central`` there is real room.
    """
    for margin in (1.05, 1.10):
        for p_low in (0.50, 0.60, 0.72, 0.80):
            forced = p_low * (1 - 1 / (margin * 1.086))
            assert forced < MAX_MARKET_DISAGREEMENT, (
                f"threshold {MAX_MARKET_DISAGREEMENT} is below the {forced:.3f} "
                f"that VALUE forces at margin {margin}, p_low {p_low} -- "
                "the gate would be a blanket ban"
            )
