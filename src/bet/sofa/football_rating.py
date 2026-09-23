"""Opponent-adjusted attack/defence ratings for football counting markets.

Why this exists. SHEET's centre for a football row was the mean of the two
teams' last ten matches, shrunk toward a league prior. Nothing in it asks who
those ten opponents were: a side that just met five low blocks carries
inflated corners into a match against a side that concedes none, and a total
pooled from both teams' own match totals targets (X + Y) / 2 + mu_opponent,
not X + Y. The literature's fix is the oldest model in the field - Maher
(1982): a team's expected count is the league's rate times its own attack
times the opponent's defence times home advantage - updated match by match by
exponential smoothing, as Wheatcroft (2020, IJF) does for shots and corners.

What it is:

  * one league rate per (competition, metric), a running mean of what one
    side produces there, with its own home/away ratio - so a Liga MX corner
    and a Bundesliga corner are never pooled into one average;
  * per team and metric, an attack and a defence ratio relative to the
    league rate of the match they were earned in, starting at 1.0 (the
    league average) and moved by ``ALPHA`` of each surprise;
  * the forecast for side i against j: rate x home x attack_i x defence_j.

Only the centre changes. The spread SHEET prices around it, the distribution
family and every gate after it are the sample's, as before, and a row priced
this way says so in its notes.

History: every finished football match in the cached listings (goals and
halves read off the score) and every one with cached /statistics (all other
metrics, through ``metrics.extract_metric`` so the quantity is exactly the one
SAMPLES and SETTLE use).
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bet.sofa.contracts import GapReason
from bet.sofa.metrics import (
    extract_flat_statistics,
    extract_metric,
    is_extra_time_event,
)

# The per-side metric every football market in scope is built from. A
# ``_total`` market is the sum of the two sides' forecasts.
BASE_METRICS: tuple[str, ...] = (
    "goals_for",
    "goals_1h_for",
    "goals_2h_for",
    "corners_for",
    "corners_1h_for",
    "corners_2h_for",
    "cards_points_for",
    "fouls_for",
    "fouls_1h_for",
    "offsides_for",
    "shots_for",
    "shots_1h_for",
    "shots_on_target_for",
    "shots_on_target_1h_for",
)
_LISTING_METRICS = frozenset({"goals_for", "goals_1h_for", "goals_2h_for"})

# Smoothing of a team's attack/defence: the weight of one match's surprise,
# per metric, because a metric that is mostly style (shots, fouls) moves with
# the team and one that is mostly noise (bookings) barely does. Chosen on
# history strictly before 2026-09-17 by one-step-ahead squared error per side,
# 2026-06-01..16 (scripts/sofa/measure_football_rating.py reprints it):
#
#   metric               n      last-10  league  rating (at ALPHA)
#   goals_for          60,916   2.337    2.219   2.054
#   corners_for         9,230   8.475    8.281   8.013
#   shots_for           7,404  28.838   29.867  26.792
#   fouls_for           7,924  16.401   17.564  16.124
#   cards_points_for    2,518   2.628    2.432   2.422
#
# Every one of the 14 metrics: the rating beats both the raw last-ten mean
# and the plain league rate - and the raw last-ten mean is WORSE than the
# plain league rate on goals, corners and cards.
ALPHA_BY_METRIC: dict[str, float] = {
    "goals_for": 0.04,
    "goals_1h_for": 0.02,
    "goals_2h_for": 0.03,
    "corners_for": 0.04,
    "corners_1h_for": 0.03,
    "corners_2h_for": 0.03,
    "cards_points_for": 0.01,
    "fouls_for": 0.08,
    "fouls_1h_for": 0.05,
    "offsides_for": 0.05,
    "shots_for": 0.08,
    "shots_1h_for": 0.05,
    "shots_on_target_for": 0.05,
    "shots_on_target_1h_for": 0.04,
}
# The rating's weight against the sample's own (league-shrunk) centre, and the
# markets it is kept out of. Measured on the settled days 2026-09-18..22
# (1,360 matches, 74,712 priced rows) by re-running SHEET and recomputing each
# row at W = 0 / 0.25 / 0.5 / 0.75 / 1 with the sample's own spread: Brier
# 0.1952 / 0.1932 / 0.1928 / 0.1938 / 0.1963 across all markets. At 0.5 on
# every market the improvement is 0.0025 (95% cluster bootstrap 0.0012 to
# 0.0038); with the exclusions below 0.0030 (0.0018 to 0.0043), better on all
# five days. The exclusions were chosen on those same days - each was worse on
# four of five - so the first number is the honest one for the model, the
# second the one SHEET now ships. Neither beats the price (0.1867).
W_FOOTBALL_RATING = 0.5
UNRATED_MARKETS = frozenset(
    {
        "corners_total",       # 0.1915 -> 0.1922, worse on 4 of 5 days
        "corners_1h_total",    # 0.1903 -> 0.1917
        "corners_1h_for",      # 0.2055 -> 0.2060
        "corners_2h_total",    # 0.1792 -> 0.1803
        "corners_2h_for",      # 0.2144 -> 0.2145
        "cards_points_for",    # 0.2197 -> 0.2198, worse on 4 of 5 days
        "offsides_total",      # 0.2312 -> 0.2334, n = 188
    }
)
# Smoothing of a league's own rate and home ratio.
ALPHA_LEAGUE = 0.02
# A league or a team with fewer matches than this is not rated from itself.
MIN_LEAGUE_MATCHES = 30
MIN_TEAM_MATCHES = 5
_RATIO_BOUNDS = (0.2, 5.0)


def base_metric(market: str) -> str | None:
    """``corners_total`` / ``corners_for`` -> ``corners_for``; None if out of scope."""
    if market.endswith("_total"):
        candidate = market[: -len("_total")] + "_for"
    elif market.endswith("_for"):
        candidate = market
    else:
        return None
    return candidate if candidate in BASE_METRICS else None


@dataclass(frozen=True)
class FootballResult:
    event_id: int
    ts: int
    competition_id: int
    home_id: int
    away_id: int
    values: Mapping[str, tuple[float, float]]  # metric -> (home, away)


def _listing_values(event: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    for metric in _LISTING_METRICS:
        h = extract_metric(metric, "football", {}, None, dict(event), True)
        a = extract_metric(metric, "football", {}, None, dict(event), False)
        if not isinstance(h, GapReason) and not isinstance(a, GapReason):
            out[metric] = (h, a)
    return out


def _stats_values(
    event: Mapping[str, Any],
    statistics: dict[str, Any] | None,
    incidents: dict[str, Any] | None,
) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    if is_extra_time_event(dict(event)):
        return out
    flat = extract_flat_statistics(statistics)
    for metric in BASE_METRICS:
        if metric in _LISTING_METRICS:
            continue
        h = extract_metric(metric, "football", flat, incidents, dict(event), True)
        a = extract_metric(metric, "football", flat, incidents, dict(event), False)
        if not isinstance(h, GapReason) and not isinstance(a, GapReason):
            out[metric] = (h, a)
    return out


def parse_event(
    event: Mapping[str, Any],
    statistics: dict[str, Any] | None = None,
    incidents: dict[str, Any] | None = None,
) -> FootballResult | None:
    try:
        if event["tournament"]["category"]["sport"]["slug"] != "football":
            return None
        if (event.get("status") or {}).get("type") != "finished":
            return None
        unique = event["tournament"].get("uniqueTournament") or {}
        competition = unique.get("id", event["tournament"]["id"])
        home, away = event["homeTeam"]["id"], event["awayTeam"]["id"]
        ts = event["startTimestamp"]
    except (KeyError, TypeError):
        return None
    if not isinstance(ts, int):
        return None
    values = _listing_values(event)
    if statistics is not None or incidents is not None:
        values.update(_stats_values(event, statistics, incidents))
    if not values:
        return None
    return FootballResult(
        event_id=int(event["id"]), ts=ts, competition_id=int(competition),
        home_id=int(home), away_id=int(away), values=values,
    )


def load_history(db_path: str | Path) -> list[FootballResult]:
    """Every distinct finished football match in the cache, in time order."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        events: dict[int, dict[str, Any]] = {}
        for (events_json,) in conn.execute(
            "SELECT events_json FROM sofa_entity_events WHERE kind = 'last' "
            "AND events_json LIKE '%\"slug\": \"football\"%'"
        ):
            for event in json.loads(events_json).get("events", []):
                if isinstance(event.get("id"), int):
                    events[event["id"]] = event
        stats: dict[int, tuple[Any, Any]] = {}
        for eid, s_json, i_json in conn.execute(
            "SELECT sofascore_event_id, statistics_json, incidents_json "
            "FROM sofa_event_stats"
        ):
            if eid in events:
                stats[eid] = (
                    json.loads(s_json) if s_json else None,
                    json.loads(i_json) if i_json else None,
                )
    finally:
        conn.close()
    out: list[FootballResult] = []
    for eid, event in events.items():
        s, i = stats.get(eid, (None, None))
        result = parse_event(event, s, i)
        if result is not None:
            out.append(result)
    return sorted(out, key=lambda r: (r.ts, r.event_id))


@dataclass
class _League:
    home_mean: float = 0.0
    away_mean: float = 0.0
    n: int = 0

    def update(self, home: float, away: float) -> None:
        if self.n == 0:
            self.home_mean, self.away_mean = home, away
        else:
            self.home_mean += ALPHA_LEAGUE * (home - self.home_mean)
            self.away_mean += ALPHA_LEAGUE * (away - self.away_mean)
        self.n += 1


@dataclass
class _Team:
    attack: float = 1.0
    defence: float = 1.0
    n: int = 0


def _clamp(x: float) -> float:
    return min(max(x, _RATIO_BOUNDS[0]), _RATIO_BOUNDS[1])


@dataclass
class RatingBook:
    leagues: dict[tuple[int, str], _League] = field(
        default_factory=lambda: defaultdict(_League))
    global_league: dict[str, _League] = field(
        default_factory=lambda: defaultdict(_League))
    teams: dict[tuple[int, str], _Team] = field(
        default_factory=lambda: defaultdict(_Team))

    def league_rates(self, competition: int, metric: str) -> tuple[float, float] | None:
        """(home side's rate, away side's rate) where the match is played."""
        league = self.leagues.get((competition, metric))
        if league is not None and league.n >= MIN_LEAGUE_MATCHES:
            return league.home_mean, league.away_mean
        g = self.global_league.get(metric)
        if g is not None and g.n >= MIN_LEAGUE_MATCHES:
            return g.home_mean, g.away_mean
        return None

    def expected(
        self, competition: int, home: int, away: int, metric: str
    ) -> tuple[float, float] | None:
        rates = self.league_rates(competition, metric)
        if rates is None:
            return None
        th, ta = self.teams[(home, metric)], self.teams[(away, metric)]
        return (
            rates[0] * th.attack * ta.defence,
            rates[1] * ta.attack * th.defence,
        )

    def team_matches(self, team: int, metric: str) -> int:
        t = self.teams.get((team, metric))
        return t.n if t is not None else 0

    def update(self, r: FootballResult) -> None:
        for metric, (vh, va) in r.values.items():
            exp = self.expected(r.competition_id, r.home_id, r.away_id, metric)
            alpha = ALPHA_BY_METRIC.get(metric, 0.04)
            if exp is not None:
                rates = self.league_rates(r.competition_id, metric)
                assert rates is not None
                th = self.teams[(r.home_id, metric)]
                ta = self.teams[(r.away_id, metric)]
                # Each side's surprise, as a ratio to what the league and the
                # opponent led us to expect, moves its attack and the
                # opponent's defence.
                if rates[0] > 0:
                    base_h = rates[0]
                    th_attack = _clamp(th.attack + alpha * (
                        vh / (base_h * ta.defence) - th.attack))
                    ta_defence = _clamp(ta.defence + alpha * (
                        vh / (base_h * th.attack) - ta.defence))
                else:
                    th_attack, ta_defence = th.attack, ta.defence
                if rates[1] > 0:
                    base_a = rates[1]
                    ta_attack = _clamp(ta.attack + alpha * (
                        va / (base_a * th.defence) - ta.attack))
                    th_defence = _clamp(th.defence + alpha * (
                        va / (base_a * ta.attack) - th.defence))
                else:
                    ta_attack, th_defence = ta.attack, th.defence
                th.attack, th.defence = th_attack, th_defence
                ta.attack, ta.defence = ta_attack, ta_defence
                th.n += 1
                ta.n += 1
            self.leagues[(r.competition_id, metric)].update(vh, va)
            self.global_league[metric].update(vh, va)


def replay(history: Iterable[FootballResult], cut_ts: int) -> RatingBook:
    book = RatingBook()
    for r in history:
        if r.ts >= cut_ts:
            break
        book.update(r)
    return book


@dataclass(frozen=True)
class FootballForecast:
    """The rating's expected count for one fixture, per base metric and side."""

    book: RatingBook
    competition_id: int
    home_id: int
    away_id: int

    def centre(self, market: str, side: str | None) -> tuple[float, str] | None:
        """(expected value for this market, note) or None if not rated."""
        metric = base_metric(market)
        if metric is None or market in UNRATED_MARKETS:
            return None
        if (
            self.book.team_matches(self.home_id, metric) < MIN_TEAM_MATCHES
            or self.book.team_matches(self.away_id, metric) < MIN_TEAM_MATCHES
        ):
            return None
        exp = self.book.expected(
            self.competition_id, self.home_id, self.away_id, metric
        )
        if exp is None:
            return None
        league = self.book.leagues.get((self.competition_id, metric))
        where = (
            f"league {self.competition_id} (n={league.n})"
            if league is not None and league.n >= MIN_LEAGUE_MATCHES
            else "global rate (league too thin)"
        )
        th = self.book.teams[(self.home_id, metric)]
        ta = self.book.teams[(self.away_id, metric)]
        detail = (
            f"{where}; home att {th.attack:.2f} def {th.defence:.2f}, "
            f"away att {ta.attack:.2f} def {ta.defence:.2f}"
        )
        if market.endswith("_total"):
            return exp[0] + exp[1], f"home {exp[0]:.2f} + away {exp[1]:.2f}, {detail}"
        if side == "side_a":
            return exp[0], f"home {exp[0]:.2f}, {detail}"
        if side == "side_b":
            return exp[1], f"away {exp[1]:.2f}, {detail}"
        return None


