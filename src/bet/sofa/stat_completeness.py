"""Which cached /statistics are frozen in a broken state.

Found 2026-09-28. Sofascore publishes a lower-league match's statistics in two
steps: within a day of the final whistle only the cards (yellowCards,
redCards), the full set - corners, shots, fouls, ~31 keys - days later.
sofa_event_stats caches a finished match forever, so whatever was fetched
first stays. Event 15275908 (Primera B Nacional) was cached 2026-09-21 with 2
keys; re-asked 2026-09-28 it had 31, corners 6-3. A live probe of 20 cached
cards-only matches: 10 of 12 fetched within a day of kick-off now carry
corners, 0 of 8 fetched a week or more after it do - so the late ones are a
league that genuinely publishes only cards, and the early ones are a snapshot.

The cost is double. SETTLE cannot grade the row (40 of the 52 ungraded
variant singles of 2026-09-27 were corners on such matches), and SAMPLES
treats the match as a gap for every later day, so the frozen match silently
drops out of every future sample of both teams.

A match cannot be judged broken by its own keys - a cards-only league is not
a defect. It is judged against its own group: the keys that at least half of
the group's non-empty events carry. Football groups by unique tournament,
tennis by category (ITF Men, Challenger, ATP...), because a tennis
tournament is one week and too few matches to set a norm.

Only the keys a market is priced from count (see ``used_keys``). A first run
over every key flagged 37,193 football matches, and a live probe recovered 1
of 20: what they lacked was punches, errorsLeadToShot, expected goals - keys
Sofascore added in later seasons that no old match will ever get, and that no
sofa market reads.

Pure: no I/O. The script scripts/sofa/audit_stat_completeness.py feeds it.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from bet.sofa.metrics import FOOTBALL_METRICS, TENNIS_METRICS

Verdict = Literal[
    "COMPLETE",  # carries every key and period its group normally has
    "PARTIAL_KEYS",  # non-empty, but missing keys its group normally has
    "PARTIAL_PERIODS",  # every key, but no 1ST/2ND (or per-set) breakdown
    "EMPTY_IN_COVERED",  # nothing, in a group whose matches normally have stats
    "NO_COVERAGE",  # nothing, in a group that normally has nothing
    "NO_NORM",  # too few events in the group to say
]
BROKEN: frozenset[str] = frozenset(
    {"PARTIAL_KEYS", "PARTIAL_PERIODS", "EMPTY_IN_COVERED"}
)

MIN_GROUP_EVENTS = 5
KEY_SHARE = 0.5
COVERAGE_SHARE = 0.5
# The probe measured recovery for matches fetched within a day of kick-off
# (10/12) and none for a week or more (0/8); 72 h is the conservative edge.
FRESH_HOURS = 72.0


# Read by a metric but not a completeness signal: expectedGoals exists for
# some leagues and seasons only, and tiebreaks is recounted from set scores.
_NOT_A_SIGNAL = frozenset({"expectedGoals", "tiebreaks"})


def used_keys(sport: str) -> frozenset[str]:
    """The /statistics keys a sofa metric reads for this sport. Derived keys
    (goals_from_listing, cards_points_from_incidents, ...) carry an underscore
    and come from elsewhere."""
    metrics = FOOTBALL_METRICS if sport == "football" else TENNIS_METRICS
    keys = {str(config["sofascore"]) for config in metrics.values()}
    return frozenset(k for k in keys if "_" not in k) - _NOT_A_SIGNAL


@dataclass(frozen=True)
class EventMeta:
    sport: str
    group_id: int | None
    group_name: str
    start_ts: int | None


@dataclass(frozen=True)
class CachedStats:
    event_id: int
    fetched_ts: float
    keys: frozenset[str]
    periods: frozenset[str]


@dataclass(frozen=True)
class Norm:
    n: int
    covered_share: float
    expected_keys: frozenset[str]
    expected_periods: frozenset[str]


@dataclass(frozen=True)
class Finding:
    event_id: int
    sport: str
    group_id: int | None
    group_name: str
    verdict: Verdict
    missing_keys: tuple[str, ...]
    missing_periods: tuple[str, ...]
    lag_hours: float | None
    start_ts: int | None = None

    @property
    def fresh(self) -> bool:
        """Fetched soon enough after kick-off that a re-fetch likely recovers it."""
        return self.lag_hours is not None and self.lag_hours < FRESH_HOURS


def parse_statistics(
    statistics_json: str | None,
) -> tuple[frozenset[str], frozenset[str]]:
    """(keys of the ALL period, every period present) of one /statistics body."""
    if not statistics_json:
        return frozenset(), frozenset()
    try:
        body = json.loads(statistics_json)
    except ValueError:
        return frozenset(), frozenset()
    keys: set[str] = set()
    periods: set[str] = set()
    for period in body.get("statistics") or []:
        name = period.get("period")
        if isinstance(name, str):
            periods.add(name)
        if name != "ALL":
            continue
        for group in period.get("groups") or []:
            for item in group.get("statisticsItems") or []:
                key = item.get("key")
                if isinstance(key, str):
                    keys.add(key)
    return frozenset(keys), frozenset(periods)


def event_meta(event: Mapping[str, Any]) -> EventMeta | None:
    """Sport and norm group of one listing event, or None if it has no sport."""
    tournament = event.get("tournament") or {}
    category = tournament.get("category") or {}
    sport = (category.get("sport") or {}).get("slug")
    if not isinstance(sport, str):
        return None
    start = event.get("startTimestamp")
    start_ts = start if isinstance(start, int) else None
    if sport == "tennis":
        gid = category.get("id")
        name = str(category.get("name", ""))
    else:
        unique = tournament.get("uniqueTournament") or {}
        gid = unique.get("id", tournament.get("id"))
        title = unique.get("name", tournament.get("name", ""))
        name = f"{category.get('name', '')} | {title}"
    return EventMeta(sport, gid if isinstance(gid, int) else None, name, start_ts)


def build_norms(
    stats: Iterable[CachedStats], meta: Mapping[int, EventMeta]
) -> dict[tuple[str, int | None], Norm]:
    """Per (sport, group): what at least half of its non-empty events carry."""
    by_group: dict[tuple[str, int | None], list[CachedStats]] = defaultdict(list)
    for s in stats:
        m = meta.get(s.event_id)
        if m is not None:
            by_group[(m.sport, m.group_id)].append(s)
    norms: dict[tuple[str, int | None], Norm] = {}
    for key, events in by_group.items():
        wanted = used_keys(key[0])
        non_empty = [e for e in events if e.keys]
        keys = Counter(k for e in non_empty for k in e.keys & wanted)
        periods = Counter(p for e in non_empty for p in e.periods)
        floor = KEY_SHARE * len(non_empty)
        norms[key] = Norm(
            n=len(events),
            covered_share=len(non_empty) / len(events),
            expected_keys=frozenset(k for k, c in keys.items() if c >= floor),
            expected_periods=frozenset(p for p, c in periods.items() if c >= floor),
        )
    return norms


def classify(s: CachedStats, m: EventMeta | None, norm: Norm | None) -> Finding:
    lag = None
    if m is not None and m.start_ts is not None:
        lag = (s.fetched_ts - m.start_ts) / 3600.0

    def finding(
        verdict: Verdict, keys: Iterable[str] = (), periods: Iterable[str] = ()
    ) -> Finding:
        return Finding(
            s.event_id,
            m.sport if m else "unknown",
            m.group_id if m else None,
            m.group_name if m else "",
            verdict,
            tuple(sorted(keys)),
            tuple(sorted(periods)),
            lag,
            m.start_ts if m else None,
        )

    if m is None or norm is None or norm.n < MIN_GROUP_EVENTS:
        return finding("NO_NORM")
    if not s.keys:
        # A group whose events carry no key any market reads (a cards-only
        # league) cannot make an empty match a loss.
        if norm.covered_share >= COVERAGE_SHARE and norm.expected_keys:
            return finding("EMPTY_IN_COVERED", norm.expected_keys)
        return finding("NO_COVERAGE")
    missing = norm.expected_keys - s.keys  # the norm holds used keys only
    if missing:
        return finding("PARTIAL_KEYS", missing, norm.expected_periods - s.periods)
    missing_periods = norm.expected_periods - s.periods
    if missing_periods:
        return finding("PARTIAL_PERIODS", (), missing_periods)
    return finding("COMPLETE")
