"""The 2026-09-07 review, pinned: league baselines, price tolerance, forecast cards.

Four defects were found by auditing that day's finished coupon and each one is
asserted here against the numbers it was found with.

1. **The shrinkage prior was league-blind and it was the whole of the day's only
   bet.** ``market_priors.json`` says so about itself ("one number for the
   Championship and the Ekstraklasa alike") and nobody had costed it. Barracas
   Central's first-half OVER 0.5 shipped as the file's single VALUE row at a
   threshold of 1.5989 against Superbet's 1.62. The Argentine Liga Profesional
   measures 0.821 first-half goals over 145 independent matches; the pinned
   prior is 1.243, and substituting it pulled the sample's own 0.900 centre up
   to 1.0143 instead of down to 0.8737. With the league's own number the
   threshold is 1.6880 and the row is 4.2% short of its price rather than 1.3%
   above it.

2. **A hard VETO left no trace when the row was already thin.** The tier gate
   ran before the veto branch, so a vetoed row sitting at WEAK left through
   ``tier_weak`` and never reached the branch that writes the note. That day's
   file recorded nine notes for ten vetoes and reported zero hard vetoes while
   the veto artifact held two.

3. **A no-op downgrade printed a second full copy of its reason.** ``variant``
   is the incoming tier, so one veto covering rows at LEAN and at WEAK rendered
   twice -- the second as ``WEAK→WEAK``, identical but for the arrow.

4. **The price threshold was a cliff.** Measured over 1,269 settled priced
   rows, ``gap >= 0%`` went 63.5% for -0.8% ROI on 52 rows while ``gap >= -5%``
   went 72.9% for +1.3% on 144. The 0% line threw away nine of every fourteen
   candidates for a worse point estimate.
"""
from __future__ import annotations

import pytest

from bet.simple_stats import coupons as coupons_module
from bet.simple_stats.analyze import (
    count_model_central,
    league_baselines,
    market_priors,
    shrinkage_target,
    shrunk_centre,
)
from bet.simple_stats.bet_builder_draft import AnalystVeto
from bet.simple_stats.contracts import (
    EventListV1,
    EventRecord,
    StatsSheetRow,
    StatsSheetV1,
    SuperbetEventOffer,
    SuperbetLine,
    SuperbetOfferV1,
)
from bet.simple_stats.coupons import PRICE_TOLERANCE_PCT, build_coupons

# Barracas Central v Argentinos Juniors, goals_1h_total, exactly as
# runs/2026-09-07/2026-09-07_event_dossiers.json left it: seven Liga Profesional
# matches for the home side, three Copa Sudamericana ones from May, ten Liga
# Profesional for the away side.
BARRACAS_1H = [
    0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0,   # comp 85, the current league
    2.0, 1.0, 2.0,                        # comp 33, a continental cup in May
    1.0, 0.0, 1.0, 2.0, 1.0, 1.0, 1.0, 1.0, 0.0, 1.0,
]
ARGENTINA_LEAGUE_ID = "85"
# Superbet's own two-sided price on that rung, devigged: 1/1.62 over
# (1/1.62 + 1/2.12).
BARRACAS_DEVIG = 0.5668


@pytest.fixture(autouse=True)
def _clear_caches():
    coupons_module.reset_competition_tier_cache()
    yield
    coupons_module.reset_competition_tier_cache()


# --- 1. the league-blind prior ----------------------------------------------


def test_the_argentine_league_measures_far_below_the_pinned_prior():
    """The fact the fix rests on, read straight off the config."""
    baselines = league_baselines()
    argentina = baselines["goals_1h_total"][ARGENTINA_LEAGUE_ID]
    assert argentina == pytest.approx(0.821, abs=0.01)
    assert market_priors()["goals_1h_total"] == pytest.approx(1.243, abs=0.001)
    # Not a rounding difference: the pooled prior is half again as high.
    assert market_priors()["goals_1h_total"] > 1.4 * argentina


def test_the_league_baseline_wins_and_says_where_it_came_from():
    value, source = shrinkage_target("goals_1h_total", None, ARGENTINA_LEAGUE_ID)
    assert value == pytest.approx(0.821, abs=0.01)
    assert source == f"league:{ARGENTINA_LEAGUE_ID}"


def test_precedence_is_league_then_venue_then_pooled():
    """Each step is a strictly narrower population than the one below it."""
    pooled_value, pooled_source = shrinkage_target("corners_for", None, None)
    venue_value, venue_source = shrinkage_target("corners_for", "home", None)
    assert pooled_source == "pooled"
    assert venue_source == "venue:home"
    assert venue_value != pooled_value
    # A venue prior must not override a measured league baseline: both correct
    # the same pooled number and the league one is the better measured.
    for market, per_league in league_baselines().items():
        if market == "corners_for" and per_league:
            some_league = next(iter(per_league))
            _, source = shrinkage_target(market, "home", some_league)
            assert source == f"league:{some_league}"
            break


def test_an_unmeasured_league_falls_back_rather_than_emptying_the_centre():
    """An unmeasured league is not a league whose average is zero."""
    value, source = shrinkage_target("goals_1h_total", None, "no-such-competition")
    assert source == "pooled"
    assert value == pytest.approx(1.243, abs=0.001)
    # And a market nobody has measured at all is left unshrunk, as before.
    assert shrunk_centre([1.0, 2.0, 3.0], "a_market_nobody_has_measured") == 2.0


def test_competition_id_none_reproduces_the_old_behaviour_exactly():
    """Every caller with no competition to name is unchanged."""
    assert shrunk_centre(BARRACAS_1H, "goals_1h_total") == pytest.approx(
        shrunk_centre(BARRACAS_1H, "goals_1h_total", None, None)
    )
    assert shrunk_centre(BARRACAS_1H, "goals_1h_total") == pytest.approx(
        1.0143, abs=1e-4
    )


def test_the_day_s_only_bet_no_longer_clears_its_price():
    """The whole finding, end to end, in the arithmetic that decides it."""
    n = len(BARRACAS_1H)
    assert n == 20

    old_centre = shrunk_centre(BARRACAS_1H, "goals_1h_total")
    new_centre = shrunk_centre(BARRACAS_1H, "goals_1h_total", None, ARGENTINA_LEAGUE_ID)
    # The prior pulled the sample *up*, away from both the league and the book.
    assert old_centre == pytest.approx(1.0143, abs=1e-4)
    assert new_centre == pytest.approx(0.8736, abs=1e-4)
    assert old_centre > max(BARRACAS_1H[:1] + [sum(BARRACAS_1H) / n])
    assert new_centre < sum(BARRACAS_1H) / n

    def threshold(centre: float) -> float:
        p_central = count_model_central(BARRACAS_1H, 0.5, "OVER", centre)
        weight = n / (n + 10.0)
        bar = weight * p_central + (1.0 - weight) * BARRACAS_DEVIG
        return 1.05 / bar  # CALL margin

    assert threshold(old_centre) == pytest.approx(1.5989, abs=1e-3)
    assert threshold(new_centre) == pytest.approx(1.6880, abs=1e-3)
    # Superbet posted 1.62. VALUE before, 4.2% short after.
    assert 1.62 >= threshold(old_centre)
    assert 1.62 < threshold(new_centre)
    assert (1.62 / threshold(new_centre) - 1.0) * 100 == pytest.approx(-4.2, abs=0.2)


# --- 2, 3, 4. the coupon ----------------------------------------------------


def _row(**over) -> StatsSheetRow:
    base = dict(
        event_id="evt-1",
        sport="football",
        market="corners_total",
        line=8.5,
        direction="UNDER",
        hits=9,
        sample_size=12,
        hit_rate=0.75,
        p_low=0.60,
        p_central=0.62,
        mean=6.0,
        median=6.0,
        dispersion=6.0**0.5,
        shrunk_mean=6.0,
        sources=["bzzoiro"],
        cross_provider_agreement="AGREE",
        corroborated_matches=9,
        confidence="HIGH",
        data_quality="READY",
    )
    base.update(over)
    return StatsSheetRow(**base)


def _sheet(*rows: StatsSheetRow) -> StatsSheetV1:
    return StatsSheetV1(
        run_id="RID-1",
        date="2026-09-07",
        generated_at="2026-09-07T00:00:00+00:00",
        rows=list(rows),
    )


def _events() -> EventListV1:
    return EventListV1(
        run_id="RID-1",
        date="2026-09-07",
        generated_at="2026-09-07T00:00:00+00:00",
        sports=["football"],
        events=[
            EventRecord(
                event_id="evt-1",
                sport="football",
                competition="Premier League",
                home_team="Home FC",
                away_team="Away FC",
                start_time="2026-09-07T18:00:00+00:00",
                source_ids={"bzzoiro": "1"},
                identity_confidence="CONFIRMED",
                status="ACTIVE",
            )
        ],
    )


def _offer(price: float) -> SuperbetOfferV1:
    return SuperbetOfferV1(
        run_id="RID-1",
        date="2026-09-07",
        generated_at="2026-09-07T00:00:00+00:00",
        source="superbet",
        window_start="2026-09-07T00:00:00+00:00",
        window_end="2026-09-08T00:00:00+00:00",
        events=[
            SuperbetEventOffer(
                superbet_event_id="1",
                superbet_match_name="Home FC·Away FC",
                sport="football",
                kickoff="2026-09-07T18:00:00Z",
                event_id="evt-1",
                match_quality="ID_MATCHED",
                lines=[
                    SuperbetLine(
                        market="corners_total",
                        line=8.5,
                        direction="UNDER",
                        price=price,
                        status="active",
                        source_market_name="corners_total",
                        source_outcome_name="x",
                    )
                ],
            )
        ],
    )


def _single(price: float, **row_over):
    coupons = build_coupons(
        _sheet(_row(**row_over)), _events(), superbet_offer=_offer(price)
    )
    assert len(coupons.singles) == 1
    return coupons.singles[0]


def test_the_tolerance_band_is_measured_at_five_percent():
    assert PRICE_TOLERANCE_PCT == 5.0


def test_a_price_just_under_the_bar_is_within_tolerance_not_below_it():
    """The cliff, removed. Same row, three prices around its own threshold."""
    threshold = _single(9.99).min_acceptable_odds
    assert threshold is not None

    above = _single(round(threshold + 0.01, 3))
    assert above.superbet_verdict == "VALUE"
    assert above.superbet_price_gap_pct > 0

    near = _single(round(threshold * 0.97, 3))
    assert near.superbet_verdict == "WITHIN_TOLERANCE"
    assert near.superbet_price_gap_pct == pytest.approx(-3.0, abs=0.3)

    far = _single(round(threshold * 0.85, 3))
    assert far.superbet_verdict == "PRICED_BELOW_THRESHOLD"
    assert far.superbet_price_gap_pct == pytest.approx(-15.0, abs=0.3)


def test_the_gap_is_a_percentage_because_odds_units_are_not_comparable():
    """0.06 of surplus is 4.6% at 1.30 and 2.2% at 2.70 -- one of those is
    inside the tolerance and one is not, and the odds difference cannot say
    which."""
    single = _single(1.30, p_central=0.83, p_low=0.80)
    assert single.superbet_price_gap_pct is not None
    assert single.superbet_surplus is not None
    recomputed = (single.superbet_price / single.min_acceptable_odds - 1.0) * 100
    assert single.superbet_price_gap_pct == pytest.approx(recomputed, abs=0.01)


def test_a_hard_veto_on_an_already_weak_row_is_still_recorded():
    """Defect 2. The row leaves as ``analyst_veto`` and the note is written."""
    thin = _row(sample_size=4, hits=3, p_low=0.55, p_central=0.60, confidence="LOW",
                cross_provider_agreement="SINGLE_SOURCE", corroborated_matches=0)
    coupons = build_coupons(
        _sheet(thin),
        _events(),
        superbet_offer=_offer(2.50),
        vetoes=[
            AnalystVeto(
                event_id="evt-1",
                market="corners_total",
                line=None,
                direction="UNDER",
                action="VETO",
                reason="FACT: cztery obserwacje z jednego turnieju.",
                reason_class="SAMPLE_NOT_REPRESENTATIVE",
            )
        ],
    )
    assert coupons.singles == []
    assert coupons.excluded.get("analyst_veto") == 1
    # Attribution: removed because the analyst removed it, not because it was thin.
    assert "tier_weak" not in coupons.excluded
    assert sum(1 for note in coupons.notes if note.startswith("WETO analityka")) == 1


def test_a_downgrade_that_changes_nothing_writes_no_note():
    """Defect 3. WEAK→WEAK is not a second finding."""
    thin = _row(sample_size=4, hits=3, p_low=0.55, p_central=0.60, confidence="LOW",
                cross_provider_agreement="SINGLE_SOURCE", corroborated_matches=0)
    coupons = build_coupons(
        _sheet(thin),
        _events(),
        superbet_offer=_offer(2.50),
        vetoes=[
            AnalystVeto(
                event_id="evt-1",
                market="corners_total",
                line=None,
                direction="UNDER",
                action="DOWNGRADE",
                reason="FACT: probka opisuje inny mecz.",
                reason_class="SAMPLE_NOT_REPRESENTATIVE",
            )
        ],
    )
    assert coupons.singles == []
    assert not [note for note in coupons.notes if "WEAK→WEAK" in note]


def test_a_downgrade_that_does_change_the_tier_still_writes_its_note():
    """The mirror of the test above -- the fix must not silence a real step."""
    coupons = build_coupons(
        _sheet(_row()),
        _events(),
        superbet_offer=_offer(2.50),
        vetoes=[
            AnalystVeto(
                event_id="evt-1",
                market="corners_total",
                line=None,
                direction="UNDER",
                action="DOWNGRADE",
                reason="FACT: sedzia juz jest w srodku.",
                reason_class="OTHER",
            )
        ],
    )
    notes = [note for note in coupons.notes if note.startswith("DOWNGRADE analityka")]
    assert len(notes) == 1
    assert "→" in notes[0]


def test_the_bar_still_reconstructs_from_the_components_the_row_prints():
    """The tolerance must not have introduced a second answer to the bar.

    Checked against the row's own published decomposition rather than by
    calling ``required_odds`` with a hand-picked market probability: the coupon
    devigs the book's *two-sided* ladder and this fixture posts one side, so
    ``bar.p_market`` is correctly None here and a test that supplied 0.40
    anyway would be asserting a different question.
    """
    single = _single(2.50)
    assert single.bar_basis == "p_central"
    assert single.market_probability is None  # one-way rung, nothing to devig
    assert single.bar_sample_probability == pytest.approx(single.p_central, abs=1e-4)
    assert single.bar_probability == pytest.approx(single.p_central, abs=1e-4)
    margin = {"CALL": 1.05, "LEAN": 1.10}[single.tier]
    assert single.min_acceptable_odds == pytest.approx(
        margin / single.bar_probability, abs=1e-3
    )


def test_a_two_sided_rung_shrinks_toward_the_book_and_the_bar_follows():
    """The other half: with both sides posted the bar is the shrunk blend."""
    offer = _offer(2.50)
    offer.events[0].lines.append(
        SuperbetLine(
            market="corners_total", line=8.5, direction="OVER", price=1.55,
            status="active", source_market_name="corners_total",
            source_outcome_name="x",
        )
    )
    coupons = build_coupons(_sheet(_row()), _events(), superbet_offer=offer)
    single = coupons.singles[0]
    assert single.market_probability is not None
    devig = (1 / 2.50) / (1 / 2.50 + 1 / 1.55)
    assert single.market_probability == pytest.approx(devig, abs=1e-3)
    weight = single.sample_size / (single.sample_size + single.shrink_k)
    assert single.sample_weight == pytest.approx(weight, abs=1e-4)
    expected_bar = weight * single.p_central + (1 - weight) * single.market_probability
    assert single.bar_probability == pytest.approx(expected_bar, abs=1e-3)
    margin = {"CALL": 1.05, "LEAN": 1.10}[single.tier]
    assert single.min_acceptable_odds == pytest.approx(
        margin / single.bar_probability, abs=1e-3
    )


def test_a_format_with_too_few_fixtures_borrows_the_worse_twin():
    """Silence is the worst of the three answers available.

    ``total_games@BO5`` sits just under the 25-fixture floor, which is exactly
    a US Open men's final, and reporting that market as never-checked hides
    that its best-of-three twin runs 18.3 points hot on its confident rows.
    Where more than one format could be borrowed from, the worse one is taken:
    a format we could not measure must not inherit the kinder reading of a
    format we could.
    """
    from bet.simple_stats.forecast import _entry_for

    table = {
        "total_games@BO3": {"skill": -0.0883, "fixtures": 88},
        "total_games@BO5": {"skill": -0.30, "fixtures": 60},
    }
    entry, borrowed = _entry_for(table, "total_games@BO3", "total_games", "tennis")
    assert borrowed is None, "an exact hit borrows nothing"
    assert entry["skill"] == -0.0883

    thin = {"total_games@BO3": table["total_games@BO3"]}
    entry, borrowed = _entry_for(thin, "total_games@BO5", "total_games", "tennis")
    assert borrowed == "total_games@BO3"
    assert entry["skill"] == -0.0883

    entry, borrowed = _entry_for(table, "total_games@UNKNOWN", "total_games", "tennis")
    assert borrowed == "total_games@BO5", "the worse of the two, not the first"

    assert _entry_for(table, "aces_total@BO5", "aces_total", "tennis") == (None, None)


def test_a_hot_market_grades_overconfident_before_its_level_is_read():
    """A market can have an acceptable centre and a hot tail at once, and the
    tail is the thing with money on it. ``shots_for`` scores +4.3% skill over
    551 settled fixtures -- so no level grade touches it -- and its rows
    claiming 0.70 or more have realised 71.2% against a claimed 77.9%, over
    527 fixtures.

    The grade names the threshold rather than the market, because below it the
    market is calibrated and saying otherwise would throw away good rows. Note
    which pool the figures come from: ``hot_above_detail`` pools every rung
    claiming at least ``hot_above``, and it is *not* ``at_75`` -- for
    ``shots_for`` those are 0.779 -> 0.712 over 527 fixtures against
    0.814 -> 0.735 over 437, and quoting one threshold beside the other's
    numbers is the kind of mismatch a fact-check pass exists to catch.
    """
    from bet.simple_stats.forecast import _grade

    hot = {
        "skill": 0.043,
        "skill_comparable": True,
        "fixtures": 551,
        "mae": 4.27,
        "mae_constant": 4.46,
        "actual_mean": 13.68,
        "actual_sd": 5.6,
        "bias": -0.50,
        "hot_above": 0.70,
        "hot_above_detail": {
            "rungs": 1974, "fixtures": 527, "claimed": 0.7793,
            "realised": 0.7124, "gap": 0.0669, "gap_ci_low": 0.0353,
        },
    }
    grade, why = _grade(hot)
    assert grade == "OVERCONFIDENT"
    assert "71.2%" in why and "77.9%" in why
    assert "70%" in why and "calibrated" in why

    # Drop the threshold and the same entry grades MEASURED instead, which is
    # what makes the order of the checks load-bearing rather than cosmetic.
    cool = {k: v for k, v in hot.items() if not k.startswith("hot_above")}
    assert _grade(cool)[0] == "MEASURED"


def test_a_rare_market_is_still_graded_biased_when_it_doubles_the_level():
    """The base-rate argument runs one way only, and gating on it in both
    directions produced a wrong grade on a real market.

    ``red_cards_total`` forecasts 0.35 against an actual 0.16 over 593 settled
    fixtures -- bias +0.19 on a spread of 0.42, 45% of the market's own
    variation -- and its MAE loses to "just say 0.16" by 47%. Because it
    happens under 0.5 times a match it carries ``skill_comparable: false``, and
    while that flag was checked *before* the level grades it read
    ``LEVEL_ONLY``: "the level is worth something", about a forecast that
    doubles the level.

    A positive skill on a rare market is unimpressive because predicting
    roughly nothing for everybody is close to right. A negative one is not
    meaningless: losing to the constant is not something luck does.
    """
    from bet.simple_stats.forecast import _grade

    rare = {
        "skill": -0.4704,
        "skill_comparable": False,
        "fixtures": 593,
        "mae": 0.404,
        "mae_constant": 0.275,
        "actual_mean": 0.16,
        "actual_sd": 0.418,
        "bias": 0.188,
        "overconfident_at_75": False,
    }
    grade, why = _grade(rare)
    assert grade == "BIASED"
    assert "+0.19" in why and "45%" in why

    # Inside the bias ceiling and with a *positive* skill it does fall through
    # to LEVEL_ONLY, which is the case the flag was added for: player_offsides
    # scores +24.2% and that is not evidence about offsides.
    credited = {**rare, "skill": 0.2422, "bias": -0.03, "actual_mean": 0.13}
    grade, why = _grade(credited)
    assert grade == "LEVEL_ONLY"
    assert "not evidence that we forecast it well" in why


def test_a_low_base_rate_market_never_grades_measured_on_its_skill():
    """``player_offsides`` happens 0.13 times a match and scores +24.2%. That is
    not evidence that we forecast offsides better than fouls -- predicting
    roughly nothing for everybody is close to right without discriminating
    between anybody -- and a MEASURED grade there would put it at the top of a
    file sorted by grade.
    """
    from bet.simple_stats.forecast import _grade

    grade, why = _grade(
        {
            "skill": 0.2422,
            "skill_comparable": False,
            "fixtures": 329,
            "mae": 0.17,
            "mae_constant": 0.224,
            "actual_mean": 0.13,
            "actual_sd": 0.36,
            "bias": -0.03,
        }
    )
    assert grade == "LEVEL_ONLY"
    assert "0.13" in why and "base rate" in why


def test_a_borrowed_measurement_says_so_in_its_reason():
    """The prefix is the point. A number borrowed from another format read as a
    measurement of this one is exactly the overconfidence this file exists to
    report.
    """
    from bet.simple_stats.forecast import _grade

    entry = {
        "skill": -0.0883,
        "skill_comparable": True,
        "fixtures": 88,
        "mae": 5.24,
        "mae_constant": 4.81,
        "actual_mean": 21.53,
        "actual_sd": 5.9,
        "bias": 1.2,
    }
    _, why = _grade(entry, borrowed_from="total_games@BO3")
    assert why.startswith("this format has too few settled fixtures")
    assert "total_games@BO3" in why
    assert "floor" in why
