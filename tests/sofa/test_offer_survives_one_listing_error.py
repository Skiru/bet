"""One Superbet listing that errors is a gap, not a FAILED OFFER (review
2026-10-01: fetch_offers had no per-listing guard)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bet.sofa.contracts import Fixture
from bet.sofa.offer import OfferFetcher


class Client:
    def event_odds(self, su_id: Any) -> Any:
        if su_id == "bad":
            raise RuntimeError("404 Client Error")
        return {"odds": []}


def _fixture(eid: int, su: str) -> Fixture:
    # fetch_offers reads only the ids; the rest of the contract is not the point.
    return Fixture.model_construct(
        sofascore_event_id=eid,
        superbet_event_ids=[su],
        sport="football",
        kickoff_utc=datetime(2026, 10, 1, 18, tzinfo=UTC),
    )


def test_one_bad_listing_is_recorded_and_the_rest_still_fetch() -> None:
    fetcher = OfferFetcher(Client())
    offers = fetcher.fetch_offers([_fixture(1, "bad"), _fixture(2, "good")])
    # The failed fixture has no entry, so a refresh merge keeps its old prices.
    assert [o.sofascore_event_id for o in offers] == [2]
    assert fetcher.errors == [("bad", "RuntimeError: 404 Client Error")]
