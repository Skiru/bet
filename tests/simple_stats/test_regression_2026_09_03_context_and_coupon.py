"""2026-09-03: context that existed and never arrived, and a coupon that
picked its rungs by sort order.

Five findings, all from the same audit and all verified against
``runs/2026-09-03/``:

* ``round_name``, ``group_name`` and ``previous_leg_event_id`` were null in
  165 of 165 dossiers although ``/events/`` publishes all three on the row the
  discovery adapter had already fetched. The Grêmio-Internacional fixture was
  a quarter-final second leg of a 0-0 tie and nothing knew.
* ``is_local_derby`` was **false** for that fixture, on the same payload that
  reported ``travel_distance_km: 11``. No code path degraded the biggest derby
  of the day.
* ``possession`` was 100.0 on 522 of 530 observations and 0.0 on the other 8:
  a per-side percentage put through the combiner that sums both sides.
* ``_confidence`` read HIGH at n>=8 with no per-side floor, so 4+4 read as
  settled -- on Neom-Al-Khaleej and Al-Fayha-Al-Kholood, both card markets.
* The coupon kept one row per (event, market, subject) and picked by price
  surplus, so the Grenal's cards 8.5 UNDER -- 20/20 with the sample's maximum
  below the line -- was dropped as ``duplicate_market_for_event`` in favour of
  7.5, which sat on the sample's mode.

No network. Every payload is a recorded shape.
"""
import pytest

from bet.simple_stats.bet_builder_draft import (
    BUILDER_SCORE_MIN,
    BetBuilderLeg,
    builder_score,
    implies,
    mechanism_family,
)
from bet.simple_stats.context_flags import (
    CEILING_DERBY,
    CEILING_KNOCKOUT_SECOND_LEG,
    CEILING_MISSING_REFEREE,
    CEILING_NO_REFERENCE_SOURCE,
    is_derby,
    knockout_second_leg_is_live,
    lean_ceilings_for_row,
    referee_card_points_per_match,
)
from bet.simple_stats.contracts import (
    SLATE_CRITICAL_SOURCES,
    EventDossierV1,
    FixtureContext,
    MetricObservation,
    ProviderValue,
    RefereeProfile,
    StatsSheetRow,
)
from bet.simple_stats.analyze import (
    ONE_SIDED_SAMPLE,
    _MIN_SIDE_FOR_HIGH,
    _confidence,
    analyze_dossier,
    count_hits,
)
from bet.simple_stats.discover import _degraded_reasons
from bet.simple_stats.providers import (
    _BZZOIRO_TOTAL_ALIASES,
    _ESPN_FOOTBALL_ALIASES,
    _HIGHLIGHTLY_NORMALIZED_ALIASES,
)


# The Grenal's own fixture context, as the backfilled event list carries it.
GRENAL_CONTEXT = FixtureContext(
    referee_id="1835",
    venue_id="152",
    league_id="35",
    is_local_derby=False,
    is_neutral_ground=False,
    travel_distance_km=11.0,
    round_name="Quarterfinals",
    group_name=None,
    previous_leg_event_id="587786",
    previous_leg_goals_home=0,
    previous_leg_goals_away=0,
    home_team_id="154",
    away_team_id="161",
)


def _dossier(**overrides) -> EventDossierV1:
    fields = dict(
        event_id="evt-1",
        sport="football",
        team_a_name="Grêmio",
        team_b_name="Internacional",
        readiness="READY",
        fixture_context=GRENAL_CONTEXT,
    )
    fields.update(overrides)
    return EventDossierV1(**fields)


def _row(**overrides) -> StatsSheetRow:
    fields = dict(
        event_id="evt-1",
        sport="football",
        market="cards_points_total",
        line=8.5,
        direction="UNDER",
        hits=16,
        sample_size=20,
        hit_rate=0.8,
        p_low=0.584,
        p_central=0.859,
        mean=6.25,
        median=6.0,
        dispersion=2.5,
        sources=["bzzoiro"],
        cross_provider_agreement="PARTIAL_AGREE",
        confidence="HIGH",
        data_quality="READY",
    )
    fields.update(overrides)
    return StatsSheetRow(**fields)


# --- Phase 5: the derby the provider denied --------------------------------


def test_eleven_kilometres_is_a_derby_whatever_the_provider_says():
    """``/events/587790/`` answers ``is_local_derby: false`` with
    ``travel_distance_km: 11`` on the same row."""
    assert GRENAL_CONTEXT.is_local_derby is False
    assert is_derby(_dossier()) is True


def test_the_pinned_pair_is_a_derby_even_with_no_distance():
    """Belt and braces on the one case where the flag is known to lie."""
    context = GRENAL_CONTEXT.model_copy(update={"travel_distance_km": None})
    assert is_derby(_dossier(fixture_context=context)) is True


@pytest.mark.parametrize("km,expected", [(11.0, True), (24.9, True), (25.0, False), (55.0, False)])
def test_the_distance_rule_is_a_conurbation_and_not_a_region(km, expected):
    context = FixtureContext(is_local_derby=False, travel_distance_km=km)
    assert is_derby(_dossier(fixture_context=context)) is expected


def test_a_fixture_with_no_context_is_not_a_derby():
    assert is_derby(_dossier(fixture_context=None)) is False


# --- Phase 5: the second leg -----------------------------------------------


@pytest.mark.parametrize(
    "home,away,live",
    [
        (0, 0, True),    # the Grenal: level, everything still to play for
        (2, 1, True),    # one goal
        (1, 2, True),
        (4, 0, False),   # decided; the second leg is a friendly
        (0, 3, False),
    ],
)
def test_only_a_live_tie_counts_as_a_second_leg(home, away, live):
    context = GRENAL_CONTEXT.model_copy(update={
        "previous_leg_goals_home": home, "previous_leg_goals_away": away,
    })
    assert knockout_second_leg_is_live(_dossier(fixture_context=context)) is live


def test_an_unreadable_first_leg_keeps_the_ceiling_on():
    """The pointer exists and the score does not. A two-legged tie of unknown
    aggregate is still a two-legged tie, and the cautious reading of an unknown
    is the one that keeps the ceiling."""
    context = GRENAL_CONTEXT.model_copy(update={
        "previous_leg_goals_home": None, "previous_leg_goals_away": None,
    })
    assert knockout_second_leg_is_live(_dossier(fixture_context=context)) is True


def test_no_first_leg_is_not_a_second_leg():
    context = GRENAL_CONTEXT.model_copy(update={"previous_leg_event_id": None})
    assert knockout_second_leg_is_live(_dossier(fixture_context=context)) is False


# --- Phase 5: what the ceilings do -----------------------------------------


def test_the_grenal_card_under_collects_both_ceilings_and_stays_a_lean():
    reasons = lean_ceilings_for_row(_row(), _dossier())
    assert set(reasons) == {CEILING_DERBY, CEILING_KNOCKOUT_SECOND_LEG}


def test_the_over_side_is_left_alone():
    """A derby and a live tie make a match rougher than either side's last ten,
    so the UNDER is the side the sample flatters. Nothing in this pipeline
    promotes a row on context, so the OVER gets no ceiling -- only the
    ``SUPPORTS`` flag it already had."""
    assert lean_ceilings_for_row(_row(direction="OVER"), _dossier()) == []


def test_a_card_market_with_no_referee_cannot_be_a_call():
    context = GRENAL_CONTEXT.model_copy(update={"referee_id": None})
    reasons = lean_ceilings_for_row(_row(direction="OVER"), _dossier(fixture_context=context))
    assert reasons == [CEILING_MISSING_REFEREE]


def test_a_sport_with_no_provider_of_record_cannot_be_a_call():
    """bzzoiro-tennis answers HTTP 402 and was withdrawn, so tennis has no
    provider of record and no tennis row is a CALL. Keyed on the roster rather
    than on the string "tennis", so the day a tennis primary is entitled this
    lifts by itself."""
    reasons = lean_ceilings_for_row(
        _row(sport="tennis", market="aces_for", team_name="Anastasia Potapova"),
        _dossier(sport="tennis", fixture_context=None),
    )
    assert CEILING_NO_REFERENCE_SOURCE in reasons


# --- Phase 5: the referee, in the units the market settles ------------------


def test_a_referees_average_is_converted_into_booking_points():
    """Bruno Arleu de Araujo on the Grenal: 49 matches, and the blend note the
    sheet printed reads 5.89/match. Comparing his yellow-only average against a
    booking-points line was the quieter half of the card defect -- it put him
    on the UNDER side of a line he is in fact above."""
    referee = RefereeProfile(
        provider_referee_id="1835", name="B. Araujo", matches=49,
        avg_yellow_per_match=4.65, avg_red_per_match=0.62,
    )
    assert referee_card_points_per_match(referee) == pytest.approx(5.89, abs=0.01)
    assert referee.avg_yellow_per_match < 5.89


def test_a_referee_with_no_yellow_average_has_no_card_points_average():
    referee = RefereeProfile(
        provider_referee_id="1", matches=30, avg_red_per_match=0.5,
    )
    assert referee_card_points_per_match(referee) is None


# --- Phase 5: the per-side confidence floor --------------------------------


@pytest.mark.parametrize(
    "sides,total,expected,reason",
    [
        # Neom-Al-Khaleej and Al-Fayha-Al-Kholood, measured: 4 observations a
        # side on cards_points_total. Both read HIGH before this rule.
        ((4, 4), 10, "MEDIUM", ONE_SIDED_SAMPLE),
        # The note's other example.
        ((3, 11), 14, "MEDIUM", ONE_SIDED_SAMPLE),
        # One side reduced to a single trial.
        ((1, 19), 20, "LOW", ONE_SIDED_SAMPLE),
        # Five a side, which is what ENRICH already calls a complete sample.
        ((5, 15), 20, "HIGH", None),
        # A per-team row or a player prop has one side by construction and must
        # not be capped for it.
        (None, 20, "HIGH", None),
    ],
)
def test_a_total_is_only_settled_when_both_sides_are(sides, total, expected, reason):
    assert _confidence("AGREE", total, sides) == (expected, reason)


def test_the_per_side_floor_matches_enrichs_own_definition_of_a_complete_sample():
    """``data_quality == "READY"`` means the primary served at least five
    matches a side, and that is what buys CALL. A sheet whose word for
    "settled" disagreed with its tier for "settled" about how many matches a
    side that takes would be two rules wearing one name."""
    assert _MIN_SIDE_FOR_HIGH == 5


# --- Phase 5: possession was a constant ------------------------------------


def test_no_provider_reports_possession_any_more():
    """522 of 530 observations were exactly 100.0 and the other 8 were 0.0 --
    a per-side percentage summed by the combiner that sums both sides of a
    count. No market read it, so nothing is unpriced by its removal."""
    for table in (_ESPN_FOOTBALL_ALIASES, _HIGHLIGHTLY_NORMALIZED_ALIASES,
                  _BZZOIRO_TOTAL_ALIASES):
        assert "possession" not in table.values()


# --- Phase 6: conflicts, and what a corroborated sample is -----------------


def _pv(provider, value, day, opponent, match_id):
    return ProviderValue(
        provider=provider, match_id=match_id, match_date=f"2026-08-{day}",
        opponent=opponent, value=value, observed_at="2026-09-03T00:00:00+00:00",
    )


def test_the_lower_value_no_longer_wins_a_conflict_by_default():
    """Náutico read 6 against 8 on one match and América 8 against 4, and both
    entered their samples as the smaller number -- ``median_low`` over a pair
    keeps the minimum. Every card row on the slate is an UNDER.

    At a line the pair straddles the observation now leaves the sample; at a
    line it does not, the adverse value is the one the centre is built from.
    """
    conflicted = _pv("bzzoiro", 6.0, "01", "Náutico", "a").model_copy(
        update={"conflict_low": 6.0, "conflict_high": 8.0}
    )
    clean = _pv("bzzoiro", 4.0, "08", "Botafogo", "b")

    straddled = count_hits([conflicted, clean], 7.5, "UNDER")
    assert straddled.sample_size == 1
    assert straddled.conflicts_on_line == 1

    outside = count_hits([conflicted, clean], 8.5, "UNDER")
    assert outside.sample_size == 2
    assert outside.conflicts_resolved_adverse == 1


def test_agree_needs_half_the_sample_and_not_two_matches_of_it():
    """The Grenal's card rows read AGREE on 3 corroborated matches out of 20 --
    the field that says so was already on the row and the label ignored it,
    while ``tier_for_row`` reads AGREE as "corroborated" and hands out CALL.

    Built as a real 20-match sample with a second provider on three of them,
    which is the shape the audit found.
    """
    observations = []
    for day in range(1, 21):
        observations.append(_pv("bzzoiro", 5.0, f"{day:02d}", f"Opp{day}", f"bz{day}"))
        if day <= 3:
            observations.append(
                _pv("espn-football", 5.0, f"{day:02d}", f"Opp{day}", f"es{day}")
            )
    dossier = _dossier(metrics={
        "cards_points_total": MetricObservation(
            canonical_name="cards_points_total", team_a_l10=observations,
        )
    })
    rows = [r for r in analyze_dossier(dossier) if r.market == "cards_points_total"]
    assert rows
    row = rows[0]
    assert row.cross_provider_agreement == "PARTIAL_AGREE"
    assert row.corroborated_matches == 3
    assert row.sample_size == 20


def test_an_exhausted_slate_driver_is_named_as_degrading_the_slate():
    """highlightly drives discovery breadth, so running out of its quota
    removes about 77% of the day's fixtures. On 2026-09-03 it was 101/100
    before the run started and DISCOVER reported OK."""
    assert "highlightly" in SLATE_CRITICAL_SOURCES
    reasons = _degraded_reasons({
        "highlightly": ["daily quota exhausted before page offset=0 (0 left)"],
    })
    assert len(reasons) == 1
    assert "highlightly" in reasons[0]


def test_a_corroborator_timing_out_is_not_a_degraded_slate():
    """A source that 404s one page has cost corroboration, which is a
    different and much smaller problem than a source that stops producing
    fixtures. A label that fires on both is a label nobody reads."""
    assert _degraded_reasons({"espn-football": ["page offset=0: timeout"]}) == []
    assert _degraded_reasons({"highlightly": ["page offset=0: timeout"]}) == []


# --- Phase 8: mechanisms, nesting and §44 ----------------------------------


def _leg(market, line, direction, **kw):
    fields = dict(
        event_id="evt-1", market=market, line=line, direction=direction,
        tier="CALL", p_low=0.70, p_central=0.80, hit_rate=0.8, sample_size=12,
        fair_odds=1.43, min_acceptable_odds=1.50,
    )
    fields.update(kw)
    return BetBuilderLeg(**fields)


def test_cards_and_fouls_are_one_mechanism():
    """"Cards under 8.5" and "fouls under 36.5" in one fixture are two readings
    of how rough the referee lets the match get. The Grenal slip took both,
    plus a per-team card line: three legs, one mechanism."""
    assert mechanism_family(_leg("cards_points_total", 8.5, "UNDER")) == "discipline"
    assert mechanism_family(_leg("fouls_total", 36.5, "UNDER")) == "discipline"
    assert mechanism_family(_leg("cards_points_for", 3.5, "UNDER")) == "discipline"
    assert mechanism_family(_leg("corners_total", 9.5, "UNDER")) == "attacking"
    assert mechanism_family(_leg("goals_total", 2.5, "OVER")) == "scoring"
    assert mechanism_family(_leg("total_games", 22.5, "UNDER")) == "length"


def test_two_props_on_two_players_are_not_one_mechanism():
    """The closest thing a same-match slip has to independent legs."""
    one = mechanism_family(_leg("player_total_shots", 1.5, "OVER", player_name="A"))
    two = mechanism_family(_leg("player_total_shots", 1.5, "OVER", player_name="B"))
    assert one != two


@pytest.mark.parametrize(
    "first,second,nested",
    [
        # The same market at two rungs.
        (("cards_points_total", 3.5, "UNDER"), ("cards_points_total", 8.5, "UNDER"), True),
        (("cards_points_total", 8.5, "OVER"), ("cards_points_total", 3.5, "OVER"), True),
        # A part inside its whole: Internacional's cards within the match's.
        (("cards_points_for", 3.5, "UNDER"), ("cards_points_total", 8.5, "UNDER"), True),
        # Opposite directions are not an implication.
        (("cards_points_for", 3.5, "UNDER"), ("cards_points_total", 8.5, "OVER"), False),
        # Different mechanisms entirely.
        (("corners_total", 9.5, "UNDER"), ("goals_total", 2.5, "UNDER"), False),
    ],
)
def test_a_leg_that_nearly_guarantees_another_is_not_a_second_leg(first, second, nested):
    assert implies(first, second) is nested


def test_the_builder_score_is_the_documents_weights_on_this_repos_terms():
    """docs/SUPERBET_BET_BUILDER_METHOD_v3.md §44 gives the five weights and
    names the terms; the definitions are this repo's. Checked by hand so a
    change to either the weights or a definition shows up here."""
    legs = [
        _leg("cards_points_total", 8.5, "UNDER", p_central=0.70, sample_size=12),
        _leg("corners_total", 9.5, "UNDER", p_central=0.90, sample_size=6),
    ]
    score, parts = builder_score(legs, correlation_risk="HIGH", bar_basis="p_central")
    assert parts == {
        "weakest_leg": 0.70,
        "mean_leg": 0.80,
        "correlation": 0.4,
        "robustness": 1.0,     # two mechanisms, two legs
        "data_quality": 0.75,  # (12/12 + 6/12) / 2
    }
    assert score == pytest.approx(
        0.40 * 0.70 + 0.25 * 0.80 + 0.15 * 0.4 + 0.10 * 1.0 + 0.10 * 0.75
    )
    assert score >= BUILDER_SCORE_MIN


def test_a_one_leg_draft_has_no_builder_score():
    assert builder_score([_leg("cards_points_total", 8.5, "UNDER")]) == (None, {})


def test_a_contradicted_source_docks_the_data_quality_term():
    """§44's source-conflict penalty, folded into the term it is about rather
    than subtracted afterwards."""
    legs = [
        _leg("cards_points_total", 8.5, "UNDER", sample_size=12,
             caveats=["providers disagree and were never averaged"]),
        _leg("corners_total", 9.5, "UNDER", sample_size=12),
    ]
    _score, parts = builder_score(legs)
    assert parts["data_quality"] == 0.75  # (0.5 + 1.0) / 2
