"""Where the market put a historical game's lines (audit 2026-10-13 A7).

The history curves of the measured sports (bet.sofa.sport_confidence) are
fitted on lines the replay places itself: `synthetic_lines` puts them at
quantiles of the model's own simulation. Superbet's lines stand where the
market sees the game, so a printed leg at p 0.75 is mostly a line the model
disagrees with the market on - a population the synthetic lines never show
the curve. This module reads Sofascore's historical odds of a finished game
(`/event/{id}/odds/1/all`, cached by scripts/sofa/backfill_event_odds.py)
for ONE thing only: the position of its total and spread lines.

The price never leaves this module: no fractional value is parsed, returned
or stored on a row. The probability of a line stays the score model's
(operator 2026-10-13, O2: "historyczne kursy wyznaczają tylko pozycję linii;
p dalej wyłącznie ze statystyk").
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bet.sofa.names import normalize_name

# Sofascore's market names (checked 2026-10-13 on basketball: Eurocup,
# Euroleague, Israeli Super League, Primera FEB, SuperCup Women).
TOTAL_MARKET = "Game total"
SPREAD_MARKET = "Point spread"
FULL_GAME_PERIOD = "Match"
_SPREAD_CHOICE = re.compile(r"^\(\s*([+-]?\d+(?:\.\d+)?)\s*\)\s*(.+)$")
# The keys of a market kept in the cache: enough to re-read the line and the
# side, nothing a reader could take a price from.
CACHED_MARKET_KEYS = ("marketId", "marketName", "marketPeriod", "marketGroup",
                      "choiceGroup", "isLive")
CACHED_CHOICE_KEYS = ("name", "winning")


@dataclass(frozen=True)
class MarketLines:
    """One finished game's market lines. `totals`: the game total lines;
    `home_handicaps`: the home side's spread (-11.5 = home gives 11.5)."""

    event_id: int
    totals: tuple[float, ...] = ()
    home_handicaps: tuple[float, ...] = ()

    def team_totals(self) -> dict[str, tuple[float, ...]]:
        """Each side's points line implied by a total and a spread posted
        together: home (T - h) / 2, away (T + h) / 2 - the market's own
        split, half a point off an integer (an integer gives the two lines
        around it). Only when the game has exactly one total and one spread
        (two of either name no single split)."""
        if len(self.totals) != 1 or len(self.home_handicaps) != 1:
            return {}
        t, h = self.totals[0], self.home_handicaps[0]
        return {"T1": _half_lines((t - h) / 2.0), "T2": _half_lines((t + h) / 2.0)}


def _half_lines(x: float) -> tuple[float, ...]:
    if abs(x - math.floor(x) - 0.5) < 1e-9:
        return (x,)
    base = round(x)
    return (base - 0.5, base + 0.5)


def trim_markets(body: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """The cached form of an odds payload: the full-game total and spread
    markets, their line and choice names only - every price dropped."""
    out: list[dict[str, Any]] = []
    for m in (body or {}).get("markets") or []:
        if not isinstance(m, Mapping):
            continue
        if m.get("marketName") not in (TOTAL_MARKET, SPREAD_MARKET):
            continue
        kept = {k: m.get(k) for k in CACHED_MARKET_KEYS if k in m}
        kept["choices"] = [{k: c.get(k) for k in CACHED_CHOICE_KEYS if k in c}
                           for c in m.get("choices") or [] if isinstance(c, Mapping)]
        out.append(kept)
    return out


def _float(raw: Any) -> float | None:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _team_matches(choice_team: str, names: Iterable[str]) -> bool:
    key = normalize_name(choice_team)
    return any(key == normalize_name(n) for n in names if n)


def parse_lines(event_id: int, markets: Iterable[Mapping[str, Any]],
                home_names: Iterable[str], away_names: Iterable[str]
                ) -> MarketLines | None:
    """The total and home-spread lines of one game's cached markets, or None
    when it has neither. A spread whose team cannot be named home or away by
    Sofascore's own names is left out (never guessed by choice order). A live
    market (isLive) is not a pre-game line."""
    home = list(home_names)
    away = list(away_names)
    totals: set[float] = set()
    hcps: set[float] = set()
    for m in markets:
        if m.get("isLive") or m.get("marketPeriod") not in (None, FULL_GAME_PERIOD):
            continue
        if m.get("marketName") == TOTAL_MARKET:
            line = _float(m.get("choiceGroup"))
            if line is not None and line > 0:
                totals.add(line)
        elif m.get("marketName") == SPREAD_MARKET:
            for c in m.get("choices") or []:
                got = _SPREAD_CHOICE.match(str(c.get("name") or "").strip())
                if got is None:
                    continue
                h = _float(got.group(1))
                if h is None:
                    continue
                team = got.group(2)
                if _team_matches(team, home):
                    hcps.add(h)
                elif _team_matches(team, away):
                    hcps.add(-h)
    if not totals and not hcps:
        return None
    return MarketLines(event_id, tuple(sorted(totals)), tuple(sorted(hcps)))


def event_names(event: Mapping[str, Any], side: str) -> list[str]:
    team = event.get(side) or {}
    return [str(team[k]) for k in ("name", "shortName") if team.get(k)]


def load_market_lines(path: str | Path) -> dict[int, MarketLines]:
    """event id -> MarketLines from a backfill_event_odds.py cache (JSONL,
    one asked event a line; a 404 or a game without lines yields nothing)."""
    out: dict[int, MarketLines] = {}
    p = Path(path)
    if not p.exists():
        return out
    with p.open(encoding="utf-8") as f:
        for raw in f:
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict) or rec.get("status") != "ok":
                continue
            eid = int(rec["event_id"])
            ml = parse_lines(eid, rec.get("markets") or [],
                             rec.get("home_names") or [],
                             rec.get("away_names") or [])
            if ml is not None:
                out[eid] = ml
    return out
