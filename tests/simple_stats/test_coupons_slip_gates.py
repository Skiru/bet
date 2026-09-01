"""Every gate a single passes, a Bet Builder leg passes too.

This file exists because that sentence was false for a year and nothing said
so. On 2026-09-01 ``build_coupons`` applied the analyst's vetoes, the
``min_p_low`` floor, the Superbet price check, the duplicate-fixture guard and
the trivial-UNDER demotion to the singles list, and applied none of them to the
slips, which were drafted straight off the raw stats sheet. The day's file
shipped eight slips: twenty-eight of their thirty legs were priced below their
own minimum or not on the book at all, and the two that cleared their price
were both rows the analyst had explicitly vetoed.

The veto suite in ``test_coupons.py`` could not have caught it. Every one of
its cases used a single-row sheet, so ``len(draft.legs) < 2`` suppressed the
slip no matter what the veto did -- the assertion passed for a reason that had
nothing to do with the behaviour it claimed to protect. **Every sheet in this
file therefore carries at least two qualifying rows on one fixture**, so a slip
is always the expected outcome and its absence is always a real signal.
"""
from __future__ import annotations

import pytest

from bet.simple_stats import coupons as coupons_module
from bet.simple_stats.bet_builder_draft import AnalystVeto, VetoIndex, draft_legs
from bet.simple_stats.contracts import (
    EventListV1,
    EventRecord,
    StatsSheetRow,
    StatsSheetV1,
    SuperbetEventOffer,
    SuperbetLine,
    SuperbetOfferV1,
)
from bet.simple_stats.coupons import MIN_SINGLE_P_LOW, build_coupons


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


def _two_row_sheet(**overrides) -> StatsSheetV1:
    """Two qualifying rows on one fixture: the minimum that can make a slip."""
    return StatsSheetV1(
        run_id="RID-1", date="2026-08-29",
        generated_at="2026-08-29T00:00:00+00:00",
        rows=[
            _row(market="corners_total", line=9.5, direction="UNDER", **overrides),
            _row(market="cards_total", line=4.5, direction="UNDER", **overrides),
        ],
    )


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


def _both_sides(market: str, line: float, direction: str, price: float, other: float):
    """A line and its opposite, which is what a devig needs."""
    opposite = "UNDER" if direction == "OVER" else "OVER"
    return (
        _line(market=market, line=line, direction=direction, price=price),
        _line(market=market, line=line, direction=opposite, price=other),
    )


# --- the control: without a gate firing, these sheets do make a slip --------


def test_two_qualifying_rows_on_one_fixture_make_a_slip():
    """The premise every other test in this file negates.

    Asserted first and on its own, because a test that expects ``slips == []``
    proves nothing unless a slip was possible to begin with -- which is exactly
    how the original veto suite fooled itself.
    """
    coupons = build_coupons(_two_row_sheet(), _events(_event()))
    assert len(coupons.slips) == 1
    assert len(coupons.slips[0].draft.legs) == 2


# --- the veto reaches the legs ---------------------------------------------


def test_a_vetoed_row_never_becomes_a_bet_builder_leg():
    """The 2026-09-01 defect, in the smallest form that reproduces it."""
    coupons = build_coupons(
        _two_row_sheet(),
        _events(_event()),
        vetoes=[
            AnalystVeto(
                event_id="evt-1", market="corners_total", line=9.5,
                direction="UNDER", action="VETO", reason="best-of-3 sample",
            )
        ],
    )
    every_leg = [leg for slip in coupons.slips for leg in slip.draft.legs]
    assert "corners_total" not in {leg.market for leg in every_leg}
    # And with only one leg left there is no slip at all, which is the honest
    # outcome: half a slip is not a coupon.
    assert coupons.slips == []


def test_a_slip_survives_a_veto_that_leaves_two_legs_standing():
    """A veto removes a leg; it does not silently delete the whole draft."""
    coupons = build_coupons(
        _sheet(
            _row(market="corners_total", line=9.5, direction="UNDER"),
            _row(market="cards_total", line=4.5, direction="UNDER"),
            _row(market="fouls_total", line=20.5, direction="OVER"),
        ),
        _events(_event()),
        vetoes=[
            AnalystVeto(
                event_id="evt-1", market="corners_total", line=9.5,
                direction="UNDER", action="VETO", reason="zeros mean unknown",
            )
        ],
    )
    assert len(coupons.slips) == 1
    assert {leg.market for leg in coupons.slips[0].draft.legs} == {
        "cards_total", "fouls_total"
    }


def test_a_downgrade_raises_the_legs_required_price_and_can_remove_it():
    """DOWNGRADE was invisible to the slips path, so a leg the analyst had
    stepped down to LEAN kept the CALL margin of 1.05 and demanded less than it
    should have -- and one stepped to WEAK stayed fully eligible."""
    sheet = _two_row_sheet()
    plain = build_coupons(sheet, _events(_event()))
    before = next(
        leg for leg in plain.slips[0].draft.legs if leg.market == "corners_total"
    )
    assert before.tier == "CALL"

    stepped = build_coupons(
        sheet, _events(_event()),
        vetoes=[
            AnalystVeto(
                event_id="evt-1", market="corners_total", line=9.5,
                direction="UNDER", action="DOWNGRADE", reason="thin referee sample",
            )
        ],
    )
    after = next(
        leg for leg in stepped.slips[0].draft.legs if leg.market == "corners_total"
    )
    assert after.tier == "LEAN"
    assert after.p_low == before.p_low, "a downgrade must never touch the sample"
    assert after.min_acceptable_odds > before.min_acceptable_odds


def test_a_downgrade_that_reaches_weak_removes_the_leg():
    coupons = build_coupons(
        _two_row_sheet(cross_provider_agreement="SINGLE_SOURCE", sample_size=6),
        _events(_event()),
        vetoes=[
            AnalystVeto(
                event_id="evt-1", market="corners_total", line=9.5,
                direction="UNDER", action="DOWNGRADE", reason="four of ten are zeros",
            )
        ],
    )
    assert coupons.slips == []


# --- the veto may scope a whole market -------------------------------------


def test_a_veto_with_no_line_strikes_every_line_of_that_market():
    """The fault the analyst finds is usually market-wide, not per line.

    On 2026-09-01 ``cards_total`` 4.5 and 3.5 were vetoed on Sheffield United -
    Bolton for seven zero-valued observations in matches with 21 and 24 fouls.
    5.5 was not written down, and 5.5 shipped as a Bet Builder leg graded CALL
    off those same seven zeros.
    """
    coupons = build_coupons(
        _sheet(
            _row(market="cards_total", line=3.5, direction="UNDER"),
            _row(market="cards_total", line=4.5, direction="UNDER"),
            _row(market="cards_total", line=5.5, direction="UNDER"),
            _row(market="corners_total", line=9.5, direction="UNDER"),
            _row(market="fouls_total", line=20.5, direction="OVER"),
        ),
        _events(_event()),
        vetoes=[
            AnalystVeto(
                event_id="evt-1", market="cards_total", action="VETO",
                reason="seven zeros in matches with 21+ fouls",
            )
        ],
    )
    assert "cards_total" not in {s.market for s in coupons.singles}
    every_leg = [leg for slip in coupons.slips for leg in slip.draft.legs]
    assert "cards_total" not in {leg.market for leg in every_leg}
    assert {leg.market for leg in every_leg} == {"corners_total", "fouls_total"}


def test_a_market_wide_veto_leaves_other_markets_alone():
    coupons = build_coupons(
        _two_row_sheet(),
        _events(_event()),
        vetoes=[
            AnalystVeto(
                event_id="evt-1", market="cards_total", action="VETO",
                reason="market-wide",
            )
        ],
    )
    assert {s.market for s in coupons.singles} == {"corners_total"}


def test_a_veto_may_scope_one_direction_of_a_market():
    coupons = build_coupons(
        _sheet(
            _row(market="corners_total", line=9.5, direction="UNDER"),
            _row(market="corners_total", line=9.5, direction="OVER", hits=3),
            _row(market="cards_total", line=4.5, direction="UNDER"),
        ),
        _events(_event()),
        vetoes=[
            AnalystVeto(
                event_id="evt-1", market="corners_total", direction="UNDER",
                action="VETO", reason="every UNDER on this event is zero-inflated",
            )
        ],
    )
    kept = {(s.market, s.direction) for s in coupons.singles}
    assert ("corners_total", "UNDER") not in kept
    assert ("corners_total", "OVER") in kept


def test_the_most_specific_veto_wins():
    """A market-wide DOWNGRADE plus a per-line VETO must not shadow each other."""
    index = VetoIndex([
        AnalystVeto(event_id="e", market="cards_total", action="DOWNGRADE",
                    reason="market-wide doubt"),
        AnalystVeto(event_id="e", market="cards_total", line=4.5, direction="UNDER",
                    action="VETO", reason="this line specifically"),
    ])
    exact = _row(event_id="e", market="cards_total", line=4.5, direction="UNDER")
    other = _row(event_id="e", market="cards_total", line=5.5, direction="UNDER")
    assert index.for_row(exact).action == "VETO"
    assert index.for_row(other).action == "DOWNGRADE"


def test_the_veto_header_note_says_how_wide_the_veto_was():
    coupons = build_coupons(
        _two_row_sheet(),
        _events(_event()),
        vetoes=[
            AnalystVeto(event_id="evt-1", market="corners_total", action="VETO",
                        reason="sample is not this fixture"),
        ],
    )
    note = next(n for n in coupons.notes if n.startswith("WETO"))
    assert "wszystkie linie" in note
    assert "OVER+UNDER" in note


# --- min_p_low reaches the legs --------------------------------------------


def test_a_leg_below_min_p_low_is_excluded_like_a_single():
    """31,083 rows were excluded from the singles on this threshold on
    2026-09-01 and none from the slips, so a leg could demand 5.00 while every
    single at the same p_low had been thrown out as unplaceable."""
    weak = _two_row_sheet(p_low=0.21, hits=3, sample_size=12, hit_rate=0.25)
    coupons = build_coupons(weak, _events(_event()))
    assert coupons.singles == []
    assert coupons.slips == [], "no single at this p_low, so no leg at it either"


def test_min_p_low_is_the_same_number_for_both_sections():
    just_under = _two_row_sheet(p_low=MIN_SINGLE_P_LOW - 0.01)
    just_over = _two_row_sheet(p_low=MIN_SINGLE_P_LOW + 0.01)
    assert build_coupons(just_under, _events(_event())).slips == []
    assert build_coupons(just_over, _events(_event())).slips != []


# --- the operator's own book reaches the legs -------------------------------


def test_require_superbet_value_removes_legs_priced_below_their_minimum():
    coupons = build_coupons(
        _two_row_sheet(),
        _events(_event()),
        superbet_offer=_offer(
            _line(market="corners_total", line=9.5, direction="UNDER", price=2.20),
            _line(market="cards_total", line=4.5, direction="UNDER", price=1.01),
        ),
        require_superbet_value=True,
    )
    assert coupons.slips == []


def test_a_leg_is_kept_when_both_prices_clear_their_minimum():
    coupons = build_coupons(
        _two_row_sheet(),
        _events(_event()),
        superbet_offer=_offer(
            _line(market="corners_total", line=9.5, direction="UNDER", price=2.20),
            _line(market="cards_total", line=4.5, direction="UNDER", price=2.30),
        ),
        require_superbet_value=True,
    )
    assert len(coupons.slips) == 1
    for leg in coupons.slips[0].draft.legs:
        assert leg.superbet_price >= leg.min_acceptable_odds


def test_without_an_offer_the_price_gate_cannot_fire():
    """No offer is not evidence a leg is unplaceable, and must not read as it."""
    coupons = build_coupons(_two_row_sheet(), _events(_event()))
    assert len(coupons.slips) == 1
    for leg in coupons.slips[0].draft.legs:
        assert leg.superbet_availability is None


# --- one fixture, one slip --------------------------------------------------


def test_two_event_ids_for_one_real_fixture_produce_one_slip():
    """The 2026-08-28 Nautico incident, on the side of the file it was never
    fixed for: the singles resolved duplicate fixtures, the slips loop still
    keyed on the raw event_id, so an operator working down the file would have
    staked one match twice believing he had diversified."""
    coupons = build_coupons(
        _sheet(
            _row(event_id="evt-1", market="corners_total", line=9.5, direction="UNDER"),
            _row(event_id="evt-1", market="cards_total", line=4.5, direction="UNDER"),
            _row(event_id="evt-2", market="corners_total", line=9.5, direction="UNDER"),
            _row(event_id="evt-2", market="cards_total", line=4.5, direction="UNDER"),
        ),
        _events(
            _event("evt-1", home="Valencia", away="Real Betis"),
            _event("evt-2", home="Valencia CF", away="Real Betis"),
        ),
    )
    assert len(coupons.slips) == 1
    assert coupons.excluded.get("duplicate_fixture_for_slip") == 1


def test_two_genuinely_different_fixtures_still_produce_two_slips():
    coupons = build_coupons(
        _sheet(
            _row(event_id="evt-1", market="corners_total", line=9.5, direction="UNDER"),
            _row(event_id="evt-1", market="cards_total", line=4.5, direction="UNDER"),
            _row(event_id="evt-2", market="corners_total", line=9.5, direction="UNDER"),
            _row(event_id="evt-2", market="cards_total", line=4.5, direction="UNDER"),
        ),
        _events(
            _event("evt-1", home="Valencia", away="Real Betis"),
            _event("evt-2", home="Sevilla", away="Girona"),
        ),
    )
    assert len(coupons.slips) == 2


# --- trivial UNDERs never lead a slip ---------------------------------------


def test_a_trivial_low_line_under_never_leads_a_slip():
    """``draft_legs`` sorted on -p_low alone, so the highest-p_low row led --
    and the highest-p_low row is always the most trivial one. Eight slips on
    2026-09-01 were led by "goals 1H UNDER 4.5" at a Superbet price of 1.001,
    under a header promising those had been pushed to the end."""
    slip = draft_legs(
        _sheet(
            _row(market="goals_1h_total", line=1.5, direction="UNDER", p_low=0.90),
            _row(market="corners_total", line=9.5, direction="UNDER", p_low=0.62),
        ),
        "evt-1",
    )
    assert [leg.market for leg in slip.legs] == ["corners_total", "goals_1h_total"]


def test_the_demotion_is_the_same_rule_the_singles_use():
    coupons = build_coupons(
        _sheet(
            _row(market="goals_1h_total", line=1.5, direction="UNDER", p_low=0.90),
            _row(market="corners_total", line=9.5, direction="UNDER", p_low=0.62),
        ),
        _events(_event()),
    )
    assert [s.market for s in coupons.singles] == [leg.market for leg in
                                                   coupons.slips[0].draft.legs]


# --- tennis legs are not independent ----------------------------------------


def test_two_length_dependent_tennis_legs_are_flagged_as_correlated():
    """Shipped as ``correlation_risk: LOW`` on 2026-09-01. A match that ends in
    three sets is a short match, so "under 34.5 games" and "under 3.5 sets" are
    close to the same bet twice."""
    slip = draft_legs(
        _sheet(
            _row(sport="tennis", market="total_games", line=34.5, direction="UNDER"),
            _row(sport="tennis", market="total_sets", line=3.5, direction="UNDER"),
        ),
        "evt-1",
    )
    assert slip.correlation_risk == "HIGH"
    assert "how long the match runs" in slip.correlation_note
