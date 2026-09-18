from typing import Any

from bet.sofa.contracts import Fixture, FixtureOffer, PricedRung
from bet.sofa.market_mapper import classify_derived_market, classify_market
from bet.sofa.superbet import odds_items
from bet.sofa.timeutil import now



def parse_line(raw_line: object, market: str) -> float:
    """The number Superbet quoted, for markets that scope a line to a period.

    A plain market sends ``specialBetValue`` as "4.5". A set-scoped one sends
    **"1-4.5"** — the set number, a dash, then the line. Reading that with
    ``float`` raises, and every per-set aces, double-faults and combined rung
    on the 2026-09-18 board landed in unmapped_markets as "unparseable line:
    '1-1.5'" (F45). The market name and the prefix carry the same scope, so
    the prefix is not information — but it is a *check*, and a rung whose
    prefix disagrees with its own market name would be a set-1 price on a
    set-2 ladder, which is worse than no rung at all.

    Raises ValueError with the text that goes into unmapped_markets.
    """
    if isinstance(raw_line, int | float):
        return float(raw_line)

    text = str(raw_line).strip()
    try:
        return float(text)
    except ValueError:
        pass

    prefix, _, rest = text.partition("-")
    if rest:
        try:
            line = float(rest)
        except ValueError:
            raise ValueError(f"unparseable line: {raw_line!r}") from None

        scope = None
        for token, name in (("set1", "1"), ("set2", "2"), ("set3", "3")):
            if token in market:
                scope = name
        for token, name in (("_1h", "1"), ("_2h", "2")):
            if token in market:
                scope = name
        if scope is not None and prefix.strip() != scope:
            raise ValueError(
                f"scope prefix {prefix.strip()!r} disagrees with market {market!r}"
            )
        if scope is None:
            # An unscoped market has no business carrying a scope prefix.
            raise ValueError(f"unexpected scope prefix on {market!r}: {raw_line!r}")
        return line

    raise ValueError(f"unparseable line: {raw_line!r}")

class OfferFetcher:
    def __init__(self, client: Any) -> None:
        self.client = client

    def fetch_offers(self, fixtures: list[Fixture]) -> list[FixtureOffer]:
        results = []
        for fixture in fixtures:
            combined_odds: dict[tuple[str, str, float], dict[str, Any]] = {}
            unmapped = set()

            for su_id in fixture.superbet_event_ids:
                items = odds_items(self.client.event_odds(su_id))
                if not items:
                    continue

                fetched_at = now()

                for item in items:
                    market_name = item.get("marketName")
                    if not market_name:
                        continue

                    raw_line = item.get("specialBetValue")
                    selection_name = item.get("name")

                    classified = classify_market(market_name)
                    if classified:
                        market, subject = classified

                        # A market with no line (or a null one) is not a rung
                        # on a ladder. Reading it as 0.0 invents a line nobody
                        # quoted; letting the TypeError escape takes the whole
                        # day's OFFER down over one malformed market.
                        if raw_line is None or raw_line == "":
                            unmapped.add(f"{market_name} (no line)")
                            continue
                        try:
                            line = parse_line(raw_line, market)
                        except ValueError as exc:
                            unmapped.add(f"{market_name} ({exc})")
                            continue

                        name_lower = str(selection_name or "").lower()
                        direction = None
                        if "poniżej" in name_lower or "under" in name_lower:
                            direction = "UNDER"
                        elif "powyżej" in name_lower or "over" in name_lower:
                            direction = "OVER"

                        if not direction:
                            continue
                    else:
                        # The both-teams, comparative and handicap families.
                        # They carry their line and their side on the
                        # *selection*, not on a shared specialBetValue, so they
                        # cannot go through the branch above (F39).
                        derived = classify_derived_market(
                            market_name,
                            selection_name,
                            str(raw_line) if raw_line not in (None, "") else None,
                        )
                        if not derived:
                            unmapped.add(market_name)
                            continue
                        market, subject, line, direction = derived

                    price = item.get("price")
                    if price is None:
                        continue

                    key = (market, subject, line)
                    if key not in combined_odds:
                        combined_odds[key] = {
                            "over_odds": None,
                            "under_odds": None,
                            "fetched_at_utc": fetched_at,
                            "collisions": [],
                        }

                    # Two listings of one match must not silently overwrite
                    # each other's price (F27). 20 of 484 fixtures carried two
                    # superbet_event_ids; merging by union is right and
                    # recovers a listing that is still live, but a *collision*
                    # decided by arrival order is not a merge, it is a coin
                    # flip on the only number the whole decision rests on. A
                    # higher price invents an edge that is not there; a lower
                    # one hides value that is.
                    #
                    # Take the more conservative quote — the lower one, for the
                    # side being priced — and record the disagreement.
                    field = "over_odds" if direction == "OVER" else "under_odds"
                    new_price = float(price)
                    existing = combined_odds[key][field]
                    if existing is not None and existing != new_price:
                        combined_odds[key]["collisions"].append(
                            f"{direction} {market} {subject or '-'} @ {line}: "
                            f"{existing} vs {new_price}, taking "
                            f"{min(existing, new_price)}"
                        )
                        new_price = min(existing, new_price)
                    combined_odds[key][field] = new_price

            rungs = []
            price_collisions: list[str] = []
            for (market, subject, line), odds_dict in combined_odds.items():
                price_collisions.extend(odds_dict["collisions"])
                rungs.append(
                    PricedRung(
                        market=market,
                        subject=subject,
                        line=line,
                        over_odds=odds_dict["over_odds"],
                        under_odds=odds_dict["under_odds"],
                        fetched_at_utc=odds_dict["fetched_at_utc"],
                    )
                )

            results.append(
                FixtureOffer(
                    sofascore_event_id=fixture.sofascore_event_id,
                    status="PRICED" if rungs else "NO_PRICE",
                    rungs=rungs,
                    unmapped_markets=sorted(list(unmapped)),
                    price_collisions=sorted(price_collisions),
                )
            )

        return results
