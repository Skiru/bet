"""The coupon, once it knows what the operator's own book is offering.

The property under test throughout is that Superbet changes the *order* and the
*labels* of the file and never its arithmetic. ``p_low``, ``fair_odds`` and
``min_acceptable_odds`` are computed from the sample and nothing else; a price
that agrees with them does not make them stronger, and a price that disagrees
does not make them weaker. What a price does is answer a question the sample
cannot: whether the bet exists.
"""
from __future__ import annotations

import pytest

from bet.simple_stats import coupons as coupons_module
from bet.simple_stats.contracts import (
    EventListV1,
    EventRecord,
    StatsSheetRow,
    StatsSheetV1,
    SuperbetEventOffer,
    SuperbetLine,
    SuperbetOfferV1,
)
from bet.simple_stats.coupons import build_coupons


@pytest.fixture(autouse=True)
def _clear_competition_tier_cache():
    coupons_module.reset_competition_tier_cache()
    yield
    coupons_module.reset_competition_tier_cache()


def _row(**overrides) -> StatsSheetRow:
    kwargs = dict(
        event_id="evt-1", sport="football", market="corners_total", line=9.5,
        direction="UNDER", hits=9, sample_size=12, hit_rate=0.75, p_low=0.60,
        mean=9.1, median=9.0, sources=["bzzoiro", "espn-football"],
        cross_provider_agreement="AGREE", confidence="HIGH", data_quality="READY",
    )
    kwargs.update(overrides)
    return StatsSheetRow(**kwargs)


def _sheet(*rows) -> StatsSheetV1:
    return StatsSheetV1(
        run_id="RID-1", date="2026-08-29",
        generated_at="2026-08-29T00:00:00+00:00", rows=list(rows),
    )


def _event(event_id="evt-1", home="Valencia", away="Real Betis") -> EventRecord:
    return EventRecord(
        event_id=event_id, sport="football", competition="La Liga",
        home_team=home, away_team=away, start_time="2026-08-29T19:00:00+00:00",
        identity_confidence="CONFIRMED", status="ACTIVE",
    )


def _events(*records) -> EventListV1:
    return EventListV1(
        run_id="RID-1", generated_at="2026-08-29T00:00:00+00:00",
        date="2026-08-29", sports=["football"], events=list(records),
    )


def _line(**overrides) -> SuperbetLine:
    kwargs = dict(
        market="corners_total", line=9.5, direction="UNDER", price=2.20,
        source_market_name="Liczba rzutów rożnych", source_outcome_name="poniżej 9.5",
    )
    kwargs.update(overrides)
    return SuperbetLine(**kwargs)


def _offer(*lines, event_id="evt-1") -> SuperbetOfferV1:
    return SuperbetOfferV1(
        run_id="RID-1", date="2026-08-29", generated_at="2026-08-29T18:00:00+00:00",
        events=[
            SuperbetEventOffer(
                superbet_event_id="900", superbet_match_name="Valencia·Real Betis",
                sport="football", kickoff="2026-08-29T19:00:00Z", event_id=event_id,
                match_quality="EXACT", lines=list(lines),
            )
        ],
    )


# --- the arithmetic must not move -----------------------------------------


def test_superbet_never_touches_p_low_or_the_minimum_price():
    """The threshold is the sample's, and a bookmaker has no vote in it.

    If a price could move ``min_acceptable_odds``, then a book that shortened a
    line would make our own bar easier to clear -- which is precisely backwards.
    """
    sheet, events = _sheet(_row()), _events(_event())
    without = build_coupons(sheet, events)
    with_generous = build_coupons(sheet, events, superbet_offer=_offer(_line(price=99.0)))
    with_stingy = build_coupons(sheet, events, superbet_offer=_offer(_line(price=1.01)))
    for other in (with_generous, with_stingy):
        assert other.singles[0].p_low == without.singles[0].p_low
        assert other.singles[0].fair_odds == without.singles[0].fair_odds
        assert other.singles[0].min_acceptable_odds == without.singles[0].min_acceptable_odds


def test_absent_offer_reproduces_the_pre_superbet_file():
    """Optional means optional: no artifact, no column, no behaviour change."""
    coupons = build_coupons(_sheet(_row()), _events(_event()))
    single = coupons.singles[0]
    assert single.superbet_availability is None
    assert single.superbet_verdict is None
    assert single.superbet_price is None
    assert not any("Superbet:" in note for note in coupons.notes)


# --- the verdicts ----------------------------------------------------------


def test_value_when_the_book_pays_the_minimum():
    coupons = build_coupons(
        _sheet(_row()), _events(_event()), superbet_offer=_offer(_line(price=2.20))
    )
    single = coupons.singles[0]
    assert single.superbet_verdict == "VALUE"
    assert single.superbet_price == 2.20
    assert single.superbet_surplus == pytest.approx(2.20 - single.min_acceptable_odds, abs=1e-4)


def test_priced_below_threshold_stays_in_the_file_and_says_so():
    """A row the book prices too short is not dropped.

    "Superbet has this at 1.36 and you need 1.76" is actionable; a row silently
    missing from the file is not, and the operator cannot tell it from a row
    that never had the evidence.
    """
    coupons = build_coupons(
        _sheet(_row()), _events(_event()), superbet_offer=_offer(_line(price=1.36))
    )
    single = coupons.singles[0]
    assert single.superbet_verdict == "PRICED_BELOW_THRESHOLD"
    assert single.superbet_price == 1.36


def test_line_not_offered_carries_the_nearest_rung():
    coupons = build_coupons(
        _sheet(_row(market="shots_on_target_total", line=4.5, direction="OVER")),
        _events(_event()),
        superbet_offer=_offer(
            _line(market="shots_on_target_total", line=7.5, direction="OVER", price=1.53),
            _line(market="shots_on_target_total", line=8.5, direction="OVER", price=1.95),
        ),
    )
    single = coupons.singles[0]
    assert single.superbet_availability == "LINE_NOT_OFFERED"
    assert single.superbet_verdict == "LINE_NOT_OFFERED"
    assert single.superbet_price is None
    assert single.superbet_nearest_line == 7.5
    assert single.superbet_nearest_price == 1.53


def test_market_not_offered_and_event_not_matched_are_different_answers():
    no_market = build_coupons(
        _sheet(_row(market="fouls_total", line=20.5)),
        _events(_event()),
        superbet_offer=_offer(_line()),
    )
    assert no_market.singles[0].superbet_availability == "MARKET_NOT_OFFERED"

    no_event = build_coupons(
        _sheet(_row(event_id="evt-2")),
        _events(_event("evt-2", "Sutton", "Wealdstone")),
        superbet_offer=_offer(_line()),
    )
    assert no_event.singles[0].superbet_availability == "EVENT_NOT_MATCHED"


def test_suspended_outcome_is_not_value_at_any_price():
    coupons = build_coupons(
        _sheet(_row()), _events(_event()),
        superbet_offer=_offer(_line(price=99.0, status="block")),
    )
    single = coupons.singles[0]
    assert single.superbet_availability == "SUSPENDED"
    assert single.superbet_verdict == "SUSPENDED"
    assert single.superbet_surplus is None


# --- ranking ---------------------------------------------------------------


def test_a_takeable_bet_outranks_a_better_evidenced_untakeable_one():
    """The whole point of the column, expressed as an ordering.

    The 0.85 row has better evidence and is not on the book at our line. The
    0.60 row is on the book above its minimum. Only one of them is a bet, and
    it has to be first, or an operator working down the file spends his
    attention on rows he cannot place.
    """
    coupons = build_coupons(
        _sheet(
            _row(market="goals_total", line=4.5, direction="UNDER", p_low=0.85,
                 hits=22, sample_size=22, hit_rate=1.0),
            _row(market="corners_total", line=9.5, direction="UNDER", p_low=0.60),
        ),
        _events(_event()),
        superbet_offer=_offer(_line(market="corners_total", line=9.5,
                                    direction="UNDER", price=2.20)),
    )
    assert coupons.singles[0].market == "corners_total"
    assert coupons.singles[0].superbet_verdict == "VALUE"
    assert coupons.singles[1].market == "goals_total"


def test_bigger_surplus_ranks_first_among_value_rows():
    coupons = build_coupons(
        _sheet(
            _row(market="corners_total", line=9.5, direction="UNDER"),
            _row(market="cards_total", line=4.5, direction="UNDER"),
        ),
        _events(_event()),
        superbet_offer=_offer(
            _line(market="corners_total", line=9.5, direction="UNDER", price=2.00),
            _line(market="cards_total", line=4.5, direction="UNDER", price=5.00),
        ),
    )
    assert [s.market for s in coupons.singles] == ["cards_total", "corners_total"]


# --- the notes -------------------------------------------------------------


def test_the_header_counts_what_is_takeable():
    coupons = build_coupons(
        _sheet(
            _row(market="corners_total", line=9.5, direction="UNDER"),
            _row(market="cards_total", line=4.5, direction="UNDER"),
        ),
        _events(_event()),
        superbet_offer=_offer(_line(market="corners_total", line=9.5,
                                    direction="UNDER", price=2.20)),
    )
    note = next(n for n in coupons.notes if n.startswith("Superbet:"))
    assert "1 z 2 singli" in note
    # Every single lands in exactly one bucket and the note prints all of them:
    # a header accounting for 3 of 15 rows reads as a broken count, not a fact.
    assert "1 bez tego rynku u bukmachera" in note


def test_a_day_with_no_takeable_row_says_so_in_the_header():
    coupons = build_coupons(
        _sheet(_row()), _events(_event()), superbet_offer=_offer(_line(price=1.10))
    )
    assert any("Żaden single nie osiąga minimalnego kursu" in n for n in coupons.notes)


def test_the_line_mismatch_is_named_in_the_header():
    coupons = build_coupons(
        _sheet(_row(market="shots_on_target_total", line=4.5, direction="OVER")),
        _events(_event()),
        superbet_offer=_offer(
            _line(market="shots_on_target_total", line=7.5, direction="OVER", price=1.53)
        ),
    )
    assert any("shots_on_target_total 4.5→7.5" in n for n in coupons.notes)


# --- bet builder legs ------------------------------------------------------


def test_slip_legs_carry_the_same_answer_as_the_singles():
    coupons = build_coupons(
        _sheet(
            _row(market="corners_total", line=9.5, direction="UNDER"),
            _row(market="cards_total", line=4.5, direction="UNDER"),
        ),
        _events(_event()),
        superbet_offer=_offer(
            _line(market="corners_total", line=9.5, direction="UNDER", price=2.20),
            _line(market="cards_total", line=4.5, direction="UNDER", price=1.95),
        ),
    )
    assert coupons.slips, "two qualifying rows on one fixture should make a slip"
    legs = {leg.market: leg for leg in coupons.slips[0].draft.legs}
    assert legs["corners_total"].superbet_availability == "OFFERED"
    assert legs["corners_total"].superbet_price == 2.20
    assert legs["cards_total"].superbet_price == 1.95


def test_a_leg_the_book_does_not_carry_is_not_a_leg():
    """A slip is placed as one unit, so an unavailable leg does not weaken it --
    it makes the whole slip impossible. Five of the eight slips shipped on
    2026-09-01 contained a line Superbet does not list and were still printed
    as coupons to go and place."""
    coupons = build_coupons(
        _sheet(
            _row(market="corners_total", line=9.5, direction="UNDER"),
            _row(market="cards_total", line=4.5, direction="UNDER"),
        ),
        _events(_event()),
        superbet_offer=_offer(_line(market="corners_total", line=9.5,
                                    direction="UNDER", price=2.20)),
    )
    assert coupons.slips == [], "the second leg is not on the book, so there is no slip"

    # The single is unaffected: it is placed alone, and "Superbet does not list
    # this market" is exactly the sentence the singles section exists to print.
    assert {s.market for s in coupons.singles} == {"corners_total", "cards_total"}
    assert next(
        s for s in coupons.singles if s.market == "cards_total"
    ).superbet_availability == "MARKET_NOT_OFFERED"


def test_slip_legs_have_no_superbet_fields_without_an_offer():
    coupons = build_coupons(
        _sheet(
            _row(market="corners_total", line=9.5, direction="UNDER"),
            _row(market="cards_total", line=4.5, direction="UNDER"),
        ),
        _events(_event()),
    )
    for leg in coupons.slips[0].draft.legs:
        assert leg.superbet_availability is None


# --- the opt-in filter -----------------------------------------------------


def test_require_superbet_value_keeps_only_what_the_book_will_pay_for():
    coupons = build_coupons(
        _sheet(
            _row(market="corners_total", line=9.5, direction="UNDER"),
            _row(market="cards_total", line=4.5, direction="UNDER"),
        ),
        _events(_event()),
        superbet_offer=_offer(_line(market="corners_total", line=9.5,
                                    direction="UNDER", price=2.20)),
        require_superbet_value=True,
    )
    assert [s.market for s in coupons.singles] == ["corners_total"]
    assert coupons.excluded["superbet_not_value"] == 1


def test_require_superbet_value_without_an_offer_empties_the_file():
    """No offer means nothing can be proven takeable, so nothing is.

    Fails closed rather than open: the alternative -- treating "unknown" as
    "value" -- would put every row through a filter whose name promises the
    opposite.
    """
    coupons = build_coupons(
        _sheet(_row()), _events(_event()), require_superbet_value=True
    )
    assert coupons.singles == []


# --- combined price, still impossible --------------------------------------


def test_superbet_does_not_introduce_a_combined_price():
    coupons = build_coupons(
        _sheet(
            _row(market="corners_total", line=9.5, direction="UNDER"),
            _row(market="cards_total", line=4.5, direction="UNDER"),
        ),
        _events(_event()),
        superbet_offer=_offer(
            _line(market="corners_total", line=9.5, direction="UNDER", price=2.20),
            _line(market="cards_total", line=4.5, direction="UNDER", price=1.90),
        ),
    )
    assert coupons.combined_price is None
    for slip in coupons.slips:
        assert slip.draft.combined_price is None


def test_the_header_accounts_for_every_single():
    """The first version of this note counted only four of seven outcomes and
    left twelve of fifteen rows unexplained on a live day."""
    coupons = build_coupons(
        _sheet(
            _row(market="corners_total", line=9.5, direction="UNDER"),
            _row(market="cards_total", line=4.5, direction="UNDER"),
            _row(market="goals_total", line=2.5, direction="OVER"),
        ),
        _events(_event()),
        superbet_offer=_offer(
            _line(market="corners_total", line=9.5, direction="UNDER", price=2.20),
            _line(market="goals_total", line=2.5, direction="OVER", price=1.01),
        ),
    )
    note = next(n for n in coupons.notes if n.startswith("Superbet:"))
    counts = [int(part) for part in note.replace(",", " ").split() if part.isdigit()]
    # "1 z 3 singli" plus one count per non-empty bucket; the buckets must sum
    # to the singles that are not VALUE.
    assert counts[0] + sum(counts[2:]) == len(coupons.singles)


def test_a_kicked_off_fixture_is_labelled_as_the_clock_not_a_missing_market():
    # No lines at all: the book has the fixture and prices nothing on it.
    offer = _offer()
    coupons = build_coupons(_sheet(_row()), _events(_event()), superbet_offer=offer)
    assert coupons.singles[0].superbet_availability == "OFFER_EMPTY"


def test_a_prop_whose_player_the_book_does_not_price_is_labelled_as_ours():
    """The coupon reads props now. When Superbet has the fixture but not this
    player, the label is PLAYER_NOT_MATCHED -- our join, not the book's gap."""
    coupons = build_coupons(
        _sheet(_row(market="player_total_shots", line=1.5, direction="UNDER",
                    player_name="Alef Manga", player_id="p1",
                    lineup_status="predicted")),
        _events(_event()),
        superbet_offer=_offer(_line()),
    )
    assert coupons.singles[0].superbet_availability == "PLAYER_NOT_MATCHED"


def test_a_prop_the_book_prices_reaches_the_coupon_with_that_price():
    """The whole point of Faza 2: before this, no player prop could carry a
    price on the coupon at any line, because the lookup refused to try."""
    prop_line = SuperbetLine(
        market="player_total_shots", line=1.5, direction="UNDER",
        player_name="Manga, Alef", price=2.10,
        source_market_name="Zawodnik - liczba strzałów",
        source_outcome_name="Manga, Alef - poniżej 1.5",
    )
    coupons = build_coupons(
        _sheet(_row(market="player_total_shots", line=1.5, direction="UNDER",
                    player_name="Alef Manga", player_id="p1",
                    lineup_status="confirmed")),
        _events(_event()),
        superbet_offer=_offer(prop_line),
    )
    assert coupons.singles[0].superbet_availability == "OFFERED"
    assert coupons.singles[0].superbet_price == 2.10
