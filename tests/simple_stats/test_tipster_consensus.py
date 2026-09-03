"""Tipster consensus: counting other people's opinions without pricing them.

The appendix exists because TIPSTERS collects a lot and delivers almost
nothing. On 2026-09-03: 55 picks ingested, 39 matched to a fixture, **2
countable** -- so the coupon's *Typerzy* column read `brak` on all four singles
that mattered. The 37 discarded picks were 1X2, BTTS or combos: a different
market, not a broken one.

These tests pin two things. First, that the narrow 1X2 recovery reads exactly
the claims it should and refuses everything else -- it is the only place this
module interprets text, and `1 + OVER 1,5 gola` starting with a `1` is the trap
it must not fall into. Second, that the boundary holds: no probability, no
price, no threshold, and consensus is never filtered down to the coupon.
"""
from __future__ import annotations

import pytest

from bet.simple_stats.contracts import (
    TipsterEventSignal,
    TipsterPickRef,
    TipsterSignalV1,
)
from bet.simple_stats.tipster_consensus import (
    TipsterConsensusRow,
    _bare_1x2_direction,
    build_consensus,
)


def _pick(tipster, claim, direction=None, *, line=None, market=None, odds=None,
          source="ZawodTyper"):
    return TipsterPickRef(
        source_id=source.lower(),
        source_name=source,
        tipster_name=tipster,
        claim=claim,
        market=market,
        line=line,
        direction=direction,
        subjects=[],
        countable=False,
        reject_reason="",
        odds=odds,
        match_date="2026-09-03",
    )


def _signal(*events, ingested=0, matched=0, countable=0):
    return TipsterSignalV1(
        run_id="r",
        date="2026-09-03",
        generated_at="2026-09-03T05:00:00+00:00",
        sources_attempted=["zawodtyper"],
        sources_with_picks=["zawodtyper"],
        sources_blocked=[],
        picks_ingested=ingested,
        picks_matched=matched,
        picks_unmatched=0,
        countable_claims=countable,
        date_filter={},
        unmatched_events=[],
        events=list(events),
    )


def _event(event_id, home, away, picks, quality="EXACT"):
    return TipsterEventSignal(
        event_id=event_id,
        home_team=home,
        away_team=away,
        match_quality=quality,
        match_score=100,
        picks=picks,
        public_lean={},
    )


# --- the only place this module reads text ---------------------------------

@pytest.mark.parametrize(
    "claim,expected",
    [
        ("1", "HOME"),
        ("2", "AWAY"),
        ("x", "DRAW"),
        ("X", "DRAW"),
        # The live case: Gent-Leuven 2026-09-03. The parser left it OTHER while
        # another source's `Winner: 1` on the same fixture became HOME, so the
        # two never met and the agreement was invisible.
        ("1(Superzprzewage)", "HOME"),
        ("1 ", "HOME"),
    ],
)
def test_bare_1x2_is_recovered(claim, expected):
    assert _bare_1x2_direction(claim) == expected


@pytest.mark.parametrize(
    "claim",
    [
        # Starts with a 1 and is emphatically not a home-win pick. This is the
        # whole reason the disqualifier list exists.
        "1 + OVER 1,5 gola",
        "X2 + powyżej 1.5 gola w meczu",
        "Over 4,5 żółtych kartek + Millonarios Over 2,5 rożne",
        "o2,5",
        "4.5+",
        "Over 0.5 HT + Over 1.5 FT",
        "Liczba fauli Palmeiras -13,5",
        "MANTOVA POWYŻEJ 9.5 STRZAŁÓW",
        "over 17,5 gems",
        "Tabilo",
        "Wygra Tabilo",
        "BTTS",
        "",
        None,
    ],
)
def test_claims_that_must_not_be_read_as_1x2(claim):
    assert _bare_1x2_direction(claim) is None


# --- what counts as agreement ---------------------------------------------

def test_two_distinct_tipsters_on_one_side_is_consensus():
    signal = _signal(
        _event("e1", "Gent", "Leuven", [
            _pick("Kacper", "1(Superzprzewage)", "OTHER", odds=1.63),
            _pick("Fitim84", "Winner: 1", "HOME", odds=1.61, source="Typersi"),
        ])
    )
    result = build_consensus(signal)
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.direction == "HOME"
    assert row.tipster_count == 2
    assert row.tipsters == ["Fitim84", "Kacper"]
    assert row.sources == ["Typersi", "ZawodTyper"]
    assert row.odds_seen == pytest.approx(1.62)


def test_one_tipster_twice_is_one_opinion():
    """Distinct people, not distinct picks -- otherwise a prolific poster or
    two sources republishing one tipster would manufacture agreement."""
    signal = _signal(
        _event("e1", "A", "B", [
            _pick("Kacper", "1", "HOME"),
            _pick("Kacper", "Winner: 1", "HOME", source="Typersi"),
        ])
    )
    assert build_consensus(signal).rows == []


def test_a_single_pick_is_not_consensus_but_is_counted():
    signal = _signal(_event("e1", "A", "B", [_pick("maer20", "Winner: 1", "HOME")]))
    result = build_consensus(signal)
    assert result.rows == []
    assert result.events_with_one_pick == 1


def test_opposite_sides_do_not_aggregate():
    signal = _signal(
        _event("e1", "A", "B", [
            _pick("one", "1", "HOME"),
            _pick("two", "2", "AWAY"),
        ])
    )
    assert build_consensus(signal).rows == []


# --- totals need a line to be a claim at all -------------------------------

def test_over_without_a_line_is_unusable_not_guessed():
    """Two people saying "over" agree about nothing if one means 1.5 goals and
    the other 4.5 cards."""
    signal = _signal(
        _event("e1", "A", "B", [
            _pick("one", "o2,5", "OVER"),
            _pick("two", "Over 0.5 HT + Over 1.5 FT", "OVER"),
        ])
    )
    result = build_consensus(signal)
    assert result.rows == []
    assert result.unusable_picks == 2
    assert result.unusable_by_reason == {"total bez czytelnej linii": 2}


def test_over_with_a_line_and_market_can_agree():
    signal = _signal(
        _event("e1", "A", "B", [
            _pick("one", "over 17,5 gems", "OVER", line=17.5, market="total_games"),
            _pick("two", "17.5+", "OVER", line=17.5, market="total_games"),
        ])
    )
    rows = build_consensus(signal).rows
    assert len(rows) == 1
    assert rows[0].direction == "OVER total_games 17.5"


def test_same_market_different_lines_do_not_agree():
    signal = _signal(
        _event("e1", "A", "B", [
            _pick("one", "over 17,5", "OVER", line=17.5, market="total_games"),
            _pick("two", "over 21,5", "OVER", line=21.5, market="total_games"),
        ])
    )
    assert build_consensus(signal).rows == []


def test_win_without_a_subject_is_reported_not_assigned():
    """Popyrin-Tabilo 2026-09-03: both `Tabilo` and `Wygra Tabilo` parsed as
    WIN with empty subjects, so which player is meant exists only in the text.
    Two tipsters did agree, and we still must not claim to know on whom."""
    signal = _signal(
        _event("e1", "Alexei Popyrin", "Alejandro Tabilo", [
            _pick("Kacper Pocztowski", "Tabilo", "WIN"),
            _pick("koxu 99", "Wygra Tabilo", "WIN"),
        ])
    )
    result = build_consensus(signal)
    assert result.rows == []
    assert result.unusable_by_reason == {"typ bez wskazanego podmiotu": 2}


# --- the boundary ----------------------------------------------------------

def test_consensus_is_not_filtered_to_the_coupon():
    """A fixture the crowd converges on which our sheet never priced is the
    most interesting row here. Filtering to the coupon would make this a mirror
    of the coupon instead of a second opinion on the day."""
    signal = _signal(
        _event("off", "MKS Avia Świdnik", "Wieczysta Kraków", [
            _pick("Iwonka1990", "2", "AWAY"),
            _pick("Pawel Stokowski", "2", "AWAY"),
        ], quality="FUZZY")
    )
    result = build_consensus(signal, frozenset({"some-other-event"}))
    assert len(result.rows) == 1
    assert result.rows[0].on_coupon is False


def test_coupon_fixtures_sort_first_then_by_depth_of_agreement():
    signal = _signal(
        _event("off", "Off A", "Off B", [
            _pick("a", "1", "HOME"), _pick("b", "1", "HOME"), _pick("c", "1", "HOME"),
        ]),
        _event("on", "On A", "On B", [
            _pick("d", "1", "HOME"), _pick("e", "1", "HOME"),
        ]),
    )
    rows = build_consensus(signal, frozenset({"on"})).rows
    assert [r.event_id for r in rows] == ["on", "off"]
    assert rows[0].tipster_count == 2 and rows[1].tipster_count == 3


def test_coupon_fixture_picks_are_listed_verbatim_including_combos():
    """The claim text is the only place a combo's legs survive, so it is
    printed rather than parsed."""
    signal = _signal(
        _event("on", "Anderlecht", "KV Kortrijk", [
            _pick("Waldemar Laszuk", "1 + OVER 1,5 gola", "OVER", odds=1.7),
        ], quality="FUZZY")
    )
    result = build_consensus(signal, frozenset({"on"}))
    assert len(result.coupon_fixtures) == 1
    listed = result.coupon_fixtures[0].picks
    assert listed == ["Waldemar Laszuk (ZawodTyper) @ 1.7: 1 + OVER 1,5 gola"]


def test_row_carries_no_probability_and_no_threshold():
    """Guards the boundary in the type system: these are opinions counted, not
    a model. A p_low or a min_acceptable_odds here would read as a bet."""
    fields = set(TipsterConsensusRow.model_fields)
    assert not fields & {
        "p_low", "p_central", "fair_odds", "min_acceptable_odds", "tier",
        "hit_rate", "sample_size", "superbet_price", "edge",
    }


def test_no_signal_is_an_empty_appendix_not_an_error():
    result = build_consensus(None)
    assert result.rows == []
    assert result.coupon_fixtures == []
    assert result.picks_ingested == 0


def test_totals_are_carried_through_for_the_operator_to_read():
    signal = _signal(
        _event("e1", "A", "B", [_pick("one", "1", "HOME")]),
        ingested=55, matched=39, countable=2,
    )
    result = build_consensus(signal)
    assert (result.picks_ingested, result.picks_matched, result.countable_claims) == (
        55, 39, 2
    )
    assert result.events_covered == 1
