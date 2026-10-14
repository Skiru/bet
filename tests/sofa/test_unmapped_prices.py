"""bet.sofa.unmapped_prices: OFFER records the unmapped odds' prices and
nothing else changes (2026-10-14: the outside-box shot markets had a model
and no price history to measure it against)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from bet.sofa import offer as offer_mod
from bet.sofa import unmapped_prices
from tests.sofa.offer_mappable_scenarios import FROZEN, _Client, fixture, payloads


def _fetch(record: bool) -> offer_mod.OfferFetcher:
    data = payloads()
    fixtures = [fixture(sport, str(p["eventId"])) for sport, p in sorted(data.items())]
    saved = offer_mod.now
    offer_mod.now = lambda: FROZEN  # type: ignore[assignment]
    try:
        fetcher = offer_mod.OfferFetcher(_Client(data), ampersand_subjects=True,
                                         record_unmapped=record)
        fetcher.offers = fetcher.fetch_offers(fixtures)  # type: ignore[attr-defined]
    finally:
        offer_mod.now = saved  # type: ignore[assignment]
    return fetcher


def test_recording_changes_no_offer_byte() -> None:
    off, on = _fetch(False), _fetch(True)
    assert [o.model_dump(mode="json") for o in off.offers] == \
        [o.model_dump(mode="json") for o in on.offers]  # type: ignore[attr-defined]
    assert off.unmapped_odds == []


def test_every_recorded_odd_is_an_unmapped_market_with_a_price() -> None:
    fetcher = _fetch(True)
    offers = {o.sofascore_event_id: o for o in fetcher.offers}  # type: ignore[attr-defined]
    assert fetcher.unmapped_odds, "the golden payloads hold unmapped markets"
    for row in fetcher.unmapped_odds:
        assert row["marketName"] in offers[row["sofascore_event_id"]].unmapped_markets
        assert "price" in row and row["fetched_at_utc"].endswith("Z")
    recorded = {(r["sofascore_event_id"], r["marketName"])
                for r in fetcher.unmapped_odds}
    labels = {(eid, m) for eid, o in offers.items() for m in o.unmapped_markets}
    # every unmapped market has its odds recorded; a label with a parse note
    # ("<name> (no line)") is not a market name and may have none
    assert all(x in recorded or x[1].endswith(")") for x in labels)


def test_write_read_round_trip_and_never_overwrite(tmp_path: Path) -> None:
    stamp = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
    rows = [{"sofascore_event_id": 1, "marketName": "M", "price": 2.5}]
    first = unmapped_prices.write(tmp_path, rows, stamp)
    second = unmapped_prices.write(tmp_path, rows, stamp)
    assert first is not None and second is not None and first != second
    assert list(unmapped_prices.read(tmp_path)) == rows + rows
    assert unmapped_prices.write(tmp_path, [], stamp) is None
