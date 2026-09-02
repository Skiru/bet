"""Disagreeing with the book is not the same thing as being right.

Before 2026-09-01 the coupon's top section was ranked by ``superbet_surplus``
descending, which reads as "best value first" and is arithmetically "where we
disagree with the operator's own book most, first". Those are the same list.

The arithmetic is exact: the gate admits a row when ``price >= 1.10 / p_low``,
and with the 8-9% overround these markets carry that requires ``p_low`` to sit
roughly 19% above the book's own probability. On 2026-09-01 the ten admitted
rows ran from +0.04 to +0.19 against devigged Superbet, and the widest gap in
the whole file -- 2.27 against a minimum of 1.38 -- was the ATP best-of-five
tie priced off best-of-three data. It was ranked first *because* it was wrong.

So the gate here is a demotion and never a deletion. The file cannot tell an
edge from a broken sample and must not pretend to; what it can do is stop
presenting the second as the first, at rank one.

**What the gate measures changed after 2026-09-01 settled.** It compared
``p_low`` to the devigged price, and that comparison is unusable: ``p_low`` is a
lower bound with a 5-10% tier margin stacked on it downstream, so the same
inequality that admits a row *forces* the gap above +0.08 for a LEAN and +0.13
for a strong one, whatever the sample holds. Six of that day's seven admitted
singles sat between +0.10 and +0.14 -- under the 0.15 threshold meant to catch
them -- and six of the seven lost. The gate now reads ``p_central``, the same
probability with no bound and no margin in it, whose run-wide median against
devigged Superbet is -0.000. See ``MAX_MARKET_DISAGREEMENT``.
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
from bet.simple_stats.coupons import MAX_MARKET_DISAGREEMENT, build_coupons


@pytest.fixture(autouse=True)
def _clear_competition_tier_cache():
    coupons_module.reset_competition_tier_cache()
    yield
    coupons_module.reset_competition_tier_cache()


def _row(**overrides) -> StatsSheetRow:
    kwargs = dict(
        event_id="evt-1", sport="football", market="corners_total", line=9.5,
        direction="UNDER", hits=9, sample_size=12, hit_rate=0.75, p_low=0.60,
        # The gate reads p_central, so the fixture has to carry one. 0.80
        # beside a floor of 0.60 is the ordinary relationship between the two:
        # the sample's own estimate, and what is left of it after Wilson and
        # the count model have both charged it for being twelve observations.
        p_central=0.80,
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


def _pair(market: str, line: float, *, under: float, over: float, event_id="evt-1"):
    """Both sides of one line. A devig needs two prices; one is only an
    overround-inflated guess, and the guess errs in the direction that lets a
    bad row through."""
    common = dict(market=market, line=line, source_market_name=market,
                  source_outcome_name="x")
    return [
        SuperbetLine(direction="UNDER", price=under, **common),
        SuperbetLine(direction="OVER", price=over, **common),
    ]


def _offer(*line_groups, event_id="evt-1") -> SuperbetOfferV1:
    lines = [line for group in line_groups for line in group]
    return SuperbetOfferV1(
        run_id="RID-1", date="2026-08-29", generated_at="2026-08-29T18:00:00+00:00",
        events=[
            SuperbetEventOffer(
                superbet_event_id="900", superbet_match_name="Valencia·Real Betis",
                sport="football", kickoff="2026-08-29T19:00:00Z", event_id=event_id,
                match_quality="EXACT", lines=lines,
            )
        ],
    )


# --- the measurement --------------------------------------------------------


def test_the_disagreement_is_measured_against_a_devigged_price():
    """2.50 / 1.55 is an overround of 1.045, so the book's real probability for
    the UNDER is 0.383 and not the 0.400 that ``1/price`` reports."""
    coupons = build_coupons(
        _sheet(_row(p_low=0.60)),
        _events(_event()),
        superbet_offer=_offer(_pair("corners_total", 9.5, under=2.50, over=1.55)),
    )
    single = coupons.singles[0]
    assert single.market_disagreement == pytest.approx(0.80 - 0.3828, abs=1e-3)
    assert single.needs_review is True


def test_a_one_sided_market_cannot_be_devigged_and_does_not_fire_the_gate():
    """We cannot say the book disagrees with us if we cannot read what it
    thinks. A single price carries the whole margin and is not an opinion."""
    coupons = build_coupons(
        _sheet(_row(p_low=0.60)),
        _events(_event()),
        superbet_offer=_offer([
            SuperbetLine(market="corners_total", line=9.5, direction="UNDER",
                         price=2.50, source_market_name="x", source_outcome_name="y")
        ]),
    )
    single = coupons.singles[0]
    assert single.market_disagreement is None
    assert single.needs_review is False


def test_without_an_offer_nothing_is_flagged():
    coupons = build_coupons(_sheet(_row(p_low=0.60)), _events(_event()))
    assert coupons.singles[0].market_disagreement is None
    assert coupons.singles[0].needs_review is False


def test_sitting_below_the_market_is_never_flagged():
    """Being under the book's number is the normal, healthy case and the gate
    is deliberately one-sided. 1.40/3.10 devigs to 0.689 for the UNDER, above
    this row's own 0.62 estimate."""
    coupons = build_coupons(
        _sheet(_row(p_low=0.55, p_central=0.62)),
        _events(_event()),
        superbet_offer=_offer(_pair("corners_total", 9.5, under=1.40, over=3.10)),
    )
    single = coupons.singles[0]
    assert single.market_disagreement < 0
    assert single.needs_review is False


# --- what the gate does to the file ----------------------------------------


def test_a_row_the_market_contradicts_loses_the_top_of_the_file():
    """Both rows clear their minimum price, so before the gate the *wider*
    disagreement led the file on surplus alone."""
    coupons = build_coupons(
        _sheet(
            _row(market="corners_total", line=9.5, p_low=0.60, p_central=0.80),
            _row(market="cards_total", line=4.5, p_low=0.60, p_central=0.70),
        ),
        _events(_event()),
        superbet_offer=_offer(
            # devigged 0.383 -- 0.417 under our own estimate, past the threshold
            _pair("corners_total", 9.5, under=2.50, over=1.55),
            # devigged 0.548 -- 0.152 under it, inside the threshold, and 1.90
            # still clears the 1.833 this row's floor demands. Both rows are
            # bettable on price; only one of them is a bet the book has not
            # already priced against us.
            _pair("cards_total", 4.5, under=1.90, over=2.30),
        ),
    )
    assert [s.market for s in coupons.singles] == ["cards_total", "corners_total"]
    assert coupons.singles[0].needs_review is False
    assert coupons.singles[1].needs_review is True


def test_a_flagged_row_is_demoted_and_never_dropped():
    """Deleting it would hide the one class of row most worth a second look."""
    coupons = build_coupons(
        _sheet(_row(p_low=0.60)),
        _events(_event()),
        superbet_offer=_offer(_pair("corners_total", 9.5, under=2.50, over=1.55)),
    )
    assert len(coupons.singles) == 1
    assert coupons.singles[0].superbet_verdict == "VALUE"
    assert coupons.singles[0].needs_review is True


def test_a_flagged_row_says_so_in_its_own_caveats_and_in_the_header():
    coupons = build_coupons(
        _sheet(_row(p_low=0.60)),
        _events(_event()),
        superbet_offer=_offer(_pair("corners_total", 9.5, under=2.50, over=1.55)),
    )
    assert any("rynek wycenia to znacznie niżej" in c
               for c in coupons.singles[0].caveats)
    assert any("sprawdź próbkę" in n.lower() for n in coupons.notes)


def test_the_threshold_is_the_published_constant():
    """Just inside and just outside, so the constant is what decides and not a
    number written twice."""
    # devig of 1.90/1.90 is exactly 0.50, so p_central is the only variable.
    inside = build_coupons(
        _sheet(_row(p_central=0.50 + MAX_MARKET_DISAGREEMENT - 0.01)),
        _events(_event()),
        superbet_offer=_offer(_pair("corners_total", 9.5, under=1.90, over=1.90)),
    )
    outside = build_coupons(
        _sheet(_row(p_central=0.50 + MAX_MARKET_DISAGREEMENT + 0.01)),
        _events(_event()),
        superbet_offer=_offer(_pair("corners_total", 9.5, under=1.90, over=1.90)),
    )
    assert inside.singles[0].needs_review is False
    assert outside.singles[0].needs_review is True
