"""A match Superbet reports under way is neither priced nor bet, clocks or no clocks.

Nothing in the repo read Superbet's offer state. Every odd carries
`offerStateId` (1 pre-match, 2 live) and every event `metadata.status`
(NOT_STARTED / STARTED / FINISHED) and `offerStateStatus`, but the only
in-play guard was the kickoff clock. On the 2026-10-04 board three events were
STARTED with Superbet's own utcDate still ahead, and Hurkacz - Khachanov (both
clocks 05:00Z) carried 665 odds, every one in the live state. A live ladder
read as a price feeds OFFER, SHEET, SHADOW, CS2 and the closing capture; a
started match with an older pre-match price could still reach the PDF.

Payload shapes below are copied from the live Superbet answers of 2026-10-04
05:40Z (event 15267666 started, 15283669 not started).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa.contracts import FixtureOffer, PricedRung
from bet.sofa.coupon import build_coupon, superbet_started
from bet.sofa.offer import OfferFetcher
from bet.sofa.superbet import (
    event_started,
    is_live_odd,
    odds_items,
    superbet_kickoff,
)
from scripts.sofa.run_sheet import strip_in_play_prices
from tests.sofa.test_player_markets import dataclasses_replace_tennis
from tests.sofa.test_price_moved_since_sheet import (
    ODDS_A,
    ODDS_B,
    UNDER_A,
    UNDER_B,
    _coupon_fixture,
    _coupon_row,
    _day,
    _offer,
    _single_ids,
    _confidence,
)


def _odd(price: float, name: str, state: int | None) -> dict[str, Any]:
    odd: dict[str, Any] = {
        "marketName": "Liczba goli",
        "name": name,
        "specialBetValue": "2.5",
        "price": price,
        "status": "active",
    }
    if state is not None:
        odd["offerStateId"] = state
    return odd


STARTED = {
    "metadata": {
        "status": "STARTED", "periodStatus": "1S", "matchStatusLabel": "1S"
    },
    "offerStateStatus": {"1": "stop", "2": "active"},
    "utcDate": "2026-10-04T05:00:00Z",
    "odds": [_odd(1.30, "poniżej 2.5", 2), _odd(3.40, "powyżej 2.5", 2)],
}
NOT_STARTED = {
    "metadata": {
        "status": "NOT_STARTED", "periodStatus": "NR", "matchStatusLabel": "NS"
    },
    "offerStateStatus": {"1": "active"},
    "utcDate": "2026-10-04T08:30:00Z",
    "odds": [_odd(1.80, "poniżej 2.5", 1), _odd(2.00, "powyżej 2.5", 1)],
}


def test_odds_items_drops_live_odds_and_keeps_prematch_and_unlabelled() -> None:
    payload = {"odds": [_odd(1.5, "a", 1), _odd(1.6, "b", 2), _odd(1.7, "c", None)]}
    assert [o["price"] for o in odds_items(payload)] == [1.5, 1.7]
    assert is_live_odd({"offerStateId": 2}) and is_live_odd({"offerStateId": "2"})
    assert not is_live_odd({"offerStateId": 1}) and not is_live_odd({})


def test_event_started_reads_superbet_not_the_clock() -> None:
    assert event_started(STARTED)
    assert not event_started(NOT_STARTED)
    assert event_started({"metadata": {"status": "FINISHED"}})
    assert event_started({"offerStateStatus": {"2": "finished"}})
    # A delisted duplicate listing, not a start: Lock - Hemery 2026-10-04
    # 05:47Z had {"1": "finished"} on one listing and {"1": "active"} on the
    # other, four hours before the match.
    assert not event_started({"offerStateStatus": {"1": "finished"}})
    # Superbet suspends pre-match markets too: stopped is not started.
    assert not event_started(
        {"metadata": {"status": "NOT_STARTED"}, "offerStateStatus": {"1": "stop"}}
    )
    # 1,686 of 3,483 events carry no live metadata at all.
    assert not event_started({"offerStateStatus": {"1": "active"}})
    assert not event_started(None) and not event_started({})


class _Client:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    def event_odds(self, event_id: str | int) -> dict[str, Any] | None:
        return self.data.get(str(event_id))


def test_offer_marks_a_started_match_and_keeps_none_of_its_live_prices() -> None:
    fixture = dataclasses_replace_tennis()
    started = fixture.model_copy(update={"superbet_event_ids": ["s"]})
    upcoming = fixture.model_copy(
        update={"sofascore_event_id": 2, "superbet_event_ids": ["u"]}
    )
    fetcher = OfferFetcher(_Client({"s": STARTED, "u": NOT_STARTED}))
    by_id = {o.sofascore_event_id: o for o in fetcher.fetch_offers([started, upcoming])}

    assert by_id[1].superbet_started_utc is not None
    assert by_id[1].rungs == [] and by_id[1].status == "NO_PRICE"
    assert by_id[2].superbet_started_utc is None
    assert by_id[2].status == "PRICED" and by_id[2].rungs


def test_one_started_listing_marks_the_whole_match() -> None:
    # Two Superbet listings of one match: either one seeing the start is enough.
    fixture = dataclasses_replace_tennis().model_copy(
        update={"superbet_event_ids": ["u", "s"]}
    )
    fetcher = OfferFetcher(_Client({"s": STARTED, "u": NOT_STARTED}))
    [offer] = fetcher.fetch_offers([fixture])
    assert offer.superbet_started_utc is not None


def test_a_delisted_duplicate_listing_is_not_a_start() -> None:
    # Lock - Hemery, 2026-10-04 05:47Z, clocks 10:30Z: listing 15285898 was
    # {"1": "finished"} with no metadata, 15285160 still active.
    delisted = {"offerStateStatus": {"1": "finished"}, "metadata": None, "odds": None}
    active = {"offerStateStatus": {"1": "active"}, "metadata": None,
              "odds": NOT_STARTED["odds"]}
    fixture = dataclasses_replace_tennis().model_copy(
        update={"superbet_event_ids": ["a", "d"]}
    )
    fetcher = OfferFetcher(_Client({"a": active, "d": delisted}))
    [offer] = fetcher.fetch_offers([fixture])
    assert offer.superbet_started_utc is None
    assert offer.status == "PRICED"


def _rung(fetched: datetime) -> PricedRung:
    return PricedRung(
        market="games_won_set1_for", subject="Kenta Kawada", line=4.5,
        over_odds=1.6, under_odds=2.2, fetched_at_utc=fetched,
    )


def test_sheet_strips_a_price_fetched_after_superbet_saw_the_start() -> None:
    # Clocks say 2026-09-23 00:00Z; Superbet reported the start at 22:30Z
    # the evening before, so a 22:45Z price is in-play however early it looks.
    fixture = dataclasses_replace_tennis()
    seen = datetime(2026, 9, 22, 22, 30, tzinfo=UTC)
    offer = FixtureOffer(
        sofascore_event_id=1, status="PRICED", unmapped_markets=[],
        rungs=[_rung(datetime(2026, 9, 22, 22, 0, tzinfo=UTC)),
               _rung(datetime(2026, 9, 22, 22, 45, tzinfo=UTC)).model_copy(
                   update={"line": 5.5})],
        superbet_started_utc=seen,
    )
    stripped, keys = strip_in_play_prices(offer, fixture)
    assert keys == {("games_won_set1_for", "Kenta Kawada", 5.5)}
    assert stripped.rungs[0].over_odds == 1.6

    # Without the signal the same offer keeps both prices: the clocks alone
    # could not see it.
    unseen = offer.model_copy(update={"superbet_started_utc": None})
    assert strip_in_play_prices(unseen, fixture)[1] == set()


def test_coupon_refuses_a_started_match_its_clocks_call_upcoming() -> None:
    t = datetime(2026, 9, 17, 10, 0, tzinfo=UTC)
    offer = FixtureOffer(
        sofascore_event_id=1, unmapped_markets=[],
        rungs=[PricedRung(market="shots_on_target_for", subject="Player A",
                          line=1.5, over_odds=2.0, under_odds=2.0,
                          fetched_at_utc=t)],
    )

    def run(o: FixtureOffer) -> Any:
        return build_coupon(
            sheet_rows=[_coupon_row()], fixtures=[_coupon_fixture()], offers=[o],
            vetoes=[], current_time=t, min_kickoff=t + timedelta(minutes=15),
            max_price_age=timedelta(minutes=45),
        )

    assert [s.sofascore_event_id for s in run(offer).coupon.singles] == [1]
    started = offer.model_copy(update={"superbet_started_utc": t})
    assert superbet_started([started]) == {1: t}
    result = run(started)
    assert result.coupon.singles == []
    [dropped] = result.dropped
    assert dropped.reason == "KICKOFF_TOO_SOON"
    assert "Superbet reported the match under way" in dropped.detail


def test_confidence_refuses_a_leg_of_a_match_superbet_reports_started(
    tmp_path: Path,
) -> None:
    # Control: the same day without the signal prints both legs (the clocks
    # in this fixture are far ahead, so only the signal can refuse leg 2).
    (tmp_path / "plain").mkdir()
    (tmp_path / "started").mkdir()
    plain = [_offer(1, ODDS_A, UNDER_A), _offer(2, ODDS_B, UNDER_B)]
    assert _single_ids(_confidence(_day(tmp_path / "plain", plain, []))) == {1, 2}

    started = _offer(2, ODDS_B, UNDER_B)
    started["superbet_started_utc"] = "2026-09-25T04:31:00Z"
    offers = [_offer(1, ODDS_A, UNDER_A), started]
    assert _single_ids(_confidence(_day(tmp_path / "started", offers, []))) == {1}


# ---------------------------------------------------------------------------
# Superbet's start time as the fetch saw it: a third clock
# ---------------------------------------------------------------------------


def test_superbet_kickoff_reads_utcdate() -> None:
    assert superbet_kickoff({"utcDate": "2026-10-04T07:20:00Z"}) == datetime(
        2026, 10, 4, 7, 20, tzinfo=UTC
    )
    assert superbet_kickoff({"utcDate": "not a date"}) is None
    assert superbet_kickoff({}) is None and superbet_kickoff(None) is None


def test_offer_keeps_the_earliest_start_of_the_listings_that_still_quote() -> None:
    # Seggerman - Tajima, 2026-10-04: RESOLVE froze 08:00Z, Superbet moved it
    # to 07:20Z. A delisted duplicate's date is not read.
    moved = {**NOT_STARTED, "utcDate": "2026-10-04T07:20:00Z"}
    later = {**NOT_STARTED, "utcDate": "2026-10-04T08:00:00Z"}
    delisted = {"offerStateStatus": {"1": "finished"}, "odds": None,
                "utcDate": "2026-10-04T01:00:00Z"}
    fixture = dataclasses_replace_tennis().model_copy(
        update={"superbet_event_ids": ["l", "m", "d"]}
    )
    fetcher = OfferFetcher(_Client({"l": later, "m": moved, "d": delisted}))
    [offer] = fetcher.fetch_offers([fixture])
    assert offer.superbet_kickoff_seen_utc == datetime(2026, 10, 4, 7, 20, tzinfo=UTC)


def test_coupon_gates_on_a_start_superbet_moved_earlier() -> None:
    t = datetime(2026, 9, 17, 10, 0, tzinfo=UTC)
    offer = FixtureOffer(
        sofascore_event_id=1, unmapped_markets=[],
        rungs=[PricedRung(market="shots_on_target_for", subject="Player A",
                          line=1.5, over_odds=2.0, under_odds=2.0,
                          fetched_at_utc=t)],
        # The fixture's two clocks say 20:00Z; Superbet now says 10:05Z.
        superbet_kickoff_seen_utc=t + timedelta(minutes=5),
    )
    result = build_coupon(
        sheet_rows=[_coupon_row()], fixtures=[_coupon_fixture()], offers=[offer],
        vetoes=[], current_time=t, min_kickoff=t + timedelta(minutes=15),
        max_price_age=timedelta(minutes=45),
    )
    assert result.coupon.singles == []
    assert [d.reason for d in result.dropped] == ["KICKOFF_TOO_SOON"]


def test_sheet_strips_a_price_fetched_after_the_moved_start() -> None:
    fixture = dataclasses_replace_tennis()  # clocks 2026-09-23 00:00Z
    offer = FixtureOffer(
        sofascore_event_id=1, status="PRICED", unmapped_markets=[],
        rungs=[_rung(datetime(2026, 9, 22, 22, 45, tzinfo=UTC))],
        superbet_kickoff_seen_utc=datetime(2026, 9, 22, 22, 30, tzinfo=UTC),
    )
    assert strip_in_play_prices(offer, fixture)[1] == {
        ("games_won_set1_for", "Kenta Kawada", 4.5)
    }


def test_confidence_gates_on_a_start_superbet_moved_earlier(tmp_path: Path) -> None:
    # The harness fixtures start in 2099; Superbet now says five minutes away.
    soon = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    moved = _offer(2, ODDS_B, UNDER_B)
    moved["superbet_kickoff_seen_utc"] = soon
    offers = [_offer(1, ODDS_A, UNDER_A), moved]
    assert _single_ids(_confidence(_day(tmp_path, offers, []))) == {1}
