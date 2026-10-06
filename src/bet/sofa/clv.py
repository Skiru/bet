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

# Below this many independent matches a resampled interval is not an
# interval: with two matches the bootstrap can only ever draw the two
# matches' own means, and audit_clv printed [-9.67%, -3.18%] off 2 legs of
# 2 matches as if it had measured something. Shown as "-" instead.
MIN_CLUSTERS = 20


def cluster_ratio_interval(
    clusters: dict[str, tuple[float, int]],
    seed: int = 7,
    n_boot: int = 2000,
    min_clusters: int = MIN_CLUSTERS,
) -> tuple[float, float] | None:
    """95% interval of sum(value) / sum(count) from resampling whole
    clusters (one cluster = one match: `{key: (value_sum, count)}`).

    None below `min_clusters` clusters with a count - too few independent
    pieces of evidence for any interval to mean what it says.
    """
    pieces = [(float(v), int(c)) for v, c in clusters.values() if int(c) > 0]
    if len(pieces) < min_clusters:
        return None
    rng = random.Random(seed)
    stats = []
    for _ in range(n_boot):
        pick = [pieces[rng.randrange(len(pieces))] for _ in pieces]
        stats.append(sum(v for v, _ in pick) / sum(c for _, c in pick))
    stats.sort()
    return stats[int(0.025 * n_boot)], stats[int(0.975 * n_boot)]


@dataclass(frozen=True)
class ClvRow:
    variant: str  # "official", "official:builder_leg", "official:hockey", ...
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
    ci95: tuple[float, float] | None  # None under MIN_CLUSTERS matches
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
    ci95 = cluster_ratio_interval(
        {g: (sum(v), len(v)) for g, v in by_game.items()}, seed, n_boot
    )
    mean = sum(r.clv_ev for r in rs) / len(rs)
    return ClvSummary(
        variant, len(rs), len(by_game), mean, ci95,
        sum(1 for r in rs if r.beat) / len(rs),
    )


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def is_close(minutes_before: float | None) -> bool:
    return (minutes_before is not None
            and CLOSE_MIN_MINUTES <= minutes_before <= CLOSE_MAX_MINUTES)


def graded_close_rows(
    coupon: dict[str, Any], graded: Iterable[dict[str, Any]], variant: str,
    key_fields: Sequence[str],
) -> list[ClvRow]:
    """CLV of printed measured-sport legs (`coupon["legs"]`) against the
    settled lines.

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
