"""Closing line value: was the price we printed better than the price at the
close?

Every practitioner source read on 2026-10-01 (Pinnacle's betting resources,
Buchdahl's closing-line work, the CLV trackers of Trademate / OddsJam, the
open-source backtesters that publish a number at all) treats beating the
closing line as THE test of a selection: per bet its spread is about ten
times smaller than profit and loss, so skill shows in tens of bets instead of
thousands. sofa had no such measurement anywhere.

The closing price here is Superbet's own, devigged by the pipeline's power
method: a soft book's close, which tells whether Superbet moved toward the
printed leg - weaker than a sharp close, and on a line Superbet never moves it
says nothing (a zero there is "untested", not "neutral").

    clv_ev = odds_taken * p_close - 1

is the expected return of the leg at the closing probability; `beat` is
odds_taken > closing odds of the same side.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bet.sofa.engine import devig, devig_many

# A close is a price taken this close to the start, and not after it.
CLOSE_MIN_MINUTES = 3.0
CLOSE_MAX_MINUTES = 30.0


@dataclass(frozen=True)
class ClvRow:
    variant: str  # "official", "wariant", "sport:hockey", ...
    game: str  # cluster key: one match
    leg: str  # a readable label
    odds_taken: float
    odds_close: float
    p_close: float  # the side's devigged closing probability

    @property
    def clv_ev(self) -> float:
        return self.odds_taken * self.p_close - 1.0

    @property
    def beat(self) -> bool:
        return self.odds_taken > self.odds_close


def two_way_close(
    odds_side: float | None, odds_other: float | None
) -> float | None:
    """The side's devigged probability from a closing two-way pair."""
    pair = devig(odds_side, odds_other)
    return None if pair is None else pair[0]


def group_close(odds: dict[str, float], side: str) -> float | None:
    """The side's devigged probability in a closing group of any width."""
    if side not in odds or len(odds) < 2:
        return None
    sides = sorted(odds)
    fair = devig_many([1.0 / odds[s] for s in sides])
    return None if fair is None else fair[sides.index(side)]


@dataclass(frozen=True)
class ClvSummary:
    variant: str
    legs: int
    games: int
    mean_clv_ev: float
    ci95: tuple[float, float]
    beat_share: float


def summarize(rows: Sequence[ClvRow], variant: str, seed: int = 7,
              n_boot: int = 2000) -> ClvSummary | None:
    """Mean CLV with a 95% interval from resampling whole matches - legs of
    one match are one bet in several pieces, not independent evidence."""
    rs = [r for r in rows if r.variant == variant]
    if not rs:
        return None
    by_game: dict[str, list[float]] = defaultdict(list)
    for r in rs:
        by_game[r.game].append(r.clv_ev)
    games = list(by_game)
    rng = random.Random(seed)
    stats = []
    for _ in range(n_boot):
        pick = [games[rng.randrange(len(games))] for _ in games]
        total = sum(sum(by_game[g]) for g in pick)
        count = sum(len(by_game[g]) for g in pick)
        stats.append(total / count)
    stats.sort()
    mean = sum(r.clv_ev for r in rs) / len(rs)
    return ClvSummary(
        variant, len(rs), len(games), mean,
        (stats[int(0.025 * n_boot)], stats[int(0.975 * n_boot)]),
        sum(1 for r in rs if r.beat) / len(rs),
    )


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def is_close(minutes_before: float | None) -> bool:
    return (minutes_before is not None
            and CLOSE_MIN_MINUTES <= minutes_before <= CLOSE_MAX_MINUTES)


def sport_coupon_rows(
    coupon: dict[str, Any], graded: Iterable[dict[str, Any]], variant: str,
    key_fields: Sequence[str],
) -> list[ClvRow]:
    """CLV of a sport coupon's printed legs against the settled lines.

    SHADOW_SETTLE / CS2_SETTLE grade each line at its latest pre-start
    snapshot - the close - and record that price and its partner (or group)
    with `minutes_before_kickoff`. A leg is matched to its graded side by the
    line's key; one whose close is not within CLOSE_* minutes is left out.
    """
    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for g in graded:
        by_key[tuple(g.get(k) for k in key_fields)] = g
    out: list[ClvRow] = []
    for leg in coupon.get("legs", []):
        found = by_key.get(tuple(leg.get(k) for k in key_fields))
        if found is None:
            continue
        g = found
        minutes = g.get("minutes_before_kickoff")
        if minutes is None and g.get("fetched_at_utc") and leg.get("kickoff_utc"):
            # CS2's graded sides carry the fetch time, not the minutes
            minutes = (_utc(str(leg["kickoff_utc"]))
                       - _utc(str(g["fetched_at_utc"]))).total_seconds() / 60
        if not is_close(minutes):
            continue
        group = g.get("group_odds")
        if isinstance(group, dict) and len(group) > 2:
            p = group_close({str(k): float(v) for k, v in group.items()}, g["side"])
        else:
            p = two_way_close(g.get("odds"), g.get("partner_odds"))
        if p is None or not math.isfinite(p):
            continue
        out.append(ClvRow(variant, str(leg.get("superbet_event_id")),
                          str(leg.get("label") or leg.get("family")),
                          float(leg["odds"]), float(g["odds"]), p))
    return out
