"""BOOSTS — Superbet's boosted prices, recorded so they can be graded.

Superbet flags a boosted price in its own offer API: the event carries
`matchTags: "...,price_boost"`, and the boosted odd carries `price_boost` in
its `tags`, its pre-boost price in `extra.originalPrice` ("220:2.900000") and,
for a combination ("SuperBets"), its legs in `oddComponents`, each pointing at
the plain odd of the same event by `oddID`. Nothing in `sofa` read any of it
until 2026-09-23.

The question this answers is the operator's: does Superbet choose what to
boost so that it loses? A boost is +8.6% / +12.4% on the two read that day,
which does not cover the 8.8-19.6% measured Bet Builder markup, and the only
ledger evidence was four slips. Recording every boost with its original price
and grading it the next morning turns the suspicion into a hit rate against
the price's own break-even.

Each leg is classified by `offer.classify_odd`, the function OFFER uses for
the same odd, so a boosted leg settles against exactly the sheet row that
SETTLE graded. This module never computes a combined probability or a price
for a combination: the numbers it prints are Superbet's.
"""

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from bet.sofa.offer import classify_odd
from bet.sofa.superbet import SPORT_BY_ID, odds_items

BOOST_TAG = "price_boost"

Outcome = Literal["WIN", "LOSS", "UNSETTLED"]


class BoostLeg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market_name: str
    selection: str
    line_raw: str | None
    # The plain, unboosted price of this leg on the same screen, when the
    # event lists it. None for a leg Superbet only offers inside the combo.
    leg_price: float | None
    market: str | None = None
    subject: str | None = None
    line: float | None = None
    direction: Literal["OVER", "UNDER"] | None = None
    # Set when the leg cannot be read as a sofa rung; the text is the market
    # name as it would appear in unmapped_markets.
    unmapped: str | None = None


class BoostObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fetched_at_utc: datetime
    boosted_price: float
    original_price: float | None


class Boost(BaseModel):
    model_config = ConfigDict(extra="forbid")
    superbet_event_id: str
    match_name: str
    sport_id: int | None
    kickoff_utc: datetime | None
    odd_uuid: str
    label: str
    boosted_price: float
    original_price: float | None
    boost_level: str | None
    combo: bool
    legs: list[BoostLeg]
    observations: list[BoostObservation]

    @property
    def boost_pct(self) -> float | None:
        if not self.original_price:
            return None
        return self.boosted_price / self.original_price - 1.0

    @property
    def leg_price_product(self) -> float | None:
        """Product of the legs' plain prices - a yardstick for Superbet's
        combination markup, and NOT a price: Superbet never pays it."""
        if not self.combo or not self.legs:
            return None
        out = 1.0
        for leg in self.legs:
            if leg.leg_price is None:
                return None
            out *= leg.leg_price
        return out


def _tags(odd: Mapping[str, Any]) -> set[str]:
    return {t.strip() for t in str(odd.get("tags") or "").split(",") if t.strip()}


def parse_original_price(raw: object) -> float | None:
    """`extra.originalPrice` is "<outcomeId>:<price>", e.g. "220:2.900000"."""
    if raw is None:
        return None
    _, _, price = str(raw).rpartition(":")
    try:
        value = float(price)
    except ValueError:
        return None
    return value if value > 1.0 else None


def _leg(
    item: Mapping[str, Any], leg_price: float | None, sport_id: object
) -> BoostLeg:
    raw = item.get("specialBetValue")
    leg = BoostLeg(
        market_name=str(item.get("marketName") or ""),
        selection=str(item.get("name") or ""),
        line_raw=None if raw in (None, "") else str(raw),
        leg_price=leg_price,
    )
    # The market mapper knows football and tennis names only, and a handball
    # "Powyżej 60.5 goli w meczu" reads as football goals_total. On
    # 2026-09-23 that was MKS Kalisz - Ostrów Wielkopolski; off the board it
    # settles nothing, but the label says a thing that is not true.
    if sport_id not in SPORT_BY_ID:
        leg.unmapped = f"sport {sport_id} is not a sofa sport"
        return leg
    classified, unmapped = classify_odd(item)
    if classified is None:
        leg.unmapped = unmapped or f"{leg.market_name} / {leg.selection}"
        return leg
    leg.market, leg.subject, leg.line, direction = classified
    leg.direction = "OVER" if direction == "OVER" else "UNDER"
    return leg


def _price(odd: Mapping[str, Any] | None) -> float | None:
    if not odd or odd.get("price") is None:
        return None
    return float(odd["price"])


def extract_boosts(event: Mapping[str, Any], fetched_at: datetime) -> list[Boost]:
    """Every boosted odd on one event payload (`/events/{id}`)."""
    odds = odds_items(dict(event))
    by_uuid = {str(o.get("uuid")): o for o in odds if o.get("uuid")}
    kickoff_raw = event.get("utcDate")
    kickoff = (
        datetime.fromisoformat(str(kickoff_raw).replace("Z", "+00:00"))
        if kickoff_raw else None
    )
    sport_id = event.get("sportId")
    out: list[Boost] = []
    for odd in odds:
        if BOOST_TAG not in _tags(odd) or odd.get("price") is None:
            continue
        extra = odd.get("extra") or {}
        components = odd.get("oddComponents") or []
        legs: list[BoostLeg] = []
        if components:
            for c in components:
                plain = (by_uuid.get(str(c.get("oddID")))
                         or by_uuid.get(str(c.get("UUID"))))
                if plain is not None:
                    legs.append(_leg(plain, _price(plain), sport_id))
                else:
                    # The combo can carry a leg the event does not list on
                    # its own; its component still names the market and line.
                    spec = c.get("specifiers") or {}
                    legs.append(_leg({
                        "marketName": c.get("marketLineName"),
                        "name": c.get("oddName"),
                        "specialBetValue": spec.get("total"),
                    }, None, sport_id))
        else:
            _, _, src_uuid = str(extra.get("sourceOddUuid") or "").rpartition(":")
            source = by_uuid.get(src_uuid)
            legs.append(_leg(source if source is not None else odd, _price(source),
                             sport_id))
        boosted = float(odd["price"])
        original = parse_original_price(extra.get("originalPrice"))
        out.append(Boost(
            superbet_event_id=str(event.get("eventId")),
            match_name=str(event.get("matchName") or ""),
            sport_id=sport_id,
            kickoff_utc=kickoff,
            odd_uuid=str(odd.get("uuid")),
            label=str(odd.get("name") or odd.get("marketName") or ""),
            boosted_price=boosted,
            original_price=original,
            boost_level=extra.get("boostLevel"),
            combo=bool(components),
            legs=legs,
            observations=[BoostObservation(
                fetched_at_utc=fetched_at, boosted_price=boosted,
                original_price=original)],
        ))
    return out


def is_boosted_event(row: Mapping[str, Any]) -> bool:
    """A `/events/by-date` row whose event carries a boosted price."""
    return BOOST_TAG in {t.strip() for t in str(row.get("matchTags") or "").split(",")}


def merge_snapshots(previous: Iterable[Boost], fresh: Iterable[Boost]) -> list[Boost]:
    """One record per boosted odd across the day's snapshots.

    A boost seen again keeps its first record and gains an observation, and
    its current prices move to the newest: a boost that Superbet re-prices
    between snapshots is graded at the price it last showed, and the history
    stays on disk. A boost that disappears is kept - it was offered.
    """
    merged: dict[str, Boost] = {b.odd_uuid: b for b in previous}
    for b in fresh:
        old = merged.get(b.odd_uuid)
        if old is None:
            merged[b.odd_uuid] = b
            continue
        old.observations.extend(b.observations)
        old.boosted_price = b.boosted_price
        old.original_price = b.original_price
    return list(merged.values())


def grade_boost(
    boost: Boost,
    sofascore_event_id: int | None,
    settled_by_key: Mapping[tuple[int, str, str, float, str], Mapping[str, Any]],
) -> tuple[Outcome, str | None]:
    """WIN / LOSS / UNSETTLED for one boost, and why when unsettled.

    A lost leg loses the boost whatever the others did - including a leg we
    cannot read - which is the same rule `audit_settlement.slip_status` keeps
    (it cost the 2026-09-22 report a slip when it was the other way round).
    A PUSH leg is unsettled: Superbet re-prices a slip with a void leg, and we
    do not know to what.
    """
    if sofascore_event_id is None:
        return "UNSETTLED", "NOT_ON_BOARD"
    outcomes: list[str | None] = []
    for leg in boost.legs:
        if leg.market is None or leg.line is None or leg.direction is None:
            outcomes.append("UNMAPPED")
            continue
        row = settled_by_key.get(
            (sofascore_event_id, leg.market, leg.subject or "", leg.line,
             leg.direction))
        outcomes.append(None if row is None else str(row["outcome"]))
    if "LOSS" in outcomes:
        return "LOSS", None
    if "UNMAPPED" in outcomes:
        return "UNSETTLED", "UNMAPPED_LEG"
    if any(o is None for o in outcomes):
        return "UNSETTLED", "LEG_NOT_SETTLED"
    if any(o != "WIN" for o in outcomes):
        return "UNSETTLED", "LEG_PUSHED"
    return "WIN", None
