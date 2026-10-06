"""A Bet Builder's price from Superbet's screen (plan 2026-10-05 production
grade, F4.4).

Superbet does not price a builder as the product of its legs (measured markup
8.8-19.6%, confidence.BUILDER_CORRELATION_HAIRCUT), and no endpoint the repo
uses prices one: bet.sofa.superbet reads the offer (`events_by_date`,
`event_odds`) and nothing else; a builder's price exists only on the slip the
operator builds by hand. Until 2026-10-04 0 of 67 printed builders had a
recorded screen price - every slip ROI was the haircut estimate.

So the price is a manual input, the file the settlement has always read::

    runs/sofa/<d>/09_screen_prices.json
    {
      "<sofascore_event_id>": {
        "odds": 1.62,
        "fetched_at_utc": "2026-10-06T09:41:00Z",
        "source": "operator screen",          # who read it, from where
        "legs": [                              # optional: the slip priced
          {"market": "goals_total", "subject": "", "line": 3.5,
           "direction": "UNDER"}, ...]
      }
    }

A bare number (`"<id>": 1.62`, the format before 2026-10-05) is still read
(no time, no source). From `epochs.BUILDER_SCREEN_PRICE_FROM_UTC` (a day >=
2026-10-06) a builder prints only with a valid screen price and is stakeable
at it (combined p x screen odds >= 0.90); otherwise it is refused, listed in
11_coupon.json with its reason - never silent:

* BUILDER_NO_SCREEN_PRICE - nothing recorded for the fixture;
* BUILDER_SCREEN_PRICE_UNTIMED - a bare number, no `fetched_at_utc`;
* BUILDER_SCREEN_PRICE_AFTER_START - read at or after the kickoff;
* BUILDER_SCREEN_PRICE_OTHER_SLIP - its `legs` are not the builder's legs;
* BUILDER_SCREEN_X_BELOW - p x screen odds < 0.90.

A locked builder (printed before its start) is never touched.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from bet.sofa.market_mapper import fold

SCREEN_PRICES_FILE = "09_screen_prices.json"
SCREEN_RULE = "screen"

NO_SCREEN_PRICE = "BUILDER_NO_SCREEN_PRICE"
UNTIMED = "BUILDER_SCREEN_PRICE_UNTIMED"
AFTER_START = "BUILDER_SCREEN_PRICE_AFTER_START"
OTHER_SLIP = "BUILDER_SCREEN_PRICE_OTHER_SLIP"
X_BELOW = "BUILDER_SCREEN_X_BELOW"

MAX_SCREEN_ODDS = 1000.0


@dataclass(frozen=True)
class ScreenPrice:
    odds: float
    source: str
    fetched_at_utc: str | None = None
    legs: tuple[tuple[str, str, float, str], ...] | None = None


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _leg_key(leg: Mapping[str, Any]) -> tuple[str, str, float, str]:
    return (str(leg["market"]), fold(str(leg.get("subject") or "")),
            float(leg["line"]), str(leg["direction"]))


def load_screen_prices(path: Path) -> dict[str, ScreenPrice]:
    """The recorded screen prices by fixture id; a missing file is none. A
    malformed entry raises (ValueError) - a typo must not read as a price."""
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(f"{path}: an object keyed by sofascore_event_id expected")
    out: dict[str, ScreenPrice] = {}
    for key, entry in doc.items():
        if not str(key).isdigit():
            raise ValueError(f"{path}: key {key!r} is not a sofascore_event_id")
        if isinstance(entry, bool):
            raise ValueError(f"{path}: {key}: odds expected, got {entry!r}")
        if isinstance(entry, int | float):
            odds, fetched, source, legs = float(entry), None, path.name, None
        elif isinstance(entry, dict):
            raw = entry.get("odds")
            if isinstance(raw, bool) or not isinstance(raw, int | float):
                raise ValueError(f"{path}: {key}: `odds` must be a number")
            odds = float(raw)
            fetched = entry.get("fetched_at_utc")
            if fetched is not None:
                try:
                    _utc(str(fetched))
                except ValueError as exc:
                    raise ValueError(f"{path}: {key}: fetched_at_utc "
                                     f"{fetched!r} is not ISO") from exc
                fetched = str(fetched)
            source = str(entry.get("source") or "")
            if not source:
                raise ValueError(f"{path}: {key}: `source` (who read the screen) "
                                 "is required")
            raw_legs = entry.get("legs")
            legs = None
            if raw_legs is not None:
                if not isinstance(raw_legs, list) or not raw_legs:
                    raise ValueError(
                        f"{path}: {key}: `legs` must be a non-empty list")
                try:
                    legs = tuple(sorted(_leg_key(x) for x in raw_legs))
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"{path}: {key}: a leg needs market, line, direction") from exc
        else:
            raise ValueError(f"{path}: {key}: odds or an object expected")
        if not 1.0 < odds <= MAX_SCREEN_ODDS:
            raise ValueError(
                f"{path}: {key}: odds {odds} outside (1, {MAX_SCREEN_ODDS}]")
        out[str(key)] = ScreenPrice(odds, source, fetched, legs)
    return out


def screen_odds_by_event(path: Path) -> dict[str, float]:
    """{fixture id: screen odds} - what the settlement grades a printed
    builder at (audit_settlement 7c, the ledger)."""
    return {k: v.odds for k, v in load_screen_prices(path).items()}


def screen_problem(builder: Mapping[str, Any], price: ScreenPrice | None) -> str | None:
    """Why this recorded price cannot price this builder, or None."""
    if price is None:
        return NO_SCREEN_PRICE
    if price.fetched_at_utc is None:
        return UNTIMED
    kickoff = builder.get("kickoff_utc")
    if kickoff and _utc(price.fetched_at_utc) >= _utc(str(kickoff)):
        return AFTER_START
    if price.legs is not None:
        own = tuple(sorted(_leg_key(x) for x in builder.get("legs") or []))
        if own != price.legs:
            return OTHER_SLIP
    return None


def apply_screen_prices(
    builders: Sequence[Mapping[str, Any]],
    prices: Mapping[str, ScreenPrice],
    required: bool,
    min_x: float,
) -> list[dict[str, Any]]:
    """The builders with their screen price; under the rule (`required`) a
    candidate without a valid one is refused and one with it is stakeable at
    it. Before the rule only the annotation is added."""
    out: list[dict[str, Any]] = []
    for b in builders:
        nb = dict(b)
        price = prices.get(str(b.get("sofascore_event_id")))
        problem = screen_problem(b, price)
        if price is not None:
            nb["screen_odds_recorded"] = price.odds
            nb["screen_odds_source"] = price.source
            nb["screen_odds_fetched_at_utc"] = price.fetched_at_utc
        if problem is None and price is not None:
            nb["screen_odds"] = price.odds
        elif price is not None:
            nb["screen_price_problem"] = problem
        if required and not b.get("locked"):
            nb["builder_price_rule"] = SCREEN_RULE
            if b.get("best_for_fixture"):
                if problem is not None:
                    nb["refusal"] = problem
                else:
                    p = float(b["combined_probability"])
                    x = round(p * float(nb["screen_odds"]), 9)
                    nb["x_at_screen"] = round(x, 4)
                    if x < min_x:
                        nb["refusal"] = X_BELOW
        out.append(nb)
    return out


def refused_builders(builders: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The builders refused for their screen price, as 11_coupon.json lists
    them (the candidates the operator can price and rebuild on)."""
    return [
        {"sofascore_event_id": b.get("sofascore_event_id"),
         "match": b.get("match"), "kickoff_utc": b.get("kickoff_utc"),
         "refusal": b["refusal"],
         "combined_probability": b.get("combined_probability"),
         "odds_after_haircut": b.get("odds_after_haircut"),
         "screen_odds_recorded": b.get("screen_odds_recorded"),
         "legs": [{k: x.get(k) for k in ("market", "subject", "line", "direction",
                                         "odds")} for x in b.get("legs") or []]}
        for b in builders
        if str(b.get("refusal") or "").startswith("BUILDER_")
    ]
