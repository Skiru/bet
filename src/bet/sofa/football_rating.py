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
import math
import pickle
import sqlite3
from collections import Counter, defaultdict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from bet.sofa.atomic import write_bytes_atomic
from bet.sofa.contracts import GapReason
from bet.sofa.listing_index import index_fingerprint, iter_indexed_events
from bet.sofa.metrics import (
    extract_flat_statistics,
    extract_metric,
    is_extra_time_event,
)
from bet.sofa.reserve_squads import (
    RESERVE_COMPETITIONS,
    TeamMatch,
    reserve_event_ids,
    reserve_fingerprint,
)
from bet.sofa.resolve import sofascore_gender
from bet.sofa.samples import FRIENDLY_COMPETITION_IDS

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

# --- League strength (2026-09-30) -------------------------------------------
#
# A team's attack and defence are ratios to the league rate of the match they
# were earned in, so they are comparable only between teams that share a
# league. FK Aktobe (women) won 20-0, 15-0 and 12-0 in Kazakhstan, carried
# attack 2.54 / defence 0.35 into the UEFA Europa Cup, Women and was forecast
# to outscore Ajax 2.59 - 1.45 a week after losing to them 0-8.
#
# Two teams are LINKED when, inside LINK_WINDOW_S, both played at least
# LINK_MIN_MATCHES in one competition: their ratios share a denominator. Any
# other pairing (a European cup, a cup against a lower division, a friendly
# between leagues, a promoted side) is priced with a per-(domain, metric)
# strength sigma - log scale, 0 for the pool - learnt only from unlinked
# matches, where it is the only thing that explains the residual. A team's
# domain is its modal competition inside the window. A domain with fewer than
# MIN_STRENGTH_LINKS unlinked matches has no strength, and the pairing is
# UNLINKED: the rating gives no centre and says so.
LINK_WINDOW_S = 365 * 86400
LINK_MIN_MATCHES = 3
TEAM_COMP_MEMORY = 40
ALPHA_STRENGTH = 0.02
MIN_STRENGTH_LINKS = 10
_STRENGTH_BOUNDS = (-2.0, 2.0)
# One match moves a ratio by alpha x (surprise - ratio); a 12-0 against a
# defence rated 0.22 made surprise ~20 and moved Ajax's attack 1.37 -> 2.15 in
# one step. The surprise is capped so no single score can.
MAX_SURPRISE = 3.0
# A team's ratios are shrunk toward 1 (the league average) by this power when
# it meets a side from another league: they were earned against its own
# league and are only partly transportable (Baio & Blangiardo 2010's
# shrinkage). Austria Wien (W), defence 0.23 from the Austrian women's
# league, was forecast 1.28 - 0.68 against Inter (W), whom Superbet made
# favourite (sofa-verifier, 2026-10-01).
# Chosen on one-step-ahead squared error (06-01..08-15, flat between 0.5 and
# 0.7): goals_for held out 08-15..09-30 2.5756 -> 2.5655, cross pairs
# 2.8414 -> ~2.79.
CROSS_RATIO_POWER = 0.6

# Chosen, not fitted on probability: ALPHA_STRENGTH, MIN_STRENGTH_LINKS and
# MAX_SURPRISE were picked on one-step-ahead squared error of the centre
# (06-01..08-15, checked on 08-15..09-30), LINK_MIN_MATCHES by hand. A row
# priced through the rating names them in UNFITTED_CONSTANTS.
RATING_UNFITTED = (
    "ALPHA_STRENGTH", "MIN_STRENGTH_LINKS", "MAX_SURPRISE", "LINK_MIN_MATCHES",
    "CROSS_RATIO_POWER", "LINK_WINDOW_S", "TEAM_COMP_MEMORY")

LINKED = "LINKED"
LINKED_BY_STRENGTH = "LINKED_BY_STRENGTH"
UNLINKED = "UNLINKED"
# The note SHEET puts on every row of an UNLINKED football fixture, which
# CONFIDENCE refuses (confidence.has_cross_league_unlinked_note). Measured on
# 09-20..29 settled rows: the model trails the price by 0.0127 Brier on such
# fixtures against 0.0106 elsewhere; FK Aktobe - Ajax (women) on 09-30 was one.
CROSS_LEAGUE_UNLINKED_NOTE = "CROSS_LEAGUE_UNLINKED"


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
    # A women's match. The global rate a thin league falls back to is kept
    # per gender: the pool is ~90% men's football, and women's leagues score
    # 3.57 goals a match against its 3.17 (baselines, 2026-09-30).
    women: bool = False
    # The side played this match with its second squad under the first team's
    # id (reserve_squads; Londrina's Copa Parana matches, 2026-10-02).
    home_reserve: bool = False
    away_reserve: bool = False


def _listing_values(event: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    ev = event if isinstance(event, dict) else dict(event)
    for metric in _LISTING_METRICS:
        h = extract_metric(metric, "football", {}, None, ev, True)
        a = extract_metric(metric, "football", {}, None, ev, False)
        if (not isinstance(h, GapReason) and not isinstance(a, GapReason)
                and h >= 0 and a >= 0):
            out[metric] = (h, a)
    return out


def _stats_values(
    event: Mapping[str, Any],
    statistics: dict[str, Any] | None,
    incidents: dict[str, Any] | None,
) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    ev = event if isinstance(event, dict) else dict(event)
    if is_extra_time_event(ev):
        return out
    flat = extract_flat_statistics(statistics)
    for metric in BASE_METRICS:
        if metric in _LISTING_METRICS:
            continue
        h = extract_metric(metric, "football", flat, incidents, ev, True)
        a = extract_metric(metric, "football", flat, incidents, ev, False)
        # A count below zero is a provider correction, never a count.
        if (not isinstance(h, GapReason) and not isinstance(a, GapReason)
                and h >= 0 and a >= 0):
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
    # A friendly is excluded from samples (config/sofa_friendly_competitions
    # .json) and from the rating for the same reason: 853 alone held 17,102
    # cached matches, 410 of them won by seven or more, all one "league".
    if competition in FRIENDLY_COMPETITION_IDS:
        return None
    values = _listing_values(event)
    if statistics is not None or incidents is not None:
        values.update(_stats_values(event, statistics, incidents))
    if not values:
        return None
    return FootballResult(
        event_id=int(event["id"]), ts=ts, competition_id=int(competition),
        home_id=int(home), away_id=int(away), values=values,
        women=sofascore_gender(event if isinstance(event, dict) else dict(event))
        == "W",
    )


# Bump when parse_event / the metrics it reads change meaning: a cached
# history parsed by older code is then never reused.
# 2026-10-02.1: calculate_cards_points ignores cards shown to staff (a
# `manager`, no `player`; Superbet komunikat 06/2022 s.2), so cards_points_for
# changes; the history also reads the listed-event index (listing_index.py).
# 2026-10-02.2: a side's second-squad matches are marked (home_reserve /
# away_reserve, reserve_squads) and move no rating.
HISTORY_PARSER_VERSION = "2026-10-02.2"


def history_fingerprint(db_path: str | Path) -> str:
    """What the parsed history depends on: the cached listings and statistics
    (row count and newest fetch of each), the parser, the friendly list and
    the second-squad rule with its list.
    Two loads with the same fingerprint parse to the same history."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.execute("PRAGMA busy_timeout = 60000")
    try:
        lst = conn.execute(
            "SELECT COUNT(*), MAX(fetched_at) FROM sofa_entity_events "
            "WHERE kind = 'last'").fetchone()
        sts = conn.execute(
            "SELECT COUNT(*), MAX(fetched_at) FROM sofa_event_stats").fetchone()
        # The listed-event index feeds the history too (and the one-time fill
        # writes it without touching a page).
        idx = index_fingerprint(conn, "football")
    finally:
        conn.close()
    friendlies = ",".join(str(c) for c in sorted(FRIENDLY_COMPETITION_IDS))
    fp = (
        f"{HISTORY_PARSER_VERSION}|{lst[0]}|{lst[1]}|{sts[0]}|{sts[1]}|{friendlies}"
        f"|reserve:{reserve_fingerprint()}"
    )
    # Appended only once the index holds a football event, so the pickle a
    # SHEET wrote before the index shipped is still reused while it is empty.
    return f"{fp}|idx:{idx}" if idx else fp


def load_history(
    db_path: str | Path, cache_dir: str | Path | None = None
) -> list[FootballResult]:
    """Every distinct finished football match in the cache, in time order.

    Parsing the backfilled cache (913k matches, 2026-10-01) takes ~10 minutes,
    and SHEET runs again after every OFFER refresh. With `cache_dir` the parsed
    history is kept as a pickle under its fingerprint (history_fingerprint)
    and reused while the listings and statistics are unchanged - a rebuild
    after an OFFER refresh writes neither.
    """
    if cache_dir is not None:
        fp = history_fingerprint(db_path)
        path = Path(cache_dir) / "football_history.pkl"
        try:
            stored_fp, history = pickle.loads(path.read_bytes())
            if stored_fp == fp:
                return list(history)
        except (OSError, pickle.PickleError, EOFError, ValueError, TypeError):
            pass
        history = _load_history_uncached(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Per-writer tmp name: two SHEETs (a rebuild beside a day) sharing one
        # ".tmp" interleaved, or the second replace found it gone and crashed.
        write_bytes_atomic(
            path, pickle.dumps((fp, history), protocol=pickle.HIGHEST_PROTOCOL)
        )
        return history
    return _load_history_uncached(db_path)


def _load_history_uncached(db_path: str | Path) -> list[FootballResult]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        events: dict[int, dict[str, Any]] = {}
        # Which page fetch supplied each payload: an indexed copy fetched
        # later (listing_index.py) is the newer one.
        fetched: dict[int, str] = {}
        for events_json, fetched_at in conn.execute(
            "SELECT events_json, fetched_at FROM sofa_entity_events "
            "WHERE kind = 'last' "
            "AND events_json LIKE '%\"slug\": \"football\"%'"
        ):
            for event in json.loads(events_json).get("events", []):
                if isinstance(event.get("id"), int):
                    events[event["id"]] = event
                    fetched[event["id"]] = str(fetched_at)
        # Matches that slid out of every cached page; nothing while the index
        # is empty.
        for event in iter_indexed_events(conn, fetched, sport="football"):
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
    return mark_second_squads(sorted(out, key=lambda r: (r.ts, r.event_id)))


def mark_second_squads(
    history: list[FootballResult],
    listed: Mapping[int, frozenset[int]] = RESERVE_COMPETITIONS,
) -> list[FootballResult]:
    """Mark each side that played a match with its second squad.

    The rule reads the side's whole cached history, so a match can be marked
    by clashes after it - the squad that played it is a fact about the match,
    not its outcome. SAMPLES asks the same question of the listing it holds
    (samples.second_squad_matches).
    """
    per_team: dict[int, list[TeamMatch]] = defaultdict(list)
    for r in history:
        per_team[r.home_id].append(TeamMatch(r.event_id, r.ts, r.competition_id))
        per_team[r.away_id].append(TeamMatch(r.event_id, r.ts, r.competition_id))
    reserve: set[tuple[int, int]] = set()
    for team, matches in per_team.items():
        for eid in reserve_event_ids(matches, listed):
            reserve.add((team, eid))
    if not reserve:
        return history
    return [
        replace(
            r,
            home_reserve=(r.home_id, r.event_id) in reserve,
            away_reserve=(r.away_id, r.event_id) in reserve,
        )
        if (r.home_id, r.event_id) in reserve or (r.away_id, r.event_id) in reserve
        else r
        for r in history
    ]


@dataclass
class _League:
    home_mean: float = 0.0
    away_mean: float = 0.0
    n: int = 0

    def update(self, home: float, away: float) -> None:
        # A plain running mean until 1/(n+1) falls to ALPHA_LEAGUE, then
        # exponential smoothing. Starting the smoothing at the first match
        # left it 32% of the weight after 57: the UAE League Cup's first
        # cached match was 0-0, and its rate read 2.13 goals a match against
        # the 3.12 its 57 matches average (sofa-verifier, 2026-10-01).
        step = max(ALPHA_LEAGUE, 1.0 / (self.n + 1))
        self.home_mean += step * (home - self.home_mean)
        self.away_mean += step * (away - self.away_mean)
        self.n += 1


@dataclass
class _Team:
    attack: float = 1.0
    defence: float = 1.0
    n: int = 0


def _clamp(x: float) -> float:
    return min(max(x, _RATIO_BOUNDS[0]), _RATIO_BOUNDS[1])


@dataclass
class _Strength:
    sigma: float = 0.0
    n: int = 0


def _surprise(value: float, base: float) -> float:
    return min(value / base, MAX_SURPRISE)


@dataclass
class RatingBook:
    leagues: dict[tuple[int, str], _League] = field(
        default_factory=lambda: defaultdict(_League))
    global_league: dict[str, _League] = field(
        default_factory=lambda: defaultdict(_League))
    teams: dict[tuple[int, str], _Team] = field(
        default_factory=lambda: defaultdict(_Team))
    # team -> its last TEAM_COMP_MEMORY (ts, competition), any metric
    team_comps: dict[int, deque[tuple[int, int]]] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=TEAM_COMP_MEMORY)))
    strength: dict[tuple[int, str], _Strength] = field(
        default_factory=lambda: defaultdict(_Strength))
    last_ts: int = 0
    # competition -> whether its matches are women's (the latest seen)
    women_competitions: set[int] = field(default_factory=set)

    @staticmethod
    def _global_key(metric: str, women: bool) -> str:
        return f"{metric}|W" if women else metric

    def _comp_counts(self, team: int) -> Counter[int]:
        since = self.last_ts - LINK_WINDOW_S
        return Counter(c for ts, c in self.team_comps.get(team, ()) if ts >= since)

    def domain(self, team: int) -> int | None:
        """The team's modal competition inside the window, None if unseen."""
        counts = self._comp_counts(team)
        if not counts:
            return None
        top = max(counts.values())
        # tie -> the most recent of the tied competitions
        for _ts, comp in reversed(self.team_comps[team]):
            if counts.get(comp) == top:
                return comp
        return None  # pragma: no cover

    def linked(self, home: int, away: int) -> bool:
        """Both sides played LINK_MIN_MATCHES in a competition that is the
        league (domain) of at least one of them.

        Sharing only the cup being played does not count: Forest U21 and
        Sporting B U21 met in competition 20048 after 3 + 3 matches in it
        while their own leagues shared nothing (sofa-verifier, 2026-09-30),
        and the same rule would have linked Aktobe and Ajax after three UEFA
        matches each.
        """
        return self._linked(home, away, self.domain(home), self.domain(away))

    def _linked(
        self, home: int, away: int, dh: int | None, da: int | None
    ) -> bool:
        ch, ca = self._comp_counts(home), self._comp_counts(away)
        leagues = {dh, da} - {None}
        return any(
            c in leagues and n >= LINK_MIN_MATCHES
            and ca.get(c, 0) >= LINK_MIN_MATCHES
            for c, n in ch.items()
        )

    def link(self, home: int, away: int, metric: str) -> tuple[str, float]:
        """(LINKED | LINKED_BY_STRENGTH | UNLINKED, log factor on home's rate).

        The away side's rate takes the opposite factor."""
        return self._link(
            self.linked(home, away), self.domain(home), self.domain(away), metric)

    def _link(
        self, linked: bool, dh: int | None, da: int | None, metric: str
    ) -> tuple[str, float]:
        if linked:
            return LINKED, 0.0
        if dh is None or da is None:
            return UNLINKED, 0.0
        sh, sa = self.strength.get((dh, metric)), self.strength.get((da, metric))
        if (
            sh is None or sa is None
            or sh.n < MIN_STRENGTH_LINKS or sa.n < MIN_STRENGTH_LINKS
        ):
            return UNLINKED, 0.0
        return LINKED_BY_STRENGTH, sh.sigma - sa.sigma

    def league_rates(self, competition: int, metric: str) -> tuple[float, float] | None:
        """(home side's rate, away side's rate) where the match is played."""
        league = self.leagues.get((competition, metric))
        if league is not None and league.n >= MIN_LEAGUE_MATCHES:
            return league.home_mean, league.away_mean
        g = self.global_league.get(
            self._global_key(metric, competition in self.women_competitions))
        if g is not None and g.n >= MIN_LEAGUE_MATCHES:
            return g.home_mean, g.away_mean
        return None

    def expected(
        self, competition: int, home: int, away: int, metric: str,
        log_factor: float = 0.0, cross: bool = False,
    ) -> tuple[float, float] | None:
        rates = self.league_rates(competition, metric)
        if rates is None:
            return None
        th, ta = self.teams[(home, metric)], self.teams[(away, metric)]
        f = math.exp(log_factor)
        k = CROSS_RATIO_POWER if cross else 1.0
        return (
            rates[0] * f * (th.attack * ta.defence) ** k,
            rates[1] / f * (ta.attack * th.defence) ** k,
        )

    def team_matches(self, team: int, metric: str) -> int:
        t = self.teams.get((team, metric))
        return t.n if t is not None else 0

    def update(self, r: FootballResult) -> None:
        self.last_ts = max(self.last_ts, r.ts)
        women = bool(getattr(r, "women", False))
        if women:
            self.women_competitions.add(r.competition_id)
        else:
            self.women_competitions.discard(r.competition_id)
        # A second squad's match (reserve_squads) moves neither side: the
        # reserve's count is not the first team's, and the opponent's
        # surprise would be measured against the first team's ratios - the
        # wrong opponent. The league it was played in still counts it.
        home_reserve = bool(getattr(r, "home_reserve", False))
        away_reserve = bool(getattr(r, "away_reserve", False))
        if home_reserve or away_reserve:
            for metric, (vh, va) in r.values.items():
                self.leagues[(r.competition_id, metric)].update(vh, va)
                self.global_league[self._global_key(metric, women)].update(vh, va)
            if not home_reserve:
                self.team_comps[r.home_id].append((r.ts, r.competition_id))
            if not away_reserve:
                self.team_comps[r.away_id].append((r.ts, r.competition_id))
            return
        dh, da = self.domain(r.home_id), self.domain(r.away_id)
        linked = self._linked(r.home_id, r.away_id, dh, da)
        for metric, (vh, va) in r.values.items():
            status, lf = self._link(linked, dh, da, metric)
            exp = self.expected(
                r.competition_id, r.home_id, r.away_id, metric, lf,
                cross=status != LINKED)
            alpha = ALPHA_BY_METRIC.get(metric, 0.04)
            if exp is not None:
                rates = self.league_rates(r.competition_id, metric)
                assert rates is not None
                f = math.exp(lf)
                th = self.teams[(r.home_id, metric)]
                ta = self.teams[(r.away_id, metric)]
                # Each side's surprise, as a ratio to what the league, the
                # league-strength gap and the opponent led us to expect, moves
                # its attack and the opponent's defence.
                if rates[0] > 0:
                    base_h = rates[0] * f
                    th_attack = _clamp(th.attack + alpha * (
                        _surprise(vh, base_h * ta.defence) - th.attack))
                    ta_defence = _clamp(ta.defence + alpha * (
                        _surprise(vh, base_h * th.attack) - ta.defence))
                else:
                    th_attack, ta_defence = th.attack, ta.defence
                if rates[1] > 0:
                    base_a = rates[1] / f
                    ta_attack = _clamp(ta.attack + alpha * (
                        _surprise(va, base_a * th.defence) - ta.attack))
                    th_defence = _clamp(th.defence + alpha * (
                        _surprise(va, base_a * ta.attack) - th.defence))
                else:
                    ta_attack, th_defence = ta.attack, th.defence
                # An unlinked match is the only evidence about the gap
                # between two domains: the log residual of the goal (or
                # corner...) difference moves both strengths, in opposite
                # directions, before the ratios absorb anything.
                if (
                    not linked and dh is not None and da is not None
                    and dh != da
                    and self.team_matches(r.home_id, metric) >= MIN_TEAM_MATCHES
                    and self.team_matches(r.away_id, metric) >= MIN_TEAM_MATCHES
                ):
                    resid = (
                        math.log((vh + 0.5) / (exp[0] + 0.5))
                        - math.log((va + 0.5) / (exp[1] + 0.5))
                    ) / 2
                    sh = self.strength[(dh, metric)]
                    sa = self.strength[(da, metric)]
                    lo, hi = _STRENGTH_BOUNDS
                    sh.sigma = min(max(sh.sigma + ALPHA_STRENGTH * resid, lo), hi)
                    sa.sigma = min(max(sa.sigma - ALPHA_STRENGTH * resid, lo), hi)
                    sh.n += 1
                    sa.n += 1
                # A cross-league match moves the ratios too: measured
                # 2026-09-30, moving only the strengths (PandaSkill) was worse.
                th.attack, th.defence = th_attack, th_defence
                ta.attack, ta.defence = ta_attack, ta_defence
                th.n += 1
                ta.n += 1
            self.leagues[(r.competition_id, metric)].update(vh, va)
            self.global_league[self._global_key(metric, women)].update(vh, va)
        self.team_comps[r.home_id].append((r.ts, r.competition_id))
        self.team_comps[r.away_id].append((r.ts, r.competition_id))


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

    def fixture_link(self) -> str:
        """The fixture's link on goals, the metric every football side has.

        Two teams that share no league (inside LINK_WINDOW_S), and whose
        leagues' strengths are unmeasured, are compared by nothing the model
        holds - their ratios and their samples both describe other leagues.
        """
        return self.book.link(self.home_id, self.away_id, "goals_for")[0]

    def link_status(self, market: str) -> str | None:
        """LINKED / LINKED_BY_STRENGTH / UNLINKED for this market's metric."""
        metric = base_metric(market)
        if metric is None:
            return None
        return self.book.link(self.home_id, self.away_id, metric)[0]

    def centre(self, market: str, side: str | None) -> tuple[float, str] | None:
        """(expected value for this market, note) or None if not rated."""
        metric = base_metric(market)
        if metric is None or market in UNRATED_MARKETS:
            return None
        if self.competition_id in FRIENDLY_COMPETITION_IDS:
            return None
        if (
            self.book.team_matches(self.home_id, metric) < MIN_TEAM_MATCHES
            or self.book.team_matches(self.away_id, metric) < MIN_TEAM_MATCHES
        ):
            return None
        # UNLINKED still gets the rating, un-adjusted: measured 2026-09-30
        # (one step ahead, goals_for, 08-15..09-30, 1,596 sides) it beats
        # the raw sample there (3.19 vs 3.78 squared error), which carries
        # the same foreign league inside it. The row is flagged instead - see
        # CROSS_LEAGUE_UNLINKED - and CONFIDENCE defers it to the price.
        status, lf = self.book.link(self.home_id, self.away_id, metric)
        exp = self.book.expected(
            self.competition_id, self.home_id, self.away_id, metric, lf,
            cross=status != LINKED,
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
        if status == UNLINKED:
            detail += "; cross-league UNLINKED: no strength for the gap"
        if status == LINKED_BY_STRENGTH:
            detail += (
                f"; cross-league: domains {self.book.domain(self.home_id)} vs "
                f"{self.book.domain(self.away_id)}, log strength gap {lf:+.2f}"
            )
        if market.endswith("_total"):
            return exp[0] + exp[1], f"home {exp[0]:.2f} + away {exp[1]:.2f}, {detail}"
        if side == "side_a":
            return exp[0], f"home {exp[0]:.2f}, {detail}"
        if side == "side_b":
            return exp[1], f"away {exp[1]:.2f}, {detail}"
        return None


