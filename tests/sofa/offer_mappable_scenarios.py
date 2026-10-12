"""OFFER run over two real Superbet payloads, for the MAPPABLE_FAMILIES switch.

`golden/offer_mappable_items.json` holds the non-combination odds (at most six
per market name) of two real Superbet events fetched 2026-10-12 for 10-13:
Villarreal - Napoli (football, 437 market names) and Alexander Zverev -
Alexander Bublik (tennis, 124). `offer_dump(None)` is OFFER as it was before
the switch existed; `golden/offer_mappable_off.json` is that output, written
from the commit the switch was added on top of (40b42923) by
`golden/make_offer_mappable_golden.py`, and with the switch off the working
tree must reproduce it byte for byte.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa import offer as offer_mod
from bet.sofa.contracts import Fixture

GOLDEN_DIR = Path(__file__).parent / "golden"
ITEMS = GOLDEN_DIR / "offer_mappable_items.json"
FROZEN = datetime(2026, 10, 12, 21, 0, tzinfo=UTC)

_SIDES = {
    "football": ("Villarreal", "Napoli"),
    "tennis": ("Alexander Zverev", "Alexander Bublik"),
}


def payloads() -> dict[str, dict[str, Any]]:
    data: dict[str, dict[str, Any]] = json.loads(ITEMS.read_text(encoding="utf-8"))
    return data


def fixture(sport: str, event_id: str) -> Fixture:
    home, away = _SIDES[sport]
    return Fixture(
        sofascore_event_id=int(event_id), superbet_event_ids=[event_id],
        sport=sport,  # type: ignore[arg-type]
        kickoff_utc=FROZEN, home_name=home, away_name=away,
        home_entity_id=1, away_entity_id=2, competition_name="C",
        competition_id=3, season_id=4, category_name="X", identity="CONFIRMED",
        round_number=None, round_name=None, cup_round_type=None,
        previous_leg_event_id=None, venue_name=None, referee=None,
        ground_type=None, default_period_count=3 if sport == "tennis" else 2,
    )


class _Client:
    def __init__(self, data: dict[str, dict[str, Any]]) -> None:
        self.by_id = {str(p["eventId"]): p for p in data.values()}

    def event_odds(self, event_id: str) -> dict[str, Any]:
        payload = dict(self.by_id[str(event_id)])
        # Pre-match: the frozen clock sits before the payload's utcDate.
        return payload


def offer_dump(mappable_families: bool | None) -> list[dict[str, Any]]:
    """04_offer.json's entries for the two events; None = no keyword at all."""
    data = payloads()
    fixtures = [fixture(sport, str(p["eventId"])) for sport, p in sorted(data.items())]
    saved = offer_mod.now
    offer_mod.now = lambda: FROZEN  # type: ignore[assignment]
    try:
        client = _Client(data)
        if mappable_families is None:
            fetcher = offer_mod.OfferFetcher(client, ampersand_subjects=True)
        else:
            fetcher = offer_mod.OfferFetcher(  # type: ignore[call-arg]
                client, ampersand_subjects=True,
                mappable_families=mappable_families,
            )
        offers = fetcher.fetch_offers(fixtures)
    finally:
        offer_mod.now = saved  # type: ignore[assignment]
    return [o.model_dump(mode="json") for o in offers]


def dumps(entries: list[dict[str, Any]]) -> str:
    """The bytes run_offer writes for a list of entries (indent 2)."""
    return json.dumps(entries, indent=2)
